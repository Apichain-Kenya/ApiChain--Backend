"""
Unified authentication dependencies.

Provides get_current_user() and require_roles() for all endpoints.
Queries both User (employees) and Farmer tables based on JWT role.
Returns a dict: {"user": <model instance>, "role": str, "user_id": int}
so batch.py and other routers have a consistent interface.
"""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from jose import jwt, JWTError  # type: ignore
from sqlalchemy.orm import Session  # type: ignore

from app.database import get_db
from app.models.user import User
from app.models.farmer import Farmer
from app.auth import SECRET_KEY, ALGORITHM

security = HTTPBearer()


def get_current_user(
    token=Depends(security), db: Session = Depends(get_db)
) -> dict:
    """
    Decode JWT and return the authenticated user from the correct table.

    - If role == "farmer", queries the Farmer table.
    - Otherwise, queries the User table (all employee roles).

    Returns:
        {"user": Farmer|User, "role": str, "user_id": int}
    """
    try:
        payload = jwt.decode(
            token.credentials, SECRET_KEY, algorithms=[ALGORITHM]
        )
        user_id = int(payload.get("sub"))
        role: str = payload.get("role")

        if user_id is None or role is None:
            raise HTTPException(status_code=401, detail="Malformed token")

    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalid or expired")

    # Route to correct table based on role
    if role == "farmer":
        user = db.query(Farmer).filter(Farmer.id == user_id).first()
    else:
        user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {"user": user, "role": role, "user_id": user_id}


def require_roles(allowed_roles: list):
    """
    Factory that returns a dependency requiring the user to have
    one of the specified roles.

    Usage:
        current_user = Depends(require_roles(["farmer", "harvest_processor"]))
    """
    def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Requires one of: {allowed_roles}",
            )
        return current_user

    return role_checker
