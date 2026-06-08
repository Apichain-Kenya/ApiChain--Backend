"""Reconcile on-chain actor roles with the `eth_wallets` table.

Companion to `reconcile_batches.py`. On a live network (Sepolia) a role-grant
tx broadcast at enrollment can be evicted from the mempool before it mines
(it happened intermittently under the old fixed-`gasPrice` pricing), leaving a
wallet the DB says is un-granted AND that holds no role on-chain — so every
state transition the user attempts reverts with "missing role". The inverse
also happens: a grant that DID mine but whose receipt arrived after the 90s
ceiling leaves the role live on-chain but `role_granted=False` in the DB.

This script reads the authoritative on-chain state via `RoleManager.checkRole`
for every wallet and repairs both cases:

  * on-chain HAS role, DB says not granted   -> sync the DB flag (no tx, free)
  * on-chain MISSING role                     -> (fund if needed) + re-grant, sync DB

Idempotent: a wallet already granted on-chain is left untouched. Never touches
admin/oracle/off-chain roles (no per-user actor role to reconcile).

Usage:
    python scripts/reconcile_roles.py                 # all wallets
    python scripts/reconcile_roles.py --user-id 3     # one user
    python scripts/reconcile_roles.py --dry-run       # report only, no writes
    python scripts/reconcile_roles.py --no-fund       # skip the balance top-up
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.eth_wallet import EthWallet  # noqa: E402
from app.services.blockchain import blockchain_service  # noqa: E402
from app.services.roles import (  # noqa: E402
    ROLE_BLOCKCHAIN_MAP,
    get_blockchain_role_bytes,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("reconcile_roles")

# Blockchain role names that map to no per-user on-chain actor role: nothing to
# reconcile (admins use the deployer key; on_ground_officer is off-chain only).
_NO_ACTOR_ROLE = {None, "DEFAULT_ADMIN"}


def _expected_role_name(wallet: EthWallet) -> Optional[str]:
    """The on-chain role this wallet should hold, preferring the stored
    `blockchain_role` and falling back to the user_role mapping."""
    return wallet.blockchain_role or ROLE_BLOCKCHAIN_MAP.get(wallet.user_role)


def reconcile_roles(
    db: Optional[Session] = None,
    user_id: Optional[int] = None,
    dry_run: bool = False,
    fund: bool = True,
) -> dict:
    """Repair every wallet whose on-chain role disagrees with the DB.

    Returns a summary dict: `{scanned, synced, regranted, ok, skipped, failed}`.
      synced    - role live on-chain, DB flag flipped to granted
      regranted - role missing on-chain, re-granted and DB updated
      ok        - already consistent (granted + on-chain), untouched
      skipped   - no per-user on-chain role (admin/off-chain)
      failed    - an error occurred for that wallet (logged, loop continues)
    """
    owns_session = db is None
    if owns_session:
        db = SessionLocal()

    summary = {"scanned": 0, "synced": 0, "regranted": 0, "ok": 0, "skipped": 0, "failed": 0}

    if not blockchain_service.is_connected or blockchain_service.role_manager is None:
        logger.error("Blockchain/RoleManager unavailable — cannot reconcile roles")
        summary["failed"] = -1
        if owns_session:
            db.close()
        return summary

    try:
        q = db.query(EthWallet)
        if user_id is not None:
            q = q.filter(EthWallet.user_id == user_id)
        wallets = q.order_by(EthWallet.user_id).all()
        summary["scanned"] = len(wallets)

        for w in wallets:
            role_name = _expected_role_name(w)
            if role_name in _NO_ACTOR_ROLE:
                summary["skipped"] += 1
                continue

            role_bytes = get_blockchain_role_bytes(role_name)
            if role_bytes is None:
                logger.warning(
                    "user %s (%s): unknown blockchain role %r — skipping",
                    w.user_id, w.user_role, role_name,
                )
                summary["skipped"] += 1
                continue

            try:
                has_role = blockchain_service.check_role(role_bytes, w.wallet_address)
            except Exception as e:
                logger.error("user %s: checkRole failed: %s", w.user_id, e)
                summary["failed"] += 1
                continue

            if has_role:
                if w.role_granted:
                    logger.info("user %s (%s): OK — %s already live on-chain",
                                w.user_id, w.user_role, role_name)
                    summary["ok"] += 1
                else:
                    logger.info("user %s (%s): SYNC — %s live on-chain but DB said not granted",
                                w.user_id, w.user_role, role_name)
                    if not dry_run:
                        w.role_granted = True
                        db.commit()
                    summary["synced"] += 1
                continue

            # Role missing on-chain — needs a (re-)grant.
            logger.info("user %s (%s): REGRANT — %s missing on-chain (%s)",
                        w.user_id, w.user_role, role_name, w.wallet_address)
            if dry_run:
                summary["regranted"] += 1
                continue
            try:
                if fund:
                    blockchain_service.fund_account(w.wallet_address)
                tx = blockchain_service.grant_role(role_bytes, w.wallet_address)
                w.role_granted = True
                w.role_tx_hash = tx
                db.commit()
                logger.info("user %s: granted %s on-chain (tx %s)", w.user_id, role_name, tx)
                summary["regranted"] += 1
            except Exception as e:
                db.rollback()
                logger.error("user %s: re-grant failed: %s", w.user_id, e)
                summary["failed"] += 1

        logger.info("reconcile_roles summary: %s", summary)
        return summary
    finally:
        if owns_session:
            db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--user-id", type=int, default=None, help="Reconcile only this user_id")
    parser.add_argument("--dry-run", action="store_true", help="Report only; make no on-chain or DB writes")
    parser.add_argument("--no-fund", action="store_true", help="Do not top up wallet balance before re-granting")
    args = parser.parse_args()

    summary = reconcile_roles(user_id=args.user_id, dry_run=args.dry_run, fund=not args.no_fund)
    # Non-zero exit if anything failed, so CI/automation can detect it.
    return 1 if summary.get("failed") else 0


if __name__ == "__main__":
    sys.exit(main())
