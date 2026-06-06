"""
Unit tests for `_verify_lab_hash` — the three-way match primitive that
`/batches/{id}/verify` uses to decide whether to show the green
"Blockchain Verified" badge.

Verifies:
1. Match case: persisted row reproduces the stored DB hash AND matches the
   on-chain hash → match=True.
2. Tampering: a column mutated after the row was hashed → recomputed differs
   from db_hash → match=False.
3. Zero on-chain hash: even with db==recomputed, match=False (lab was never
   anchored on chain).

The handler-level join is exercised end-to-end by `scripts/e2e_lifecycle.py`,
which asserts the new `verification.lab.match` and `tx_hashes.lab_tx` fields
against a live Hardhat run.
"""

from types import SimpleNamespace

from app.routers.batch import _verify_lab_hash, _lab_result_canonical_payload
from app.services.blockchain import BlockchainService


def _row(**overrides) -> SimpleNamespace:
    """Build a LabResult-shaped stand-in. `_lab_result_canonical_payload`
    reads attributes only, so a SimpleNamespace works without touching the DB."""
    base = dict(
        batch_id=1,
        moisture_content=18.2,
        sucrose_level=2.1,
        hmf_level=10.0,
        pollen_density=42.0,
        predicted_moisture=19.12, predicted_sugar=75.5, predicted_hmf=28.4,
        authenticity_score=0.79, validation_status="suspicious",
        explanation="Verdict: suspicious.",
        laboratory_name="Lab Co",
        analyst_name="A. Tester",
        certificate_number="CERT-001",
        notes="ok",
        lab_proof_hash=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _hash_of(row) -> str:
    return "0x" + BlockchainService.compute_data_hash(
        _lab_result_canonical_payload(row)
    ).hex()


def test_three_way_match_when_chain_db_and_recomputed_agree():
    row = _row()
    h = _hash_of(row)
    row.lab_proof_hash = h

    result = _verify_lab_hash(row, h)

    assert result["match"] is True
    assert result["db_hash"] == result["chain_hash"] == result["recomputed_hash"] == h


def test_tampering_after_persisted_hash_breaks_match():
    row = _row()
    persisted_hash = _hash_of(row)
    row.lab_proof_hash = persisted_hash

    # Someone edits the row after the hash was anchored. The recomputed hash
    # must now diverge from the stored db_hash, so match=False.
    row.moisture_content = 99.9

    result = _verify_lab_hash(row, persisted_hash)

    assert result["match"] is False
    assert result["recomputed_hash"] != result["db_hash"]
    assert result["db_hash"] == result["chain_hash"] == persisted_hash


def test_zero_chain_hash_never_matches():
    """If the lab proof was never anchored on chain, the registry returns
    bytes32(0). A green badge in that state would be a lie."""
    row = _row()
    h = _hash_of(row)
    row.lab_proof_hash = h

    zero = "0x" + ("00" * 32)
    result = _verify_lab_hash(row, zero)

    assert result["match"] is False
    assert result["chain_hash"] == zero
    assert result["recomputed_hash"] == result["db_hash"] == h
