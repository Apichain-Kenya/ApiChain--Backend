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


class ApiaryRecord(Base):
    """Persisted pre-image of the on-chain `apiaryHash` anchored at S0.

    Sprint 6 closes the symmetry gap left by Sprint 5: every mutating stage
    now has a structured row whose canonical payload is hashed and anchored,
    so `/verify` can three-way-compare db_hash / chain_hash / recomputed_hash
    for the apiary side of S0 too. The snapshotted columns deliberately
    duplicate fields from `apiary_locations` — the hash must remain
    reproducible even if the underlying apiary row is later edited.
    """

    __tablename__ = "apiary_records"

    id = Column(Integer, primary_key=True, index=True)

    batch_id = Column(
        Integer,
        ForeignKey("honey_batches.id"),
        nullable=False,
        unique=True,
    )

    apiary_id = Column(
        Integer,
        ForeignKey("apiary_locations.id"),
        nullable=False,
    )

    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    altitude = Column(Float, nullable=True)
    vegetation_type = Column(String, nullable=True)
    hive_count = Column(Integer, nullable=True)

    recorded_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
    )

    apiary_proof_hash = Column(String, nullable=True, index=True)

    batch = relationship("HoneyBatch", back_populates="apiary_record")
