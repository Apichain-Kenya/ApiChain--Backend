"""Unit tests for `_verify_metadata_hash` — Sprint 8 mirror of the apiary
pattern. Three cases: three-way match, tamper detection, zero chain hash.

No DB or chain required — `SimpleNamespace` stands in for a `BatchMetadata`
row so the canonical payload helper and three-way verification can be
exercised in pure-unit form.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.routers.batch import (
    _verify_metadata_hash,
    _metadata_record_canonical_payload,
)
from app.services.blockchain import BlockchainService


def _row(**overrides) -> SimpleNamespace:
    base = dict(
        batch_id=1,
        honey_type="acacia",
        expected_yield_kg=Decimal("50.00"),
        harvest_window_start=date(2026, 5, 1),
        harvest_window_end=date(2026, 5, 31),
        apiary_management_method="organic",
        notes="harvest planned for end of season",
        recorded_at=datetime(2026, 5, 18, 12, 0, 0, tzinfo=timezone.utc),
        metadata_proof_hash=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _hash_of(row) -> str:
    return "0x" + BlockchainService.compute_data_hash(
        _metadata_record_canonical_payload(row)
    ).hex()


def test_three_way_match_when_chain_db_and_recomputed_agree():
    row = _row()
    h = _hash_of(row)
    row.metadata_proof_hash = h

    result = _verify_metadata_hash(row, h)

    assert result["match"] is True
    assert result["db_hash"] == result["chain_hash"] == result["recomputed_hash"] == h


def test_tampering_after_persisted_hash_breaks_match():
    row = _row()
    persisted_hash = _hash_of(row)
    row.metadata_proof_hash = persisted_hash

    # Mutate a hashed field — should break the recomputation
    row.honey_type = "wildflower"

    result = _verify_metadata_hash(row, persisted_hash)

    assert result["match"] is False
    assert result["recomputed_hash"] != result["db_hash"]
    assert result["db_hash"] == result["chain_hash"] == persisted_hash


def test_zero_chain_hash_never_matches():
    row = _row()
    h = _hash_of(row)
    row.metadata_proof_hash = h

    zero = "0x" + ("00" * 32)
    result = _verify_metadata_hash(row, zero)

    assert result["match"] is False
    assert result["chain_hash"] == zero
    assert result["recomputed_hash"] == result["db_hash"] == h
