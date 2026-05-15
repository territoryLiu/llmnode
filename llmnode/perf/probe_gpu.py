from __future__ import annotations

import shutil
import subprocess
from typing import Any


def classify_gpu_processes(rows: list[dict[str, Any]], backend_pids: set[int]) -> dict[str, Any]:
    backend_rows = [row for row in rows if row["pid"] in backend_pids]
    other_rows = [row for row in rows if row["pid"] not in backend_pids]
    return {
        "backend_processes": backend_rows,
        "backend_process_used_mb": sum(row["used_memory_mb"] for row in backend_rows),
        "other_processes_total_mb": sum(row["used_memory_mb"] for row in other_rows),
        "other_processes": other_rows,
    }


def read_gpu_process_rows(raw_text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in raw_text.splitlines():
        raw = line.strip()
        if not raw:
            continue
        parts = [part.strip() for part in raw.split(",", 2)]
        if len(parts) != 3:
            continue
        try:
            rows.append(
                {
                    "pid": int(parts[0]),
                    "process_name": parts[1],
                    "used_memory_mb": int(parts[2].removesuffix(" MiB").strip()),
                }
            )
        except ValueError:
            continue
    return rows


def query_gpu_process_rows() -> list[dict[str, Any]]:
    if shutil.which("nvidia-smi") is None:
        return []
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return read_gpu_process_rows(result.stdout)


def query_gpu_total_used_mb() -> int | None:
    if shutil.which("nvidia-smi") is None:
        return None
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=memory.used",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    total = 0
    saw_value = False
    for line in result.stdout.splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            total += int(raw)
            saw_value = True
        except ValueError:
            continue
    return total if saw_value else None
