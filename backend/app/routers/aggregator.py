import os, shutil
import requests
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
# FIX: Import shared get_db from database.py instead of duplicating it here.
from app.database import get_db
from app.models.aggregator import Aggregator
from app.schemas.aggregator import AggregatorCreate, AggregatorLogin, AggregatorDetails
from app.auth import hash_password, verify_password, create_access_token
from app.models.document import Document
from geoalchemy2.shape import from_shape
from shapely.geometry import Point

router = APIRouter(prefix="/aggregators", tags=["Aggregators"])


@router.post("/details/{agg_id}")
def add_details(agg_id: int, data: AggregatorDetails, db: Session = Depends(get_db)):
    agg = db.query(Aggregator).filter(Aggregator.id == agg_id).first()
    if not agg:
        raise HTTPException(status_code=404, detail="Aggregator not found")

    latitude = data.latitude
    longitude = data.longitude

    # If coordinates not provided, geocode the address
    # FIX: Use "is None" — 0.0 is a valid coordinate but falsy in Python.
    if latitude is None or longitude is None:
        if not data.address:
            raise HTTPException(status_code=400, detail="Provide either latitude/longitude or an address")

        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": data.address, "format": "json", "limit": 1},
            headers={"User-Agent": "AgriScanAI-App"}  # Nominatim requires a User-Agent
        )
        results = response.json()
        if not results:
            raise HTTPException(status_code=404, detail="Address not found")

        latitude = float(results[0]["lat"])
        longitude = float(results[0]["lon"])

    # Update aggregator data
    agg.region_location = from_shape(Point(longitude, latitude), srid=4326)
    agg.farmers_count = data.farmers_count
    agg.address = data.address  # <-- store the human-readable address

    db.commit()
    return {
        "message": "Aggregator details updated with geo-location",
        "latitude": latitude,
        "longitude": longitude,
        "address": agg.address
    }





UPLOAD_DIR = "uploads/aggregators"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/upload-document/{aggregator_id}")
def upload_document(aggregator_id: int, doc_type: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    agg = db.query(Aggregator).filter(Aggregator.id == aggregator_id).first()
    if not agg:
        raise HTTPException(status_code=404, detail="Aggregator not found")

    file_location = os.path.join(UPLOAD_DIR, f"{aggregator_id}_{file.filename}")
    with open(file_location, "wb") as f:
        f.write(file.file.read())

    document = Document(
        file_path=file_location,
        doc_type=doc_type,
        aggregator_id=aggregator_id
    )
    db.add(document)
    db.commit()
    return {"message": f"{doc_type} uploaded successfully"}