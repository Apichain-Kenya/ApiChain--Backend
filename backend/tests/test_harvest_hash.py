"""Unit tests for `_verify_harvest_hash` — Sprint 5 mirror of the lab pattern.

Same three cases as test_verify_endpoint.py: match, tampering, zero chain hash.
No DB or chain required — SimpleNamespace stands in for a HarvestRecord row.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.routers.batch import _verify_harvest_hash, _harvest_record_canonical_payload
from app.services.blockchain import BlockchainService


def _row(**overrides) -> SimpleNamespace:
    base = dict(
        batch_id=1,
        harvest_date=datetime(2026, 5, 16, 9, 0, 0, tzinfo=timezone.utc),
        quantity_kg=12.5,
        hive_ids=["H-01", "H-02"],
        gps_lat=-1.2921,
        gps_lon=36.8219,
        notes="morning harvest",
        harvest_proof_hash=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _hash_of(row) -> str:
    return "0x" + BlockchainService.compute_data_hash(
        _harvest_record_canonical_payload(row)
    ).hex()


def test_three_way_match_when_chain_db_and_recomputed_agree():
    row = _row()
    h = _hash_of(row)
    row.harvest_proof_hash = h

    result = _verify_harvest_hash(row, h)

    assert result["match"] is True
    assert result["db_hash"] == result["chain_hash"] == result["recomputed_hash"] == h


def test_tampering_after_persisted_hash_breaks_match():
    row = _row()
    persisted_hash = _hash_of(row)
    row.harvest_proof_hash = persisted_hash

    row.quantity_kg = 999.0

    result = _verify_harvest_hash(row, persisted_hash)

    assert result["match"] is False
    assert result["recomputed_hash"] != result["db_hash"]
    assert result["db_hash"] == result["chain_hash"] == persisted_hash


def test_zero_chain_hash_never_matches():
    row = _row()
    h = _hash_of(row)
    row.harvest_proof_hash = h

    zero = "0x" + ("00" * 32)
    result = _verify_harvest_hash(row, zero)

    assert result["match"] is False
    assert result["chain_hash"] == zero
    assert result["recomputed_hash"] == result["db_hash"] == h
