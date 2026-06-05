# Sprint 12 Roadmap — GeoAI Integration (off-chain) + Future Works

**Created:** 2026-05-31 · **Refined:** 2026-06-05 (decisions resolved with Ian)
**Author:** Ian Ndolo Mwau (SCT211-0034/2022, JKUAT) — blockchain component
**Status:** Roadmap for a fresh session to execute. As of this writing **no GeoAI
code is pulled** and **no working-tree changes** have been made. `app/ml_models/`
artifacts are already in place locally.

---

## 0. Where we are (start of Sprint 12)

End-to-end traceability is live and pushed to `origin/main`:
- **Backend** `6fca39b` — 6-state lifecycle, oracle-signed lab verification, three-way
  `/verify`, proven on Hardhat + Sepolia (Sprint 9). **Local HEAD is here.**
- **Frontend** `8500931` — Farmer/Processor/Lab/Packager/Distributor dashboards, walked
  S0→S5 in the browser (Sprint 11).

The team confirms everything works except the **GeoAI integration** — this sprint.

## 1. What the teammate delivered (not yet pulled)

Commit **`35aeac2` "feat: add geo-ai prediction and validation routes"** sits on
`origin/main`, **one commit ahead of local** (parented on `6fca39b`; no conflict).
Backend-only. Adds:

| File | New? | Purpose |
|------|------|---------|
| `app/services/geo_ai.py` | new | ML inference: load models, predict expected lab metrics, score authenticity |
| `app/routers/geo_ai.py` | new | `POST /geo-ai/{id}/predict`, `POST /geo-ai/{id}/validate`, `GET /geo-ai/{id}/result` |
| `app/models/geo_ai.py` | new | DB tables `geo_ai_predictions`, `validation_results` |
| `app/routers/lab_result.py` | **RE-ADDED** | ⚠ integrity regression — §5 |
| `app/schemas/lab_result.py` | **RE-ADDED** | ⚠ supports the above |
| `app/main.py` | edit | registers `lab_result` + `geo_ai` routers |
| `requirements.txt` | edit | +`numpy`, `joblib`, `scikit-learn`, `xgboost` (unpinned) |
| `.gitignore` | new | ignores `app/ml_models/` (artifacts are out-of-band) |

