from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path


def hash_api_key(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def generate_api_key(prefix: str = "sk") -> str:
    return f"{prefix}-{secrets.token_hex(32)}"


def write_secret_file(path: Path, secret: str) -> None:
    """Atomically persist a local secret with owner-only permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(secret.strip() + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise
        os.chmod(temp, 0o600)
        os.replace(temp, path)
        os.chmod(path, 0o600)
        if hash_api_key(path.read_text(encoding="utf-8").strip()) != hash_api_key(secret.strip()):
            raise RuntimeError(f"secret file verification failed: {path}")
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def read_secret_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    os.chmod(path, 0o600)
    value = path.read_text(encoding="utf-8").strip()
    return value or None
