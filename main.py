import logging
from pathlib import Path

import webview

from backend.security.biometric_auth import BiometricAuth
from backend.security.dongle_auth import DongleAuth


logger = logging.getLogger("universal_secure_locker")


class LockerApi:
    def __init__(self, storage_dir: Path) -> None:
        self.dongle = DongleAuth(storage_dir)
        self.biometric = BiometricAuth(storage_dir)
        self._usb_verified = False
        self._face_verified = False
        self._authenticated = False

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
        self._authenticated = False
        self._usb_verified = self.dongle.verify()
        return self._usb_verified

    def verify_face(self) -> dict[str, float | bool | str]:
        self._face_verified = False
        self._authenticated = False
        result = self.biometric.verify()
        self._face_verified = bool(result["verified"])
        return result

    def complete_authentication(self) -> bool:
        if not (self._usb_verified and self._face_verified):
            raise PermissionError("Kedua kunci harus diverifikasi sebelum membuka aplikasi.")
        self._authenticated = True
        self.biometric.stop_camera()
        return True

    def is_authenticated(self) -> bool:
        return self._authenticated

    def logout(self) -> None:
        self._authenticated = False
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