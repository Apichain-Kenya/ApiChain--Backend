import os
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
import requests
from sqlalchemy.orm import Session
from geoalchemy2.shape import from_shape
from shapely.geometry import Point

# FIX: Import shared get_db from database.py instead of duplicating it here.
from app.database import get_db
from app.models.farmer import Farmer
from app.models.document import Document
from app.schemas.farmer import FarmerCreate, FarmerLogin, FarmerFarmDetails, FarmerDocumentUpload
from app.auth import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/farmers", tags=["Farmers"])

UPLOAD_DIR = "uploads/farmers"
os.makedirs(UPLOAD_DIR, exist_ok=True)



@router.post("/register")
def register_farmer(data: FarmerCreate, db: Session = Depends(get_db)):
    farmer = Farmer(
        first_name=data.first_name,
        last_name=data.last_name,
        phone=data.phone,
        email=data.email,
        password=hash_password(data.password)
    )
    db.add(farmer)
    db.commit()
    db.refresh(farmer)
    return {"message": "Farmer registered. Proceed to OTP verification"}



@router.post("/farm-details/{farmer_id}")
def add_farm_details(farmer_id: int, data: FarmerFarmDetails, db: Session = Depends(get_db)):
    farmer = db.query(Farmer).filter(Farmer.id == farmer_id).first()
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found")

    latitude = data.latitude
    longitude = data.longitude

    # FIX: Use "is None" instead of truthiness check. 0.0 is a valid coordinate
    # (equator/prime meridian) but "not 0.0" evaluates to True in Python.
    if latitude is None or longitude is None:
        if not data.address:
            raise HTTPException(status_code=400, detail="Provide either latitude/longitude or an address")
        
        # Geocode address using OpenStreetMap
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": data.address, "format": "json", "limit": 1},
            headers={"User-Agent": "AgriScanAI-App"}
        )
        results = response.json()
        if not results:
            raise HTTPException(status_code=404, detail="Address not found")
        
        latitude = float(results[0]["lat"])
        longitude = float(results[0]["lon"])

    # Update farmer data
    farmer.location = from_shape(Point(longitude, latitude), srid=4326)
    farmer.number_of_hives = data.number_of_hives
    farmer.address = data.address  # <-- store the address

    db.commit()
    return {
        "message": "Farm details updated with geo-location",
        "latitude": latitude,
        "longitude": longitude,
        "address": farmer.address
    }




@router.post("/upload-document/{farmer_id}")
def upload_document(farmer_id: int, doc_type: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    farmer = db.query(Farmer).filter(Farmer.id == farmer_id).first()
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found")

    file_location = os.path.join(UPLOAD_DIR, f"{farmer_id}_{file.filename}")
    with open(file_location, "wb") as f:
        f.write(file.file.read())

    document = Document(
        file_path=file_location,
        doc_type=doc_type,
        farmer_id=farmer_id
    )
    db.add(document)
    db.commit()
    return {"message": f"{doc_type} uploaded successfully"}