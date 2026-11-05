import math
import re

from cryptography.exceptions import InvalidKey, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class SuperEncryption:
    key_min_length = 12
    key_max_length = 128
    max_plaintext_bytes = 16 * 1024
    rsa_key_size = 3072
    min_rsa_key_size = 2048
    max_rsa_key_size = 4096
    max_key_pem_length = 20_000
    _ciphertext_pattern = re.compile(r"^[0-9a-fA-F]+$")

    @classmethod
    def generate_rsa_key_pair(cls) -> dict[str, str]:
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=cls.rsa_key_size,
        )
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii")
        return {"public_key": public_pem, "private_key": private_pem}

    @classmethod
    def encrypt_text(
        cls,
        plaintext: str,
        shift: int,
        key: str,
        public_key_pem: str,
    ) -> str:
        cls._validate_text(plaintext, "Pesan")
        payload = plaintext.encode("utf-8")
        if not payload:
            raise ValueError("Pesan tidak boleh kosong.")
        if len(payload) > cls.max_plaintext_bytes:
            raise ValueError("Pesan maksimal 16 KiB setelah dikodekan sebagai UTF-8.")

        normalized_shift, key_letters, key_bytes = cls._validate_parameters(
            shift, key
        )
        public_key = cls._load_public_key(public_key_pem)
        caesar_text = cls._shift_letters(plaintext, normalized_shift)
        vigenere_text = cls._vigenere(caesar_text, key_letters, decrypt=False)
        xor_payload = cls._xor(vigenere_text.encode("utf-8"), key_bytes)
        encrypted = cls._rsa_encrypt_blocks(public_key, xor_payload)
        return encrypted.hex()

    @classmethod
    def decrypt_text(
        cls,
        ciphertext: str,
        shift: int,
        key: str,
        private_key_pem: str,
    ) -> str:
        cls._validate_text(ciphertext, "Ciphertext")
        if not ciphertext or not cls._ciphertext_pattern.fullmatch(ciphertext):
            raise ValueError("Ciphertext harus berupa string heksadesimal.")

        normalized_shift, key_letters, key_bytes = cls._validate_parameters(
            shift, key
        )
        private_key = cls._load_private_key(private_key_pem)
        block_bytes = (private_key.key_size + 7) // 8
        if len(ciphertext) % (block_bytes * 2):
            raise ValueError("Ciphertext tidak sesuai dengan ukuran kunci RSA.")

        block_count = len(ciphertext) // (block_bytes * 2)
        max_plaintext_block = block_bytes - 2 * hashes.SHA256().digest_size - 2
        max_blocks = math.ceil(cls.max_plaintext_bytes / max_plaintext_block)
        if block_count > max_blocks:
            raise ValueError("Ciphertext melebihi batas ukuran pesan 16 KiB.")

        encrypted = bytes.fromhex(ciphertext)
        xor_payload = cls._rsa_decrypt_blocks(
            private_key, encrypted, block_bytes
        )
        if len(xor_payload) > cls.max_plaintext_bytes:
            raise ValueError("Pesan hasil dekripsi melebihi batas 16 KiB.")

        vigenere_bytes = cls._xor(xor_payload, key_bytes)
        try:
            vigenere_text = vigenere_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(
                "Dekripsi gagal. Periksa kunci, Caesar shift, dan ciphertext."
            ) from error
        caesar_text = cls._vigenere(
            vigenere_text, key_letters, decrypt=True
        )
        return cls._shift_letters(caesar_text, -normalized_shift)

    @staticmethod
    def _validate_text(value: str, label: str) -> None:
        if not isinstance(value, str):
            raise ValueError(f"{label} harus berupa teks.")

    @classmethod
    def _validate_parameters(
        cls, shift: int, key: str
    ) -> tuple[int, tuple[int, ...], bytes]:
        if (
            not isinstance(shift, int)
            or isinstance(shift, bool)
            or not 0 <= shift <= 25
        ):
            raise ValueError("Caesar shift harus berupa angka antara 0 dan 25.")
        if (
            not isinstance(key, str)
            or not cls.key_min_length <= len(key) <= cls.key_max_length
            or not key.isascii()
            or not key.isalnum()
        ):
            raise ValueError(
                "Kunci Vigenere/XOR harus terdiri dari 12–128 huruf atau angka ASCII."
            )
        key_shifts = tuple(
            ord(character.lower()) - ord("a")
            if character.isalpha()
            else int(character)
            for character in key
        )
        return shift, key_shifts, key.encode("ascii")

    @staticmethod
    def _shift_letters(text: str, shift: int) -> str:
        shifted: list[str] = []
        for character in text:
            if "a" <= character <= "z":
                shifted.append(
                    chr((ord(character) - ord("a") + shift) % 26 + ord("a"))
                )
            elif "A" <= character <= "Z":
                shifted.append(
                    chr((ord(character) - ord("A") + shift) % 26 + ord("A"))
                )
            else:
                shifted.append(character)
        return "".join(shifted)

    @staticmethod
    def _vigenere(text: str, key: tuple[int, ...], decrypt: bool) -> str:
        result: list[str] = []
        key_index = 0
        direction = -1 if decrypt else 1
        for character in text:
            if "a" <= character <= "z":
                base = ord("a")
                key_shift = key[key_index % len(key)]
                result.append(
                    chr((ord(character) - base + direction * key_shift) % 26 + base)
                )
                key_index += 1
            elif "A" <= character <= "Z":
                base = ord("A")
                key_shift = key[key_index % len(key)]
                result.append(
                    chr((ord(character) - base + direction * key_shift) % 26 + base)
                )
                key_index += 1
            else:
                result.append(character)
        return "".join(result)

    @staticmethod
    def _xor(payload: bytes, key: bytes) -> bytes:
        return bytes(
            value ^ key[index % len(key)] for index, value in enumerate(payload)
        )

    @classmethod
    def _load_public_key(cls, public_key_pem: str) -> rsa.RSAPublicKey:
        if (
            not isinstance(public_key_pem, str)
            or len(public_key_pem) > cls.max_key_pem_length
        ):
            raise ValueError("Public key RSA PEM tidak valid atau terlalu besar.")
        try:
            key = serialization.load_pem_public_key(public_key_pem.encode("ascii"))
        except (UnicodeEncodeError, ValueError, UnsupportedAlgorithm) as error:
            raise ValueError("Public key RSA PEM tidak valid.") from error
        if (
            not isinstance(key, rsa.RSAPublicKey)
            or not cls.min_rsa_key_size <= key.key_size <= cls.max_rsa_key_size
        ):
            raise ValueError("Gunakan public key RSA berukuran 2048–4096 bit.")
        return key

    @classmethod
    def _load_private_key(cls, private_key_pem: str) -> rsa.RSAPrivateKey:
        if (
            not isinstance(private_key_pem, str)
            or len(private_key_pem) > cls.max_key_pem_length
        ):
            raise ValueError("Private key RSA PEM tidak valid atau terlalu besar.")
        try:
            key = serialization.load_pem_private_key(
                private_key_pem.encode("ascii"), password=None
            )
        except (
            UnicodeEncodeError,
            TypeError,
            ValueError,
            UnsupportedAlgorithm,
        ) as error:
            raise ValueError(
                "Private key RSA PEM tidak valid atau memakai passphrase."
            ) from error
        if (
            not isinstance(key, rsa.RSAPrivateKey)
            or not cls.min_rsa_key_size <= key.key_size <= cls.max_rsa_key_size
        ):
            raise ValueError("Gunakan private key RSA berukuran 2048–4096 bit.")
        return key

    @staticmethod
    def _oaep_padding() -> padding.OAEP:
        return padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        )

    @classmethod
    def _rsa_encrypt_blocks(
        cls, public_key: rsa.RSAPublicKey, payload: bytes
    ) -> bytes:
        block_bytes = (public_key.key_size + 7) // 8
        max_plaintext_block = block_bytes - 2 * hashes.SHA256().digest_size - 2
        return b"".join(
            public_key.encrypt(
                payload[offset : offset + max_plaintext_block],
                cls._oaep_padding(),
            )
            for offset in range(0, len(payload), max_plaintext_block)
        )

    @classmethod
    def _rsa_decrypt_blocks(
        cls, private_key: rsa.RSAPrivateKey, payload: bytes, block_bytes: int
    ) -> bytes:
        try:
            return b"".join(
                private_key.decrypt(
                    payload[offset : offset + block_bytes], cls._oaep_padding()
                )
                for offset in range(0, len(payload), block_bytes)
            )
        except (ValueError, InvalidKey) as error:
            raise ValueError(
                "Dekripsi RSA gagal. Pastikan kunci privat dan ciphertext cocok."
            ) from error