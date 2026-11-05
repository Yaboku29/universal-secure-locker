import re
import unittest

from backend.security.crypto_engine import SuperEncryption


class SuperEncryptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.key_pair = SuperEncryption.generate_rsa_key_pair()

    def test_round_trip_supports_unicode_and_multiblock_text(self) -> None:
        plaintext = "Halo, Closure! Rahasia 🚀 — baris kedua. " * 25
        ciphertext = SuperEncryption.encrypt_text(
            plaintext, 7, "LockerKey2026", self.key_pair["public_key"]
        )

        self.assertRegex(ciphertext, re.compile(r"^[0-9a-f]+$"))
        self.assertGreater(len(ciphertext), 2 * 384)
        self.assertEqual(
            SuperEncryption.decrypt_text(
                ciphertext, 7, "LockerKey2026", self.key_pair["private_key"]
            ),
            plaintext,
        )

    def test_rsa_oaep_randomizes_ciphertext(self) -> None:
        ciphertexts = {
            SuperEncryption.encrypt_text(
                "same plaintext", 3, "LockerKey2026", self.key_pair["public_key"]
            )
            for _ in range(2)
        }
        self.assertEqual(len(ciphertexts), 2)

    def test_numeric_shared_key_can_be_used_for_both_classical_layers(self) -> None:
        ciphertext = SuperEncryption.encrypt_text(
            "numeric key works", 0, "123456789012", self.key_pair["public_key"]
        )
        self.assertEqual(
            SuperEncryption.decrypt_text(
                ciphertext, 0, "123456789012", self.key_pair["private_key"]
            ),
            "numeric key works",
        )

    def test_decryption_rejects_wrong_keys_and_malformed_ciphertext(self) -> None:
        ciphertext = SuperEncryption.encrypt_text(
            "secret", 3, "LockerKey2026", self.key_pair["public_key"]
        )
        wrong_key_pair = SuperEncryption.generate_rsa_key_pair()

        with self.assertRaisesRegex(ValueError, "Dekripsi RSA gagal"):
            SuperEncryption.decrypt_text(
                ciphertext, 3, "LockerKey2026", wrong_key_pair["private_key"]
            )
        with self.assertRaisesRegex(ValueError, "heksadesimal"):
            SuperEncryption.decrypt_text(
                "not-ciphertext", 3, "LockerKey2026", self.key_pair["private_key"]
            )

    def test_invalid_shift_and_short_shared_key_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "12–128"):
            SuperEncryption.encrypt_text(
                "secret", 3, "short", self.key_pair["public_key"]
            )
        with self.assertRaisesRegex(ValueError, "0 dan 25"):
            SuperEncryption.encrypt_text(
                "secret", 26, "LockerKey2026", self.key_pair["public_key"]
            )

    def test_text_over_16_kib_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "maksimal 16 KiB"):
            SuperEncryption.encrypt_text(
                "x" * (SuperEncryption.max_plaintext_bytes + 1),
                3,
                "LockerKey2026",
                self.key_pair["public_key"],
            )

    def test_generated_rsa_key_pair_uses_at_least_3072_bits(self) -> None:
        public_key = SuperEncryption._load_public_key(self.key_pair["public_key"])
        self.assertGreaterEqual(public_key.key_size, 3072)


if __name__ == "__main__":
    unittest.main()
