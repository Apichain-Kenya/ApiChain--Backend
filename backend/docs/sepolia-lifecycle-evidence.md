# Sepolia Lifecycle Evidence — End-to-End Honey Batch Traceability

**Date of run:** 2026-05-15
**Network:** Ethereum Sepolia testnet (Chain ID 11155111)
**RoleManager contract:** [`0x27c71713aef68728f39b6D82837C70639559C0A7`](https://sepolia.etherscan.io/address/0x27c71713aef68728f39b6D82837C70639559C0A7)
**TraceabilityRegistry contract:** [`0xBe0302b5F34F05C1347780EF72086aE9b5c43162`](https://sepolia.etherscan.io/address/0xBe0302b5F34F05C1347780EF72086aE9b5c43162)
**Batch ID:** `0x91005fea24df4cd1f2c5a08eaf6a852377310795c297461354a5916c3cb83dbd`
**Backend revision:** `backend-blockchain-intergration-v1.0` (post Phase 0 stabilization)
**Total wall time:** 201.7s (one batch, six transitions, average 12s/block)
**Total gas cost:** ~0.004 Sepolia ETH

## Why this artifact exists

This document is the project-deliverable proof that the ApiChain Kenya
backend can drive the full 6-state honey traceability lifecycle on a
public Ethereum testnet, end to end, without any cheating: each
transition is signed by a different wallet (the per-user pattern
required by the smart contract), the lab verification uses the system
oracle key, and the public `/verify` endpoint reads back what was
written. Every transaction below is independently verifiable on
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

# 2. Truncate DB, start backend
psql ... -c 'TRUNCATE TABLE users, farmers, honey_batches, eth_wallets RESTART IDENTITY CASCADE'
uvicorn app.main:app --port 8000

# 3. Run the walkthrough
python scripts/e2e_lifecycle.py --invite-code <SUPER_ADMIN_CODE>
```

The script enrolls a super admin, five role-specific employees
(`on_ground_officer`, `harvest_processor`, `lab_test_officer`,
`packager`, `distributor`), a farmer, then walks the same batch through
all six states asserting each new state and finally that the public
`/verify` endpoint returns six non-zero hashes and six monotonically
increasing block timestamps.

## On-chain evidence

| Stage      | Role                          | Signer (msg.sender)                        | Block    | Gas used | tx |
|------------|-------------------------------|--------------------------------------------|----------|----------|----|
| CREATE     | farmer                        | `0x0097a26F97aBAb31D922DCF0b2FefB1e03F32A4c` | 10855695 | 232,092 | [`0xd8fe...7869`](https://sepolia.etherscan.io/tx/0xd8fe3c9394a48918776fd703c3c127e701f66c397d2d07102e33b485661d7869) |
| HARVEST    | farmer                        | `0x0097a26F97aBAb31D922DCF0b2FefB1e03F32A4c` | 10855696 |  82,449 | [`0xf48a...514e`](https://sepolia.etherscan.io/tx/0xf48aa12086ce85c1db6216e12accb2c0192d86360a25ae54ef6fb8c83df7514e) |
| PROCESS    | harvest_processor             | `0x1c8F61f813C8fab3E648c8FDcEE3102fF770fB53` | 10855697 |  86,531 | [`0x1ea7...024d`](https://sepolia.etherscan.io/tx/0x1ea7bdd2c0154537802ddb88697c981251f378d31efa06b52e075edc4033024d) |
| LAB_VERIFY | lab_test_officer (oracle key) | `0x6d6bE144Ce4cE281F2489fBaFA4f47C6D5BF98D7` | 10855698 |  82,600 | [`0x8e6b...ee9c`](https://sepolia.etherscan.io/tx/0x8e6bb5787f89fa74727f68a9d9e035d6b3ad6524c5c8c05ad1d505a96486ee9c) |
| PACKAGE    | packager                      | `0x8803A581203323f275399CF5cE9c13728Fd74956` | 10855699 |  86,368 | [`0x8e04...ca56`](https://sepolia.etherscan.io/tx/0x8e04a1d31cde87dd2af6c1d436729d549952260af8a8fbd60928aa9bc306ca56) |
| DISTRIBUTE | distributor                   | `0xaAE1178A0F921F23d552abE47825c3cFb8C82beA` | 10855700 |  85,418 | [`0x9412...6275`](https://sepolia.etherscan.io/tx/0x9412624f961b13c13754e624ff709480f5f26d515656a59422c970d3b33e6275) |

**Total gas:** 655,458 across six transitions. Average non-creation
transition is ~84k gas, consistent with the local test-suite figures in
`ApiBlockchain/test/integration.test.js`.

## Per-user signing verified

The signer column shows **five distinct addresses**, exactly matching
the contract's intent: each lifecycle role signs from its own wallet so
the on-chain `msg.sender` attribution names the right party. The
LAB_VERIFY row is the only one signed by the deployer/oracle EOA
(`0x6d6b...98D7`), which is correct per the architecture — ORACLE_ROLE
is a single trusted system identity, not a per-user role (see
`backend/app/services/blockchain.py::anchor_lab_proof` docstring).

## Public verification

Anyone, anywhere, can verify this batch without credentials:

```
GET https://<your-host>/batches/0x91005fea24df4cd1f2c5a08eaf6a852377310795c297461354a5916c3cb83dbd/verify
```

Or directly from chain:

```
TraceabilityRegistry.getBatch(0x91005fea24df4cd1f2c5a08eaf6a852377310795c297461354a5916c3cb83dbd)
TraceabilityRegistry.getBatchTimeline(...)
TraceabilityRegistry.getBatchHashes(...)
```

Both return identical state, hashes, and timestamps — the backend is a
convenience surface, not a source of truth.

## What this run does NOT prove

- It does not prove that the off-chain `*_data` payloads stored in the
  `honey_batches` table match the hashes anchored on-chain. That
  property follows from the deterministic hashing invariant locked in
  by `tests/test_hash_determinism.py` and from the fact that the same
  payload bytes feed both `compute_data_hash()` and the DB column.
- It does not prove behaviour under DB-commit failure. The
  `_commit_or_orphan` helper raises a structured 500 in that case and
  `scripts/reconcile_batches.py` repairs from chain state; this is not
  exercised here because we don't induce a commit failure.
- It does not exercise role revocation, which is supported by
  `RoleManager.revokeActorRole` but not used in the iteration-1 flow.

## Cross-reference

- Local Hardhat walkthrough: `scripts/e2e_lifecycle.py` against
  `http://127.0.0.1:8545` (Chain ID 31337), completed in ~15s.
- Pytest equivalent: `tests/test_lifecycle_integration.py`.
- Source plan: `~/.claude/plans/i-think-it-s-important-temporal-lerdorf.md`.
