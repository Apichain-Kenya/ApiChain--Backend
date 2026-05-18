"""Determinism guards for `_metadata_record_canonical_payload`.

These tests lock in the explicit canonical-form rules from the Sprint 8
metadata-schema proposal so a future contributor can't silently break hash
reproducibility by switching to a float / unsorted dict / mixed-case enum.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.routers.batch import _metadata_record_canonical_payload
from app.services.blockchain import BlockchainService


def _row(**overrides) -> SimpleNamespace:
    base = dict(
        batch_id=1,
        honey_type="acacia",
        expected_yield_kg=Decimal("50.00"),
        harvest_window_start=date(2026, 5, 1),
        harvest_window_end=date(2026, 5, 31),
        apiary_management_method="organic",
        notes="some farmer notes",
        recorded_at=datetime(2026, 5, 18, 12, 0, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_notes_excluded_from_canonical_payload():
    payload = _metadata_record_canonical_payload(_row(notes="anything goes here"))
    assert "notes" not in payload


def test_yield_decimal_and_float_produce_same_hash():
    """50, 50.0, and Decimal('50.00') must all hash identically — the canonical
    form normalises to the fixed-precision string '50.00'."""
    h_decimal = BlockchainService.compute_data_hash(
        _metadata_record_canonical_payload(_row(expected_yield_kg=Decimal("50.00")))
    )
    h_float = BlockchainService.compute_data_hash(
        _metadata_record_canonical_payload(_row(expected_yield_kg=50.0))
    )
    h_int = BlockchainService.compute_data_hash(
        _metadata_record_canonical_payload(_row(expected_yield_kg=50))
    )
    assert h_decimal == h_float == h_int


def test_dates_serialize_as_iso_yyyy_mm_dd():
    payload = _metadata_record_canonical_payload(_row())
    assert payload["harvest_window_start"] == "2026-05-01"
    assert payload["harvest_window_end"] == "2026-05-31"


def test_enum_values_are_lowercased():
    """Even if the row was constructed with a mixed-case enum value (e.g.
    from a legacy import), the canonical payload normalises to lowercase."""
    payload = _metadata_record_canonical_payload(
        _row(honey_type="Acacia", apiary_management_method="Organic")
    )
    assert payload["honey_type"] == "acacia"
    assert payload["apiary_management_method"] == "organic"


def test_hash_invariant_under_compute_data_hash_sort_keys():
    """The hash is `compute_data_hash(canonical_payload)` and
    `compute_data_hash` sorts keys before serializing. Two canonical payloads
    that differ only in field insertion order must hash to the same bytes."""
    row = _row()
    payload_a = _metadata_record_canonical_payload(row)
    payload_b = {k: payload_a[k] for k in sorted(payload_a.keys(), reverse=True)}

    assert BlockchainService.compute_data_hash(payload_a) == \
        BlockchainService.compute_data_hash(payload_b)


def test_recorded_at_tz_aware_and_naive_match():
    """A tz-aware UTC datetime and its tz-naive counterpart must produce the
    same canonical string — protects the hash against the
    TIMESTAMP-without-timezone DB round-trip class of bug."""
    aware = datetime(2026, 5, 18, 12, 0, 0, tzinfo=timezone.utc)
    naive = datetime(2026, 5, 18, 12, 0, 0)

    payload_aware = _metadata_record_canonical_payload(_row(recorded_at=aware))
    payload_naive = _metadata_record_canonical_payload(_row(recorded_at=naive))

    assert payload_aware["recorded_at"] == payload_naive["recorded_at"]
