import os
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session  # type: ignore

from app.database import get_db
from app.models.user import User
from app.schemas.user import SuperAdminCreate, EmployeeCreate
from app.auth import hash_password
from app.deps import require_roles
from app.services.wallet import create_user_wallet
from app.services.roles import grant_blockchain_role_to_user

logger = logging.getLogger(__name__)

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

    user = User(
        first_name=data.firstName,
        last_name=data.lastName,
        username=data.username,
        email=data.email,
        phone=data.phone,
        password=hash_password(data.password),
        role="super_admin",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    # Super admin uses the deployer key (DEFAULT_ADMIN_ROLE already granted
    # at contract deployment). No personal wallet needed.
    role_result = grant_blockchain_role_to_user(db, user.id, "super_admin")
    logger.info(f"Super admin {user.id} created. Blockchain: {role_result['message']}")

    return {"message": "Super admin created successfully"}


@router.post("/create-employee")
def create_employee(
    data: EmployeeCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["super_admin", "admin"])),
):
    """
    Create system employees (admin-controlled endpoint).
    Wallet + blockchain role are assigned automatically for applicable roles.
    """

    allowed_roles = [
        "admin",
        "on_ground_officer",
        "harvest_processor",
        "lab_test_officer",
        "packager",
        "distributor",
    ]

    if data.role not in allowed_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Allowed roles: {allowed_roles}",
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
        created_by=current_user["user_id"],
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    # Blockchain: create wallet + grant role for applicable employee roles
    wallet_address = create_user_wallet(db, user.id, data.role)
    if wallet_address:
        db.commit()

    role_result = grant_blockchain_role_to_user(db, user.id, data.role)
    logger.info(
        f"Employee {user.id} (role={data.role}) created. "
        f"Wallet={wallet_address or 'N/A'}, Blockchain: {role_result['message']}"
    )

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
            "created_by": user.created_by,
        },
        "wallet_address": wallet_address,
        "blockchain": role_result,
    }
