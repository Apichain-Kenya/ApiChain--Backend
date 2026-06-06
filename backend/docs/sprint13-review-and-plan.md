# Sprint 13 — System Review & Plan

**Created:** 2026-06-06 · **Author:** Ian Ndolo Mwau (SCT211-0034/2022, JKUAT)
**Status:** PLAN — decisions locked in review session 2026-06-06; pending Ian's lock before implementation.
**Predecessor:** Sprint 12 (off-chain GeoAI integration + lifecycle dashboards), see
`future-works-and-sprint12-geoai.md`. Full lifecycle ran clean via `DEBUG-RUNBOOK.md`
and was presented to the supervisor; this plan folds in that meeting's feedback.

---

## 0. Where we are (start of Sprint 13)

End-to-end build works: enrollment → farmer/batch creation → full S0→S5 provenance
(all six role dashboards wired) → off-chain GeoAI authenticity (Sprint 12). Carried-over
flags from Sprint 12 that this sprint must account for:

- **`sucrose_level` model target is mislabeled** (predicts ~75 = total sugar, not true
  sucrose ~4) — penalizes genuine honey on the sugar axis.
- **NDVI is a hardcoded stub (`0.55`)** — accuracy caveat.
- **`northern_kenya`** region is in the geography but not the trained encoders — degraded.
- **`PUT/DELETE /farmers/{id}`** are called by the admin UI but absent on the backend.
- **No frontend test framework** (Vitest unbuilt) — every FE change is build/lint only,
  never runtime-tested.
- **No auth guards** — all frontend routes are public.

## 1. Decisions locked this session

| # | Decision |
|---|----------|
| **A1 anchor scope** | Anchor `authenticity_score` + `validation_status` + the 3 predicted metrics + the explanation, alongside the actual lab metrics. Authenticity becomes blockchain-provable. |
| **A1 explanation** | **Rule-based template** generated from the components we already compute (region, per-metric predicted-vs-actual deviation, triangulation, confidence). Deterministic, offline, free, stored once. |
| **A1 sucrose** | **Exclude sucrose from the score** this sprint (score on moisture + HMF + triangulation + confidence). Re-add once the model target is relabeled. Sucrose is still measured/stored/anchored as a value — just not scored. |
| **A1 flow** | "Run Authenticity Score" is a **preview** (compute, no persist). The single **Submit** authoritatively recomputes server-side (deterministic → same result), persists everything, and anchors. Downstream only reads stored values. |
| **A1 prediction independence** | **Decouple the prediction from lab input.** Today `predict` consumes `lab.pollen_density` (feeds triangulation), so "predicted" isn't independent of "actual". Source the triangulation/prediction pollen from an **expected/region-derived** value instead; lab pollen stays a stored measurement only. (Coordinate the model-logic change with the teammate.) |
| **A1 input lock** | After "Run Score", the metric fields **lock**; editing any value clears the score and forces a re-run before Submit. What the tester reviewed is what gets anchored. |
| **A1 removals** | Remove the hard pass/fail toggle and the purity-score input (both currently *hashed* — see §2.1). |
| **A2 QR** | **One scannable QR per batch** encoding `/scan?b=<hex>`. Drop per-jar codes (packager still records jar *count* for the packaging hash). |
| **A2 consumer identity** | Show the **real geocoded place** (Nominatim from apiary lat/lon); producer shown as **"a verified ApiChain beekeeper"** (no farmer name). Score shown **interpreted** (band + explanation), never raw. |
| **A3 data** | Backend **batch view-model** exposes a canonical `quantity` + lab/authenticity summary; `SixStateTimeline` reads **DB `current_state` + `*_at`**, not the flaky chain `/timeline`. |
| **A4 analytics** | Basic aggregates only; **no "aggregator" framing** (entity dropped Sprint 8 — use distributor/`retailer_name`). |

---

## 2. Per-area design

### 2.1 Area 1 — Lab + Geo-AI merge (HEADLINE; touches blockchain)

**The blockchain core.** The lab proof anchored on-chain hashes
`_lab_result_canonical_payload`, today:
`batch_id, moisture, sucrose, hmf, pollen_density, purity_score, passed_quality_check,
laboratory_name, analyst_name, certificate_number, notes`. Sprint 13 redefines this
pre-image (no contract change — `anchorLabProof(batchId, proofHash)` is unchanged; only
the bytes hashed change):
- **Drop** `purity_score`, `passed_quality_check`.
- **Add** `predicted_moisture`, `predicted_sugar`, `predicted_hmf`, `authenticity_score`,
  `validation_status`, `explanation`.
- Keep `moisture, sucrose, hmf, pollen_density` + lab metadata.

This is a **canonical-hash change** → per design principle 7: migration (new `lab_results`
columns), update `test_hash_determinism` + the lab hash tests, refresh Sepolia evidence.

**Backend**
- Migration: add the 6 new columns to `lab_results`; drop (or stop hashing) `purity_score`
  + `passed_quality_check`. *(Sub-decision: physically drop the columns or just remove
  from the form + hash — settle in detailed design.)*
- `validate_and_save` scoring: compute `phys_match` from **moisture + HMF only**
  (exclude sucrose), combined with triangulation + confidence as today.
