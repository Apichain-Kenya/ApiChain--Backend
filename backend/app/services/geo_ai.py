# app/services/geo_ai.py
import json, pickle, joblib
import numpy as np
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.geo_ai import GeoAIPrediction, ValidationResult

ML_DIR = Path(__file__).parent.parent / "ml_models"

TARGETS = ["moisture_content", "sucrose_level", "hmf_level"]


class GeoAIModelError(RuntimeError):
    """Raised when ML artifacts are missing/incompatible. Routes catch this
    and return HTTP 503 so a model problem degrades the geo-ai routes only,
    instead of crashing backend boot (artifacts load lazily, not at import)."""


# Module-level handles, populated lazily by _ensure_loaded() on first use.
scaler = le_region = le_season = le_veg = None
FEATURE_COLS = FLOWERING_CALENDAR = REGION_BOUNDS = None
ZONE_CENTROIDS = TOLERANCES = THRESHOLD = ensemble_models = None
# Max plausible distance (km) from a coord to its nearest region centroid before
# we treat the location as outside Kenya's modelled regions. Derived at load
# time from the regions' own spread (max pairwise centroid distance), so it
# scales with the data instead of being a magic constant.
_REGION_DIST_CAP = None
_LOADED = False


def _ensure_loaded():
    """Load ML artifacts once, on first request. Any failure (missing file,
    pickle/version incompatibility, feature/scaler mismatch) raises
    GeoAIModelError rather than propagating at import time."""
    global scaler, le_region, le_season, le_veg, FEATURE_COLS
    global FLOWERING_CALENDAR, REGION_BOUNDS, ZONE_CENTROIDS, TOLERANCES, THRESHOLD
    global ensemble_models, _REGION_DIST_CAP, _LOADED
    if _LOADED:
        return
    # SAFETY: these .pkl artifacts are first-party — the teammate's own trained
    # models, shipped out-of-band and extracted into app/ml_models/ (gitignored),
    # never user-supplied. joblib/pickle load of trusted local artifacts is the
    # standard sklearn/xgboost path; no untrusted deserialization happens here.
    try:
        scaler    = joblib.load(ML_DIR / "scaler.pkl")
        le_region = joblib.load(ML_DIR / "le_region.pkl")
        le_season = joblib.load(ML_DIR / "le_season.pkl")
        le_veg    = joblib.load(ML_DIR / "le_veg.pkl")

        with open(ML_DIR / "feature_cols.json") as f:
            FEATURE_COLS = json.load(f)

        with open(ML_DIR / "flowering_calendar.pkl", "rb") as f:
            _cal = pickle.load(f)
        FLOWERING_CALENDAR = _cal["FLOWERING_CALENDAR"]
        REGION_BOUNDS      = _cal["REGION_BOUNDS"]
        ZONE_CENTROIDS     = _cal["ZONE_CENTROIDS"]
        TOLERANCES         = _cal["TOLERANCES"]
        THRESHOLD          = _cal["THRESHOLD"]

        ensemble_models = {t: joblib.load(ML_DIR / f"ensemble_{t}.pkl") for t in TARGETS}
    except Exception as e:
        raise GeoAIModelError(f"GeoAI model artifacts failed to load: {e}") from e

    # Catch feature/scaler mismatches before any prediction runs.
    if len(FEATURE_COLS) != scaler.n_features_in_:
        raise GeoAIModelError(
            f"MISMATCH: feature_cols.json has {len(FEATURE_COLS)} cols "
            f"but scaler expects {scaler.n_features_in_}. FEATURE_COLS: {FEATURE_COLS}"
        )

    # Distance cap for region snapping = the regions' own max pairwise spread.
    _cents = list(ZONE_CENTROIDS.values())
    _REGION_DIST_CAP = max(
        _haversine(a[0], a[1], b[0], b[1]) for a in _cents for b in _cents
    )

    _LOADED = True


# ── Helpers ───────────────────────────────────────────────────────────────────
def _haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

