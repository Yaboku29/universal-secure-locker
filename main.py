import base64
import logging
from pathlib import Path

import webview

from backend.database import AccountDatabase
from backend.security.biometric_auth import BiometricAuth
from backend.security.crypto_engine import SuperEncryption
from backend.security.dongle_auth import DongleAuth


logger = logging.getLogger("universal_secure_locker")


class LockerApi:
    def __init__(self, storage_dir: Path) -> None:
        self.dongle = DongleAuth(storage_dir)
        self.biometric = BiometricAuth(storage_dir)
        self.accounts = AccountDatabase(storage_dir)
        self._usb_verified = False
        self._face_verified = False
        self._hardware_verified = False
        self._authenticated = False
        self._current_account_id: int | None = None

    def get_status(self) -> dict[str, bool]:
        return {
            "usb_registered": self.dongle.is_registered(),
            "face_registered": self.biometric.is_registered(),
        }

    def list_usb_drives(self) -> list[dict[str, str]]:
        return self.dongle.list_removable_drives()

    def register_usb_key(self, letter: str) -> str:
        return self.dongle.register_drive(letter)

    def start_camera(self) -> str:
        return self.biometric.start_camera()

    def stop_camera(self) -> None:
        self.biometric.stop_camera()

    def camera_frame(self) -> str:
        return self.biometric.camera_frame()

    def capture_face_sample(self) -> dict[str, int | str]:
        return self.biometric.capture_enrollment_sample()

    def finish_face_enrollment(self) -> str:
        return self.biometric.finish_enrollment()

    def verify_usb(self) -> bool:
        self._usb_verified = False
        self._face_verified = False
        self._hardware_verified = False
        self._authenticated = False
        self._current_account_id = None
        self._usb_verified = self.dongle.verify()
        return self._usb_verified

    def verify_face(self) -> dict[str, float | bool | str]:
        self._face_verified = False
        self._hardware_verified = False
        self._authenticated = False
        self._current_account_id = None
        result = self.biometric.verify()
        self._face_verified = bool(result["verified"])
        return result

    def complete_hardware_authentication(self) -> bool:
        if not (self._usb_verified and self._face_verified):
            raise PermissionError("USB dan wajah harus diverifikasi sebelum login akun.")
        self._hardware_verified = True
        self.biometric.stop_camera()
        return True

    def _require_hardware_authentication(self) -> None:
        if not self._hardware_verified:
            raise PermissionError("Verifikasi USB dan wajah terlebih dahulu.")

    def _require_account_authentication(self) -> int:
        self._require_hardware_authentication()
        if not self._authenticated or self._current_account_id is None:
            raise PermissionError("Login ke akun terlebih dahulu.")
        return self._current_account_id

    def get_account_state(self) -> dict[str, bool]:
        self._require_hardware_authentication()
        return {"has_accounts": self.accounts.has_accounts()}

    def create_account(
        self, username: str, password: str
    ) -> dict[str, int | str | bool]:
        self._require_hardware_authentication()
        account = self.accounts.create_account(username, password)
        self._current_account_id = int(account["id"])
        self._authenticated = True
        logger.info("Akun %s dibuat; admin=%s.", account["username"], account["is_admin"])
        return account

    def login_account(
        self, username: str, password: str
    ) -> dict[str, int | str | bool]:
        self._require_hardware_authentication()
        account = self.accounts.authenticate(username, password)
        self._current_account_id = int(account["id"])
        self._authenticated = True
        logger.info("Akun %s berhasil login.", account["username"])
        return account

    def is_authenticated(self) -> bool:
        return self._hardware_verified and self._authenticated

    def get_current_account(self) -> dict[str, int | str | bool]:
        return self.accounts.get_account(self._require_account_authentication())

    def list_accounts_for_sharing(self, resource_id: str) -> dict[str, object]:
        account_id = self._require_account_authentication()
        return self.accounts.list_accounts_for_sharing(account_id, resource_id)

    def list_resources(
        self, parent_id: str | None = None
    ) -> list[dict[str, int | str | bool | None]]:
        return self.accounts.list_resources(
            self._require_account_authentication(), parent_id
        )

    def can_create_in(self, parent_id: str | None = None) -> bool:
        return self.accounts.can_create_in(
            self._require_account_authentication(), parent_id
        )

    def create_resource(
        self,
        name: str,
        kind: str,
        parent_id: str | None = None,
        content_base64: str | None = None,
        content_type: str | None = None,
    ) -> str:
        account_id = self._require_account_authentication()
        content = None
        if content_base64 is not None:
            if not isinstance(content_base64, str):
                raise ValueError("Isi file tidak valid.")
            if len(content_base64) > (self.accounts.max_file_size * 4 // 3) + 8:
                raise ValueError("Ukuran file maksimal 10 MiB.")
            try:
                content = base64.b64decode(content_base64, validate=True)
            except ValueError as error:
                raise ValueError("Isi file tidak valid.") from error
        return self.accounts.create_resource(
            account_id,
            name,
            kind,
            parent_id,
            content,
            content_type,
        )

    def read_resource(self, resource_id: str) -> dict[str, str]:
        data = self.accounts.read_file(
            self._require_account_authentication(), resource_id
        )
        return {
            "name": str(data["name"]),
            "content_type": str(data["content_type"]),
            "content_base64": base64.b64encode(data["content"]).decode("ascii"),
        }

    def update_resource(
        self,
        resource_id: str,
        name: str,
        content_base64: str | None = None,
        content_type: str | None = None,
    ) -> None:
        account_id = self._require_account_authentication()
        content = None
        if content_base64 is not None:
            if not isinstance(content_base64, str):
                raise ValueError("Isi file tidak valid.")
            if len(content_base64) > (self.accounts.max_file_size * 4 // 3) + 8:
                raise ValueError("Ukuran file maksimal 10 MiB.")
            try:
                content = base64.b64decode(content_base64, validate=True)
            except ValueError as error:
                raise ValueError("Isi file tidak valid.") from error
        self.accounts.update_resource(
            account_id,
            resource_id,
            name,
            content,
            content_type,
        )

    def save_encrypted_message(self, message: str) -> str:
        return self.accounts.save_encrypted_message(
            self._require_account_authentication(), message
        )

    def generate_rsa_key_pair(self) -> dict[str, str]:
        self._require_account_authentication()
        return SuperEncryption.generate_rsa_key_pair()

    def encrypt_message(
        self, plaintext: str, shift: int, key: str, public_key_pem: str
    ) -> str:
        self._require_account_authentication()
        return SuperEncryption.encrypt_text(
            plaintext, shift, key, public_key_pem
        )

    def decrypt_message(
        self, ciphertext: str, shift: int, key: str, private_key_pem: str
    ) -> str:
        self._require_account_authentication()
        return SuperEncryption.decrypt_text(
            ciphertext, shift, key, private_key_pem
        )

    def set_resource_permissions(
        self,
        resource_id: str,
        target_account_id: int,
        can_create: bool,
        can_read: bool,
        can_update: bool,
    ) -> None:
        self.accounts.set_resource_permissions(
            self._require_account_authentication(),
            resource_id,
            target_account_id,
            can_create,
            can_read,
            can_update,
        )

    def logout(self) -> None:
        self._authenticated = False
        self._current_account_id = None
        self._hardware_verified = False
        self._usb_verified = False
        self._face_verified = False
        self.biometric.stop_camera()

    def shutdown(self) -> None:
        self.logout()
        logger.info("Aplikasi ditutup.")

    def log_frontend_message(self, message: str) -> None:
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Pesan log harus berupa teks yang tidak kosong.")
        logger.info("Closure: %s", " ".join(message.split())[:300])


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger.info("Universal Secure Locker dimulai.")
    project_dir = Path(__file__).resolve().parent
    storage_dir = project_dir / "storage"
    api = LockerApi(storage_dir)
    window = webview.create_window(
        "Universal Secure Locker",
        (project_dir / "frontend" / "index.html").as_uri(),
        js_api=api,
        min_size=(960, 680),
        width=1180,
        height=800,
    )
    window.events.closed += api.shutdown
    webview.start()


if __name__ == "__main__":
    main()