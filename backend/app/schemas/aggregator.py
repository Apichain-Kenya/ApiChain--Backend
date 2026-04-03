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
    longitude: float
    latitude: float
    farmers_count: int

class AggregatorDocumentUpload(BaseModel):
    doc_type: str  # e.g., "business_registration"