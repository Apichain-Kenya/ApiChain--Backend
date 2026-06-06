from typing import Optional
from datetime import datetime, date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


# -- Enums (single edit point) -----------------------------------------------
#
# Sprint 8: enums live here, not in the DB, so the team can amend the
# allowed-values list with a one-file edit. The DB column is plain String;
# Pydantic enforces the constraint at the API boundary. Values are lowercase
# ASCII so the canonical hash payload is stable.

class HoneyType(str, Enum):
    ACACIA = "acacia"
    WILDFLOWER = "wildflower"
    EUCALYPTUS = "eucalyptus"
    SUNFLOWER = "sunflower"
    MIXED = "mixed"


class ApiaryManagementMethod(str, Enum):
    ORGANIC = "organic"
    CONVENTIONAL = "conventional"
    REGENERATIVE = "regenerative"


# -- Request schemas --------------------------------------------------------

class BatchMetadataInput(BaseModel):
    """Typed pre-image of the on-chain `metadataHash` (Sprint 8).

    `notes` is intentionally NOT part of the canonical hash payload — see
    `app/models/batch_metadata.py` and `_metadata_record_canonical_payload`
    in `app/routers/batch.py`. Farmers can correct a typo in notes without
    invalidating chain-anchored history.
    """
    honey_type: HoneyType
    expected_yield_kg: Decimal = Field(gt=Decimal("0"), max_digits=8, decimal_places=2)
    harvest_window_start: date
    harvest_window_end: date
    apiary_management_method: ApiaryManagementMethod
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _check_window(self) -> "BatchMetadataInput":
        if self.harvest_window_end < self.harvest_window_start:
            raise ValueError(
                "harvest_window_end must be on or after harvest_window_start"
            )
        return self


class BatchCreateRequest(BaseModel):
    """Data for creating a new honey batch (S0).

    Sprint 6: `apiary_data` (free-form dict) replaced by `apiary_id` pointing at
    a row in `apiary_locations`. The handler snapshots the apiary fields into
    `apiary_records` so the canonical pre-image hash anchored on chain can be
    reproduced verbatim at QR-verification time.

    Sprint 9: `metadata` is now strictly typed (`BatchMetadataInput`). The
    legacy free-form `dict` path accepted in Sprint 8 is removed — requests
    that do not match `BatchMetadataInput` return 422. Persisted in
    `batch_metadata` and three-way verifiable on `/verify`.
    """
    apiary_id: int
    metadata: BatchMetadataInput


class ApiaryLocationCreateRequest(BaseModel):
    """Seed an apiary owned by the authenticated farmer."""
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    altitude: Optional[float] = None
    vegetation_type: Optional[str] = None
    hive_count: Optional[int] = Field(default=None, ge=0)


class ApiaryLocationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    latitude: float
    longitude: float
    altitude: Optional[float] = None
    vegetation_type: Optional[str] = None
    hive_count: Optional[int] = None
    farmer_id: int


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


class LabVerifyRequest(BaseModel):
    """Data for anchoring lab proof (S2→S3). Oracle-signed.

    Fields mirror the `lab_results` table columns so the persisted row is the
    canonical pre-image of the on-chain proof hash. See `app/models/lab_result.py`.
    """
    moisture_content: Optional[float] = Field(default=None, ge=0, le=100)
    sucrose_level: Optional[float] = Field(default=None, ge=0)
    hmf_level: Optional[float] = Field(default=None, ge=0)
    pollen_density: Optional[float] = Field(default=None, ge=0)
    purity_score: Optional[float] = Field(default=None, ge=0, le=100)

    passed_quality_check: bool

    laboratory_name: Optional[str] = None
    analyst_name: Optional[str] = None
    certificate_number: Optional[str] = None
    notes: Optional[str] = None


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


# -- Response schemas -------------------------------------------------------

class BatchResponse(BaseModel):
    """Full batch data returned by API."""
    model_config = ConfigDict(from_attributes=True)

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


class LabResultPublic(BaseModel):
    """Persisted lab_results row exposed by the public verify endpoint."""
    model_config = ConfigDict(from_attributes=True)

    batch_id: int
    moisture_content: Optional[float] = None
    sucrose_level: Optional[float] = None
    hmf_level: Optional[float] = None
    pollen_density: Optional[float] = None
    purity_score: Optional[float] = None
    passed_quality_check: bool
    laboratory_name: Optional[str] = None
    analyst_name: Optional[str] = None
    certificate_number: Optional[str] = None
    notes: Optional[str] = None
    lab_proof_hash: Optional[str] = None
    tested_at: Optional[datetime] = None


class EnvironmentalDataPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    temperature: Optional[float] = None
    humidity: Optional[float] = None
    rainfall: Optional[float] = None
    wind_speed: Optional[float] = None
    pressure: Optional[float] = None
    cloud_cover: Optional[float] = None
    weather_source: Optional[str] = None
    recorded_at: Optional[datetime] = None


