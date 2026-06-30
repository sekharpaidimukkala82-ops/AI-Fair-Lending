"""
Simple reversible encryption for API keys stored in the database.
Uses Fernet symmetric encryption derived from SECRET_KEY.
Falls back to base64 obfuscation if cryptography package not available.
"""
from __future__ import annotations

import base64
import hashlib
import os


def _get_fernet():
    try:
        from cryptography.fernet import Fernet
        secret = os.getenv("SECRET_KEY", "fairlend-platform-secret-key-2024-change-in-production")
        # Derive a 32-byte key from the secret
        key_bytes = hashlib.sha256(secret.encode()).digest()
        fernet_key = base64.urlsafe_b64encode(key_bytes)
        return Fernet(fernet_key)
    except ImportError:
        return None


def encrypt_key(api_key: str) -> str:
    """Encrypt an API key for database storage."""
    fernet = _get_fernet()
    if fernet:
        return fernet.encrypt(api_key.encode()).decode()
    # Fallback: base64 obfuscation (not true encryption, but hides key from casual inspection)
    return base64.b64encode(api_key.encode()).decode()


def decrypt_key(encrypted: str) -> str:
    """Decrypt a stored API key."""
    fernet = _get_fernet()
    if fernet:
        try:
            return fernet.decrypt(encrypted.encode()).decode()
        except Exception:
            # Maybe stored as base64 fallback — try that
            pass
    try:
        return base64.b64decode(encrypted.encode()).decode()
    except Exception:
        return encrypted  # return as-is if all decryption fails
