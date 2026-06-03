from __future__ import annotations

import json
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .lab_models import PerfMatrixPoint
from .lab_models import PerfRunRequest


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class PerfRunStore:
    def __init__(self, root_dir: Path):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def create_run(self, request: PerfRunRequest, points: list[PerfMatrixPoint]) -> dict[str, Any]:
        run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-perf-{uuid4().hex[:8]}"
        run_dir = self.root_dir / run_id
        payload = {
            "run_id": run_id,
            "status": "queued",
            "request": request.to_dict(),
            "created_at": _now(),
            "started_at": None,
            "finished_at": None,
            "errors": [],
        }
        _write_json(run_dir / "run.json", payload)
        _write_json(run_dir / "matrix.json", {"points": [point.to_dict() for point in points]})
        for point in points:
            point_dir = run_dir / "points" / point.point_id
            _write_json(point_dir / "summary.json", point.to_dict())
            _write_json(point_dir / "errors.json", {"errors": []})
        return payload

    def get_run(self, run_id: str) -> dict[str, Any]:
        run_dir = self.root_dir / run_id
        run = _read_json(run_dir / "run.json")
        points = []
        for point_file in sorted((run_dir / "points").glob("*/summary.json")):
            points.append(_read_json(point_file))
        run["matrix"] = points
        return run

    def list_runs(self) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        for run_file in self.root_dir.glob("*/run.json"):
            runs.append(_read_json(run_file))
        return sorted(runs, key=lambda item: item.get("created_at") or "", reverse=True)

    def update_run(self, run_id: str, **updates: Any) -> dict[str, Any]:
        path = self.root_dir / run_id / "run.json"
        payload = _read_json(path)
        payload.update(updates)
        _write_json(path, payload)
        return payload

    def update_point(
        self,
        run_id: str,
        point_id: str,
        *,
        status: str,
        summary: dict[str, Any] | None = None,
        startup: dict[str, Any] | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        point_dir = self.root_dir / run_id / "points" / point_id
        current = _read_json(point_dir / "summary.json")
        current.update(summary or {})
        current["status"] = status
        _write_json(point_dir / "summary.json", current)
        if startup is not None:
            _write_json(point_dir / "startup.json", startup)
        if errors is not None:
            _write_json(point_dir / "errors.json", {"errors": errors})
        return current

    def read_samples(self, run_id: str, point_id: str | None = None) -> list[dict[str, Any]]:
        files = (
            [self.root_dir / run_id / "points" / point_id / "samples.jsonl"]
            if point_id
            else sorted((self.root_dir / run_id / "points").glob("*/samples.jsonl"))
        )
        rows: list[dict[str, Any]] = []
        for path in files:
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
        return rows
