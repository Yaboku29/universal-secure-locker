import base64
import logging
import tempfile
from pathlib import Path

import webview

from backend.database import AccountDatabase
from backend.security.biometric_auth import BiometricAuth
from backend.security.crypto_engine import SuperEncryption
from backend.security.database_crypto import DatabaseFileEncryption
from backend.security.dongle_auth import DongleAuth
from backend.security.file_key_store import WindowsFileKeyStore
from backend.security.steganography import hide_message, reveal_message


logger = logging.getLogger("universal_secure_locker")


class LockerApi:
    max_steganography_image_size = 10 * 1024 * 1024

    def __init__(self, storage_dir: Path) -> None:
        self.dongle = DongleAuth(storage_dir)
        self.biometric = BiometricAuth(storage_dir)
        self.file_key_store = WindowsFileKeyStore(
            storage_dir / "file-encryption-key.dpapi"
        )
        self._storage_dir = storage_dir
        self._database_path = storage_dir / "accounts.db"
        self._database_key = self.file_key_store.load_or_create()
        self._accounts: AccountDatabase | None = None
        self._database_workspace: tempfile.TemporaryDirectory[str] | None = None
        DatabaseFileEncryption.seal(self._database_path, self._database_key)
        self._usb_verified = False
        self._face_verified = False
        self._hardware_verified = False
        self._authenticated = False
        self._current_account_id: int | None = None

    @property
    def accounts(self) -> AccountDatabase:
        if self._accounts is None:
            raise PermissionError("Verifikasi USB dan wajah terlebih dahulu.")
        return self._accounts

    @accounts.setter
    def accounts(self, database: AccountDatabase | None) -> None:
        self._accounts = database

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
        self._lock_database()
        self._usb_verified = False
        self._face_verified = False
        self._hardware_verified = False
        self._authenticated = False
        self._current_account_id = None
        self._usb_verified = self.dongle.verify()
        return self._usb_verified

    def verify_face(self) -> dict[str, float | bool | str]:
        self._lock_database()
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
        self._open_database()
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

    def _unlock_file_storage(self) -> None:
        key = self._database_key
        try:
            self.accounts.activate_file_encryption(key)
        except Exception:
            self.accounts.deactivate_file_encryption()
            raise

    def _open_database(self) -> None:
        workspace = tempfile.TemporaryDirectory(prefix="usl-database-")
        working_database_path = Path(workspace.name) / "accounts.db"
        try:
            DatabaseFileEncryption.unlock_to(
                self._database_path,
                working_database_path,
                self._database_key,
            )
            self.accounts = AccountDatabase(
                self._storage_dir, database_path=working_database_path
            )
            self._database_workspace = workspace
            self.accounts.activate_sensitive_data_encryption(self._database_key)
            try:
                self.accounts.activate_file_encryption(self._database_key)
            finally:
                self.accounts.deactivate_file_encryption()
        except Exception:
            self._accounts = None
            workspace.cleanup()
            raise

    def _prepare_file_storage(self) -> None:
        key = self._database_key
        try:
            self.accounts.activate_file_encryption(key)
        finally:
            self.accounts.deactivate_file_encryption()

    def _lock_file_storage(self) -> None:
        if self._accounts is not None:
            self.accounts.deactivate_file_encryption()
            self.accounts.deactivate_sensitive_data_encryption()

    def _lock_database(self) -> None:
        if self._accounts is None:
            return
        self._lock_file_storage()
        DatabaseFileEncryption.seal_to(
            self._accounts.database_path,
            self._database_path,
            self._database_key,
        )
        self._accounts = None
        if self._database_workspace is not None:
            self._database_workspace.cleanup()
            self._database_workspace = None

    def get_account_state(self) -> dict[str, bool]:
        self._require_hardware_authentication()
        return {"has_accounts": self.accounts.has_accounts()}

    def create_account(
        self, username: str, password: str
    ) -> dict[str, int | str | bool]:
        self._require_hardware_authentication()
        account = self.accounts.create_account(username, password)
        self._unlock_file_storage()
        self._current_account_id = int(account["id"])
        self._authenticated = True
        logger.info("Akun %s dibuat; admin=%s.", account["username"], account["is_admin"])
        return account

    def login_account(
        self, username: str, password: str
    ) -> dict[str, int | str | bool]:
        self._require_hardware_authentication()
        account = self.accounts.authenticate(username, password)
        self._unlock_file_storage()
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

    def download_resource(
        self, resource_id: str, password: str
    ) -> dict[str, str | bool]:
        account_id = self._require_account_authentication()
        self.accounts.verify_account_password(account_id, password)
        data = self.accounts.read_file(account_id, resource_id)
        destination = self._select_download_path(str(data["name"]))
        if destination is None:
            return {"cancelled": True, "name": str(data["name"])}
        try:
            destination.write_bytes(data["content"])
        except OSError as error:
            raise RuntimeError(
                "File tidak dapat disimpan ke lokasi yang dipilih."
            ) from error
        logger.info(
            "File %s berhasil diunduh oleh akun %s.",
            data["name"],
            account_id,
        )
        return {"cancelled": False, "name": str(data["name"])}

    @staticmethod
    def _select_download_path(
        filename: str, file_types: tuple[str, ...] = ()
    ) -> Path | None:
        if not webview.windows:
            raise RuntimeError("Dialog simpan file tidak tersedia.")
        selected_paths = webview.windows[0].create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename=filename,
            file_types=file_types,
        )
        if not selected_paths:
            return None
        return Path(selected_paths[0])

    @classmethod
    def _decode_steganography_image(
        cls, image_base64: str, image_name: str
    ) -> bytes:
        if (
            not isinstance(image_name, str)
            or not image_name
            or len(image_name) > 255
            or Path(image_name).name != image_name
            or "\x00" in image_name
            or Path(image_name).suffix.lower() != ".png"
        ):
            raise ValueError("Pilih file gambar PNG.")
        if (
            not isinstance(image_base64, str)
            or len(image_base64) > (cls.max_steganography_image_size * 4 // 3) + 8
        ):
            raise ValueError("Ukuran gambar maksimal 10 MiB.")
        try:
            image_content = base64.b64decode(image_base64, validate=True)
        except ValueError as error:
            raise ValueError("Isi gambar tidak valid.") from error
        if len(image_content) > cls.max_steganography_image_size:
            raise ValueError("Ukuran gambar maksimal 10 MiB.")
        if not image_content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("File yang dipilih bukan gambar PNG yang valid.")
        return image_content

    def hide_steganographic_message(
        self, image_base64: str, image_name: str, ciphertext: str
    ) -> dict[str, bool | str]:
        account_id = self._require_account_authentication()
        image_content = self._decode_steganography_image(image_base64, image_name)
        output_name = f"{Path(image_name).stem}-stego.png"
        with tempfile.TemporaryDirectory(prefix="usl-steganography-") as directory:
            temporary_directory = Path(directory)
            source_path = temporary_directory / "source.png"
            output_path = temporary_directory / output_name
            source_path.write_bytes(image_content)
            hide_message(source_path, ciphertext, output_path)

            destination = self._select_download_path(
                output_name, ("PNG Image (*.png)",)
            )
            if destination is None:
                return {"cancelled": True, "name": output_name}
            if destination.suffix.lower() != ".png":
                destination = destination.with_suffix(".png")
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(output_path.read_bytes())
            except OSError as error:
                raise RuntimeError(
                    "Gambar hasil steganografi tidak dapat disimpan."
                ) from error

        logger.info(
            "Gambar steganografi berhasil dibuat untuk akun %s.",
            account_id,
        )
        return {"cancelled": False, "name": destination.name}

    def reveal_steganographic_message(
        self, image_base64: str, image_name: str
    ) -> str:
        self._require_account_authentication()
        image_content = self._decode_steganography_image(image_base64, image_name)
        with tempfile.TemporaryDirectory(prefix="usl-steganography-") as directory:
            image_path = Path(directory) / "image.png"
            image_path.write_bytes(image_content)
            return reveal_message(image_path)

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

    def save_secret_note(self, content: str) -> str:
        return self.accounts.save_secret_note(
            self._require_account_authentication(), content
        )

    def get_secret_notes(self) -> list[dict[str, str]]:
        return self.accounts.get_secret_notes(
            self._require_account_authentication()
        )

    def record_transaction(self, action: str, details: str) -> dict[str, int | str]:
        return self.accounts.record_transaction(
            self._require_account_authentication(), action, details
        )

    def verify_transaction_chain(self) -> bool:
        self._require_account_authentication()
        return self.accounts.verify_transaction_chain()

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
        self._lock_database()
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