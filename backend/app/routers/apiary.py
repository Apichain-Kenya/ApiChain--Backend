"""Apiary location endpoints.

Sprint 6: extracted from the implicit "apiary created elsewhere" assumption.
`POST /batches/` now requires an `apiary_id` (the canonical pre-image of the
on-chain `apiaryHash` is a snapshot of a real apiary row), so we need an
explicit way for farmers and field officers to seed an apiary first.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_roles
from app.models.apiary import ApiaryLocation
from app.models.farmer import Farmer
from app.schemas.batch import (
    ApiaryLocationCreateRequest,
    ApiaryLocationPublic,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/apiary-locations", tags=["Apiary"])


@router.post("/", response_model=ApiaryLocationPublic)
def create_apiary_location(
    data: ApiaryLocationCreateRequest,
    farmer_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(
        require_roles(["farmer", "on_ground_officer", "admin", "super_admin"])
    ),
):
    """Create an apiary owned by a farmer.

    Ownership rules:
    - role=farmer: ignores `farmer_id`, always uses the JWT subject.
    - role=on_ground_officer | admin | super_admin: must supply `farmer_id`
      query param identifying the farmer they're enrolling for.
    """
    if current_user["role"] == "farmer":
        owner_id = current_user["user_id"]
    else:
        if farmer_id is None:
            raise HTTPException(
                status_code=400,
                detail="farmer_id query param required for non-farmer roles",
            )
        owner_id = farmer_id

    if not db.query(Farmer).filter(Farmer.id == owner_id).first():
        raise HTTPException(status_code=404, detail="Farmer not found")

    apiary = ApiaryLocation(
        farmer_id=owner_id,
        latitude=data.latitude,
        longitude=data.longitude,
        # PostGIS Geography(POINT) — note: (lon, lat) order per the project
        # convention documented in backend/.claude/CLAUDE.md.
        location=from_shape(Point(data.longitude, data.latitude), srid=4326),
        altitude=data.altitude,
        vegetation_type=data.vegetation_type,
        hive_count=data.hive_count,
    )
    db.add(apiary)
    db.commit()
    db.refresh(apiary)
    return apiary
