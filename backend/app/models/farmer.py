from sqlalchemy import Column, Integer, String, Boolean
from geoalchemy2 import Geography  # PostGIS type
from sqlalchemy.orm import relationship
from app.database import Base

class Farmer(Base):
    __tablename__ = "farmers"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    phone = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=True) 
    password = Column(String, nullable=False)

    is_verified = Column(Boolean, default=False)

    # PostGIS location: POINT (longitude, latitude)
    location = Column(Geography(geometry_type='POINT', srid=4326), nullable=True)
    address = Column(String, nullable=True)
    number_of_hives = Column(Integer, nullable=True)

    verification_status = Column(String, default="pending")
    documents = relationship("Document", back_populates="farmer")