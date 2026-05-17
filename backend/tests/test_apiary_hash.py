"""Unit tests for `_verify_apiary_hash` — Sprint 6 mirror of the harvest pattern.

Three cases identical in shape to the other stage tests: three-way match,
tamper detection, zero chain hash. No DB or chain required — `SimpleNamespace`
stands in for an `ApiaryRecord` row.
"""

from types import SimpleNamespace

from app.routers.batch import _verify_apiary_hash, _apiary_record_canonical_payload
from app.services.blockchain import BlockchainService


def _row(**overrides) -> SimpleNamespace:
    base = dict(
        batch_id=1,
        apiary_id=42,
        latitude=-1.2921,
        longitude=36.8219,
        altitude=1795.0,
        vegetation_type="acacia woodland",
        hive_count=18,
        apiary_proof_hash=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _hash_of(row) -> str:
    return "0x" + BlockchainService.compute_data_hash(
        _apiary_record_canonical_payload(row)
    ).hex()


def test_three_way_match_when_chain_db_and_recomputed_agree():
    row = _row()
    h = _hash_of(row)
    row.apiary_proof_hash = h

    result = _verify_apiary_hash(row, h)

    assert result["match"] is True
    assert result["db_hash"] == result["chain_hash"] == result["recomputed_hash"] == h


def test_tampering_after_persisted_hash_breaks_match():
    row = _row()
    persisted_hash = _hash_of(row)
    row.apiary_proof_hash = persisted_hash

    row.latitude = 0.0

    result = _verify_apiary_hash(row, persisted_hash)

    assert result["match"] is False
    assert result["recomputed_hash"] != result["db_hash"]
    assert result["db_hash"] == result["chain_hash"] == persisted_hash


def test_zero_chain_hash_never_matches():
    row = _row()
    h = _hash_of(row)
    row.apiary_proof_hash = h

    zero = "0x" + ("00" * 32)
    result = _verify_apiary_hash(row, zero)

    assert result["match"] is False
    assert result["chain_hash"] == zero
    assert result["recomputed_hash"] == result["db_hash"] == h
