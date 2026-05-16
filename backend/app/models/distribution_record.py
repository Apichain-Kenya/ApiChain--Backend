from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.database import Base


class DistributionRecord(Base):
    """Persisted pre-image of the on-chain `distributionHash` anchored at S5
    (terminal state)."""

    __tablename__ = "distribution_records"

    id = Column(Integer, primary_key=True, index=True)

    batch_id = Column(
        Integer,
        ForeignKey("honey_batches.id"),
        nullable=False,
        unique=True,
    )

    retailer_name = Column(String, nullable=False)
    transport_reference = Column(String, nullable=True)
    handover_notes = Column(String, nullable=True)

    recorded_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
    )

    distribution_proof_hash = Column(String, nullable=True, index=True)

    batch = relationship("HoneyBatch", back_populates="distribution_record")
