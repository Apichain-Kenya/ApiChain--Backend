# app/services/geo_ai.py
import json, pickle, joblib
import numpy as np
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path
from datetime import datetime

ML_DIR = Path(__file__).parent.parent / "ml_models"

TARGETS = ["moisture_content", "sucrose_level", "hmf_level"]


class GeoAIModelError(RuntimeError):
    """Raised when ML artifacts are missing/incompatible."""


scaler = le_region = le_season = le_veg = None
FEATURE_COLS = FLOWERING_CALENDAR = REGION_BOUNDS = None
ZONE_CENTROIDS = TOLERANCES = THRESHOLD = ensemble_models = None
_REGION_DIST_CAP = None
_LOADED = False


def _ensure_loaded():
    global scaler, le_region, le_season, le_veg, FEATURE_COLS
    global FLOWERING_CALENDAR, REGION_BOUNDS, ZONE_CENTROIDS, TOLERANCES, THRESHOLD
    global ensemble_models, _REGION_DIST_CAP, _LOADED
    if _LOADED:
        return
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

        ensemble_models = {
            t: joblib.load(ML_DIR / f"ensemble_{t}.pkl") for t in TARGETS
        }
    except Exception as e:
        raise GeoAIModelError(f"GeoAI model artifacts failed to load: {e}") from e

    if len(FEATURE_COLS) != scaler.n_features_in_:
        raise GeoAIModelError(
            f"MISMATCH: feature_cols.json has {len(FEATURE_COLS)} cols "
            f"but scaler expects {scaler.n_features_in_}."
        )

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
    best, best_d = None, None
    for region, (clat, clon) in ZONE_CENTROIDS.items():
        d = _haversine(lat, lon, clat, clon)
        if best_d is None or d < best_d:
            best, best_d = region, d
    return best, best_d

def _get_region(lat, lon):
    for region, (mn, mx, mnl, mxl) in REGION_BOUNDS.items():
        if mn <= lat <= mx and mnl <= lon <= mxl:
            return region
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
    # Prediction phase: pollen_density=None → neutral (1.0), decoupled from lab
    eff_pollen   = exp_pollen if pollen_density is None else pollen_density
    pollen_cons  = 1.0 if eff_pollen >= exp_pollen \
                   else eff_pollen / max(exp_pollen, 1)

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


def _check_honey_type_consistency(claimed_honey_type: str | None,
                                   prediction: dict) -> tuple[bool, str]:
    """
    Check whether the honey type the farmer declared on the UI
    is consistent with what the flowering calendar says should
    be at that GPS location at harvest time.

    Returns (is_consistent, note_string).
    """
    if not claimed_honey_type:
        return True, ""

    flowering_species = prediction.get("flowering_species", "") or ""
    region            = prediction.get("region_detected", "") or ""

    # Map UI honey_type values to pollen markers / keywords
    # that indicate consistency
    HONEY_TYPE_MARKERS = {
        "acacia":      ["acacia"],
        "eucalyptus":  ["eucalyptus"],
        "wildflower":  [],            # wildflower is always plausible if ≥2 species
        "sunflower":   ["sunflower"],
        "mixed":       [],            # mixed is always plausible
    }

    claimed = claimed_honey_type.lower().strip()
    markers = HONEY_TYPE_MARKERS.get(claimed, [])
    n_sp    = prediction.get("n_flowering_species", 0)

    if claimed in ("wildflower", "mixed"):
        # Plausible if at least 2 species are flowering
        consistent = n_sp >= 2
        note = (
            f"Claimed '{claimed}' honey consistent with "
            f"{n_sp} flowering species at harvest time."
            if consistent else
            f"Claimed '{claimed}' honey — only {n_sp} species flowering "
            f"at this location/season; monofloral origin more likely."
        )
    elif not markers:
        consistent = True
        note = f"Claimed '{claimed}' honey type — no marker conflict detected."
    else:
        species_str = flowering_species.lower()
        consistent  = any(m in species_str for m in markers)
        if consistent:
            note = (
                f"Claimed '{claimed}' honey consistent with flowering species "
                f"({flowering_species}) detected at this location in harvest month."
            )
        else:
            note = (
                f"Claimed '{claimed}' honey — but {flowering_species or 'no matching species'} "
                f"detected at this GPS location in harvest month. "
                f"Possible mislabelling or off-season harvest."
            )

    return consistent, note


