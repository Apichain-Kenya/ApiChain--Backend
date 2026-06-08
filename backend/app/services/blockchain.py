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
import time
import uuid
import logging
from pathlib import Path
from typing import Callable, Optional

from web3 import Web3
from web3.exceptions import ContractLogicError, TimeExhausted

logger = logging.getLogger(__name__)


class ReceiptPendingError(Exception):
    """Raised when a transaction was successfully broadcast but its receipt
    did not arrive within the configured ceiling.

    Distinct from a generic Exception so callers in `routers/batch.py` can
    treat it as "anchor in flight" rather than "anchor failed": persist the
    tx hash, leave DB state unchanged, return HTTP 202, and let the
    `reconcile_pending_batches` scheduler job finish the job once the tx
    confirms.
    """

    def __init__(self, tx_hash: str):
        super().__init__(f"Transaction broadcast but receipt pending: {tx_hash}")
        self.tx_hash = tx_hash


# Retry tuning. Kept module-level so tests can monkeypatch a tighter cadence.
RPC_RETRY_ATTEMPTS = 3
RPC_RETRY_INITIAL_DELAY_S = 0.5
RPC_RETRY_MAX_DELAY_S = 4.0
RECEIPT_CEILING_S = 90
RECEIPT_POLL_INITIAL_S = 1.0
RECEIPT_POLL_MAX_S = 8.0

# Gas pricing (EIP-1559). Legacy fixed-`gasPrice` txs priced at `baseFee + ~0`
# tip got stranded and evicted on Sepolia when the base fee ticked up during
# the 90s receipt wait (observed: role grants + a distribute tx silently
# dropped). A type-2 tx sets a generous `maxFeePerGas` ceiling (affordability,
# not spend — you pay base+tip) plus a real priority tip so validators include
# it. Base fee can move +12.5%/block; ~8 blocks over the wait → ~2.6x worst
# case, so a 3x ceiling covers it.
GAS_MAX_FEE_MULTIPLIER = 3
GAS_PRIORITY_FEE_GWEI = 2

# Wallet funding. The maxFeePerGas ceiling raises the node's required
# submission balance (gas_limit × maxFeePerGas). At 500k gas and a ~5 gwei
# Sepolia ceiling that is ~0.0025 ETH per tx; a farmer's /simple does two txs
# (create + harvest). 0.01 ETH covers the 2-tx flow with headroom; top up
# anything below 0.005.
DEFAULT_FUND_ETH = 0.01
FUND_MIN_BALANCE_ETH = 0.005


def _is_transient(exc: BaseException) -> bool:
    """Classify whether an exception should trigger a retry.

    Deterministic reverts (`ContractLogicError`) are never retried — the
    contract said no, retrying will just say no again. Everything else
    (connection reset, 5xx from the RPC, socket timeout) is treated as
    transient.
    """
    if isinstance(exc, ContractLogicError):
        return False
    return True


