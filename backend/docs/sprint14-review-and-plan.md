# Sprint 14 — Review & Plan

**Created:** 2026-06-07 · **Author:** Ian Ndolo Mwau (SCT211-0034/2022, JKUAT)
**Status:** PLAN — carry-over from Sprint 13. Start here in the next session.
**Predecessor:** Sprint 13 (lab+GeoAI on-chain anchoring, one-QR consumer view, tracing,
analytics, + phone-demo tunnel). See `sprint13-review-and-plan.md` (locked plan) and
`docs/superpowers/plans/2026-06-06-sprint13-implementation.md` (task-by-task impl plan).

---

## 0. Where we are (start of Sprint 14)

**Sprint 13 is COMPLETE, verified, and PUSHED — but not yet merged to main.**

- **Branches (both repos):** `sprint13/lab-anchor-qr`, pushed to origin, working trees clean.
  PRs not yet opened (Ian merges via PR, as with Sprint 12).
  - Backend PR: `github.com/Apichain-Kenya/ApiChain--Backend/pull/new/sprint13/lab-anchor-qr`
  - Frontend PR: `github.com/Apichain-Kenya/Apichain-Frontend/pull/new/sprint13/lab-anchor-qr`
- **Backend:** 75 passed / 2 skipped. **Alembic head: `a7b8c9d0e1f2`** (lab authenticity cols
  `f1a2b3c4d5e6` → packaging drop-qr_codes `a7b8c9d0e1f2`, both off `e2f3a4b5c6d7`).
- **Frontend:** Vitest 10 passing (scoped: `labPanelReducer`, `interpretAuthenticity`), build
  clean, lint at pre-existing baseline (8 errors — incl. an `Icon` eslint false-positive).
- **On-chain proof:** local Hardhat e2e **7/7 three-way matches** with BOTH new pre-images
  (lab + packaging). Anchored authenticity reads `verified` 0.9711 at central_highlands with
  realistic chemistry (sucrose-exclusion fix). **Sepolia NOT yet run.**
- **Phone QR demo:** VERIFIED on a real device via ngrok tunnel
  (`smoothly-faithful-trout.ngrok-free.app`). See DEBUG-RUNBOOK §15.
- **All local servers shut down** (Hardhat / backend / Vite / ngrok). Ports free.

**Key reference docs:** `sprint13-review-and-plan.md`, the impl plan under
`docs/superpowers/plans/`, DEBUG-RUNBOOK §14 (GeoAI workflow) + §15 (ngrok phone demo).
Project memory: `project_sprint13_plan` (full carry-over), `reference_geoai_model_contract`,
`feedback_hardhat_db_desync`, `feedback_venv_activation`.

---

## 1. First moves (recommended order)

1. **P0a — Security quick-fix** (push-review finding, §3) — 1-line `vite.config.js` change.
2. **P0b — Sepolia evidence run** (the one Sprint-13 hard-constraint left, §4).
3. **P0c — Merge both `sprint13/lab-anchor-qr` branches to `main`** (PR flow).

After P0, pick from the prioritized backlog (§2) based on what the JKUAT defense needs next.

---

## 2. Carry-over backlog (prioritized)

| Pri | Item | Notes |
|---|---|---|
| **P0** | Security: narrow `vite.config.js` allowedHosts | §3 — DNS-rebinding finding from push review |
| **P0** | Sepolia evidence run | §4 — defense artifact; hash logic already 7/7 on Hardhat |
| **P0** | Merge sprint13 → main (both repos) | PR flow; then delete the feature branches |
| **P1** | FE cleanup: ProcessorDashboard still imports stale `PackageJarQRs` | Sprint 13 went one-QR-per-batch; Processor's per-jar packaging UI is now dead/inconsistent |
| **P1** | `BatchQR` print includes the modal overlay | add `@media print` isolation like the old `PackageJarQRs` had |
| **P1** | FE auth guards (`ProtectedRoute`) | all routes currently public; a consumer-facing build is a good moment |
| **P2** | Route normalization (kebab-case) | `/Scan` vs `/scan` (both routed now), `/Contact Us`, `/Sign Up`, header link mismatch |
| **P2** | `PUT/DELETE /farmers/{id}` missing | admin farmer edit/delete broken (teammate scope — flag) |
| **P2** | ngrok "Visit Site" interstitial | free-tier only; gone with a paid plan or a real custom domain — narrate in demo |
| **P3** | Model team coordination | sucrose target relabel (then **re-add sucrose to the score**), NDVI `0.55` stub, `northern_kenya` encoder gap (see `reference_geoai_model_contract`) |

