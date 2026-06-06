"""Environmental data endpoints.

Sprint 3 (2026-05-16): rebuilt to honour the data model.

The `environmental_data.batch_id` FK is NOT NULL with a UNIQUE constraint —
each snapshot belongs to exactly one batch. The Sprint 2 implementation took
`{apiary_id}` and tried to write `apiary_id=...` into a column named
`batch_id`, which 500'd on every commit. The endpoint now takes the on-chain
`batch_id` (hex string), resolves the batch's apiary via the existing
relationship, and fetches a snapshot keyed to the batch.

Auth: write is guarded; read is public (matches `GET /batches/{id}/verify`'s
public-QR posture).

The hot path for creating env snapshots remains `POST /batches/simple`, which
attaches a snapshot at S0+S1. This endpoint is the manual fallback for
batches that didn't go through `/simple`.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_roles
from app.models.apiary import ApiaryLocation
from app.models.batch import HoneyBatch
from app.models.environmental_data import EnvironmentalData
from app.services.environment import fetch_environment_snapshot

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/environment",
    tags=["Environmental Data"]
)


@router.post("/fetch/{batch_id}")
def fetch_environment_data(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles([
        "farmer",
        "on_ground_officer",
        "harvest_processor",
        "lab_test_officer",
        "admin",
        "super_admin",
    ])),
):
    """Fetch and persist an environmental snapshot for a batch.

    Uses the batch's apiary GPS coords. Idempotent in spirit: one row per
    batch — second calls return 409.
    """
    batch = db.query(HoneyBatch).filter(
        HoneyBatch.blockchain_batch_id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.apiary_id is None:
        raise HTTPException(
            status_code=400,
            detail="Batch has no apiary; cannot fetch environmental data",
        )

    apiary = db.query(ApiaryLocation).filter(
        ApiaryLocation.id == batch.apiary_id
    ).first()
    if not apiary:
        raise HTTPException(status_code=404, detail="Apiary not found")

    existing = db.query(EnvironmentalData).filter(
        EnvironmentalData.batch_id == batch.id
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Environmental data already exists for this batch",
        )

    try:
        snapshot = fetch_environment_snapshot(apiary.latitude, apiary.longitude)
    except Exception:
        logger.exception("Open-Meteo fetch failed for batch %s", batch_id)
        raise HTTPException(
            status_code=502,
            detail="Failed to fetch weather data",
        )

    env = EnvironmentalData(batch_id=batch.id, **snapshot)
    db.add(env)
    db.commit()
    db.refresh(env)

    return {
        "message": "Environmental data fetched successfully",
        "data": env,
    }


@router.get("/{batch_id}")
def get_environment_data(
    batch_id: str,
    db: Session = Depends(get_db),
):
    """Public read: env snapshot keyed by on-chain batch_id (hex string)."""
    batch = db.query(HoneyBatch).filter(
        HoneyBatch.blockchain_batch_id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    env = db.query(EnvironmentalData).filter(
        EnvironmentalData.batch_id == batch.id
    ).first()
    if not env:
        raise HTTPException(
            status_code=404,
            detail="Environmental data not found",
        )

    return env
