from typing import Optional

from pydantic import BaseModel

class AggregatorCreate(BaseModel):
    business_name: str
    phone: str
    email: str
    password: str

class AggregatorLogin(BaseModel):
    phone: str
    password: str

class AggregatorDetails(BaseModel):
    address: Optional[str] = None
    # FIX: Made lat/lon Optional — same reason as FarmerFarmDetails.
    # Check with "is None" in the router, not truthiness (0.0 is a valid coordinate).
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    farmers_count: int

class AggregatorDocumentUpload(BaseModel):
    doc_type: str  # e.g., "business_registration"