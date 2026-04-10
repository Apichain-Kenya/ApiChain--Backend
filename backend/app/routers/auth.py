from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session # type: ignore
from sqlalchemy import or_ # type: ignore
from datetime import datetime, timedelta
import random
from app.database import get_db
from app.models.farmer import Farmer
from app.models.aggregator import Aggregator
from app.auth import verify_password, create_access_token
from app.schemas.auth import LoginRequest
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Auth"])




@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):

    user = db.query(User).filter(
        User.phone == data.identifier
    ).first()

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

    farmer = db.query(Farmer).filter(
        or_(
            Farmer.phone == data.identifier,
            Farmer.username == data.identifier
        )
    ).first()

    if farmer and verify_password(data.password, farmer.password):
        token = create_access_token({
            "sub": str(farmer.id),
            "role": "farmer"
        })

        return {
            "access_token": token,
            "token_type": "bearer",
            "role": "farmer"
        }

    raise HTTPException(status_code=401, detail="Invalid credentials")