"""
Local Simulated Blockchain
---------------------------
A minimal proof-of-work chain implemented in pure Python, persisted to
a local JSON file. This is NOT a real distributed blockchain -- there's
no network of independent nodes keeping each other honest, so whoever
controls local_chain.json can technically edit it directly.

What it DOES demonstrate genuinely:
  - Hash-chaining (each block references the previous block's hash)
  - Proof-of-work (mining requires finding a nonce that produces a hash
    with a given number of leading zeros -- cheap to verify, costly to
    forge/redo for every subsequent block)
  - Tamper-evidence WITHIN this file's own internal consistency: if you
    edit an old block's data without re-mining every block after it,
    the chain's hash-links break and validate_chain() will catch it.

This satisfies the hackathon's "local/simulated chain is acceptable"
allowance while being explicit and honest about what it does and
doesn't guarantee (see README's Known Limitations section).
"""

import hashlib
import json
import os
import time
from config.config import LOCAL_CHAIN_DIFFICULTY_PREFIX, LOCAL_CHAIN_FILE

CHAIN_FILE = LOCAL_CHAIN_FILE
DIFFICULTY_PREFIX = LOCAL_CHAIN_DIFFICULTY_PREFIX  # number of leading hex zeros required to "mine" a block


class LocalChain:
    def __init__(self, chain_file: str = CHAIN_FILE):
        self.chain_file = chain_file
        os.makedirs(os.path.dirname(chain_file), exist_ok=True)
        self.blocks = self._load()
        if not self.blocks:
            self.blocks = [self._genesis_block()]
            self._save()

    # ---- persistence -------------------------------------------------

    def _load(self) -> list[dict]:
        if not os.path.exists(self.chain_file):
            return []
        with open(self.chain_file, "r") as f:
            return json.load(f)

    def _save(self):
        with open(self.chain_file, "w") as f:
            json.dump(self.blocks, f, indent=2)

    # ---- block construction -------------------------------------------

    def _genesis_block(self) -> dict:
        return {
            "index": 0,
            "timestamp": time.time(),
            "previous_hash": "0" * 64,
            "record_hash": None,
            "nonce": 0,
            "block_hash": "genesis",
        }

    @staticmethod
    def _compute_block_hash(index, timestamp, previous_hash, record_hash, nonce) -> str:
        payload = f"{index}:{timestamp}:{previous_hash}:{record_hash}:{nonce}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _mine_block(self, record_hash: str) -> dict:
        """
        Proof-of-work: increment nonce until the resulting block_hash
        starts with DIFFICULTY_PREFIX. At '000' this is fast (milliseconds
        to a few seconds) -- intentionally low difficulty since this is a
        demonstration, not a real security-critical chain.
        """
        previous_block = self.blocks[-1]
        index = previous_block["index"] + 1
        timestamp = time.time()
        previous_hash = previous_block["block_hash"]

        nonce = 0
        while True:
            candidate_hash = self._compute_block_hash(
                index, timestamp, previous_hash, record_hash, nonce
            )
            if candidate_hash.startswith(DIFFICULTY_PREFIX):
                break
            nonce += 1

        return {
            "index": index,
            "timestamp": timestamp,
            "previous_hash": previous_hash,
            "record_hash": record_hash,
            "nonce": nonce,
            "block_hash": candidate_hash,
        }

    # ---- public API -----------------------------------------------------

    def anchor(self, record_hash: str) -> dict:
        """Mine and append a new block containing record_hash. Returns the block."""
        block = self._mine_block(record_hash)
        self.blocks.append(block)
        self._save()
        return block

    def lookup(self, record_hash: str) -> dict | None:
        """Return the block containing record_hash, or None if not found."""
        for block in self.blocks:
            if block.get("record_hash") == record_hash:
                return block
        return None

    def validate_chain(self) -> bool:
        """
        Recompute every block's hash and every hash-link, confirming the
        chain hasn't been internally tampered with (e.g. someone edited
        an old block's record_hash by hand in the JSON file).
        """
        for i in range(1, len(self.blocks)):
            block = self.blocks[i]
            prev_block = self.blocks[i - 1]

            if block["previous_hash"] != prev_block["block_hash"]:
                return False

            recomputed = self._compute_block_hash(
                block["index"], block["timestamp"], block["previous_hash"],
                block["record_hash"], block["nonce"],
            )
            if recomputed != block["block_hash"]:
                return False

        return True


if __name__ == "__main__":
    chain = LocalChain()
    test_hash = "deadbeef" * 8
    print("Mining test block...")
    block = chain.anchor(test_hash)
    print(f"Mined block #{block['index']}, hash={block['block_hash']}, nonce={block['nonce']}")

    found = chain.lookup(test_hash)
    print(f"Lookup result: {'FOUND' if found else 'NOT FOUND'}")

    print(f"Chain valid: {chain.validate_chain()}")
