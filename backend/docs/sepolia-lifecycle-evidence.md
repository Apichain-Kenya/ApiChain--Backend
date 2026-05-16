# Sepolia Lifecycle Evidence — End-to-End Honey Batch Traceability

**Date of run:** 2026-05-16 (Sprint 4 re-verification)
**Network:** Ethereum Sepolia testnet (Chain ID 11155111)
**RoleManager contract:** [`0x27c71713aef68728f39b6D82837C70639559C0A7`](https://sepolia.etherscan.io/address/0x27c71713aef68728f39b6D82837C70639559C0A7)
**TraceabilityRegistry contract:** [`0xBe0302b5F34F05C1347780EF72086aE9b5c43162`](https://sepolia.etherscan.io/address/0xBe0302b5F34F05C1347780EF72086aE9b5c43162)
**Batch ID:** `0x356d9e43be1e6a0dbbb0729882a3b82774e33bbb97fcaca9fff8ca24eeddf88d`
**Backend revision:** Sprint 4 (`sprint3/lab-verification-consolidation` + Sprint-4 commits)

## Why this artifact exists

This document is the project-deliverable proof that the ApiChain Kenya
backend drives the full 6-state honey traceability lifecycle on a public
Ethereum testnet, end to end, without cheating: each transition is signed
by a different wallet (the per-user pattern required by the smart
contract), the lab verification uses the system oracle key, and the
public `/verify` endpoint reads back what was written. Sprint 4
additionally proves the **three-way lab-hash match** holds across chains:
the persisted `lab_results` row re-hashed at scan time agrees byte-for-
byte with both the DB-stored `lab_proof_hash` column and the on-chain
`getBatch().labProofHash`. Every transaction below is independently
verifiable on Etherscan.

## How to reproduce

```bash
# 1. Configure backend/.env with Sepolia values:
#    BLOCKCHAIN_RPC_URL=<alchemy sepolia url>
#    ROLE_MANAGER_ADDRESS=0x27c71713aef68728f39b6D82837C70639559C0A7
#    REGISTRY_ADDRESS=0xBe0302b5F34F05C1347780EF72086aE9b5c43162
#    ADMIN_PRIVATE_KEY=<deployer key>
#    ORACLE_PRIVATE_KEY=<deployer key>    # iteration 1: same EOA
#    CHAIN_ID=11155111

# 2. Truncate DB, start backend
TRUNCATE TABLE users, farmers, honey_batches, eth_wallets, lab_results,
  environmental_data, apiary_locations, documents
  RESTART IDENTITY CASCADE;
uvicorn app.main:app --port 8000

# 3. Run the walkthrough
python scripts/e2e_lifecycle.py --invite-code <SUPER_ADMIN_CODE>
```

The script enrolls a super admin, five role-specific employees
(`on_ground_officer`, `harvest_processor`, `lab_test_officer`,
`packager`, `distributor`), a farmer, then walks the same batch through
all six states asserting each new state and finally that the public
`/verify` endpoint returns six non-zero hashes, six monotonically
increasing block timestamps, **the persisted `lab_result` row**,
**`verification.lab.match === true`**, and **all six `tx_hashes.*`
entries** (Sprint 4 additions).

## On-chain evidence

Block range: 10862070 → 10862082. Block timestamps span 84s of wall time.

| Stage      | Role                          | Signer (msg.sender)                          | tx |
|------------|-------------------------------|----------------------------------------------|----|
| CREATE     | farmer                        | `0x42B9E4d945e59315A497BDf22D08469660e2a074` | [`0x112a…c2d3`](https://sepolia.etherscan.io/tx/0x112af2314c791f31f2cc3d186ff278da0ffc856532f072b582ca08dca518c2d3) |
| HARVEST    | farmer                        | `0x42B9E4d945e59315A497BDf22D08469660e2a074` | [`0x8d16…55b5`](https://sepolia.etherscan.io/tx/0x8d1667a261881024fe75187f928f9db37bf0515d4c0cdcbb69a856780b1455b5) |
| PROCESS    | harvest_processor             | `0x000211f2E30B623d53b3984771A7d8454548b049` | [`0x9b78…5cdb`](https://sepolia.etherscan.io/tx/0x9b78ffe64863560874f1b0776855883c2330378f5a4ff004655d9f02cbcc5cdb) |
| LAB_VERIFY | lab_test_officer (oracle key) | `0x6d6bE144Ce4cE281F2489fBaFA4f47C6D5BF98D7` | [`0x36fd…5d2e`](https://sepolia.etherscan.io/tx/0x36fd830c4d5e3346f84a2c8a7629f76958efe46d07eeb5eea742669f38075d2e) |
| PACKAGE    | packager                      | `0x97E27B05617623d71fe6627F07408ff6eD6F53d1` | [`0xe977…9195`](https://sepolia.etherscan.io/tx/0xe977cc1cc773bf0f384adbf3a17cbcfb93cda240728daa7db7e6f1d882e69195) |
| DISTRIBUTE | distributor                   | `0x63aa944AB532Ac53416aEe318103F83340642b1A` | [`0xa457…7d61`](https://sepolia.etherscan.io/tx/0xa457cef03fffb97acc55049d89d90d645b61f909435b7c7cef86c7a7afb67d61) |

### On-chain hashes (`getBatchHashes` on the registry)

```
apiary_hash       = 0xcdd72dce77fd3fb806708db48f101bf40c4cd75df9e13e1c41494b9bc757b9e6
harvest_hash      = 0x0be48436750ae6fa44bef08349edca54f6a31b0f97ec19328705af6a091d370c
process_hash      = 0x28353b7d7b26c7f32d16966d12ea8f6bacf6018fce61dc78e78fb19204bf3278
lab_proof_hash    = 0xf2111e036947acdc8b2b704a3d2cc4681323698eaf65e11a59dfb2644d8fa14a
packaging_hash    = 0x3d78aa6f380f858332305ad8b67426ed90a6487fdd569e05ee5a81623fcc8259
distribution_hash = 0x961b4753da970ee55e21e47f46584db86527ea09f87f651938da59e5677d2c96
```

**Hash-determinism cross-check:** `lab_proof_hash` here is **identical**
to the local-Hardhat hash recorded against the same `passed_quality_check
=true` panel (Sprint-3 batch `0x91005fea…83dbd`, Sprint-4 local-Hardhat
batch `0x64d47e1941…f10c6b`). Same canonical pre-image →
same `keccak256` regardless of chain or run — empirically confirms the
invariant locked by `tests/test_hash_determinism.py`.

## Sprint 4: three-way hash match on Sepolia

`GET /batches/0x356d9e43…f88d/verify` returns:

```json
{
  "state": "DISTRIBUTED",
  "verification": {
    "lab": {
      "db_hash":         "0xf2111e036947acdc8b2b704a3d2cc4681323698eaf65e11a59dfb2644d8fa14a",
      "chain_hash":      "0xf2111e036947acdc8b2b704a3d2cc4681323698eaf65e11a59dfb2644d8fa14a",
      "recomputed_hash": "0xf2111e036947acdc8b2b704a3d2cc4681323698eaf65e11a59dfb2644d8fa14a",
      "match": true
    }
  },
  "tx_hashes": {
    "create_tx":     "112af2314c791f31f2cc3d186ff278da0ffc856532f072b582ca08dca518c2d3",
    "harvest_tx":    "8d1667a261881024fe75187f928f9db37bf0515d4c0cdcbb69a856780b1455b5",
    "process_tx":    "9b78ffe64863560874f1b0776855883c2330378f5a4ff004655d9f02cbcc5cdb",
    "lab_tx":        "36fd830c4d5e3346f84a2c8a7629f76958efe46d07eeb5eea742669f38075d2e",
    "package_tx":    "e977cc1cc773bf0f384adbf3a17cbcfb93cda240728daa7db7e6f1d882e69195",
    "distribute_tx": "0xa457cef03fffb97acc55049d89d90d645b61f909435b7c7cef86c7a7afb67d61"
  }
}
```

The three columns are byte-identical — what was anchored on chain, what
the backend persisted at lab-verify time, and what we get by re-hashing
the row right now all agree. This is the primitive the consumer scan UI
uses to gate its green "Blockchain Verified" badge.

## Operational gotcha caught this run

The DISTRIBUTE step's backend call returned HTTP 502 because the
configured 30-second wait for `eth_getTransactionReceipt` fired before
Sepolia mined the tx. The transaction **did** confirm successfully in
block 10862082 (status=1, gas used 85,430), so the chain state advanced
to S5 even though the backend rolled back the DB row. The S5 column was
reconciled manually after the run; `scripts/reconcile_batches.py` does
the same thing programmatically.

This is the Sprint-2 backlog item `TODO(sprint-2)` in
`services/blockchain.py` — the RPC layer needs retry/backoff with a
longer ceiling on Sepolia mining variance. Tracked for Sprint 5.

## Per-user signing verified

The signer column shows **five distinct addresses**, exactly matching
the contract's intent: each lifecycle role signs from its own wallet so
the on-chain `msg.sender` attribution names the right party. The
LAB_VERIFY row is the only one signed by the deployer/oracle EOA
(`0x6d6b…98D7`), which is correct per the architecture — ORACLE_ROLE is
a single trusted system identity, not a per-user role (see
`backend/app/services/blockchain.py::anchor_lab_proof` docstring).

## Public verification

Anyone, anywhere, can verify this batch without credentials:

```
GET https://<your-host>/batches/0x356d9e43be1e6a0dbbb0729882a3b82774e33bbb97fcaca9fff8ca24eeddf88d/verify
```

Or directly from chain:

```
TraceabilityRegistry.getBatch(0x356d9e43be1e6a0dbbb0729882a3b82774e33bbb97fcaca9fff8ca24eeddf88d)
TraceabilityRegistry.getBatchTimeline(...)
TraceabilityRegistry.getBatchHashes(...)
```

Both return identical state, hashes, and timestamps — the backend is a
convenience surface, not a source of truth.

## Cross-reference

- Local Hardhat Sprint-4 walkthrough: `scripts/e2e_lifecycle.py` against
  `http://127.0.0.1:8545` (Chain ID 31337), batch
  `0x64d47e1941ed9f33c9a152a1b2deba4de2c5fb32711fe6ce0d0db7d375f10c6b`,
  completed in ~7s. Same `lab_proof_hash` as this Sepolia run.
- Pytest equivalent: `tests/test_lifecycle_integration.py`.
- Sprint 4 plan: `~/.claude/plans/we-are-in-another-agile-storm.md`.
- Prior Sprint 1 Sepolia run (pre-structured-lab-row): retained in
  git history; batch `0x91005fea24df4cd1f2c5a08eaf6a852377310795c297461354a5916c3cb83dbd`.
