# app/routers/geo_ai.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_roles
from app.models.batch import HoneyBatch
from app.models.apiary import ApiaryLocation
from app.models.geo_ai import GeoAIPrediction, ValidationResult
from app.models.lab_result import LabResult
from app.schemas.batch import LabPreviewRequest, LabPreviewResponse
from app.routers.batch import _ensure_environmental_data, _compute_authenticity

router = APIRouter(prefix="/geo-ai", tags=["Geo-AI"])


@router.post("/{batch_id}/preview", response_model=LabPreviewResponse)
def preview_authenticity(
    batch_id: int,
    data: LabPreviewRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles([
        "lab_test_officer", "on_ground_officer", "admin", "super_admin"
    ])),
):
    """Non-persisting authenticity preview for the merged lab panel's 'Run Score'.
    Persists the ENV snapshot (so submit reuses it → identical anchored result) but
    does NOT write geo_ai_predictions / validation_results. Server computes the
    score from the tester's entered actuals; the client never supplies a score."""
    batch = db.query(HoneyBatch).filter(HoneyBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, "Batch not found")
    apiary = db.query(ApiaryLocation).filter(ApiaryLocation.id == batch.apiary_id).first()
    if not apiary:
        raise HTTPException(400, "Apiary not recorded for this batch")

    env = _ensure_environmental_data(db, batch)
    if env is None:
        raise HTTPException(400, "Environmental data unavailable (no apiary coords)")
    db.commit()  # persist the env snapshot so submit reuses the same inputs

    claimed_honey_type = None
    if batch.metadata_record:
       claimed_honey_type = batch.metadata_record.honey_type

    pred, val, explanation = _compute_authenticity(
        batch, apiary, env,
        data.moisture_content,
        data.hmf_level,
        data.sucrose_level,
        pollen_density     = data.pollen_density,
        claimed_honey_type = claimed_honey_type,
)
    return LabPreviewResponse(
        predicted_moisture=pred["predicted_moisture"],
        predicted_sugar=pred["predicted_sugar"],
        predicted_hmf=pred["predicted_hmf"],
        authenticity_score=val["authenticity_score"],
        validation_status=val["validation_status"],
        explanation=explanation,
        region_detected=pred["region_detected"],
        triangulation_score=pred["triangulation_score"],
        confidence_score=pred["confidence_score"],
        phys_match_score=val["phys_match_score"],
    )


@router.get("/{batch_id}/result")
def get_result(batch_id: int, db: Session = Depends(get_db)):
    """Public — stored prediction + validation + actual lab metrics. (Lab-verify is
    now the sole writer of these rows; this is read-only.)"""
    if not db.query(HoneyBatch).filter(HoneyBatch.id == batch_id).first():
        raise HTTPException(404, "Batch not found")
    prediction = db.query(GeoAIPrediction).filter(GeoAIPrediction.batch_id == batch_id).first()
    validation = db.query(ValidationResult).filter(ValidationResult.batch_id == batch_id).first()
    if not prediction:
        raise HTTPException(404, "No prediction found — run lab verification first")
    lab = db.query(LabResult).filter(LabResult.batch_id == batch_id).first()
    return {
        "batch_id": batch_id,
        "prediction": prediction,
        "validation": validation,
        "lab": {
            "moisture_content": lab.moisture_content if lab else None,
            "sucrose_level": lab.sucrose_level if lab else None,
            "hmf_level": lab.hmf_level if lab else None,
        },
    }
