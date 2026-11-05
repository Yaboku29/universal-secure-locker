import tempfile
import unittest
from pathlib import Path

from PIL import Image

from backend.security.crypto_engine import SuperEncryption
from backend.security.steganography import hide_message, reveal_message


class SteganographyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary_directory.name)
        self.source = self.directory / "source.png"
        self.output_directory = self.directory / "output"
        self.output_directory.mkdir()
        Image.new("RGB", (256, 256), (80, 120, 160)).save(self.source)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_round_trip_ciphertext_in_lossless_png(self) -> None:
        ciphertext = "a1b2c3d4" * 8
        output = hide_message(
            self.source, ciphertext, self.output_directory
        )

        self.assertEqual(output.name, "source.png")
        self.assertEqual(reveal_message(output), ciphertext)
        with Image.open(self.source) as original, Image.open(output) as encoded:
            self.assertEqual(encoded.format, "PNG")
            self.assertEqual(original.size, encoded.size)
            original_pixels = original.convert("RGB").tobytes()
            encoded_pixels = encoded.convert("RGB").tobytes()
            self.assertTrue(
                all(abs(before - after) <= 1 for before, after in zip(
                    original_pixels, encoded_pixels
                ))
            )

    def test_round_trip_preserves_transparency(self) -> None:
        source = self.directory / "transparent.png"
        output_directory = self.directory / "transparent-output"
        output_directory.mkdir()
        Image.new("RGBA", (256, 256), (10, 20, 30, 0)).save(source)

        output = hide_message(source, "deadc0de", output_directory)

        with Image.open(output) as encoded:
            self.assertEqual(encoded.mode, "RGBA")
            self.assertEqual(encoded.getchannel("A").tobytes(), bytes(256 * 256))
        self.assertEqual(reveal_message(output), "deadc0de")

    def test_super_encryption_ciphertext_can_be_hidden_and_revealed(self) -> None:
        key_pair = SuperEncryption.generate_rsa_key_pair()
        ciphertext = SuperEncryption.encrypt_text(
            "steganografi aman",
            7,
            "LockerKey2026",
            key_pair["public_key"],
        )
        output_directory = self.directory / "ciphertext-output"
        output_directory.mkdir()

        output = hide_message(self.source, ciphertext, output_directory)

        extracted = reveal_message(output)
        self.assertEqual(extracted, ciphertext)
        self.assertEqual(
            SuperEncryption.decrypt_text(
                extracted, 7, "LockerKey2026", key_pair["private_key"]
            ),
            "steganografi aman",
        )

    def test_rejects_plaintext_non_png_and_insufficient_capacity(self) -> None:
        with self.assertRaisesRegex(ValueError, "ciphertext heksadesimal"):
            hide_message(self.source, "plain secret", self.output_directory)

        jpeg = self.directory / "source.jpg"
        Image.new("RGB", (128, 128)).save(jpeg)
        with self.assertRaisesRegex(ValueError, "PNG"):
            hide_message(jpeg, "deadbeef", self.output_directory)

        tiny = self.directory / "tiny.png"
        Image.new("RGB", (8, 8)).save(tiny)
        with self.assertRaisesRegex(ValueError, "Kapasitas"):
            hide_message(tiny, "a1" * 100, self.output_directory)

    def test_rejects_image_without_a_steganographic_message(self) -> None:
        with self.assertRaisesRegex(ValueError, "tidak ditemukan"):
            reveal_message(self.source)

    def test_preserves_name_and_adds_number_for_duplicates(self) -> None:
        original = self.source.read_bytes()
        existing_output = self.output_directory / "source.png"
        existing_output.write_bytes(b"existing file")

        output = hide_message(
            self.source, "deadbeef", self.output_directory
        )

        self.assertEqual(output.name, "source (1).png")
        self.assertEqual(existing_output.read_bytes(), b"existing file")
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(reveal_message(output), "deadbeef")


if __name__ == "__main__":
    unittest.main()
