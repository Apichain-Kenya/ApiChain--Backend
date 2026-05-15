from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    DateTime,
    ForeignKey,
    Boolean,
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.database import Base


class LabResult(Base):
    __tablename__ = "lab_results"

    id = Column(Integer, primary_key=True, index=True)

    batch_id = Column(
        Integer,
        ForeignKey("honey_batches.id"),
        nullable=False,
        unique=True
    )

    moisture_content = Column(Float, nullable=True)

    sucrose_level = Column(Float, nullable=True)

    hmf_level = Column(Float, nullable=True)

    pollen_density = Column(Float, nullable=True)

    purity_score = Column(Float, nullable=True)

    passed_quality_check = Column(Boolean, default=False)

    laboratory_name = Column(String, nullable=True)

    analyst_name = Column(String, nullable=True)

    certificate_number = Column(String, nullable=True)

    notes = Column(String, nullable=True)

    tested_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc)
    )

    batch = relationship(
        "HoneyBatch",
        back_populates="lab_result"
    )