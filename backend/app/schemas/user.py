from pydantic import BaseModel, EmailStr

class SuperAdminCreate(BaseModel):
    inviteCode: str
    firstName: str
    lastName: str
    username: str
    email: EmailStr
    phone: str
    password: str