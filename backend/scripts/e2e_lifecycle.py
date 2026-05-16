"""
End-to-end lifecycle walkthrough for the honey traceability backend.

Drives the full enrollment + 6-state lifecycle via HTTP only — no DB or
Web3 imports. Each step asserts the expected new_state. Final step calls
the public `/verify` endpoint and asserts all 6 tx hashes are present.

Prerequisites (before running):
    1. Hardhat node up:                  npx hardhat node
    2. Contracts deployed locally:       npx hardhat run scripts/deploy.js --network localhost
    3. Backend `.env` populated with     ROLE_MANAGER_ADDRESS, REGISTRY_ADDRESS,
       the addresses from step 2.        ADMIN_PRIVATE_KEY, ORACLE_PRIVATE_KEY,
                                         WALLET_ENCRYPTION_KEY, SUPER_ADMIN_CODE
    4. Alembic migrations applied:       alembic upgrade head
    5. Backend running:                  uvicorn app.main:app --port 8000
    6. seed_admin.py run if you want
       the deployer's wallet recorded.

Usage:
    python scripts/e2e_lifecycle.py [--base-url http://localhost:8000] [--invite-code <code>]
"""

import argparse
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone

import httpx

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("e2e_lifecycle")

DEFAULT_BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")
DEFAULT_INVITE_CODE = os.getenv("SUPER_ADMIN_CODE", "INVITE-DEV")

EMPLOYEE_ROLES = [
    "on_ground_officer",
    "harvest_processor",
    "lab_test_officer",
    "packager",
    "distributor",
]


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


def _assert(cond, msg):
    if not cond:
        raise SystemExit(f"E2E FAILED: {msg}")


def _post(client, path, json, headers=None, expect=200):
    r = client.post(path, json=json, headers=headers or {})
    if r.status_code != expect:
        raise SystemExit(f"POST {path} -> {r.status_code}: {r.text}")
    return r.json()


