# Sepolia Lifecycle Evidence — End-to-End Honey Batch Traceability

**Date of run:** 2026-05-18 (Sprint 9 re-verification)
**Network:** Ethereum Sepolia testnet (Chain ID 11155111)
**RoleManager contract:** [`0x27c71713aef68728f39b6D82837C70639559C0A7`](https://sepolia.etherscan.io/address/0x27c71713aef68728f39b6D82837C70639559C0A7)
**TraceabilityRegistry contract:** [`0xBe0302b5F34F05C1347780EF72086aE9b5c43162`](https://sepolia.etherscan.io/address/0xBe0302b5F34F05C1347780EF72086aE9b5c43162)
**Batch ID:** `0x2c5c47b5d50243f8d698616143dec0cd9c44a05d49bde5386f9e83c9c5683fc3`
**Backend revision:** Sprint 9 (typed `batch_metadata` row authoritative;
legacy free-form `metadata: dict` path hard-cut to 422; legacy
`honey_batches.metadata_payload` JSON mirror column dropped in migration
`c0d1e2f3a4b5`). Alembic head at run time: `c0d1e2f3a4b5`.
**Total wall-clock:** 340.3 s (vs. 258.0 s in Sprint 6 — the extra ~80 s is the
additional `batch_metadata` row insert/flush on `POST /batches/` plus general
Sepolia block-confirmation variance for this run).

## Why this artifact exists

This document is the project-deliverable proof that the ApiChain Kenya
backend drives the full 6-state honey traceability lifecycle on a public
Ethereum testnet, end to end, without cheating: each transition is signed
by a different wallet (the per-user pattern required by the smart
contract), the lab verification uses the system oracle key, and the
public `/verify` endpoint reads back what was written.

Sprint 9 closes the last gap in the three-way verification story.
Sprint 6 extended Sprint 4/5's proof from one stage (lab) to six stages
(apiary, harvest, process, lab, packaging, distribution). Sprint 8
added a typed `batch_metadata` row + `verification.metadata` block to
`/verify`. Sprint 9 made that typed shape the **only** accepted shape
(hard-cut from `Union[BatchMetadataInput, dict]` to plain
`BatchMetadataInput` after the first Hardhat e2e exposed that Pydantic
smart-Union routing was silently sending typed payloads to the dict
branch) and dropped the legacy `honey_batches.metadata_payload` mirror
column.

The result: **every chain hash in the seven-stage lifecycle is now
independently recomputable from a single normalized DB row.** For every
stage below, the canonical pre-image re-hashed from the persisted
`*_records` / `batch_metadata` row at scan time agrees byte-for-byte with
both the DB-stored `*_proof_hash` column and the on-chain hash returned
by `getBatch()`. Every transaction is independently verifiable on
Etherscan.

## How to reproduce

```bash
# 1. Configure backend/.env with Sepolia values:
#    BLOCKCHAIN_RPC_URL=<alchemy sepolia url>
#    ROLE_MANAGER_ADDRESS=0x27c71713aef68728f39b6D82837C70639559C0A7
#    REGISTRY_ADDRESS=0xBe0302b5F34F05C1347780EF72086aE9b5c43162
#    ADMIN_PRIVATE_KEY=<deployer key>
#    ORACLE_PRIVATE_KEY=<deployer key>    # iteration 1: same EOA
#    CHAIN_ID=11155111
#    WALLET_ENCRYPTION_KEY=<Fernet key>
#    SUPER_ADMIN_CODE=<invite code>
#
# (A pre-populated backend/.env.sepolia ships with the repo for convenience;
#  cp .env.sepolia .env after backing up the local-Hardhat .env.)

# 2. Apply Sprint 9 migration + truncate
alembic upgrade head        # head c0d1e2f3a4b5 (drops metadata_payload)
psql ... -c "TRUNCATE TABLE
  batch_metadata, apiary_records, distribution_records, packaging_records,
  process_records, harvest_records, lab_results, environmental_data,
  honey_batches, documents, eth_wallets, apiary_locations, farmers, users
  RESTART IDENTITY CASCADE"

# 3. Start backend
uvicorn app.main:app --port 8000

# 4. Run e2e (httpx client must wait at least 90 s receipt ceiling)
python scripts/e2e_lifecycle.py --base-url http://localhost:8000 \
  --invite-code "<SUPER_ADMIN_CODE>"
```

## What was anchored (the 7 stage hashes, verified three-way)

All seven entries are `match: true` under `verification.{stage}` on
`GET /batches/{id}/verify`, where `match := db_hash == chain_hash ==
recomputed_hash` AND `chain_hash != 0x00…00`. The `metadata` row is
anchored within the S0 `createBatch` call (alongside `apiaryHash`), so
six on-chain transactions cover seven verifiable stages.

| Stage | Anchored hash | Source row |
|-------|---------------|-----------|
| **apiary** (S0)        | `0xb1a59a7e9b7c4fbadeb5964ad7ccc1bdbfd0dc434182b68a568564b3e59f4a3c` | `apiary_records` |
| **metadata** (S0)      | `0xa091c34205e7273f27facf3970e362ca9b79fe02444744117fc094044b53a2c8` | `batch_metadata` (Sprint 8/9 new) |
| **harvest** (S1)       | `0xc694b5aeeb18a4c320b49fd099c1ccc2d68695b50fdede88e146e636fc903a27` | `harvest_records` |
| **process** (S2)       | `0x160f60023bad4bbda94219369f0dbf09f9551894e55c98eb6c0309150b4922a4` | `process_records` |
| **lab** (S3)           | `0xf2111e036947acdc8b2b704a3d2cc4681323698eaf65e11a59dfb2644d8fa14a` | `lab_results` |
| **packaging** (S4)     | `0x4dc0fc0d2cc208c3834d7ebf88978ea343bc404326e581e3afbddbda2a6bd0f3` | `packaging_records` |
| **distribution** (S5)  | `0x5ddb723fab5c32abb418b7a783c14a0c4f06c646944c4e491897caee31d936ef` | `distribution_records` |

## The 6 on-chain transactions

Each tx is signed by the per-user wallet for that role (oracle is the
deployer EOA for lab-verify in iteration 1). Click any tx hash to view
on Etherscan.

| Stage | Signer role | Signer address | Tx | Block time (UTC) |
|-------|-------------|----------------|----|------------------|
| **CREATE** (S0)     | farmer (beekeeper)        | `0x1966d9CD37780eE52360667f2ff5266b04cc5C2C` | [`0x1dbed06b85b4ba129793b75fec33e382849442c6dfd798134b83325567829c6d`](https://sepolia.etherscan.io/tx/0x1dbed06b85b4ba129793b75fec33e382849442c6dfd798134b83325567829c6d) | 2026-05-18 18:54:36 |
| **HARVEST** (S1)    | farmer (beekeeper)        | `0x1966d9CD37780eE52360667f2ff5266b04cc5C2C` | [`0x31e7842051e90f4adb545dae21ee90b3b682c52f7433da8e380bfe78acbc6c9b`](https://sepolia.etherscan.io/tx/0x31e7842051e90f4adb545dae21ee90b3b682c52f7433da8e380bfe78acbc6c9b) | 2026-05-18 18:55:00 |
| **PROCESS** (S2)    | harvest_processor         | `0x95F3a0cFC5DBB28B02d5485C3ae133B7B8d9BF27` | [`0xddd366127b02fa190d0b56ece3b63d9a7cb7e960a0960ddb3f17e35a841cac78`](https://sepolia.etherscan.io/tx/0xddd366127b02fa190d0b56ece3b63d9a7cb7e960a0960ddb3f17e35a841cac78) | 2026-05-18 18:55:24 |
| **LAB_VERIFY** (S3) | lab_test_officer (oracle) | deployer EOA                                 | [`0xa65d551be2073854803ab8c6fe671b553b3f90f618022290d9ec9e0230ec6da0`](https://sepolia.etherscan.io/tx/0xa65d551be2073854803ab8c6fe671b553b3f90f618022290d9ec9e0230ec6da0) | 2026-05-18 18:55:36 |
| **PACKAGE** (S4)    | packager                  | `0xCdCb33BC821cbE5DaaA1f2FCd75955254c175c4f` | [`0xeab1c9a4c5b5b90eddb12671e7667bd79cd2b3f7732d0252fd81e3395aecf3b4`](https://sepolia.etherscan.io/tx/0xeab1c9a4c5b5b90eddb12671e7667bd79cd2b3f7732d0252fd81e3395aecf3b4) | 2026-05-18 18:56:12 |
| **DISTRIBUTE** (S5) | distributor               | `0x93cf62Ec2Af58AF1bA919d76ff5938B466090620` | [`0xdc31c64a5345a8e4a2b1f4feb27daf49a1357a5a83e8a1d042aa5d73ddbf00f2`](https://sepolia.etherscan.io/tx/0xdc31c64a5345a8e4a2b1f4feb27daf49a1357a5a83e8a1d042aa5d73ddbf00f2) | 2026-05-18 18:56:36 |

**Wallet provenance:** all four non-deployer wallets (farmer +
harvest_processor + packager + distributor) were generated by the
backend during enrollment (`POST /users/create-employee` and
`POST /farmers/create-farmer`), encrypted with the local Fernet key, and
funded with 0.001 ETH each by the deployer admin key before signing.
The on-chain `beekeeper` field on the batch is the farmer's own wallet
(`0x1966…5C2C`), not the deployer — i.e. provenance is preserved on
chain, not just in the backend DB. `on_ground_officer` and
`lab_test_officer` have no per-user wallet in iteration 1 by design
(officer is off-chain; lab uses the shared oracle key).

## Three-way hash table (the proof that anchored = stored = recomputed)

For each stage, three columns must be identical hex for
`verification.{stage}.match` to be `true` on `/verify`. All seven rows
below pass; the column-collapsed form (`db_hash == chain_hash ==
recomputed_hash`) is what the QR scan UI gates the green "Blockchain
Verified" badge on.

| Stage | `db_hash` | `chain_hash` | `recomputed_hash` | match |
|-------|-----------|--------------|-------------------|-------|
| apiary       | `…59f4a3c` | `…59f4a3c` | `…59f4a3c` | ✓ |
| metadata     | `…4b53a2c8` | `…4b53a2c8` | `…4b53a2c8` | ✓ |
| harvest      | `…fc903a27` | `…fc903a27` | `…fc903a27` | ✓ |
| process      | `…b4922a4` | `…b4922a4` | `…b4922a4` | ✓ |
| lab          | `…d8fa14a` | `…d8fa14a` | `…d8fa14a` | ✓ |
| packaging    | `…a6bd0f3` | `…a6bd0f3` | `…a6bd0f3` | ✓ |
| distribution | `…1d936ef` | `…1d936ef` | `…1d936ef` | ✓ |

(Full 32-byte hashes are in the "What was anchored" table above. The
collapsed suffix here is just for visual scan.)

## Metadata round-trip (Sprint 9 headline)

The typed `BatchMetadataInput` submitted in the `POST /batches/` request
body comes back through `/verify` as `batch_metadata`, unchanged:

| Field | Submitted | Returned on `/verify` |
|-------|-----------|----------------------|
| `honey_type`               | `wildflower`     | `wildflower` |
| `expected_yield_kg`        | `50.00`          | `50.00` |
| `harvest_window_start`     | `2026-05-01`     | `2026-05-01` |
| `harvest_window_end`       | `2026-05-31`     | `2026-05-31` |
| `apiary_management_method` | `organic`        | `organic` |
| `notes`                    | `e2e run`        | `e2e run` (hashed-excluded, display-included by design — farmers can correct a typo without invalidating chain history) |

`metadata_proof_hash` on the persisted `batch_metadata` row matches
`chain_hash` from `getBatch().metadata_hash` matches
`compute_data_hash(_metadata_record_canonical_payload(row))` recomputed
at scan time. Three-way verified, on Sepolia, on real funds.

## Tamper test (local Hardhat, not run on Sepolia)

A separate run on local Hardhat with the same Sprint 9 backend verifies
that mutating any stage's persisted row flips only that stage's
`match` to `false` without affecting the other six. This is the
mechanical inverse proof: the hash IS the canonical pre-image,
post-anchor changes are detected.

Example: `UPDATE batch_metadata SET honey_type = 'acacia' WHERE batch_id = <id>` →
`verification.metadata.match` becomes `false` (recomputed_hash diverges
from db_hash + chain_hash), all other six blocks remain `true`. See
`tests/test_metadata_hash.py` and `tests/test_apiary_hash.py` for the
unit-test versions.

## What is NOT in this evidence (intentional)

- **Environmental snapshot.** `POST /batches/` doesn't fetch one; only
  `POST /batches/simple` does. `environmental_data` is `null` in the
  `/verify` response above by design.
- **Reconciler in action.** This run didn't trigger any
  `ReceiptPendingError` because Sepolia confirmed each tx within the
  90 s ceiling. The reconciler-as-scheduler-job is wired, unit-tested,
  and fires live every 60 s (logged during the local Hardhat Sprint 9
  e2e); it would mirror chain state back into the DB on the next tick
  if any 202 had been returned.
- **Standalone `/batches/{id}/hashes` endpoint** still returns 6 fields
  (apiary + 5 stages); the metadata hash is exposed via `/verify` only.
  Extending `services/blockchain.py:get_batch_hashes()` to include
  `metadata_hash` is tracked as a low-priority follow-up.
