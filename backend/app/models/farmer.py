from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from geoalchemy2 import Geography   # type: ignore
from sqlalchemy.orm import relationship  # type: ignore
from sqlalchemy.sql import func
from app.database import Base
from datetime import datetime
from app.models.apiary import ApiaryLocation   

class Farmer(Base):
    __tablename__ = "farmers"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    phone = Column(String, unique=True, nullable=False)
    username = Column(String, unique=True, nullable=True)
    email = Column(String, unique=True, nullable=True)
    password = Column(String, nullable=False)

    is_verified = Column(Boolean, default=False)

    
    location = Column(Geography(geometry_type='POINT', srid=4326), nullable=True)
    address = Column(String, nullable=True)

    number_of_hives = Column(Integer, nullable=True)


    experience = Column(Integer, nullable=True)
    education = Column(String, nullable=True)
    feeding_practice = Column(String, nullable=True)

    wallet_address = Column(String, unique=True, nullable=True)

    verification_status = Column(String, default="pending")
    onboarded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    documents = relationship("Document", back_populates="farmer")
    apiaries = relationship("ApiaryLocation", back_populates="farmer")

    is_active = Column(Boolean, default=True)