import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from backend.blockchain import MiniBlockchain


class MiniBlockchainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "audit.db"
        self.blockchain = MiniBlockchain(self.database_path)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_creates_genesis_and_appends_linked_blocks(self) -> None:
        genesis = self.blockchain.get_chain()
        self.assertEqual(len(genesis), 1)
        self.assertEqual(genesis[0]["index"], 0)
        self.assertEqual(genesis[0]["action_data"], "Genesis Block")
        self.assertEqual(genesis[0]["previous_hash"], "0" * 64)
        self.assertTrue(self.blockchain.is_chain_valid())

        first = self.blockchain.add_audit_log("Login 2FA berhasil.")
        second = self.blockchain.add_audit_log("Simpan catatan rahasia.")

        self.assertEqual(first["index"], 1)
        self.assertEqual(first["previous_hash"], genesis[0]["hash"])
        self.assertEqual(second["index"], 2)
        self.assertEqual(second["previous_hash"], first["hash"])
        self.assertEqual(
            MiniBlockchain(self.database_path).get_chain(),
            [*genesis, first, second],
        )
        self.assertTrue(self.blockchain.is_chain_valid())

    def test_detects_block_data_rewrite_and_deleted_block(self) -> None:
        self.blockchain.add_audit_log("File diperbarui.")
        self.blockchain.add_audit_log("File diunduh.")
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                "UPDATE blockchain_blocks SET action_data = ? WHERE block_index = 1",
                ("File diubah.",),
            )
            connection.commit()
        self.assertFalse(self.blockchain.is_chain_valid())

        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                "DELETE FROM blockchain_blocks WHERE block_index = 1"
            )
            connection.commit()
        self.assertFalse(self.blockchain.is_chain_valid())

    def test_rejects_empty_or_oversized_audit_data(self) -> None:
        for action_data in ("", "  ", "x" * 4001):
            with self.subTest(action_data_length=len(action_data)):
                with self.assertRaises(ValueError):
                    self.blockchain.add_audit_log(action_data)


if __name__ == "__main__":
    unittest.main()
