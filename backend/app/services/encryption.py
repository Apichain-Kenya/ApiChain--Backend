"""
Fernet symmetric encryption for private key storage.

The encryption key must be set in .env as WALLET_ENCRYPTION_KEY.
Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import os
from cryptography.fernet import Fernet


def _load_encryption_key() -> bytes:
    key = os.getenv("WALLET_ENCRYPTION_KEY", "")
    if not key:
        raise RuntimeError(
            "WALLET_ENCRYPTION_KEY not set in .env. "
            "Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )

    key_bytes = key.encode()
    try:
        Fernet(key_bytes)
    except Exception as exc:
        raise RuntimeError(
            "WALLET_ENCRYPTION_KEY is invalid. "
            "Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        ) from exc

    return key_bytes


_key = _load_encryption_key()


def _get_fernet() -> Fernet:
    return Fernet(_key)
def encrypt_private_key(private_key: str) -> str:
    """Encrypt a hex private key. Returns base64-encoded ciphertext."""
    return _get_fernet().encrypt(private_key.encode()).decode()


def decrypt_private_key(encrypted: str) -> str:
    """Decrypt an encrypted private key. Returns hex private key."""
    return _get_fernet().decrypt(encrypted.encode()).decode()
