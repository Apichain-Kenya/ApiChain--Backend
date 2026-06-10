import os
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, EmailStr

from app.database import get_db
from app.models.user import User
from app.models.farmer import Farmer
from app.auth import hash_password
from app.deps import require_roles
from app.services.wallet import create_user_wallet
from app.services.roles import grant_blockchain_role_to_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Users"])

# ========== Schemas ==========

class SuperAdminCreate(BaseModel):
    inviteCode: str
    firstName: str
    lastName: str
    username: str
    email: EmailStr
    phone: str
    password: str

class EmployeeCreate(BaseModel):
    first_name: str
    last_name: str
    username: str
    email: EmailStr
    phone: str
    password: str
    role: str

class InviteCodeVerify(BaseModel):
    inviteCode: str

class UserResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    username: str
    email: Optional[str] = None
    phone: str
    role: str
    is_active: bool = True
    created_by: Optional[int] = None

    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

class ToggleStatusRequest(BaseModel):
    is_active: bool

class EmployeeResponse(BaseModel):
    message: str
    user: dict
    wallet_address: Optional[str] = None
    blockchain: Optional[dict] = None

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

@router.post("/{user_id}/change-password")
def change_password(
    user_id: int,
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["super_admin", "admin"])),
):
    """Change user password"""
    from app.auth import verify_password, hash_password
    
    if user_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="You can only change your own password")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not verify_password(data.current_password, user.password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    user.password = hash_password(data.new_password)
    db.commit()
    
    return {"message": "Password changed successfully"}

# ========== PUBLIC ENDPOINTS (No authentication required) ==========

@router.post("/verify-invite-code")
def verify_invite_code(data: InviteCodeVerify):
    """
    Verify if the invite code is valid.
    """
    correct_code = os.getenv("SUPER_ADMIN_CODE", "ApiChain@SuperAdmin2025")
    
    if data.inviteCode == correct_code:
        return {"valid": True, "message": "Code verified successfully"}
    else:
        raise HTTPException(status_code=400, detail="Invalid invite code")


@router.post("/super-admin/signup")
def create_super_admin(data: SuperAdminCreate, db: Session = Depends(get_db)):
    super_admin_code = os.getenv("SUPER_ADMIN_CODE", "ApiChain@SuperAdmin2025")
    if data.inviteCode != super_admin_code:
        raise HTTPException(status_code=400, detail="Invalid invite code")

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
        is_active=True,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    # Super admin uses the deployer key (DEFAULT_ADMIN_ROLE already granted
    # at contract deployment). No personal wallet needed.
    role_result = grant_blockchain_role_to_user(db, user.id, "super_admin")
    logger.info(f"Super admin {user.id} created. Blockchain: {role_result['message']}")

    return {"message": "Super admin created successfully", "user_id": user.id}


# ========== AUTHENTICATED ENDPOINTS ==========
@router.post("/create-employee", response_model=EmployeeResponse)
def create_employee(
    data: EmployeeCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["super_admin", "admin"])),
):
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

    from datetime import datetime
    
    user = User(
        first_name=data.first_name,
        last_name=data.last_name,
        username=data.username,
        email=data.email,
        phone=data.phone,
        password=hash_password(data.password),
        role=data.role,
        created_by=current_user["user_id"],
        is_active=True,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    # Blockchain: create wallet + grant role for applicable employee roles
    wallet_address = create_user_wallet(db, user.id, data.role)
    if wallet_address:
        db.commit()

    role_result = grant_blockchain_role_to_user(db, user.id, data.role)
    logger.info(f"Employee {user.id} (role={data.role}) created")

    return EmployeeResponse(
        message="Employee created successfully",
        user={
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
            "email": user.email,
            "phone": user.phone,
            "role": user.role,
            "created_by": user.created_by,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        wallet_address=wallet_address,
        blockchain=role_result,
    )

@router.get("/")
def get_all_users(
    current_user: dict = Depends(require_roles(["super_admin", "admin"])),
    db: Session = Depends(get_db),
):
    users = db.query(User).all()
    return users

@router.get("/all-users-with-farmers")
def get_all_users_including_farmers(
    current_user: dict = Depends(require_roles(["super_admin", "admin"])),
    db: Session = Depends(get_db),
):
    from app.models.farmer import Farmer
    from datetime import datetime
    
    employees = db.query(User).all()
    farmers = db.query(Farmer).all()
    
    all_users = []
    
    for emp in employees:
        created_at = getattr(emp, 'created_at', None)
        if created_at is None:
            created_at = datetime.utcnow()
        
        all_users.append({
            "id": emp.id,
            "user_type": "employee",
            "first_name": emp.first_name,
            "last_name": emp.last_name,
            "username": emp.username,
            "email": emp.email,
            "phone": emp.phone,
            "role": emp.role,
            "is_active": emp.is_active,
            "created_by": emp.created_by,
            "created_at": created_at.isoformat() if hasattr(created_at, 'isoformat') else created_at,
        })
    
    for farmer in farmers:
        created_at = getattr(farmer, 'created_at', None)
        if created_at is None:
            created_at = datetime.utcnow()
        
        farmer_dict = {
            "id": farmer.id,
            "user_type": "farmer",
            "first_name": farmer.first_name,
            "last_name": farmer.last_name,
            "username": farmer.username if farmer.username else farmer.phone,
            "phone": farmer.phone,
            "role": "farmer",
            "is_active": True,
            "created_at": created_at.isoformat() if hasattr(created_at, 'isoformat') else created_at,
        }
        if hasattr(farmer, 'email') and farmer.email:
            farmer_dict["email"] = farmer.email
        if hasattr(farmer, 'onboarded_by'):
            farmer_dict["created_by"] = farmer.onboarded_by
        
        all_users.append(farmer_dict)
    
    all_users.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    return all_users

@router.get("/{user_id}")
def get_user(
    user_id: int,
    current_user: dict = Depends(require_roles(["super_admin", "admin"])),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user

@router.put("/{user_id}")
def update_user(
    user_id: int,
    user_update: UserUpdate,
    current_user: dict = Depends(require_roles(["super_admin", "admin"])),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.id == current_user["user_id"] and user_update.role and user_update.role != user.role:
        raise HTTPException(
            status_code=400,
            detail="Cannot change your own role"
        )
    
    update_data = user_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)
    
    db.commit()
    db.refresh(user)
    return user

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    current_user: dict = Depends(require_roles(["super_admin", "admin"])),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.id == current_user["user_id"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete your own account"
        )
    
    if user.role == "super_admin":
        super_admin_count = db.query(User).filter(User.role == "super_admin").count()
        if super_admin_count <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete the last super admin"
            )
    
    db.delete(user)
    db.commit()
    return None

@router.patch("/{user_id}/toggle-status")
def toggle_user_status(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["super_admin", "admin"])),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.id == current_user["user_id"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot deactivate your own account"
        )
    
    if user.role == "super_admin":
        super_admin_count = db.query(User).filter(User.role == "super_admin").count()
        if super_admin_count <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot deactivate the last super admin"
            )
    
    user.is_active = not user.is_active
    db.commit()
    db.refresh(user)
    
    return {
        "id": user.id,
        "is_active": user.is_active,
        "message": f"User {'activated' if user.is_active else 'deactivated'} successfully"
    }

