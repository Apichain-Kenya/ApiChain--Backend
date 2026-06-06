"""
Batch lifecycle endpoints for honey traceability.

Each endpoint uses per-user wallet signing via _get_user_signing_key().
Role-based access control is enforced at the API level via require_role()
and on-chain by the smart contract's role checks.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from web3.exceptions import ContractLogicError

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models.batch import HoneyBatch
from app.models.batch_metadata import BatchMetadata
from app.models.environmental_data import EnvironmentalData
from app.models.apiary import ApiaryLocation
from app.models.apiary_record import ApiaryRecord
from app.models.lab_result import LabResult
from app.models.harvest_record import HarvestRecord
from app.models.process_record import ProcessRecord
from app.models.packaging_record import PackagingRecord
from app.models.distribution_record import DistributionRecord
from app.schemas.batch import (
    ApiaryRecordPublic,
    AuthenticityPublic,
    BatchAuthenticitySummary,
    BatchCreateRequest,
    BatchMetadataInput,
    BatchMetadataPublic,
    BatchResponse,
    BatchTransitionResponse,
    BatchHashesResponse,
    BatchTimelineResponse,
    BatchVerifyResponse,
    DistributionRecordPublic,
    DistributionRequest,
    EnvironmentalDataPublic,
    HarvestRecordPublic,
    HarvestRequest,
    LabResultPublic,
    LabVerifyRequest,
    PackagingRecordPublic,
    PackagingRequest,
    ProcessRecordPublic,
    ProcessingRequest,
    SimpleBatchCreateRequest,
    StageHashVerification,
    TxHashes,
    VerificationBlock,
)
from app.models.eth_wallet import EthWallet
from app.services.blockchain import blockchain_service, ReceiptPendingError
from app.services.encryption import decrypt_private_key
from app.services.environment import fetch_environment_snapshot

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


def _pending_response(batch_id: str, tx_hash: str, stage: str) -> JSONResponse:
    """Sprint 6 — the tx was broadcast but its receipt didn't arrive within
    the 90 s ceiling. The DB row carries the tx hash; the reconciler job
    will mirror chain state back in once the tx confirms.

    Returns 202 Accepted, not 200, so the frontend can distinguish "anchor
    in flight" from "anchor complete" and poll `/verify` for the eventual
    state flip.
    """
    return JSONResponse(
        status_code=202,
        content={
            "batch_id": batch_id,
            "tx_hash": tx_hash,
            "stage": stage,
            "status": "pending_confirmation",
            "message": (
                "Transaction broadcast but receipt not yet observed. "
                "Reconciler will mirror chain state once the tx confirms."
            ),
        },
    )


# ------------------------------------------------------------------
# Create batch (S0)
# ------------------------------------------------------------------

def _persist_typed_metadata(
    db: Session, batch_id: int, payload: BatchMetadataInput
) -> BatchMetadata:
    """Insert a `batch_metadata` row from the typed Pydantic payload, flush
    and refresh so the canonical hash uses the post-roundtrip values.

    The caller commits (or rolls back) — this helper only stages the row.
    """
    row = BatchMetadata(
        batch_id=batch_id,
        honey_type=payload.honey_type.value,
        expected_yield_kg=payload.expected_yield_kg,
        harvest_window_start=payload.harvest_window_start,
        harvest_window_end=payload.harvest_window_end,
        apiary_management_method=payload.apiary_management_method.value,
        notes=payload.notes,
    )
    db.add(row)
    db.flush()
    db.refresh(row)
    return row


@router.post("/", response_model=BatchTransitionResponse)
def create_batch(
    data: BatchCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["farmer"])),
):
    """Create a new honey batch on-chain (S0). Farmer only.

    Sprint 6: `apiary_data` replaced by `apiary_id`; apiary fields snapshotted
    into `apiary_records` for three-way `/verify` comparison.

    Sprint 9: `metadata` is strictly typed (`BatchMetadataInput`). The
    canonical payload of the persisted `batch_metadata` row is what's
    hashed on chain, so `/verify.metadata.match` is recomputable from the
    row alone.
    """
    _check_blockchain()

    farmer_id = current_user["user_id"]

    apiary = db.query(ApiaryLocation).filter(
        ApiaryLocation.id == data.apiary_id
    ).first()
    if not apiary:
        raise HTTPException(status_code=404, detail="Apiary not found")
    if apiary.farmer_id != farmer_id:
        raise HTTPException(status_code=403, detail="Apiary does not belong to this farmer")

    signer_key = _get_user_signing_key(db, farmer_id, current_user["role"])
    signer_address = blockchain_service.w3.eth.account.from_key(signer_key).address

    batch_id_bytes = blockchain_service.generate_batch_id(signer_address)
    batch_id_hex = "0x" + batch_id_bytes.hex()

    batch = HoneyBatch(
        blockchain_batch_id=batch_id_hex,
        farmer_id=farmer_id,
        apiary_id=apiary.id,
        current_state="CREATED",
    )
    db.add(batch)
    db.flush()

    apiary_row = ApiaryRecord(
        batch_id=batch.id,
        apiary_id=apiary.id,
        latitude=apiary.latitude,
        longitude=apiary.longitude,
        altitude=apiary.altitude,
        vegetation_type=apiary.vegetation_type,
        hive_count=apiary.hive_count,
    )
    db.add(apiary_row)
    db.flush()
    db.refresh(apiary_row)

    apiary_payload = _apiary_record_canonical_payload(apiary_row)
    apiary_hash = blockchain_service.compute_data_hash(apiary_payload)

    metadata_row = _persist_typed_metadata(db, batch.id, data.metadata)
    metadata_payload = _metadata_record_canonical_payload(metadata_row)
    metadata_hash = blockchain_service.compute_data_hash(metadata_payload)

    try:
        tx_hash, block_ts = blockchain_service.create_batch(
            signer_key, batch_id_bytes, apiary_hash, metadata_hash
        )
    except ContractLogicError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Contract error: {e}")
    except ReceiptPendingError as e:
        apiary_row.apiary_proof_hash = "0x" + apiary_hash.hex()
        metadata_row.metadata_proof_hash = "0x" + metadata_hash.hex()
        batch.create_tx_hash = e.tx_hash
        _commit_or_orphan(db, batch_id_hex, e.tx_hash)
        return _pending_response(batch_id_hex, e.tx_hash, "create")
    except Exception as e:
        db.rollback()
        logger.error(f"Blockchain error in create_batch: {e}")
        raise HTTPException(status_code=502, detail="Blockchain transaction failed")

    apiary_row.apiary_proof_hash = "0x" + apiary_hash.hex()
    metadata_row.metadata_proof_hash = "0x" + metadata_hash.hex()
    batch.create_tx_hash = tx_hash
    batch.created_at = datetime.fromtimestamp(block_ts, tz=timezone.utc)
    _commit_or_orphan(db, batch_id_hex, tx_hash)

    return BatchTransitionResponse(
        batch_id=batch_id_hex,
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

    if db.query(HarvestRecord).filter(HarvestRecord.batch_id == batch.id).first():
        raise HTTPException(status_code=409, detail="Harvest record already exists for this batch")

    row = HarvestRecord(
        batch_id=batch.id,
        harvest_date=data.harvest_date,
        quantity_kg=data.quantity_kg,
        hive_ids=data.hive_ids,
        gps_lat=data.gps_lat,
        gps_lon=data.gps_lon,
        notes=data.notes,
    )
    db.add(row)
    db.flush()
    # Re-read so the anchor-time hash matches the verify-time hash: the
    # `harvest_date` column is TIMESTAMP WITHOUT TIME ZONE, so a tz-aware
    # Pydantic datetime round-trips to a naive datetime in the session
    # timezone. Hashing the post-roundtrip value guarantees determinism.
    db.refresh(row)

    harvest_payload = _harvest_record_canonical_payload(row)
    harvest_hash = blockchain_service.compute_data_hash(harvest_payload)
    batch_id_bytes = _batch_id_to_bytes(batch_id)

    try:
        tx_hash, block_ts = blockchain_service.record_harvest(
            _get_user_signing_key(db, current_user["user_id"], current_user["role"]), batch_id_bytes, harvest_hash
        )
    except ContractLogicError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Contract error: {e}")
    except ReceiptPendingError as e:
        row.harvest_proof_hash = "0x" + harvest_hash.hex()
        batch.harvest_tx_hash = e.tx_hash
        _commit_or_orphan(db, batch_id, e.tx_hash)
        return _pending_response(batch_id, e.tx_hash, "harvest")
    except Exception as e:
        db.rollback()
        logger.error(f"Blockchain error in record_harvest: {e}")
        raise HTTPException(status_code=502, detail="Blockchain transaction failed")

    row.harvest_proof_hash = "0x" + harvest_hash.hex()
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

    if db.query(ProcessRecord).filter(ProcessRecord.batch_id == batch.id).first():
        raise HTTPException(status_code=409, detail="Process record already exists for this batch")

    row = ProcessRecord(
        batch_id=batch.id,
        extraction_method=data.extraction_method,
        moisture_content=data.moisture_content,
        handling_notes=data.handling_notes,
    )
    db.add(row)
    db.flush()

    process_payload = _process_record_canonical_payload(row)
    process_hash = blockchain_service.compute_data_hash(process_payload)
    batch_id_bytes = _batch_id_to_bytes(batch_id)

    try:
        tx_hash, block_ts = blockchain_service.record_processing(
            _get_user_signing_key(db, current_user["user_id"], current_user["role"]), batch_id_bytes, process_hash
        )
    except ContractLogicError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Contract error: {e}")
    except ReceiptPendingError as e:
        row.process_proof_hash = "0x" + process_hash.hex()
        batch.process_tx_hash = e.tx_hash
        _commit_or_orphan(db, batch_id, e.tx_hash)
        return _pending_response(batch_id, e.tx_hash, "process")
    except Exception as e:
        db.rollback()
        logger.error(f"Blockchain error in record_processing: {e}")
        raise HTTPException(status_code=502, detail="Blockchain transaction failed")

    row.process_proof_hash = "0x" + process_hash.hex()
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

def _lab_result_canonical_payload(row: LabResult) -> dict:
    """Build the deterministic pre-image dict used for `proofHash`.

    The persisted row is the single source of truth — re-running this on the
    DB row at QR-verification time must reproduce the exact bytes that were
    hashed at lab-verify time. Only stable, oracle-anchored columns are
    included; `id`, `tested_at`, and `lab_proof_hash` are excluded (the first
    two are DB-assigned post-hash; the third IS the hash).
    """
    return {
        "batch_id": row.batch_id,
        "moisture_content": row.moisture_content,
        "sucrose_level": row.sucrose_level,
        "hmf_level": row.hmf_level,
        "pollen_density": row.pollen_density,
        "purity_score": row.purity_score,
        "passed_quality_check": row.passed_quality_check,
        "laboratory_name": row.laboratory_name,
        "analyst_name": row.analyst_name,
        "certificate_number": row.certificate_number,
        "notes": row.notes,
    }


def _canonical_dt(dt) -> str | None:
    """Serialize a datetime to a tz-stable ISO-8601 string.

    The DB columns are `TIMESTAMP WITHOUT TIME ZONE`, so a tz-aware datetime
    passed in by Pydantic round-trips to a naive datetime. To keep the anchor
    hash and the verify hash identical, normalize both sides to UTC-naive
    ISO-8601 here before hashing.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat()


