from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import random
# FIX: Import shared get_db from database.py instead of duplicating it in every router.
# Also removed duplicate 'from app.database import SessionLocal' that appeared twice.
from app.database import get_db
from app.models.farmer import Farmer
from app.models.aggregator import Aggregator
from app.auth import verify_password, create_access_token
from app.schemas.auth import LoginRequest
from app.models.otp import OTP
from app.schemas.otp import OTPVerify
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Auth"])


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

    # 🔹 First check users table
    user = db.query(User).filter(User.phone == data.phone).first()

    if user and verify_password(data.password, user.password):
        token = create_access_token({
            "sub": str(user.id),
            "role": user.role
        })
        return {
            "access_token": token,
            "token_type": "bearer",
            "role": user.role
        }

    # 🔹 fallback (old system)
    farmer = db.query(Farmer).filter(Farmer.phone == data.phone).first()
    if farmer and verify_password(data.password, farmer.password):
        token = create_access_token({"sub": str(farmer.id), "role": "farmer"})
        return {"access_token": token, "token_type": "bearer", "role": "farmer"}

    aggregator = db.query(Aggregator).filter(Aggregator.phone == data.phone).first()
    if aggregator and verify_password(data.password, aggregator.password):
        token = create_access_token({"sub": str(aggregator.id), "role": "aggregator"})
        return {"access_token": token, "token_type": "bearer", "role": "aggregator"}

    raise HTTPException(status_code=401, detail="Invalid credentials")