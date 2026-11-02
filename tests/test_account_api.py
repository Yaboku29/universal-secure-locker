import tempfile
import unittest
from pathlib import Path

from backend.database import AccountDatabase
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
        self.api.biometric = BiometricStub()
        self.api._usb_verified = False
        self.api._face_verified = False
        self.api._hardware_verified = False
        self.api._authenticated = False
        self.api._current_account_id = None

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
        self.assertTrue(self.api.is_authenticated())
        self.assertEqual(self.api.get_current_account()["username"], "first-user")

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
        self.assertFalse(self.api.is_authenticated())


if __name__ == "__main__":
    unittest.main()
