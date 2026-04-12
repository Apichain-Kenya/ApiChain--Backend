from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class HoneyBatch(Base):
    __tablename__ = "honey_batches"

    id = Column(Integer, primary_key=True, index=True)
    blockchain_batch_id = Column(String, unique=True, index=True, nullable=False)

    # The farmer who created this batch
    farmer_id = Column(Integer, ForeignKey("farmers.id"), nullable=False)
    farmer = relationship("Farmer")

    # Off-chain data (raw payloads whose keccak256 hashes go on-chain)
    apiary_data = Column(JSON, nullable=True)
    metadata_payload = Column(JSON, nullable=True)
    harvest_data = Column(JSON, nullable=True)
    process_data = Column(JSON, nullable=True)
    lab_proof_data = Column(JSON, nullable=True)
    packaging_data = Column(JSON, nullable=True)
    distribution_data = Column(JSON, nullable=True)

    # Current state mirrored from blockchain (for fast DB queries)
    current_state = Column(String, default="CREATED", nullable=False)

    # Transaction hashes for each state transition
    create_tx_hash = Column(String, nullable=True)
    harvest_tx_hash = Column(String, nullable=True)
    process_tx_hash = Column(String, nullable=True)
    lab_verify_tx_hash = Column(String, nullable=True)
    packaging_tx_hash = Column(String, nullable=True)
    distribution_tx_hash = Column(String, nullable=True)

    # Timestamps (mirrored from chain via tx receipts)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    harvested_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    lab_verified_at = Column(DateTime, nullable=True)
    packaged_at = Column(DateTime, nullable=True)
    distributed_at = Column(DateTime, nullable=True)
