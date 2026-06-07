from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.database import Base


class PackagingRecord(Base):
    """Persisted pre-image of the on-chain `packagingHash` anchored at S4."""

    __tablename__ = "packaging_records"

    id = Column(Integer, primary_key=True, index=True)

    batch_id = Column(
        Integer,
        ForeignKey("honey_batches.id"),
        nullable=False,
        unique=True,
    )

    unit_count = Column(Integer, nullable=False)
    jar_ids = Column(JSON, nullable=False)
    notes = Column(String, nullable=True)

    recorded_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
    )

    packaging_proof_hash = Column(String, nullable=True, index=True)

    batch = relationship("HoneyBatch", back_populates="packaging_record")