def _nearest_region(lat, lon):
    """Closest region centroid to a coordinate -> (region, distance_km)."""
    best, best_d = None, None
    for region, (clat, clon) in ZONE_CENTROIDS.items():
        d = _haversine(lat, lon, clat, clon)
        if best_d is None or d < best_d:
            best, best_d = region, d
    return best, best_d


def _get_region(lat, lon):
    # Exact bounding-box hit first.
    for region, (mn, mx, mnl, mxl) in REGION_BOUNDS.items():
        if mn <= lat <= mx and mnl <= lon <= mxl:
            return region
    # The bounding boxes do NOT tile Kenya — real apiaries (e.g. the eastern /
    # Ukambani belt) land in gaps between them and would otherwise be "unknown",
    # which collapses triangulation and mis-flags legitimate honey. Snap to the
    # nearest region centroid, unless the point is implausibly far from every
    # modelled region (> the regions' own spread) — then it really is off-grid
    # and "unknown" is the correct suspicion signal.
    region, dist = _nearest_region(lat, lon)
    return region if dist <= _REGION_DIST_CAP else "unknown"

def _get_flowering(lat, lon, month):
    region = _get_region(lat, lon)
    return [info for sp, info in FLOWERING_CALENDAR.get(region, {}).items()
            if month in info["months"]]

def _encode_safe(encoder, value, fallback=0):
    try:    return int(encoder.transform([value])[0])
    except: return fallback

def _triangulation(lat, lon, month, vegetation_type, pollen_density=None):
    region   = _get_region(lat, lon)
    expected = _get_flowering(lat, lon, month)
    n_exp    = len(expected)

    flora_match  = 1.0 if region == vegetation_type else 0.3
    centroid     = ZONE_CENTROIDS.get(vegetation_type, (0, 0))
    dist_km      = _haversine(lat, lon, centroid[0], centroid[1])
    dist_score   = max(0.0, 1.0 - dist_km / 200)
    flower_align = min(1.0, n_exp / 3.0) if n_exp > 0 else 0.1
    exp_pollen   = n_exp * 8000
    # Decoupled: if no measured pollen is supplied, use the region-expected value
    # so pollen consistency is neutral (1.0) and the prediction is independent of
    # the lab pollen it will later be compared against.
    eff_pollen   = exp_pollen if pollen_density is None else pollen_density
    pollen_cons  = 1.0 if eff_pollen >= exp_pollen else eff_pollen / max(exp_pollen, 1)

    score = flora_match*0.35 + dist_score*0.25 + flower_align*0.25 + pollen_cons*0.15
    return {
        "triangulation_score": round(score, 4),
        "flowering_alignment": round(flower_align, 4),
        "dist_to_zone_km":     round(dist_km, 2),
        "flora_match_score":   round(flora_match, 3),
        "n_flowering_species": n_exp,
        "region_detected":     region,
        "flowering_species":   [f.get("pollen_marker") for f in expected],
    }


# ── Pure compute functions (no DB, no side effects) ───────────────────────────

