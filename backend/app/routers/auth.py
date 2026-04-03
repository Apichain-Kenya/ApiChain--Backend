from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import random
from app.database import SessionLocal
from app.models.farmer import Farmer
from app.models.aggregator import Aggregator
from app.auth import verify_password, create_access_token
from app.schemas.auth import LoginRequest
from app.database import SessionLocal
from app.models.otp import OTP
from app.schemas.otp import OTPVerify

router = APIRouter(prefix="/auth", tags=["Auth"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Send OTP
@router.post("/send-otp")
def send_otp(phone: str, db: Session = Depends(get_db)):
    code = str(random.randint(100000, 999999))

    otp = OTP(
        phone=phone,
        code=code,
        expires_at=datetime.utcnow() + timedelta(minutes=5)
    )

    db.add(otp)
    db.commit()

    return {"otp": code}  # replace with SMS later


@router.post("/verify-otp")
def verify_otp(data: OTPVerify, db: Session = Depends(get_db)):
    otp = db.query(OTP).filter(
        OTP.phone == data.phone,
        OTP.code == data.code
    ).first()

    if not otp or otp.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    # OTP is valid -> find the user (Farmer or Aggregator)
    user = db.query(Farmer).filter(Farmer.phone == data.phone).first()
    role = "farmer"
    if not user:
        user = db.query(Aggregator).filter(Aggregator.phone == data.phone).first()
        role = "aggregator"

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update verification
    user.is_verified = True
    user.verification_status = "verified"

    # Delete OTP after use
    db.delete(otp)
    db.commit()

    return {"message": f"{role.capitalize()} verified successfully"}



@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(Farmer).filter(Farmer.phone == data.phone).first()
    role = None

    if user:
        role = "farmer"
    else:
        user = db.query(Aggregator).filter(Aggregator.phone == data.phone).first()
        if user:
            role = "aggregator"

    if not user or not verify_password(data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": str(user.id), "role": role})
    return {"access_token": token, "token_type": "bearer", "role": role}