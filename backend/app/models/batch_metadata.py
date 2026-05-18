from sqlalchemy import (
    Column,
    Integer,
    Numeric,
    String,
    Date,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.database import Base


class BatchMetadata(Base):
    """Persisted pre-image of the on-chain `metadataHash` anchored at S0.

    Sprint 8 closes the last verifiability gap. With this row, every chain
    hash in the six-stage lifecycle is recomputable from a single normalized
    DB row, so `/verify` can three-way-compare (db_hash / chain_hash /
    recomputed_hash) for metadata too.

    Enums (`honey_type`, `apiary_management_method`) are validated at the
    Pydantic layer rather than the DB layer so the team can amend the
    allowed-values list with a single edit in `app/schemas/batch.py` —
    no PostgreSQL ENUM migration needed.

    `notes` is intentionally excluded from the canonical payload (and thus
    the hash). It is persisted only so `/verify` can display farmer notes;
    correcting a typo in notes must not invalidate chain-anchored history.
    """

    __tablename__ = "batch_metadata"

    id = Column(Integer, primary_key=True, index=True)

    batch_id = Column(
        Integer,
        ForeignKey("honey_batches.id"),
        nullable=False,
        unique=True,
    )

    honey_type = Column(String, nullable=False)
    expected_yield_kg = Column(Numeric(8, 2), nullable=False)
    harvest_window_start = Column(Date, nullable=False)
    harvest_window_end = Column(Date, nullable=False)
    apiary_management_method = Column(String, nullable=False)

    notes = Column(String, nullable=True)

    recorded_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    metadata_proof_hash = Column(String, nullable=True, index=True)

    batch = relationship("HoneyBatch", back_populates="metadata_record")