def _apiary_record_canonical_payload(row: ApiaryRecord) -> dict:
    """Pre-image dict for `apiaryHash` anchored at S0.

    Sprint 6 — snapshot fields live on `apiary_records`, not
    `apiary_locations`, so later edits to the underlying apiary do not
    invalidate the anchored hash.
    """
    return {
        "batch_id": row.batch_id,
        "apiary_id": row.apiary_id,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "altitude": row.altitude,
        "vegetation_type": row.vegetation_type,
        "hive_count": row.hive_count,
    }


def _metadata_record_canonical_payload(row: BatchMetadata) -> dict:
    """Pre-image dict for `metadataHash` anchored at S0 (Sprint 8).

    `notes` is intentionally excluded so farmers can amend non-material
    notes without invalidating chain-anchored history. Numeric values are
    rendered as fixed-precision strings ("50.00", not 50 or 50.0) to dodge
    float round-trip drift; dates as plain `YYYY-MM-DD`; enums lowercased;
    `recorded_at` routed through `_canonical_dt()` to dodge the
    TIMESTAMP-without-timezone round-trip bug.
    """
    yield_str: str | None = None
    if row.expected_yield_kg is not None:
        # str() handles both Decimal and float cleanly; quantize fixes the precision.
        yield_str = str(Decimal(str(row.expected_yield_kg)).quantize(Decimal("0.01")))
    return {
        "batch_id": row.batch_id,
        "honey_type": (row.honey_type or "").lower(),
        "expected_yield_kg": yield_str,
        "harvest_window_start": (
            row.harvest_window_start.isoformat() if row.harvest_window_start else None
        ),
        "harvest_window_end": (
            row.harvest_window_end.isoformat() if row.harvest_window_end else None
        ),
        "apiary_management_method": (row.apiary_management_method or "").lower(),
        "recorded_at": _canonical_dt(row.recorded_at),
    }


