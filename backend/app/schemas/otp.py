from pydantic import BaseModel

class OTPVerify(BaseModel):
    phone: str
    code: str