def _get(client, path, headers=None, expect=200):
    r = client.get(path, headers=headers or {})
    if r.status_code != expect:
        raise SystemExit(f"GET {path} -> {r.status_code}: {r.text}")
    return r.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def run(base_url: str, invite_code: str) -> int:
    rows: list[tuple[str, str, str, int]] = []  # (stage, role, tx_hash, block_ts)

    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        suffix = _suffix()
        logger.info("Using unique suffix %s for this run", suffix)

        # 1. Super admin signup
        super_admin = {
            "inviteCode": invite_code,
            "firstName": "E2E",
            "lastName": "SuperAdmin",
            "username": f"e2e_super_{suffix}",
            "email": f"e2e_super_{suffix}@example.com",
            "phone": f"+25470000{suffix[:4]}",
            "password": "TestPass123!",
        }
        # Tolerate "super admin already exists" — re-use the existing one.
        r = client.post("/users/super-admin/signup", json=super_admin)
        if r.status_code == 400 and "already exists" in r.text.lower():
            logger.info("Super admin already exists — assuming earlier run, attempting login with provided credentials")
            # Cannot login without the existing creds; require fresh DB or env value
            raise SystemExit(
                "Super admin already exists in DB. Drop and recreate the DB, or set "
                "SUPER_ADMIN_USERNAME / SUPER_ADMIN_PASSWORD to log in with existing creds. "
                "Run: psql ... -c 'TRUNCATE TABLE users, farmers, honey_batches, eth_wallets RESTART IDENTITY CASCADE'"
            )
        if r.status_code != 200:
            raise SystemExit(f"super-admin/signup failed: {r.status_code} {r.text}")
        logger.info("Super admin created")

        # Login as super admin
        super_token = _post(client, "/auth/login", {
            "identifier": super_admin["username"],
            "password": super_admin["password"],
        })["access_token"]

        # 2. Create 5 employees
        employee_credentials: dict[str, dict] = {}
        for role in EMPLOYEE_ROLES:
            user_suffix = f"{role[:4]}_{suffix}"
            payload = {
                "first_name": role,
                "last_name": "User",
                "username": f"e2e_{user_suffix}",
                "email": f"e2e_{user_suffix}@example.com",
                "phone": f"+254711{suffix[:3]}{EMPLOYEE_ROLES.index(role):02d}",
                "password": "EmpPass123!",
                "role": role,
            }
            resp = _post(client, "/users/create-employee", payload, headers=_auth(super_token))
            employee_credentials[role] = {
                "identifier": payload["username"],
                "password": payload["password"],
                "wallet_address": resp.get("wallet_address"),
                "user_id": resp["user"]["id"],
            }
            logger.info("Created %s id=%s wallet=%s", role, resp["user"]["id"], resp.get("wallet_address"))

        # 3. Login as on_ground_officer
        officer_token = _post(client, "/auth/login", {
            "identifier": employee_credentials["on_ground_officer"]["identifier"],
            "password": employee_credentials["on_ground_officer"]["password"],
        })["access_token"]

        # 4. Create a farmer
        farmer_payload = {
            "first_name": "E2E",
            "last_name": "Farmer",
            "phone": f"+254722{suffix[:5]}",
            "username": f"e2e_farmer_{suffix}",
            "email": f"e2e_farmer_{suffix}@example.com",
            "password": "FarmerPass123!",
        }
        farmer_resp = _post(client, "/farmers/create-farmer", farmer_payload, headers=_auth(officer_token))
        farmer_wallet = farmer_resp.get("wallet_address")
        logger.info("Created farmer id=%s wallet=%s", farmer_resp["farmer_id"], farmer_wallet)
        _assert(farmer_wallet, "farmer wallet missing in create-farmer response")

        # 5. Login as farmer
        farmer_token = _post(client, "/auth/login", {
            "identifier": farmer_payload["username"],
            "password": farmer_payload["password"],
        })["access_token"]

        # 6. Create batch (S0)
        create_resp = _post(client, "/batches/", {
            "apiary_data": {"region": "Baringo", "apiary_id": f"AP-{suffix}"},
            "metadata": {"honey_type": "wildflower", "expected_yield_kg": 50},
        }, headers=_auth(farmer_token))
        batch_id = create_resp["batch_id"]
        _assert(create_resp["new_state"] == "CREATED", f"expected CREATED, got {create_resp['new_state']}")
        rows.append(("CREATE", "farmer", create_resp["tx_hash"], 0))
        logger.info("S0 CREATED batch_id=%s tx=%s", batch_id, create_resp["tx_hash"])

        # 7. Harvest (S0 → S1)
        harvest_resp = _post(client, f"/batches/{batch_id}/harvest", {
            "harvest_date": datetime.now(timezone.utc).isoformat(),
            "quantity_kg": 25.5,
            "hive_ids": ["H1", "H2"],
            "gps_lat": 0.5,
            "gps_lon": 36.0,
            "notes": "first run",
        }, headers=_auth(farmer_token))
        _assert(harvest_resp["new_state"] == "HARVESTED", f"expected HARVESTED, got {harvest_resp['new_state']}")
        rows.append(("HARVEST", "farmer", harvest_resp["tx_hash"], 0))
        logger.info("S1 HARVESTED tx=%s", harvest_resp["tx_hash"])

        # 8. Process (S1 → S2)
        processor_token = _post(client, "/auth/login", {
            "identifier": employee_credentials["harvest_processor"]["identifier"],
            "password": employee_credentials["harvest_processor"]["password"],
        })["access_token"]
        process_resp = _post(client, f"/batches/{batch_id}/process", {
            "extraction_method": "centrifugal",
            "moisture_content": 18.2,
            "handling_notes": "hygienic",
        }, headers=_auth(processor_token))
        _assert(process_resp["new_state"] == "PROCESSED", f"expected PROCESSED, got {process_resp['new_state']}")
        rows.append(("PROCESS", "harvest_processor", process_resp["tx_hash"], 0))
        logger.info("S2 PROCESSED tx=%s", process_resp["tx_hash"])

        # 9. Lab verify (S2 → S3)
        lab_token = _post(client, "/auth/login", {
            "identifier": employee_credentials["lab_test_officer"]["identifier"],
            "password": employee_credentials["lab_test_officer"]["password"],
        })["access_token"]
        lab_resp = _post(client, f"/batches/{batch_id}/lab-verify", {
            "moisture_content": 18.2,
            "hmf_level": 12.0,
            "purity_score": 95.5,
            "passed_quality_check": True,
            "laboratory_name": "KEBS Lab #1",
            "analyst_name": "Sprint3 E2E",
            "certificate_number": "abcd1234",
        }, headers=_auth(lab_token))
        _assert(lab_resp["new_state"] == "LAB_VERIFIED", f"expected LAB_VERIFIED, got {lab_resp['new_state']}")
        rows.append(("LAB_VERIFY", "lab_test_officer (oracle)", lab_resp["tx_hash"], 0))
        logger.info("S3 LAB_VERIFIED tx=%s", lab_resp["tx_hash"])

        # 10. Package (S3 → S4)
        packager_token = _post(client, "/auth/login", {
            "identifier": employee_credentials["packager"]["identifier"],
            "password": employee_credentials["packager"]["password"],
        })["access_token"]
        package_resp = _post(client, f"/batches/{batch_id}/package", {
            "unit_count": 3,
            "jar_ids": ["J1", "J2", "J3"],
            "qr_codes": ["QR1", "QR2", "QR3"],
            "notes": "500g jars",
        }, headers=_auth(packager_token))
        _assert(package_resp["new_state"] == "PACKAGED", f"expected PACKAGED, got {package_resp['new_state']}")
        rows.append(("PACKAGE", "packager", package_resp["tx_hash"], 0))
        logger.info("S4 PACKAGED tx=%s", package_resp["tx_hash"])

        # 11. Distribute (S4 → S5)
        distributor_token = _post(client, "/auth/login", {
            "identifier": employee_credentials["distributor"]["identifier"],
            "password": employee_credentials["distributor"]["password"],
        })["access_token"]
        dist_resp = _post(client, f"/batches/{batch_id}/distribute", {
            "retailer_name": "Nakumatt CBD",
            "transport_reference": "TR-001",
            "handover_notes": "delivered intact",
        }, headers=_auth(distributor_token))
        _assert(dist_resp["new_state"] == "DISTRIBUTED", f"expected DISTRIBUTED, got {dist_resp['new_state']}")
        rows.append(("DISTRIBUTE", "distributor", dist_resp["tx_hash"], 0))
        logger.info("S5 DISTRIBUTED tx=%s", dist_resp["tx_hash"])

        # 12. Public verify (no auth)
        verify_resp = _get(client, f"/batches/{batch_id}/verify")
        # State may come back as the int enum (5) or the string name ("DISTRIBUTED")
        # depending on the response model — accept both.
        terminal = verify_resp["state"]
        _assert(
            terminal in (5, "DISTRIBUTED"),
            f"expected on-chain state DISTRIBUTED, got {terminal}",
        )
        hashes = verify_resp["hashes"]
        timeline = verify_resp["timeline"]
        for hk in ["apiary_hash", "harvest_hash", "process_hash", "lab_proof_hash", "packaging_hash", "distribution_hash"]:
            v = hashes[hk]
            _assert(v and v != "0x" + "00" * 32, f"hash {hk} is zero/missing: {v}")
        for tk in ["created_at", "harvested_at", "processed_at", "lab_verified_at", "packaged_at", "distributed_at"]:
            _assert(timeline[tk] > 0, f"timestamp {tk} is zero: {timeline[tk]}")

        # Sprint 4: /verify now joins persisted lab_results + the 6 anchoring
        # tx hashes and includes a three-way hash match. The scan UI gates
        # the green "Blockchain Verified" badge on `verification.lab.match`.
        lab_result = verify_resp.get("lab_result")
        _assert(lab_result is not None, "lab_result missing from /verify response")
        _assert(
            lab_result.get("lab_proof_hash") == hashes["lab_proof_hash"],
            f"lab_result.lab_proof_hash ({lab_result.get('lab_proof_hash')}) "
            f"!= on-chain lab_proof_hash ({hashes['lab_proof_hash']})",
        )

        verification = verify_resp.get("verification") or {}
        lab_v = verification.get("lab") or {}
        _assert(
            lab_v.get("match") is True,
            f"verification.lab.match is not True: {lab_v}",
        )
        _assert(
            lab_v.get("recomputed_hash") == lab_v.get("db_hash") == lab_v.get("chain_hash"),
            f"three-way hash mismatch in verification.lab: {lab_v}",
        )

        tx = verify_resp.get("tx_hashes") or {}
        for tk in ["create_tx", "harvest_tx", "process_tx", "lab_tx", "package_tx", "distribute_tx"]:
            _assert(tx.get(tk), f"tx_hashes.{tk} missing in /verify response: {tx}")

        # environmental_data is optional in this flow — /batches/ (used here)
        # doesn't trigger the env snapshot; /batches/simple does. Log it.
        if verify_resp.get("environmental_data"):
            logger.info("environmental_data present in /verify (snapshot was fetched)")
        else:
            logger.info("environmental_data absent in /verify (expected — /batches/ path doesn't fetch snapshot)")

        # Backfill block timestamps into rows for the summary table
        ts_keys = ["created_at", "harvested_at", "processed_at", "lab_verified_at", "packaged_at", "distributed_at"]
        rows = [(stage, role, tx, timeline[ts_keys[i]]) for i, (stage, role, tx, _) in enumerate(rows)]

    # Print summary
    logger.info("=" * 88)
    logger.info("E2E LIFECYCLE SUCCESS — batch %s", batch_id)
    logger.info("=" * 88)
    logger.info("%-12s | %-26s | %-66s | %s", "stage", "role", "tx_hash", "block_ts (UTC)")
    logger.info("-" * 88)
    for stage, role, tx, ts in rows:
        when = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else "?"
        logger.info("%-12s | %-26s | %-66s | %s", stage, role, tx, when)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--invite-code", default=DEFAULT_INVITE_CODE)
    args = parser.parse_args()
    t0 = time.time()
    code = run(args.base_url, args.invite_code)
    logger.info("Total elapsed: %.1fs", time.time() - t0)
    return code


if __name__ == "__main__":
    sys.exit(main())
