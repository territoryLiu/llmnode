from __future__ import annotations

import threading
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import Protocol

from .lab_models import PerfMatrixPoint
from .lab_models import PerfRunRequest
from .lab_models import expand_matrix
from .lab_store import PerfRunStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PerfPointExecutor(Protocol):
    def execute_point(
        self,
        *,
        run_id: str,
        point: PerfMatrixPoint,
        request: PerfRunRequest,
        store: PerfRunStore,
        cancel_requested,
    ) -> None:
        raise NotImplementedError


class NoopPerfPointExecutor:
    def execute_point(
        self,
        *,
        run_id: str,
        point: PerfMatrixPoint,
        request: PerfRunRequest,
        store: PerfRunStore,
        cancel_requested,
    ) -> None:
        store.update_point(
            run_id,
            point.point_id,
            status="benchmark_failed",
            errors=[{"message": "perf point executor is not configured"}],
        )


class PerfLabRunner:
    def __init__(self, *, store: PerfRunStore, executor: PerfPointExecutor):
        self.store = store
        self.executor = executor
        self._lock = threading.Lock()
        self._active_run_id: str | None = None
        self._cancel_requested: set[str] = set()

    def create_run(self, request: PerfRunRequest) -> dict[str, Any]:
        with self._lock:
            if self._active_run_id is not None:
                return {"status_code": 409, "detail": "perf_run_already_active"}
            points = expand_matrix(request)
            run = self.store.create_run(request, points)
            self._active_run_id = run["run_id"]
        thread = threading.Thread(target=self._run, args=(run["run_id"], request, points), daemon=True)
        thread.start()
        return run

    def _run(self, run_id: str, request: PerfRunRequest, points: list[PerfMatrixPoint]) -> None:
        status = "completed"
        errors: list[dict[str, Any]] = []
        self.store.update_run(run_id, status="running", started_at=_now())
        try:
            for point in points:
                if run_id in self._cancel_requested:
                    status = "cancelled"
                    self.store.update_point(run_id, point.point_id, status="cancelled")
                    break
                self.executor.execute_point(
                    run_id=run_id,
                    point=point,
                    request=request,
                    store=self.store,
                    cancel_requested=lambda: run_id in self._cancel_requested,
                )
            run_payload = self.store.get_run(run_id)
            if status != "cancelled":
                point_statuses = [item["status"] for item in run_payload["matrix"]]
                status = "completed" if all(item == "completed" for item in point_statuses) else "completed_with_errors"
        except Exception as exc:
            status = "failed"
            errors.append({"message": str(exc)})
        finally:
            self.store.update_run(run_id, status=status, finished_at=_now(), errors=errors)
            with self._lock:
                if self._active_run_id == run_id:
                    self._active_run_id = None
            self._cancel_requested.discard(run_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self.store.get_run(run_id)

    def list_runs(self) -> list[dict[str, Any]]:
        return self.store.list_runs()

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        self._cancel_requested.add(run_id)
        return self.store.update_run(run_id, status="cancel_requested")