def compute_prediction(
    latitude: float, longitude: float, altitude: float,
    vegetation_type: str, harvest_date: datetime,
    temperature: float, humidity: float, rainfall: float,
    ndvi: float,
) -> dict:
    """Pure prediction — NO db write, NO lab pollen. Returns predicted_* +
    confidence + triangulation components."""
    _ensure_loaded()

    month  = harvest_date.month
    season = "dry" if month in [1, 2, 6, 7, 8] else "rainy"
    region = _get_region(latitude, longitude)

    # The trained encoders' vegetation vocabulary IS the 5 region labels
    # (le_veg.classes_ == the regions), so a free-text apiary vegetation_type
    # like "shrubland" is out-of-distribution -> encoder fallback 0 and a bogus
    # (0,0) zone centroid. Coordinates are the only in-vocab source, so we feed
    # the coord-derived region as the vegetation input. NOTE: this assumes the
    # model was trained with vegetation_type == region; confirm against the
    # teammate's training setup. See reference_geoai_model_contract (auto-memory).
    vegetation_type = region

    # pollen_density=None so prediction is independent of the lab pollen it will
    # later be compared against (decoupled per Sprint 13 design).
    tri = _triangulation(latitude, longitude, month, vegetation_type, pollen_density=None)

    # Compute sugar_boost from flowering calendar (generated, not from lab)
    flowering         = _get_flowering(latitude, longitude, month)
    sugar_boost_score = float(np.mean([f["sugar_boost"] for f in flowering])) \
                        if flowering else 0.5

    # ── Build feature dict keyed by name ──────────────────────────────────────
    # Order is determined by FEATURE_COLS loaded from feature_cols.json
    # so adding/removing features here never silently breaks the scaler order
    feature_dict = {
        "latitude":            latitude,
        "longitude":           longitude,
        "altitude":            altitude,
        "region_enc":          _encode_safe(le_region, region),
        "veg_enc":             _encode_safe(le_veg, vegetation_type),
        "dist_to_zone_km":     tri["dist_to_zone_km"],
        "harvest_month":       month,
        "season_enc":          _encode_safe(le_season, season),
        "n_flowering_species": tri["n_flowering_species"],
        "sugar_boost_score":   sugar_boost_score,
        "temperature":         temperature,
        "humidity":            humidity,
        "rainfall":            rainfall,
        "ndvi":                ndvi,
        "triangulation_score": tri["triangulation_score"],
        "flowering_alignment": tri["flowering_alignment"],
    }

    # Build row in the exact order the scaler was fitted on
    try:
        features = [feature_dict[col] for col in FEATURE_COLS]
    except KeyError as e:
        raise ValueError(
            f"Feature {e} is in FEATURE_COLS but missing from feature_dict. "
            f"FEATURE_COLS={FEATURE_COLS}, feature_dict keys={list(feature_dict.keys())}"
        )

    X_sc   = scaler.transform([features])
    preds  = {}
    errors = []

    for target, m in ensemble_models.items():
        rf_p  = m["rf"].predict(X_sc)[0]
        xgb_p = m["xgb"].predict(X_sc)[0]
        final = m["meta"].predict([[rf_p, xgb_p]])[0]
        preds[m["pred_col"]] = round(float(final), 4)
        errors.append(abs(rf_p - xgb_p) / (abs(rf_p) + 1e-6))

    conf = round(float(np.clip(1.0 - np.mean(errors), 0, 1)), 4)

    return {
        "predicted_moisture":  preds["predicted_moisture"],
        "predicted_sugar":     preds["predicted_sugar"],
        "predicted_hmf":       preds["predicted_hmf"],
        "confidence_score":    conf,
        "region_detected":     tri["region_detected"],
        "flowering_species":   ",".join(tri["flowering_species"]),
        "triangulation_score": tri["triangulation_score"],
        "flora_match_score":   tri["flora_match_score"],
        "dist_to_zone_km":     tri["dist_to_zone_km"],
        "n_flowering_species": tri["n_flowering_species"],
    }


def compute_validation(
    prediction: dict,
    actual_moisture: float,
    actual_hmf: float,
    actual_sugar=None,
) -> dict:
    """Pure scoring — NO db write. Sucrose EXCLUDED from phys_match this sprint
    (model target mislabeled); accepted only so callers can pass it without error."""
    _ensure_loaded()

    # Our lab form makes the 5 metrics optional, so any actual_* can be None.
    # Skip absent metrics rather than treating them as deviation-from-0 (which
    # would unfairly tank the score). If ALL metrics are absent there is no
    # physical evidence to compare, so phys_match falls back to a neutral 0.5
    # and the authenticity score leans on triangulation + confidence instead.
    # Sucrose is intentionally excluded this sprint — the sucrose_level model
    # target predicts total sugar (~75) not true sucrose (~4), so it unfairly
    # penalises genuine honey. Sugar passes through (stored/anchored) but not scored.
    ps = []
    for actual, pred_val, tol_key in [
        (actual_moisture, prediction["predicted_moisture"], "moisture_content"),
        (actual_hmf,      prediction["predicted_hmf"],      "hmf_level"),
    ]:
        if actual is None:
            continue
        dev = abs(actual - (pred_val or 0))
        ps.append(max(0.0, 1.0 - dev / (2 * TOLERANCES[tol_key])))

    mean_phys = float(np.mean(ps)) if ps else 0.5
    tri       = prediction.get("triangulation_score") or 0.5
    conf      = prediction.get("confidence_score") or 0.5
    auth      = round(float(np.clip(mean_phys*0.50 + tri*0.35 + conf*0.15, 0, 1)), 4)
    status    = "verified"   if auth >= 0.80 else \
                "suspicious" if auth >= THRESHOLD else "flagged"
    return {
        "authenticity_score": auth,
        "is_valid":           auth >= THRESHOLD,
        "validation_status":  status,
        "phys_match_score":   round(mean_phys, 4),
        "triangulation_score": round(tri, 4),
        "confidence_score":   round(conf, 4),
    }


