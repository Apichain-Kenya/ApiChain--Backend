import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session # type: ignore

from app.database import get_db
from app.models.user import User
from app.schemas.user import SuperAdminCreate
from app.auth import hash_password
from app.schemas.user import EmployeeCreate
from app.deps import require_roles

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

def require_admin(user_role: str):
    if user_role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
@router.post("/create-employee")
def create_employee(
    data: EmployeeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["super_admin", "admin"]))
):
    """
    Create system employees (admin-controlled endpoint)
    """

   
    allowed_roles = [
        "admin",
        "onboarding_officer",
        "harvest_processor",
        "tester_lab",
        "packaging_distribution"
    ]

  
    if data.role not in allowed_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Allowed roles: {allowed_roles}"
        )

   
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already exists")

    if db.query(User).filter(User.phone == data.phone).first():
        raise HTTPException(status_code=400, detail="Phone already exists")

    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")

    user = User(
        first_name=data.first_name,
        last_name=data.last_name,
        username=data.username,
        email=data.email,
        phone=data.phone,
        password=hash_password(data.password),
        role=data.role,
        created_by=current_user.id 
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "message": "Employee created successfully",
        "user": {
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
            "email": user.email,
            "phone": user.phone,
            "role": user.role,
            "created_by": user.created_by
        }
    }