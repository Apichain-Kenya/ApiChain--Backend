from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.batch import HoneyBatch
from app.models.lab_result import LabResult
from app.schemas.lab_result import (
    LabResultCreate,
    LabResultResponse
)

router = APIRouter(
    prefix="/lab-results",
    tags=["Lab Results"]
)


@router.post("/{batch_id}", response_model=LabResultResponse)
def create_lab_result(
    batch_id: int,
    data: LabResultCreate,
    db: Session = Depends(get_db),
):

    batch = db.query(HoneyBatch).filter(
        HoneyBatch.id == batch_id
    ).first()

    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    existing = db.query(LabResult).filter(
        LabResult.batch_id == batch_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Lab result already exists"
        )

    result = LabResult(
        batch_id=batch_id,
        **data.model_dump()
    )

    db.add(result)

    batch.current_state = "LAB_VERIFIED"

    db.commit()
    db.refresh(result)

    return result


@router.get("/{batch_id}")
def get_lab_result(
    batch_id: int,
    db: Session = Depends(get_db),
):

    result = db.query(LabResult).filter(
        LabResult.batch_id == batch_id
    ).first()

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Lab result not found"
        )

    return result