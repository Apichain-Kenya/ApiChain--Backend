import math
import pytest
from fastapi import HTTPException
from app.routers.batch import _reject_non_finite


def test_passes_finite_and_none():
    _reject_non_finite({"a": 1.0, "b": 0.0, "c": None, "d": -3.2})  # no raise


def test_rejects_nan():
    with pytest.raises(HTTPException) as ei:
        _reject_non_finite({"authenticity_score": float("nan")})
    assert ei.value.status_code == 503
    assert "authenticity_score" in str(ei.value.detail)


def test_rejects_inf():
    with pytest.raises(HTTPException) as ei:
        _reject_non_finite({"predicted_moisture": float("inf")})
    assert ei.value.status_code == 503
