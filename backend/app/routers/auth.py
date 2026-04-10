from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session # type: ignore
from datetime import datetime, timedelta
import random
# FIX: Import shared get_db from database.py instead of duplicating it in every router.
# Also removed duplicate 'from app.database import SessionLocal' that appeared twice.
from app.database import get_db
from app.models.farmer import Farmer
from app.models.aggregator import Aggregator
from app.auth import verify_password, create_access_token
from app.schemas.auth import LoginRequest
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):

    from app.models.user import User

    user = db.query(User).filter(User.phone == data.phone).first()

    if not user or not verify_password(data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({
        "sub": str(user.id),
        "role": user.role
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role
    }