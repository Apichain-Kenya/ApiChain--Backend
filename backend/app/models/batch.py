from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class HoneyBatch(Base):
    __tablename__ = "honey_batches"

    id = Column(Integer, primary_key=True, index=True)

    # Blockchain identity
    blockchain_batch_id = Column(String, unique=True, index=True, nullable=False)

    #  Relationships
    farmer_id = Column(Integer, ForeignKey("farmers.id"), nullable=False)
    apiary_id = Column(Integer, ForeignKey("apiary_locations.id"), nullable=True)

    farmer = relationship("Farmer")
    apiary = relationship("ApiaryLocation", back_populates="honey_batches")

    #  Core batch data (your original system)
    harvest_date = Column(DateTime, nullable=True)
    quantity = Column(Float, nullable=True)
    # CREATED → HARVESTED → PROCESSED → LAB_VERIFIED → PACKAGED → DISTRIBUTED

    # Sprint 8 replaced the free-form metadata_payload JSON mirror with the
    # structured `batch_metadata` row (see relationship below); Sprint 9
    # dropped the legacy column in migration c0d1e2f3a4b5.

    # State mirror (blockchain)
    current_state = Column(String, default="CREATED", nullable=False)

    #  Transaction hashes
    create_tx_hash = Column(String)
    harvest_tx_hash = Column(String)
    process_tx_hash = Column(String)
    lab_verify_tx_hash = Column(String)
    packaging_tx_hash = Column(String)
    distribution_tx_hash = Column(String)

    # Lifecycle timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    harvested_at = Column(DateTime)
    processed_at = Column(DateTime)
    lab_verified_at = Column(DateTime)
    packaged_at = Column(DateTime)
    distributed_at = Column(DateTime)

    lab_result = relationship(
        "LabResult",
        back_populates="batch",
        uselist=False,
        cascade="all, delete-orphan",
    )

    environmental_data = relationship(
        "EnvironmentalData",
        back_populates="batch",
        uselist=False,
        cascade="all, delete-orphan",
    )

    apiary_record = relationship(
        "ApiaryRecord",
        back_populates="batch",
        uselist=False,
        cascade="all, delete-orphan",
    )

    harvest_record = relationship(
        "HarvestRecord",
        back_populates="batch",
        uselist=False,
        cascade="all, delete-orphan",
    )

    process_record = relationship(
        "ProcessRecord",
        back_populates="batch",
        uselist=False,
        cascade="all, delete-orphan",
    )

    packaging_record = relationship(
        "PackagingRecord",
        back_populates="batch",
        uselist=False,
        cascade="all, delete-orphan",
    )

    distribution_record = relationship(
        "DistributionRecord",
        back_populates="batch",
        uselist=False,
        cascade="all, delete-orphan",
    )

    metadata_record = relationship(
        "BatchMetadata",
        back_populates="batch",
        uselist=False,
        cascade="all, delete-orphan",
    )
    #prediction = relationship("PredictionResult", back_populates="batch", uselist=False)
    #validation = relationship("ValidationResult", back_populates="batch", uselist=False)