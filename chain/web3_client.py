"""
Polygon Amoy Web3 Client
-------------------------
Connects to the deployed PostAnchor.sol contract on Polygon Amoy testnet
(chain ID 80002) and provides the same anchor/lookup interface as
LocalChain, so the rest of the pipeline can treat both backends the
same way (see the Strategy-pattern discussion: both expose anchor()
and lookup()).

Requires in .env:
    POLYGON_AMOY_RPC_URL
    WALLET_PRIVATE_KEY
    POST_ANCHOR_CONTRACT_ADDRESS
"""

import os
from config.config import AMOY_CHAIN_ID
from web3 import Web3



# Minimal ABI -- only the functions/events we actually call.
CONTRACT_ABI = [
    {
        "inputs": [{"internalType": "bytes32", "name": "recordHash", "type": "bytes32"}],
        "name": "anchor",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "recordHash", "type": "bytes32"}],
        "name": "verify",
        "outputs": [
            {"internalType": "bool", "name": "found", "type": "bool"},
            {"internalType": "address", "name": "submitter", "type": "address"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


class AmoyChain:
    def __init__(
        self,
        rpc_url: str | None = None,
        private_key: str | None = None,
        contract_address: str | None = None,
    ):
        self.rpc_url = rpc_url or os.environ.get("POLYGON_AMOY_RPC_URL")
        self.private_key = private_key or os.environ.get("WALLET_PRIVATE_KEY")
        self.contract_address = contract_address or os.environ.get("POST_ANCHOR_CONTRACT_ADDRESS")

        if not all([self.rpc_url, self.private_key, self.contract_address]):
            raise ValueError(
                "Missing config. Set POLYGON_AMOY_RPC_URL, WALLET_PRIVATE_KEY, "
                "and POST_ANCHOR_CONTRACT_ADDRESS (in .env or passed explicitly)."
            )

        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        if not self.w3.is_connected():
            raise ConnectionError(f"Could not connect to RPC at {self.rpc_url}")

        self.account = self.w3.eth.account.from_key(self.private_key)
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.contract_address),
            abi=CONTRACT_ABI,
        )

    @staticmethod
    def _to_bytes32(hex_hash: str) -> bytes:
        """Convert a hex string (e.g. SHA-256 hexdigest) into bytes32 for Solidity."""
        return bytes.fromhex(hex_hash.replace("0x", ""))

    def anchor(self, record_hash: str) -> dict:
        """
        Submit a transaction anchoring record_hash on-chain.

        Returns
        -------
        dict with tx_hash, block_number, and a link to view it on PolygonScan.
        """
        bytes32_hash = self._to_bytes32(record_hash)

        tx = self.contract.functions.anchor(bytes32_hash).build_transaction({
            "chainId": AMOY_CHAIN_ID,
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "gas": 200_000,
            "gasPrice": self.w3.eth.gas_price,
        })

        signed_tx = self.w3.eth.account.sign_transaction(tx, private_key=self.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

        tx_hash_hex = "0x" + tx_hash.hex().removeprefix("0x")  # ensure 0x prefix regardless of web3.py version

        return {
            "tx_hash": tx_hash_hex,
            "block_number": receipt["blockNumber"],
            "explorer_url": f"https://amoy.polygonscan.com/tx/{tx_hash_hex}",
        }

    def lookup(self, record_hash: str) -> dict | None:
        """
        Read-only check: does this hash exist on-chain?

        Returns
        -------
        dict with submitter address and timestamp if found, else None.
        Free to call -- no gas cost, no transaction needed (view function).
        """
        bytes32_hash = self._to_bytes32(record_hash)
        found, submitter, timestamp = self.contract.functions.verify(bytes32_hash).call()

        if not found:
            return None

        return {
            "submitter": submitter,
            "timestamp": timestamp,
        }


if __name__ == "__main__":
    import hashlib
    import sys

    from dotenv import load_dotenv
    load_dotenv()

    chain = AmoyChain()

    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        test_hash = hashlib.sha256(b"test record").hexdigest()
        result = chain.lookup(test_hash)
        print(f"Lookup result: {result}")
    else:
        test_hash = hashlib.sha256(b"test record").hexdigest()
        print(f"Anchoring test hash: {test_hash}")
        result = chain.anchor(test_hash)
        print(f"Anchored! Tx: {result['explorer_url']}")
