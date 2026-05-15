from sqlalchemy import (
    Column,
    Integer,
    Float,
    DateTime,
    ForeignKey,
    String,
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.database import Base


class EnvironmentalData(Base):
    __tablename__ = "environmental_data"

    id = Column(Integer, primary_key=True, index=True)

    batch_id = Column(
        Integer,
        ForeignKey("honey_batches.id"),
        nullable=False,
        unique=True
    )

    temperature = Column(Float, nullable=True)

    humidity = Column(Float, nullable=True)

    rainfall = Column(Float, nullable=True)

    wind_speed = Column(Float, nullable=True)

    pressure = Column(Float, nullable=True)

    cloud_cover = Column(Float, nullable=True)

    weather_source = Column(String, nullable=True)

    recorded_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc)
    )

    batch = relationship(
        "HoneyBatch",
        back_populates="environmental_data"
    )