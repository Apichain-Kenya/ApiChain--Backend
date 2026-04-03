from typing import Optional

from pydantic import BaseModel, EmailStr

class FarmerCreate(BaseModel):
    first_name: str
    last_name: str
    phone: str
    email: Optional[EmailStr] = None
    password: str

class FarmerLogin(BaseModel):
    phone: str
    password: str


class FarmerFarmDetails(BaseModel):
    address: Optional[str] = None
    longitude: float
    latitude: float
    number_of_hives: int

class FarmerDocumentUpload(BaseModel):
    doc_type: str 