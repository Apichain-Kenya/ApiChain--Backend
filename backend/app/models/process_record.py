from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.database import Base


class ProcessRecord(Base):
    """Persisted pre-image of the on-chain `processHash` anchored at S2."""

    __tablename__ = "process_records"

    id = Column(Integer, primary_key=True, index=True)

    batch_id = Column(
        Integer,
        ForeignKey("honey_batches.id"),
        nullable=False,
        unique=True,
    )

    extraction_method = Column(String, nullable=False)
    moisture_content = Column(Float, nullable=True)
    handling_notes = Column(String, nullable=True)

    recorded_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
    )

    process_proof_hash = Column(String, nullable=True, index=True)

    batch = relationship("HoneyBatch", back_populates="process_record")
