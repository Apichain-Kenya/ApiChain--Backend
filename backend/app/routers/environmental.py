import requests
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.apiary import ApiaryLocation
from app.models.environmental_data import EnvironmentalData
from app.schemas.environmental_data import EnvironmentalDataResponse

router = APIRouter(
    prefix="/environment",
    tags=["Environmental Data"]
)


@router.post("/fetch/{apiary_id}")
def fetch_environment_data(
    apiary_id: int,
    db: Session = Depends(get_db),
):
    apiary = db.query(ApiaryLocation).filter(
        ApiaryLocation.id == apiary_id
    ).first()

    if not apiary:
        raise HTTPException(status_code=404, detail="Apiary not found")

    latitude = apiary.latitude
    longitude = apiary.longitude

    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": ",".join([
                    "temperature_2m",
                    "relative_humidity_2m",
                    "rain",
                    "wind_speed_10m"
                ])
            },
            timeout=10
        )

        data = response.json()

    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Failed to fetch weather data"
        )

    current = data.get("current", {})

    env = EnvironmentalData(
        apiary_id=apiary.id,

        temperature=current.get("temperature_2m"),
        humidity=current.get("relative_humidity_2m"),
        rainfall=current.get("rain"),
        wind_speed=current.get("wind_speed_10m"),

        weather_source="open-meteo"
    )

    db.add(env)
    db.commit()
    db.refresh(env)

    return {
        "message": "Environmental data fetched successfully",
        "data": env
    }

@router.get("/environment/{batch_id}")
def get_environment_data(
    batch_id: int,
    db: Session = Depends(get_db),
):

    env = db.query(EnvironmentalData).filter(
        EnvironmentalData.batch_id == batch_id
    ).first()

    if not env:
        raise HTTPException(
            status_code=404,
            detail="Environmental data not found"
        )

    return env