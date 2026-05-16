from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    DateTime,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.database import Base


class HarvestRecord(Base):
    """Persisted pre-image of the on-chain `harvestHash` anchored at S1.

    Mirrors `LabResult` (Sprint 3): the row IS the canonical source of the
    keccak256 bytes that were anchored via `recordHarvest(batchId, harvestHash)`.
    `harvest_proof_hash` stores that anchor in hex; `/verify` re-hashes the row
    at scan time and compares against both this column and the chain.
    """

    __tablename__ = "harvest_records"

    id = Column(Integer, primary_key=True, index=True)

    batch_id = Column(
        Integer,
        ForeignKey("honey_batches.id"),
        nullable=False,
        unique=True,
    )

    harvest_date = Column(DateTime, nullable=False)
    quantity_kg = Column(Float, nullable=False)
    hive_ids = Column(JSON, nullable=False)
    gps_lat = Column(Float, nullable=True)
    gps_lon = Column(Float, nullable=True)
    notes = Column(String, nullable=True)

    recorded_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
    )

    harvest_proof_hash = Column(String, nullable=True, index=True)

    batch = relationship("HoneyBatch", back_populates="harvest_record")
