"""
Centralized role mapping and blockchain role granting.

Single source of truth for the mapping between backend user roles
and on-chain blockchain roles (RoleManager contract).

Standardized role names (agreed 2026-04-12):
  farmer             -> BEEKEEPER_ROLE
  super_admin        -> DEFAULT_ADMIN_ROLE (deployer key)
  admin              -> DEFAULT_ADMIN_ROLE (deployer key)
  on_ground_officer  -> None (off-chain only, iteration 1)
  harvest_processor  -> PROCESSOR_ROLE
  lab_test_officer   -> ORACLE_ROLE (system oracle key)
  packager           -> PROCESSOR_ROLE
  distributor        -> DISTRIBUTOR_ROLE
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.eth_wallet import EthWallet
from app.services.blockchain import blockchain_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------
# Backend user_role string  ->  Blockchain role name string
# None means no on-chain role (off-chain only).
# ---------------------------------------------------------------
ROLE_BLOCKCHAIN_MAP: dict[str, Optional[str]] = {
    "farmer": "BEEKEEPER",
    "super_admin": "DEFAULT_ADMIN",
    "admin": "DEFAULT_ADMIN",
    "on_ground_officer": None,
    "harvest_processor": "PROCESSOR",
    "lab_test_officer": "ORACLE",
    "packager": "PROCESSOR",
    "distributor": "DISTRIBUTOR",
}

# All backend role strings recognized by the system.
ALL_ROLES = set(ROLE_BLOCKCHAIN_MAP.keys())

# Roles that require a personal Ethereum wallet for signing transactions.
# Admin/super_admin use the deployer key; lab_test_officer uses the oracle
# key; on_ground_officer has no on-chain role.
ROLES_NEEDING_WALLET = {
    "farmer", "harvest_processor", "packager", "distributor",
}


def get_blockchain_role_bytes(blockchain_role_name: str) -> Optional[bytes]:
    """
    Convert a blockchain role name string (e.g. "BEEKEEPER") to the
    keccak256 bytes32 value used by the smart contract.

    Returns None for DEFAULT_ADMIN (already has it) or unknown names.
    """
    mapping = {
        "BEEKEEPER": blockchain_service.BEEKEEPER_ROLE,
        "PROCESSOR": blockchain_service.PROCESSOR_ROLE,
        "ORACLE": blockchain_service.ORACLE_ROLE,
        "DISTRIBUTOR": blockchain_service.DISTRIBUTOR_ROLE,
    }
    return mapping.get(blockchain_role_name)


def grant_blockchain_role_to_user(
    db: Session,
    user_id: int,
    user_role: str,
) -> dict:
    """
    Look up the user's wallet, determine the correct blockchain role,
    grant it on-chain via the admin key, and update the EthWallet record.

    Can be called from any enrollment or admin endpoint.

    Returns:
        {"role_granted": bool, "role_tx_hash": str | None, "message": str}
    """
    blockchain_role_name = ROLE_BLOCKCHAIN_MAP.get(user_role)

    # No blockchain role for this user type (e.g. on_ground_officer)
    if blockchain_role_name is None:
        return {
            "role_granted": False,
            "role_tx_hash": None,
            "message": f"Role '{user_role}' has no on-chain blockchain role",
        }

    # Admin already has DEFAULT_ADMIN_ROLE from contract deployment
    if blockchain_role_name == "DEFAULT_ADMIN":
        return {
            "role_granted": True,
            "role_tx_hash": None,
            "message": "Admin role already granted at deploy time",
        }

    # Look up the user's wallet
    wallet = db.query(EthWallet).filter(
        EthWallet.user_id == user_id,
        EthWallet.user_role == user_role,
    ).first()

    if not wallet:
        return {
            "role_granted": False,
            "role_tx_hash": None,
            "message": f"No wallet found for user {user_id} with role '{user_role}'",
        }

    # Already granted
    if wallet.role_granted:
        return {
            "role_granted": True,
            "role_tx_hash": wallet.role_tx_hash,
            "message": "Blockchain role already granted",
        }

    # Check blockchain connectivity
    if not blockchain_service.is_connected or not blockchain_service.role_manager:
        logger.warning("Blockchain unavailable — cannot grant role")
        return {
            "role_granted": False,
            "role_tx_hash": None,
            "message": "Blockchain node unavailable",
        }

    # Grant role on-chain
    role_bytes = get_blockchain_role_bytes(blockchain_role_name)
    if role_bytes is None:
        return {
            "role_granted": False,
            "role_tx_hash": None,
            "message": f"Unknown blockchain role: {blockchain_role_name}",
        }

    try:
        role_tx_hash = blockchain_service.grant_role(role_bytes, wallet.wallet_address)
        wallet.role_granted = True
        wallet.role_tx_hash = role_tx_hash
        db.commit()
        logger.info(
            f"Granted {blockchain_role_name} role to {wallet.wallet_address} "
            f"(user {user_id}, role '{user_role}', tx: {role_tx_hash})"
        )
        return {
            "role_granted": True,
            "role_tx_hash": role_tx_hash,
            "message": f"{blockchain_role_name} role granted on-chain",
        }
    except Exception as e:
        logger.warning(f"Failed to grant blockchain role: {e}")
        return {
            "role_granted": False,
            "role_tx_hash": None,
            "message": f"Role grant failed: {e}",
        }