# ── Pure compute functions (no DB, no side effects) ───────────────────────────

def compute_prediction(
    latitude: float,
    longitude: float,
    altitude: float,
    vegetation_type: str,
    harvest_date: datetime,
    temperature: float,
    humidity: float,
    rainfall: float,
    ndvi: float,
) -> dict:
    """
    Pure prediction — NO db write, NO lab pollen.
    pollen_density intentionally excluded so prediction is independent
    of the lab result it will later be compared against.
    """
    _ensure_loaded()

    month  = harvest_date.month
    season = "dry" if month in [1, 2, 6, 7, 8] else "rainy"
    region = _get_region(latitude, longitude)

    # Snap vegetation to coord-derived region (encoders trained on region labels)
    vegetation_type = region

    tri = _triangulation(latitude, longitude, month, vegetation_type, pollen_density=None)

    flowering         = _get_flowering(latitude, longitude, month)
    sugar_boost_score = float(np.mean([f["sugar_boost"] for f in flowering])) \
                        if flowering else 0.5

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

    try:
        features = [feature_dict[col] for col in FEATURE_COLS]
    except KeyError as e:
        raise GeoAIModelError(
            f"Feature {e} is in FEATURE_COLS but missing from feature_dict. "
            f"FEATURE_COLS={FEATURE_COLS}"
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
        # The model was trained on total_sugars labelled as sucrose_level.
        # The predicted value (~75-80) represents TOTAL SUGARS, not the
        # disaccharide sucrose (~1-5). Stored as predicted_sugar throughout.
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
    actual_moisture: "float | None",
    actual_hmf: "float | None",
    actual_total_sugars: "float | None" = None,   # renamed from actual_sugar
    actual_pollen_density: "float | None" = None,
) -> dict:
    """
    Pure scoring — NO db write.

    Scoring signals:
      - moisture_content:  scored (model trained on this correctly)
      - hmf_level:         scored (model trained on this correctly)
      - total_sugars:      NOW SCORED — model predicted total sugars (~75-80%),
                           lab submits total sugars, so comparison is valid
      - pollen_density:    scored at validation time (not prediction time)
    """
    _ensure_loaded()

    ps = []

    # ── Moisture ──────────────────────────────────────────────────────────────
    if actual_moisture is not None:
        dev = abs(actual_moisture - (prediction["predicted_moisture"] or 0))
        ps.append(max(0.0, 1.0 - dev / (2 * TOLERANCES["moisture_content"])))

    # ── HMF ───────────────────────────────────────────────────────────────────
    if actual_hmf is not None:
        dev = abs(actual_hmf - (prediction["predicted_hmf"] or 0))
        ps.append(max(0.0, 1.0 - dev / (2 * TOLERANCES["hmf_level"])))

    # ── Total sugars (model trained on total sugars labelled sucrose_level) ───
    # Only score if the submitted value looks like total sugars (>20%)
    # A real sucrose-only reading would be <10% and must NOT be compared
    # against a ~75-80% prediction — that would always flag genuine honey.
    if actual_total_sugars is not None:
        if actual_total_sugars > 20.0:
            # Submitted value is total sugars — safe to score
            dev = abs(actual_total_sugars - (prediction["predicted_sugar"] or 0))
            ps.append(max(0.0, 1.0 - dev / (2 * TOLERANCES["sucrose_level"])))
        # If < 20% we silently skip — likely a true sucrose reading submitted
        # by mistake; scoring it would unfairly penalise genuine honey

    # ── Pollen density (validation-time signal only) ──────────────────────────
    if actual_pollen_density is not None:
        n_exp      = prediction.get("n_flowering_species", 0)
        exp_pollen = n_exp * 8000
        p_score    = 1.0 if actual_pollen_density >= exp_pollen \
                     else actual_pollen_density / max(exp_pollen, 1)
        ps.append(p_score)

    mean_phys = float(np.mean(ps)) if ps else 0.5
    # None → neutral 0.5, but a genuine 0.0 must stay 0.0. A `... or 0.5` here is
    # a truthiness trap: it silently rescues a zero-triangulation / zero-confidence
    # batch (a totally inconsistent origin) up to 0.5, masking the fraud signal.
    # Guarded by test_geoai_compute::test_zero_triangulation_not_treated_as_missing.
    tri = prediction.get("triangulation_score")
    tri = 0.5 if tri is None else tri
    conf = prediction.get("confidence_score")
    conf = 0.5 if conf is None else conf
    auth = round(float(np.clip(
        mean_phys * 0.50 + tri * 0.35 + conf * 0.15, 0, 1
    )), 4)

    status = "verified"   if auth >= 0.80 else \
             "suspicious" if auth >= THRESHOLD else "flagged"

    return {
        "authenticity_score":  auth,
        "is_valid":            auth >= THRESHOLD,
        "validation_status":   status,
        "phys_match_score":    round(mean_phys, 4),
        "triangulation_score": round(tri, 4),
        "confidence_score":    round(conf, 4),
    }


