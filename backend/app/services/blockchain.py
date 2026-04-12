"""
Web3.py blockchain service for ApiChain Kenya.

Connects to the Ethereum network (Hardhat local or Sepolia testnet),
loads contract ABIs, and provides methods for all TraceabilityRegistry
and RoleManager interactions.

Stage 1: Uses a single test wallet for all transactions.
Stage 2: Will switch to per-user wallet signing.
"""

import json
import os
import uuid
import logging
from pathlib import Path
from typing import Optional

from web3 import Web3
from web3.exceptions import ContractLogicError

logger = logging.getLogger(__name__)

# BatchState enum values matching the Solidity contract
BATCH_STATES = {
    0: "CREATED",
    1: "HARVESTED",
    2: "PROCESSED",
    3: "LAB_VERIFIED",
    4: "PACKAGED",
    5: "DISTRIBUTED",
}

# ABI directory relative to this file: app/services/ -> ../../contracts/abi/
ABI_DIR = Path(__file__).resolve().parent.parent.parent / "contracts" / "abi"


def _load_abi(filename: str) -> list:
    with open(ABI_DIR / filename) as f:
        return json.load(f)


class BlockchainService:
    """Wrapper around Web3.py for all smart contract interactions."""

    def __init__(self):
        rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8545")
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.chain_id = int(os.getenv("CHAIN_ID", "31337"))

        # Admin key (deployer, can grant/revoke roles)
        self.admin_key = os.getenv("ADMIN_PRIVATE_KEY", "")
        self.admin_address = (
            self.w3.eth.account.from_key(self.admin_key).address
            if self.admin_key
            else None
        )

        # Oracle key (for lab verification)
        self.oracle_key = os.getenv("ORACLE_PRIVATE_KEY", "")
        self.oracle_address = (
            self.w3.eth.account.from_key(self.oracle_key).address
            if self.oracle_key
            else None
        )

        # Contract addresses
        rm_address = os.getenv("ROLE_MANAGER_ADDRESS", "")
        reg_address = os.getenv("REGISTRY_ADDRESS", "")

        # Startup validation: warn about missing configuration
        if not self.admin_key:
            logger.warning("ADMIN_PRIVATE_KEY not set -- blockchain writes will fail")
        if not rm_address:
            logger.warning("ROLE_MANAGER_ADDRESS not set -- role management disabled")
        if not reg_address:
            logger.warning("REGISTRY_ADDRESS not set -- batch operations disabled")
        if not self.oracle_key:
            logger.warning("ORACLE_PRIVATE_KEY not set -- lab verification disabled")

        # Load ABIs and create contract instances
        rm_abi = _load_abi("RoleManager.json")
        reg_abi = _load_abi("TraceabilityRegistry.json")

        self.role_manager = (
            self.w3.eth.contract(
                address=Web3.to_checksum_address(rm_address), abi=rm_abi
            )
            if rm_address
            else None
        )
        self.registry = (
            self.w3.eth.contract(
                address=Web3.to_checksum_address(reg_address), abi=reg_abi
            )
            if reg_address
            else None
        )

        # Role constants (keccak256 of role name strings)
        self.BEEKEEPER_ROLE = Web3.keccak(text="BEEKEEPER")
        self.PROCESSOR_ROLE = Web3.keccak(text="PROCESSOR")
        self.ORACLE_ROLE = Web3.keccak(text="ORACLE")
        self.DISTRIBUTOR_ROLE = Web3.keccak(text="DISTRIBUTOR")

        # Log connection status at startup
        if self.is_connected:
            logger.info(f"BlockchainService connected to {rpc_url}")
            logger.info(f"  Admin: {self.admin_address or 'NOT SET'}")
            logger.info(f"  RoleManager: {'LOADED' if self.role_manager else 'NOT CONFIGURED'}")
            logger.info(f"  Registry: {'LOADED' if self.registry else 'NOT CONFIGURED'}")
        else:
            logger.warning(f"BlockchainService CANNOT connect to {rpc_url}")

    @property
    def is_connected(self) -> bool:
        try:
            return self.w3.is_connected()
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Account funding (for dev/testnet -- new wallets start with 0 ETH)
    # ------------------------------------------------------------------

    def fund_account(self, address: str, amount_eth: float = 0.1) -> Optional[str]:
        """
        Send ETH from admin wallet to a user wallet so it can pay gas.
        Only needed on Hardhat/testnet where new wallets have 0 balance.
        Returns tx hash or None if funding not needed or failed.
        """
        balance = self.w3.eth.get_balance(address)
        min_balance = self.w3.to_wei(0.01, "ether")
        if balance >= min_balance:
            return None  # already funded

        if not self.admin_key:
            logger.warning(f"Cannot fund {address}: no admin key")
            return None

        try:
            nonce = self.w3.eth.get_transaction_count(self.admin_address, "pending")
            tx = {
                "to": address,
                "value": self.w3.to_wei(amount_eth, "ether"),
                "gas": 21000,
                "gasPrice": self.w3.eth.gas_price,
                "nonce": nonce,
                "chainId": self.chain_id,
            }
            signed = self.w3.eth.account.sign_transaction(tx, self.admin_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
            logger.info(f"Funded {address} with {amount_eth} ETH (tx: {tx_hash.hex()})")
            return tx_hash.hex()
        except Exception as e:
            logger.error(f"Failed to fund {address}: {e}")
            return None

    # ------------------------------------------------------------------
    # Generic transaction helper
    # ------------------------------------------------------------------

    def _sign_and_send(self, contract_fn, private_key: str) -> str:
        """
        Build, sign, send a transaction and wait for receipt.

        Args:
            contract_fn: A prepared contract function call
                         (e.g., self.registry.functions.createBatch(...))
            private_key: Hex private key of the signer.

        Returns:
            Transaction hash as hex string.

        Raises:
            ContractLogicError: If the contract reverts.
            Exception: For network/connection errors.
        """
        account = self.w3.eth.account.from_key(private_key)
        nonce = self.w3.eth.get_transaction_count(account.address, "pending")

        tx = contract_fn.build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "chainId": self.chain_id,
                "gas": 500_000,
                "gasPrice": self.w3.eth.gas_price,
            }
        )

        signed = self.w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)

        if receipt["status"] != 1:
            raise Exception(
                f"Transaction reverted: {tx_hash.hex()}"
                # Consider including the operation type or additional context to make debugging easier.
            )

        return tx_hash.hex()

    # ------------------------------------------------------------------
    # Hash computation
    # ------------------------------------------------------------------

    @staticmethod
    def compute_data_hash(data: dict) -> bytes:
        """
        Compute keccak256 hash of a data dict for on-chain anchoring.
        Uses deterministic JSON serialization (sorted keys).
        Returns bytes32.
        """
        payload = json.dumps(data, sort_keys=True, default=str)
        return Web3.keccak(text=payload)

    def generate_batch_id(self, creator_address: str) -> bytes:
        """
        Generate a unique batch ID as bytes32.
        keccak256(abi.encodePacked(creatorAddress, uuid, chainId))
        """
        unique = uuid.uuid4().hex
        packed = Web3.solidity_keccak(
            ["address", "string", "uint256"],
            [Web3.to_checksum_address(creator_address), unique, self.chain_id],
        )
        return packed

    # ------------------------------------------------------------------
    # Role management (admin key)
    # ------------------------------------------------------------------

    def grant_role(self, role: bytes, account_address: str) -> str:
        """Grant a blockchain role to an address. Uses admin key."""
        fn = self.role_manager.functions.grantActorRole(
            role, Web3.to_checksum_address(account_address)
        )
        return self._sign_and_send(fn, self.admin_key)

    def revoke_role(self, role: bytes, account_address: str) -> str:
        """Revoke a blockchain role from an address. Uses admin key."""
        fn = self.role_manager.functions.revokeActorRole(
            role, Web3.to_checksum_address(account_address)
        )
        return self._sign_and_send(fn, self.admin_key)

    def check_role(self, role: bytes, account_address: str) -> bool:
        """Check if an address has a specific role (read-only, no gas)."""
        return self.role_manager.functions.checkRole(
            role, Web3.to_checksum_address(account_address)
        ).call()

    # ------------------------------------------------------------------
    # Batch write functions (state transitions)
    # ------------------------------------------------------------------

    def create_batch(
        self,
        private_key: str,
        batch_id: bytes,
        apiary_hash: bytes,
        metadata_hash: bytes,
    ) -> str:
        """S0: Create a new batch. Caller must have BEEKEEPER_ROLE."""
        fn = self.registry.functions.createBatch(
            batch_id, apiary_hash, metadata_hash
        )
        return self._sign_and_send(fn, private_key)

    def record_harvest(
        self, private_key: str, batch_id: bytes, harvest_hash: bytes
    ) -> str:
        """S0→S1: Record harvest. Must be the batch creator."""
        fn = self.registry.functions.recordHarvest(batch_id, harvest_hash)
        return self._sign_and_send(fn, private_key)

    def record_processing(
        self, private_key: str, batch_id: bytes, process_hash: bytes
    ) -> str:
        """S1→S2: Record processing. BEEKEEPER or PROCESSOR."""
        fn = self.registry.functions.recordProcessing(batch_id, process_hash)
        return self._sign_and_send(fn, private_key)

    def anchor_lab_proof(self, batch_id: bytes, proof_hash: bytes) -> str:
        """S2→S3: Anchor lab proof. Uses oracle key from env."""
        fn = self.registry.functions.anchorLabProof(batch_id, proof_hash)
        return self._sign_and_send(fn, self.oracle_key)

    def record_packaging(
        self, private_key: str, batch_id: bytes, packaging_hash: bytes
    ) -> str:
        """S3→S4: Record packaging. BEEKEEPER or PROCESSOR."""
        fn = self.registry.functions.recordPackaging(batch_id, packaging_hash)
        return self._sign_and_send(fn, private_key)

    def record_distribution(
        self, private_key: str, batch_id: bytes, distribution_hash: bytes
    ) -> str:
        """S4→S5: Record distribution (terminal). DISTRIBUTOR or ADMIN."""
        fn = self.registry.functions.recordDistribution(
            batch_id, distribution_hash
        )
        return self._sign_and_send(fn, private_key)

    # ------------------------------------------------------------------
    # Batch read functions (view, no gas)
    # ------------------------------------------------------------------

    def get_batch(self, batch_id: bytes) -> dict:
        """Get full batch data from chain."""
        b = self.registry.functions.getBatch(batch_id).call()
        # The contract returns a tuple matching the Batch struct order
        return {
            "batch_id": "0x" + b[0].hex(),
            "beekeeper": b[1],
            "state": BATCH_STATES.get(b[2], "UNKNOWN"),
            "state_code": b[2],
            "lab_verified": b[3],
            "apiary_hash": "0x" + b[4].hex(),
            "metadata_hash": "0x" + b[5].hex(),
            "harvest_hash": "0x" + b[6].hex(),
            "process_hash": "0x" + b[7].hex(),
            "lab_proof_hash": "0x" + b[8].hex(),
            "packaging_hash": "0x" + b[9].hex(),
            "distribution_hash": "0x" + b[10].hex(),
            "created_at": b[11],
            "harvested_at": b[12],
            "processed_at": b[13],
            "lab_verified_at": b[14],
            "packaged_at": b[15],
            "distributed_at": b[16],
        }

    def get_batch_state(self, batch_id: bytes) -> str:
        """Get just the current state of a batch."""
        state_code = self.registry.functions.getBatchState(batch_id).call()
        return BATCH_STATES.get(state_code, "UNKNOWN")

    def get_batch_timeline(self, batch_id: bytes) -> dict:
        """Get all 6 timestamps for a batch."""
        t = self.registry.functions.getBatchTimeline(batch_id).call()
        return {
            "created_at": t[0],
            "harvested_at": t[1],
            "processed_at": t[2],
            "lab_verified_at": t[3],
            "packaged_at": t[4],
            "distributed_at": t[5],
        }

    def get_batch_hashes(self, batch_id: bytes) -> dict:
        """Get all 6 hash anchors for a batch."""
        h = self.registry.functions.getBatchHashes(batch_id).call()
        return {
            "apiary_hash": "0x" + h[0].hex(),
            "harvest_hash": "0x" + h[1].hex(),
            "process_hash": "0x" + h[2].hex(),
            "lab_proof_hash": "0x" + h[3].hex(),
            "packaging_hash": "0x" + h[4].hex(),
            "distribution_hash": "0x" + h[5].hex(),
        }

    def get_batch_count(self) -> int:
        """Get total number of registered batches."""
        return self.registry.functions.getBatchCount().call()

    def get_batch_ids_paginated(
        self, offset: int = 0, limit: int = 20
    ) -> list:
        """Get paginated list of batch IDs."""
        ids = self.registry.functions.getBatchIdsPaginated(
            offset, limit
        ).call()
        return ["0x" + bid.hex() for bid in ids]

    def is_lab_verified(self, batch_id: bytes) -> bool:
        """Check if a batch has passed lab verification."""
        return self.registry.functions.isLabVerified(batch_id).call()


# Singleton instance — initialized once, reused across requests.
# Contract addresses are read from env at import time; if empty,
# the contract objects will be None (service degrades gracefully).
blockchain_service = BlockchainService()
