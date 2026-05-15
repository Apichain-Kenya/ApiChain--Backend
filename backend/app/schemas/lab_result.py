from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class LabResultCreate(BaseModel):
    moisture_content: Optional[float] = None
    sucrose_level: Optional[float] = None
    hmf_level: Optional[float] = None
    pollen_density: Optional[float] = None
    purity_score: Optional[float] = None

    passed_quality_check: bool

    laboratory_name: Optional[str] = None
    analyst_name: Optional[str] = None
    certificate_number: Optional[str] = None
    notes: Optional[str] = None


class LabResultResponse(BaseModel):
    id: int
    batch_id: int

    moisture_content: Optional[float]
    sucrose_level: Optional[float]
    hmf_level: Optional[float]
    pollen_density: Optional[float]
    purity_score: Optional[float]

    passed_quality_check: bool

    laboratory_name: Optional[str]
    analyst_name: Optional[str]
    certificate_number: Optional[str]
    notes: Optional[str]

    tested_at: datetime

    class Config:
        from_attributes = True