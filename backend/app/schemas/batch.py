from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator


# -- Request schemas --

class BatchCreateRequest(BaseModel):
    """Data for creating a new honey batch (S0)."""
    apiary_data: dict  # Apiary record (location, hive IDs, registration info)
    metadata: dict     # Batch metadata (honey type, expected yield, notes)


class HarvestRequest(BaseModel):
    """Data for recording harvest (S0→S1)."""
    harvest_date: datetime
    quantity_kg: float = Field(gt=0)
    hive_ids: list[str] = Field(min_length=1)
    gps_lat: Optional[float] = Field(default=None, ge=-90, le=90)
    gps_lon: Optional[float] = Field(default=None, ge=-180, le=180)
    notes: Optional[str] = None


class ProcessingRequest(BaseModel):
    """Data for recording processing (S1→S2)."""
    extraction_method: str = Field(min_length=1)
    moisture_content: Optional[float] = Field(default=None, ge=0, le=100)
    handling_notes: Optional[str] = None


class LabResults(BaseModel):
    """Structured lab test results. Extra fields permitted for lab-specific data."""
    model_config = ConfigDict(extra="allow")

    moisture_pct: float = Field(ge=0, le=100)
    hmf_mg_per_kg: float = Field(ge=0)
    diastase_activity: float = Field(ge=0)
    passed: bool


class LabVerifyRequest(BaseModel):
    """Data for anchoring lab proof (S2→S3). Oracle-only."""
    lab_results: LabResults
    verifier_name: str = Field(min_length=1)
    file_hash: Optional[str] = None


class PackagingRequest(BaseModel):
    """Data for recording packaging (S3→S4)."""
    unit_count: int = Field(ge=1)
    jar_ids: list[str] = Field(min_length=1)
    qr_codes: list[str] = Field(min_length=1)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _check_count_consistency(self) -> "PackagingRequest":
        if len(self.jar_ids) != self.unit_count:
            raise ValueError(
                f"jar_ids length ({len(self.jar_ids)}) must equal unit_count ({self.unit_count})"
            )
        if len(self.qr_codes) != self.unit_count:
            raise ValueError(
                f"qr_codes length ({len(self.qr_codes)}) must equal unit_count ({self.unit_count})"
            )
        return self


class DistributionRequest(BaseModel):
    """Data for recording distribution (S4→S5, terminal)."""
    retailer_name: str = Field(min_length=1)
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
