# Sprint 8 + Sprint 9 Roadmap

**Status:** Forecast, surfaced at the close of Sprint 7. Two more sprints to
take the prototype from "backend mature, frontend behind" to demo-ready
for the JKUAT academic defense.

**Scope rule:** prototype completion, not production hardening.
Production-grade items (KMS, rate-limiting, multi-oracle, IPFS, backups,
Sentry) are explicitly out of scope — document them as "future work" in
the evaluation chapter and move on.

---

## Carry-over watchlist (small flags from Sprint 7)

Track these so they don't rot. None blocks Sprint 8.

1. **`backend/tests/test_lifecycle_integration.py` lines 97 + 224** still
   send `apiary_data` in the request body. That field was removed from
   `BatchCreateRequest` in Sprint 6. Tests are marker-gated
   (`@pytest.mark.requires_backend`) so they don't run in normal pytest,
   but they'll fail the moment anyone runs `pytest -m requires_backend`.
   Fix: seed an apiary via `POST /apiary-locations/` first, then pass
   `apiary_id`. Pure mechanical edit, ~20 min.

2. **Local Hardhat e2e (`python scripts/e2e_lifecycle.py`)** — deferred
   from Sprint 7. Run it before the next push to confirm the legacy-JSON
   drop in PR 1 didn't break anything end-to-end. If green, do a fresh
   Sepolia run and refresh `backend/docs/sepolia-lifecycle-evidence.md`
   (Sprint 6 watchlist #1, two sprints stale).

3. **`_canonical_dt()` discipline** — only `harvest_date` flows through it
   today. Any new datetime entering a hash payload silently breaks
   determinism if it skips the helper. One-line note in
   `backend/.claude/CLAUDE.md` Sprint 6 watchlist would lock this in.

4. **Pydantic V2 `class Config` deprecation warnings** — ~10 callsites.
   Cosmetic, but worth a single drive-by cleanup commit.

5. **Backend scheduler-wiring smoke test** — once the Sprint 7 PR is
   merged and deployed, watch the logs for `"scheduler started"` within a
   second of `"Application startup complete"`, then create a batch, kill
   uvicorn before the receipt resolves, restart, confirm the orphan row's
   `*_at` populates within 60s. Don't ship the next sprint without seeing
   this work live once.

---

## Sprint 8 — Frontend completion push

This is what gates the demo story. Backend is ahead; the audit at Sprint
7 planning surfaced three missing role dashboards, an empty farmer
dashboard, a stub register-harvest form, no 202-pending UX, and no
Swahili strings for the blockchain UI.

### In scope

- **Scaffold Lab dashboard** (`/Lab/Dashboard`). List batches in
  `PROCESSED` state, single action: trigger
  `POST /batches/{id}/lab-verify`. Pre-fill the lab-result fields, show
  success → batch moves to `LAB_VERIFIED`.
- **Scaffold Packager dashboard** (`/Packager/Dashboard`). List batches
  in `LAB_VERIFIED`, single action: trigger
  `POST /batches/{id}/package`. Per-jar QR generation already exists in
  `PackageJarQRs.jsx` — wire it in.
- **Scaffold Distributor dashboard** (`/Distributor/Dashboard`). List
  batches in `PACKAGED`, single action: trigger
  `POST /batches/{id}/distribute`.
- **Wire the "Register a harvest" form** to `POST /batches/simple`. Form
  skeleton exists in `ProcessorDashboard.jsx`; just needs the POST + error
  handling.
- **Fill in the empty `FarmerDashboard.jsx`**. Minimum: list the farmer's
  batches with state badges, link to `/Scan?b=<id>` for the public view.
- **HTTP 202 pending-tx UX**. Single axios interceptor that detects
  `status === 202` and shows a "Transaction submitted, confirming on
  chain…" toast that resolves when the next `GET /batches/{id}` shows the
  new state. Without this the frontend treats Sprint 6's pending
  responses as errors.
- **Add the 6 blockchain state names + verification badges to
  `en.json` and `sw.json`**. Already enumerated in
  `docs/blockchain-ui-spec.md`.

### Out of scope for Sprint 8 (push to Sprint 9)

- Admin role-revocation UI.
- Per-tester dashboard polish beyond the basic scaffold.
- Dedicated 404 page for invalid batch IDs.

### Estimate

Biggest single sprint of the project. Three new dashboard files + two
existing ones to flesh out + one interceptor + ~30 i18n keys. A week of
focused frontend work.

---

## Sprint 9 — Final cleanup + the metadata story

What makes the prototype feel "done" rather than "mostly working".

### In scope

- **Metadata schema implementation.** Assumes Dr. Mindila signs off on
  `backend/docs/metadata-schema-proposal.md` during Sprint 8. New
  `batch_metadata` model + migration, refactor `POST /batches/` and
  `/simple` to accept the typed shape, three-way
  `verification.metadata` block on `/verify`, three new unit tests
  mirroring `test_apiary_hash.py`. After this, every single anchored
  hash on the chain is independently verifiable.
- **Drop legacy `aggregators` table + router** (Tier 2 #8). Single
  migration + delete `aggregator.py` + remove from any remaining imports.
  Closes a deprecated surface that's been hanging around since the
  2026-04-12 pivot.
- **Admin role-revocation UI** (Tier 3 #17). `revokeActorRole` already
  exists at `RoleManager.sol:128`; just needs a button on the
  SuperAdminDashboard. ~2 hours.
- **Fix `test_lifecycle_integration.py`** (watchlist #1 above) so
  `pytest -m requires_backend` runs clean.
- **Sepolia evidence refresh** (watchlist #2 above). Fresh end-to-end
  run, capture all six tx hashes including the new structured metadata
  anchor, refresh `sepolia-lifecycle-evidence.md`.
- **CLAUDE.md cleanups.** `_canonical_dt()` discipline note
  (watchlist #3), drive-by Pydantic warnings cleanup (watchlist #4).

### Definition of done

After Sprint 9 the prototype is feature-complete for the academic
defense:
- Every role has a working dashboard.
- Every chain hash is three-way verifiable.
- The public QR/verify flow tells the full story.
- A fresh Sepolia run is recorded as evidence.

---

## Explicitly NOT in the prototype roadmap

Document each as "future work" / "production gaps identified" in the
evaluation chapter. Do not build.

- **KMS / HSM for `WALLET_ENCRYPTION_KEY`** — production hardening. The
  Fernet-in-env model is acceptable for an academic prototype as long as
  the limitation is named.
- **Rate-limiting on `/verify` + `getBatchIdsPaginated`** — relevant if
  this ships publicly, not for a demo.
- **Multi-oracle lab attestation** — iteration 2 research. Contract
  comment at `RoleManager.sol:26` already names the migration path.
- **IPFS / Arweave pinning for off-chain payloads** — iteration 2.
- **DB backups, structured logs, Prometheus, Sentry-equivalent** — all
  real concerns, all out of scope for a JKUAT prototype defense.

---

## Two-sprint summary

| Sprint | Theme | Owner-time estimate | Demo impact |
|--------|-------|---------------------|-------------|
| 8 | Frontend completion | ~1 week focused | High — unlocks role-aware demo for all 8 user types |
| 9 | Metadata + cleanup | ~3–4 days | Medium — closes the last verifiability gap + tidies surface |

Sprint 9 ends with the prototype demo-ready. Anything beyond is iteration
2 / production / publication scope.
