"""Lock the Sprint 13 lab pre-image. The new ML-derived numeric fields must hash
identically whether they arrive as float or Decimal (a Numeric column or psycopg
Decimal roundtrip must not silently break the anchor). Mirrors the metadata-hash
Decimal/float parity guard."""
from decimal import Decimal
from types import SimpleNamespace
from app.routers.batch import _lab_result_canonical_payload, _q4
from app.services.blockchain import BlockchainService


def _row(**o):
    base = dict(
        batch_id=1, moisture_content=19.0, sucrose_level=4.0, hmf_level=28.0,
        pollen_density=30000.0, predicted_moisture=19.1234, predicted_sugar=75.5,
        predicted_hmf=28.4321, authenticity_score=0.79, validation_status="suspicious",
        explanation="Origin region detected: central_highlands. Verdict: suspicious.",
        laboratory_name="KEBS", analyst_name="A", certificate_number="C-1", notes="ok",
        lab_proof_hash=None,
    )
    base.update(o)
    return SimpleNamespace(**base)


def _h(row):
    return BlockchainService.compute_data_hash(_lab_result_canonical_payload(row)).hex()


def test_predicted_and_score_float_decimal_parity():
    f = _row(predicted_moisture=19.1234, authenticity_score=0.79)
    d = _row(predicted_moisture=Decimal("19.1234"), authenticity_score=Decimal("0.7900"))
    assert _h(f) == _h(d)


def test_q4_quantizes_consistently():
    assert _q4(0.79) == _q4(Decimal("0.7900")) == "0.7900"
    assert _q4(None) is None


def test_dropped_fields_are_not_in_payload():
    payload = _lab_result_canonical_payload(_row())
    assert "purity_score" not in payload
    assert "passed_quality_check" not in payload
    assert {"predicted_moisture", "authenticity_score", "validation_status",
            "explanation"} <= set(payload)
