# app/routers/geo_ai.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_roles
from app.models.batch import HoneyBatch
from app.models.lab_result import LabResult
from app.models.environmental_data import EnvironmentalData
from app.models.apiary import ApiaryLocation
from app.models.geo_ai import GeoAIPrediction, ValidationResult
from app.services.geo_ai import predict_and_save, validate_and_save, GeoAIModelError

router = APIRouter(prefix="/geo-ai", tags=["Geo-AI"])


@router.post("/{batch_id}/predict")
def run_prediction(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles([
        "lab_test_officer", "on_ground_officer", "admin", "super_admin"
    ])),
):
    batch = db.query(HoneyBatch).filter(
        HoneyBatch.id == batch_id
    ).first()
    if not batch:
        raise HTTPException(404, "Batch not found")

    existing = db.query(GeoAIPrediction).filter(
        GeoAIPrediction.batch_id == batch_id
    ).first()
    if existing:
        raise HTTPException(409, "Prediction already exists for this batch")

    apiary = db.query(ApiaryLocation).filter(
        ApiaryLocation.id == batch.apiary_id
    ).first()
    if not apiary:
        raise HTTPException(400, "Apiary not recorded for this batch")

    env = db.query(EnvironmentalData).filter(
        EnvironmentalData.batch_id == batch_id
    ).first()
    if not env:
        raise HTTPException(400, "Environmental data not recorded yet")

    lab = db.query(LabResult).filter(
        LabResult.batch_id == batch_id
    ).first()
    pollen_density = (lab.pollen_density or 30000) if lab else 30000

    try:
        prediction = predict_and_save(
            db              = db,
            batch_id        = batch_id,
            latitude        = apiary.latitude,
            longitude       = apiary.longitude,
            altitude        = apiary.altitude or 1000.0,
            vegetation_type = apiary.vegetation_type or "unknown",
            harvest_date    = batch.harvested_at or batch.created_at,
            temperature     = env.temperature or 22.0,
            humidity        = env.humidity or 65.0,
            rainfall        = env.rainfall or 80.0,
            ndvi            = 0.55,
            pollen_density  = pollen_density,
        )
    except GeoAIModelError as e:
        raise HTTPException(503, f"GeoAI model unavailable: {e}")

    return {
        "batch_id":            batch_id,
        "predicted_moisture":  prediction.predicted_moisture,
        "predicted_sugar":     prediction.predicted_sugar,
        "predicted_hmf":       prediction.predicted_hmf,
        "confidence_score":    prediction.confidence_score,
        "region_detected":     prediction.region_detected,
        "flowering_species":   prediction.flowering_species,
        "triangulation_score": prediction.triangulation_score,
    }


@router.post("/{batch_id}/validate")
def run_validation(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles([
        "lab_test_officer", "on_ground_officer", "admin", "super_admin"
    ])),
):
    batch = db.query(HoneyBatch).filter(
        HoneyBatch.id == batch_id
    ).first()
    if not batch:
        raise HTTPException(404, "Batch not found")

    lab = db.query(LabResult).filter(
        LabResult.batch_id == batch_id
    ).first()
    if not lab:
        raise HTTPException(400, "Lab result not recorded yet — run lab test first")

    prediction = db.query(GeoAIPrediction).filter(
        GeoAIPrediction.batch_id == batch_id
    ).first()
    if not prediction:
        raise HTTPException(400, "Run POST /geo-ai/{batch_id}/predict first")

    existing = db.query(ValidationResult).filter(
        ValidationResult.batch_id == batch_id
    ).first()
    if existing:
        raise HTTPException(409, "Validation already exists for this batch")

    try:
        validation = validate_and_save(
            db              = db,
            batch_id        = batch_id,
            prediction      = prediction,
            actual_moisture = lab.moisture_content,
            actual_sugar    = lab.sucrose_level,
            actual_hmf      = lab.hmf_level,
        )
    except GeoAIModelError as e:
        raise HTTPException(503, f"GeoAI model unavailable: {e}")

    return {
        "batch_id":            batch_id,
        "authenticity_score":  validation.authenticity_score,
        "is_valid":            validation.is_valid,
        "validation_status":   validation.validation_status,
        "phys_match_score":    validation.phys_match_score,
        "triangulation_score": validation.triangulation_score,
    }


@router.get("/{batch_id}/result")
def get_result(
    batch_id: int,
    db: Session = Depends(get_db),
):
    """Public — get stored prediction + validation for a batch."""
    if not db.query(HoneyBatch).filter(HoneyBatch.id == batch_id).first():
        raise HTTPException(404, "Batch not found")

    prediction = db.query(GeoAIPrediction).filter(
        GeoAIPrediction.batch_id == batch_id
    ).first()
    validation = db.query(ValidationResult).filter(
        ValidationResult.batch_id == batch_id
    ).first()

    if not prediction:
        raise HTTPException(404, "No prediction found — run /predict first")

    return {
        "batch_id":   batch_id,
        "prediction": prediction,
        "validation": validation,
    }