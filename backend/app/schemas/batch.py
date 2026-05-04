from typing import Optional
from datetime import datetime
from pydantic import BaseModel


# -- Request schemas --

class BatchCreateRequest(BaseModel):
    """Data for creating a new honey batch (S0)."""
    apiary_data: dict  # Apiary record (location, hive IDs, registration info)
    metadata: dict     # Batch metadata (honey type, expected yield, notes)


class HarvestRequest(BaseModel):
    """Data for recording harvest (S0→S1)."""
    harvest_date: str
    quantity_kg: float
    hive_ids: list[str] = []
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None
    notes: Optional[str] = None


class ProcessingRequest(BaseModel):
    """Data for recording processing (S1→S2)."""
    extraction_method: str
    moisture_content: Optional[float] = None
    handling_notes: Optional[str] = None


class LabVerifyRequest(BaseModel):
    """Data for anchoring lab proof (S2→S3). Oracle-only."""
    lab_results: dict
    verifier_name: str
    file_hash: Optional[str] = None


class PackagingRequest(BaseModel):
    """Data for recording packaging (S3→S4)."""
    unit_count: int
    jar_ids: list[str] = []
    qr_codes: list[str] = []
    notes: Optional[str] = None


class DistributionRequest(BaseModel):
    """Data for recording distribution (S4→S5, terminal)."""
    retailer_name: str
    transport_reference: Optional[str] = None
    handover_notes: Optional[str] = None


# -- Response schemas --

class BatchResponse(BaseModel):
    """Full batch data returned by API."""
    id: int
    blockchain_batch_id: str
    farmer_id: int
    current_state: str
    create_tx_hash: Optional[str] = None
    harvest_tx_hash: Optional[str] = None
    process_tx_hash: Optional[str] = None
    lab_verify_tx_hash: Optional[str] = None
    packaging_tx_hash: Optional[str] = None
    distribution_tx_hash: Optional[str] = None
    created_at: Optional[datetime] = None
    harvested_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    lab_verified_at: Optional[datetime] = None
    packaged_at: Optional[datetime] = None
    distributed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BatchTransitionResponse(BaseModel):
    """Response after a state transition."""
    batch_id: str
    tx_hash: str
    new_state: str
    message: str


class BatchTimelineResponse(BaseModel):
    """Timeline of batch timestamps from blockchain."""
    batch_id: str
    created_at: int
    harvested_at: int
    processed_at: int
    lab_verified_at: int
    packaged_at: int
    distributed_at: int


class BatchHashesResponse(BaseModel):
    """All hash anchors from blockchain."""
    batch_id: str
    apiary_hash: str
    harvest_hash: str
    process_hash: str
    lab_proof_hash: str
    packaging_hash: str
    distribution_hash: str


class BatchVerifyResponse(BaseModel):
    """Public verification response (for QR scan)."""
    batch_id: str
    state: str
    beekeeper: str
    lab_verified: bool
    timeline: BatchTimelineResponse
    hashes: BatchHashesResponse


class SimpleBatchCreateRequest(BaseModel):
    farmer_id: int
    apiary_id: Optional[int] = None
    harvest_date: datetime
    quantity: float
