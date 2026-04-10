from sqlalchemy import Column, Integer, String, Boolean, ForeignKey  # type: ignore
from sqlalchemy.orm import relationship # type: ignore                                                                                                 
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    username = Column(String, unique=True, nullable=False)

    email = Column(String, unique=True, nullable=False)
    phone = Column(String, unique=True, nullable=False)

    password = Column(String, nullable=False)

    role = Column(String, nullable=False)  
    # super_admin, admin, onboarding_officer, etc
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True) 

    creator = relationship("User", remote_side=[id])