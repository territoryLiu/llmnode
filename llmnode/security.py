from __future__ import annotations

import hashlib
import secrets


def hash_api_key(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def generate_api_key(prefix: str = "sk") -> str:
    return f"{prefix}-{secrets.token_hex(32)}"
