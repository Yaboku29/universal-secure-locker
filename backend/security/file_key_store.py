import ctypes
import os
import secrets
import tempfile
from ctypes import wintypes
from pathlib import Path

from backend.security.file_crypto import FileEncryption


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


class WindowsFileKeyStore:
    _entropy = b"Universal Secure Locker AES-GCM key v1"

    def __init__(self, path: Path) -> None:
        self.path = path

    def load_or_create(self) -> bytes:
        if self.path.exists():
            key = self._unprotect(self.path.read_bytes())
            FileEncryption._validate_key(key)
            return key

        key = secrets.token_bytes(FileEncryption.key_size)
        protected_key = self._protect(key)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.path.parent,
                prefix=".usl-key-",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(protected_key)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            temporary_path.replace(self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return key

    @classmethod
    def _protect(cls, data: bytes) -> bytes:
        return cls._transform(data, protect=True)

    @classmethod
    def _unprotect(cls, data: bytes) -> bytes:
        return cls._transform(data, protect=False)

    @classmethod
    def _transform(cls, data: bytes, protect: bool) -> bytes:
        win_dll = getattr(ctypes, "WinDLL", None)
        if win_dll is None:
            raise OSError("Windows DPAPI tidak tersedia pada platform ini.")
        crypt32 = win_dll("crypt32", use_last_error=True)
        kernel32 = win_dll("kernel32", use_last_error=True)
        input_buffer = ctypes.create_string_buffer(data)
        entropy_buffer = ctypes.create_string_buffer(cls._entropy)
        input_blob = _DataBlob(
            len(data),
            ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_ubyte)),
        )
        entropy_blob = _DataBlob(
            len(cls._entropy),
            ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_ubyte)),
        )
        output_blob = _DataBlob()
        if protect:
            function = crypt32.CryptProtectData
            function.argtypes = [
                ctypes.POINTER(_DataBlob),
                wintypes.LPCWSTR,
                ctypes.POINTER(_DataBlob),
                ctypes.c_void_p,
                ctypes.c_void_p,
                wintypes.DWORD,
                ctypes.POINTER(_DataBlob),
            ]
            function.restype = wintypes.BOOL
            succeeded = function(
                ctypes.byref(input_blob),
                "Universal Secure Locker",
                ctypes.byref(entropy_blob),
                None,
                None,
                0,
                ctypes.byref(output_blob),
            )
        else:
            function = crypt32.CryptUnprotectData
            function.argtypes = [
                ctypes.POINTER(_DataBlob),
                ctypes.POINTER(wintypes.LPWSTR),
                ctypes.POINTER(_DataBlob),
                ctypes.c_void_p,
                ctypes.c_void_p,
                wintypes.DWORD,
                ctypes.POINTER(_DataBlob),
            ]
            function.restype = wintypes.BOOL
            succeeded = function(
                ctypes.byref(input_blob),
                None,
                ctypes.byref(entropy_blob),
                None,
                None,
                0,
                ctypes.byref(output_blob),
            )

        if not succeeded:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            kernel32.LocalFree.argtypes = [ctypes.c_void_p]
            kernel32.LocalFree.restype = ctypes.c_void_p
            kernel32.LocalFree(ctypes.cast(output_blob.pbData, ctypes.c_void_p))
