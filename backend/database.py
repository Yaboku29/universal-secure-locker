import re
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


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
        self.password_hasher = PasswordHasher(
            time_cost=3,
            memory_cost=65536,
            parallelism=2,
        )
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

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
                   created_at, updated_at
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
            if parent_id is not None:
                parent = self._get_resource(connection, parent_id)
                if parent["kind"] != "folder":
                    raise ValueError("Folder induk tidak valid.")
                self._require_resource_access(connection, account_id, parent, "read")
                if not self._has_permission(connection, account_id, parent, "create"):
                    raise PermissionError("Tidak memiliki izin membuat item di folder ini.")
            connection.execute(
                """
                INSERT INTO resources
                    (id, owner_id, parent_id, name, kind, content, content_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resource_id,
                    account_id,
                    parent_id,
                    name,
                    kind,
                    content if kind == "file" else None,
                    content_type if kind == "file" else None,
                ),
            )
        return resource_id

    def read_file(self, account_id: int, resource_id: str) -> dict[str, bytes | str]:
        self._validate_account_id(account_id)
        with self._connect() as connection:
            row = self._get_resource(connection, resource_id)
            if row["kind"] != "file":
                raise ValueError("Item tersebut bukan file.")
            self._require_resource_access(connection, account_id, row, "read")
            if row["content"] is None:
                raise RuntimeError("Isi file tidak ditemukan.")
            return {
                "name": str(row["name"]),
                "content_type": str(
                    row["content_type"] or "application/octet-stream"
                ),
                "content": bytes(row["content"]),
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
            connection.execute(
                """
                UPDATE resources
                SET name = ?, content = CASE WHEN ? IS NULL THEN content ELSE ? END,
                    content_type = CASE
                        WHEN ? IS NULL THEN content_type ELSE ? END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    name,
                    content,
                    content,
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