import ctypes
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path


class DongleAuth:
    marker_name = "USL-USB-KEY.txt"
    drive_removable = 2

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.settings_path = storage_dir / "auth_config.json"

    def _read_settings(self) -> dict[str, str]:
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as error:
            raise RuntimeError("File konfigurasi autentikasi rusak.") from error

        if not isinstance(data, dict):
            raise RuntimeError("Format file konfigurasi autentikasi tidak valid.")
        return data

    def _write_settings(self, settings: dict[str, str]) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = self.settings_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(settings, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(self.settings_path)

    def list_removable_drives(self) -> list[dict[str, str]]:
        if os.name != "nt":
            raise RuntimeError("Deteksi USB saat ini hanya didukung di Windows.")

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetLogicalDrives.restype = ctypes.c_uint32
        kernel32.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
        kernel32.GetDriveTypeW.restype = ctypes.c_uint
        drive_mask = kernel32.GetLogicalDrives()
        drives = []

        for index in range(26):
            if not drive_mask & (1 << index):
                continue
            letter = chr(ord("A") + index)
            root = f"{letter}:\\"
            if kernel32.GetDriveTypeW(root) == self.drive_removable:
                drives.append({"id": letter, "label": f"USB Drive ({letter}:)"})

        return drives

    def register_drive(self, letter: str) -> str:
        if letter not in {drive["id"] for drive in self.list_removable_drives()}:
            raise ValueError("USB tidak terdeteksi. Sambungkan USB lalu perbarui daftar.")

        settings = self._read_settings()
        marker_path = Path(f"{letter}:\\") / self.marker_name
        if marker_path.exists():
            raise ValueError(
                f"File {self.marker_name} sudah ada di USB tersebut. "
                "Pindahkan atau hapus file itu secara manual jika ingin mendaftar ulang."
            )

        token = secrets.token_urlsafe(32)
        try:
            with marker_path.open("x", encoding="utf-8") as marker_file:
                marker_file.write(token)
        except OSError as error:
            raise RuntimeError(
                "Tidak dapat menulis kunci USB. Pastikan USB tidak terkunci "
                "dan memiliki ruang kosong."
            ) from error

        settings["usb_key_sha256"] = hashlib.sha256(token.encode("utf-8")).hexdigest()
        try:
            self._write_settings(settings)
        except OSError as error:
            try:
                marker_path.unlink()
            except OSError as cleanup_error:
                raise RuntimeError(
                    "Konfigurasi lokal gagal disimpan dan token USB tidak dapat "
                    "dibersihkan. Hapus file kunci pada USB secara manual."
                ) from cleanup_error
            raise RuntimeError(
                "Token sudah dibuat pada USB, tetapi konfigurasi lokal gagal "
                "disimpan. Coba daftarkan ulang."
            ) from error

        return f"Kunci USB berhasil didaftarkan pada drive {letter}:."

    def is_registered(self) -> bool:
        return bool(self._read_settings().get("usb_key_sha256"))

    def verify(self) -> bool:
        expected_hash = self._read_settings().get("usb_key_sha256")
        if not expected_hash:
            return False

        for drive in self.list_removable_drives():
            marker_path = Path(f"{drive['id']}:\\") / self.marker_name
            try:
                token = marker_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                continue
            except OSError as error:
                raise RuntimeError(
                    f"Tidak dapat membaca file kunci USB pada drive {drive['id']}:."
                ) from error

            actual_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            if hmac.compare_digest(actual_hash, expected_hash):
                return True

        return False
