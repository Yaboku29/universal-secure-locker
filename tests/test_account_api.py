import base64
import tempfile
import unittest
from pathlib import Path

from backend.database import AccountDatabase
from backend.security.file_crypto import FileEncryption
from backend.security.file_key_store import WindowsFileKeyStore
from main import LockerApi


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
        self.api.biometric = BiometricStub()
        self.api._usb_verified = False
        self.api._face_verified = False
        self.api._hardware_verified = False
        self.api._authenticated = False
        self.api._current_account_id = None
        self.api._prepare_file_storage()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_account_creation_requires_both_hardware_factors(self) -> None:
        with self.assertRaises(PermissionError):
            self.api.complete_hardware_authentication()

        self.api._usb_verified = True
        with self.assertRaises(PermissionError):
            self.api.complete_hardware_authentication()

        self.api._face_verified = True
        self.assertTrue(self.api.complete_hardware_authentication())
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
        self.assertTrue(FileEncryption.is_encrypted(stored_path.read_bytes()))
        self.api._usb_verified = True
        self.api._face_verified = True
        self.api.complete_hardware_authentication()
        self.api.login_account("first-user", "first-password-123")
        self.assertEqual(
            base64.b64decode(self.api.read_resource(resource_id)["content_base64"]),
            document,
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
        self.assertFalse(self.api.is_authenticated())


if __name__ == "__main__":
    unittest.main()
