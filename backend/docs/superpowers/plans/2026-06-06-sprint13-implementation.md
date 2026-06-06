# Sprint 13 Implementation Plan — Lab+GeoAI Anchoring, One-QR Consumer View, Tracing, Analytics

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Anchor GeoAI authenticity into the on-chain lab proof, collapse lab entry + scoring into one tester panel, move to one consumer QR per batch with a redesigned scan page, fix the quantity=0 tracing bug at source, and add basic analytics — across two canonical-hash pre-image changes with no contract redeploy.

**Architecture:** Backend (FastAPI/SQLAlchemy/Web3.py) is the source of truth: it redesigns two keccak256 pre-images (lab + packaging), recomputes authenticity server-side deterministically, and anchors opaque `bytes32` (ABI verified: `anchorLabProof(bytes32,bytes32)` + `recordPackaging(bytes32,bytes32)` — no Solidity change). The React frontend never touches chain; it renders server-computed, three-way-verified state. GeoAI stays chain-neutral in compute but its output now rides inside the lab anchor.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Web3.py, scikit-learn==1.6.1 (pickle-pinned), PostgreSQL/PostGIS; React 19 + Vite, i18next (EN/SW), qrcode.react, Vitest+RTL (new, scoped).

---

## Locked decisions (this session, 2026-06-06)

From the locked plan §6 + the review session:

1. **Lab columns:** physically **DROP** `purity_score` + `passed_quality_check` from `lab_results`; **ADD** `predicted_moisture`, `predicted_sugar`, `predicted_hmf`, `authenticity_score`, `validation_status`, `explanation`.
2. **Packaging pre-image:** **drop `qr_codes` only, KEEP `jar_ids`** (records jar identity/count). New pre-image: `batch_id + unit_count + jar_ids + notes`.
3. **Env timing:** **auto-fetch in the lab flow** — the `preview` endpoint persists the env snapshot if missing; `lab-verify` reuses it (idempotent), so preview and submit hash identical inputs.
4. **FE testing:** **scoped Vitest** for the two pure-logic pieces (`interpretAuthenticity`, lab-panel reducer) + a written **manual test matrix** for everything else.
5. **Score interpretation:** **server-side** band enum + anchored English explanation. Server returns a localizable **band** (`consistent` / `under_review`), never raw prose for the band; the anchored `explanation` string is English (a proof artifact). FE localizes the band; SW shows the band localized + the English explanation under a "on-chain statement" label.

### Advisor-driven correctness tasks folded into P0b (do not treat as polish)

