import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from backend.database import AccountDatabase
from backend.security.database_crypto import DatabaseFileEncryption
from backend.security.file_crypto import FileEncryption
from backend.security.file_key_store import WindowsFileKeyStore
from main import LockerApi, webview


class BiometricStub:
    def __init__(self) -> None:
        self.stopped = False

    def stop_camera(self) -> None:
        self.stopped = True


class AccountApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = AccountDatabase(Path(self.temporary_directory.name))
        self.api = LockerApi.__new__(LockerApi)
        self.api.accounts = self.database
        self.api.file_key_store = WindowsFileKeyStore(
            Path(self.temporary_directory.name) / "file-encryption-key.dpapi"
        )
        self.api._storage_dir = Path(self.temporary_directory.name)
        self.api._database_path = self.api._storage_dir / "accounts.db"
        self.api._database_key = self.api.file_key_store.load_or_create()
        self.api._database_workspace = None
        self.api._accounts = self.database
        self.api.biometric = BiometricStub()
        self.api._usb_verified = False
        self.api._face_verified = False
        self.api._hardware_verified = False
        self.api._authenticated = False
        self.api._current_account_id = None
        self.api._prepare_file_storage()
        DatabaseFileEncryption.seal(
            self.api._database_path, self.api._database_key
        )

    def tearDown(self) -> None:
        self.api.logout()
        self.temporary_directory.cleanup()

    def test_account_creation_requires_both_hardware_factors(self) -> None:
        with self.assertRaises(PermissionError):
            self.api.complete_hardware_authentication()

        self.api._usb_verified = True
        with self.assertRaises(PermissionError):
            self.api.complete_hardware_authentication()

        self.api._face_verified = True
        self.assertTrue(self.api.complete_hardware_authentication())
        self.assertTrue(
            DatabaseFileEncryption.is_encrypted(
                self.api._database_path.read_bytes()
            )
        )
        self.assertNotEqual(
            self.api.accounts.database_path, self.api._database_path
        )
        self.assertTrue(
            self.api.accounts.database_path.read_bytes().startswith(
                b"SQLite format 3\x00"
            )
        )
        self.assertTrue(self.api.biometric.stopped)
        self.assertEqual(self.api.get_account_state(), {"has_accounts": False})

        account = self.api.create_account("first-user", "first-password-123")
        self.assertTrue(account["is_admin"])
        self.assertTrue(
            (
                self.database.users_dir
                / f"account-{account['id']}-{account['username']}"
            ).is_dir()
        )
        self.assertTrue(self.api.is_authenticated())
        self.assertEqual(self.api.get_current_account()["username"], "first-user")
        note_id = self.api.save_secret_note("API catatan rahasia")
        self.assertEqual(self.api.get_secret_notes()[0]["id"], note_id)
        transaction = self.api.record_transaction("create-note", note_id)
        self.assertEqual(transaction["block_index"], 0)
        self.assertTrue(self.api.verify_transaction_chain())
        document = b"%PDF-1.7\nAPI encrypted document"
        resource_id = self.api.create_resource(
            "secure.pdf",
            "file",
            content_base64=base64.b64encode(document).decode("ascii"),
            content_type="application/pdf",
        )
        stored_path = (
            self.database.users_dir
            / f"account-{account['id']}-{account['username']}"
            / "items"
            / f"{resource_id}.blob"
        )
        self.assertTrue(FileEncryption.is_encrypted(stored_path.read_bytes()))
        self.assertEqual(
            base64.b64decode(self.api.read_resource(resource_id)["content_base64"]),
            document,
        )
        download_path = Path(self.temporary_directory.name) / "downloaded.pdf"
        with patch.object(
            self.api, "_select_download_path", return_value=download_path
        ) as select_path:
            with self.assertRaisesRegex(ValueError, "Password akun salah"):
                self.api.download_resource(resource_id, "wrong-password-123")
            select_path.assert_not_called()
            download_result = self.api.download_resource(
                resource_id, "first-password-123"
            )
        self.assertEqual(download_result, {"cancelled": False, "name": "secure.pdf"})
        self.assertEqual(download_path.read_bytes(), document)
        with patch.object(self.api, "_select_download_path", return_value=None):
            cancelled = self.api.download_resource(
                resource_id, "first-password-123"
            )
        self.assertEqual(cancelled, {"cancelled": True, "name": "secure.pdf"})
        key_pair = self.api.generate_rsa_key_pair()
        ciphertext = self.api.encrypt_message(
            "pesan API", 5, "LockerKey2026", key_pair["public_key"]
        )
        self.assertEqual(
            self.api.decrypt_message(
                ciphertext, 5, "LockerKey2026", key_pair["private_key"]
            ),
            "pesan API",
        )
        self.assertEqual(
            self.api.save_encrypted_message("manual-ciphertext"),
            "pesan_terenkripsi_1.txt",
        )
        self.api.logout()
        self.assertTrue(
            DatabaseFileEncryption.is_encrypted(
                self.api._database_path.read_bytes()
            )
        )
        self.assertTrue(FileEncryption.is_encrypted(stored_path.read_bytes()))
        self.api._usb_verified = True
        self.api._face_verified = True
        self.api.complete_hardware_authentication()
        self.api.login_account("first-user", "first-password-123")
        self.assertEqual(
            base64.b64decode(self.api.read_resource(resource_id)["content_base64"]),
            document,
        )

    def test_download_path_uses_native_save_dialog(self) -> None:
        selected_path = Path(self.temporary_directory.name) / "saved.txt"
        window = Mock()
        window.create_file_dialog.return_value = (str(selected_path),)
        with patch("main.webview.windows", [window]):
            result = self.api._select_download_path("document.txt")

        self.assertEqual(result, selected_path)
        window.create_file_dialog.assert_called_once_with(
            webview.FileDialog.SAVE,
            save_filename="document.txt",
            file_types=(),
        )

    def test_steganography_api_saves_and_reveals_encrypted_text(self) -> None:
        self.api._usb_verified = True
        self.api._face_verified = True
        self.api.complete_hardware_authentication()
        self.api.create_account("steg-user", "steg-password-123")
        image_path = Path(self.temporary_directory.name) / "cover.png"
        output_path = Path(self.temporary_directory.name) / "cover-stego.png"
        Image.new("RGB", (64, 64), (80, 120, 160)).save(image_path)
        image_base64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        with patch.object(
            self.api, "_select_download_path", return_value=output_path
        ) as select_path:
            result = self.api.hide_steganographic_message(
                image_base64, "cover.png", "a1b2c3d4"
            )

        self.assertEqual(
            result, {"cancelled": False, "name": "cover-stego.png"}
        )
        self.assertEqual(
            self.api.reveal_steganographic_message(
                base64.b64encode(output_path.read_bytes()).decode("ascii"),
                output_path.name,
            ),
            "a1b2c3d4",
        )
        select_path.assert_called_once_with(
            "cover-stego.png", ("PNG Image (*.png)",)
        )

    def test_account_creation_and_login_are_blocked_after_logout(self) -> None:
        self.api._usb_verified = True
        self.api._face_verified = True
        self.api.complete_hardware_authentication()
        self.api.create_account("first-user", "first-password-123")
        self.api.logout()

        with self.assertRaises(PermissionError):
            self.api.create_account("second-user", "second-password-123")
        with self.assertRaises(PermissionError):
            self.api.login_account("first-user", "first-password-123")
        with self.assertRaises(PermissionError):
            self.api.save_encrypted_message("ciphertext-after-logout")
        with self.assertRaises(PermissionError):
            self.api.generate_rsa_key_pair()
        with self.assertRaises(PermissionError):
            self.api.encrypt_message(
                "secret", 3, "LockerKey2026", "public-key"
            )
        with self.assertRaises(PermissionError):
            self.api.download_resource("resource-id", "first-password-123")
        self.assertFalse(self.api.is_authenticated())


if __name__ == "__main__":
    unittest.main()
