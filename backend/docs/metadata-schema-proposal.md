# Metadata Schema Proposal (Implemented in Sprint 8)

**Status:** Implemented as of 2026-05-18. Supervisor-approved.
**Owner:** Ian Mwau. **Supervisor sign-off:** Dr. Agnes Mindila (approved).
**Sprint 8 references:** model `app/models/batch_metadata.py`; migration
`alembic/versions/a8b9c0d1e2f3_add_batch_metadata.py`; helpers
`_metadata_record_canonical_payload` + `_verify_metadata_hash` in
`app/routers/batch.py`; unit tests `tests/test_metadata_hash.py` +
`tests/test_metadata_canonical_payload.py`.

The implementation matches sections 2 + 3 of this proposal verbatim, except
that enums are enforced at the Pydantic layer (`HoneyType` and
`ApiaryManagementMethod` in `app/schemas/batch.py`) rather than via
PostgreSQL ENUM types — this keeps the allowed-values list editable with a
one-file change instead of an `ALTER TYPE` migration. Section 5's open
questions are unresolved by design: the schema is intentionally flexible so
the team can amend it after live feedback without breaking persistence.

---

## 1. Problem

`POST /batches/` and `POST /batches/simple` both anchor a `metadataHash` on
chain at S0 alongside `apiaryHash`. Today the `metadata` field on the request
schema is a free-form `dict` (`app/schemas/batch.py:18`, hashed at
`app/routers/batch.py:247`).

This is the last unverifiable hash in the lifecycle. Sprint 6 closed the
apiary half with a structured `ApiaryRecord` row; every other stage (S1–S5)
already has a `*_records` table whose canonical payload is recomputable.
`metadataHash` cannot be three-way verified because there is no persisted
schema to recompute against.

Consequences:
- `/verify` cannot return a `verification.metadata.match` block analogous to
  the other five stages.
- Hash determinism is fragile: the frontend chooses what keys to send, in
  what order. A typo in a field name silently changes the hash.
- Audit story is weaker: a regulator cannot independently verify what
  metadata was committed at batch creation.

## 2. Proposed structure

Mirror the Sprint 5/6 pattern: a new `batch_metadata` table, one row per
batch (FK + UNIQUE on `batch_id`), with an indexed `metadata_proof_hash`
column. Pre-image written before chain anchor, rolled back on chain failure.

### Proposed fields

| Field                       | Type         | Hashed? | Notes                                                |
|-----------------------------|--------------|---------|------------------------------------------------------|
| `honey_type`                | enum (str)   | Yes     | One of: `acacia`, `wildflower`, `eucalyptus`, `sunflower`, `mixed`. List finalized with Dr. Mindila. |
| `expected_yield_kg`         | Decimal(8,2) | Yes     | Farmer's planned harvest amount. Compared at S1 by analysts. |
| `harvest_window_start`      | Date         | Yes     | UTC date, ISO-8601.                                  |
| `harvest_window_end`        | Date         | Yes     | UTC date, ISO-8601. `end >= start` enforced.         |
| `apiary_management_method`  | enum (str)   | Yes     | One of: `organic`, `conventional`, `regenerative`. Aligns with the eight-role pivot doc. |
| `notes`                     | str          | **No**  | Free-text, optional. Excluded from the hash so a farmer can amend non-material notes without invalidating S0. Stored alongside for `/verify` display only. |
| `recorded_at`               | DateTime UTC | Yes     | Routed through `_canonical_dt()` (see watchlist).    |

### Hashing rules

Canonical JSON, mirroring the existing helpers in
`app/routers/batch.py`:
- Sorted keys.
- Dates as ISO-8601 strings, UTC, no timezone suffix on dates (`YYYY-MM-DD`);
  datetimes use `_canonical_dt()` (already centralized for `harvest_date`).
- Decimals as fixed-precision strings (`"50.00"`, never `50` or `50.0`),
  to dodge float round-trip drift.
- Enums as their string value, lowercase.
- `notes` excluded from the canonical payload entirely.

## 3. Migration sketch (not implemented this sprint)

```python
# alembic/versions/<new>_add_batch_metadata.py
op.create_table(
    "batch_metadata",
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("batch_id", sa.Integer,
              sa.ForeignKey("honey_batches.id"), nullable=False, unique=True),
    sa.Column("honey_type", sa.String, nullable=False),
    sa.Column("expected_yield_kg", sa.Numeric(8, 2), nullable=False),
    sa.Column("harvest_window_start", sa.Date, nullable=False),
    sa.Column("harvest_window_end", sa.Date, nullable=False),
    sa.Column("apiary_management_method", sa.String, nullable=False),
    sa.Column("notes", sa.String, nullable=True),
    sa.Column("recorded_at", sa.DateTime, nullable=False),
    sa.Column("metadata_proof_hash", sa.String, nullable=True, index=True),
)
```

`HoneyBatch.metadata_payload` (JSON) stayed for one sprint as the legacy
mirror — same pattern as the Sprint 7 legacy-JSON deprecation. **Dropped in
Sprint 9** (migration `c0d1e2f3a4b5`). The legacy free-form `dict` path on
both `POST /batches/` and `POST /batches/simple` was also hard-cut to 422
in Sprint 9 — required after the first Hardhat e2e exposed that Pydantic
smart-Union routing was silently sending typed payloads to the dict branch.

## 4. `/verify` additions

A new `verification.metadata` block (same shape as the other five), a
`batch_metadata` public field on `BatchVerifyResponse`. Three-way comparison
matches the Sprint 5 generic `_verify_stage_hash` flow — a 1-line
`_verify_metadata_hash` wrapper.

## 5. Open questions for the supervisor

1. **Is the `honey_type` enum list above complete?** Smallholder honey in
   Kenya covers more floral sources than the proposal lists. Should the
   schema be tied to a Kenyan-specific reference list (e.g., from a KEBS or
   ministry guidance doc)?
2. **`expected_yield_kg` — sensible field, or does it leak commercial info
   that shouldn't be on a public chain?** The chain only stores the hash,
   but `/verify` is public — if `batch_metadata` returns the row, the value
   is exposed to anyone who scans the jar QR.
3. **`harvest_window_*` — is the date range the right grain?** Alternatives:
   single planned harvest date, or quarter (`2026-Q2`).
4. **`apiary_management_method` enum** — is `organic/conventional/regenerative`
   the right taxonomy for the Kenyan smallholder context? Should this
   instead be linked to a certification body's terminology?
5. **`notes` exclusion from the hash** — does this weaken the audit story?
   Argument for excluding: farmers shouldn't lose chain-anchored history by
   correcting a typo. Argument against: anything in the persisted row should
   be anchored, or it's not really part of the canonical batch identity.

## 6. Out of scope for this proposal

- IPFS / Arweave pinning for the off-chain payload (Tier 4 #20).
- Multi-language metadata fields (EN/SW labels) — the schema stores ASCII
  enum values; UI handles localization.
- Mutability after S0 — proposal is append-only for hashed fields.

## 7. If approved

Sprint 8 work, in order:
1. New schema + model + migration.
2. Refactor `POST /batches/` and `POST /batches/simple` to accept the typed
   shape; old free-form `dict` path returns 422 with a deprecation hint for
   one release.
3. Add `_verify_metadata_hash` wrapper and extend `/verify`.
4. Three new unit tests mirroring `test_apiary_hash.py` (match / tamper /
   zero-chain).
5. `e2e_lifecycle.py` asserts `verification.metadata.match is True`.
6. Drop `honey_batches.metadata_payload` one sprint after frontend confirms
   the typed path.
