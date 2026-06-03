from __future__ import annotations

import os
import subprocess
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any
from collections.abc import Iterator
from typing import Protocol

import httpx

from ..config import load_settings
from ..diagnostics import get_container_logs
from .benchmark import run_benchmark
from .lab_models import PerfMatrixPoint
from .lab_models import PerfRunRequest
from .lab_models import expand_matrix
from .lab_store import PerfRunStore
from .probe_backend import parse_vllm_startup_metrics


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


@contextmanager
def _patched_env(env: dict[str, str]) -> Iterator[None]:
    keys = [
        "VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE",
        "VLLM_CLAUDE_VLLM_GPU_MEMORY_UTILIZATION",
        "VLLM_CLAUDE_VLLM_MAX_MODEL_LEN",
        "VLLM_CLAUDE_VLLM_MAX_NUM_SEQS",
    ]
    previous = {key: os.environ.get(key) for key in keys}
    try:
        for key in keys:
            if key in env:
                os.environ[key] = env[key]
            else:
                os.environ.pop(key, None)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class ControlFacade:
    def __init__(self, *, python_bin: str = "/home/heshan/.conda/envs/paper2any/bin/python"):
        self.python_bin = python_bin
        self._last_env: dict[str, str] | None = None

    def _env(self, profile: str, overrides: dict[str, object] | None = None) -> dict[str, str]:
        env = os.environ.copy()
        env["VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE"] = profile
        for key, value in (overrides or {}).items():
            if key == "gpu_memory_utilization":
                env["VLLM_CLAUDE_VLLM_GPU_MEMORY_UTILIZATION"] = str(value)
            elif key == "max_model_len":
                env["VLLM_CLAUDE_VLLM_MAX_MODEL_LEN"] = str(value)
            elif key == "max_num_seqs":
                env["VLLM_CLAUDE_VLLM_MAX_NUM_SEQS"] = str(value)
            else:
                raise ValueError(f"unsupported override key: {key}")
        return env

    def _run_control(self, profile: str, args: list[str], overrides: dict[str, object] | None = None) -> None:
        env = self._env(profile, overrides)
        subprocess.run(
            [self.python_bin, "-m", "llmnode.control", *args],
            check=True,
            env=env,
        )
        self._last_env = env

    def stop(self, profile: str) -> None:
        self._run_control(profile, ["stop"])

    def start(self, profile: str, overrides: dict[str, object]) -> None:
        self._run_control(profile, ["start", "--service", "vllm", "--daemon"], overrides)

    def wait_healthy(self, profile: str) -> bool:
        env = self._last_env or self._env(profile)
        with _patched_env(env):
            settings = load_settings()
        deadline = time.monotonic() + settings.agent.startup_grace_period
        while time.monotonic() < deadline:
            try:
                response = httpx.get(f"{settings.gateway.backend_url.rstrip('/')}/v1/models", timeout=5)
                if response.status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            time.sleep(5)
        return False

    def startup_metrics(self, profile: str) -> dict[str, object]:
        env = self._last_env or self._env(profile)
        with _patched_env(env):
            settings = load_settings()
        logs = "\n".join(get_container_logs(settings.vllm.container_name, 800))
        return parse_vllm_startup_metrics(logs)


class LocalPerfPointExecutor:
    def __init__(self, *, control: ControlFacade | None = None, benchmark=run_benchmark):
        self.control = control or ControlFacade()
        self.benchmark = benchmark

    def execute_point(self, *, run_id, point, request, store, cancel_requested) -> None:
        store.update_point(run_id, point.point_id, status="starting")
        if request.restart_backend:
            self.control.stop(point.profile)
        self.control.start(point.profile, point.overrides)
        if not self.control.wait_healthy(point.profile):
            startup = self.control.startup_metrics(point.profile)
            store.update_point(
                run_id,
                point.point_id,
                status="startup_failed",
                startup=startup,
                errors=[{"message": "backend healthcheck failed"}],
            )
            return
        startup = self.control.startup_metrics(point.profile)
        store.update_point(run_id, point.point_id, status="healthy", startup=startup)
        if cancel_requested():
            store.update_point(run_id, point.point_id, status="cancelled")
            return
        store.update_point(run_id, point.point_id, status="benchmarking")
        point_dir = Path(store.root_dir) / run_id / "points" / point.point_id
        try:
            self.benchmark(
                profile=point.profile,
                targets=request.targets,
                max_tokens=request.max_tokens,
                warmup_runs=request.warmup_runs,
                measure_runs=request.measure_runs,
                sample_interval=request.sample_interval,
                output_dir=str(point_dir),
                concurrency=request.concurrency,
            )
        except Exception as exc:
            store.update_point(run_id, point.point_id, status="benchmark_failed", errors=[{"message": str(exc)}])
            return
        store.update_point(run_id, point.point_id, status="completed", summary={"result": "success"})


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
