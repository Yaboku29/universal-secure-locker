from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.database import AccountDatabase
from backend.security.file_crypto import FileEncryption


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
        self.database.verify_account_password(
            self.owner["id"], "owner-password-123"
        )
        with self.assertRaisesRegex(ValueError, "Password akun salah"):
            self.database.verify_account_password(
                self.owner["id"], "wrong-password-123"
            )
        with self.assertRaisesRegex(ValueError, "Username atau password salah"):
            self.database.authenticate("owner", "wrong-password-123")

    def test_secret_notes_and_transaction_payloads_are_encrypted(self) -> None:
        key = bytes(range(FileEncryption.key_size))
        self.database.activate_sensitive_data_encryption(key)
        secret = "catatan yang tidak boleh terbaca langsung"

        note_id = self.database.save_secret_note(self.owner["id"], secret)
        with closing(sqlite3.connect(self.database.database_path)) as connection:
            encrypted_note = connection.execute(
                "SELECT encrypted_content FROM secret_notes WHERE id = ?",
                (note_id,),
            ).fetchone()[0]
        self.assertTrue(FileEncryption.is_encrypted(bytes(encrypted_note)))
        self.assertNotIn(secret.encode("utf-8"), bytes(encrypted_note))
        self.assertEqual(
            self.database.get_secret_notes(self.owner["id"])[0]["content"],
            secret,
        )
        self.assertEqual(self.database.get_secret_notes(self.reader["id"]), [])

        first_block = self.database.record_transaction(
            self.owner["id"], "save-note", secret
        )
        second_block = self.database.record_transaction(
            self.reader["id"], "open-vault", "session started"
        )
        self.assertEqual(second_block["previous_hash"], first_block["block_hash"])
        with closing(sqlite3.connect(self.database.database_path)) as connection:
            encrypted_payload = connection.execute(
                "SELECT encrypted_payload FROM mini_chain WHERE block_index = 0"
            ).fetchone()[0]
        self.assertTrue(FileEncryption.is_encrypted(bytes(encrypted_payload)))
        self.assertNotIn(secret.encode("utf-8"), bytes(encrypted_payload))
        self.assertTrue(self.database.verify_transaction_chain())

        with closing(sqlite3.connect(self.database.database_path)) as connection:
            connection.execute(
                "UPDATE mini_chain SET block_hash = ? WHERE block_index = 0",
                ("0" * 64,),
            )
            connection.commit()
        self.assertFalse(self.database.verify_transaction_chain())

    def test_unshared_accounts_cannot_view_or_update_resources(self) -> None:
        file_id = self.database.create_resource(
            self.owner["id"], "private.txt", "file", content=b"private", content_type="text/plain"
        )
        with closing(sqlite3.connect(self.database.database_path)) as connection:
            stored_content = connection.execute(
                "SELECT content FROM resources WHERE id = ?", (file_id,)
            ).fetchone()[0]
        self.assertIsNone(stored_content)
        with self.assertRaises(PermissionError):
            self.database.read_file(self.outsider["id"], file_id)
        with self.assertRaises(PermissionError):
            self.database.update_resource(
                self.outsider["id"], file_id, "changed.txt", b"changed", "text/plain"
            )
        self.assertEqual(self.database.list_resources(self.outsider["id"]), [])

    def test_account_files_and_nested_folders_are_stored_on_disk(self) -> None:
        folder_id = self.database.create_resource(
            self.owner["id"], "private-folder", "folder"
        )
        file_id = self.database.create_resource(
            self.owner["id"],
            "private.txt",
            "file",
            folder_id,
            b"private",
            "text/plain",
        )
        account_directory = (
            self.database.users_dir
            / f"account-{self.owner['id']}-{self.owner['username']}"
        )
        folder_path = account_directory / "items" / folder_id
        file_path = folder_path / f"{file_id}.blob"

        self.assertTrue(folder_path.is_dir())
        self.assertEqual(file_path.read_bytes(), b"private")
        self.assertEqual(
            self.database.read_file(self.owner["id"], file_id)["content"],
            b"private",
        )

    def test_documents_are_encrypted_at_rest_and_shared_reads_are_decrypted(self) -> None:
        key = bytes(range(FileEncryption.key_size))
        self.database.activate_file_encryption(key)
        document_content = b"%PDF-1.7\nconfidential"
        document_id = self.database.create_resource(
            self.owner["id"],
            "confidential.pdf",
            "file",
            content=document_content,
            content_type="application/pdf",
        )
        image_content = b"\x89PNG\r\n\x1a\noriginal-image"
        image_id = self.database.create_resource(
            self.owner["id"],
            "photo.png",
            "file",
            content=image_content,
            content_type="image/png",
        )
        account_directory = (
            self.database.users_dir
            / f"account-{self.owner['id']}-{self.owner['username']}"
        )
        encrypted_document = (
            account_directory / "items" / f"{document_id}.blob"
        ).read_bytes()
        stored_image = (
            account_directory / "items" / f"{image_id}.blob"
        ).read_bytes()

        self.assertTrue(FileEncryption.is_encrypted(encrypted_document))
        self.assertNotIn(document_content, encrypted_document)
        self.assertEqual(stored_image, image_content)
        self.assertEqual(
            self.database.read_file(self.owner["id"], document_id)["content"],
            document_content,
        )

        self.database.set_resource_permissions(
            self.owner["id"], document_id, self.reader["id"], False, True, False
        )
        self.assertEqual(
            self.database.read_file(self.reader["id"], document_id)["content"],
            document_content,
        )
        replacement_content = b"%PDF-1.7\nupdated document"
        self.database.update_resource(
            self.owner["id"],
            document_id,
            "confidential.pdf",
            replacement_content,
            "application/pdf",
        )
        encrypted_document = (
            account_directory / "items" / f"{document_id}.blob"
        ).read_bytes()
        self.assertTrue(FileEncryption.is_encrypted(encrypted_document))
        self.assertEqual(
            self.database.read_file(self.owner["id"], document_id)["content"],
            replacement_content,
        )

    def test_legacy_plaintext_documents_are_encrypted_when_storage_unlocks(self) -> None:
        document_content = b"legacy plaintext"
        document_id = self.database.create_resource(
            self.owner["id"], "legacy.txt", "file", content=document_content
        )
        account_directory = (
            self.database.users_dir
            / f"account-{self.owner['id']}-{self.owner['username']}"
        )
        path = account_directory / "items" / f"{document_id}.blob"
        key = bytes(range(FileEncryption.key_size))

        self.database.activate_file_encryption(key)

        stored_content = path.read_bytes()
        self.assertTrue(FileEncryption.is_encrypted(stored_content))
        self.assertEqual(
            self.database.read_file(self.owner["id"], document_id)["content"],
            document_content,
        )
        self.database.deactivate_file_encryption()
        with self.assertRaises(PermissionError):
            self.database.read_file(self.owner["id"], document_id)

    def test_existing_database_blobs_are_migrated_to_account_storage(self) -> None:
        file_id = self.database.create_resource(
            self.owner["id"], "legacy.txt", "file", content=b"legacy-data"
        )
        with closing(sqlite3.connect(self.database.database_path)) as connection:
            connection.execute(
                "UPDATE resources SET content = ?, storage_path = NULL WHERE id = ?",
                (b"legacy-data", file_id),
            )
            connection.commit()

        migrated_database = AccountDatabase(self.storage_dir)

        account_directory = (
            self.storage_dir
            / "users"
            / f"account-{self.owner['id']}-{self.owner['username']}"
        )
        file_path = account_directory / "items" / f"{file_id}.blob"
        with closing(sqlite3.connect(self.database.database_path)) as connection:
            stored_content = connection.execute(
                "SELECT content FROM resources WHERE id = ?", (file_id,)
            ).fetchone()[0]
        self.assertIsNone(stored_content)
        self.assertEqual(file_path.read_bytes(), b"legacy-data")
        self.assertEqual(
            migrated_database.read_file(self.owner["id"], file_id)["content"],
            b"legacy-data",
        )

    def test_encrypted_message_save_uses_incremented_text_filenames(self) -> None:
        first_name = self.database.save_encrypted_message(
            self.owner["id"], "manual-ciphertext-1"
        )
        second_name = self.database.save_encrypted_message(
            self.owner["id"], "manual-ciphertext-2"
        )

        self.assertEqual(first_name, "pesan_terenkripsi_1.txt")
        self.assertEqual(second_name, "pesan_terenkripsi_2.txt")
        resources = self.database.list_resources(self.owner["id"])
        saved = next(item for item in resources if item["name"] == second_name)
        account_directory = (
            self.database.users_dir
            / f"account-{self.owner['id']}-{self.owner['username']}"
        )
        message_path = account_directory / "items" / second_name
        self.assertEqual(
            message_path.read_text(encoding="utf-8"), "manual-ciphertext-2"
        )
        reopened_database = AccountDatabase(self.storage_dir)
        self.assertTrue(message_path.is_file())
        self.assertEqual(
            reopened_database.read_file(
                self.owner["id"], str(saved["id"])
            )["content"],
            b"manual-ciphertext-2",
        )

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
