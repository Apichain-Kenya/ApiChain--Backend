import requests

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.apiary import ApiaryLocation
from app.models.environmental_data import EnvironmentalData


scheduler = BackgroundScheduler()


def fetch_all_environmental_data():

    db: Session = SessionLocal()

    try:
        apiaries = db.query(ApiaryLocation).all()

        for apiary in apiaries:

            response = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": apiary.latitude,
                    "longitude": apiary.longitude,
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

    finally:
        db.close()


def start_scheduler():

    scheduler.add_job(
        fetch_all_environmental_data,
        "interval",
        hours=6
    )

    scheduler.start()