def build_explanation(
    prediction: dict,
    validation: dict,
    actual_moisture,
    actual_hmf,
) -> str:
    """Deterministic, offline, English rule-based explanation. Anchored on chain
    as a proof artifact (English is fine — the consumer view localizes the BAND,
    not this prose). Built only from rounded components, so re-running it server-
    side at submit reproduces the exact string hashed."""
    region   = prediction.get("region_detected") or "unknown"
    tri      = prediction.get("triangulation_score") or 0.0
    tri_word = "strong" if tri >= 0.7 else "moderate" if tri >= 0.4 else "weak"
    pm       = prediction.get("predicted_moisture")
    ph       = prediction.get("predicted_hmf")
    status   = validation.get("validation_status", "flagged")
    am       = "n/a" if actual_moisture is None else actual_moisture
    ah       = "n/a" if actual_hmf is None else actual_hmf
    return (
        f"Origin region detected: {region}. "
        f"Moisture {am} vs expected {pm}; HMF {ah} vs expected {ph}. "
        f"{tri_word.capitalize()} origin triangulation ({round(tri*100)}%). "
        f"Sugar measured but not scored (model target under review). "
        f"Verdict: {status}."
    )


# ── Persist wrappers (thin shell over compute fns) ────────────────────────────

def predict_and_save(
    db: Session,
    batch_id: int,
    latitude: float, longitude: float, altitude: float,
    vegetation_type: str, harvest_date: datetime,
    temperature: float, humidity: float, rainfall: float,
    ndvi: float, pollen_density: float,
) -> GeoAIPrediction:
    # pollen_density kept in signature for back-compat but no longer used (decoupled)
    p = compute_prediction(latitude, longitude, altitude, vegetation_type,
                           harvest_date, temperature, humidity, rainfall, ndvi)
    record = GeoAIPrediction(
        batch_id            = batch_id,
        predicted_moisture  = p["predicted_moisture"],
        predicted_sugar     = p["predicted_sugar"],
        predicted_hmf       = p["predicted_hmf"],
        confidence_score    = p["confidence_score"],
        region_detected     = p["region_detected"],
        flowering_species   = p["flowering_species"],
        triangulation_score = p["triangulation_score"],
        flora_match_score   = p["flora_match_score"],
        dist_to_zone_km     = p["dist_to_zone_km"],
        n_flowering_species = p["n_flowering_species"],
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def validate_and_save(
    db: Session,
    batch_id: int,
    prediction: GeoAIPrediction,
    actual_moisture: float,
    actual_sugar: float,
    actual_hmf: float,
) -> ValidationResult:
    pred_dict = {
        "predicted_moisture":  prediction.predicted_moisture,
        "predicted_sugar":     prediction.predicted_sugar,
        "predicted_hmf":       prediction.predicted_hmf,
        "triangulation_score": prediction.triangulation_score,
        "confidence_score":    prediction.confidence_score,
    }
    v = compute_validation(pred_dict, actual_moisture, actual_hmf, actual_sugar)
    record = ValidationResult(
        batch_id            = batch_id,
        prediction_id       = prediction.id,
        authenticity_score  = v["authenticity_score"],
        is_valid            = v["is_valid"],
        validation_status   = v["validation_status"],
        phys_match_score    = v["phys_match_score"],
        triangulation_score = v["triangulation_score"],
        confidence_score    = v["confidence_score"],
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record