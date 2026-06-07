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

    # Sprint 13: GeoAI authenticity, anchored inside the lab proof pre-image.
    predicted_moisture = Column(Float, nullable=True)
    predicted_sugar = Column(Float, nullable=True)
    predicted_hmf = Column(Float, nullable=True)
    authenticity_score = Column(Float, nullable=True)
    validation_status = Column(String, nullable=True)   # verified|suspicious|flagged
    explanation = Column(String, nullable=True)

    laboratory_name = Column(String, nullable=True)

    analyst_name = Column(String, nullable=True)

    certificate_number = Column(String, nullable=True)

    notes = Column(String, nullable=True)

    tested_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc)
    )

    # Hash that was anchored on chain via `anchorLabProof(batchId, proofHash)`.
    # Stored here so the QR-verification phase can: (a) re-hash the persisted
    # row and confirm it matches this value, and (b) compare this value against
    # the chain's `getBatch.labProofHash`. Hex string with 0x prefix.
    lab_proof_hash = Column(String, nullable=True, index=True)

    batch = relationship(
        "HoneyBatch",
        back_populates="lab_result"
    )