**Model artifacts are in place** at `backend/app/ml_models/` (the team's zip, extracted):
`scaler.pkl`, `le_region.pkl`, `le_season.pkl`, `le_veg.pkl`, `feature_cols.json`,
`flowering_calendar.pkl`, `ensemble_{moisture_content,sucrose_level,hmf_level}.pkl`.
Loaded at runtime by `app/services/geo_ai.py`. **Confirmed present 2026-06-05.**

## 2. How GeoAI works (provenance authentication)

Two off-chain steps:
1. **Predict** — from apiary location + harvest month/season + environmental snapshot
   (temp/humidity/rainfall/NDVI) + a flowering-calendar "triangulation", an RF+XGBoost
   ensemble predicts the *expected* moisture/sugar/HMF for honey genuinely from that
   place+time, plus a confidence score. → `geo_ai_predictions`.
2. **Validate** — compares predicted vs **actual lab** metrics → `authenticity_score`
   → `verified` (≥0.80) / `suspicious` (≥THRESHOLD) / `flagged`. → `validation_results`.

It answers *"does this honey's measured chemistry match its claimed origin?"* —
adulteration / mislabeled-origin decision support **on top of** the anchored lab data.
It does **not** replace the tester's `passed_quality_check`.

Routes key off the **integer** `HoneyBatch.id`; `predict`/`validate` are guarded to
`on_ground_officer`/`admin`/`super_admin`; `GET /result` is public.

## 3. Decisions resolved (2026-06-05)

| # | Question | Decision |
|---|----------|----------|
| **Anchoring** | Put the authenticity score on chain? | **Off-chain now, anchor later.** Build the off-chain flow this sprint; the on-chain version is a scheduled follow-up (§8, "anchor-later"). Keeps the proven hash story untouched. |
| **Lab_result regression** | Keep the re-added router? | **No — strip it on pull** (§5). Coordinate with the teammate (it was likely a test convenience), don't silently delete. |
| **Model loading** | Import-time vs guarded? | **Lazy/guarded** so a missing/incompatible model degrades the geo-ai routes to 503 instead of killing backend boot. |
| **`validate` null-guard** | Handle absent lab metrics? | **Yes** — our lab form makes the 5 metrics optional; `validate` must not crash on `None`. |
| **`batch_id` hex alignment** | Align geo-ai routes to the hex id? | **Recommended** (consistency with every other batch endpoint); confirm during execution. Sub-decision, not blocking. |
| **Frontend** | This sprint? | **Backend-first.** FE surfacing is a fast-follow once the teammate's UI lands (§7). |

## 4. Blockchain impact

The GeoAI core is **hash-neutral**: predict/validate read apiary/env/lab and write to
two new off-chain tables — they never touch a canonical `*_records` payload, a
keccak256 anchor, or the 6-state machine. So `/verify` and hash determinism are
unaffected. Per the decision above, the authenticity score stays **off-chain (DB only)**
this sprint, surfaced via `GET /geo-ai/{id}/result` and (later) the QR page.

## 5. ⚠ Critical regression to strip on pull

`app/routers/lab_result.py` is the duplicate off-chain lab path **Sprint 3 deleted**.
As re-added, `POST /lab-results/{id}` is **unauthenticated**, **anchors nothing**, and
sets `current_state = "LAB_VERIFIED"` **with no `PROCESSED` precondition** — it can jump
*any* batch straight to LAB_VERIFIED in the DB with no proof hash. That's a
state-machine + integrity bypass that breaks three-way `/verify`.

**On pull:** remove `app/routers/lab_result.py`, `app/schemas/lab_result.py`, and the
two `main.py` lines that import/register it. The pre-existing
`app/models/lab_result.py` **LabResult model stays** (Sprint 2/3) — only the re-added
*router* + *schema* + wiring go. Flag to the teammate so it isn't re-pushed.

## 6. Other gaps to close on pull

1. **Boot coupling (high).** Models load at import time → main.py imports the geo_ai
   router → a missing/incompatible `app/ml_models/` **kills the whole backend at
   startup**. Wrap loading so failure → 503 on geo-ai routes only (decision §3).
2. **No Alembic migration** for `geo_ai_predictions` + `validation_results`.
   Autogenerate one — and first ensure `app/models/geo_ai.py` is imported where
   alembic's `env.py` / `models/__init__.py` sees it, or autogenerate emits empty.
3. **`validate` 500s on absent lab metrics.** `abs(actual - (pred_val or 0))` with
   nullable `lab.moisture_content/sucrose_level/hmf_level` → guard for `None`.
4. **Unpinned ML deps** → pin `scikit-learn`/`xgboost`/`numpy` to the training versions
   (pickle compatibility) before installing into the venv.
5. **`batch_id` integer vs hex** — align the 3 routes to the hex `blockchain_batch_id`
   if confirmed (decision §3).
6. **NDVI is a stub** (`0.55` hardcoded; not captured) — accuracy caveat, note it.

## 7. Sprint 12 execution roadmap (what a fresh session does)

**Backend reconciliation (this sprint), in order:**

1. **Pin + install deps.** Pin the 3 ML libs in `requirements.txt`, install into the
   backend venv (CLAUDE.md venv rule — never system Python).
2. **Pull `35aeac2`** into local `main` (`git pull origin main`; fast-forward expected).
3. **Strip the lab_result regression** (§5) — delete router + schema, remove the 2
   `main.py` lines. Verify `/batches/{id}/lab-verify` is still the only lab path.
4. **Guard model loading** (§6.1) so a model problem can't break backend boot.
5. **Wire models into the migration chain** (§6.2) — confirm `models/__init__.py`
   imports `geo_ai`, then `alembic revision --autogenerate -m "geo_ai tables"` →
   `alembic upgrade head`. New head supersedes `c0d1e2f3a4b5`.
6. **Null-guard `validate`** (§6.3).
7. **(Optional) align `batch_id` to hex** (§6.5) if confirmed.
8. **Smoke-test** on a freshly-walked batch (RUNBOOK §13 + the Hardhat/DB-desync rule —
   never reuse an old DB against a fresh chain): walk a batch to LAB_VERIFIED, then
   `POST /geo-ai/{id}/predict` → `POST /geo-ai/{id}/validate` → `GET /geo-ai/{id}/result`;
   confirm an `authenticity_score` + status come back and the backend stays up.

**Frontend fast-follow (when the teammate's UI lands):**
- **Lab dashboard:** after a successful lab-verify, call predict + validate and show the
  authenticity score + verified/suspicious/flagged next to the tester's verdict (decision
  support, not a gate). Reuse the Sprint 11 kit (`apiFetch`, badges, modal).
- Use the integer `batch.id` for geo-ai calls unless §6.5 aligns them to hex.

## 8. Anchor-later (scheduled follow-up — the on-chain version)

When the off-chain flow is proven and the team wants the score cryptographically
anchored, the **only** no-redeploy path is **fold it into the lab-proof payload**:
run GeoAI synchronously inside `/batches/{id}/lab-verify`, add an `authenticity_score`
column to `lab_results`, include it in the canonical payload, anchor it as part of the
existing `lab_proof_hash`. This is a **canonical-hash change** → migration + determinism
tests (design principle 7) + a refresh of the Sepolia lab-verify evidence. Scope it as
its own sprint; do **not** mix it into the off-chain work above.

## 9. Future works (beyond Sprint 12)

1. **Consumer QR refinement.** Surface the GeoAI authenticity score on the `/verify` /
   scan page (a consumer-legible "authenticity" chip alongside the blockchain-verified
   badge), and optimize the whole page for a non-technical consumer — highlight the few
   details that speak to quality/origin/authenticity, de-emphasize raw hashes.
2. **Sepolia testnet validation of the full UI flow.** Backend proven on Sepolia
   (Sprint 9); the Sprint 11 dashboards haven't been exercised there. The 202-pending
   path becomes the norm (~340s/batch — already handled); wallets need real Sepolia ETH +
   roles. Point `.env` at Sepolia (`reference_sepolia_env_recovery`), re-enroll, walk it.
3. **Admin oversight dashboard** (read-only, frontend-only) — all batches + timeline +
   flagged/failed/suspicious indicators. Reuses the Sprint 11 kit.
4. **Admin "all-rights" transitions** — backend + contract-role work (DEFAULT_ADMIN_ROLE
   doesn't satisfy stage roles); needs an "admin acts-as" / role-widening design.
5. **Farmer & admin analytics** — batches by state, total kg, distributed, bad batches
   (failed lab), timelines; admin rollups. **Aggregator caveat:** the aggregator entity
   was dropped in Sprint 8; "sold to aggregator" framing needs an iteration-2 schema —
   build on the existing distributor/`retailer_name` for now.
6. **i18n EN/SW sweep** across all dashboards (Sprint 11 shipped English; spec §6 has keys).
7. **Route/UX debt** — kebab-case routes, `ProtectedRoute` wrapper, error boundaries,
   a frontend test framework (Vitest + RTL).
