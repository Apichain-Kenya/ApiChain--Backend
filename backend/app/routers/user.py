import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.user import SuperAdminCreate
from app.auth import hash_password

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/super-admin/signup")
def create_super_admin(data: SuperAdminCreate, db: Session = Depends(get_db)):

    if data.inviteCode != os.getenv("SUPER_ADMIN_CODE"):
        raise HTTPException(status_code=403, detail="Invalid invite code")

    existing = db.query(User).filter(User.role == "super_admin").first()
    if existing:
        raise HTTPException(status_code=400, detail="Super admin already exists")

    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already in use")

    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username already in use")

    if db.query(User).filter(User.phone == data.phone).first():
        raise HTTPException(status_code=400, detail="Phone already in use")

    # Create user
    user = User(
        first_name=data.firstName,
        last_name=data.lastName,
        username=data.username,
        email=data.email,
        phone=data.phone,
        password=hash_password(data.password),
        role="super_admin"
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {"message": "Super admin created successfully"}