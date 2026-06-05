from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import datetime, timedelta
import random
from app.database import get_db
from app.models.farmer import Farmer
from app.auth import verify_password, create_access_token
from app.schemas.auth import LoginRequest
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):

    # Check regular users (employees)
    user = db.query(User).filter(
        or_(
            User.phone == data.identifier,
            User.username == data.identifier,
        )
    ).first()

    if user:
        # Check if user is active
        if not user.is_active:
            raise HTTPException(status_code=401, detail="Your account has been deactivated. Please contact your administrator.")
        
        if verify_password(data.password, user.password):
            token = create_access_token({
                "sub": str(user.id),
                "role": user.role
            })

            return {
                "access_token": token,
                "token_type": "bearer",
                "role": user.role,
                "user": {
                    "id": user.id,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "username": user.username,
                    "email": user.email,
                    "phone": user.phone,
                    "role": user.role,
                    "is_active": user.is_active
                }
            }

    # Check farmers
    farmer = db.query(Farmer).filter(
        or_(
            Farmer.phone == data.identifier,
            Farmer.username == data.identifier
        )
    ).first()

    if farmer:
        # Check if farmer is active (if Farmer model has is_active field)
        # Note: Your Farmer model might need an is_active column
        if hasattr(farmer, 'is_active') and not farmer.is_active:
            raise HTTPException(status_code=401, detail="Your farmer account has been deactivated. Please contact your administrator.")
        
        if verify_password(data.password, farmer.password):
            token = create_access_token({
                "sub": str(farmer.id),
                "role": "farmer"
            })

            return {
                "access_token": token,
                "token_type": "bearer",
                "role": "farmer",
                "user": {
                    "id": farmer.id,
                    "first_name": farmer.first_name,
                    "last_name": farmer.last_name,
                    "username": farmer.username,
                    "email": farmer.email,
                    "phone": farmer.phone,
                    "role": "farmer",
                    "is_active": getattr(farmer, 'is_active', True)
                }
            }

    raise HTTPException(status_code=401, detail="Invalid credentials")