class StageHashVerification(BaseModel):
    """Three-way comparison between DB-stored hash, on-chain hash, and a
    freshly-recomputed keccak256 of the persisted row.

    `match` is true only when all three agree and the chain hash is non-zero.
    Shared across all lifecycle stages.
    """
    db_hash: str
    chain_hash: str
    recomputed_hash: str
    match: bool


# Backwards-compat alias from Sprint 4 when only the lab stage had it.
LabHashVerification = StageHashVerification


class VerificationBlock(BaseModel):
    """Per-stage hash verification. Each field is populated only when the
    corresponding `*_records` row exists for the batch (i.e. the stage has
    been executed)."""
    apiary: Optional[StageHashVerification] = None
    metadata: Optional[StageHashVerification] = None
    harvest: Optional[StageHashVerification] = None
    process: Optional[StageHashVerification] = None
    lab: Optional[StageHashVerification] = None
    packaging: Optional[StageHashVerification] = None
    distribution: Optional[StageHashVerification] = None


class ApiaryRecordPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    batch_id: int
    apiary_id: int
    latitude: float
    longitude: float
    altitude: Optional[float] = None
    vegetation_type: Optional[str] = None
    hive_count: Optional[int] = None
    apiary_proof_hash: Optional[str] = None
    recorded_at: Optional[datetime] = None


class BatchMetadataPublic(BaseModel):
    """Persisted `batch_metadata` row exposed by /verify."""
    model_config = ConfigDict(from_attributes=True)

    batch_id: int
    honey_type: str
    expected_yield_kg: Decimal
    harvest_window_start: date
    harvest_window_end: date
    apiary_management_method: str
    notes: Optional[str] = None
    metadata_proof_hash: Optional[str] = None
    recorded_at: Optional[datetime] = None


class HarvestRecordPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    batch_id: int
    harvest_date: Optional[datetime] = None
    quantity_kg: float
    hive_ids: list[str]
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None
    notes: Optional[str] = None
    harvest_proof_hash: Optional[str] = None
    recorded_at: Optional[datetime] = None


class ProcessRecordPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    batch_id: int
    extraction_method: str
    moisture_content: Optional[float] = None
    handling_notes: Optional[str] = None
    process_proof_hash: Optional[str] = None
    recorded_at: Optional[datetime] = None


class PackagingRecordPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    batch_id: int
    unit_count: int
    jar_ids: list[str]
    qr_codes: list[str]
    notes: Optional[str] = None
    packaging_proof_hash: Optional[str] = None
    recorded_at: Optional[datetime] = None


class DistributionRecordPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    batch_id: int
    retailer_name: str
    transport_reference: Optional[str] = None
    handover_notes: Optional[str] = None
    distribution_proof_hash: Optional[str] = None
    recorded_at: Optional[datetime] = None


class TxHashes(BaseModel):
    """The 6 anchoring tx hashes from `honey_batches`, so the scan UI can
    deep-link each transition to Etherscan."""
    create_tx: Optional[str] = None
    harvest_tx: Optional[str] = None
    process_tx: Optional[str] = None
    lab_tx: Optional[str] = None
    package_tx: Optional[str] = None
    distribute_tx: Optional[str] = None


class AuthenticityPublic(BaseModel):
    """Consumer-facing GeoAI authenticity summary on /verify. Joined from
    validation_results by batch.id. Chain-neutral (no hashed field)."""
    available: bool
    status: Optional[str] = None   # "verified" | "suspicious" | "flagged"
    score: Optional[float] = None  # authenticity_score (0..1)
    model_config = ConfigDict(from_attributes=True)


class BatchVerifyResponse(BaseModel):
    """Public verification response (for QR scan)."""
    batch_id: str
    state: str
    beekeeper: str
    lab_verified: bool
    timeline: BatchTimelineResponse
    hashes: BatchHashesResponse
    lab_result: Optional[LabResultPublic] = None
    apiary_record: Optional[ApiaryRecordPublic] = None
    batch_metadata: Optional[BatchMetadataPublic] = None
    harvest_record: Optional[HarvestRecordPublic] = None
    process_record: Optional[ProcessRecordPublic] = None
    packaging_record: Optional[PackagingRecordPublic] = None
    distribution_record: Optional[DistributionRecordPublic] = None
    environmental_data: Optional[EnvironmentalDataPublic] = None
    verification: Optional[VerificationBlock] = None
    tx_hashes: Optional[TxHashes] = None
    authenticity: Optional[AuthenticityPublic] = None


class SimpleBatchCreateRequest(BaseModel):
    """One-shot batch creation: anchors S0 (CREATED) and S1 (HARVESTED) on chain
    in a single call, then attaches a fresh environmental snapshot.

    The farmer is taken from the JWT, not the request body, so authenticated
    users cannot create batches attributed to other farmers.

    Sprint 9: `metadata` is required and strictly typed. Same persistence +
    hashing path as `POST /batches/`. The Sprint 8 fallback to an inline
    legacy dict is removed.
    """
    apiary_id: int
    harvest_date: datetime
    quantity_kg: float = Field(gt=0)
    hive_ids: list[str] = Field(min_length=1)
    notes: Optional[str] = None
    metadata: BatchMetadataInput
