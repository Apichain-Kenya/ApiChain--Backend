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
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    number_of_hives: int

    experience: Optional[int] = None
    education: Optional[str] = None
    feeding_practice: Optional[str] = None

class FarmerDocumentUpload(BaseModel):
    doc_type: str 