def build_explanation(
    prediction: dict,
    validation: dict,
    actual_moisture,
    actual_hmf,
    actual_total_sugars=None,
    actual_pollen_density=None,
    claimed_honey_type=None,
) -> str:
    """Deterministic English explanation anchored on chain."""
    region   = prediction.get("region_detected") or "unknown"
    tri      = prediction.get("triangulation_score") or 0.0
    tri_word = "strong" if tri >= 0.7 else "moderate" if tri >= 0.4 else "weak"
    pm       = prediction.get("predicted_moisture")
    ph       = prediction.get("predicted_hmf")
    ps_pred  = prediction.get("predicted_sugar")
    n_sp     = prediction.get("n_flowering_species", 0)
    species  = prediction.get("flowering_species", "") or "none identified"
    status   = validation.get("validation_status", "flagged")

    am  = "n/a" if actual_moisture     is None else actual_moisture
    ah  = "n/a" if actual_hmf          is None else actual_hmf
    ats = "n/a" if actual_total_sugars is None else actual_total_sugars

    # Pollen note
    pollen_note = ""
    if actual_pollen_density is not None:
        exp_pollen = n_sp * 8000
        if actual_pollen_density >= exp_pollen:
            pollen_note = (
                f"Pollen density {int(actual_pollen_density)}/mL consistent "
                f"with {n_sp} flowering species. "
            )
        else:
            pollen_note = (
                f"Pollen density {int(actual_pollen_density)}/mL below expected "
                f"{exp_pollen}/mL for {n_sp} flowering species — "
                f"possible dilution or off-season harvest. "
            )

    # Sugar note
    sugar_note = ""
    if actual_total_sugars is not None:
        if actual_total_sugars > 20.0:
            sugar_note = (
                f"Total sugars {ats}% vs expected {ps_pred}%. "
            )
        else:
            sugar_note = (
                f"Sucrose-only reading ({ats}%) submitted — "
                f"total sugars not scored (submit total sugars for full scoring). "
            )

    # Honey type note
    _, honey_type_note = _check_honey_type_consistency(claimed_honey_type, prediction)

    return (
        f"Origin region detected: {region}. "
        f"Flowering species at harvest time: {species}. "
        f"Moisture {am}% vs expected {pm}%; "
        f"HMF {ah} mg/kg vs expected {ph} mg/kg. "
        f"{sugar_note}"
        f"{pollen_note}"
        f"{honey_type_note + ' ' if honey_type_note else ''}"
        f"{tri_word.capitalize()} origin triangulation ({round(tri * 100)}%). "
        f"Verdict: {status}."
    )