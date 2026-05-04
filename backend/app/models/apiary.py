from sqlalchemy import Column, Integer, Float, ForeignKey, String
from sqlalchemy.orm import relationship
from geoalchemy2 import Geography
from app.database import Base

class ApiaryLocation(Base):
    __tablename__ = "apiary_locations"

    id = Column(Integer, primary_key=True, index=True)

    latitude = Column(Float, nullable=False, index=True)
    longitude = Column(Float, nullable=False, index=True)

    location = Column(Geography(geometry_type="POINT", srid=4326), nullable=False)

    altitude = Column(Float, nullable=True)


    vegetation_type = Column(String, nullable=True)

    hive_count = Column(Integer, nullable=True)

    farmer_id = Column(Integer, ForeignKey("farmers.id"), nullable=False)

    farmer = relationship("Farmer", back_populates="apiaries")
    honey_batches = relationship("HoneyBatch", back_populates="apiary")