---

## 3. Security finding — `vite.config.js` allowedHosts (P0, from push review)

**Finding (MEDIUM):** the dev-server `allowedHosts` whitelists the ENTIRE ngrok shared
namespace via bare-suffix entries:
```js
allowedHosts: ['localhost', '127.0.0.1', '.ngrok-free.app', '.ngrok.io', '.ngrok.app']
```
A leading-dot bare suffix on a shared SaaS namespace means **any** `*.ngrok-free.app`
subdomain passes Vite's host check → a DNS-rebinding / host-check-bypass vector against the
dev server.

**Risk context:** dev-server only, demo-time, single developer — low real-world exploitability,
but the fix is trivial and it's good hygiene (and it's what the push-review flagged, so close it).

**Fix (pin to OUR static domain, from an env var so it's not hard-coded):**
```js
// vite.config.js
const TUNNEL_HOST = process.env.VITE_DEV_TUNNEL_HOST || 'smoothly-faithful-trout.ngrok-free.app'
export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: ['localhost', '127.0.0.1', TUNNEL_HOST],
    proxy: Object.fromEntries(API_PREFIXES.map((p) => [p, { target: API_TARGET, changeOrigin: true }])),
  },
})
```
- Keep `localhost` + `127.0.0.1` for local dev.
- `VITE_DEV_TUNNEL_HOST` lets a new tunnel/domain be set without editing the config.
- Verify: `npm run build` + re-run the tunnel test (`curl -s http://127.0.0.1:4040/api/tunnels`,
  then `curl -H 'ngrok-skip-browser-warning: true' https://<domain>/analytics/farmer` → 401).
- Commit on a fresh branch off main (e.g. `sprint14/security-and-sepolia`).

---

## 4. Sepolia evidence run (P0)

The only Sprint-13 hard-constraint deliverable not completed. **Low risk:** Sepolia runs the
IDENTICAL hashing code already proven 7/7 on local Hardhat; this is the defense/evidence artifact.

**Pre-reqs:** Sepolia wallets funded with test ETH + on-chain roles granted; `.env.sepolia` present
(`reference_sepolia_env_recovery` memory if it needs reconstructing).

**Steps (DEBUG-RUNBOOK §11):**
1. `cp .env .env.hardhat.bak && cp .env.sepolia .env` ; confirm `CHAIN_ID=11155111`.
2. Restart backend; ensure wallets funded + roles granted (re-enroll if needed).
3. `python scripts/e2e_lifecycle.py --base-url http://127.0.0.1:8000 --invite-code "ApiChain@SuperAdmin2025"`
   (~340s). Expect all 7 `verification.*.match` true on the NEW lab + packaging pre-images.
4. Capture evidence → `backend/docs/sepolia-lifecycle-evidence.md` (new batch id, ~6 Etherscan
   tx hashes, wall-clock, the 7/7). Note the Sprint-13 pre-image redesign date.
5. `cp .env.hardhat.bak .env && rm .env.hardhat.bak` (restore Hardhat env).

> The e2e lab body already uses the new shape (no purity/pass-fail) and a centroid apiary
> (`-0.5, 37.0`); the package body already drops `qr_codes`. No script edits needed.

---

## 5. Bring-the-stack-up cheatsheet (for a fresh session)

```
# T1 Hardhat:   npx hardhat node                              (from ApiBlockchain/)
# T1b deploy:   npx hardhat run scripts/deploy.js --network localhost
#               (must print RoleManager 0x5FbDB... + Registry 0xe7f1725...)
# DB reset:     truncate per RUNBOOK §3 (Hardhat restart wipes chain+roles → desync rule)
# T2 backend:   .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000   (venv!)
# T3 frontend:  npm run dev                                   (from apichain-website/)
# Phone demo:   ngrok http --url=smoothly-faithful-trout.ngrok-free.app 5173   (RUNBOOK §15)
```
Hardhat/DB desync rule: restarting Hardhat wipes chain+roles → ALWAYS truncate + re-walk;
`/verify` now returns a clean 404 (not 500) on desync (FIX-A).

---

## 6. Open decisions (resolve early)

- **Supervisor sign-off** on the "lab verified = authenticity-verified" semantics shift —
  Sprint 13 dropped the human `passed_quality_check`, so the green consumer badge now signals
  authenticity, not a human pass/fail (plan §5). Confirm the team/supervisor accept this.
- **Re-add sucrose to the score?** Only after the model team relabels the `sucrose_level`
  target (currently predicts total sugar ~75, not true sucrose ~4). Until then it stays
  measured/anchored but unscored.
- **Auth guards scope** — minimal `ProtectedRoute` now, or defer to a dedicated auth pass.

---

## 7. What NOT to re-do (already done in Sprint 13)

- Lab + packaging canonical-hash redesigns (anchored, tested, 7/7 on Hardhat). Do NOT touch
  `_lab_result_canonical_payload` / `_packaging_record_canonical_payload` / `_q4` without a
  migration + determinism test + fresh evidence (design principle 7).
- The merged lab panel, one-QR consumer view, animated farmer/admin timeline, analytics,
  and the ngrok phone-demo plumbing (Vite proxy + relative API + skip-header) — all shipped.

---

## 8. Day 1 progress (2026-06-08 EAT) — Sepolia walk + bridge tx-robustness fix

Sprint 13 is now **merged to `main` on both repos** (backend PR #12 `4e3b23f`, frontend PR #5
`09887ce`). This branch is fresh Sprint-14 work off that merged main.

**What happened:** the manual Sepolia walkthrough surfaced a real (previously hidden) bridge
bug. Two transactions were **silently dropped from the Sepolia mempool** — a processor's
role-grant and a `distribute` tx — leaving a processor unable to sign (`recordProcessing`
reverted "missing role") and a batch stuck `PACKAGED` with an orphan `DistributionRecord`
(→ 409 on retry). Root cause: the bridge built **legacy fixed-`gasPrice` txs priced at
`baseFee + ~0.001 gwei` tip**; on a live network a rising base fee strands them and the node
evicts them. Intermittent — some txs mined, others dropped.

**Fixes shipped this branch (all in `blockchain.py` + the reconcilers):**
1. **EIP-1559 gas pricing** — `_sign_and_send` + `fund_account` now set
   `maxFeePerGas = baseFee×3 + 2 gwei` and `maxPriorityFeePerGas = 2 gwei` (drops legacy
   `gasPrice`; falls back to legacy on a pre-London chain). The ceiling is affordability, not
   spend — actual cost stays ~base+tip. Constants `GAS_MAX_FEE_MULTIPLIER`, `GAS_PRIORITY_FEE_GWEI`.
2. **Funding bump** — `fund_account` default `0.001 → 0.01 ETH` (`DEFAULT_FUND_ETH`), top-up
   floor `0.0005 → 0.005` (`FUND_MIN_BALANCE_ETH`). REQUIRED pairing with #1: the higher
   maxFeePerGas ceiling raises the node's submission-balance requirement above the old 0.001;
   without this the gas fix trades dropped txs for insufficient-funds reverts. Covers the
   farmer's 2-tx `/simple`.
3. **Reconciler crash fix** (`reconcile_batches.py`) — used `batch_data["state"]` (the string
   name) where it needed `["state_code"]` (the int) → `TypeError` on every genuinely-pending
   batch. Latent because Hardhat receipts return before a row goes pending; only reachable on
   slow Sepolia. This crash was *also* why the stuck distribute never auto-recovered.
4. **`scripts/reconcile_roles.py`** (new) — repairs on-chain role drift: syncs the DB flag when
   a role is live on-chain but `role_granted=False` (receipt arrived after the 90s ceiling), and
   **re-grants** when the role is missing on-chain (dropped grant). Idempotent; `--dry-run`,
   `--user-id`, `--no-fund`. Run it after any Sepolia enrollment that logged "Failed to grant
   blockchain role … receipt pending".

**Verification gate (all green):** pytest **76 passed / 2 skipped**; Hardhat e2e **7/7
three-way matches** in 13.7s (gas refactor touches no anchored hash); `reconcile_roles` regrant
path exercised live (revoke → reconcile → role restored + DB synced); `reconcile_batches`
runs clean on a real DISTRIBUTED batch. Manual Sepolia S0→S5 confirmed working by Ian.

**NOT captured:** the e2e evidence artifact (`sepolia-lifecycle-evidence.md`) was **not**
refreshed for the Sprint-13 pre-images — the e2e run was skipped (manual walk used instead).
The Sprint-9 evidence (batch `0x2c5c47…`, 7/7) still stands; tonight's manual walk + the gas
fix corroborate it. If the defense wants fresh on-chain evidence on the new pre-images, run
`python scripts/e2e_lifecycle.py` against Sepolia (~340s, now reliable post-gas-fix) and capture.

---

## 9. Day 2 plan (2026-06-09) — presentation-readiness

**Primary: GeoAI sugar + pollen "measurable properties" coherence** (so the pending/placeholder
sections can be finalized). Background: `reference_geoai_model_contract` + DEBUG-RUNBOOK §14.2.

- **Sucrose/sugar:** measured + anchored on-chain but **excluded from the authenticity score**
  because the model's `sucrose_level` target predicts *total sugar* (~75) not *true sucrose*
  (~4%) — a labeling mismatch. Decision for the prototype:
  - **(A) UI-only (recommended for tomorrow):** keep it excluded; relabel the displayed field
    as a recorded measurement ("measured, not scored — under review"), remove any placeholder
    text implying it gates authenticity. No model retrain (no time before the defense).
  - **(B) Model relabel:** model-team retrains/relabels the target to true sucrose, then re-add
    to the score. Out of scope for tomorrow; track as post-defense.
- **Pollen density:** decoupled from the score in Sprint 13 (the prediction's pollen component
  is region-derived, not from the entered value). UI must reflect this — entered pollen is a
  recorded measurement, not a score input. Fix placeholder labels/tooltips that still imply it
  drives the score.
- **Then:** sweep the lab/scan UI sections left as placeholders for these two properties and
  make them consistent with the Sprint-13 scoring model (moisture + HMF + triangulation +
  confidence are the score axes; sugar + pollen are measured-but-not-scored).

> Tomorrow, brainstorm A-vs-B with the team/supervisor before touching UI — it decides the
> consumer-facing wording.

**Also important (don't forget):**
1. **Security P0a** — narrow `vite.config.js` `allowedHosts` (frontend, §3). Trivial, still open.
2. **Docs** — fold the gas/EIP-1559 behavior + `reconcile_roles.py` into DEBUG-RUNBOOK §11 and
   backend CLAUDE.md (impact-shield note on `blockchain.py` gas; known-issue #3 fund amount is
   now 0.01). Future Sepolia runs need the "dropped tx → run reconcile_roles" guidance.
3. **FE cleanup carryover** (§2 P1): ProcessorDashboard stale `PackageJarQRs` import; `BatchQR`
   print overlay; optional `ProtectedRoute` auth guards.
4. **Open the Sprint-14 backend PR** to `main`.
