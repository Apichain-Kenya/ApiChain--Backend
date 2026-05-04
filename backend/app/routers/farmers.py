import os
import requests
import logging
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
import math
from sqlalchemy import func
from datetime import datetime, timedelta
from app.database import get_db
from app.models.farmer import Farmer
from app.models.document import Document
from app.models.apiary import ApiaryLocation
from app.schemas.farmer import (
    FarmerCreate,
    FarmerFarmDetails,
)
from app.auth import hash_password
from app.deps import get_current_user
from app.services.wallet import create_user_wallet
from app.services.roles import grant_blockchain_role_to_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/farmers", tags=["Farmers"])

UPLOAD_DIR = "uploads/farmers"
os.makedirs(UPLOAD_DIR, exist_ok=True)


api_cache = {}

def get_cache_key(lat: float, lon: float):
    return f"{round(lat, 4)}_{round(lon, 4)}"

def infer_vegetation(lat: float, lon: float, altitude: float | None) -> str:
    """
    Simple ecological inference for Kenya
    """

    # Central Highlands (Nyeri, Murang'a, Kiambu)
    if -0.8 < lat < 0.2 and 36.5 < lon < 37.5:
        if altitude and altitude > 1500:
            return "forest"
        return "cropland"

    # Rift Valley grasslands
    if -1.5 < lat < 1.0 and 35.0 < lon < 36.5:
        return "grassland"

    # Eastern dry areas
    if lon > 37.5:
        return "shrubland"

    # Nairobi / urban
    if -1.5 < lat < -1.0 and 36.6 < lon < 37.0:
        return "unknown"

    return "unknown"
    
def map_landcover_code(code: int) -> str:
    """
    Map ESA land cover codes to clean categories
    """

    if code is None:
        return "unknown"

    # Forest
    if code in [50, 60, 61, 62]:
        return "forest"

    # Grassland / savanna
    if code in [30, 40]:
        return "grassland"

    # Cropland
    if code in [10, 20]:
        return "cropland"

    # Shrubland
    if code in [120, 121, 122]:
        return "shrubland"

    # Urban / bare → treat as unknown for beekeeping
    if code in [190, 200]:
        return "unknown"

    return "unknown"

def map_vegetation(raw_data: dict) -> str:
    raw_str = str(raw_data).lower()

    if any(word in raw_str for word in ["forest", "tree", "woodland"]):
        return "forest"

    if any(word in raw_str for word in ["grass", "savanna", "pasture"]):
        return "grassland"

    if any(word in raw_str for word in ["crop", "farmland", "agriculture"]):
        return "cropland"

    if any(word in raw_str for word in ["shrub", "bush"]):
        return "shrubland"

    return "unknown"


