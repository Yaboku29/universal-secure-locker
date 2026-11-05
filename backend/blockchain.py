import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, TypedDict


class AuditBlock(TypedDict):
    index: int
    timestamp: str
    action_data: str
    previous_hash: str
    hash: str


class MiniBlockchain:
    genesis_action = "Genesis Block"
    genesis_previous_hash = "0" * 64

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.init_db()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _calculate_hash(
        index: int,
        timestamp: str,
        action_data: str,
        previous_hash: str,
    ) -> str:
        block_content = json.dumps(
            {
                "index": index,
                "timestamp": timestamp,
                "action_data": action_data,
                "previous_hash": previous_hash,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(block_content).hexdigest()

    @classmethod
    def _make_block(
        cls,
        index: int,
        timestamp: str,
        action_data: str,
        previous_hash: str,
    ) -> AuditBlock:
        return {
            "index": index,
            "timestamp": timestamp,
            "action_data": action_data,
            "previous_hash": previous_hash,
            "hash": cls._calculate_hash(
                index, timestamp, action_data, previous_hash
            ),
        }

    def init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS blockchain_blocks (
                    block_index INTEGER PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    action_data TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    block_hash TEXT NOT NULL UNIQUE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS blockchain_state (
                    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                    latest_index INTEGER NOT NULL,
                    latest_hash TEXT NOT NULL
                )
                """
            )
            connection.execute("BEGIN IMMEDIATE")
            first_block = connection.execute(
                "SELECT 1 FROM blockchain_blocks LIMIT 1"
            ).fetchone()
            if first_block is None:
                state = connection.execute(
                    "SELECT 1 FROM blockchain_state WHERE singleton_id = 1"
                ).fetchone()
                if state is None:
                    timestamp = datetime.now(timezone.utc).isoformat()
                    genesis = self._make_block(
                        0,
                        timestamp,
                        self.genesis_action,
                        self.genesis_previous_hash,
                    )
                    connection.execute(
                        """
                        INSERT INTO blockchain_blocks
                            (block_index, timestamp, action_data, previous_hash, block_hash)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            genesis["index"],
                            genesis["timestamp"],
                            genesis["action_data"],
                            genesis["previous_hash"],
                            genesis["hash"],
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO blockchain_state
                            (singleton_id, latest_index, latest_hash)
                        VALUES (1, ?, ?)
                        """,
                        (genesis["index"], genesis["hash"]),
                    )

    def add_audit_log(self, action_data: str) -> AuditBlock:
        if not isinstance(action_data, str) or not action_data.strip():
            raise ValueError("Data aktivitas audit tidak boleh kosong.")
        normalized_action = action_data.strip()
        if len(normalized_action) > 4000:
            raise ValueError("Data aktivitas audit maksimal 4000 karakter.")

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                """
                SELECT block_index, block_hash FROM blockchain_blocks
                ORDER BY block_index DESC LIMIT 1
                """
            ).fetchone()
            if previous is None:
                raise RuntimeError("Genesis block belum dibuat.")
            state = connection.execute(
                """
                SELECT latest_index, latest_hash
                FROM blockchain_state WHERE singleton_id = 1
                """
            ).fetchone()
            if (
                state is None
                or int(state["latest_index"]) != int(previous["block_index"])
                or str(state["latest_hash"]) != str(previous["block_hash"])
            ):
                raise RuntimeError("Ledger audit tidak valid; aktivitas tidak dicatat.")
            block = self._make_block(
                int(previous["block_index"]) + 1,
                datetime.now(timezone.utc).isoformat(),
                normalized_action,
                str(previous["block_hash"]),
            )
            connection.execute(
                """
                INSERT INTO blockchain_blocks
                    (block_index, timestamp, action_data, previous_hash, block_hash)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    block["index"],
                    block["timestamp"],
                    block["action_data"],
                    block["previous_hash"],
                    block["hash"],
                ),
            )
            connection.execute(
                """
                UPDATE blockchain_state
                SET latest_index = ?, latest_hash = ?
                WHERE singleton_id = 1
                """,
                (block["index"], block["hash"]),
            )
        return block

    def get_chain(self) -> list[AuditBlock]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT block_index, timestamp, action_data, previous_hash, block_hash
                FROM blockchain_blocks ORDER BY block_index
                """
            ).fetchall()
        return [
            {
                "index": int(row["block_index"]),
                "timestamp": str(row["timestamp"]),
                "action_data": str(row["action_data"]),
                "previous_hash": str(row["previous_hash"]),
                "hash": str(row["block_hash"]),
            }
            for row in rows
        ]

    def is_chain_valid(self) -> bool:
        chain = self.get_chain()
        if not chain:
            return False
        with self._connect() as connection:
            state = connection.execute(
                """
                SELECT latest_index, latest_hash
                FROM blockchain_state WHERE singleton_id = 1
                """
            ).fetchone()
        if state is None:
            return False
        for expected_index, block in enumerate(chain):
            expected_previous_hash = (
                self.genesis_previous_hash
                if expected_index == 0
                else chain[expected_index - 1]["hash"]
            )
            if (
                block["index"] != expected_index
                or block["previous_hash"] != expected_previous_hash
                or block["hash"]
                != self._calculate_hash(
                    block["index"],
                    block["timestamp"],
                    block["action_data"],
                    block["previous_hash"],
                )
            ):
                return False
        return (
            int(state["latest_index"]) == chain[-1]["index"]
            and str(state["latest_hash"]) == chain[-1]["hash"]
            and
            chain[0]["action_data"] == self.genesis_action
            and chain[0]["previous_hash"] == self.genesis_previous_hash
        )