- **Decouple prediction from lab input:** in `predict_and_save`/`_triangulation`, stop
  sourcing pollen from `lab.pollen_density`; use an expected/region-derived pollen so the
  predicted profile is independent of the lab measurement being compared against. Lab pollen
  remains a stored, anchored measurement.
- Rule-based `explanation` generator in `services/geo_ai.py`: e.g. *"Moisture and HMF
  consistent with central_highlands honey; strong region triangulation; sugar measured
  but not scored (model under review). Verdict: suspicious."*
- New `POST /geo-ai/{id}/preview` — takes the entered actual metrics, returns predicted +
  score + explanation **without persisting**. Roles: lab_test_officer / on_ground_officer
  / admin / super_admin.
- Redesign `POST /batches/{id}/lab-verify`: accept actual metrics; **server authoritatively
  recomputes** predict+score (don't trust client-passed score); persist `lab_results` (with
  authenticity fields) + the `geo_ai_predictions`/`validation_results` rows in one tx;
  hash the new canonical payload; anchor; existing rollback + 202-pending semantics intact.
- **Env-timing guarantee**: predict needs `environmental_data`. The merged panel/endpoint
  auto-fetches it if missing (lab_test_officer is now permitted — Sprint 12 fix), or trigger
  the snapshot at the process stage. Pick one in detailed design; default = auto-fetch in
  the lab flow.

**Frontend**
- **Merge into ONE panel** — lab form + GeoAI, no tab switch. Larger, more interactive modal.
- **Live validation** as values are entered (e.g. moisture trending out of range), extending
  the existing `METRICS.ok` hints.
- **"Run Authenticity Score"** → `preview` → render the loved side-by-side
  predicted-vs-actual table (now populated — Sprint 12 already returns actual `lab` in
  `/result`; preview returns the same shape) + score + explanation. Mark the **sugar row
  "measured, not scored (under review)"** so the ~75-vs-~4 gap isn't alarming.
- **Lock-after-score:** once "Run Score" returns, the metric inputs lock; any edit clears the
  score and re-enables Run. The tester anchors exactly what they reviewed.
- **Single Submit** → redesigned `lab-verify` (anchors everything). Handle the **202-pending**
  state gracefully (on Sepolia this sits minutes — see §4).
- **Remove** pass/fail toggle + purity input. **Fix the quantity field** (root cause is the
  batch view-model — §2.3). **Audit every displayed value** for accuracy.

### 2.2 Area 2 — QR + Consumer View (HEADLINE)

**Backend**
- `/verify` additive consumer fields (chain-neutral, additive like Sprint 12's authenticity
  block): **geocoded place** (Nominatim reverse-geocode of apiary lat/lon → county/region
  string), **producer label** ("a verified ApiChain beekeeper" — no name), and the
  **interpreted authenticity** (band + explanation) sourced from the now-anchored lab data.
  *(Sub-decision: interpret server-side vs client-side — server keeps it consistent.)*
- Because A1 anchors authenticity, the consumer page reads it as **blockchain-provable**.

**Frontend**
- **One QR per batch** encoding `/scan?b=<hex>` (drop `PackageJarQRs` per-jar loop).
- **"Verify" button → QR popup** on farmer + admin dashboards, per batch at its current
  provenance stage.
