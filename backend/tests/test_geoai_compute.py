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


def test_compute_validation_all_none_actuals_uses_neutral_phys_match():
    # No physical metrics supplied → phys_match falls back to neutral 0.5,
    # score leans on triangulation + confidence.
    pred = {"predicted_moisture": 19.0, "predicted_hmf": 28.0,
            "triangulation_score": 0.8, "confidence_score": 0.9}
    v = geo.compute_validation(pred, actual_moisture=None, actual_hmf=None, actual_sugar=None)
    assert v["phys_match_score"] == 0.5


def test_compute_validation_zero_triangulation_not_treated_as_missing():
    # A genuine 0.0 triangulation must NOT be silently replaced by 0.5.
    pred_zero = {"predicted_moisture": 19.0, "predicted_hmf": 28.0,
                 "triangulation_score": 0.0, "confidence_score": 0.0}
    pred_half = {"predicted_moisture": 19.0, "predicted_hmf": 28.0,
                 "triangulation_score": 0.5, "confidence_score": 0.5}
    z = geo.compute_validation(pred_zero, actual_moisture=19.0, actual_hmf=28.0)
    h = geo.compute_validation(pred_half, actual_moisture=19.0, actual_hmf=28.0)
    assert z["authenticity_score"] < h["authenticity_score"]


def test_build_explanation_is_deterministic_and_well_formed():
    pred = {"region_detected": "central_highlands", "triangulation_score": 0.8,
            "predicted_moisture": 19.0, "predicted_hmf": 28.0}
    val = {"validation_status": "suspicious"}
    s1 = geo.build_explanation(pred, val, 19.0, 28.0)
    s2 = geo.build_explanation(pred, val, 19.0, 28.0)
    assert s1 == s2
    assert s1.endswith("Verdict: suspicious.")
    assert "not scored" in s1
