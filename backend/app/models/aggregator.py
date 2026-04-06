from sqlalchemy import Column, Integer, String, Boolean
from geoalchemy2 import Geography
from sqlalchemy.orm import relationship
from app.database import Base

class Aggregator(Base):
    __tablename__ = "aggregators"

    id = Column(Integer, primary_key=True, index=True)
    business_name = Column(String, nullable=False)
    phone = Column(String, unique=True, nullable=False)
    email = Column(String, nullable=False)
    password = Column(String, nullable=False)

    is_verified = Column(Boolean, default=False)

    # PostGIS location: center of operational region
    region_location = Column(Geography(geometry_type='POINT', srid=4326), nullable=True)
    farmers_count = Column(Integer, nullable=True)
    # FIX: Added missing 'address' column. The router (routers/aggregator.py:65) sets
    # agg.address = data.address, which throws AttributeError without this column.
    address = Column(String, nullable=True)

    verification_status = Column(String, default="pending")
    documents = relationship("Document", back_populates="aggregator")