@router.post("/create-farmer")
def create_farmer(
    data: FarmerCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if current_user["role"] != "on_ground_officer":
        raise HTTPException(status_code=403, detail="Only on-ground officers can create farmers")

    farmer = Farmer(
        first_name=data.first_name,
        last_name=data.last_name,
        phone=data.phone,
        username=data.username,
        email=data.email,
        password=hash_password(data.password),
        onboarded_by=current_user["user_id"],
    )

    db.add(farmer)
    db.flush()

    # Blockchain wallet
    wallet_address = create_user_wallet(db, farmer.id, "farmer")
    if wallet_address:
        farmer.wallet_address = wallet_address

    db.commit()
    db.refresh(farmer)

    role_result = grant_blockchain_role_to_user(db, farmer.id, "farmer")

    logger.info(
        f"Farmer {farmer.id} created. Wallet={wallet_address}, Blockchain={role_result}"
    )

    return {
        "message": "Farmer created successfully",
        "farmer_id": farmer.id,
        "wallet_address": wallet_address,
        "blockchain": role_result,
    }

@router.post("/farm-details/{farmer_id}")
def add_farm_details(
    farmer_id: int,
    data: FarmerFarmDetails,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if current_user["role"] not in ["on_ground_officer", "farmer"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    farmer = db.query(Farmer).filter(Farmer.id == farmer_id).first()
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found")

    latitude = data.latitude
    longitude = data.longitude

    # ---------------------------
    # GEOCODING
    # ---------------------------
    if latitude is None or longitude is None:
        if not data.address:
            raise HTTPException(
                status_code=400,
                detail="Provide either coordinates or address"
            )

        try:
            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": data.address, "format": "json", "limit": 1},
                headers={"User-Agent": "AgriScanAI-App"},
                timeout=5
            )
            results = response.json()
        except Exception as e:
            raise HTTPException(status_code=502, detail="Geocoding service failed")

        if not results:
            raise HTTPException(status_code=404, detail="Address not found")

        latitude = float(results[0]["lat"])
        longitude = float(results[0]["lon"])

    # ---------------------------
    # VALIDATE COORDINATES
    # ---------------------------
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise HTTPException(status_code=400, detail="Invalid coordinates")

    # ---------------------------
    # CACHE CHECK
    # ---------------------------
    cache_key = get_cache_key(latitude, longitude)

    if cache_key in api_cache:
        cached = api_cache[cache_key]
        altitude = cached["altitude"]
        vegetation = cached["vegetation"]
    else:
        # ALTITUDE
        altitude = None
        try:
            elev_res = requests.get(
                f"https://api.open-elevation.com/api/v1/lookup?locations={latitude},{longitude}",
                timeout=5
            )
            elev_data = elev_res.json()
            altitude = elev_data.get("results", [{}])[0].get("elevation")
        except Exception as e:
            logger.warning(f"Altitude fetch failed: {e}")

        vegetation = infer_vegetation(latitude, longitude, altitude)

        # VEGETATION
        # vegetation = "unknown"
        # try:
        #     veg_res = requests.get(
        #         f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=landcover",
        #         timeout=5
        #     )
        #     veg_data = veg_res.json()

        #     landcover_code = veg_data.get("current", {}).get("landcover")
        #     vegetation = map_landcover_code(landcover_code)

        # except Exception as e:
        #     logger.warning(f"Vegetation fetch failed: {e}")

        # CACHE STORE
        api_cache[cache_key] = {
            "altitude": altitude,
            "vegetation": vegetation
        }

    # ---------------------------
    # CREATE APIARY
    # ---------------------------
    apiary = ApiaryLocation(
        latitude=latitude,
        longitude=longitude,
        location=from_shape(Point(longitude, latitude), srid=4326),
        altitude=altitude,
        vegetation_type=vegetation,
        hive_count=data.number_of_hives,
        farmer_id=farmer.id
    )

    db.add(apiary)

    # Update farmer summary
    farmer.address = data.address
    farmer.experience = data.experience
    farmer.education = data.education
    farmer.feeding_practice = data.feeding_practice
    farmer.number_of_hives = data.number_of_hives

    db.commit()
    db.refresh(apiary)

    return {
        "message": "Apiary created successfully",
        "apiary_id": apiary.id,
        "latitude": latitude,
        "longitude": longitude,
        "altitude": altitude,
        "vegetation": vegetation
    }


@router.post("/upload-document/{farmer_id}")
def upload_document(
    farmer_id: int,
    doc_type: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
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

@router.get("/")
def get_farmers(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if current_user["role"] != "on_ground_officer":
        raise HTTPException(status_code=403, detail="Unauthorized")

    farmers = (
        db.query(Farmer)
        .filter(Farmer.onboarded_by == current_user["user_id"])
        .all()
    )

    return {
        "count": len(farmers),
        "data": [
            {
                "id": f.id,
                "first_name": f.first_name,
                "last_name": f.last_name,
                "phone": f.phone,
                "email": f.email,
                "address": f.address,
                "number_of_hives": f.number_of_hives,
                "experience": f.experience,
                "education": f.education,
                "feeding_practice": f.feeding_practice,
                "created_at": f.created_at,
            }
            for f in farmers
        ],
    }

@router.get("/{farmer_id}")
def get_farmer(
    farmer_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    farmer = db.query(Farmer).filter(Farmer.id == farmer_id).first()

    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found")

    return {
        "id": farmer.id,
        "first_name": farmer.first_name,
        "last_name": farmer.last_name,
        "phone": farmer.phone,
        "email": farmer.email,
        "address": farmer.address,
        "number_of_hives": farmer.number_of_hives,
        "experience": farmer.experience,
        "education": farmer.education,
        "feeding_practice": farmer.feeding_practice,
    }



@router.get("/stats/overview")
def get_farm_stats(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if current_user["role"] != "on_ground_officer":
        raise HTTPException(status_code=403, detail="Unauthorized")

    farmers_query = db.query(Farmer).filter(
        Farmer.onboarded_by == current_user["user_id"]
    )

    farmers = farmers_query.all()

    total_farmers = len(farmers)
    total_hives = sum(f.number_of_hives or 0 for f in farmers)
    avg_hives = total_hives // total_farmers if total_farmers else 0

    # correct monthly filter
    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    monthly = farmers_query.filter(
        Farmer.created_at >= start_of_month
    ).count()

    return {
        "total_farmers": total_farmers,
        "total_hives": total_hives,
        "average_hives": avg_hives,
        "monthly_registrations": monthly,
    }