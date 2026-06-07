from app.routers.batch import _authenticity_band


def test_verified_maps_to_consistent():
    assert _authenticity_band("verified") == "consistent"


def test_suspicious_and_flagged_map_to_under_review():
    assert _authenticity_band("suspicious") == "under_review"
    assert _authenticity_band("flagged") == "under_review"


def test_none_maps_to_none():
    assert _authenticity_band(None) is None


def test_band_never_leaks_flagged():
    for status in ("verified", "suspicious", "flagged", None, "weird"):
        assert _authenticity_band(status) != "flagged"
