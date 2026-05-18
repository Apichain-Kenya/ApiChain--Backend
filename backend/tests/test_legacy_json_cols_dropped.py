"""Sprint 7 regression guard: the six legacy *_data JSON columns on
honey_batches were dropped in migration f7012345abcd. If a future change
adds one back, this test fails loud — likely a sign that someone is
re-mirroring a structured row in the wrong place.
"""
from app.models.batch import HoneyBatch


LEGACY_COLS = (
    "apiary_data",
    "harvest_data",
    "process_data",
    "lab_proof_data",
    "packaging_data",
    "distribution_data",
    # Sprint 9: metadata_payload joined its siblings now that batch_metadata
    # is canonical (migration c0d1e2f3a4b5).
    "metadata_payload",
)


def test_legacy_json_columns_removed_from_model():
    table_cols = set(HoneyBatch.__table__.columns.keys())
    leaked = sorted(c for c in LEGACY_COLS if c in table_cols)
    assert not leaked, (
        f"Legacy honey_batches JSON mirror columns reappeared: {leaked}. "
        "They were dropped in Sprint 7 (f7012345abcd) and Sprint 9 "
        "(c0d1e2f3a4b5); the structured rows are now canonical."
    )
