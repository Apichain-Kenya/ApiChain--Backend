# Sepolia Lifecycle Evidence — End-to-End Honey Batch Traceability

**Date of run:** 2026-05-17 (Sprint 6 re-verification)
**Network:** Ethereum Sepolia testnet (Chain ID 11155111)
**RoleManager contract:** [`0x27c71713aef68728f39b6D82837C70639559C0A7`](https://sepolia.etherscan.io/address/0x27c71713aef68728f39b6D82837C70639559C0A7)
**TraceabilityRegistry contract:** [`0xBe0302b5F34F05C1347780EF72086aE9b5c43162`](https://sepolia.etherscan.io/address/0xBe0302b5F34F05C1347780EF72086aE9b5c43162)
**Batch ID:** `0x6fe6548eb8368f07529c0876382fc19ff5b6ee379ab7c4e676858220701a5380`
**Backend revision:** Sprint 6 (RPC retry / 90 s ceiling / `ReceiptPendingError`
202 path / `apiary_records` structured S0).
**Total wall-clock:** 258.0 s (vs. ~200 s in Sprint 4 — the extra ~60 s is the
additional `POST /apiary-locations/` step + the new `apiary_records` insert/flush
on `POST /batches/`).

## Why this artifact exists

This document is the project-deliverable proof that the ApiChain Kenya
backend drives the full 6-state honey traceability lifecycle on a public
Ethereum testnet, end to end, without cheating: each transition is signed
by a different wallet (the per-user pattern required by the smart
contract), the lab verification uses the system oracle key, and the
public `/verify` endpoint reads back what was written.

Sprint 6 extends the Sprint 4/5 three-way-hash proof from one stage (lab)
to **all six stages**. For every transition below, the canonical pre-image
re-hashed from the persisted `*_records` row at scan time agrees
byte-for-byte with both the DB-stored `*_proof_hash` column and the
on-chain hash returned by `getBatch()`. Every transaction is independently
verifiable on Etherscan.

Sprint 6 also resolves the Sprint 4 carry-over where Sepolia's DISTRIBUTE
step intermittently returned HTTP 502 because the hardcoded 30 s
`wait_for_transaction_receipt` fired before the tx confirmed. The new
`_wait_for_receipt(ceiling_s=90)` with exponential poll backoff absorbed
the long tail cleanly — DISTRIBUTE completed in 12 s of block time this
run, no 502, no pending-confirmation 202 path triggered.

## How to reproduce

```bash
# 1. Configure backend/.env with Sepolia values:
#    BLOCKCHAIN_RPC_URL=<alchemy sepolia url>
#    ROLE_MANAGER_ADDRESS=0x27c71713aef68728f39b6D82837C70639559C0A7
#    REGISTRY_ADDRESS=0xBe0302b5F34F05C1347780EF72086aE9b5c43162
#    ADMIN_PRIVATE_KEY=<deployer key>
#    ORACLE_PRIVATE_KEY=<deployer key>    # iteration 1: same EOA
#    CHAIN_ID=11155111

# 2. Apply Sprint 6 migration + truncate
alembic upgrade head        # creates apiary_records (head e5f60123abcd)
psql ... -c "TRUNCATE TABLE
  apiary_records, distribution_records, packaging_records, process_records,
  harvest_records, lab_results, environmental_data, honey_batches,
  documents, eth_wallets, apiary_locations, farmers, users
  RESTART IDENTITY CASCADE"

# 3. Start backend
uvicorn app.main:app --port 8000

# 4. Run e2e (httpx client must wait at least 90 s receipt ceiling)
python scripts/e2e_lifecycle.py --base-url http://localhost:8000 \
  --invite-code "<SUPER_ADMIN_CODE>"
```

## What was anchored (the 6 stage hashes, verified three-way)

All six entries are `match: true` under `verification.{stage}` on
`GET /batches/{id}/verify`, where `match := db_hash == chain_hash ==
recomputed_hash` AND `chain_hash != 0x00…00`.

| Stage | Anchored hash | Source row |
|-------|---------------|-----------|
| **apiary** (S0) | `0xb1a59a7e9b7c4fbadeb5964ad7ccc1bdbfd0dc434182b68a568564b3e59f4a3c` | `apiary_records` (Sprint 6 new) |
| **harvest** (S1) | `0xe6e00e16b26d41244e3b50657bff120e8c92b50dcbd3a89adc01305b1b0a1e1a` | `harvest_records` |
| **process** (S2) | `0x160f60023bad4bbda94219369f0dbf09f9551894e55c98eb6c0309150b4922a4` | `process_records` |
| **lab** (S3) | `0xf2111e036947acdc8b2b704a3d2cc4681323698eaf65e11a59dfb2644d8fa14a` | `lab_results` |
| **packaging** (S4) | `0x4dc0fc0d2cc208c3834d7ebf88978ea343bc404326e581e3afbddbda2a6bd0f3` | `packaging_records` |
| **distribution** (S5) | `0x5ddb723fab5c32abb418b7a783c14a0c4f06c646944c4e491897caee31d936ef` | `distribution_records` |

## The 6 on-chain transactions

Each tx is signed by the per-user wallet for that role (oracle is the
deployer EOA for lab-verify in iteration 1). Click any tx hash to view
on Etherscan.

| Stage | Signer role | Signer address | Tx | Block time (UTC) |
|-------|-------------|----------------|----|------------------|
| **CREATE** (S0)     | farmer (beekeeper)        | `0xBe783d4545524A9562d485199B4583d6b17fC8cd` | [`0xa7da36fd5894e5a2d23f50a1dbd49c6bb1bc69751aa7242adf2fa5b6d1ef778d`](https://sepolia.etherscan.io/tx/0xa7da36fd5894e5a2d23f50a1dbd49c6bb1bc69751aa7242adf2fa5b6d1ef778d) | 2026-05-17 08:23:00 |
| **HARVEST** (S1)    | farmer (beekeeper)        | `0xBe783d4545524A9562d485199B4583d6b17fC8cd` | [`0x8f376cdf4bf5f16b582b05270ce3936597146ec64d5eb10eb61e45d0e7acce7f`](https://sepolia.etherscan.io/tx/0x8f376cdf4bf5f16b582b05270ce3936597146ec64d5eb10eb61e45d0e7acce7f) | 2026-05-17 08:23:12 |
| **PROCESS** (S2)    | harvest_processor         | `0x8D0034bB377C48173ec51bC1909f89350Cd07197` | [`0x99bf314e496d2159ecaed5139d3688f240e3ec55ab6a340521f54f1f15635807`](https://sepolia.etherscan.io/tx/0x99bf314e496d2159ecaed5139d3688f240e3ec55ab6a340521f54f1f15635807) | 2026-05-17 08:24:00 |
| **LAB_VERIFY** (S3) | lab_test_officer (oracle) | `0x6d6bE144Ce4cE281F2489fBaFA4f47C6D5BF98D7` | [`0x9019fc990b541daef404fe0417129e2420d71c69b88ca502864ac4afdcd6813a`](https://sepolia.etherscan.io/tx/0x9019fc990b541daef404fe0417129e2420d71c69b88ca502864ac4afdcd6813a) | 2026-05-17 08:24:24 |
| **PACKAGE** (S4)    | packager                  | `0x1D5F6c55B1723e49959521A9329991EB5c5d7c50` | [`0xfc1ba66862e88f1679a3cef69d5231e23e0f7a0116e2724635ba59e470a56e77`](https://sepolia.etherscan.io/tx/0xfc1ba66862e88f1679a3cef69d5231e23e0f7a0116e2724635ba59e470a56e77) | 2026-05-17 08:24:36 |
| **DISTRIBUTE** (S5) | distributor               | `0x32f2C08E4187d55448853eA94C94A3C51CdfA484` | [`0x19ada4e69b00e25c2e48d82b9e3d2157bae1bf6f520a0c1791e01e5c32bab3a5`](https://sepolia.etherscan.io/tx/0x19ada4e69b00e25c2e48d82b9e3d2157bae1bf6f520a0c1791e01e5c32bab3a5) | 2026-05-17 08:24:48 |

**Wallet provenance:** all five non-deployer wallets were generated by the
backend during enrollment (`POST /users/create-employee` and
`POST /farmers/create-farmer`), encrypted with the local Fernet key, and
funded with 0.001 ETH each by the deployer admin key before signing. The
on-chain `beekeeper` field on the batch is the farmer's own wallet
(`0xBe78…F8cd`), not the deployer — i.e. provenance is preserved on chain,
not just in the backend DB.

## Three-way hash table (the proof that anchored = stored = recomputed)

For each stage, three columns must be identical hex for
`verification.{stage}.match` to be `true` on `/verify`. All six rows
below pass; the column-collapsed form (`db_hash == chain_hash ==
recomputed_hash`) is what the QR scan UI gates the green "Blockchain
Verified" badge on.

| Stage | `db_hash` | `chain_hash` | `recomputed_hash` | match |
|-------|-----------|--------------|-------------------|-------|
| apiary       | `…59f4a3c` | `…59f4a3c` | `…59f4a3c` | ✓ |
| harvest      | `…b0a1e1a` | `…b0a1e1a` | `…b0a1e1a` | ✓ |
| process      | `…b4922a4` | `…b4922a4` | `…b4922a4` | ✓ |
| lab          | `…d8fa14a` | `…d8fa14a` | `…d8fa14a` | ✓ |
| packaging    | `…a6bd0f3` | `…a6bd0f3` | `…a6bd0f3` | ✓ |
| distribution | `…1d936ef` | `…1d936ef` | `…1d936ef` | ✓ |

(Full 32-byte hashes are in the "What was anchored" table above. The
collapsed suffix here is just for visual scan.)

## Tamper test (local Hardhat, not run on Sepolia)

A separate run on local Hardhat with the same Sprint 6 backend verifies
that mutating any stage's persisted row flips only that stage's
`match` to `false` without affecting the other five. This is the
mechanical inverse proof: the hash IS the canonical pre-image,
post-anchor changes are detected.

Example: `UPDATE apiary_records SET latitude = 0.0 WHERE batch_id = <id>` →
`verification.apiary.match` becomes `false` (recomputed_hash diverges
from db_hash + chain_hash), all other five blocks remain `true`. See
`tests/test_apiary_hash.py` for the unit-test version.

## What is NOT in this evidence (intentional)

- **Metadata hash three-way comparison.** The on-chain `metadataHash`
  was computed from the request body's free-form `metadata` dict, not
  a structured row. Sprint 7 ships the metadata schema after a
  stakeholder conversation. The `metadataHash` still ANCHORS, but
  `/verify` cannot today show a recomputed-hash column for it.
- **Environmental snapshot.** `POST /batches/` doesn't fetch one; only
  `POST /batches/simple` does. `environmental_data` is `null` in the
  /verify response above by design.
- **Reconciler in action.** This run didn't trigger any
  `ReceiptPendingError` because Sepolia confirmed each tx within the
  90 s ceiling. The reconciler-as-scheduler-job is wired and unit-tested;
  it would mirror chain state back into the DB on the next 60 s tick if
  any 202 had been returned.
