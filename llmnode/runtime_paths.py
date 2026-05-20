from __future__ import annotations

import os
from pathlib import Path

from .config import PROJECT_ROOT


def resolve_gateway_db_path() -> Path:
    configured = os.getenv("VLLM_CLAUDE_DB_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    runtime_dir = Path(os.getenv("VLLM_CLAUDE_RUNTIME_DIR", str(PROJECT_ROOT / "runtime"))).expanduser().resolve()
    return runtime_dir / "data" / "gateway.db"
