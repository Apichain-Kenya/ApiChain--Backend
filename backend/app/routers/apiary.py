"""Apiary location endpoints.

Sprint 6: extracted from the implicit "apiary created elsewhere" assumption.
`POST /batches/` now requires an `apiary_id` (the canonical pre-image of the
on-chain `apiaryHash` is a snapshot of a real apiary row), so we need an
explicit way for farmers and field officers to seed an apiary first.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_roles, get_current_user
from app.models.apiary import ApiaryLocation
from app.models.farmer import Farmer
from app.schemas.batch import (
    ApiaryLocationCreateRequest,
    ApiaryLocationPublic,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/apiary-locations", tags=["Apiary"])


@router.get("/")
def get_apiary_locations(
    farmer_id: int = Query(None, description="Filter by farmer ID"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get apiary locations.
    - Harvest processors can view all apiaries
    - On-ground officers can view apiaries for farmers they onboarded
    - Farmers can view their own apiaries
    """
    
    query = db.query(ApiaryLocation)
    
    if farmer_id:
        query = query.filter(ApiaryLocation.farmer_id == farmer_id)
    
    if current_user["role"] == "farmer":
        query = query.filter(ApiaryLocation.farmer_id == current_user["user_id"])
    elif current_user["role"] == "on_ground_officer":
        farmer_ids = db.query(Farmer.id).filter(Farmer.onboarded_by == current_user["user_id"]).all()
        farmer_ids = [f[0] for f in farmer_ids]
        if farmer_ids:
            query = query.filter(ApiaryLocation.farmer_id.in_(farmer_ids))
        else:
            return []
    elif current_user["role"] not in ["super_admin", "admin", "harvest_processor"]:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    apiaries = query.all()
    
    return [
        {
            "id": a.id,
            "latitude": a.latitude,
            "longitude": a.longitude,
            "altitude": a.altitude,
            "vegetation_type": a.vegetation_type,
            "hive_count": a.hive_count,
            "farmer_id": a.farmer_id,
        }
        for a in apiaries
    ]


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