- **Redesign the scan page** (`scan.jsx`): plain-language verified journey ("Honey from
  [place] · moved through harvest → … → distribution · authenticity: [interpreted band]"),
  the rule-based explanation, blockchain badge, mobile-first, EN/SW. Improve the visual
  design.

### 2.3 Area 3 — Provenance tracing reliability

**Backend (foundational — do early; unblocks display bugs in A1/A2/A3)**
- **Batch view-model**: `GET /batches/` + `GET /batches/{id}` return a canonical shape the
  FE can trust — real `quantity` (joined from `harvest_records`), `current_state`, per-stage
  `*_at` timestamps, and a lab/authenticity summary. Kills the **quantity = 0** bug at the
  source (today `batch.quantity` is absent → FE falls through to `0`).

**Frontend**
- `SixStateTimeline` reads **DB `current_state` + `*_at`** (reconciler-synced), not the
  intermittent chain `/timeline`. Reliable light-up indicators.
- Audit dashboard forms for stale/zero values. **Pressure-test**: many batches across all
  six states, refresh cycles, concurrent transitions.

### 2.4 Area 4 — Reports & Analytics (scoped basics)

**Backend**
- Aggregate endpoints: **farmer** (my batches by state, total kg harvested, distributed
  count, flagged/suspicious count), **admin** (rollups across batches + per-role activity
  counts). No aggregator framing.

**Frontend**
- Basic stat widgets on the farmer + admin dashboards.

---

## 3. Prioritized sequence

1. **P0a — BE foundational:** batch view-model + env-timing guarantee (§2.3, §2.1). Unblocks
   display bugs across A1/A2/A3.
2. **P0b — BE + blockchain (HEADLINE):** lab canonical payload redesign + scoring (exclude
   sucrose) + rule-based explanation + `preview` endpoint + `lab-verify` redesign +
   determinism tests.
3. **P0c — FE (HEADLINE):** merged lab+GeoAI panel + single submit + live validation +
   remove pass/fail+purity + fix quantity.
4. **P1a — BE:** `/verify` consumer fields (geocoded place, producer label, interpreted
   authenticity).
5. **P1b — FE (HEADLINE):** one-QR-per-batch + QR popups + consumer scan redesign.
6. **P2 — FE:** `SixStateTimeline` reliability + form audit + pressure test.
7. **P3 — BE+FE:** analytics endpoints + widgets.
8. **After P0b — blockchain:** refresh Sepolia lab-verify evidence (new pre-image).

**Scope cut-line (this is large for one sprint):** if scope slips, **P3 (analytics) drops
first, then P2 (tracing polish)**. The headline P0 (lab merge + anchoring) and P1 (QR +
consumer) ship together or the sprint's story is incomplete.

## 4. Grouped by layer (headline = Lab + QR)

**Blockchain layer** (small but **two** pre-image changes, highest-risk):
- **No contract redeploy — VERIFIED.** `anchorLabProof(batchId: bytes32, proofHash: bytes32)`
  (and the packaging anchor) take an **opaque `bytes32`**; nothing on-chain validates the
  pre-image shape, so redefining what we hash needs no Solidity change.
- **Lab proof pre-image redesign** (A1) — anchor authenticity + predicted + explanation, drop
  purity/pass-fail. Migration + `test_hash_determinism` + lab-hash test updates + three-way
  `verification.lab` still matches.
- **Packaging proof pre-image change** (A2) — ⚠ *the packaging canonical payload currently
  hashes `jar_ids` + `qr_codes`* (`_packaging_record_canonical_payload`). Moving to one QR per
  batch changes the packaging pre-image too → a SECOND hash redesign (drop `qr_codes`, and
  decide whether `jar_ids` stays as recorded jar count). Same discipline: migration if the
  record shape changes, determinism test, `verification.packaging` still matches.
- After both: **one** fresh Sepolia evidence run (~340 s, ~0.005 ETH) covering the new lab +
  packaging pre-images.

**Backend layer:**
- `lab-verify` redesign + scoring (exclude sucrose) + rule-based explanation + `preview`
  endpoint (A1).
- Env-timing guarantee (A1).
- Batch view-model (A3) — foundational.
- `/verify` consumer fields: geocoded place + producer label + interpreted authenticity (A2).
- Analytics aggregate endpoints (A4).
- *(Debt to flag to teammate: `PUT/DELETE /farmers/{id}`.)*

**Frontend layer:**
- Merged lab+GeoAI panel: single submit, live validation, remove pass/fail+purity, fix
  quantity, audit values, larger interactive modal (A1).
- One QR/batch, QR popup on dashboards, consumer scan redesign (A2).
- Reliable `SixStateTimeline` + form audit + pressure test (A3).
- Analytics widgets (A4).

## 5. Compromises & things to revisit (callouts)

- **Sepolia single-submit latency.** On Sepolia the merged "single submit" anchors over
  ~340 s → it will sit in the **202-pending** path for minutes. The panel MUST NOT block the
  tester: show "anchoring on chain…", let the reconciler finalize, surface the result when
  ready. Design the merged panel for this from the start.
- **"Lab verified" semantics shift.** Dropping `passed_quality_check` means the green
  consumer "Blockchain Verified" badge (gated on `DISTRIBUTED && verification.lab.match`) now
  signals *authenticity-verified*, not a human pass/fail. Confirm the team/supervisor accept
  this redefinition.
- **Sucrose** excluded this sprint — re-add after the model teammate relabels; the lab panel
  marks the sugar row "measured, not scored."
- **NDVI stub (0.55)** and **`northern_kenya`** encoder gap still degrade accuracy — name in
  the explanation/limitations; future work.
- **No FE test framework.** A sprint touching the consumer page + the lab/anchor flow with
  zero runtime tests is risky. Minimum: a manual test matrix in the implementation plan;
  recommended: a scoped Vitest + RTL setup for the lab panel + scan chip logic.
- **No auth guards.** A consumer-facing sprint is a good moment to add a `ProtectedRoute`
  wrapper so staff dashboards aren't publicly reachable.
- **`PUT/DELETE /farmers/{id}`** still missing → admin farmer edit/delete broken (teammate).
- **Minor debt** (optional this sprint): `VITE_API_URL` vs `VITE_API_BASE_URL` env-name
  mismatch; mixed-case/spaced routes (`/Admin/Sign Up`); pre-existing lint errors in
  `TesterDashboard` (`getUser`, `Icon`).

## 6. Open sub-decisions for detailed design

- Physically drop `purity_score` / `passed_quality_check` columns, or only remove from the
  form + hash?
- **Packaging pre-image:** drop `qr_codes` only, or also `jar_ids` (keep a single `jar_count`
  field instead)? Determines the packaging migration shape.
- Score interpretation: server-side vs client-side.
- Env snapshot trigger point: lab-flow auto-fetch (default) vs process-stage trigger.
- Vitest adoption scope (lab panel + scan logic, or skip with a manual matrix).
