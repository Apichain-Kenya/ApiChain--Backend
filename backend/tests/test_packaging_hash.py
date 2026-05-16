"""Unit tests for `_verify_packaging_hash` — Sprint 5 packaging stage."""

from types import SimpleNamespace

from app.routers.batch import _verify_packaging_hash, _packaging_record_canonical_payload
from app.services.blockchain import BlockchainService


def _row(**overrides) -> SimpleNamespace:
    base = dict(
        batch_id=3,
        unit_count=3,
        jar_ids=["J-01", "J-02", "J-03"],
        qr_codes=["QR-01", "QR-02", "QR-03"],
        notes="500g glass jars",
        packaging_proof_hash=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _hash_of(row) -> str:
    return "0x" + BlockchainService.compute_data_hash(
        _packaging_record_canonical_payload(row)
    ).hex()


def test_three_way_match_when_chain_db_and_recomputed_agree():
    row = _row()
    h = _hash_of(row)
    row.packaging_proof_hash = h

    result = _verify_packaging_hash(row, h)

    assert result["match"] is True
    assert result["db_hash"] == result["chain_hash"] == result["recomputed_hash"] == h


def test_tampering_after_persisted_hash_breaks_match():
    row = _row()
    persisted_hash = _hash_of(row)
    row.packaging_proof_hash = persisted_hash

    row.jar_ids = ["J-01", "J-02", "J-99"]

    result = _verify_packaging_hash(row, persisted_hash)

    assert result["match"] is False
    assert result["recomputed_hash"] != result["db_hash"]


def test_zero_chain_hash_never_matches():
    row = _row()
    h = _hash_of(row)
    row.packaging_proof_hash = h

    zero = "0x" + ("00" * 32)
    result = _verify_packaging_hash(row, zero)

    assert result["match"] is False
    assert result["chain_hash"] == zero
