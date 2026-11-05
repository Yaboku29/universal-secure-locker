import os
import tempfile
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class DatabaseFileEncryption:
    key_size = 32
    nonce_size = 12
    _header = b"USLDB\x01"

    @classmethod
    def encrypt_bytes(cls, content: bytes, key: bytes) -> bytes:
        cls._validate_key(key)
        if not isinstance(content, bytes):
            raise ValueError("Isi database harus berupa bytes.")
        if cls.is_encrypted(content):
            raise ValueError("Database sudah terenkripsi.")
        nonce = os.urandom(cls.nonce_size)
        ciphertext = AESGCM(key).encrypt(nonce, content, cls._header)
        return cls._header + nonce + ciphertext

    @classmethod
    def decrypt_bytes(cls, encrypted_content: bytes, key: bytes) -> bytes:
        cls._validate_key(key)
        minimum_size = len(cls._header) + cls.nonce_size + 16
        if (
            not isinstance(encrypted_content, bytes)
            or len(encrypted_content) < minimum_size
            or not cls.is_encrypted(encrypted_content)
        ):
            raise ValueError("Format database terenkripsi tidak valid.")
        nonce_start = len(cls._header)
        ciphertext_start = nonce_start + cls.nonce_size
        try:
            return AESGCM(key).decrypt(
                encrypted_content[nonce_start:ciphertext_start],
                encrypted_content[ciphertext_start:],
                cls._header,
            )
        except InvalidTag as error:
            raise ValueError(
                "Database gagal didekripsi: kunci salah atau data telah berubah."
            ) from error

    @classmethod
    def seal(cls, path: Path, key: bytes) -> None:
        cls.seal_to(path, path, key)

    @classmethod
    def seal_to(cls, source: Path, destination: Path, key: bytes) -> None:
        cls._validate_key(key)
        if not source.exists():
            return
        content = source.read_bytes()
        if cls.is_encrypted(content):
            if source.resolve() != destination.resolve():
                cls._write_atomically(destination, content)
            return
        cls._write_atomically(destination, cls.encrypt_bytes(content, key))

    @classmethod
    def unlock(cls, path: Path, key: bytes) -> None:
        cls.unlock_to(path, path, key)

    @classmethod
    def unlock_to(cls, source: Path, destination: Path, key: bytes) -> None:
        cls._validate_key(key)
        if not source.exists():
            return
        content = source.read_bytes()
        encrypted = cls.is_encrypted(content)
        if encrypted:
            content = cls.decrypt_bytes(content, key)
        if source.resolve() != destination.resolve() or encrypted:
            cls._write_atomically(destination, content)

    @classmethod
    def is_encrypted(cls, content: bytes) -> bool:
        return isinstance(content, bytes) and content.startswith(cls._header)

    @classmethod
    def _validate_key(cls, key: bytes) -> None:
        if not isinstance(key, bytes) or len(key) != cls.key_size:
            raise ValueError("Kunci database AES-GCM harus berukuran 32 byte.")

    @staticmethod
    def _write_atomically(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=path.parent,
                prefix=".usl-db-",
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
