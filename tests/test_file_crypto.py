import tempfile
import unittest
from pathlib import Path

from backend.security.file_crypto import FileEncryption


class FileEncryptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = bytes(range(FileEncryption.key_size))

    def test_encrypted_file_is_opaque_and_decrypts_to_original_bytes(self) -> None:
        original = b"%PDF-1.7\nprivate document contents"
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "document.pdf"
            source.write_bytes(original)

            encrypted_path = FileEncryption.encrypt_file(source, self.key)
            encrypted_content = encrypted_path.read_bytes()
            decrypted_path = FileEncryption.decrypt_file(encrypted_path, self.key)

            self.assertTrue(FileEncryption.is_encrypted(encrypted_content))
            self.assertNotIn(original, encrypted_content)
            self.assertEqual(decrypted_path.read_bytes(), original)
            self.assertEqual(encrypted_path, source.with_name("document.pdf.enc"))

    def test_aes_gcm_detects_tampering_and_wrong_keys(self) -> None:
        encrypted = bytearray(FileEncryption.encrypt_bytes(b"secret", self.key))
        encrypted[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "kunci salah atau data telah berubah"):
            FileEncryption.decrypt_bytes(bytes(encrypted), self.key)
        with self.assertRaisesRegex(ValueError, "kunci salah atau data telah berubah"):
            FileEncryption.decrypt_bytes(
                FileEncryption.encrypt_bytes(b"secret", self.key),
                bytes(reversed(self.key)),
            )

    def test_image_extensions_are_excluded_but_common_documents_are_encrypted(self) -> None:
        for image_name in ("photo.png", "photo.JPG", "scan.webp"):
            with self.subTest(image_name=image_name):
                self.assertFalse(FileEncryption.should_encrypt(image_name))
        self.assertFalse(
            FileEncryption.should_encrypt("image.bin", "image/jpeg")
        )
        for document_name in ("report.pdf", "notes.txt", "clip.mp4"):
            with self.subTest(document_name=document_name):
                self.assertTrue(FileEncryption.should_encrypt(document_name))

    def test_encrypt_file_refuses_to_replace_its_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "report.txt"
            original = b"do not overwrite"
            source.write_bytes(original)
            with self.assertRaisesRegex(ValueError, "sumber dan tujuan"):
                FileEncryption.encrypt_file(source, self.key, source)
            self.assertEqual(source.read_bytes(), original)

    def test_file_helpers_leave_images_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "photo.png"
            original = b"\x89PNG\r\n\x1a\noriginal image"
            source.write_bytes(original)

            encrypted_path = FileEncryption.encrypt_file(source, self.key)
            decrypted_path = FileEncryption.decrypt_file(source, self.key)

            self.assertEqual(encrypted_path, source)
            self.assertEqual(decrypted_path, source)
            self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