def _retry_rpc(fn: Callable, *args, **kwargs):
    """Bounded exponential-backoff retry for a single RPC call.

    Not a decorator on purpose — `_sign_and_send` mixes nonce-fetch,
    build, sign, broadcast, and receipt-wait, and we only want retries
    around the truly transient hops (connection + broadcast), not the
    whole compound operation.
    """
    delay = RPC_RETRY_INITIAL_DELAY_S
    last_exc: Optional[BaseException] = None
    for attempt in range(1, RPC_RETRY_ATTEMPTS + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if not _is_transient(exc) or attempt == RPC_RETRY_ATTEMPTS:
                raise
            last_exc = exc
            logger.warning(
                f"RPC call failed (attempt {attempt}/{RPC_RETRY_ATTEMPTS}): {exc!r} — retrying in {delay}s"
            )
            time.sleep(delay)
            delay = min(delay * 2, RPC_RETRY_MAX_DELAY_S)
    # Unreachable, but keeps type-checkers happy.
    raise last_exc  # type: ignore[misc]

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
        """Bounded-retry connectivity check.

        Sprint 6: transient RPC blips (Sepolia load balancer hiccups, brief
        socket resets) used to 503 every batch endpoint at once. The retry
        absorbs the most common failure mode without masking a genuine
        outage — three attempts with exponential backoff returns False fast
        enough not to wedge the request thread.
        """
        try:
            return _retry_rpc(self.w3.is_connected)
        except Exception:
            return False

    def _wait_for_receipt(self, tx_hash, ceiling_s: int = RECEIPT_CEILING_S):
        """Poll for a transaction receipt with exponential backoff up to
        `ceiling_s` seconds.

        Sprint 4 Sepolia evidence (docs/sepolia-lifecycle-evidence.md L126)
        showed the old hardcoded 30s `wait_for_transaction_receipt` firing
        prematurely on DISTRIBUTE even though the tx confirmed seconds later.
        90s covers the Sepolia long tail; locally on Hardhat the first poll
        succeeds.

        Raises:
            ReceiptPendingError: ceiling exceeded with no receipt observed.
        """
        deadline = time.monotonic() + ceiling_s
        poll = RECEIPT_POLL_INITIAL_S
        while True:
            try:
                # Web3 raises TimeExhausted when its internal timeout hits;
                # we want to keep polling until OUR ceiling hits.
                return self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=poll)
            except TimeExhausted:
                if time.monotonic() >= deadline:
                    raise ReceiptPendingError(tx_hash.hex() if hasattr(tx_hash, "hex") else str(tx_hash))
                poll = min(poll * 2, RECEIPT_POLL_MAX_S)

    def _fee_fields(self) -> dict:
        """Build EIP-1559 fee fields with headroom for base-fee drift.

        Returns `{maxFeePerGas, maxPriorityFeePerGas}` on a post-London chain
        (Sepolia, Hardhat) so a tx survives base-fee movement across the
        receipt wait instead of being evicted. Falls back to legacy
        `{gasPrice}` on a pre-London chain that exposes no `baseFeePerGas`.

        NOTE: callers must NOT also set `gasPrice` — web3.py rejects a tx that
        mixes legacy and 1559 fee fields.
        """
        base_fee = self.w3.eth.get_block("latest").get("baseFeePerGas")
        if base_fee is None:
            return {"gasPrice": self.w3.eth.gas_price}
        priority = self.w3.to_wei(GAS_PRIORITY_FEE_GWEI, "gwei")
        max_fee = base_fee * GAS_MAX_FEE_MULTIPLIER + priority
        return {"maxFeePerGas": max_fee, "maxPriorityFeePerGas": priority}

    # ------------------------------------------------------------------
    # Account funding (for dev/testnet -- new wallets start with 0 ETH)
    # ------------------------------------------------------------------

    def fund_account(self, address: str, amount_eth: float = DEFAULT_FUND_ETH) -> Optional[str]:
        """
        Send ETH from admin wallet to a user wallet so it can pay gas.
        Only needed on Hardhat/testnet where new wallets have 0 balance.
        Default DEFAULT_FUND_ETH covers a wallet's full lifecycle under the
        EIP-1559 maxFeePerGas ceiling (including the farmer's 2-tx /simple);
        raise it if you see "insufficient funds" reverts.
        Returns tx hash or None if funding not needed or failed.
        """
        balance = self.w3.eth.get_balance(address)
        min_balance = self.w3.to_wei(FUND_MIN_BALANCE_ETH, "ether")
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
                **self._fee_fields(),
                "nonce": nonce,
                "chainId": self.chain_id,
            }
            signed = self.w3.eth.account.sign_transaction(tx, self.admin_key)
            tx_hash = _retry_rpc(self.w3.eth.send_raw_transaction, signed.raw_transaction)
            self._wait_for_receipt(tx_hash)
            logger.info(f"Funded {address} with {amount_eth} ETH (tx: {tx_hash.hex()})")
            return tx_hash.hex()
        except ReceiptPendingError as e:
            # Funding receipts are non-critical; the wallet may still be
            # usable on the next request once the tx confirms. Surface the
            # tx hash for operator visibility but don't fail enrollment.
            logger.warning(f"Funding tx pending for {address}: {e.tx_hash}")
            return e.tx_hash
        except Exception as e:
            logger.error(f"Failed to fund {address}: {e}")
            return None

    # ------------------------------------------------------------------
    # Generic transaction helper
    # ------------------------------------------------------------------

    def _sign_and_send(self, contract_fn, private_key: str) -> tuple[str, int]:
        """
        Build, sign, send a transaction and wait for receipt.

        Args:
            contract_fn: A prepared contract function call
                         (e.g., self.registry.functions.createBatch(...))
            private_key: Hex private key of the signer.

        Returns:
            (tx_hash_hex, block_timestamp_unix) — block timestamp comes from
            the mined block so callers can record chain time, not local time.

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
                **self._fee_fields(),
            }
        )

        signed = self.w3.eth.account.sign_transaction(tx, private_key)
        # Retry only the broadcast hop: nonce-fetch and build above are
        # cheap to re-run on a retry up here, but the receipt-wait below
        # is governed by its own ceiling and must not be retried (that
        # would re-broadcast the same tx and waste gas).
        tx_hash = _retry_rpc(self.w3.eth.send_raw_transaction, signed.raw_transaction)
        receipt = self._wait_for_receipt(tx_hash)

        if receipt["status"] != 1:
            raise Exception(f"Transaction reverted: {tx_hash.hex()}")

        block = self.w3.eth.get_block(receipt["blockNumber"])
        return tx_hash.hex(), int(block["timestamp"])

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
        tx_hash, _ = self._sign_and_send(fn, self.admin_key)
        return tx_hash

    def revoke_role(self, role: bytes, account_address: str) -> str:
        """Revoke a blockchain role from an address. Uses admin key."""
        fn = self.role_manager.functions.revokeActorRole(
            role, Web3.to_checksum_address(account_address)
        )
        tx_hash, _ = self._sign_and_send(fn, self.admin_key)
        return tx_hash

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
    ) -> tuple[str, int]:
        """S0: Create a new batch. Caller must have BEEKEEPER_ROLE.

        Returns (tx_hash, block_timestamp).
        """
        fn = self.registry.functions.createBatch(
            batch_id, apiary_hash, metadata_hash
        )
        return self._sign_and_send(fn, private_key)

    def record_harvest(
        self, private_key: str, batch_id: bytes, harvest_hash: bytes
    ) -> tuple[str, int]:
        """S0→S1: Record harvest. Must be the batch creator.

        Returns (tx_hash, block_timestamp).
        """
        fn = self.registry.functions.recordHarvest(batch_id, harvest_hash)
        return self._sign_and_send(fn, private_key)

    def record_processing(
        self, private_key: str, batch_id: bytes, process_hash: bytes
    ) -> tuple[str, int]:
        """S1→S2: Record processing. BEEKEEPER or PROCESSOR.

        Returns (tx_hash, block_timestamp).
        """
        fn = self.registry.functions.recordProcessing(batch_id, process_hash)
        return self._sign_and_send(fn, private_key)

    def anchor_lab_proof(
        self, batch_id: bytes, proof_hash: bytes
    ) -> tuple[str, int]:
        """S2→S3: Anchor lab proof.

        Signs with the system oracle key (`ORACLE_PRIVATE_KEY`), NOT a per-user
        wallet. ORACLE_ROLE is a single trusted EOA assigned to the backend,
        not a user identity — multiple lab_test_officer users share this
        signer. Do not change this to per-user signing without first granting
        ORACLE_ROLE to each lab tester's wallet on-chain.

        Returns (tx_hash, block_timestamp).
        """
        if not self.oracle_key:
            raise ValueError(
                "Oracle private key is not configured; set ORACLE_PRIVATE_KEY "
                "to anchor lab proofs."
            )
        fn = self.registry.functions.anchorLabProof(batch_id, proof_hash)
        return self._sign_and_send(fn, self.oracle_key)

    def record_packaging(
        self, private_key: str, batch_id: bytes, packaging_hash: bytes
    ) -> tuple[str, int]:
        """S3→S4: Record packaging. BEEKEEPER or PROCESSOR.

        Returns (tx_hash, block_timestamp).
        """
        fn = self.registry.functions.recordPackaging(batch_id, packaging_hash)
        return self._sign_and_send(fn, private_key)

    def record_distribution(
        self, private_key: str, batch_id: bytes, distribution_hash: bytes
    ) -> tuple[str, int]:
        """S4→S5: Record distribution (terminal). DISTRIBUTOR or ADMIN.

        Returns (tx_hash, block_timestamp).
        """
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
