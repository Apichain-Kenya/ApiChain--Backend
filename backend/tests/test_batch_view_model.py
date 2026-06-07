# tests/test_batch_view_model.py
"""Unit tests for build_batch_view — the canonical batch shape the FE trusts.
Pure function over relationship attributes; no DB needed (SimpleNamespace)."""
from types import SimpleNamespace
from app.routers.batch import build_batch_view


def _batch(**o):
    base = dict(
        id=7, blockchain_batch_id="0x" + "ab" * 32, farmer_id=3,
        current_state="HARVESTED", quantity=None,
        create_tx_hash="0xc", harvest_tx_hash="0xh", process_tx_hash=None,
        lab_verify_tx_hash=None, packaging_tx_hash=None, distribution_tx_hash=None,
        created_at=None, harvested_at=None, processed_at=None,
        lab_verified_at=None, packaged_at=None, distributed_at=None,
        harvest_record=SimpleNamespace(quantity_kg=25.5),
        lab_result=None, validation=None,
    )
    base.update(o)
    return SimpleNamespace(**base)


def test_quantity_comes_from_harvest_record_not_batch_column():
    b = _batch(quantity=0, harvest_record=SimpleNamespace(quantity_kg=25.5))
    view = build_batch_view(b)
    assert view["quantity"] == 25.5  # NOT 0 — the bug this fixes


def test_quantity_falls_back_to_batch_column_when_no_harvest_record():
    b = _batch(quantity=12.0, harvest_record=None)
    assert build_batch_view(b)["quantity"] == 12.0


def test_quantity_is_none_when_neither_present():
    b = _batch(quantity=None, harvest_record=None)
    assert build_batch_view(b)["quantity"] is None


def test_authenticity_summary_absent_until_validation_exists():
    b = _batch(validation=None)
    assert build_batch_view(b)["authenticity"] == {"available": False, "status": None, "score": None}


def test_authenticity_summary_present_when_validation_exists():
    b = _batch(validation=SimpleNamespace(validation_status="suspicious", authenticity_score=0.79))
    assert build_batch_view(b)["authenticity"] == {
        "available": True, "status": "suspicious", "score": 0.79,
    }
