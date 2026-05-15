"""
Regression tests for the deterministic-hash invariant.

`compute_data_hash()` MUST be deterministic across:
- Different key insertion orders in the input dict (sort_keys=True is doing its job).
- Whether or not optional fields are present (None vs missing must differ).

If either invariant breaks, two callers can submit "the same" lifecycle data
and produce different on-chain anchors, which silently corrupts traceability.
"""

import json
from app.services.blockchain import BlockchainService


def test_key_order_does_not_affect_hash():
    h1 = BlockchainService.compute_data_hash({"a": 1, "b": 2, "c": 3})
    h2 = BlockchainService.compute_data_hash({"c": 3, "a": 1, "b": 2})
    assert h1 == h2, "Hash must be invariant under key reordering"


def test_nested_dict_key_order_does_not_affect_hash():
    h1 = BlockchainService.compute_data_hash({"outer": {"x": 1, "y": 2}})
    h2 = BlockchainService.compute_data_hash({"outer": {"y": 2, "x": 1}})
    assert h1 == h2


def test_missing_optional_differs_from_explicit_none():
    """If a payload omits a field, the hash MUST differ from one that sets it to None.
    Otherwise the schema's optional-field discipline is a no-op for traceability."""
    h_without = BlockchainService.compute_data_hash({"a": 1})
    h_with_none = BlockchainService.compute_data_hash({"a": 1, "b": None})
    assert h_without != h_with_none


def test_datetime_serializes_deterministically():
    """`default=str` is what allows datetime in payloads. Same datetime → same hash."""
    from datetime import datetime, timezone

    dt = datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)
    h1 = BlockchainService.compute_data_hash({"when": dt, "x": 1})
    h2 = BlockchainService.compute_data_hash({"x": 1, "when": dt})
    assert h1 == h2


def test_hash_length_is_32_bytes():
    h = BlockchainService.compute_data_hash({"anything": "here"})
    assert len(h) == 32, f"keccak256 must be 32 bytes, got {len(h)}"


def test_uses_sort_keys_in_serialization():
    """Lock in the implementation choice — the serializer must produce
    sorted-key JSON. If someone changes this, two writers with identical
    semantic input produce different anchors."""
    import inspect

    src = inspect.getsource(BlockchainService.compute_data_hash)
    assert "sort_keys=True" in src, "compute_data_hash must call json.dumps with sort_keys=True"
