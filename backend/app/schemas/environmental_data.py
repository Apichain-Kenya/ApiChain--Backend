from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class EnvironmentalDataResponse(BaseModel):
    id: int
    apiary_id: int

    temperature: Optional[float]
    humidity: Optional[float]
    rainfall: Optional[float]
    wind_speed: Optional[float]

    air_quality_index: Optional[float]
    vegetation_index: Optional[float]
    soil_moisture: Optional[float]

    weather_source: Optional[str]

    recorded_at: datetime

    class Config:
        from_attributes = True