- **Float-determinism:** the new ML-derived numeric fields are rendered as **fixed-precision quantized strings** in the canonical payload (`_q4()`), making the anchor type-independent (a future `Numeric` column or a psycopg `Decimal` roundtrip can't silently break the match). Existing `moisture/sucrose/hmf/pollen` stay native float (proven on Sepolia).
- **Preview == Submit inputs:** env snapshot persisted at preview, reused at submit; predict/validate split into **compute-only** (preview, no DB write) vs **persist** (submit). What the tester reviewed is exactly what gets anchored.
- **Decouple pollen** from `lab.pollen_density` (region-derived expected pollen) → re-baseline the RUNBOOK §14.2 demo score table and the e2e.
- **Sole writer:** `lab-verify` becomes the **only** writer of `geo_ai_predictions` + `validation_results`; the standalone `POST /geo-ai/{id}/predict` + `/validate` routes are **removed** (replaced by `POST /geo-ai/{id}/preview`, compute-only). `GET /geo-ai/{id}/result` stays public.
- **e2e is the Sepolia-evidence vehicle:** `scripts/e2e_lifecycle.py` lab + package bodies updated; the single fresh Sepolia run happens **after both** hash changes (P0b + P0d).

---

## Phase / sequence overview

| Phase | What | Layer | Gate |
|---|---|---|---|
| **P0a** | Batch view-model (canonical quantity + lab/authenticity summary) + reusable env-ensure helper | BE | unit tests green |
| **P0b** | Lab pre-image redesign + scoring (exclude sucrose, decouple pollen) + rule-based explanation + compute/persist split + `preview` endpoint + `lab-verify` rewrite + lab determinism tests | BE + ⛓ | unit tests + local Hardhat `verification.lab.match` |
| **P0d** | Packaging pre-image change (drop `qr_codes`, keep `jar_ids`) | BE + ⛓ | packaging hash tests + `verification.packaging.match` |
| **⛓ EV** | One fresh Sepolia evidence run covering both new pre-images | ⛓ | all 7 `verification.*.match` true on Sepolia |
| **P0c** | FE merged lab+GeoAI panel: preview → lock-after-score → single submit → 202-pending | FE | Vitest reducer + manual matrix |
| **P1a** | `/verify` consumer fields: geocoded place + producer label + interpreted authenticity band/explanation | BE | unit test |
| **P1b** | FE one-QR-per-batch + QR "Verify" popup + consumer scan redesign | FE | Vitest interpret + manual matrix |
| **P2** | `SixStateTimeline` reliability (DB-sourced) + form/value audit + pressure test | FE | manual matrix |
| **P3** | Analytics aggregate endpoints + farmer/admin widgets | BE + FE | unit test + manual |

**Scope cut-line (if time slips):** drop **P3** first, then **P2**. P0 (lab anchor) + P1 (QR/consumer) ship together.

**Always:** activate the backend venv (`.venv/Scripts/python.exe`) before any Python/alembic/pytest/uvicorn. Never system Python. Kill zombie `python.exe` on Windows before restarting uvicorn (DEBUG-RUNBOOK §4). Restarting Hardhat wipes chain+roles → truncate DB + re-enroll per DEBUG-RUNBOOK §3/§13 before any fresh e2e.

---

# PHASE P0a — Backend foundational (batch view-model + env-ensure)

**Why first:** kills the `quantity = 0` bug at source and provides the reusable env-ensure helper P0b needs. No hash impact.

### Task P0a-1: Pure batch view-model builder

**Files:**
- Modify: `app/routers/batch.py` (add `build_batch_view` helper + new response schema usage)
- Modify: `app/schemas/batch.py` (extend `BatchResponse`)
- Test: `tests/test_batch_view_model.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_batch_view_model.py
"""Unit tests for build_batch_view — the canonical batch shape the FE trusts.
Pure function over relationship attributes; no DB needed (SimpleNamespace)."""
from types import SimpleNamespace
from app.routers.batch import build_batch_view


def _batch(**o):
    base = dict(
        id=7, blockchain_batch_id="0x" + "ab" * 32, farmer_id=3,
        current_state="HARVESTED", quantity=None,
        create_tx_hash="0xc", harvest_tx_hash="0xh", process_tx_hash=None,
        lab_verify_tx_hash=None, packaging_tx_hash=None, distribution_tx_hash=None,
        created_at=None, harvested_at=None, processed_at=None,
        lab_verified_at=None, packaged_at=None, distributed_at=None,
        harvest_record=SimpleNamespace(quantity_kg=25.5),
        lab_result=None, validation=None,
    )
    base.update(o)
    return SimpleNamespace(**base)


def test_quantity_comes_from_harvest_record_not_batch_column():
    b = _batch(quantity=0, harvest_record=SimpleNamespace(quantity_kg=25.5))
    view = build_batch_view(b)
    assert view["quantity"] == 25.5  # NOT 0 — the bug this fixes


def test_quantity_falls_back_to_batch_column_when_no_harvest_record():
    b = _batch(quantity=12.0, harvest_record=None)
    assert build_batch_view(b)["quantity"] == 12.0


def test_quantity_is_none_when_neither_present():
    b = _batch(quantity=None, harvest_record=None)
    assert build_batch_view(b)["quantity"] is None


def test_authenticity_summary_absent_until_validation_exists():
    b = _batch(validation=None)
    assert build_batch_view(b)["authenticity"] == {"available": False, "status": None, "score": None}


def test_authenticity_summary_present_when_validation_exists():
    b = _batch(validation=SimpleNamespace(validation_status="suspicious", authenticity_score=0.79))
    assert build_batch_view(b)["authenticity"] == {
        "available": True, "status": "suspicious", "score": 0.79,
    }
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_batch_view_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_batch_view'`.

- [ ] **Step 3: Implement `build_batch_view` + extend `BatchResponse`**

In `app/schemas/batch.py`, extend `BatchResponse` (add the two summary fields after `distributed_at`):

```python
class BatchAuthenticitySummary(BaseModel):
    available: bool
    status: Optional[str] = None
    score: Optional[float] = None


class BatchResponse(BaseModel):
    """Full batch data returned by API."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    blockchain_batch_id: str
    farmer_id: int
    current_state: str
    quantity: Optional[float] = None          # canonical: harvest_record.quantity_kg
    create_tx_hash: Optional[str] = None
    harvest_tx_hash: Optional[str] = None
    process_tx_hash: Optional[str] = None
    lab_verify_tx_hash: Optional[str] = None
    packaging_tx_hash: Optional[str] = None
    distribution_tx_hash: Optional[str] = None
    created_at: Optional[datetime] = None
    harvested_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    lab_verified_at: Optional[datetime] = None
    packaged_at: Optional[datetime] = None
    distributed_at: Optional[datetime] = None
    authenticity: Optional[BatchAuthenticitySummary] = None
```

In `app/routers/batch.py`, add near the read endpoints (above `list_batches`):

```python
def build_batch_view(batch) -> dict:
    """Canonical batch shape the FE can trust. Sources `quantity` from the
    harvest_record (the two-step create path never set batch.quantity, which is
    the root of the FE quantity=0 bug), and joins the GeoAI authenticity summary
    from the validation_results backref. Pure over attributes — unit-testable."""
    harvest = getattr(batch, "harvest_record", None)
    if harvest is not None and harvest.quantity_kg is not None:
        quantity = harvest.quantity_kg
    else:
        quantity = batch.quantity
    val = getattr(batch, "validation", None)
    return {
        "id": batch.id,
        "blockchain_batch_id": batch.blockchain_batch_id,
        "farmer_id": batch.farmer_id,
        "current_state": batch.current_state,
        "quantity": quantity,
        "create_tx_hash": batch.create_tx_hash,
        "harvest_tx_hash": batch.harvest_tx_hash,
        "process_tx_hash": batch.process_tx_hash,
        "lab_verify_tx_hash": batch.lab_verify_tx_hash,
        "packaging_tx_hash": batch.packaging_tx_hash,
        "distribution_tx_hash": batch.distribution_tx_hash,
        "created_at": batch.created_at,
        "harvested_at": batch.harvested_at,
        "processed_at": batch.processed_at,
        "lab_verified_at": batch.lab_verified_at,
        "packaged_at": batch.packaged_at,
        "distributed_at": batch.distributed_at,
        "authenticity": {
            "available": val is not None,
            "status": val.validation_status if val else None,
            "score": val.authenticity_score if val else None,
        },
    }
```

> Note: `batch.validation` is the backref defined on `ValidationResult` (`app/models/geo_ai.py:55`); `batch.harvest_record` is the relationship on `HoneyBatch` (`app/models/batch.py:71`). Both load lazily.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_batch_view_model.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Wire the view-model into the read endpoints**

Replace the bodies of `list_batches` and `get_batch` (`app/routers/batch.py`) to return `build_batch_view(...)`:

```python
@router.get("/", response_model=list[BatchResponse])
def list_batches(skip: int = 0, limit: int = 20, db: Session = Depends(get_db),
                 current_user: dict = Depends(get_current_user)):
    """List batches (paginated) in the canonical view-model shape."""
    batches = (
        db.query(HoneyBatch).order_by(HoneyBatch.id.desc())
        .offset(skip).limit(limit).all()
    )
    return [build_batch_view(b) for b in batches]


@router.get("/{batch_id}", response_model=BatchResponse)
def get_batch(batch_id: str, db: Session = Depends(get_db),
              current_user: dict = Depends(get_current_user)):
    """Get batch detail in the canonical view-model shape."""
    batch = db.query(HoneyBatch).filter(
        HoneyBatch.blockchain_batch_id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return build_batch_view(batch)
```

> `create_simple_batch` currently `return batch` (an ORM object). FastAPI will still coerce it via `from_attributes`, but `quantity`/`authenticity` would then read the ORM (quantity is set on `/simple`, authenticity absent) — acceptable, but for consistency change its final `return batch` to `return build_batch_view(batch)`.

- [ ] **Step 6: Run full suite (no regressions)**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: prior 39 passed + new 5 = 44 passed, 2 skipped.

- [ ] **Step 7: Commit**

```bash
git add app/routers/batch.py app/schemas/batch.py tests/test_batch_view_model.py
git commit -m "feat(batch): canonical batch view-model — fix quantity=0 at source + authenticity summary"
```

### Task P0a-2: Reusable env-ensure helper

**Files:**
- Modify: `app/routers/batch.py` (add `_ensure_environmental_data`)
- Test: `tests/test_ensure_env.py` (new)

- [ ] **Step 1: Write the failing test** (uses a fake db + monkeypatched fetch)

```python
# tests/test_ensure_env.py
from types import SimpleNamespace
import app.routers.batch as batch_mod
from app.routers.batch import _ensure_environmental_data


class _Query:
    def __init__(self, result): self._result = result
    def filter(self, *a, **k): return self
    def first(self): return self._result


class _DB:
    def __init__(self, env_existing, apiary):
        self._env, self._apiary = env_existing, apiary
        self.added = []
    def query(self, model):
        name = getattr(model, "__name__", "")
        if name == "EnvironmentalData": return _Query(self._env)
        if name == "ApiaryLocation": return _Query(self._apiary)
        return _Query(None)
    def add(self, row): self.added.append(row)
    def flush(self): pass


def test_returns_existing_env_without_fetching(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(batch_mod, "fetch_environment_snapshot",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or {})
    env = SimpleNamespace(batch_id=1)
    db = _DB(env_existing=env, apiary=SimpleNamespace(latitude=-0.5, longitude=37.0))
    batch = SimpleNamespace(id=1, apiary_id=4)
    assert _ensure_environmental_data(db, batch) is env
    assert called["n"] == 0  # did not fetch


def test_fetches_and_persists_when_missing(monkeypatch):
    monkeypatch.setattr(batch_mod, "fetch_environment_snapshot",
                        lambda lat, lon: {"temperature": 22.0, "humidity": 65.0,
                                          "rainfall": 80.0, "pressure": 1013.0,
                                          "cloud_cover": 10.0, "wind_speed": 3.0,
                                          "weather_source": "open-meteo"})
    db = _DB(env_existing=None, apiary=SimpleNamespace(latitude=-0.5, longitude=37.0))
    batch = SimpleNamespace(id=1, apiary_id=4)
    env = _ensure_environmental_data(db, batch)
    assert env is not None and env.temperature == 22.0
    assert len(db.added) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ensure_env.py -v`
Expected: FAIL — import error.

- [ ] **Step 3: Implement the helper** (`app/routers/batch.py`, near the other helpers)

```python
def _ensure_environmental_data(db: Session, batch) -> "EnvironmentalData | None":
    """Guarantee an environmental_data row exists for a batch, fetching+persisting
    a snapshot from the batch's apiary coords if missing. Idempotent: returns the
    existing row when present (so preview and submit reuse the SAME snapshot →
    identical predicted values → anchored == reviewed). Staged (flush, not commit);
    the caller's commit/rollback owns durability. Returns None if no apiary coords."""
    existing = db.query(EnvironmentalData).filter(
        EnvironmentalData.batch_id == batch.id
    ).first()
    if existing is not None:
        return existing
    if batch.apiary_id is None:
        return None
    apiary = db.query(ApiaryLocation).filter(
        ApiaryLocation.id == batch.apiary_id
    ).first()
    if apiary is None:
        return None
    snap = fetch_environment_snapshot(apiary.latitude, apiary.longitude)
    env = EnvironmentalData(batch_id=batch.id, **snap)
    db.add(env)
    db.flush()
    return env
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ensure_env.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/routers/batch.py tests/test_ensure_env.py
git commit -m "feat(env): reusable _ensure_environmental_data helper (idempotent, staged)"
```

---

# PHASE P0b — Lab pre-image redesign + scoring + preview + lab-verify rewrite (HEADLINE, ⛓)

This is the highest-risk phase: a canonical-hash change. Order matters — migration, then payload+tests, then the flow, then a local-Hardhat three-way check before moving on.

### Task P0b-1: GeoAI compute/persist split (no behavior change yet, just refactor)

**Files:**
- Modify: `app/services/geo_ai.py`
- Test: `tests/test_geoai_compute.py` (new)

- [ ] **Step 1: Write the failing test** (compute-only fns return dicts, never touch db)

```python
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
```

> `importorskip` keeps this green in environments without the ML deps installed; it runs for real in the venv.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_geoai_compute.py -v`
Expected: FAIL — `compute_validation` not defined.

- [ ] **Step 3: Refactor `geo_ai.py`** — extract compute-only fns; keep `*_and_save` as thin persist wrappers; exclude sucrose; decouple pollen.

Replace the `_triangulation` pollen coupling and add the split. Key edits:

```python
# In _triangulation: when pollen_density is None, treat it as region-expected
# (decouples the prediction from the lab measurement).
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
    # Decoupled: if no measured pollen is supplied, use the region-expected
    # value so pollen consistency is neutral (1.0) and the prediction is
    # independent of the lab pollen it will later be compared against.
    eff_pollen   = exp_pollen if pollen_density is None else pollen_density
    pollen_cons  = 1.0 if eff_pollen >= exp_pollen else eff_pollen / max(exp_pollen, 1)
    score = flora_match*0.35 + dist_score*0.25 + flower_align*0.25 + pollen_cons*0.15
    return { ...unchanged dict... }
```

```python
def compute_prediction(latitude, longitude, altitude, vegetation_type,
                       harvest_date, temperature, humidity, rainfall, ndvi) -> dict:
    """Pure prediction — NO db write, NO lab pollen. Returns predicted_* +
    confidence + triangulation components."""
    _ensure_loaded()
    month  = harvest_date.month
    season = "dry" if month in [1, 2, 6, 7, 8] else "rainy"
    region = _get_region(latitude, longitude)
    vegetation_type = region  # encoder vocab IS the region labels
    tri = _triangulation(latitude, longitude, month, vegetation_type, pollen_density=None)
    flowering = _get_flowering(latitude, longitude, month)
    sugar_boost_score = float(np.mean([f["sugar_boost"] for f in flowering])) if flowering else 0.5
    feature_dict = { ...unchanged... }
    features = [feature_dict[col] for col in FEATURE_COLS]
    X_sc = scaler.transform([features])
    preds, errors = {}, []
    for target, m in ensemble_models.items():
        rf_p  = m["rf"].predict(X_sc)[0]
        xgb_p = m["xgb"].predict(X_sc)[0]
        final = m["meta"].predict([[rf_p, xgb_p]])[0]
        preds[m["pred_col"]] = round(float(final), 4)
        errors.append(abs(rf_p - xgb_p) / (abs(rf_p) + 1e-6))
    conf = round(float(np.clip(1.0 - np.mean(errors), 0, 1)), 4)
    return {
        "predicted_moisture": preds["predicted_moisture"],
        "predicted_sugar":    preds["predicted_sugar"],
        "predicted_hmf":      preds["predicted_hmf"],
        "confidence_score":   conf,
        "region_detected":    tri["region_detected"],
        "flowering_species":  ",".join(tri["flowering_species"]),
        "triangulation_score": tri["triangulation_score"],
        "flora_match_score":  tri["flora_match_score"],
        "dist_to_zone_km":    tri["dist_to_zone_km"],
        "n_flowering_species": tri["n_flowering_species"],
    }


def compute_validation(prediction: dict, actual_moisture, actual_hmf, actual_sugar=None) -> dict:
    """Pure scoring — NO db write. Sucrose EXCLUDED from phys_match this sprint
    (model target mislabeled); accepted only so callers can pass it without error."""
    _ensure_loaded()
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
    tri = prediction.get("triangulation_score") or 0.5
    conf = prediction.get("confidence_score") or 0.5
    auth = round(float(np.clip(mean_phys*0.50 + tri*0.35 + conf*0.15, 0, 1)), 4)
    status = "verified" if auth >= 0.80 else "suspicious" if auth >= THRESHOLD else "flagged"
    return {
        "authenticity_score": auth,
        "is_valid": auth >= THRESHOLD,
        "validation_status": status,
        "phys_match_score": round(mean_phys, 4),
        "triangulation_score": round(tri, 4),
        "confidence_score": round(conf, 4),
    }
```

Then make the persist wrappers call the compute fns (preserve existing signatures so `routers/geo_ai.py`'s GET/`/result` and any caller keep working):

```python
def predict_and_save(db, batch_id, latitude, longitude, altitude, vegetation_type,
                     harvest_date, temperature, humidity, rainfall, ndvi, pollen_density):
    # pollen_density kept in signature for back-compat but no longer used (decoupled)
    p = compute_prediction(latitude, longitude, altitude, vegetation_type,
                           harvest_date, temperature, humidity, rainfall, ndvi)
    record = GeoAIPrediction(batch_id=batch_id, **{
        k: p[k] for k in ("predicted_moisture","predicted_sugar","predicted_hmf",
                          "confidence_score","region_detected","flowering_species",
                          "triangulation_score","flora_match_score","dist_to_zone_km",
                          "n_flowering_species")})
    db.add(record); db.commit(); db.refresh(record)
    return record


def validate_and_save(db, batch_id, prediction, actual_moisture, actual_sugar, actual_hmf):
    pred_dict = {"predicted_moisture": prediction.predicted_moisture,
                 "predicted_sugar": prediction.predicted_sugar,
                 "predicted_hmf": prediction.predicted_hmf,
                 "triangulation_score": prediction.triangulation_score,
                 "confidence_score": prediction.confidence_score}
    v = compute_validation(pred_dict, actual_moisture, actual_hmf, actual_sugar)
    record = ValidationResult(batch_id=batch_id, prediction_id=prediction.id, **{
        k: v[k] for k in ("authenticity_score","is_valid","validation_status",
                          "phys_match_score","triangulation_score","confidence_score")})
    db.add(record); db.commit(); db.refresh(record)
    return record
```

- [ ] **Step 4: Add the rule-based explanation generator** (`app/services/geo_ai.py`)

```python
def build_explanation(prediction: dict, validation: dict,
                      actual_moisture, actual_hmf) -> str:
    """Deterministic, offline, English rule-based explanation. Anchored on chain
    as a proof artifact (English is fine — the consumer view localizes the BAND,
    not this prose). Built only from rounded components, so re-running it server-
    side at submit reproduces the exact string hashed."""
    region = prediction.get("region_detected") or "unknown"
    tri = prediction.get("triangulation_score") or 0.0
    tri_word = "strong" if tri >= 0.7 else "moderate" if tri >= 0.4 else "weak"
    pm = prediction.get("predicted_moisture")
    ph = prediction.get("predicted_hmf")
    status = validation.get("validation_status", "flagged")
    am = "n/a" if actual_moisture is None else actual_moisture
    ah = "n/a" if actual_hmf is None else actual_hmf
    return (
        f"Origin region detected: {region}. "
        f"Moisture {am} vs expected {pm}; HMF {ah} vs expected {ph}. "
        f"{tri_word.capitalize()} origin triangulation ({round(tri*100)}%). "
        f"Sugar measured but not scored (model target under review). "
        f"Verdict: {status}."
    )
```

- [ ] **Step 5: Run the compute test + full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/test_geoai_compute.py -v && .venv/Scripts/python.exe -m pytest -q`
Expected: compute tests PASS; full suite still green.

- [ ] **Step 6: Commit**

```bash
git add app/services/geo_ai.py tests/test_geoai_compute.py
git commit -m "refactor(geoai): compute/persist split, exclude sucrose, decouple pollen, rule-based explanation"
```

### Task P0b-2: Migration — drop 2 cols, add 6 cols on lab_results

**Files:**
- Create: `alembic/versions/f1a2b3c4d5e6_sprint13_lab_authenticity_cols.py`
- Modify: `app/models/lab_result.py`

- [ ] **Step 1: Update the model first** (`app/models/lab_result.py`) — remove `purity_score`, `passed_quality_check`; add the 6:

```python
    moisture_content = Column(Float, nullable=True)
    sucrose_level = Column(Float, nullable=True)
    hmf_level = Column(Float, nullable=True)
    pollen_density = Column(Float, nullable=True)

    # Sprint 13: GeoAI authenticity, anchored inside the lab proof pre-image.
    predicted_moisture = Column(Float, nullable=True)
    predicted_sugar = Column(Float, nullable=True)
    predicted_hmf = Column(Float, nullable=True)
    authenticity_score = Column(Float, nullable=True)
    validation_status = Column(String, nullable=True)   # verified|suspicious|flagged
    explanation = Column(String, nullable=True)

    laboratory_name = Column(String, nullable=True)
    analyst_name = Column(String, nullable=True)
    certificate_number = Column(String, nullable=True)
    notes = Column(String, nullable=True)
```

(Delete the `purity_score` and `passed_quality_check` Column lines and the unused `Boolean` import.)

- [ ] **Step 2: Hand-write the migration** (explicit ops; autogenerate is fine too but be explicit for the drops)

```python
# alembic/versions/f1a2b3c4d5e6_sprint13_lab_authenticity_cols.py
"""sprint13: drop purity_score+passed_quality_check, add authenticity cols to lab_results"""
from alembic import op
import sqlalchemy as sa

revision = "f1a2b3c4d5e6"
down_revision = "e2f3a4b5c6d7"   # current head (Sprint 12 geo_ai tables)
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("lab_results", sa.Column("predicted_moisture", sa.Float(), nullable=True))
    op.add_column("lab_results", sa.Column("predicted_sugar", sa.Float(), nullable=True))
    op.add_column("lab_results", sa.Column("predicted_hmf", sa.Float(), nullable=True))
    op.add_column("lab_results", sa.Column("authenticity_score", sa.Float(), nullable=True))
    op.add_column("lab_results", sa.Column("validation_status", sa.String(), nullable=True))
    op.add_column("lab_results", sa.Column("explanation", sa.String(), nullable=True))
    op.drop_column("lab_results", "purity_score")
    op.drop_column("lab_results", "passed_quality_check")


def downgrade():
    op.add_column("lab_results", sa.Column("passed_quality_check", sa.Boolean(), nullable=True))
    op.add_column("lab_results", sa.Column("purity_score", sa.Float(), nullable=True))
    op.drop_column("lab_results", "explanation")
    op.drop_column("lab_results", "validation_status")
    op.drop_column("lab_results", "authenticity_score")
    op.drop_column("lab_results", "predicted_hmf")
    op.drop_column("lab_results", "predicted_sugar")
    op.drop_column("lab_results", "predicted_moisture")
```

- [ ] **Step 3: Apply + round-trip the migration**

Run (DB at :5433, see CLAUDE.md):
```bash
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic downgrade -1
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic current   # expect f1a2b3c4d5e6 (head)
```
Expected: clean up/down/up; head is `f1a2b3c4d5e6`.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/f1a2b3c4d5e6_sprint13_lab_authenticity_cols.py app/models/lab_result.py
git commit -m "feat(db): lab_results authenticity columns; drop purity_score+passed_quality_check (alembic f1a2b3c4d5e6)"
```

### Task P0b-3: Redesign `_lab_result_canonical_payload` + `_q4` + determinism tests

**Files:**
- Modify: `app/routers/batch.py` (`_lab_result_canonical_payload`, add `_q4`)
- Modify: `tests/test_verify_endpoint.py` (fixture: drop 2 fields, add 6)
- Create: `tests/test_lab_canonical_payload.py`

- [ ] **Step 1: Write the failing determinism test** (float↔Decimal parity — catches the type trap WITHOUT a live DB)

```python
# tests/test_lab_canonical_payload.py
"""Lock the Sprint 13 lab pre-image. The new ML-derived numeric fields must hash
identically whether they arrive as float or Decimal (a Numeric column or psycopg
Decimal roundtrip must not silently break the anchor). Mirrors the metadata-hash
Decimal/float parity guard."""
from decimal import Decimal
from types import SimpleNamespace
from app.routers.batch import _lab_result_canonical_payload, _q4
from app.services.blockchain import BlockchainService


def _row(**o):
    base = dict(
        batch_id=1, moisture_content=19.0, sucrose_level=4.0, hmf_level=28.0,
        pollen_density=30000.0, predicted_moisture=19.1234, predicted_sugar=75.5,
        predicted_hmf=28.4321, authenticity_score=0.79, validation_status="suspicious",
        explanation="Origin region detected: central_highlands. Verdict: suspicious.",
        laboratory_name="KEBS", analyst_name="A", certificate_number="C-1", notes="ok",
        lab_proof_hash=None,
    )
    base.update(o)
    return SimpleNamespace(**base)


def _h(row):
    return BlockchainService.compute_data_hash(_lab_result_canonical_payload(row)).hex()


def test_predicted_and_score_float_decimal_parity():
    f = _row(predicted_moisture=19.1234, authenticity_score=0.79)
    d = _row(predicted_moisture=Decimal("19.1234"), authenticity_score=Decimal("0.7900"))
    assert _h(f) == _h(d)


def test_q4_quantizes_consistently():
    assert _q4(0.79) == _q4(Decimal("0.7900")) == "0.7900"
    assert _q4(None) is None


def test_dropped_fields_are_not_in_payload():
    payload = _lab_result_canonical_payload(_row())
    assert "purity_score" not in payload
    assert "passed_quality_check" not in payload
    assert {"predicted_moisture", "authenticity_score", "validation_status",
            "explanation"} <= set(payload)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_lab_canonical_payload.py -v`
Expected: FAIL — `_q4` not defined / old payload still has `purity_score`.

- [ ] **Step 3: Implement `_q4` + redesign the payload** (`app/routers/batch.py`)

```python
def _q4(x) -> str | None:
    """Render an ML-derived numeric as a fixed-precision (4dp) string so the
    canonical hash is independent of float-vs-Decimal column typing. Mirrors the
    expected_yield_kg quantize pattern in _metadata_record_canonical_payload."""
    if x is None:
        return None
    return str(Decimal(str(x)).quantize(Decimal("0.0001")))


def _lab_result_canonical_payload(row: LabResult) -> dict:
    """Sprint 13 pre-image. Drops purity_score + passed_quality_check; adds the
    anchored GeoAI authenticity fields. Existing measured metrics stay native
    float (proven on Sepolia); the new ML floats route through _q4 (type-stable).
    `explanation` + `validation_status` are stored strings — round-trip identical."""
    return {
        "batch_id": row.batch_id,
        "moisture_content": row.moisture_content,
        "sucrose_level": row.sucrose_level,
        "hmf_level": row.hmf_level,
        "pollen_density": row.pollen_density,
        "predicted_moisture": _q4(row.predicted_moisture),
        "predicted_sugar": _q4(row.predicted_sugar),
        "predicted_hmf": _q4(row.predicted_hmf),
        "authenticity_score": _q4(row.authenticity_score),
        "validation_status": row.validation_status,
        "explanation": row.explanation,
        "laboratory_name": row.laboratory_name,
        "analyst_name": row.analyst_name,
        "certificate_number": row.certificate_number,
        "notes": row.notes,
    }
```

- [ ] **Step 4: Update `tests/test_verify_endpoint.py` fixture** — in `_row()`, delete `purity_score=95.5,` and `passed_quality_check=True,`; add:

```python
        predicted_moisture=19.12, predicted_sugar=75.5, predicted_hmf=28.4,
        authenticity_score=0.79, validation_status="suspicious",
        explanation="Verdict: suspicious.",
```

(The three existing three-way match/tamper/zero tests still pass unchanged — they only need the fixture to match the new payload field set. The tamper test mutates `moisture_content`, still valid.)

- [ ] **Step 5: Run both lab hash test files + full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/test_lab_canonical_payload.py tests/test_verify_endpoint.py -v && .venv/Scripts/python.exe -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add app/routers/batch.py tests/test_lab_canonical_payload.py tests/test_verify_endpoint.py
git commit -m "feat(⛓): redesign lab canonical pre-image — anchor authenticity, _q4 type-stable floats"
```

### Task P0b-4: Schemas — LabVerifyRequest/Public + Preview request/response

**Files:**
- Modify: `app/schemas/batch.py`

- [ ] **Step 1: Edit `LabVerifyRequest`** — remove `purity_score` + `passed_quality_check`; it now carries only tester-entered actuals + lab metadata. (No required fields remain; that's intentional — server computes the rest.)

```python
class LabVerifyRequest(BaseModel):
    """Tester-entered actual metrics (S2→S3). Authenticity (predicted_*, score,
    validation_status, explanation) is computed server-side and is NOT accepted
    from the client — the server never trusts a client-passed score."""
    moisture_content: Optional[float] = Field(default=None, ge=0, le=100)
    sucrose_level: Optional[float] = Field(default=None, ge=0)
    hmf_level: Optional[float] = Field(default=None, ge=0)
    pollen_density: Optional[float] = Field(default=None, ge=0)
    laboratory_name: Optional[str] = None
    analyst_name: Optional[str] = None
    certificate_number: Optional[str] = None
    notes: Optional[str] = None
```

- [ ] **Step 2: Edit `LabResultPublic`** — remove `purity_score` + `passed_quality_check`; add the new fields:

```python
class LabResultPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    batch_id: int
    moisture_content: Optional[float] = None
    sucrose_level: Optional[float] = None
    hmf_level: Optional[float] = None
    pollen_density: Optional[float] = None
    predicted_moisture: Optional[float] = None
    predicted_sugar: Optional[float] = None
    predicted_hmf: Optional[float] = None
    authenticity_score: Optional[float] = None
    validation_status: Optional[str] = None
    explanation: Optional[str] = None
    laboratory_name: Optional[str] = None
    analyst_name: Optional[str] = None
    certificate_number: Optional[str] = None
    notes: Optional[str] = None
    lab_proof_hash: Optional[str] = None
    tested_at: Optional[datetime] = None
```

- [ ] **Step 3: Add Preview request/response schemas**

```python
class LabPreviewRequest(BaseModel):
    """Actual metrics the tester entered, for a non-persisting authenticity preview."""
    moisture_content: Optional[float] = Field(default=None, ge=0, le=100)
    sucrose_level: Optional[float] = Field(default=None, ge=0)
    hmf_level: Optional[float] = Field(default=None, ge=0)
    pollen_density: Optional[float] = Field(default=None, ge=0)


class LabPreviewResponse(BaseModel):
    predicted_moisture: Optional[float] = None
    predicted_sugar: Optional[float] = None
    predicted_hmf: Optional[float] = None
    authenticity_score: Optional[float] = None
    validation_status: Optional[str] = None
    explanation: Optional[str] = None
    region_detected: Optional[str] = None
    triangulation_score: Optional[float] = None
    confidence_score: Optional[float] = None
    phys_match_score: Optional[float] = None
```

- [ ] **Step 4: Smoke-import + commit**

Run: `.venv/Scripts/python.exe -c "import app.schemas.batch"` (no error)

```bash
git add app/schemas/batch.py
git commit -m "feat(schema): lab request/public drop pass-fail+purity; add preview request/response"
```

### Task P0b-5: `POST /geo-ai/{id}/preview` (compute-only) + remove standalone predict/validate

**Files:**
- Modify: `app/routers/geo_ai.py`
- Modify: `app/routers/batch.py` (import the env-ensure + compute fns — preview lives where it has db + helpers)

> **Placement:** keep `preview` in the geo_ai router (int id) per the locked plan, but it needs `_ensure_environmental_data`. Import that helper from `app.routers.batch`. (No circular import: `geo_ai` already imports models, and `batch` doesn't import `geo_ai` at module scope — it imports `ValidationResult` lazily inside `verify_batch`.)

- [ ] **Step 1: Rewrite `app/routers/geo_ai.py`** — remove `run_prediction` + `run_validation` (POST predict/validate); add `preview`; keep `get_result`.

```python
# app/routers/geo_ai.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_roles
from app.models.batch import HoneyBatch
from app.models.apiary import ApiaryLocation
from app.models.geo_ai import GeoAIPrediction, ValidationResult
from app.models.lab_result import LabResult
from app.schemas.batch import LabPreviewRequest, LabPreviewResponse
from app.services.geo_ai import (
    compute_prediction, compute_validation, build_explanation, GeoAIModelError,
)
from app.routers.batch import _ensure_environmental_data

router = APIRouter(prefix="/geo-ai", tags=["Geo-AI"])


@router.post("/{batch_id}/preview", response_model=LabPreviewResponse)
def preview_authenticity(
    batch_id: int,
    data: LabPreviewRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles([
        "lab_test_officer", "on_ground_officer", "admin", "super_admin"
    ])),
):
    """Non-persisting authenticity preview for the merged lab panel's 'Run Score'.
    Persists the ENV snapshot (so submit reuses it → identical anchored result) but
    does NOT write geo_ai_predictions / validation_results. Server computes the
    score from the tester's entered actuals; the client never supplies a score."""
    batch = db.query(HoneyBatch).filter(HoneyBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(404, "Batch not found")
    apiary = db.query(ApiaryLocation).filter(ApiaryLocation.id == batch.apiary_id).first()
    if not apiary:
        raise HTTPException(400, "Apiary not recorded for this batch")

    env = _ensure_environmental_data(db, batch)
    if env is None:
        raise HTTPException(400, "Environmental data unavailable (no apiary coords)")
    db.commit()  # persist the env snapshot so submit reuses the same inputs

    try:
        pred = compute_prediction(
            latitude=apiary.latitude, longitude=apiary.longitude,
            altitude=apiary.altitude or 1000.0,
            vegetation_type=apiary.vegetation_type or "unknown",
            harvest_date=batch.harvested_at or batch.created_at,
            temperature=env.temperature or 22.0, humidity=env.humidity or 65.0,
            rainfall=env.rainfall or 80.0, ndvi=0.55,
        )
        val = compute_validation(pred, actual_moisture=data.moisture_content,
                                 actual_hmf=data.hmf_level, actual_sugar=data.sucrose_level)
    except GeoAIModelError as e:
        raise HTTPException(503, f"GeoAI model unavailable: {e}")

    explanation = build_explanation(pred, val, data.moisture_content, data.hmf_level)
    return LabPreviewResponse(
        predicted_moisture=pred["predicted_moisture"],
        predicted_sugar=pred["predicted_sugar"],
        predicted_hmf=pred["predicted_hmf"],
        authenticity_score=val["authenticity_score"],
        validation_status=val["validation_status"],
        explanation=explanation,
        region_detected=pred["region_detected"],
        triangulation_score=pred["triangulation_score"],
        confidence_score=pred["confidence_score"],
        phys_match_score=val["phys_match_score"],
    )


@router.get("/{batch_id}/result")
def get_result(batch_id: int, db: Session = Depends(get_db)):
    """Public — stored prediction + validation + actual lab metrics. (Lab-verify is
    now the sole writer of these rows; this is read-only.)"""
    if not db.query(HoneyBatch).filter(HoneyBatch.id == batch_id).first():
        raise HTTPException(404, "Batch not found")
    prediction = db.query(GeoAIPrediction).filter(GeoAIPrediction.batch_id == batch_id).first()
    validation = db.query(ValidationResult).filter(ValidationResult.batch_id == batch_id).first()
    if not prediction:
        raise HTTPException(404, "No prediction found — run lab verification first")
    lab = db.query(LabResult).filter(LabResult.batch_id == batch_id).first()
    return {
        "batch_id": batch_id,
        "prediction": prediction,
        "validation": validation,
        "lab": {
            "moisture_content": lab.moisture_content if lab else None,
            "sucrose_level": lab.sucrose_level if lab else None,
            "hmf_level": lab.hmf_level if lab else None,
        },
    }
```

> The `from app.routers.batch import _ensure_environmental_data` at module scope is safe because `main.py` imports `batch` before `geo_ai` (verify import order; if a circular import surfaces, move the import inside `preview_authenticity`).

- [ ] **Step 2: Verify app boots + routes present**

Run: `.venv/Scripts/python.exe -c "from app.main import app; print([r.path for r in app.routes if 'geo-ai' in r.path])"`
Expected: `['/geo-ai/{batch_id}/preview', '/geo-ai/{batch_id}/result']` (no `/predict`, `/validate`).

- [ ] **Step 3: Commit**

```bash
git add app/routers/geo_ai.py
git commit -m "feat(geoai): compute-only preview endpoint; remove standalone predict/validate (lab-verify is sole writer)"
```

### Task P0b-6: Rewrite `lab-verify` — server-authoritative compute + anchor everything in one tx

**Files:**
- Modify: `app/routers/batch.py` (`anchor_lab_proof`)

- [ ] **Step 1: Rewrite the handler body** (`anchor_lab_proof`). After the state + existing-row checks, before building the lab row:

```python
    # Ensure env (idempotent — preview already persisted it; reuse the SAME snapshot
    # so the anchored prediction == what the tester previewed).
    env = _ensure_environmental_data(db, batch)
    if env is None:
        raise HTTPException(400, "Environmental data unavailable (no apiary coords)")
    apiary = db.query(ApiaryLocation).filter(ApiaryLocation.id == batch.apiary_id).first()
    if apiary is None:
        raise HTTPException(400, "Apiary not recorded for this batch")

    # Server AUTHORITATIVELY recomputes (deterministic → matches preview); never
    # trusts a client-passed score.
    from app.services.geo_ai import (
        compute_prediction, compute_validation, build_explanation, GeoAIModelError,
    )
    try:
        pred = compute_prediction(
            latitude=apiary.latitude, longitude=apiary.longitude,
            altitude=apiary.altitude or 1000.0,
            vegetation_type=apiary.vegetation_type or "unknown",
            harvest_date=batch.harvested_at or batch.created_at,
            temperature=env.temperature or 22.0, humidity=env.humidity or 65.0,
            rainfall=env.rainfall or 80.0, ndvi=0.55,
        )
        val = compute_validation(pred, actual_moisture=data.moisture_content,
                                 actual_hmf=data.hmf_level, actual_sugar=data.sucrose_level)
    except GeoAIModelError as e:
        raise HTTPException(503, f"GeoAI model unavailable: {e}")
    explanation = build_explanation(pred, val, data.moisture_content, data.hmf_level)

    # Persist lab_results WITH authenticity (the anchored row).
    row = LabResult(
        batch_id=batch.id,
        moisture_content=data.moisture_content, sucrose_level=data.sucrose_level,
        hmf_level=data.hmf_level, pollen_density=data.pollen_density,
        predicted_moisture=pred["predicted_moisture"], predicted_sugar=pred["predicted_sugar"],
        predicted_hmf=pred["predicted_hmf"], authenticity_score=val["authenticity_score"],
        validation_status=val["validation_status"], explanation=explanation,
        laboratory_name=data.laboratory_name, analyst_name=data.analyst_name,
        certificate_number=data.certificate_number, notes=data.notes,
    )
    db.add(row)
    db.flush()

    # Sole writer of the geo rows (so /verify authenticity + /geo-ai/result keep
    # working). Staged in the SAME tx → chain failure rolls these back too.
    from app.models.geo_ai import GeoAIPrediction, ValidationResult
    geo_pred = GeoAIPrediction(batch_id=batch.id, **{
        k: pred[k] for k in ("predicted_moisture","predicted_sugar","predicted_hmf",
                             "confidence_score","region_detected","flowering_species",
                             "triangulation_score","flora_match_score","dist_to_zone_km",
                             "n_flowering_species")})
    db.add(geo_pred)
    db.flush()
    db.add(ValidationResult(batch_id=batch.id, prediction_id=geo_pred.id, **{
        k: val[k] for k in ("authenticity_score","is_valid","validation_status",
                            "phys_match_score","triangulation_score","confidence_score")}))
    db.flush()

    proof_payload = _lab_result_canonical_payload(row)
    proof_hash = blockchain_service.compute_data_hash(proof_payload)
    batch_id_bytes = _batch_id_to_bytes(batch_id)
```

The chain-anchor try/except block below stays exactly as-is (ContractLogicError → rollback+400; ReceiptPendingError → persist proof+tx+202; generic → rollback+502; success → set proof hash + state + tx + `lab_verified_at` + commit).

> Add `from app.models.apiary import ApiaryLocation` to the imports at the top if not already there (it is — line 23).

- [ ] **Step 2: Manual local check (needs live Hardhat + walked batch — DEBUG-RUNBOOK §13)**

Walk a fresh batch to PROCESSED (centroid apiary `-0.5, 37.0` per RUNBOOK §14.1), then:
```bash
TOK=<lab_test_officer JWT>; ID=0x<hex batch id>
curl -s -X POST http://127.0.0.1:8000/batches/$ID/lab-verify -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{"moisture_content":19,"sucrose_level":4,"hmf_level":28,"pollen_density":30000,"laboratory_name":"KEBS","analyst_name":"E2E","certificate_number":"C-1","notes":"s13"}' | jq
curl -s http://127.0.0.1:8000/batches/$ID/verify | jq '.verification.lab.match, .lab_result.authenticity_score, .lab_result.validation_status'
```
Expected: `new_state: LAB_VERIFIED` (or 202 pending), `verification.lab.match == true`, an `authenticity_score` + `validation_status` present.

- [ ] **Step 3: Commit**

```bash
git add app/routers/batch.py
git commit -m "feat(⛓): lab-verify recomputes authenticity server-side + anchors it; sole writer of geo rows"
```

### Task P0b-7: Update e2e + integration-test lab bodies; re-baseline RUNBOOK §14.2

**Files:**
- Modify: `scripts/e2e_lifecycle.py:225-233`
- Modify: `tests/test_lifecycle_integration.py:~145-155`
- Modify: `DEBUG-RUNBOOK.md` §14.2

- [ ] **Step 1: e2e lab body** — replace lines 226–232 (remove `purity_score`, `passed_quality_check`):

```python
        lab_resp = _post(client, f"/batches/{batch_id}/lab-verify", {
            "moisture_content": 19.0,
            "sucrose_level": 4.0,
            "hmf_level": 28.0,
            "pollen_density": 30000,
            "laboratory_name": "KEBS Lab #1",
            "analyst_name": "Sprint13 E2E",
            "certificate_number": "abcd1234",
        }, headers=_auth(lab_token))
```

> Ensure the e2e seeds the apiary at a centroid (`-0.5, 37.0`) so `compute_prediction` gets an in-vocab region. Check the apiary-seed call in the script; if it uses arbitrary coords, change to `-0.5, 37.0`.

- [ ] **Step 2: Integration test lab body** (`tests/test_lifecycle_integration.py`) — drop `purity_score`/`passed_quality_check` from the lab-verify dict (lines ~151–152), keep the rest.

- [ ] **Step 3: RUNBOOK §14.2** — re-baseline the score table. After decoupling pollen (region-derived → `pollen_cons=1.0`) the triangulation no longer depends on entered pollen. Re-run the central_highlands case and record the new score. Replace the §14.2 table values with the observed numbers and note "pollen decoupled (Sprint 13) — score independent of entered pollen_density."

- [ ] **Step 4: Run unit suite** (integration test is marker-gated; run later with a live backend)

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: green (44+ passed, 2 skipped).

- [ ] **Step 5: Commit**

```bash
git add scripts/e2e_lifecycle.py tests/test_lifecycle_integration.py DEBUG-RUNBOOK.md
git commit -m "test(⛓): e2e+integration lab bodies for new pre-image; re-baseline RUNBOOK §14.2 scores"
```

### Task P0b-8: Local-Hardhat full e2e gate

- [ ] **Step 1:** Truncate DB + re-enroll (DEBUG-RUNBOOK §3), Hardhat fresh + deploy (§2). Then:

```bash
.venv/Scripts/python.exe scripts/e2e_lifecycle.py --base-url http://127.0.0.1:8000 --invite-code "ApiChain@SuperAdmin2025"
```
Expected: `E2E LIFECYCLE SUCCESS`, all 7 `verification.*.match` true (note: packaging still uses OLD pre-image here — that's fine, P0d changes it next; the lab pre-image is the one under test). ~15s.

> Do NOT run the Sepolia evidence yet — it comes after P0d so a single run covers both new pre-images.

---

# PHASE P0d — Packaging pre-image change (drop qr_codes, keep jar_ids) (⛓)

### Task P0d-1: Migration — drop `qr_codes` from packaging_records

**Files:**
- Create: `alembic/versions/a7b8c9d0e1f2_sprint13_drop_qr_codes.py`
- Modify: `app/models/packaging_record.py` (remove `qr_codes` column + unused `JSON`? — `jar_ids` still uses JSON, keep the import)

- [ ] **Step 1:** Remove `qr_codes = Column(JSON, nullable=False)` from `app/models/packaging_record.py` (keep `jar_ids`).

- [ ] **Step 2:** Migration:

```python
# alembic/versions/a7b8c9d0e1f2_sprint13_drop_qr_codes.py
"""sprint13: drop qr_codes from packaging_records (one QR per batch)"""
from alembic import op
import sqlalchemy as sa

revision = "a7b8c9d0e1f2"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("packaging_records", "qr_codes")


def downgrade():
    op.add_column("packaging_records",
                  sa.Column("qr_codes", sa.JSON(), nullable=False,
                            server_default=sa.text("'[]'::json")))
```

- [ ] **Step 3:** `alembic upgrade head` → `downgrade -1` → `upgrade head`; `alembic current` → `a7b8c9d0e1f2`.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/a7b8c9d0e1f2_sprint13_drop_qr_codes.py app/models/packaging_record.py
git commit -m "feat(db): drop packaging_records.qr_codes (alembic a7b8c9d0e1f2)"
```

### Task P0d-2: Payload + schema + handler + tests for packaging

**Files:**
- Modify: `app/routers/batch.py` (`_packaging_record_canonical_payload`, `record_packaging`)
- Modify: `app/schemas/batch.py` (`PackagingRequest`, `PackagingRecordPublic`)
- Modify: `tests/test_packaging_hash.py`

- [ ] **Step 1: Update the packaging hash test fixture first** (`tests/test_packaging_hash.py`) — remove `qr_codes=[...]` from `_row()`. The three tests stay (tamper test mutates `jar_ids`, still valid).

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_packaging_hash.py -v`
Expected: FAIL — payload still references `row.qr_codes` (AttributeError on SimpleNamespace without it).

- [ ] **Step 3: Redesign the payload** (`app/routers/batch.py`):

```python
def _packaging_record_canonical_payload(row: PackagingRecord) -> dict:
    """Sprint 13 pre-image — one QR per batch, so qr_codes is gone. jar_ids stays
    (records physical jar identity/count); unit_count already equals the jar count."""
    return {
        "batch_id": row.batch_id,
        "unit_count": row.unit_count,
        "jar_ids": list(row.jar_ids) if row.jar_ids else [],
        "notes": row.notes,
    }
```

- [ ] **Step 4: Edit `PackagingRequest`** — remove `qr_codes` field + its validator branch:

```python
class PackagingRequest(BaseModel):
    """Data for recording packaging (S3→S4). One consumer QR per batch is derived
    from the batch id; jars are still recorded for count/identity."""
    unit_count: int = Field(ge=1)
    jar_ids: list[str] = Field(min_length=1)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _check_count_consistency(self) -> "PackagingRequest":
        if len(self.jar_ids) != self.unit_count:
            raise ValueError(
                f"jar_ids length ({len(self.jar_ids)}) must equal unit_count ({self.unit_count})"
            )
        return self
```

- [ ] **Step 5: Edit `PackagingRecordPublic`** — remove `qr_codes: list[str]`.

- [ ] **Step 6: Edit `record_packaging` handler** — remove `qr_codes=data.qr_codes,` from the `PackagingRecord(...)` constructor (`app/routers/batch.py:765`).

- [ ] **Step 7: Update e2e + integration package bodies** — `scripts/e2e_lifecycle.py:243-248` and `tests/test_lifecycle_integration.py:~160-166`: remove the `"qr_codes": [...]` line from the package dict.

- [ ] **Step 8: Run packaging tests + full suite**

Run: `.venv/Scripts/python.exe -m pytest tests/test_packaging_hash.py -v && .venv/Scripts/python.exe -m pytest -q`
Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add app/routers/batch.py app/schemas/batch.py tests/test_packaging_hash.py scripts/e2e_lifecycle.py tests/test_lifecycle_integration.py
git commit -m "feat(⛓): packaging pre-image drops qr_codes (keeps jar_ids); one QR per batch"
```

### Task P0d-3: Local-Hardhat e2e gate (both pre-images)

- [ ] **Step 1:** Truncate + re-enroll + fresh Hardhat + deploy. Run `e2e_lifecycle.py`. Expected: `E2E LIFECYCLE SUCCESS`, all 7 `verification.*.match` true — now both lab AND packaging on the new pre-images.

---

# PHASE ⛓ EV — Fresh Sepolia evidence run (after BOTH hash changes)

### Task EV-1: Sepolia evidence

- [ ] **Step 1:** Switch env to Sepolia (DEBUG-RUNBOOK §11: `cp .env .env.hardhat.bak && cp .env.sepolia .env`; confirm `CHAIN_ID=11155111`). Restart uvicorn. Ensure wallets have Sepolia ETH + roles (re-enroll if needed).
- [ ] **Step 2:** Run `e2e_lifecycle.py` against Sepolia (~340s). Expect all 7 `verification.*.match` true on the new lab + packaging pre-images.
- [ ] **Step 3:** Capture evidence into `backend/docs/sepolia-lifecycle-evidence.md` (new batch id, ~6 Etherscan-resolvable tx hashes, wall-clock, the seven match=true). Note the pre-image redesign date.
- [ ] **Step 4:** Restore Hardhat env (`cp .env.hardhat.bak .env && rm .env.hardhat.bak`).
- [ ] **Step 5: Commit**

```bash
git add backend/docs/sepolia-lifecycle-evidence.md
git commit -m "docs(⛓): fresh Sepolia evidence — new lab + packaging pre-images, 7/7 match"
```

> **GATE:** do not start FE headline work until EV-1 is green. A determinism/drift bug surfaces here (expensively); catching it now protects P0c/P1b.

---

# PHASE P0c — FE merged lab+GeoAI panel (HEADLINE)

**Target:** `Apichain-Frontend/apichain-website/src/features/dashboard/TesterDashboard.jsx`. Merge `LabVerifyModal` (the form) and `GeoAIPanel` (predicted-vs-actual) into ONE modal: enter metrics → **Run Authenticity Score** (`/geo-ai/{id}/preview`) → review predicted-vs-actual + score + explanation → inputs **lock** → **Submit Lab Result** (`/batches/{id}/lab-verify`, server recomputes + anchors) → 202-pending handled.

### Task P0c-0: Scoped Vitest setup

**Files:**
- Modify: `Apichain-Frontend/apichain-website/package.json`
- Create: `vitest.config.js`, `src/test/setup.js`

- [ ] **Step 1:** Install dev deps:

```bash
cd "C:/Users/ADMIN/.vscode-cli/ApiChain Kenya/Apichain-Frontend/apichain-website"
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

- [ ] **Step 2:** `vitest.config.js`:

```js
import { defineConfig } from "vitest/config";
export default defineConfig({
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/test/setup.js"] },
});
```

- [ ] **Step 3:** `src/test/setup.js`: `import "@testing-library/jest-dom";`

- [ ] **Step 4:** `package.json` scripts: add `"test": "vitest run"`, `"test:watch": "vitest"`.

- [ ] **Step 5:** Commit `chore(fe): scoped Vitest + RTL setup`.

### Task P0c-1: Pure lab-panel reducer (lock-after-score) + Vitest

**Files:**
- Create: `src/features/dashboard/shared/labPanelReducer.js`
- Create: `src/features/dashboard/shared/labPanelReducer.test.js`

- [ ] **Step 1: Write the failing test**

```js
// labPanelReducer.test.js
import { describe, it, expect } from "vitest";
import { labPanelReducer, initialLabState } from "./labPanelReducer";

describe("labPanelReducer", () => {
  it("starts unlocked with no score", () => {
    expect(initialLabState.locked).toBe(false);
    expect(initialLabState.score).toBe(null);
  });
  it("SCORED locks inputs and stores the preview", () => {
    const s = labPanelReducer(initialLabState, { type: "SCORED", payload: { authenticity_score: 0.79 } });
    expect(s.locked).toBe(true);
    expect(s.score.authenticity_score).toBe(0.79);
  });
  it("EDIT after SCORED clears the score and unlocks (re-run required before submit)", () => {
    let s = labPanelReducer(initialLabState, { type: "SCORED", payload: { authenticity_score: 0.79 } });
    s = labPanelReducer(s, { type: "EDIT", key: "moisture_content", value: "20" });
    expect(s.locked).toBe(false);
    expect(s.score).toBe(null);
    expect(s.values.moisture_content).toBe("20");
  });
  it("EDIT while unlocked just updates values", () => {
    const s = labPanelReducer(initialLabState, { type: "EDIT", key: "hmf_level", value: "28" });
    expect(s.values.hmf_level).toBe("28");
    expect(s.locked).toBe(false);
  });
});
```

- [ ] **Step 2:** `npm run test` → FAIL (module missing).

- [ ] **Step 3: Implement**

```js
// labPanelReducer.js
export const initialLabState = { values: {}, meta: {}, locked: false, score: null };

export function labPanelReducer(state, action) {
  switch (action.type) {
    case "EDIT": {
      const values = { ...state.values, [action.key]: action.value };
      // Editing any metric after scoring invalidates the reviewed score.
      return state.locked
        ? { ...state, values, locked: false, score: null }
        : { ...state, values };
    }
    case "META":
      return { ...state, meta: { ...state.meta, [action.key]: action.value } };
    case "SCORED":
      return { ...state, locked: true, score: action.payload };
    case "RESET":
      return initialLabState;
    default:
      return state;
  }
}
```

- [ ] **Step 4:** `npm run test` → PASS. Commit `feat(fe): lab-panel lock-after-score reducer + tests`.

### Task P0c-2: Merge the modal

**Files:**
- Modify: `src/features/dashboard/TesterDashboard.jsx`
- Modify: `src/i18n/en.json`, `src/i18n/sw.json`

- [ ] **Step 1:** Replace `LabVerifyModal`'s ad-hoc `values`/`passed` state with `useReducer(labPanelReducer, initialLabState)`. Remove the PASS/FAIL verdict block (lines ~767–788) and the `purity_score` METRICS entry (line 673). New `METRICS`:

```js
const METRICS = [
  { key: "moisture_content", label: t("lab.moisture"), hint: "≤ 20%", ok: (v) => v <= 20 },
  { key: "hmf_level", label: t("lab.hmf"), hint: "≤ 40", ok: (v) => v <= 40 },
  { key: "sucrose_level", label: t("lab.sucrose"), hint: t("lab.notScored"), ok: () => true },
  { key: "pollen_density", label: t("lab.pollen"), hint: "informational", ok: () => true },
];
```

- [ ] **Step 2:** Add a **Run Authenticity Score** button (disabled when `locked`) that calls preview:

```js
const runScore = async () => {
  setLoading(true);
  const body = {};
  ["moisture_content","hmf_level","sucrose_level","pollen_density"].forEach((k) => {
    if (state.values[k] !== undefined && state.values[k] !== "") body[k] = Number(state.values[k]);
  });
  const { ok, body: res } = await apiFetch(`/geo-ai/${batch.id}/preview`, {
    method: "POST", body: JSON.stringify(body),
  });
  setLoading(false);
  if (!ok) { showToast(errorMessage(res, t("lab.previewFailed")), "error"); return; }
  dispatch({ type: "SCORED", payload: res });
};
```

- [ ] **Step 3:** Render the predicted-vs-actual table + score badge + explanation from `state.score` when `locked` (reuse the GeoAI table markup from the old `GeoAIPanel`, lines 561–571). Mark the **sugar row** "measured, not scored (under review)". Lock the metric `<input>`s with `disabled={state.locked}`; the `onChange` dispatches `{type:"EDIT"}` (which auto-clears the score).

- [ ] **Step 4:** Gate **Submit Lab Result** on `state.locked && state.score` (must score before submit). Submit posts the actuals to `/batches/${batchId}/lab-verify` (NO `passed_quality_check`, NO score — server recomputes). Keep the existing 202-pending toast branch (`pending ? "anchor in flight…" : "anchored!"`).

- [ ] **Step 5:** Remove the now-duplicated `GeoAIPanel` usage from `BatchDetailsModal` IF the merged lab modal supersedes it — OR keep `GeoAIPanel` read-only in `BatchDetailsModal` but switch its data source to `/geo-ai/{id}/result` only (it already does). Decision: **keep `GeoAIPanel` as a read-only results view** in `BatchDetailsModal` (no "Run check" button — that capability moves into the lab modal). Remove its `run`/`fetchEnv`/predict/validate calls (those endpoints are gone); it now only `load()`s `/result`.

- [ ] **Step 6:** Fix the quantity display (`BatchDetailsModal` line 611): `{batch.quantity ?? 0} kg` now reads the canonical view-model quantity (P0a) — verify it shows the real harvest quantity, not 0.

- [ ] **Step 7:** Add EN/SW keys (`lab.moisture`, `lab.hmf`, `lab.sucrose`, `lab.pollen`, `lab.notScored`, `lab.runScore`, `lab.previewFailed`, `lab.submit`, `lab.locked`, `lab.anchorInFlight`, etc.) to BOTH `en.json` and `sw.json`.

- [ ] **Step 8:** `npm run build && npm run lint` clean. Commit `feat(fe): merged lab+authenticity panel, single submit, lock-after-score`.

### Task P0c-3: Manual test matrix (P0c) — run against live stack

See the **Manual Test Matrix** appendix (rows MM-1…MM-8). Execute the lab-panel rows; record pass/fail.

---

# PHASE P1a — Backend `/verify` consumer fields

### Task P1a-1: Reverse-geocode helper

**Files:**
- Create: `app/services/geocode.py`
- Test: `tests/test_geocode.py`

- [ ] **Step 1: Test (monkeypatch requests):**

```python
# tests/test_geocode.py
import app.services.geocode as g

def test_reverse_geocode_builds_place_string(monkeypatch):
    class _R:
        status_code = 200
        def json(self): return {"address": {"county": "Nyeri", "state": "Central", "country": "Kenya"}}
    monkeypatch.setattr(g.requests, "get", lambda *a, **k: _R())
    assert g.reverse_geocode(-0.42, 36.95) == "Nyeri, Central, Kenya"

def test_reverse_geocode_failsoft_returns_none(monkeypatch):
    def _boom(*a, **k): raise RuntimeError("down")
    monkeypatch.setattr(g.requests, "get", _boom)
    assert g.reverse_geocode(-0.42, 36.95) is None
```

- [ ] **Step 2:** Implement (Nominatim, `User-Agent: AgriScanAI-App` per backend CLAUDE.md geospatial section):

```python
# app/services/geocode.py
import requests

_NOMINATIM = "https://nominatim.openstreetmap.org/reverse"

def reverse_geocode(latitude: float, longitude: float) -> str | None:
    """Reverse-geocode apiary coords to a human place string. Fail-soft (None on
    any error) — never block /verify. Nominatim ToS requires the custom UA."""
    try:
        r = requests.get(_NOMINATIM, params={
            "lat": latitude, "lon": longitude, "format": "json", "zoom": 10,
        }, headers={"User-Agent": "AgriScanAI-App"}, timeout=8)
        if r.status_code != 200:
            return None
        addr = (r.json() or {}).get("address", {})
        parts = [addr.get("county") or addr.get("city") or addr.get("town"),
                 addr.get("state"), addr.get("country")]
        parts = [p for p in parts if p]
        return ", ".join(parts) or None
    except Exception:
        return None
```

- [ ] **Step 3:** `pytest tests/test_geocode.py -v` → PASS. Commit.

### Task P1a-2: Consumer block on `/verify`

**Files:**
- Modify: `app/schemas/batch.py` (extend `AuthenticityPublic` + add `ConsumerView`)
- Modify: `app/routers/batch.py` (`verify_batch`)

- [ ] **Step 1:** Extend `AuthenticityPublic` with consumer-safe band + anchored explanation, and add a `ConsumerView`:

```python
class AuthenticityPublic(BaseModel):
    available: bool
    status: Optional[str] = None     # raw: verified|suspicious|flagged (dashboards)
    score: Optional[float] = None    # raw 0..1 (dashboards; consumer never shows)
    band: Optional[str] = None       # consumer-safe: consistent|under_review
    explanation: Optional[str] = None  # anchored English proof statement
    model_config = ConfigDict(from_attributes=True)


class ConsumerView(BaseModel):
    place: Optional[str] = None
    producer_label: str = "a verified ApiChain beekeeper"
    authenticity_band: Optional[str] = None      # consistent|under_review
    authenticity_explanation: Optional[str] = None
```

Add `consumer: Optional[ConsumerView] = None` to `BatchVerifyResponse`.

- [ ] **Step 2:** In `verify_batch`, after the authenticity join, compute band + place. Source `band`/`explanation` from the anchored `lab_results` (preferred — provable) falling back to `validation_results`:

```python
        lab_row = batch.lab_result
        _status = (lab_row.validation_status if lab_row else None) or (_val.validation_status if _val else None)
        band = "consistent" if _status == "verified" else ("under_review" if _status else None)
        explanation = lab_row.explanation if lab_row else None
        authenticity = AuthenticityPublic(
            available=_val is not None or (lab_row is not None and lab_row.authenticity_score is not None),
            status=_status,
            score=(lab_row.authenticity_score if lab_row else (_val.authenticity_score if _val else None)),
            band=band, explanation=explanation,
        )
        place = None
        if batch.apiary_record is not None:
            from app.services.geocode import reverse_geocode
            place = reverse_geocode(batch.apiary_record.latitude, batch.apiary_record.longitude)
        consumer = ConsumerView(place=place, authenticity_band=band, authenticity_explanation=explanation)
```

Pass `consumer=consumer` into `BatchVerifyResponse(...)`. (Import `ConsumerView` in the schemas import block.)

- [ ] **Step 3:** Unit-extend `tests/test_verify_endpoint.py` or add `tests/test_consumer_band.py` asserting `verified→consistent`, `suspicious→under_review`, `None→None`.

- [ ] **Step 4:** Commit `feat(verify): consumer block — geocoded place, producer label, interpreted band+explanation`.

---

# PHASE P1b — FE one-QR-per-batch + QR popup + consumer scan redesign (HEADLINE)

### Task P1b-1: Pure `interpretAuthenticity` + Vitest

**Files:**
- Create: `src/api/authenticity.js`
- Create: `src/api/authenticity.test.js`

- [ ] **Step 1: Test:**

```js
import { describe, it, expect } from "vitest";
import { interpretAuthenticity } from "./authenticity";

describe("interpretAuthenticity", () => {
  it("maps consistent band to the positive consumer key (never 'flagged')", () => {
    expect(interpretAuthenticity({ authenticity_band: "consistent" }).key).toBe("consistent");
  });
  it("maps under_review band to neutral", () => {
    expect(interpretAuthenticity({ authenticity_band: "under_review" }).key).toBe("under_review");
  });
  it("absent authenticity returns unknown (no scary words)", () => {
    expect(interpretAuthenticity({}).key).toBe("unknown");
    expect(interpretAuthenticity(null).key).toBe("unknown");
  });
  it("never exposes the raw word 'flagged'", () => {
    const r = interpretAuthenticity({ authenticity_band: "under_review", status: "flagged" });
    expect(JSON.stringify(r)).not.toMatch(/flagged/i);
  });
});
```

- [ ] **Step 2: Implement** (consumer-safe — derives from `consumer.authenticity_band`, never raw status):

```js
// authenticity.js — consumer-safe interpretation. Input: the /verify consumer block.
export function interpretAuthenticity(consumer) {
  const band = consumer?.authenticity_band;
  if (band === "consistent") return { key: "consistent", tone: "positive", i18n: "scan.authConsistent" };
  if (band === "under_review") return { key: "under_review", tone: "neutral", i18n: "scan.authUnderReview" };
  return { key: "unknown", tone: "neutral", i18n: "scan.authUnknown" };
}
```

- [ ] **Step 3:** `npm run test` → PASS. Commit.

### Task P1b-2: One QR per batch

**Files:**
- Modify/replace: `src/features/dashboard/PackageJarQRs.jsx` → `BatchQR.jsx` (single QR)
- Modify: `src/features/dashboard/PackagerDashboard.jsx` (stop sending `qr_codes`; render one `BatchQR`)
- Modify: `src/features/dashboard/FarmerDashboard.jsx`, `SuperAdminDashboard.jsx` (add a **Verify** button → QR popup)

- [ ] **Step 1:** Create `BatchQR.jsx` — one `<QRCodeCanvas value={`${SCAN_BASE}/scan?b=${batchId}`}/>` with Print + Download PNG. (Strip the per-jar loop from `PackageJarQRs`.)

```jsx
import { QRCodeCanvas } from "qrcode.react";
const SCAN_BASE = import.meta.env.VITE_PUBLIC_BASE_URL || window.location.origin;
export default function BatchQR({ batchId, size = 200 }) {
  if (!batchId) return null;
  const url = `${SCAN_BASE.replace(/\/$/, "")}/scan?b=${batchId}`;
  return (
    <div className="batch-qr">
      <QRCodeCanvas value={url} size={size} includeMargin />
      <code>{url}</code>
    </div>
  );
}
```

- [ ] **Step 2:** `PackagerDashboard` package submit: drop `qr_codes` from the POST body (backend ignores extras, but remove for cleanliness); keep `jar_ids` + `unit_count`. Render `<BatchQR batchId={batch.blockchain_batch_id} />` after packaging instead of the per-jar grid.

- [ ] **Step 3:** Add a small **Verify** button on each batch row in `FarmerDashboard` + `SuperAdminDashboard` that opens a modal showing `<BatchQR>` + a "View on Scan" link to `/scan?b=<id>`.

- [ ] **Step 4:** `npm run build && npm run lint`. Commit `feat(fe): one QR per batch + Verify popup on farmer/admin dashboards`.

### Task P1b-3: Consumer scan redesign

**Files:**
- Modify: `src/features/scan/scan.jsx` (+ `Scan.css`)
- Modify: `src/i18n/{en,sw}.json`

- [ ] **Step 1:** Use the new `/verify` `consumer` block. Render a plain-language verified journey: "Honey from **{consumer.place}** · moved through harvest → … → distribution · authenticity: **{interpreted band}**" + the (English, labelled) anchored `authenticity_explanation` + blockchain badge. Producer shown as `consumer.producer_label` (no farmer name). Use `interpretAuthenticity(verifyResponse.consumer)` for the chip; **never render the raw score or the word "flagged"**.

- [ ] **Step 2:** Keep `isThreeWayVerified` for the green "Blockchain Verified" badge gate (`DISTRIBUTED && verification.lab.match`). Note the badge now means *authenticity-verified* (no human pass/fail) — reflected in copy.

- [ ] **Step 3:** Mobile-first polish; EN/SW keys (`scan.authConsistent`, `scan.authUnderReview`, `scan.authUnknown`, `scan.journey`, `scan.producer`, `scan.onChainStatement`, etc.) in both files.

- [ ] **Step 4:** `npm run build && npm run lint`. Commit `feat(fe): consumer scan redesign — place, interpreted authenticity, on-chain statement`.

- [ ] **Step 5:** Manual matrix rows MM-9…MM-12.

---

# PHASE P2 — Tracing reliability

### Task P2-1: `SixStateTimeline` DB-sourced

**Files:** `src/features/dashboard/shared/SixStateTimeline.jsx`

- [ ] **Step 1:** It already reads `batch.current_state` + `*_at` + `*_tx_hash` (no chain `/timeline` call) — confirm every dashboard passes the **view-model batch** (P0a) so `*_at` are reconciler-synced DB values, not chain reads. Audit each dashboard's batch fetch: ensure it uses `GET /batches/` or `/batches/{id}` (now view-model), not `/batches/{id}/timeline`.
- [ ] **Step 2:** Grep the FE for `/timeline` usage; replace any timeline-driven light-up with the view-model `current_state`. Commit.

### Task P2-2: Value audit + pressure test

- [ ] **Step 1:** Walk many batches across all six states; refresh cycles; confirm quantity, timestamps, authenticity render correctly everywhere (no 0s, no stale). Record in the manual matrix (MM-13).

---

# PHASE P3 — Analytics (scope-cut-first)

### Task P3-1: Aggregate endpoints

**Files:** `app/routers/analytics.py` (new), register in `app/main.py`; `tests/test_analytics.py`

- [ ] **Step 1: Test** the aggregation SQL shape (counts by state, total kg from harvest_records, flagged count from validation_results) against a seeded session OR as a pure aggregation over a list (unit-test the grouping fn).
- [ ] **Step 2:** Implement `GET /analytics/farmer` (my batches by state, total kg, distributed count, flagged/suspicious count) + `GET /analytics/admin` (rollups + per-role activity). **No aggregator framing** — use distributor/`retailer_name`. Role-guard farmer vs admin.
- [ ] **Step 3:** Commit.

### Task P3-2: FE widgets

- [ ] **Step 1:** Basic stat cards on `FarmerDashboard` + `SuperAdminDashboard` consuming the new endpoints. EN/SW keys. `npm run build && npm run lint`. Commit.

---

# Appendix A — Manual Test Matrix (FE; no automated coverage)

Run against the live stack (DEBUG-RUNBOOK §13 bring-up; centroid apiary `-0.5, 37.0`).

| # | Area | Steps | Expected |
|---|---|---|---|
| MM-1 | Lab panel render | Open a PROCESSED batch → Lab Verify | Single modal: metrics form (no PASS/FAIL, no purity), timeline, Run Score button |
| MM-2 | Run Score | Enter moisture 19, hmf 28, sucrose 4, pollen 30000 → Run Score | Predicted-vs-actual table + score + explanation; sugar row "measured, not scored"; inputs lock |
| MM-3 | Lock-after-score | Edit moisture after scoring | Score clears, inputs unlock, Submit disabled until re-run |
| MM-4 | Submit (Hardhat) | Run Score → Submit | "anchored!" toast; modal closes; batch → LAB_VERIFIED |
| MM-5 | Submit 202 (Sepolia) | Same on Sepolia env | "anchor in flight…" toast; no block; reconciler flips state later |
| MM-6 | Server authority | DevTools: tamper preview score, then Submit | Anchored score == server recompute (not the tampered value) — check `/verify` |
| MM-7 | Quantity fix | Open a two-step-created batch detail | Quantity shows real kg, not 0 |
| MM-8 | EN/SW | Toggle language in lab panel | All strings translate |
| MM-9 | One QR | Packager packages a batch | One QR (not N per-jar); resolves to `/scan?b=<id>` |
| MM-10 | Verify popup | Farmer/Admin dashboard → Verify on a batch | QR popup + View on Scan link |
| MM-11 | Consumer scan | Open `/scan?b=<id>` for a DISTRIBUTED+verified batch | Place shown, producer = "a verified ApiChain beekeeper", interpreted band, on-chain statement, green badge; NO raw score, NO "flagged" |
| MM-12 | Consumer scan (suspicious) | Scan a suspicious batch | Neutral "under review" chip; never the word "flagged" |
| MM-13 | Pressure | Many batches, all states, refresh | Timelines light up from DB state; no stale/zero values |

# Appendix B — Hard-constraint checklist (before declaring the sprint done)

- [ ] Two pre-image changes: lab (P0b) + packaging (P0d). NO contract redeploy (ABI verified opaque bytes32).
- [ ] Each: migration round-tripped (up/down/up); `test_hash_determinism` family green; lab + packaging hash tests updated; three-way `verification.{lab,packaging}.match` true on local Hardhat AND one fresh Sepolia run (EV-1).
- [ ] `_q4` quantize-string applied to all new ML numerics; float↔Decimal parity test green.
- [ ] Preview persists env; submit reuses it; server recompute == preview (MM-6).
- [ ] scikit-learn pinned 1.6.1 in the venv.
- [ ] venv used for every Python/alembic/pytest/uvicorn command.
- [ ] Full pytest: prior 39 + new tests passed, 2 skipped.
- [ ] FE: `npm run build` + `npm run lint` clean; Vitest green; manual matrix executed.
- [ ] Alembic head documented (after P0d: `a7b8c9d0e1f2`); update DEBUG-RUNBOOK §3 + CLAUDE.md head references.

# Appendix C — Out of scope / debt to flag (not this sprint)

- `PUT/DELETE /farmers/{id}` (teammate scope) — admin farmer edit/delete broken.
- `sucrose_level` model relabel (re-add to score afterward); NDVI stub `0.55`; `northern_kenya` encoder gap.
- FE auth guards (`ProtectedRoute`); kebab-case route normalization; `VITE_API_URL` vs `VITE_API_BASE_URL`.
