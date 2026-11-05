import os
import tempfile
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class FileEncryption:
    key_size = 32
    nonce_size = 12
    _header = b"USLFILE\x01"
    _image_extensions = {
        ".bmp",
        ".gif",
        ".heic",
        ".heif",
        ".jpeg",
        ".jpg",
        ".png",
        ".tif",
        ".tiff",
        ".webp",
    }

    @classmethod
    def encrypt_bytes(cls, content: bytes, key: bytes) -> bytes:
        cls._validate_key(key)
        if not isinstance(content, bytes):
            raise ValueError("Isi file harus berupa bytes.")
        if cls.is_encrypted(content):
            raise ValueError("File sudah terenkripsi.")
        nonce = os.urandom(cls.nonce_size)
        ciphertext = AESGCM(key).encrypt(nonce, content, cls._header)
        return cls._header + nonce + ciphertext

    @classmethod
    def decrypt_bytes(cls, encrypted_content: bytes, key: bytes) -> bytes:
        cls._validate_key(key)
        if not isinstance(encrypted_content, bytes):
            raise ValueError("Isi file terenkripsi harus berupa bytes.")
        header_size = len(cls._header)
        minimum_size = header_size + cls.nonce_size + 16
        if (
            len(encrypted_content) < minimum_size
            or not encrypted_content.startswith(cls._header)
        ):
            raise ValueError("Format file terenkripsi USL tidak valid.")
        nonce_start = header_size
        ciphertext_start = nonce_start + cls.nonce_size
        nonce = encrypted_content[nonce_start:ciphertext_start]
        ciphertext = encrypted_content[ciphertext_start:]
        try:
            return AESGCM(key).decrypt(nonce, ciphertext, cls._header)
        except InvalidTag as error:
            raise ValueError(
                "File gagal didekripsi: kunci salah atau data telah berubah."
            ) from error

    @classmethod
    def encrypt_file(
        cls,
        file_path: Path | str,
        key: bytes,
        output_path: Path | str | None = None,
    ) -> Path:
        source = Path(file_path)
        cls._validate_key(key)
        if not cls.should_encrypt(source.name):
            return source
        destination = (
            Path(output_path)
            if output_path is not None
            else source.with_name(f"{source.name}.enc")
        )
        cls._require_distinct_paths(source, destination)
        encrypted = cls.encrypt_bytes(source.read_bytes(), key)
        cls.write_bytes_atomically(destination, encrypted)
        return destination

    @classmethod
    def decrypt_file(
        cls,
        encrypted_path: Path | str,
        key: bytes,
        output_path: Path | str | None = None,
    ) -> Path:
        source = Path(encrypted_path)
        cls._validate_key(key)
        original_name = source.stem if source.suffix == ".enc" else source.name
        if output_path is None and not cls.should_encrypt(original_name):
            return source
        if output_path is not None:
            destination = Path(output_path)
        elif source.suffix == ".enc":
            destination = source.with_name(source.stem)
        else:
            destination = source.with_name(f"{source.name}.decrypted")
        cls._require_distinct_paths(source, destination)
        decrypted = cls.decrypt_bytes(source.read_bytes(), key)
        cls.write_bytes_atomically(destination, decrypted)
        return destination

    @classmethod
    def should_encrypt(cls, name: str, content_type: str | None = None) -> bool:
        if not isinstance(name, str):
            raise ValueError("Nama file tidak valid.")
        if Path(name).suffix.lower() in cls._image_extensions:
            return False
        if isinstance(content_type, str) and content_type.lower().startswith("image/"):
            return False
        return True

    @classmethod
    def is_encrypted(cls, content: bytes) -> bool:
        return isinstance(content, bytes) and content.startswith(cls._header)

    @classmethod
    def _validate_key(cls, key: bytes) -> None:
        if not isinstance(key, bytes) or len(key) != cls.key_size:
            raise ValueError("Kunci AES-GCM harus berukuran tepat 32 byte.")

    @staticmethod
    def _require_distinct_paths(source: Path, destination: Path) -> None:
        if source.resolve() == destination.resolve():
            raise ValueError("File sumber dan tujuan tidak boleh sama.")

    @staticmethod
    def write_bytes_atomically(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=path.parent,
                prefix=".usl-",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(content)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            temporary_path.replace(path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