@router.get("/all-users-with-farmers")
def get_all_users_including_farmers(
    current_user: dict = Depends(require_roles(["super_admin"])),
    db: Session = Depends(get_db),
):
    """Get all users including farmers with proper created_at dates"""
    from app.models.farmer import Farmer
    from datetime import datetime
    
    employees = db.query(User).all()
    farmers = db.query(Farmer).all()
    
    all_users = []
    
    # Add employees
    for emp in employees:
        # Handle created_at properly
        created_at = getattr(emp, 'created_at', None)
        if created_at is None:
            created_at = datetime.utcnow()
        
        all_users.append({
            "id": emp.id,
            "user_type": "employee",
            "first_name": emp.first_name,
            "last_name": emp.last_name,
            "username": emp.username,
            "email": emp.email,
            "phone": emp.phone,
            "role": emp.role,
            "is_active": emp.is_active,
            "created_by": emp.created_by,
            "created_at": created_at.isoformat() if hasattr(created_at, 'isoformat') else created_at,
        })
    
    # Add farmers
    for farmer in farmers:
        # Handle created_at properly
        created_at = getattr(farmer, 'created_at', None)
        if created_at is None:
            created_at = datetime.utcnow()
        
        farmer_dict = {
            "id": farmer.id,
            "user_type": "farmer",
            "first_name": farmer.first_name,
            "last_name": farmer.last_name,
            "username": farmer.username if farmer.username else farmer.phone,
            "phone": farmer.phone,
            "role": "farmer",
            "is_active": True,
            "created_at": created_at.isoformat() if hasattr(created_at, 'isoformat') else created_at,
        }
        if hasattr(farmer, 'email') and farmer.email:
            farmer_dict["email"] = farmer.email
        if hasattr(farmer, 'onboarded_by'):
            farmer_dict["created_by"] = farmer.onboarded_by
        
        all_users.append(farmer_dict)
    
    # Sort by created_at (newest first)
    all_users.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    return all_users

@router.get("/{user_id}")
def get_user(
    user_id: int,
    current_user: dict = Depends(require_roles(["super_admin"])),
    db: Session = Depends(get_db),
):
    """Get a specific user by ID"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user


@router.put("/{user_id}")
def update_user(
    user_id: int,
    user_update: UserUpdate,
    current_user: dict = Depends(require_roles(["super_admin"])),
    db: Session = Depends(get_db),
):
    """Update a user"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Don't allow updating your own role
    if user.id == current_user["user_id"] and user_update.role and user_update.role != user.role:
        raise HTTPException(
            status_code=400,
            detail="Cannot change your own role"
        )
    
    update_data = user_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)
    
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    current_user: dict = Depends(require_roles(["super_admin"])),
    db: Session = Depends(get_db),
):
    """Delete a user"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Cannot delete yourself
    if user.id == current_user["user_id"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete your own account"
        )
    
    # Cannot delete last super admin
    if user.role == "super_admin":
        super_admin_count = db.query(User).filter(User.role == "super_admin").count()
        if super_admin_count <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete the last super admin"
            )
    
    db.delete(user)
    db.commit()
    return None


@router.patch("/{user_id}/toggle-status")
def toggle_user_status(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(["super_admin"])),
):
    """Toggle user active status"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Cannot deactivate yourself
    if user.id == current_user["user_id"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot deactivate your own account"
        )
    
    # Cannot deactivate last super admin
    if user.role == "super_admin":
        super_admin_count = db.query(User).filter(User.role == "super_admin").count()
        if super_admin_count <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot deactivate the last super admin"
            )
    
    user.is_active = not user.is_active
    db.commit()
    db.refresh(user)
    
    return {
        "id": user.id,
        "is_active": user.is_active,
        "message": f"User {'activated' if user.is_active else 'deactivated'} successfully"
    }