def _harvest_record_canonical_payload(row: HarvestRecord) -> dict:
    """Pre-image dict for `harvestHash` anchored at S1."""
    return {
        "batch_id": row.batch_id,
        "harvest_date": _canonical_dt(row.harvest_date),
        "quantity_kg": row.quantity_kg,
        "hive_ids": list(row.hive_ids) if row.hive_ids else [],
        "gps_lat": row.gps_lat,
        "gps_lon": row.gps_lon,
        "notes": row.notes,
    }


def _process_record_canonical_payload(row: ProcessRecord) -> dict:
    """Pre-image dict for `processHash` anchored at S2."""
    return {
        "batch_id": row.batch_id,
        "extraction_method": row.extraction_method,
        "moisture_content": row.moisture_content,
        "handling_notes": row.handling_notes,
    }


def _packaging_record_canonical_payload(row: PackagingRecord) -> dict:
    """Pre-image dict for `packagingHash` anchored at S4."""
    return {
        "batch_id": row.batch_id,
        "unit_count": row.unit_count,
        "jar_ids": list(row.jar_ids) if row.jar_ids else [],
        "qr_codes": list(row.qr_codes) if row.qr_codes else [],
        "notes": row.notes,
    }


def _distribution_record_canonical_payload(row: DistributionRecord) -> dict:
    """Pre-image dict for `distributionHash` anchored at S5 (terminal)."""
    return {
        "batch_id": row.batch_id,
        "retailer_name": row.retailer_name,
        "transport_reference": row.transport_reference,
        "handover_notes": row.handover_notes,
    }


