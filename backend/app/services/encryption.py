"""
Fernet symmetric encryption for private key storage.

The encryption key must be set in .env as WALLET_ENCRYPTION_KEY.
Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import os
from cryptography.fernet import Fernet

_key = os.getenv("WALLET_ENCRYPTION_KEY", "")


def _get_fernet() -> Fernet:
    if not _key:
        raise RuntimeError(
            "WALLET_ENCRYPTION_KEY not set in .env. "
            "Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(_key.encode())


def encrypt_private_key(private_key: str) -> str:
    """Encrypt a hex private key. Returns base64-encoded ciphertext."""
    return _get_fernet().encrypt(private_key.encode()).decode()


def decrypt_private_key(encrypted: str) -> str:
    """Decrypt an encrypted private key. Returns hex private key."""
    return _get_fernet().decrypt(encrypted.encode()).decode()
