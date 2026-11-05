import re
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from backend.security.file_crypto import FileEncryption


class AccountDatabase:
    max_file_size = 10 * 1024 * 1024
    username_pattern = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")
    permission_columns = {
        "create": "can_create",
        "read": "can_read",
        "update": "can_update",
    }

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.database_path = storage_dir / "accounts.db"
        self.users_dir = storage_dir / "users"
        self._file_encryption_key: bytes | None = None
        self.password_hasher = PasswordHasher(
            time_cost=3,
            memory_cost=65536,
            parallelism=2,
        )
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()
        self._migrate_files_to_local_storage()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS resources (
                    id TEXT PRIMARY KEY,
                    owner_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                    parent_id TEXT REFERENCES resources(id),
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK (kind IN ('folder', 'file')),
                    content BLOB,
                    content_type TEXT,
                    storage_path TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS resource_permissions (
                    resource_id TEXT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
                    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                    can_create INTEGER NOT NULL DEFAULT 0,
                    can_read INTEGER NOT NULL DEFAULT 0,
                    can_update INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (resource_id, account_id)
                );

                CREATE INDEX IF NOT EXISTS resources_parent_idx
                    ON resources(parent_id);
                CREATE INDEX IF NOT EXISTS resources_owner_idx
                    ON resources(owner_id);
                CREATE INDEX IF NOT EXISTS permissions_account_idx
                    ON resource_permissions(account_id);
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(resources)")
            }
            if "storage_path" not in columns:
                connection.execute(
                    "ALTER TABLE resources ADD COLUMN storage_path TEXT"
                )

    def _account_directory(self, account_id: int, username: str) -> Path:
        safe_username = self._validate_username(username)
        return self.users_dir / f"account-{account_id}-{safe_username}"

    @staticmethod
    def _relative_resource_path(
        connection: sqlite3.Connection,
        resource_id: str,
        kind: str,
        parent_id: str | None,
    ) -> Path:
        folder_ids: list[str] = []
        while parent_id is not None:
            parent = AccountDatabase._get_resource(connection, parent_id)
            if parent["kind"] != "folder":
                raise ValueError("Folder induk tidak valid.")
            try:
                folder_ids.append(str(uuid.UUID(str(parent["id"]))))
            except ValueError as error:
                raise RuntimeError("ID folder penyimpanan tidak valid.") from error
            parent_id = parent["parent_id"]
        parts = ["items", *reversed(folder_ids)]
        try:
            safe_resource_id = str(uuid.UUID(resource_id))
        except ValueError as error:
            raise RuntimeError("ID item penyimpanan tidak valid.") from error
        if kind == "folder":
            parts.append(safe_resource_id)
        else:
            parts.append(f"{safe_resource_id}.blob")
        return Path(*parts)

    @staticmethod
    def _resolve_storage_path(account_directory: Path, relative_path: Path) -> Path:
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise RuntimeError("Lokasi file akun tidak valid.")
        root = account_directory.resolve()
        path = (root / relative_path).resolve()
        if path == root or not path.is_relative_to(root):
            raise RuntimeError("Lokasi file berada di luar folder akun.")
        return path

    def _migrate_files_to_local_storage(self) -> None:
        self.users_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            accounts = connection.execute(
                "SELECT id, username FROM accounts"
            ).fetchall()
            account_directories = {
                int(account["id"]): self._account_directory(
                    int(account["id"]), str(account["username"])
                )
                for account in accounts
            }
            for directory in account_directories.values():
                directory.mkdir(parents=True, exist_ok=True)

            resources = connection.execute(
                """
                SELECT id, owner_id, parent_id, name, kind, content, storage_path
                FROM resources ORDER BY created_at, id
                """
            ).fetchall()
            for resource in resources:
                owner_id = int(resource["owner_id"])
                owner_directory = account_directories.get(owner_id)
                if owner_directory is None:
                    raise RuntimeError("Folder penyimpanan akun tidak ditemukan.")
                relative_path = (
                    Path(str(resource["storage_path"]))
                    if resource["storage_path"] is not None
                    else self._relative_resource_path(
                        connection,
                        str(resource["id"]),
                        str(resource["kind"]),
                        resource["parent_id"],
                    )
                )
                path = self._resolve_storage_path(owner_directory, relative_path)
                if resource["kind"] == "folder":
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    content = resource["content"]
                    if content is not None:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(bytes(content))
                    elif resource["storage_path"] is None and not path.exists():
                        path.parent.mkdir(parents=True, exist_ok=True)

                connection.execute(
                    """
                    UPDATE resources SET storage_path = ?, content = NULL
                    WHERE id = ?
                    """,
                    (str(relative_path), resource["id"]),
                )

    def activate_file_encryption(self, key: bytes) -> None:
        FileEncryption._validate_key(key)
        self._file_encryption_key = key
        with self._connect() as connection:
            resources = connection.execute(
                """
                SELECT id, owner_id, name, content_type, storage_path
                FROM resources WHERE kind = 'file'
                """
            ).fetchall()
            owners = {
                int(row["id"]): self._account_directory(
                    int(row["id"]), str(row["username"])
                )
                for row in connection.execute(
                    "SELECT id, username FROM accounts"
                ).fetchall()
            }

        for resource in resources:
            owner_directory = owners.get(int(resource["owner_id"]))
            if owner_directory is None or not resource["storage_path"]:
                raise RuntimeError("Lokasi file akun tidak ditemukan.")
            path = self._resolve_storage_path(
                owner_directory, Path(str(resource["storage_path"]))
            )
            try:
                stored_content = path.read_bytes()
            except OSError as error:
                raise RuntimeError("Isi file lokal tidak dapat dibaca.") from error

            should_encrypt = FileEncryption.should_encrypt(
                str(resource["name"]), resource["content_type"]
            )
            is_encrypted = FileEncryption.is_encrypted(stored_content)
            if should_encrypt and not is_encrypted:
                stored_content = FileEncryption.encrypt_bytes(stored_content, key)
            elif not should_encrypt and is_encrypted:
                stored_content = FileEncryption.decrypt_bytes(stored_content, key)
            else:
                continue
            FileEncryption.write_bytes_atomically(path, stored_content)

    def deactivate_file_encryption(self) -> None:
        self._file_encryption_key = None

    @staticmethod
    def _validate_account_id(account_id: int) -> None:
        if not isinstance(account_id, int) or account_id < 1:
            raise ValueError("Akun tidak valid.")

    @staticmethod
    def _validate_username(username: str) -> str:
        if not isinstance(username, str):
            raise ValueError("Username harus berupa teks.")
        username = username.strip()
        if not AccountDatabase.username_pattern.fullmatch(username):
            raise ValueError(
                "Username harus 3–32 karakter dan hanya boleh berisi huruf, "
                "angka, titik, garis bawah, atau tanda hubung."
            )
        return username.lower()

    @staticmethod
    def _validate_password(password: str) -> None:
        if not isinstance(password, str) or not 10 <= len(password) <= 128:
            raise ValueError("Password harus berisi 10–128 karakter.")

    @staticmethod
    def _validate_resource_name(name: str) -> str:
        if not isinstance(name, str):
            raise ValueError("Nama folder/file harus berupa teks.")
        name = name.strip()
        if (
            not name
            or len(name) > 160
            or any(character in name for character in ("/", "\\", "\0"))
            or name in {".", ".."}
        ):
            raise ValueError("Nama harus 1–160 karakter dan tidak boleh berupa path.")
        return name

    @staticmethod
    def _account_dict(row: sqlite3.Row) -> dict[str, int | str | bool]:
        return {
            "id": int(row["id"]),
            "username": str(row["username"]),
            "is_admin": bool(row["is_admin"]),
        }

    def has_accounts(self) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT EXISTS(SELECT 1 FROM accounts)").fetchone()
        return bool(row[0])

    def create_account(
        self, username: str, password: str
    ) -> dict[str, int | str | bool]:
        normalized_username = self._validate_username(username)
        self._validate_password(password)
        password_hash = self.password_hasher.hash(password)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            account_count = connection.execute(
                "SELECT COUNT(*) FROM accounts"
            ).fetchone()[0]
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO accounts (username, password_hash, is_admin)
                    VALUES (?, ?, ?)
                    """,
                    (normalized_username, password_hash, int(account_count == 0)),
                )
            except sqlite3.IntegrityError as error:
                if "accounts.username" in str(error):
                    raise ValueError("Username tersebut sudah digunakan.") from error
                raise
            account_id = int(cursor.lastrowid)
            row = connection.execute(
                "SELECT id, username, is_admin FROM accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
            self._account_directory(account_id, str(row["username"])).mkdir(
                parents=True, exist_ok=True
            )
        return self._account_dict(row)

    def authenticate(
        self, username: str, password: str
    ) -> dict[str, int | str | bool]:
        normalized_username = self._validate_username(username)
        self._validate_password(password)

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, username, password_hash, is_admin
                FROM accounts WHERE username = ? COLLATE NOCASE
                """,
                (normalized_username,),
            ).fetchone()
            if row is None:
                raise ValueError("Username atau password salah.")

            try:
                self.password_hasher.verify(row["password_hash"], password)
            except (VerifyMismatchError, VerificationError, InvalidHashError) as error:
                raise ValueError("Username atau password salah.") from error

            if self.password_hasher.check_needs_rehash(row["password_hash"]):
                connection.execute(
                    "UPDATE accounts SET password_hash = ? WHERE id = ?",
                    (self.password_hasher.hash(password), row["id"]),
                )
            return self._account_dict(row)

    def get_account(self, account_id: int) -> dict[str, int | str | bool]:
        self._validate_account_id(account_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, username, is_admin FROM accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
        if row is None:
            raise ValueError("Akun tidak ditemukan.")
        return self._account_dict(row)

    def list_accounts(self) -> list[dict[str, int | str | bool]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, username, is_admin FROM accounts ORDER BY username"
            ).fetchall()
        return [self._account_dict(row) for row in rows]

    @staticmethod
    def _get_resource(
        connection: sqlite3.Connection, resource_id: str
    ) -> sqlite3.Row:
        if not isinstance(resource_id, str) or not resource_id:
            raise ValueError("Folder/file tidak valid.")
        row = connection.execute(
            """
            SELECT id, owner_id, parent_id, name, kind, content, content_type,
                   storage_path, created_at, updated_at
            FROM resources WHERE id = ?
            """,
            (resource_id,),
        ).fetchone()
        if row is None:
            raise ValueError("Folder/file tidak ditemukan.")
        return row

    @classmethod
    def _has_permission(
        cls,
        connection: sqlite3.Connection,
        account_id: int,
        resource: sqlite3.Row,
        permission: str,
    ) -> bool:
        if permission not in cls.permission_columns:
            raise ValueError("Jenis izin tidak valid.")
        if resource["owner_id"] == account_id:
            return True

        column = cls.permission_columns[permission]
        row = connection.execute(
            f"""
            SELECT {column} FROM resource_permissions
            WHERE resource_id = ? AND account_id = ?
            """,
            (resource["id"], account_id),
        ).fetchone()
        return bool(row and row[0])

    @classmethod
    def _require_resource_access(
        cls,
        connection: sqlite3.Connection,
        account_id: int,
        resource: sqlite3.Row,
        permission: str,
    ) -> None:
        parent_id = resource["parent_id"]
        while parent_id is not None:
            parent = cls._get_resource(connection, parent_id)
            if parent["kind"] != "folder" or not cls._has_permission(
                connection, account_id, parent, "read"
            ):
                raise PermissionError("Tidak memiliki izin melihat folder induk.")
            parent_id = parent["parent_id"]
        if not cls._has_permission(connection, account_id, resource, permission):
            raise PermissionError("Akun ini tidak memiliki izin untuk folder/file tersebut.")

    @staticmethod
    def _resource_dict(
        row: sqlite3.Row,
        account_id: int,
        can_read: bool,
        can_update: bool,
        can_manage: bool,
    ) -> dict[str, int | str | bool | None]:
        return {
            "id": str(row["id"]),
            "name": str(row["name"]),
            "kind": str(row["kind"]),
            "parent_id": row["parent_id"],
            "owner_id": int(row["owner_id"]),
            "is_owner": row["owner_id"] == account_id,
            "can_read": can_read,
            "can_update": can_update,
            "can_manage": can_manage,
            "content_type": row["content_type"],
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    def list_resources(
        self, account_id: int, parent_id: str | None = None
    ) -> list[dict[str, int | str | bool | None]]:
        self._validate_account_id(account_id)
        with self._connect() as connection:
            account = connection.execute(
                "SELECT id FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
            if account is None:
                raise ValueError("Akun tidak ditemukan.")
            if parent_id is not None:
                parent = self._get_resource(connection, parent_id)
                if parent["kind"] != "folder":
                    raise ValueError("Folder induk tidak valid.")
                self._require_resource_access(connection, account_id, parent, "read")
                rows = connection.execute(
                    "SELECT * FROM resources WHERE parent_id = ? ORDER BY kind, name",
                    (parent_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM resources WHERE parent_id IS NULL ORDER BY kind, name"
                ).fetchall()

            visible = []
            is_admin = bool(
                connection.execute(
                    "SELECT is_admin FROM accounts WHERE id = ?", (account_id,)
                ).fetchone()["is_admin"]
            )
            for row in rows:
                try:
                    self._require_resource_access(connection, account_id, row, "read")
                except PermissionError:
                    continue
                can_update = self._has_permission(
                    connection, account_id, row, "update"
                )
                visible.append(
                    self._resource_dict(
                        row,
                        account_id,
                        True,
                        can_update,
                        row["owner_id"] == account_id or is_admin,
                    )
                )
            return visible

    def can_create_in(
        self, account_id: int, parent_id: str | None
    ) -> bool:
        self._validate_account_id(account_id)
        if parent_id is None:
            return True
        with self._connect() as connection:
            parent = self._get_resource(connection, parent_id)
            if parent["kind"] != "folder":
                raise ValueError("Folder induk tidak valid.")
            self._require_resource_access(connection, account_id, parent, "read")
            return self._has_permission(connection, account_id, parent, "create")

    def create_resource(
        self,
        account_id: int,
        name: str,
        kind: str,
        parent_id: str | None = None,
        content: bytes | None = None,
        content_type: str | None = None,
    ) -> str:
        self._validate_account_id(account_id)
        name = self._validate_resource_name(name)
        if kind not in {"folder", "file"}:
            raise ValueError("Jenis item harus folder atau file.")
        if kind == "folder" and content is not None:
            raise ValueError("Folder tidak dapat berisi data file.")
        if kind == "file":
            if not isinstance(content, bytes):
                raise ValueError("Isi file tidak valid.")
            if len(content) > self.max_file_size:
                raise ValueError("Ukuran file maksimal 10 MiB.")
            if not isinstance(content_type, str) or len(content_type) > 255:
                content_type = "application/octet-stream"

        resource_id = str(uuid.uuid4())
        with self._connect() as connection:
            self._insert_resource(
                connection,
                account_id,
                resource_id,
                name,
                kind,
                parent_id,
                content,
                content_type,
            )
        return resource_id

    def _insert_resource(
        self,
        connection: sqlite3.Connection,
        account_id: int,
        resource_id: str,
        name: str,
        kind: str,
        parent_id: str | None,
        content: bytes | None,
        content_type: str | None,
        storage_path: Path | None = None,
    ) -> None:
        if parent_id is not None:
            parent = self._get_resource(connection, parent_id)
            if parent["kind"] != "folder":
                raise ValueError("Folder induk tidak valid.")
            self._require_resource_access(connection, account_id, parent, "read")
            if not self._has_permission(connection, account_id, parent, "create"):
                raise PermissionError("Tidak memiliki izin membuat item di folder ini.")

        account = connection.execute(
            "SELECT username FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if account is None:
            raise ValueError("Akun tidak ditemukan.")
        relative_path = storage_path or self._relative_resource_path(
            connection, resource_id, kind, parent_id
        )
        account_directory = self._account_directory(
            account_id, str(account["username"])
        )
        path = self._resolve_storage_path(account_directory, relative_path)
        if kind == "folder":
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            stored_content = content or b""
            if (
                self._file_encryption_key is not None
                and FileEncryption.should_encrypt(name, content_type)
            ):
                stored_content = FileEncryption.encrypt_bytes(
                    stored_content, self._file_encryption_key
                )
            FileEncryption.write_bytes_atomically(path, stored_content)
        connection.execute(
            """
            INSERT INTO resources
                (id, owner_id, parent_id, name, kind, content, content_type, storage_path)
            VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                resource_id,
                account_id,
                parent_id,
                name,
                kind,
                content_type if kind == "file" else None,
                str(relative_path),
            ),
        )

    def save_encrypted_message(self, account_id: int, message: str) -> str:
        self._validate_account_id(account_id)
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Isi pesan terenkripsi tidak boleh kosong.")
        content = message.encode("utf-8")
        if len(content) > self.max_file_size:
            raise ValueError("Ukuran pesan maksimal 10 MiB.")

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            names = connection.execute(
                """
                SELECT name FROM resources
                WHERE owner_id = ? AND parent_id IS NULL AND kind = 'file'
                """,
                (account_id,),
            ).fetchall()
            used_numbers = {
                int(match.group(1))
                for row in names
                if (match := re.fullmatch(
                    r"pesan_terenkripsi_(\d+)\.txt", str(row["name"]), re.IGNORECASE
                ))
            }
            number = 1
            while number in used_numbers:
                number += 1
            name = f"pesan_terenkripsi_{number}.txt"
            self._insert_resource(
                connection,
                account_id,
                str(uuid.uuid4()),
                name,
                "file",
                None,
                content,
                "text/plain; charset=utf-8",
                Path("items") / name,
            )
        return name

    def read_file(self, account_id: int, resource_id: str) -> dict[str, bytes | str]:
        self._validate_account_id(account_id)
        with self._connect() as connection:
            row = self._get_resource(connection, resource_id)
            if row["kind"] != "file":
                raise ValueError("Item tersebut bukan file.")
            self._require_resource_access(connection, account_id, row, "read")
            owner = connection.execute(
                "SELECT username FROM accounts WHERE id = ?", (row["owner_id"],)
            ).fetchone()
            if owner is None or not row["storage_path"]:
                raise RuntimeError("Lokasi file tidak ditemukan.")
            account_directory = self._account_directory(
                int(row["owner_id"]), str(owner["username"])
            )
            path = self._resolve_storage_path(
                account_directory, Path(str(row["storage_path"]))
            )
            name = str(row["name"])
            content_type = str(
                row["content_type"] or "application/octet-stream"
            )
        try:
            content = path.read_bytes()
        except OSError as error:
            raise RuntimeError("Isi file lokal tidak dapat dibaca.") from error
        if FileEncryption.is_encrypted(content):
            if self._file_encryption_key is None:
                raise PermissionError(
                    "Login ke akun terlebih dahulu untuk mendekripsi file."
                )
            content = FileEncryption.decrypt_bytes(
                content, self._file_encryption_key
            )
        elif (
            self._file_encryption_key is not None
            and FileEncryption.should_encrypt(name, content_type)
        ):
            raise RuntimeError("File dokumen belum terenkripsi pada penyimpanan.")
        return {
            "name": name,
            "content_type": content_type,
            "content": content,
        }

    def update_resource(
        self,
        account_id: int,
        resource_id: str,
        name: str,
        content: bytes | None = None,
        content_type: str | None = None,
    ) -> None:
        self._validate_account_id(account_id)
        name = self._validate_resource_name(name)
        if content is not None and not isinstance(content, bytes):
            raise ValueError("Isi file tidak valid.")
        if content is not None and len(content) > self.max_file_size:
            raise ValueError("Ukuran file maksimal 10 MiB.")
        if content is not None and (
            not isinstance(content_type, str) or len(content_type) > 255
        ):
            content_type = "application/octet-stream"

        with self._connect() as connection:
            row = self._get_resource(connection, resource_id)
            self._require_resource_access(connection, account_id, row, "update")
            if row["kind"] == "file" and content is None:
                raise ValueError("Pilih file baru untuk memperbarui isi file.")
            if row["kind"] == "folder" and content is not None:
                raise ValueError("Folder tidak dapat berisi data file.")
            if row["kind"] == "file":
                owner = connection.execute(
                    "SELECT username FROM accounts WHERE id = ?", (row["owner_id"],)
                ).fetchone()
                if owner is None or not row["storage_path"]:
                    raise RuntimeError("Lokasi file tidak ditemukan.")
                account_directory = self._account_directory(
                    int(row["owner_id"]), str(owner["username"])
                )
                path = self._resolve_storage_path(
                    account_directory, Path(str(row["storage_path"]))
                )
                final_content_type = str(
                    content_type
                    if content_type is not None
                    else row["content_type"] or "application/octet-stream"
                )
                stored_content = content
                if (
                    self._file_encryption_key is not None
                    and FileEncryption.should_encrypt(name, final_content_type)
                ):
                    stored_content = FileEncryption.encrypt_bytes(
                        content, self._file_encryption_key
                    )
                FileEncryption.write_bytes_atomically(path, stored_content)
            connection.execute(
                """
                UPDATE resources
                SET name = ?,
                    content = NULL,
                    content_type = CASE WHEN ? IS NULL THEN content_type ELSE ? END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    name,
                    content_type,
                    content_type,
                    resource_id,
                ),
            )

    def list_accounts_for_sharing(
        self, actor_id: int, resource_id: str
    ) -> dict[str, object]:
        self._validate_account_id(actor_id)
        with self._connect() as connection:
            resource = self._get_resource(connection, resource_id)
            actor = connection.execute(
                "SELECT is_admin FROM accounts WHERE id = ?", (actor_id,)
            ).fetchone()
            if actor is None:
                raise ValueError("Akun tidak ditemukan.")
            if resource["owner_id"] != actor_id and not actor["is_admin"]:
                raise PermissionError("Hanya pemilik item atau admin yang dapat mengatur izin.")

            account_rows = connection.execute(
                """
                SELECT id, username FROM accounts
                WHERE id != ? AND id != ? ORDER BY username
                """,
                (actor_id, resource["owner_id"]),
            ).fetchall()
            permission_rows = connection.execute(
                """
                SELECT account_id, can_create, can_read, can_update
                FROM resource_permissions WHERE resource_id = ?
                """,
                (resource_id,),
            ).fetchall()
        permissions = {
            int(row["account_id"]): {
                "create": bool(row["can_create"]),
                "read": bool(row["can_read"]),
                "update": bool(row["can_update"]),
            }
            for row in permission_rows
        }
        return {
            "resource_id": resource_id,
            "kind": str(resource["kind"]),
            "accounts": [
                {
                    "id": int(row["id"]),
                    "username": str(row["username"]),
                    "permissions": permissions.get(
                        int(row["id"]),
                        {"create": False, "read": False, "update": False},
                    ),
                }
                for row in account_rows
            ],
        }

    def set_resource_permissions(
        self,
        actor_id: int,
        resource_id: str,
        target_account_id: int,
        can_create: bool,
        can_read: bool,
        can_update: bool,
    ) -> None:
        self._validate_account_id(actor_id)
        self._validate_account_id(target_account_id)
        if not all(
            isinstance(value, bool) for value in (can_create, can_read, can_update)
        ):
            raise ValueError("Nilai izin tidak valid.")

        with self._connect() as connection:
            resource = self._get_resource(connection, resource_id)
            actor = connection.execute(
                "SELECT is_admin FROM accounts WHERE id = ?", (actor_id,)
            ).fetchone()
            if actor is None:
                raise ValueError("Akun tidak ditemukan.")
            if resource["owner_id"] != actor_id and not actor["is_admin"]:
                raise PermissionError("Hanya pemilik item atau admin yang dapat mengatur izin.")

            target = connection.execute(
                "SELECT id FROM accounts WHERE id = ?", (target_account_id,)
            ).fetchone()
            if target is None:
                raise ValueError("Akun tujuan tidak ditemukan.")
            if target_account_id == resource["owner_id"]:
                raise ValueError("Pemilik item sudah memiliki akses penuh.")
            if resource["kind"] == "file" and can_create:
                raise ValueError("Izin membuat item hanya berlaku untuk folder.")

            can_read = can_read or can_create or can_update
            if not (can_create or can_read or can_update):
                connection.execute(
                    """
                    DELETE FROM resource_permissions
                    WHERE resource_id = ? AND account_id = ?
                    """,
                    (resource_id, target_account_id),
                )
                return

            connection.execute(
                """
                INSERT INTO resource_permissions
                    (resource_id, account_id, can_create, can_read, can_update)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(resource_id, account_id) DO UPDATE SET
                    can_create = excluded.can_create,
                    can_read = excluded.can_read,
                    can_update = excluded.can_update
                """,
                (
                    resource_id,
                    target_account_id,
                    int(can_create),
                    int(can_read),
                    int(can_update),
                ),
            )