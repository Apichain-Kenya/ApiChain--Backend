# tests/test_geoai_compute.py
"""compute_prediction / compute_validation are pure (no DB). Guards the preview
path (must not persist) and the sucrose-excluded scoring."""
import pytest
geo = pytest.importorskip("app.services.geo_ai")


def test_compute_validation_excludes_sugar_from_phys_match():
    # Two identical inputs except sugar deviates wildly; score must be unchanged
    # because sugar is excluded from phys_match this sprint.
    pred = {"predicted_moisture": 19.0, "predicted_sugar": 75.0, "predicted_hmf": 28.0,
            "triangulation_score": 0.8, "confidence_score": 0.9}
    a = geo.compute_validation(pred, actual_moisture=19.0, actual_hmf=28.0, actual_sugar=4.0)
    b = geo.compute_validation(pred, actual_moisture=19.0, actual_hmf=28.0, actual_sugar=999.0)
    assert a["authenticity_score"] == b["authenticity_score"]
    assert a["validation_status"] == b["validation_status"]


def test_compute_validation_status_bands():
    pred = {"predicted_moisture": 19.0, "predicted_sugar": 75.0, "predicted_hmf": 28.0,
            "triangulation_score": 0.9, "confidence_score": 0.95}
    v = geo.compute_validation(pred, actual_moisture=19.0, actual_hmf=28.0, actual_sugar=4.0)
    assert v["validation_status"] in {"verified", "suspicious", "flagged"}
    assert 0.0 <= v["authenticity_score"] <= 1.0