_ZERO_HASH = "0x" + ("00" * 32)


def _verify_stage_hash(payload: dict, db_hash_hex: str, chain_hash_hex: str) -> dict:
    """Generic three-way comparison: recomputes keccak256 of `payload` and
    compares against the DB-stored hash and the chain-anchored hash.

    `match` is True only when all three agree AND the chain hash is non-zero
    (zero chain hash means the stage was never anchored)."""
    recomputed = "0x" + blockchain_service.compute_data_hash(payload).hex()
    db = (db_hash_hex or "").lower()
    chain = (chain_hash_hex or "").lower()
    return {
        "db_hash": db,
        "chain_hash": chain,
        "recomputed_hash": recomputed.lower(),
        "match": recomputed.lower() == db == chain and chain != _ZERO_HASH,
    }


def _verify_lab_hash(row: LabResult, chain_hash_hex: str) -> dict:
    """Three-way comparison for the S3 lab proof. Thin wrapper around
    `_verify_stage_hash` kept for backward-compat with Sprint 4 imports
    (tests, other modules)."""
    return _verify_stage_hash(
        _lab_result_canonical_payload(row),
        row.lab_proof_hash,
        chain_hash_hex,
    )


def _verify_apiary_hash(row: ApiaryRecord, chain_hash_hex: str) -> dict:
    return _verify_stage_hash(
        _apiary_record_canonical_payload(row),
        row.apiary_proof_hash,
        chain_hash_hex,
    )


def _verify_metadata_hash(row: BatchMetadata, chain_hash_hex: str) -> dict:
    return _verify_stage_hash(
        _metadata_record_canonical_payload(row),
        row.metadata_proof_hash,
        chain_hash_hex,
    )


def _verify_harvest_hash(row: HarvestRecord, chain_hash_hex: str) -> dict:
    return _verify_stage_hash(
        _harvest_record_canonical_payload(row),
        row.harvest_proof_hash,
        chain_hash_hex,
    )


def _verify_process_hash(row: ProcessRecord, chain_hash_hex: str) -> dict:
    return _verify_stage_hash(
        _process_record_canonical_payload(row),
        row.process_proof_hash,
        chain_hash_hex,
    )


def _verify_packaging_hash(row: PackagingRecord, chain_hash_hex: str) -> dict:
    return _verify_stage_hash(
        _packaging_record_canonical_payload(row),
        row.packaging_proof_hash,
        chain_hash_hex,
    )


def _verify_distribution_hash(row: DistributionRecord, chain_hash_hex: str) -> dict:
    return _verify_stage_hash(
        _distribution_record_canonical_payload(row),
        row.distribution_proof_hash,
        chain_hash_hex,
    )


