"""
Batch lifecycle endpoints for honey traceability.

Each endpoint uses per-user wallet signing via _get_user_signing_key().
Role-based access control is enforced at the API level via require_role()
and on-chain by the smart contract's role checks.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from web3.exceptions import ContractLogicError

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models.batch import HoneyBatch
from app.schemas.batch import (
    BatchCreateRequest,
    BatchResponse,
    BatchTransitionResponse,
    BatchHashesResponse,
    BatchTimelineResponse,
    BatchVerifyResponse,
    DistributionRequest,
    HarvestRequest,
    LabVerifyRequest,
    PackagingRequest,
    ProcessingRequest,
)
from app.models.eth_wallet import EthWallet
from app.services.blockchain import blockchain_service
from app.services.encryption import decrypt_private_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/batches", tags=["Batches"])


def _get_user_signing_key(db: Session, user_id: int, user_role: str) -> str:
    """
    Look up the user's encrypted private key and decrypt it.

    Hard-fails (HTTP 500) if no `EthWallet` row exists. Every role that can
    reach a write endpoint is in `ROLES_NEEDING_WALLET` and must have a
    wallet provisioned at enrollment. If you encounter this error in
    practice, run `scripts/backfill_wallets.py` to repair legacy users.
    """
    wallet = db.query(EthWallet).filter(
        EthWallet.user_id == user_id,
        EthWallet.user_role == user_role,
    ).first()
    if not wallet:
        raise HTTPException(
            status_code=500,
            detail=(
                f"User {user_id} ({user_role}) has no wallet — re-enrollment "
                f"required. Run scripts/backfill_wallets.py to repair."
            ),
        )
    try:
        key = decrypt_private_key(wallet.encrypted_key)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Failed to decrypt wallet private key for user_id=%s role=%s wallet=%s",
            user_id,
            user_role,
            wallet.wallet_address,
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "User wallet is temporarily unavailable due to a server-side "
                "encryption configuration or wallet data issue. Verify "
                "WALLET_ENCRYPTION_KEY and stored wallet data."
            ),
        ) from exc
    # Ensure wallet has gas (admin funds it if needed on dev/testnet)
    blockchain_service.fund_account(wallet.wallet_address)
    return key


def _check_blockchain():
    """Raise 503 if blockchain node is unavailable."""
    if not blockchain_service.is_connected:
        raise HTTPException(
            status_code=503, detail="Blockchain node unavailable"
        )
    if blockchain_service.registry is None:
        raise HTTPException(
            status_code=503,
            detail="Contract addresses not configured. Set REGISTRY_ADDRESS and ROLE_MANAGER_ADDRESS in .env",
        )


def _batch_id_to_bytes(batch_id: str) -> bytes:
    """Decode a batch_id hex string (with or without 0x prefix) into 32-byte form."""
    hex_part = batch_id[2:] if batch_id.startswith("0x") else batch_id
    return bytes.fromhex(hex_part)


def _commit_or_orphan(db: Session, batch_id: str, tx_hash: str) -> None:
    """
    Commit the DB session, but surface an actionable error if commit fails
    AFTER the on-chain tx has already succeeded.

    The on-chain write is durable; the DB row is not. If commit fails the
    batch is "orphaned" — visible via /verify but missing from local list/
    detail endpoints. The remediation is `scripts/reconcile_batches.py`.
    """
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "DB commit failed AFTER on-chain tx %s for batch %s; batch is orphaned in DB",
            tx_hash,
            batch_id,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "db_commit_failed_after_chain_success",
                "batch_id": batch_id,
                "tx_hash": tx_hash,
                "remediation": "Run scripts/reconcile_batches.py to repair local row from chain state.",
            },
        )


# ------------------------------------------------------------------
# Create batch (S0)
# ------------------------------------------------------------------

@router.post("/", response_model=BatchTransitionResponse)
def create_batch(
    data: BatchCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["farmer"])),
):
    """Create a new honey batch on-chain. Farmer only."""
    _check_blockchain()

    signer_key = _get_user_signing_key(db, current_user["user_id"], current_user["role"])
    signer_address = blockchain_service.w3.eth.account.from_key(signer_key).address

    # Generate unique batch ID
    batch_id_bytes = blockchain_service.generate_batch_id(signer_address)

    # Compute hashes of off-chain data
    apiary_hash = blockchain_service.compute_data_hash(data.apiary_data)
    metadata_hash = blockchain_service.compute_data_hash(data.metadata)

    try:
        tx_hash, block_ts = blockchain_service.create_batch(
            signer_key, batch_id_bytes, apiary_hash, metadata_hash
        )
    except ContractLogicError as e:
        raise HTTPException(status_code=400, detail=f"Contract error: {e}")
    except Exception as e:
        logger.error(f"Blockchain error in create_batch: {e}")
        raise HTTPException(status_code=502, detail="Blockchain transaction failed")

    # Save off-chain data to database
    batch = HoneyBatch(
        blockchain_batch_id="0x" + batch_id_bytes.hex(),
        farmer_id=current_user["user_id"],
        apiary_data=data.apiary_data,
        metadata_payload=data.metadata,
        current_state="CREATED",
        create_tx_hash=tx_hash,
        created_at=datetime.fromtimestamp(block_ts, tz=timezone.utc),
    )
    db.add(batch)
    _commit_or_orphan(db, "0x" + batch_id_bytes.hex(), tx_hash)

    return BatchTransitionResponse(
        batch_id="0x" + batch_id_bytes.hex(),
        tx_hash=tx_hash,
        new_state="CREATED",
        message="Batch created on-chain",
    )


# ------------------------------------------------------------------
# Record harvest (S0 → S1)
# ------------------------------------------------------------------

@router.post("/{batch_id}/harvest", response_model=BatchTransitionResponse)
def record_harvest(
    batch_id: str,
    data: HarvestRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["farmer"])),
):
    """Record harvest data. Must be the batch creator."""
    _check_blockchain()

    batch = db.query(HoneyBatch).filter(
        HoneyBatch.blockchain_batch_id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.current_state != "CREATED":
        raise HTTPException(status_code=400, detail=f"Batch is in state {batch.current_state}, expected CREATED")

    # mode="json" serializes datetime → ISO string so the payload is both
    # JSON-storable on the DB column and deterministically hashable.
    harvest_payload = data.model_dump(mode="json")
    harvest_hash = blockchain_service.compute_data_hash(harvest_payload)
    batch_id_bytes = _batch_id_to_bytes(batch_id)

    try:
        tx_hash, block_ts = blockchain_service.record_harvest(
            _get_user_signing_key(db, current_user["user_id"], current_user["role"]), batch_id_bytes, harvest_hash
        )
    except ContractLogicError as e:
        raise HTTPException(status_code=400, detail=f"Contract error: {e}")
    except Exception as e:
        logger.error(f"Blockchain error in record_harvest: {e}")
        raise HTTPException(status_code=502, detail="Blockchain transaction failed")

    batch.harvest_data = harvest_payload
    batch.current_state = "HARVESTED"
    batch.harvest_tx_hash = tx_hash
    batch.harvested_at = datetime.fromtimestamp(block_ts, tz=timezone.utc)
    _commit_or_orphan(db, batch_id, tx_hash)

    return BatchTransitionResponse(
        batch_id=batch_id,
        tx_hash=tx_hash,
        new_state="HARVESTED",
        message="Harvest recorded on-chain",
    )


# ------------------------------------------------------------------
# Record processing (S1 → S2)
# ------------------------------------------------------------------

@router.post("/{batch_id}/process", response_model=BatchTransitionResponse)
def record_processing(
    batch_id: str,
    data: ProcessingRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["farmer", "harvest_processor"])),
):
    """Record processing data. Farmer or harvest processor."""
    _check_blockchain()

    batch = db.query(HoneyBatch).filter(
        HoneyBatch.blockchain_batch_id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.current_state != "HARVESTED":
        raise HTTPException(status_code=400, detail=f"Batch is in state {batch.current_state}, expected HARVESTED")

    process_payload = data.model_dump()
    process_hash = blockchain_service.compute_data_hash(process_payload)
    batch_id_bytes = _batch_id_to_bytes(batch_id)

    try:
        tx_hash, block_ts = blockchain_service.record_processing(
            _get_user_signing_key(db, current_user["user_id"], current_user["role"]), batch_id_bytes, process_hash
        )
    except ContractLogicError as e:
        raise HTTPException(status_code=400, detail=f"Contract error: {e}")
    except Exception as e:
        logger.error(f"Blockchain error in record_processing: {e}")
        raise HTTPException(status_code=502, detail="Blockchain transaction failed")

    batch.process_data = process_payload
    batch.current_state = "PROCESSED"
    batch.process_tx_hash = tx_hash
    batch.processed_at = datetime.fromtimestamp(block_ts, tz=timezone.utc)
    _commit_or_orphan(db, batch_id, tx_hash)

    return BatchTransitionResponse(
        batch_id=batch_id,
        tx_hash=tx_hash,
        new_state="PROCESSED",
        message="Processing recorded on-chain",
    )


# ------------------------------------------------------------------
# Anchor lab proof (S2 → S3) — Oracle only
# ------------------------------------------------------------------

@router.post("/{batch_id}/lab-verify", response_model=BatchTransitionResponse)
def anchor_lab_proof(
    batch_id: str,
    data: LabVerifyRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["lab_test_officer", "admin", "super_admin"])),
):
    """Anchor lab verification proof.

    Signs with the system oracle key, deliberately bypassing
    `_get_user_signing_key()` — ORACLE_ROLE is one trusted EOA, not a user
    identity. See `blockchain_service.anchor_lab_proof` for details.
    """
    _check_blockchain()

    batch = db.query(HoneyBatch).filter(
        HoneyBatch.blockchain_batch_id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.current_state != "PROCESSED":
        raise HTTPException(status_code=400, detail=f"Batch is in state {batch.current_state}, expected PROCESSED")

    proof_payload = data.model_dump()
    proof_hash = blockchain_service.compute_data_hash(proof_payload)
    batch_id_bytes = _batch_id_to_bytes(batch_id)

    try:
        tx_hash, block_ts = blockchain_service.anchor_lab_proof(batch_id_bytes, proof_hash)
    except ContractLogicError as e:
        raise HTTPException(status_code=400, detail=f"Contract error: {e}")
    except Exception as e:
        logger.error(f"Blockchain error in anchor_lab_proof: {e}")
        raise HTTPException(status_code=502, detail="Blockchain transaction failed")

    batch.lab_proof_data = proof_payload
    batch.current_state = "LAB_VERIFIED"
    batch.lab_verify_tx_hash = tx_hash
    batch.lab_verified_at = datetime.fromtimestamp(block_ts, tz=timezone.utc)
    _commit_or_orphan(db, batch_id, tx_hash)

    return BatchTransitionResponse(
        batch_id=batch_id,
        tx_hash=tx_hash,
        new_state="LAB_VERIFIED",
        message="Lab proof anchored on-chain by oracle",
    )


# ------------------------------------------------------------------
# Record packaging (S3 → S4)
# ------------------------------------------------------------------

@router.post("/{batch_id}/package", response_model=BatchTransitionResponse)
def record_packaging(
    batch_id: str,
    data: PackagingRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["farmer", "harvest_processor", "packager"])),
):
    """Record packaging data. Farmer, harvest processor, or packager."""
    _check_blockchain()

    batch = db.query(HoneyBatch).filter(
        HoneyBatch.blockchain_batch_id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.current_state != "LAB_VERIFIED":
        raise HTTPException(status_code=400, detail=f"Batch is in state {batch.current_state}, expected LAB_VERIFIED")

    packaging_payload = data.model_dump()
    packaging_hash = blockchain_service.compute_data_hash(packaging_payload)
    batch_id_bytes = _batch_id_to_bytes(batch_id)

    try:
        tx_hash, block_ts = blockchain_service.record_packaging(
            _get_user_signing_key(db, current_user["user_id"], current_user["role"]), batch_id_bytes, packaging_hash
        )
    except ContractLogicError as e:
        raise HTTPException(status_code=400, detail=f"Contract error: {e}")
    except Exception as e:
        logger.error(f"Blockchain error in record_packaging: {e}")
        raise HTTPException(status_code=502, detail="Blockchain transaction failed")

    batch.packaging_data = packaging_payload
    batch.current_state = "PACKAGED"
    batch.packaging_tx_hash = tx_hash
    batch.packaged_at = datetime.fromtimestamp(block_ts, tz=timezone.utc)
    _commit_or_orphan(db, batch_id, tx_hash)

    return BatchTransitionResponse(
        batch_id=batch_id,
        tx_hash=tx_hash,
        new_state="PACKAGED",
        message="Packaging recorded on-chain",
    )


# ------------------------------------------------------------------
# Record distribution (S4 → S5, terminal)
# ------------------------------------------------------------------

@router.post("/{batch_id}/distribute", response_model=BatchTransitionResponse)
def record_distribution(
    batch_id: str,
    data: DistributionRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["distributor", "admin", "super_admin"])),
):
    """Record distribution (terminal state). Distributor or admin."""
    _check_blockchain()

    batch = db.query(HoneyBatch).filter(
        HoneyBatch.blockchain_batch_id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.current_state != "PACKAGED":
        raise HTTPException(status_code=400, detail=f"Batch is in state {batch.current_state}, expected PACKAGED")

    dist_payload = data.model_dump()
    dist_hash = blockchain_service.compute_data_hash(dist_payload)
    batch_id_bytes = _batch_id_to_bytes(batch_id)

    try:
        tx_hash, block_ts = blockchain_service.record_distribution(
            _get_user_signing_key(db, current_user["user_id"], current_user["role"]), batch_id_bytes, dist_hash
        )
    except ContractLogicError as e:
        raise HTTPException(status_code=400, detail=f"Contract error: {e}")
    except Exception as e:
        logger.error(f"Blockchain error in record_distribution: {e}")
        raise HTTPException(status_code=502, detail="Blockchain transaction failed")

    batch.distribution_data = dist_payload
    batch.current_state = "DISTRIBUTED"
    batch.distribution_tx_hash = tx_hash
    batch.distributed_at = datetime.fromtimestamp(block_ts, tz=timezone.utc)
    _commit_or_orphan(db, batch_id, tx_hash)

    return BatchTransitionResponse(
        batch_id=batch_id,
        tx_hash=tx_hash,
        new_state="DISTRIBUTED",
        message="Distribution recorded on-chain (terminal state)",
    )


# ------------------------------------------------------------------
# Read endpoints
# ------------------------------------------------------------------

@router.get("/", response_model=list[BatchResponse])
def list_batches(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List batches from the database (paginated)."""
    batches = (
        db.query(HoneyBatch)
        .order_by(HoneyBatch.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return batches


@router.get("/{batch_id}", response_model=BatchResponse)
def get_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get batch details from the database."""
    batch = db.query(HoneyBatch).filter(
        HoneyBatch.blockchain_batch_id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@router.get("/{batch_id}/timeline", response_model=BatchTimelineResponse)
def get_batch_timeline(batch_id: str):
    """Get batch timeline directly from blockchain (no auth required)."""
    _check_blockchain()

    batch_id_bytes = _batch_id_to_bytes(batch_id)

    try:
        timeline = blockchain_service.get_batch_timeline(batch_id_bytes)
    except ContractLogicError as e:
        raise HTTPException(status_code=404, detail=f"Batch not found on chain: {e}")

    return BatchTimelineResponse(batch_id=batch_id, **timeline)


@router.get("/{batch_id}/hashes", response_model=BatchHashesResponse)
def get_batch_hashes(batch_id: str):
    """Get all hash anchors directly from blockchain (no auth required)."""
    _check_blockchain()

    batch_id_bytes = _batch_id_to_bytes(batch_id)

    try:
        hashes = blockchain_service.get_batch_hashes(batch_id_bytes)
    except ContractLogicError as e:
        raise HTTPException(status_code=404, detail=f"Batch not found on chain: {e}")

    return BatchHashesResponse(batch_id=batch_id, **hashes)


@router.get("/{batch_id}/verify", response_model=BatchVerifyResponse)
def verify_batch(batch_id: str):
    """
    Public batch verification endpoint (for QR scan).
    No authentication required. Reads directly from blockchain.
    """
    _check_blockchain()

    batch_id_bytes = _batch_id_to_bytes(batch_id)

    try:
        batch_data = blockchain_service.get_batch(batch_id_bytes)
        timeline = blockchain_service.get_batch_timeline(batch_id_bytes)
        hashes = blockchain_service.get_batch_hashes(batch_id_bytes)
    except ContractLogicError as e:
        raise HTTPException(status_code=404, detail=f"Batch not found on chain: {e}")

    return BatchVerifyResponse(
        batch_id=batch_id,
        state=batch_data["state"],
        beekeeper=batch_data["beekeeper"],
        lab_verified=batch_data["lab_verified"],
        timeline=BatchTimelineResponse(batch_id=batch_id, **timeline),
        hashes=BatchHashesResponse(batch_id=batch_id, **hashes),
    )
