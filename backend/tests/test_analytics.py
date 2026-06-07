"""Pure aggregation over batch-like objects — no DB needed (SimpleNamespace)."""
from types import SimpleNamespace
from app.routers.analytics import aggregate_batches, STATES


def _b(state, kg=None, status=None):
    return SimpleNamespace(
        current_state=state,
        harvest_record=SimpleNamespace(quantity_kg=kg) if kg is not None else None,
        validation=SimpleNamespace(validation_status=status) if status is not None else None,
    )


def test_empty():
    a = aggregate_batches([])
    assert a["total_batches"] == 0
    assert a["by_state"] == {s: 0 for s in STATES}
    assert a["total_kg_harvested"] == 0
    assert a["distributed_count"] == 0
    assert a["flagged_count"] == 0


def test_counts_by_state_and_totals():
    batches = [
        _b("HARVESTED", kg=25.5),
        _b("DISTRIBUTED", kg=10.0, status="verified"),
        _b("LAB_VERIFIED", kg=5.0, status="suspicious"),
        _b("DISTRIBUTED", kg=8.0, status="flagged"),
        _b("CREATED"),
    ]
    a = aggregate_batches(batches)
    assert a["total_batches"] == 5
    assert a["by_state"]["DISTRIBUTED"] == 2
    assert a["by_state"]["HARVESTED"] == 1
    assert a["by_state"]["CREATED"] == 1
    assert a["total_kg_harvested"] == 48.5
    assert a["distributed_count"] == 2
    assert a["flagged_count"] == 2  # suspicious + flagged both count as needs-attention


def test_unknown_state_ignored_in_by_state_but_counted_in_total():
    a = aggregate_batches([_b("WEIRD"), _b("HARVESTED")])
    assert a["total_batches"] == 2
    assert sum(a["by_state"].values()) == 1  # only HARVESTED bucketed
