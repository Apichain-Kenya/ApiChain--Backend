"""
Backfill Ethereum wallets for any user (farmer or employee) whose role
requires one but who has no row in `eth_wallets`.

Runs idempotently — re-running picks up any users newly created since
the last run. Safe to invoke before flipping the admin-key fallback off
in `routers/batch.py::_get_user_signing_key`.

Usage:
    python scripts/backfill_wallets.py [--dry-run]
"""

import argparse
import logging
import sys
from pathlib import Path

# Allow running as a plain script from inside backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal  # noqa: E402
from app.models.eth_wallet import EthWallet  # noqa: E402
from app.models.farmer import Farmer  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.roles import (  # noqa: E402
    ROLES_NEEDING_WALLET,
    grant_blockchain_role_to_user,
)
from app.services.wallet import create_user_wallet  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_wallets")


def _find_missing(db, user_id: int, user_role: str) -> bool:
    return (
        db.query(EthWallet)
        .filter(EthWallet.user_id == user_id, EthWallet.user_role == user_role)
        .first()
        is None
    )


def backfill_farmers(db, dry_run: bool) -> tuple[int, int]:
    """Returns (checked, fixed)."""
    farmers = db.query(Farmer).all()
    fixed = 0
    for farmer in farmers:
        if not _find_missing(db, farmer.id, "farmer"):
            continue
        logger.info("Missing wallet for farmer id=%s name=%s", farmer.id, farmer.first_name)
        if dry_run:
            fixed += 1
            continue
        address = create_user_wallet(db, farmer.id, "farmer")
        if not address:
            logger.error("create_user_wallet returned None for farmer %s", farmer.id)
            continue
        farmer.wallet_address = address
        db.commit()
        grant = grant_blockchain_role_to_user(db, farmer.id, "farmer")
        logger.info("Granted role: %s", grant)
        fixed += 1
    return len(farmers), fixed


def backfill_employees(db, dry_run: bool) -> tuple[int, int]:
    """Returns (checked, fixed)."""
    users = (
        db.query(User)
        .filter(User.role.in_(list(ROLES_NEEDING_WALLET)))
        .all()
    )
    fixed = 0
    for user in users:
        if not _find_missing(db, user.id, user.role):
            continue
        logger.info("Missing wallet for user id=%s role=%s", user.id, user.role)
        if dry_run:
            fixed += 1
            continue
        address = create_user_wallet(db, user.id, user.role)
        if not address:
            logger.error("create_user_wallet returned None for user %s", user.id)
            continue
        db.commit()
        grant = grant_blockchain_role_to_user(db, user.id, user.role)
        logger.info("Granted role: %s", grant)
        fixed += 1
    return len(users), fixed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report missing wallets without creating them.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        f_checked, f_fixed = backfill_farmers(db, args.dry_run)
        u_checked, u_fixed = backfill_employees(db, args.dry_run)
    finally:
        db.close()

    verb = "would fix" if args.dry_run else "fixed"
    logger.info("Farmers: checked=%d, %s=%d", f_checked, verb, f_fixed)
    logger.info("Employees (wallet roles): checked=%d, %s=%d", u_checked, verb, u_fixed)
    logger.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
