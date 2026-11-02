from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.database import AccountDatabase


class AccountDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.storage_dir = Path(self.temporary_directory.name)
        self.database = AccountDatabase(self.storage_dir)
        self.owner = self.database.create_account("owner", "owner-password-123")
        self.reader = self.database.create_account("reader", "reader-password-123")
        self.outsider = self.database.create_account(
            "outsider", "outsider-password-123"
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_passwords_are_argon2id_hashes_and_first_user_is_admin(self) -> None:
        self.assertTrue(self.owner["is_admin"])
        self.assertFalse(self.reader["is_admin"])
        with closing(sqlite3.connect(self.database.database_path)) as connection:
            stored_hash = connection.execute(
                "SELECT password_hash FROM accounts WHERE username = 'owner'"
            ).fetchone()[0]
        self.assertTrue(stored_hash.startswith("$argon2id$"))
        self.assertNotIn("owner-password-123", stored_hash)
        self.assertEqual(
            self.database.authenticate("OWNER", "owner-password-123")["id"],
            self.owner["id"],
        )
        with self.assertRaisesRegex(ValueError, "Username atau password salah"):
            self.database.authenticate("owner", "wrong-password-123")

    def test_unshared_accounts_cannot_view_or_update_resources(self) -> None:
        file_id = self.database.create_resource(
            self.owner["id"], "private.txt", "file", content=b"private", content_type="text/plain"
        )
        with self.assertRaises(PermissionError):
            self.database.read_file(self.outsider["id"], file_id)
        with self.assertRaises(PermissionError):
            self.database.update_resource(
                self.outsider["id"], file_id, "changed.txt", b"changed", "text/plain"
            )
        self.assertEqual(self.database.list_resources(self.outsider["id"]), [])

    def test_file_size_is_limited(self) -> None:
        with self.assertRaisesRegex(ValueError, "maksimal 10 MiB"):
            self.database.create_resource(
                self.owner["id"],
                "oversized.bin",
                "file",
                content=b"x" * (self.database.max_file_size + 1),
            )

    def test_folder_and_file_permissions_are_independent(self) -> None:
        folder_id = self.database.create_resource(
            self.owner["id"], "shared", "folder"
        )
        file_id = self.database.create_resource(
            self.owner["id"],
            "note.txt",
            "file",
            folder_id,
            b"secret",
            "text/plain",
        )
        self.database.set_resource_permissions(
            self.owner["id"], folder_id, self.reader["id"], False, True, False
        )
        self.assertEqual(
            [item["id"] for item in self.database.list_resources(self.reader["id"])],
            [folder_id],
        )
        self.assertEqual(
            self.database.list_resources(self.reader["id"], folder_id), []
        )
        with self.assertRaises(PermissionError):
            self.database.read_file(self.reader["id"], file_id)

        self.database.set_resource_permissions(
            self.owner["id"], file_id, self.reader["id"], False, True, False
        )
        self.assertEqual(
            self.database.read_file(self.reader["id"], file_id)["content"],
            b"secret",
        )

    def test_create_permission_allows_uploads_only_in_shared_folder(self) -> None:
        folder_id = self.database.create_resource(
            self.owner["id"], "team", "folder"
        )
        with self.assertRaises(PermissionError):
            self.database.create_resource(
                self.reader["id"], "note.txt", "file", folder_id, b"blocked"
            )

        self.database.set_resource_permissions(
            self.owner["id"], folder_id, self.reader["id"], True, False, False
        )
        self.assertTrue(self.database.can_create_in(self.reader["id"], folder_id))
        created_id = self.database.create_resource(
            self.reader["id"],
            "shared-note.txt",
            "file",
            folder_id,
            b"created by reader",
            "text/plain",
        )
        self.assertEqual(
            self.database.read_file(self.reader["id"], created_id)["content"],
            b"created by reader",
        )
        with self.assertRaises(PermissionError):
            self.database.read_file(self.owner["id"], created_id)

    def test_only_owner_or_admin_can_grant_permissions(self) -> None:
        file_id = self.database.create_resource(
            self.reader["id"], "reader-file.txt", "file", content=b"data"
        )
        with self.assertRaises(PermissionError):
            self.database.set_resource_permissions(
                self.outsider["id"], file_id, self.owner["id"], False, True, False
            )

        self.database.set_resource_permissions(
            self.owner["id"], file_id, self.outsider["id"], False, True, False
        )
        self.assertEqual(
            self.database.read_file(self.outsider["id"], file_id)["content"],
            b"data",
        )


if __name__ == "__main__":
    unittest.main()
