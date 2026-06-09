# tests/test_geoai_compute.py
"""compute_prediction / compute_validation / build_explanation are pure (no DB).

Guards the Sprint-14 total-sugars flow:
  - sugar is scored ONLY when the reading looks like total sugars (>20%); a
    sub-20 value is treated as a mistaken true-sucrose reading and skipped so it
    never penalises genuine honey,
  - pollen is a validation-time consistency signal (vs n_species*8000),
  - the claimed honey type is cross-checked against flowering species
    (explanation-only — it does NOT move the score).
"""
import pytest
geo = pytest.importorskip("app.services.geo_ai")


def _pred(**over):
    """A hand-built prediction dict (compute_validation/build_explanation are
    pure over dicts, so no ML inference is needed to exercise scoring)."""
    base = {
        "predicted_moisture": 19.0,
        "predicted_sugar": 75.0,          # model predicts TOTAL sugars (~75-80%)
        "predicted_hmf": 28.0,
        "triangulation_score": 0.8,
        "confidence_score": 0.9,
        "n_flowering_species": 3,
        "flowering_species": "acacia, eucalyptus, sunflower",
        "region_detected": "central_highlands",
    }
    base.update(over)
    return base


def test_sugar_below_20_is_skipped_not_scored():
    # A sub-20 reading is treated as a mistaken true-sucrose value and skipped,
    # so it must NOT change the score vs supplying no sugar at all.
    pred = _pred()
    none_sugar = geo.compute_validation(pred, actual_moisture=19.0, actual_hmf=28.0,
                                        actual_total_sugars=None)
    low_sugar = geo.compute_validation(pred, actual_moisture=19.0, actual_hmf=28.0,
                                       actual_total_sugars=4.0)
    assert none_sugar["authenticity_score"] == low_sugar["authenticity_score"]


def test_sugar_above_20_is_scored():
    # A plausible total-sugars reading IS scored: matching the prediction scores
    # higher than deviating far from it.
    pred = _pred()
    matching = geo.compute_validation(pred, actual_moisture=19.0, actual_hmf=28.0,
                                      actual_total_sugars=75.0)
    deviating = geo.compute_validation(pred, actual_moisture=19.0, actual_hmf=28.0,
                                       actual_total_sugars=120.0)
    assert matching["authenticity_score"] > deviating["authenticity_score"]


def test_pollen_scored_at_validation_time():
    # Pollen consistent with expected (n_species*8000) scores higher than pollen
    # far below it.
    pred = _pred(n_flowering_species=3)  # expected ~24000/mL
    good = geo.compute_validation(pred, actual_moisture=19.0, actual_hmf=28.0,
                                  actual_pollen_density=30000)
    poor = geo.compute_validation(pred, actual_moisture=19.0, actual_hmf=28.0,
                                  actual_pollen_density=2000)
    assert good["authenticity_score"] > poor["authenticity_score"]


def test_status_bands_well_formed():
    pred = _pred(triangulation_score=0.9, confidence_score=0.95)
    v = geo.compute_validation(pred, actual_moisture=19.0, actual_hmf=28.0,
                               actual_total_sugars=75.0)
    assert v["validation_status"] in {"verified", "suspicious", "flagged"}
    assert 0.0 <= v["authenticity_score"] <= 1.0


def test_all_none_actuals_uses_neutral_phys_match():
    # No physical metrics supplied → phys_match falls back to neutral 0.5,
    # score leans on triangulation + confidence.
    pred = _pred()
    v = geo.compute_validation(pred, actual_moisture=None, actual_hmf=None,
                               actual_total_sugars=None, actual_pollen_density=None)
    assert v["phys_match_score"] == 0.5


def test_zero_triangulation_not_treated_as_missing():
    # A genuine 0.0 triangulation must NOT be silently replaced by 0.5.
    pred_zero = _pred(triangulation_score=0.0, confidence_score=0.0)
    pred_half = _pred(triangulation_score=0.5, confidence_score=0.5)
    z = geo.compute_validation(pred_zero, actual_moisture=19.0, actual_hmf=28.0)
    h = geo.compute_validation(pred_half, actual_moisture=19.0, actual_hmf=28.0)
    assert z["authenticity_score"] < h["authenticity_score"]


def test_honey_type_consistency_matches_flowering_species():
    pred = _pred(flowering_species="acacia, eucalyptus", n_flowering_species=2)
    ok, note = geo._check_honey_type_consistency("acacia", pred)
    assert ok and "consistent" in note.lower()
    bad, note2 = geo._check_honey_type_consistency("sunflower", pred)
    assert not bad and note2  # mismatch flagged with a note


def test_honey_type_consistency_neutral_when_unclaimed():
    ok, note = geo._check_honey_type_consistency(None, _pred())
    assert ok and note == ""


def test_wildflower_needs_at_least_two_species():
    ok_multi, _ = geo._check_honey_type_consistency("wildflower", _pred(n_flowering_species=3))
    ok_mono, _ = geo._check_honey_type_consistency("wildflower", _pred(n_flowering_species=1))
    assert ok_multi and not ok_mono


def test_build_explanation_is_deterministic_and_well_formed():
    pred = _pred(region_detected="central_highlands", triangulation_score=0.8)
    val = {"validation_status": "suspicious"}
    s1 = geo.build_explanation(pred, val, 19.0, 28.0)
    s2 = geo.build_explanation(pred, val, 19.0, 28.0)
    assert s1 == s2
    assert s1.endswith("Verdict: suspicious.")
    assert "central_highlands" in s1


def test_build_explanation_distinguishes_total_sugars_from_sucrose():
    pred = _pred()
    val = {"validation_status": "verified"}
    s_total = geo.build_explanation(pred, val, 19.0, 28.0, actual_total_sugars=75.0)
    assert "Total sugars" in s_total
    s_sucrose = geo.build_explanation(pred, val, 19.0, 28.0, actual_total_sugars=4.0)
    assert "not scored" in s_sucrose
