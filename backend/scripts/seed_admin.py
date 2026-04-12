"""
Seed the system with the initial admin wallet record.

The deployer key (ADMIN_PRIVATE_KEY in .env) already has DEFAULT_ADMIN_ROLE
on-chain from the contract deployment. This script creates the corresponding
EthWallet record in the database so the system recognizes the admin.

Usage:
    cd backend
    source .venv/Scripts/activate   # or .venv/bin/activate on Linux
    python -m scripts.seed_admin

Note: This script does NOT create a user account in the Farmer/Employee tables.
The backend teammate will handle the admin user model. This only ensures the
blockchain wallet record exists so that admin-initiated transactions work.
"""

import os
import sys

# Add parent directory to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.database import SessionLocal
from app.models.eth_wallet import EthWallet
from web3 import Web3


def seed_admin():
    admin_key = os.getenv("ADMIN_PRIVATE_KEY")
    if not admin_key:
        print("ERROR: ADMIN_PRIVATE_KEY not set in .env")
        sys.exit(1)

    # Derive the wallet address from the private key
    w3 = Web3()
    admin_address = w3.eth.account.from_key(admin_key).address

    db = SessionLocal()
    try:
        # Check if admin wallet already exists
        existing = db.query(EthWallet).filter(
            EthWallet.wallet_address == admin_address,
        ).first()

        if existing:
            print(f"Admin wallet already exists: {admin_address}")
            print(f"  user_id: {existing.user_id}, user_role: {existing.user_role}")
            print(f"  role_granted: {existing.role_granted}")
            return

        # Create the admin wallet record.
        # user_id=0 is a placeholder — update when the admin user model exists.
        wallet = EthWallet(
            user_id=0,
            user_role="admin",
            wallet_address=admin_address,
            encrypted_key="DEPLOYER_KEY_IN_ENV",  # Admin key lives in .env, not encrypted in DB
            blockchain_role="DEFAULT_ADMIN",
            role_granted=True,  # Already has role from deploy
            role_tx_hash=None,
        )
        db.add(wallet)
        db.commit()

        print(f"Admin wallet seeded successfully:")
        print(f"  Address: {admin_address}")
        print(f"  Role: DEFAULT_ADMIN (granted at deploy)")
        print(f"  user_id: 0 (placeholder — update when admin user model exists)")
        print()
        print("Next steps:")
        print("  1. Backend teammate creates admin user in Farmer/Employee table")
        print("  2. Update this EthWallet record's user_id to match")

    finally:
        db.close()


if __name__ == "__main__":
    seed_admin()
