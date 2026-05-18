"""
Wallet creation service for ApiChain Kenya.

Provides a single reusable function for generating Ethereum wallets,
encrypting private keys, and storing them in the eth_wallets table.

Previously this logic was duplicated inline in farmers.py
registration endpoints. Now it lives here so that any enrollment
path (admin enrollment, seeding) can call the same function.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.eth_wallet import EthWallet
from app.services.blockchain import blockchain_service
from app.services.encryption import encrypt_private_key
from app.services.roles import ROLE_BLOCKCHAIN_MAP, ROLES_NEEDING_WALLET

logger = logging.getLogger(__name__)


def create_user_wallet(
    db: Session,
    user_id: int,
    user_role: str,
) -> Optional[str]:
    """
    Generate an Ethereum wallet for a user, encrypt the private key,
    and store it in the eth_wallets table. Also funds the wallet with
    ETH for gas on dev/testnet.

    Args:
        db: SQLAlchemy session (caller manages commit).
        user_id: The database ID of the user (farmer or employee).
        user_role: Backend role string (e.g. "farmer", "harvest_processor").

    Returns:
        The wallet address (0x...) on success, or None on failure.

    Notes:
        - The caller is responsible for storing wallet_address on the
          user model (e.g. Farmer.wallet_address) and committing.
        - The EthWallet record is added to the session but NOT committed
          here — the caller should commit after any additional work.
        - For roles not needing a personal wallet (admin, super_admin,
          lab_test_officer, on_ground_officer), returns None without error.
    """
    # Check if this role needs a personal wallet
    if user_role not in ROLES_NEEDING_WALLET:
        logger.info(
            f"Role '{user_role}' does not need a personal wallet — skipping"
        )
        return None

    # Determine the blockchain role name for this user role
    blockchain_role_name = ROLE_BLOCKCHAIN_MAP.get(user_role)

    try:
        from eth_account import Account

        acct = Account.create()
        wallet_address = acct.address
        private_key_hex = acct.key.hex()
    except Exception as e:
        logger.error(f"Wallet generation failed for user {user_id}: {e}")
        return None

    try:
        wallet = EthWallet(
            user_id=user_id,
            user_role=user_role,
            wallet_address=wallet_address,
            encrypted_key=encrypt_private_key(private_key_hex),
            blockchain_role=blockchain_role_name or "",
        )
        db.add(wallet)

        # Fund the new wallet with ETH for gas (dev/testnet only)
        if blockchain_service.is_connected and blockchain_service.admin_key:
            funding_result = blockchain_service.fund_account(wallet_address)
            if funding_result:
                logger.info(
                    f"Funded wallet {wallet_address} for user {user_id}: "
                    f"{funding_result}"
                )
            else:
                logger.warning(
                    f"Funding failed or returned no result for wallet "
                    f"{wallet_address} (user {user_id})"
                )
        else:
            logger.info(
                f"Skipping wallet funding for user {user_id} "
                f"(wallet {wallet_address}): blockchain unavailable "
                f"or admin key not configured"
            )

    except Exception as e:
        logger.error(
            f"EthWallet creation failed for user {user_id} "
            f"(role '{user_role}'): {e}"
        )
        return None

    logger.info(
        f"Wallet created for user {user_id} (role '{user_role}'): "
        f"{wallet_address}"
    )
    return wallet_address