@router.post("/{batch_id}/lab-verify", response_model=BatchTransitionResponse)
def anchor_lab_proof(
    batch_id: str,
    data: LabVerifyRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["lab_test_officer", "admin", "super_admin"])),
):
    """Anchor lab verification proof (S2→S3).

    Signs with the system oracle key, deliberately bypassing
    `_get_user_signing_key()` — ORACLE_ROLE is one trusted EOA, not a user
    identity. See `blockchain_service.anchor_lab_proof` for details.

    Flow: validate state → INSERT lab_results row (flushed but uncommitted) →
    hash the persisted row → anchor on chain → store hash on row + tx on
    batch → commit. If the chain call fails, the inserted row is rolled back
    so no unanchored lab result is persisted.
    """
    _check_blockchain()

    batch = db.query(HoneyBatch).filter(
        HoneyBatch.blockchain_batch_id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.current_state != "PROCESSED":
        raise HTTPException(status_code=400, detail=f"Batch is in state {batch.current_state}, expected PROCESSED")

    existing = db.query(LabResult).filter(LabResult.batch_id == batch.id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Lab result already exists for this batch")

    # Insert + flush so DB-assigned columns (id, tested_at) are populated, but
    # do NOT commit until the chain anchor succeeds.
    row = LabResult(batch_id=batch.id, **data.model_dump())
    db.add(row)
    db.flush()

    proof_payload = _lab_result_canonical_payload(row)
    proof_hash = blockchain_service.compute_data_hash(proof_payload)
    batch_id_bytes = _batch_id_to_bytes(batch_id)

    try:
        tx_hash, block_ts = blockchain_service.anchor_lab_proof(batch_id_bytes, proof_hash)
    except ContractLogicError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Contract error: {e}")
    except ReceiptPendingError as e:
        row.lab_proof_hash = "0x" + proof_hash.hex()
        batch.lab_verify_tx_hash = e.tx_hash
        _commit_or_orphan(db, batch_id, e.tx_hash)
        return _pending_response(batch_id, e.tx_hash, "lab")
    except Exception as e:
        db.rollback()
        logger.error(f"Blockchain error in anchor_lab_proof: {e}")
        raise HTTPException(status_code=502, detail="Blockchain transaction failed")

    row.lab_proof_hash = "0x" + proof_hash.hex()
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

    if db.query(PackagingRecord).filter(PackagingRecord.batch_id == batch.id).first():
        raise HTTPException(status_code=409, detail="Packaging record already exists for this batch")

    row = PackagingRecord(
        batch_id=batch.id,
        unit_count=data.unit_count,
        jar_ids=data.jar_ids,
        qr_codes=data.qr_codes,
        notes=data.notes,
    )
    db.add(row)
    db.flush()

    packaging_payload = _packaging_record_canonical_payload(row)
    packaging_hash = blockchain_service.compute_data_hash(packaging_payload)
    batch_id_bytes = _batch_id_to_bytes(batch_id)

    try:
        tx_hash, block_ts = blockchain_service.record_packaging(
            _get_user_signing_key(db, current_user["user_id"], current_user["role"]), batch_id_bytes, packaging_hash
        )
    except ContractLogicError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Contract error: {e}")
    except ReceiptPendingError as e:
        row.packaging_proof_hash = "0x" + packaging_hash.hex()
        batch.packaging_tx_hash = e.tx_hash
        _commit_or_orphan(db, batch_id, e.tx_hash)
        return _pending_response(batch_id, e.tx_hash, "package")
    except Exception as e:
        db.rollback()
        logger.error(f"Blockchain error in record_packaging: {e}")
        raise HTTPException(status_code=502, detail="Blockchain transaction failed")

    row.packaging_proof_hash = "0x" + packaging_hash.hex()
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

    if db.query(DistributionRecord).filter(DistributionRecord.batch_id == batch.id).first():
        raise HTTPException(status_code=409, detail="Distribution record already exists for this batch")

    row = DistributionRecord(
        batch_id=batch.id,
        retailer_name=data.retailer_name,
        transport_reference=data.transport_reference,
        handover_notes=data.handover_notes,
    )
    db.add(row)
    db.flush()

    dist_payload = _distribution_record_canonical_payload(row)
    dist_hash = blockchain_service.compute_data_hash(dist_payload)
    batch_id_bytes = _batch_id_to_bytes(batch_id)

    try:
        tx_hash, block_ts = blockchain_service.record_distribution(
            _get_user_signing_key(db, current_user["user_id"], current_user["role"]), batch_id_bytes, dist_hash
        )
    except ContractLogicError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Contract error: {e}")
    except ReceiptPendingError as e:
        row.distribution_proof_hash = "0x" + dist_hash.hex()
        batch.distribution_tx_hash = e.tx_hash
        _commit_or_orphan(db, batch_id, e.tx_hash)
        return _pending_response(batch_id, e.tx_hash, "distribute")
    except Exception as e:
        db.rollback()
        logger.error(f"Blockchain error in record_distribution: {e}")
        raise HTTPException(status_code=502, detail="Blockchain transaction failed")

    row.distribution_proof_hash = "0x" + dist_hash.hex()
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

def build_batch_view(batch) -> dict:
    """Canonical batch shape the FE can trust. Sources `quantity` from the
    harvest_record (the two-step create path never set batch.quantity, which is
    the root of the FE quantity=0 bug), and joins the GeoAI authenticity summary
    from the validation_results backref. Pure over attributes — unit-testable."""
    harvest = getattr(batch, "harvest_record", None)
    if harvest is not None and harvest.quantity_kg is not None:
        quantity = harvest.quantity_kg
    else:
        quantity = batch.quantity
    val = getattr(batch, "validation", None)
    return {
        "id": batch.id,
        "blockchain_batch_id": batch.blockchain_batch_id,
        "farmer_id": batch.farmer_id,
        "current_state": batch.current_state,
        "quantity": quantity,
        "create_tx_hash": batch.create_tx_hash,
        "harvest_tx_hash": batch.harvest_tx_hash,
        "process_tx_hash": batch.process_tx_hash,
        "lab_verify_tx_hash": batch.lab_verify_tx_hash,
        "packaging_tx_hash": batch.packaging_tx_hash,
        "distribution_tx_hash": batch.distribution_tx_hash,
        "created_at": batch.created_at,
        "harvested_at": batch.harvested_at,
        "processed_at": batch.processed_at,
        "lab_verified_at": batch.lab_verified_at,
        "packaged_at": batch.packaged_at,
        "distributed_at": batch.distributed_at,
        "authenticity": {
            "available": val is not None,
            "status": val.validation_status if val else None,
            "score": val.authenticity_score if val else None,
        },
    }


@router.get("/", response_model=list[BatchResponse])
def list_batches(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List batches (paginated) in the canonical view-model shape."""
    batches = (
        db.query(HoneyBatch).order_by(HoneyBatch.id.desc())
        .offset(skip).limit(limit).all()
    )
    return [build_batch_view(b) for b in batches]


@router.get("/{batch_id}", response_model=BatchResponse)
def get_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get batch detail in the canonical view-model shape."""
    batch = db.query(HoneyBatch).filter(
        HoneyBatch.blockchain_batch_id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return build_batch_view(batch)


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
def verify_batch(batch_id: str, db: Session = Depends(get_db)):
    """Public batch verification endpoint (for QR scan).

    No authentication required. Reads on-chain state and joins the persisted
    `lab_results` and `environmental_data` rows when present. When a lab row
    exists, also returns a three-way hash comparison: recomputed pre-image hash
    of the persisted row vs. `lab_results.lab_proof_hash` vs. on-chain
    `getBatch().labProofHash`. The scan UI shows the green "Blockchain
    Verified" badge only when state == DISTRIBUTED and `verification.lab.match`
    is true.
    """
    _check_blockchain()

    batch_id_bytes = _batch_id_to_bytes(batch_id)

    try:
        batch_data = blockchain_service.get_batch(batch_id_bytes)
        timeline = blockchain_service.get_batch_timeline(batch_id_bytes)
        hashes = blockchain_service.get_batch_hashes(batch_id_bytes)
    except ContractLogicError as e:
        raise HTTPException(status_code=404, detail=f"Batch not found on chain: {e}")

    batch = db.query(HoneyBatch).filter(
        HoneyBatch.blockchain_batch_id == batch_id
    ).first()

    lab_public: LabResultPublic | None = None
    apiary_public: ApiaryRecordPublic | None = None
    metadata_public: BatchMetadataPublic | None = None
    harvest_public: HarvestRecordPublic | None = None
    process_public: ProcessRecordPublic | None = None
    packaging_public: PackagingRecordPublic | None = None
    distribution_public: DistributionRecordPublic | None = None
    env_public: EnvironmentalDataPublic | None = None
    verification: VerificationBlock | None = None
    tx_hashes: TxHashes | None = None
    authenticity: AuthenticityPublic | None = None

    if batch is not None:
        tx_hashes = TxHashes(
            create_tx=batch.create_tx_hash,
            harvest_tx=batch.harvest_tx_hash,
            process_tx=batch.process_tx_hash,
            lab_tx=batch.lab_verify_tx_hash,
            package_tx=batch.packaging_tx_hash,
            distribute_tx=batch.distribution_tx_hash,
        )

        # GeoAI authenticity summary (chain-neutral): joined from
        # validation_results by integer batch.id. Absent until validate runs.
        from app.models.geo_ai import ValidationResult
        _val = (
            db.query(ValidationResult)
            .filter(ValidationResult.batch_id == batch.id)
            .first()
        )
        authenticity = AuthenticityPublic(
            available=_val is not None,
            status=_val.validation_status if _val else None,
            score=_val.authenticity_score if _val else None,
        )

        v_kwargs: dict = {}

        if batch.apiary_record is not None:
            apiary_public = ApiaryRecordPublic.model_validate(batch.apiary_record)
            v_kwargs["apiary"] = StageHashVerification(
                **_verify_apiary_hash(batch.apiary_record, hashes["apiary_hash"])
            )

        if batch.metadata_record is not None:
            metadata_public = BatchMetadataPublic.model_validate(batch.metadata_record)
            # The contract's getBatchHashes() view returns 6 fields (no
            # metadata); the metadata hash lives in the wider getBatch() tuple,
            # already in `batch_data` above.
            v_kwargs["metadata"] = StageHashVerification(
                **_verify_metadata_hash(batch.metadata_record, batch_data["metadata_hash"])
            )

        if batch.harvest_record is not None:
            harvest_public = HarvestRecordPublic.model_validate(batch.harvest_record)
            v_kwargs["harvest"] = StageHashVerification(
                **_verify_harvest_hash(batch.harvest_record, hashes["harvest_hash"])
            )

        if batch.process_record is not None:
            process_public = ProcessRecordPublic.model_validate(batch.process_record)
            v_kwargs["process"] = StageHashVerification(
                **_verify_process_hash(batch.process_record, hashes["process_hash"])
            )

        if batch.lab_result is not None:
            lab_public = LabResultPublic.model_validate(batch.lab_result)
            v_kwargs["lab"] = StageHashVerification(
                **_verify_lab_hash(batch.lab_result, hashes["lab_proof_hash"])
            )

        if batch.packaging_record is not None:
            packaging_public = PackagingRecordPublic.model_validate(batch.packaging_record)
            v_kwargs["packaging"] = StageHashVerification(
                **_verify_packaging_hash(batch.packaging_record, hashes["packaging_hash"])
            )

        if batch.distribution_record is not None:
            distribution_public = DistributionRecordPublic.model_validate(batch.distribution_record)
            v_kwargs["distribution"] = StageHashVerification(
                **_verify_distribution_hash(batch.distribution_record, hashes["distribution_hash"])
            )

        if v_kwargs:
            verification = VerificationBlock(**v_kwargs)

        if batch.environmental_data is not None:
            env_public = EnvironmentalDataPublic.model_validate(batch.environmental_data)

    return BatchVerifyResponse(
        batch_id=batch_id,
        state=batch_data["state"],
        beekeeper=batch_data["beekeeper"],
        lab_verified=batch_data["lab_verified"],
        timeline=BatchTimelineResponse(batch_id=batch_id, **timeline),
        hashes=BatchHashesResponse(batch_id=batch_id, **hashes),
        lab_result=lab_public,
        apiary_record=apiary_public,
        batch_metadata=metadata_public,
        harvest_record=harvest_public,
        process_record=process_public,
        packaging_record=packaging_public,
        distribution_record=distribution_public,
        environmental_data=env_public,
        verification=verification,
        tx_hashes=tx_hashes,
        authenticity=authenticity,
    )


@router.post("/simple", response_model=BatchResponse)
def create_simple_batch(
    data: SimpleBatchCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["farmer"])),
):
    """One-shot batch creation that anchors S0 (CREATED) and S1 (HARVESTED)
    on chain in a single call, then attaches a fresh environmental snapshot.

    The frontend uses this for the "register a harvest" form so it gets a
    real on-chain batch + environmental data without making three separate
    calls. The farmer is taken from the JWT — request body cannot impersonate.

    Sprint 9: `data.metadata` is required and strictly typed
    (`BatchMetadataInput`). The legacy inline-dict fallback from Sprint 8
    is removed — requests without typed metadata return 422.
    """
    _check_blockchain()

    farmer_id = current_user["user_id"]

    apiary = db.query(ApiaryLocation).filter(
        ApiaryLocation.id == data.apiary_id
    ).first()
    if not apiary:
        raise HTTPException(status_code=404, detail="Apiary not found")
    if apiary.farmer_id != farmer_id:
        raise HTTPException(status_code=403, detail="Apiary does not belong to this farmer")

    signer_key = _get_user_signing_key(db, farmer_id, current_user["role"])
    signer_address = blockchain_service.w3.eth.account.from_key(signer_key).address

    batch_id_bytes = blockchain_service.generate_batch_id(signer_address)
    batch_id_hex = "0x" + batch_id_bytes.hex()

    batch = HoneyBatch(
        blockchain_batch_id=batch_id_hex,
        farmer_id=farmer_id,
        apiary_id=apiary.id,
        harvest_date=data.harvest_date,
        quantity=data.quantity_kg,
        current_state="CREATED",
    )
    db.add(batch)
    db.flush()  # surface batch.id

    apiary_row = ApiaryRecord(
        batch_id=batch.id,
        apiary_id=apiary.id,
        latitude=apiary.latitude,
        longitude=apiary.longitude,
        altitude=apiary.altitude,
        vegetation_type=apiary.vegetation_type,
        hive_count=apiary.hive_count,
    )
    db.add(apiary_row)
    db.flush()
    db.refresh(apiary_row)

    apiary_payload = _apiary_record_canonical_payload(apiary_row)
    apiary_hash = blockchain_service.compute_data_hash(apiary_payload)

    metadata_row = _persist_typed_metadata(db, batch.id, data.metadata)
    metadata_hash = blockchain_service.compute_data_hash(
        _metadata_record_canonical_payload(metadata_row)
    )

    try:
        create_tx, create_block_ts = blockchain_service.create_batch(
            signer_key, batch_id_bytes, apiary_hash, metadata_hash
        )
    except ContractLogicError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Contract error (create): {e}")
    except ReceiptPendingError as e:
        apiary_row.apiary_proof_hash = "0x" + apiary_hash.hex()
        metadata_row.metadata_proof_hash = "0x" + metadata_hash.hex()
        batch.create_tx_hash = e.tx_hash
        _commit_or_orphan(db, batch_id_hex, e.tx_hash)
        return _pending_response(batch_id_hex, e.tx_hash, "create")
    except Exception as e:
        db.rollback()
        logger.error(f"Blockchain error in simple create_batch: {e}")
        raise HTTPException(status_code=502, detail="Blockchain transaction failed (create)")

    # Top up gas — the create tx drained the dev-funded wallet; record_harvest
    # would otherwise revert with insufficient funds on a second back-to-back tx.
    blockchain_service.fund_account(signer_address)

    apiary_row.apiary_proof_hash = "0x" + apiary_hash.hex()
    metadata_row.metadata_proof_hash = "0x" + metadata_hash.hex()
    batch.current_state = "HARVESTED"
    batch.create_tx_hash = create_tx
    batch.created_at = datetime.fromtimestamp(create_block_ts, tz=timezone.utc)

    harvest_row = HarvestRecord(
        batch_id=batch.id,
        harvest_date=data.harvest_date,
        quantity_kg=data.quantity_kg,
        hive_ids=data.hive_ids,
        gps_lat=apiary.latitude,
        gps_lon=apiary.longitude,
        notes=data.notes,
    )
    db.add(harvest_row)
    db.flush()
    db.refresh(harvest_row)  # see record_harvest for rationale

    harvest_payload = _harvest_record_canonical_payload(harvest_row)
    harvest_hash = blockchain_service.compute_data_hash(harvest_payload)

    try:
        harvest_tx, harvest_block_ts = blockchain_service.record_harvest(
            signer_key, batch_id_bytes, harvest_hash
        )
    except ContractLogicError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Contract error (harvest): {e}")
    except Exception as e:
        db.rollback()
        logger.error(f"Blockchain error in simple record_harvest: {e}")
        raise HTTPException(
            status_code=502,
            detail={
                "error": "harvest_anchor_failed_after_create_succeeded",
                "batch_id": batch_id_hex,
                "create_tx_hash": create_tx,
                "remediation": "Batch is in CREATED state on chain. Call POST /batches/{id}/harvest to advance.",
            },
        )

    harvest_row.harvest_proof_hash = "0x" + harvest_hash.hex()
    batch.harvest_tx_hash = harvest_tx
    batch.harvested_at = datetime.fromtimestamp(harvest_block_ts, tz=timezone.utc)

    try:
        env_data = fetch_environment_snapshot(apiary.latitude, apiary.longitude)
        db.add(EnvironmentalData(
            batch_id=batch.id,
            temperature=env_data["temperature"],
            humidity=env_data["humidity"],
            rainfall=env_data["rainfall"],
            pressure=env_data["pressure"],
            cloud_cover=env_data["cloud_cover"],
            wind_speed=env_data["wind_speed"],
            weather_source=env_data["weather_source"],
        ))
    except Exception:
        # Env snapshot is non-fatal — the batch is on chain, that's the source of truth.
        logger.exception("Environmental snapshot fetch failed for batch %s", batch_id_hex)

    _commit_or_orphan(db, batch_id_hex, harvest_tx)
    db.refresh(batch)
    return build_batch_view(batch)