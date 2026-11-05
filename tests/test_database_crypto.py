import tempfile
import unittest
from pathlib import Path

from backend.security.database_crypto import DatabaseFileEncryption


class DatabaseFileEncryptionTests(unittest.TestCase):
    def test_database_file_is_sealed_and_restored(self) -> None:
        key = bytes(range(DatabaseFileEncryption.key_size))
        original = b"SQLite format 3\x00 sensitive database contents"
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "accounts.db"
            database_path.write_bytes(original)

            DatabaseFileEncryption.seal(database_path, key)
            encrypted = database_path.read_bytes()
            self.assertTrue(DatabaseFileEncryption.is_encrypted(encrypted))
            self.assertNotIn(original, encrypted)

            DatabaseFileEncryption.unlock(database_path, key)
            self.assertEqual(database_path.read_bytes(), original)

    def test_database_ciphertext_rejects_wrong_keys_and_tampering(self) -> None:
        key = bytes(range(DatabaseFileEncryption.key_size))
        encrypted = DatabaseFileEncryption.encrypt_bytes(b"database", key)

        with self.assertRaisesRegex(ValueError, "kunci salah"):
            DatabaseFileEncryption.decrypt_bytes(encrypted, b"x" * 32)
        tampered = encrypted[:-1] + bytes([encrypted[-1] ^ 1])
        with self.assertRaisesRegex(ValueError, "kunci salah"):
            DatabaseFileEncryption.decrypt_bytes(tampered, key)


if __name__ == "__main__":
    unittest.main()
