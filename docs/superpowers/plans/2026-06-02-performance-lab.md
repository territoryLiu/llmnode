# Performance Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the performance lab automation loop for local model benchmark matrices, with admin APIs, file-backed run state, structured startup diagnostics, and a web-console page.

**Architecture:** Add a focused `llmnode.perf.lab_*` layer around the existing benchmark module. The API creates file-backed background jobs; the runner executes one matrix point at a time, uses the official control path for backend lifecycle, delegates request measurement to `llmnode.perf.benchmark`, and exposes summaries/samples to the web-console.

**Tech Stack:** Python dataclasses, FastAPI admin endpoints, existing `llmnode.control` semantics, JSON/JSONL files under `runtime/benchmarks`, pytest/httpx ASGI tests, React + TypeScript + Vitest in `web-console`.

---

## File Structure

- Create `llmnode/perf/lab_models.py`
  - Request validation dataclasses, matrix expansion, status enums, point IDs.
- Create `llmnode/perf/lab_store.py`
  - File-backed run/point storage under `runtime/benchmarks/<run_id>`.
- Create `llmnode/perf/lab_runner.py`
  - Single-process task manager, background execution, cancellation, dependency injection for tests.
- Create `llmnode/api/perf_lab.py`
  - Admin API route registration helpers used by `llmnode/api/app.py`.
- Modify `llmnode/api/app.py`
  - Register performance lab endpoints and attach the task manager to `app.state`.
- Modify `llmnode/perf/benchmark.py`
  - Add optional concurrency support after single-run API is stable.
- Modify `llmnode/perf/probe_backend.py`
  - Extend vLLM startup failure parsing.
- Create tests:
  - `tests/test_perf_lab_models.py`
  - `tests/test_perf_lab_store.py`
  - `tests/test_perf_lab_runner.py`
  - `tests/test_admin_perf_lab.py`
- Modify frontend:
  - `web-console/src/store.tsx`
  - `web-console/src/App.tsx`
  - `web-console/src/components/Layout.tsx`
  - `web-console/src/i18n.ts`
  - Create `web-console/src/pages/PerformanceLabView.tsx`
  - Extend `web-console/src/pages/ConsoleViews.test.tsx`
- Docs:
  - `docs/blueprint/current.md`
  - `docs/process/run.md`
  - `docs/knowledge/model_context_performance.md`

---

### Task 1: Performance Lab Models And Matrix Expansion

**Files:**
- Create: `llmnode/perf/lab_models.py`
- Test: `tests/test_perf_lab_models.py`

- [ ] **Step 1: Write failing tests for request normalization and matrix expansion**

Create `tests/test_perf_lab_models.py`:

```python
from llmnode.perf.lab_models import PerfRunRequest, expand_matrix


def test_expand_matrix_defaults_to_single_current_profile_point():
    request = PerfRunRequest(profile="vllm_qwen36-27b-nvfp4", targets=[4096])

    points = expand_matrix(request)

    assert len(points) == 1
    assert points[0].point_id == "point-001"
    assert points[0].profile == "vllm_qwen36-27b-nvfp4"
    assert points[0].overrides == {}


def test_expand_matrix_creates_cartesian_product_in_stable_order():
    request = PerfRunRequest(
        profile="vllm_qwen36-27b-nvfp4",
        targets=[4096, 262000],
        matrix={
            "gpu_memory_utilization": [0.55, 0.6],
            "max_model_len": [262144],
            "max_num_seqs": [1, 4],
        },
    )

    points = expand_matrix(request)

    assert [point.point_id for point in points] == ["point-001", "point-002", "point-003", "point-004"]
    assert points[0].overrides == {
        "gpu_memory_utilization": 0.55,
        "max_model_len": 262144,
        "max_num_seqs": 1,
    }
    assert points[-1].overrides == {
        "gpu_memory_utilization": 0.6,
        "max_model_len": 262144,
        "max_num_seqs": 4,
    }


def test_request_rejects_empty_targets():
    try:
        PerfRunRequest(profile="vllm_qwen36-27b-nvfp4", targets=[])
    except ValueError as exc:
        assert "targets must not be empty" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_request_rejects_unknown_matrix_key():
    try:
        PerfRunRequest(
            profile="vllm_qwen36-27b-nvfp4",
            targets=[4096],
            matrix={"tensor_parallel_size": [2]},
        )
    except ValueError as exc:
        assert "unsupported matrix key" in str(exc)
    else:
        raise AssertionError("expected ValueError")
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_perf_lab_models.py -q
```

Expected: fail because `llmnode.perf.lab_models` does not exist.

- [ ] **Step 3: Implement models and matrix expansion**

Create `llmnode/perf/lab_models.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from itertools import product
from typing import Any, Literal


PerfRunStatus = Literal[
    "queued",
    "running",
    "completed",
    "completed_with_errors",
    "failed",
    "cancel_requested",
    "cancelled",
]

PerfPointStatus = Literal[
    "pending",
    "starting",
    "startup_failed",
    "healthy",
    "benchmarking",
    "benchmark_failed",
    "completed",
    "cancelled",
]

SUPPORTED_MATRIX_KEYS = ("gpu_memory_utilization", "max_model_len", "max_num_seqs")


@dataclass
class PerfRunRequest:
    profile: str
    targets: list[int]
    max_tokens: int = 64
    warmup_runs: int = 1
    measure_runs: int = 3
    sample_interval: float = 1.0
    concurrency: int = 1
    restart_backend: bool = True
    matrix: dict[str, list[Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.profile.strip():
            raise ValueError("profile must not be empty")
        if not self.targets:
            raise ValueError("targets must not be empty")
        if any(int(target) <= 0 for target in self.targets):
            raise ValueError("targets must be positive")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if self.warmup_runs < 0:
            raise ValueError("warmup_runs must be non-negative")
        if self.measure_runs <= 0:
            raise ValueError("measure_runs must be positive")
        if self.sample_interval <= 0:
            raise ValueError("sample_interval must be positive")
        if self.concurrency <= 0:
            raise ValueError("concurrency must be positive")
        for key, values in self.matrix.items():
            if key not in SUPPORTED_MATRIX_KEYS:
                raise ValueError(f"unsupported matrix key: {key}")
            if not values:
                raise ValueError(f"matrix key {key} must contain at least one value")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PerfMatrixPoint:
    point_id: str
    profile: str
    overrides: dict[str, Any]
    status: PerfPointStatus = "pending"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def expand_matrix(request: PerfRunRequest) -> list[PerfMatrixPoint]:
    if not request.matrix:
        return [PerfMatrixPoint(point_id="point-001", profile=request.profile, overrides={})]

    keys = [key for key in SUPPORTED_MATRIX_KEYS if key in request.matrix]
    points: list[PerfMatrixPoint] = []
    for index, values in enumerate(product(*(request.matrix[key] for key in keys)), start=1):
        overrides = {key: value for key, value in zip(keys, values)}
        points.append(
            PerfMatrixPoint(
                point_id=f"point-{index:03d}",
                profile=request.profile,
                overrides=overrides,
            )
        )
    return points
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_perf_lab_models.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add llmnode/perf/lab_models.py tests/test_perf_lab_models.py
git commit -m "新增性能实验室矩阵模型"
```

---

### Task 2: File-Backed Run Store

**Files:**
- Create: `llmnode/perf/lab_store.py`
- Test: `tests/test_perf_lab_store.py`

- [ ] **Step 1: Write failing tests for run and point persistence**

Create `tests/test_perf_lab_store.py`:

```python
import json

from llmnode.perf.lab_models import PerfRunRequest, expand_matrix
from llmnode.perf.lab_store import PerfRunStore


def test_store_creates_run_files(tmp_path):
    store = PerfRunStore(tmp_path)
    request = PerfRunRequest(profile="vllm_qwen36-27b-nvfp4", targets=[4096])
    points = expand_matrix(request)

    run = store.create_run(request, points)

    run_dir = tmp_path / run["run_id"]
    assert (run_dir / "run.json").exists()
    assert (run_dir / "matrix.json").exists()
    assert json.loads((run_dir / "run.json").read_text())["status"] == "queued"


def test_store_updates_point_status_and_errors(tmp_path):
    store = PerfRunStore(tmp_path)
    request = PerfRunRequest(profile="vllm_qwen36-27b-nvfp4", targets=[4096])
    run = store.create_run(request, expand_matrix(request))

    store.update_point(run["run_id"], "point-001", status="startup_failed", errors=[{"message": "KV cache too small"}])

    point_dir = tmp_path / run["run_id"] / "points" / "point-001"
    assert json.loads((point_dir / "summary.json").read_text())["status"] == "startup_failed"
    assert json.loads((point_dir / "errors.json").read_text())["errors"][0]["message"] == "KV cache too small"


def test_store_lists_runs_newest_first(tmp_path):
    store = PerfRunStore(tmp_path)
    first = store.create_run(PerfRunRequest(profile="a", targets=[1]), expand_matrix(PerfRunRequest(profile="a", targets=[1])))
    second = store.create_run(PerfRunRequest(profile="b", targets=[1]), expand_matrix(PerfRunRequest(profile="b", targets=[1])))

    runs = store.list_runs()

    assert [run["run_id"] for run in runs] == [second["run_id"], first["run_id"]]
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_perf_lab_store.py -q
```

Expected: fail because `llmnode.perf.lab_store` does not exist.

- [ ] **Step 3: Implement store**

Create `llmnode/perf/lab_store.py` with atomic-enough JSON writes for this single-process use case:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .lab_models import PerfMatrixPoint, PerfRunRequest


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
        matrix = _read_json(run_dir / "matrix.json")
        run["matrix"] = matrix["points"]
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
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_perf_lab_store.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add llmnode/perf/lab_store.py tests/test_perf_lab_store.py
git commit -m "新增性能实验室文件存储"
```

---

### Task 3: Background Runner Skeleton

**Files:**
- Create: `llmnode/perf/lab_runner.py`
- Test: `tests/test_perf_lab_runner.py`

- [ ] **Step 1: Write failing tests for single active run and cancellation**

Create `tests/test_perf_lab_runner.py`:

```python
import time

from llmnode.perf.lab_models import PerfRunRequest
from llmnode.perf.lab_runner import PerfLabRunner
from llmnode.perf.lab_store import PerfRunStore


class FakeExecutor:
    def __init__(self):
        self.executed = []

    def execute_point(self, *, run_id, point, request, store, cancel_requested):
        self.executed.append(point.point_id)
        store.update_point(run_id, point.point_id, status="completed", summary={"result": "success"})


def wait_until_done(runner, run_id):
    for _ in range(50):
        payload = runner.get_run(run_id)
        if payload["status"] in {"completed", "completed_with_errors", "failed", "cancelled"}:
            return payload
        time.sleep(0.02)
    raise AssertionError("run did not finish")


def test_runner_rejects_second_active_run(tmp_path):
    store = PerfRunStore(tmp_path)
    runner = PerfLabRunner(store=store, executor=FakeExecutor())
    request = PerfRunRequest(profile="vllm_qwen36-27b-nvfp4", targets=[4096])

    first = runner.create_run(request)
    second = runner.create_run(request)

    assert first["status"] == "queued"
    assert second["status_code"] == 409


def test_runner_completes_run(tmp_path):
    store = PerfRunStore(tmp_path)
    executor = FakeExecutor()
    runner = PerfLabRunner(store=store, executor=executor)

    run = runner.create_run(PerfRunRequest(profile="vllm_qwen36-27b-nvfp4", targets=[4096]))
    final = wait_until_done(runner, run["run_id"])

    assert final["status"] == "completed"
    assert executor.executed == ["point-001"]


def test_runner_accepts_cancel_request(tmp_path):
    store = PerfRunStore(tmp_path)
    runner = PerfLabRunner(store=store, executor=FakeExecutor())
    run = runner.create_run(PerfRunRequest(profile="vllm_qwen36-27b-nvfp4", targets=[4096]))

    response = runner.cancel_run(run["run_id"])

    assert response["status"] in {"cancel_requested", "completed", "cancelled"}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_perf_lab_runner.py -q
```

Expected: fail because runner does not exist.

- [ ] **Step 3: Implement runner skeleton**

Create `llmnode/perf/lab_runner.py`:

```python
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Protocol

from .lab_models import PerfMatrixPoint, PerfRunRequest, expand_matrix
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
                point_summary = self.store.get_run(run_id)["matrix"]
                _ = point_summary
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
        run = self.store.update_run(run_id, status="cancel_requested")
        return run
```

- [ ] **Step 4: Run tests and fix matrix status refresh**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_perf_lab_runner.py -q
```

If the status aggregation does not see point updates, update `PerfRunStore.get_run()` to load point summaries from `points/*/summary.json` instead of only `matrix.json`:

```python
    def get_run(self, run_id: str) -> dict[str, Any]:
        run_dir = self.root_dir / run_id
        run = _read_json(run_dir / "run.json")
        points = []
        for point_file in sorted((run_dir / "points").glob("*/summary.json")):
            points.append(_read_json(point_file))
        run["matrix"] = points
        return run
```

Expected after fix: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add llmnode/perf/lab_runner.py llmnode/perf/lab_store.py tests/test_perf_lab_runner.py
git commit -m "新增性能实验室后台任务骨架"
```

---

### Task 4: Admin API Endpoints

**Files:**
- Create: `llmnode/api/perf_lab.py`
- Modify: `llmnode/api/app.py`
- Test: `tests/test_admin_perf_lab.py`

- [ ] **Step 1: Write API tests**

Create `tests/test_admin_perf_lab.py`:

```python
import asyncio
import time

import httpx

from llmnode.api.app import create_app
from llmnode.perf.lab_runner import PerfLabRunner
from llmnode.perf.lab_store import PerfRunStore
from llmnode.security import hash_api_key
from llmnode.storage.db import create_api_key


class ApiFakeExecutor:
    def execute_point(self, *, run_id, point, request, store, cancel_requested):
        store.update_point(run_id, point.point_id, status="completed", summary={"result": "success"})


def seed_admin_key(app, secret: str = "sk-admin-test") -> str:
    create_api_key(app.state.db, name="admin-perf", key_hash=hash_api_key(secret), scopes=["admin"])
    return secret


async def wait_done(client, run_id, headers):
    for _ in range(50):
        response = await client.get(f"/admin/perf/runs/{run_id}", headers=headers)
        payload = response.json()
        if payload["run"]["status"] in {"completed", "completed_with_errors", "failed", "cancelled"}:
            return payload
        await asyncio.sleep(0.02)
    raise AssertionError("run did not finish")


def test_admin_perf_run_lifecycle(tmp_path):
    async def run():
        app = create_app()
        app.state.perf_lab_runner = PerfLabRunner(
            store=PerfRunStore(tmp_path),
            executor=ApiFakeExecutor(),
        )
        admin_secret = seed_admin_key(app)
        headers = {"Authorization": f"Bearer {admin_secret}"}
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            create = await client.post(
                "/admin/perf/runs",
                headers=headers,
                json={"profile": "vllm_qwen36-27b-nvfp4", "targets": [4096]},
            )
            assert create.status_code == 200
            run_id = create.json()["run"]["run_id"]
            final = await wait_done(client, run_id, headers)
            assert final["run"]["status"] == "completed"

            listing = await client.get("/admin/perf/runs", headers=headers)
            assert listing.status_code == 200
            assert listing.json()["runs"][0]["run_id"] == run_id

            samples = await client.get(f"/admin/perf/runs/{run_id}/samples", headers=headers)
            assert samples.status_code == 200
            assert "samples" in samples.json()

    asyncio.run(run())


def test_admin_perf_rejects_invalid_payload(tmp_path):
    async def run():
        app = create_app()
        app.state.perf_lab_runner = PerfLabRunner(store=PerfRunStore(tmp_path), executor=ApiFakeExecutor())
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/admin/perf/runs",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={"profile": "", "targets": []},
            )
            assert response.status_code == 400

    asyncio.run(run())
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_admin_perf_lab.py -q
```

Expected: fail because API routes are not registered.

- [ ] **Step 3: Add route registration helper**

Create `llmnode/api/perf_lab.py`:

```python
from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from ..perf.lab_models import PerfRunRequest


def register_perf_lab_routes(app, require_admin):
    @app.post("/admin/perf/runs")
    async def create_perf_run(request: Request):
        require_admin(request)
        try:
            payload = await request.json()
            run_request = PerfRunRequest(**payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = request.app.state.perf_lab_runner.create_run(run_request)
        if result.get("status_code") == 409:
            raise HTTPException(status_code=409, detail=result["detail"])
        return JSONResponse({"run": result})

    @app.get("/admin/perf/runs")
    async def list_perf_runs(request: Request):
        require_admin(request)
        return JSONResponse({"runs": request.app.state.perf_lab_runner.list_runs()})

    @app.get("/admin/perf/runs/{run_id}")
    async def get_perf_run(request: Request, run_id: str):
        require_admin(request)
        try:
            run = request.app.state.perf_lab_runner.get_run(run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="perf_run_not_found") from exc
        return JSONResponse({"run": run})

    @app.get("/admin/perf/runs/{run_id}/samples")
    async def get_perf_samples(request: Request, run_id: str, point_id: str | None = None):
        require_admin(request)
        samples = request.app.state.perf_lab_runner.store.read_samples(run_id, point_id=point_id)
        return JSONResponse({"samples": samples})

    @app.post("/admin/perf/runs/{run_id}/cancel")
    async def cancel_perf_run(request: Request, run_id: str):
        require_admin(request)
        run = request.app.state.perf_lab_runner.cancel_run(run_id)
        return JSONResponse({"run": run})
```

- [ ] **Step 4: Wire into app factory**

Modify `llmnode/api/app.py`:

```python
from .perf_lab import register_perf_lab_routes
from ..config import BENCHMARK_DIR
from ..perf.lab_runner import PerfLabRunner
from ..perf.lab_store import PerfRunStore
```

After app state initialization, attach:

```python
    if not hasattr(app.state, "perf_lab_runner"):
        from ..perf.lab_runner import NoopPerfPointExecutor
        app.state.perf_lab_runner = PerfLabRunner(
            store=PerfRunStore(BENCHMARK_DIR),
            executor=NoopPerfPointExecutor(),
        )
```

Before `return app`, register:

```python
    register_perf_lab_routes(app, require_admin)
```

Also add `NoopPerfPointExecutor` in `llmnode/perf/lab_runner.py` for API boot safety:

```python
class NoopPerfPointExecutor:
    def execute_point(self, *, run_id, point, request, store, cancel_requested) -> None:
        store.update_point(
            run_id,
            point.point_id,
            status="benchmark_failed",
            errors=[{"message": "perf point executor is not configured"}],
        )
```

- [ ] **Step 5: Run API tests**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_admin_perf_lab.py -q
```

Expected: `2 passed`.

- [ ] **Step 6: Commit**

```bash
git add llmnode/api/perf_lab.py llmnode/api/app.py llmnode/perf/lab_runner.py tests/test_admin_perf_lab.py
git commit -m "新增性能实验室管理接口"
```

---

### Task 5: Real Point Executor And Startup Parsing

**Files:**
- Modify: `llmnode/perf/lab_runner.py`
- Modify: `llmnode/perf/probe_backend.py`
- Test: `tests/test_perf_lab_runner.py`
- Test: `tests/test_probe_backend.py`

- [ ] **Step 1: Add startup parsing tests**

Add to `tests/test_probe_backend.py`:

```python
from llmnode.perf.probe_backend import parse_vllm_startup_metrics


def test_parse_vllm_kv_shortage_error():
    logs = """
    Model loading took 24.05 GiB memory
    Available KV cache memory: 13.42 GiB
    ValueError: The model's max seq len (262144) is larger than the maximum number of tokens that can be stored in KV cache (217168).
    Try increasing `gpu_memory_utilization` or decreasing `max_model_len`.
    """

    metrics = parse_vllm_startup_metrics(logs)

    assert metrics["model_weight_memory_gib"] == 24.05
    assert metrics["available_kv_cache_memory_gib"] == 13.42
    assert metrics["startup_error_kind"] == "kv_cache_too_small"
    assert metrics["suggested_max_model_len"] == 217168
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_probe_backend.py::test_parse_vllm_kv_shortage_error -q
```

Expected: fail on missing `startup_error_kind` and `suggested_max_model_len`.

- [ ] **Step 3: Extend startup parser**

Modify `llmnode/perf/probe_backend.py` in `parse_vllm_startup_metrics()`:

```python
    kv_shortage = re.search(
        r"max seq len \\((\\d+)\\).*maximum number of tokens.*KV cache \\((\\d+)\\)",
        logs,
        re.IGNORECASE | re.DOTALL,
    )
    if kv_shortage:
        metrics["startup_error_kind"] = "kv_cache_too_small"
        metrics["requested_max_model_len"] = int(kv_shortage.group(1))
        metrics["suggested_max_model_len"] = int(kv_shortage.group(2))
    if re.search(r"out of memory|OutOfMemory|CUDA out of memory", logs):
        metrics["startup_error_kind"] = metrics.get("startup_error_kind") or "cuda_oom"
```

- [ ] **Step 4: Add real executor test with fakes**

Add to `tests/test_perf_lab_runner.py`:

```python
from llmnode.perf.lab_runner import LocalPerfPointExecutor


class FakeControl:
    def __init__(self):
        self.calls = []

    def stop(self, profile):
        self.calls.append(("stop", profile))

    def start(self, profile, overrides):
        self.calls.append(("start", profile, overrides))

    def wait_healthy(self, profile):
        self.calls.append(("wait_healthy", profile))
        return True

    def startup_metrics(self, profile):
        return {"model_weight_memory_gib": 24.05, "available_kv_cache_memory_gib": 17.38}


class FakeBenchmark:
    def __call__(self, *, profile, targets, max_tokens, warmup_runs, measure_runs, sample_interval, output_dir, concurrency):
        point_dir = Path(output_dir)
        point_dir.mkdir(parents=True, exist_ok=True)
        (point_dir / "summary.json").write_text('{"steps": []}', encoding="utf-8")
        (point_dir / "samples.jsonl").write_text("", encoding="utf-8")


def test_local_executor_runs_control_and_benchmark(tmp_path):
    store = PerfRunStore(tmp_path)
    request = PerfRunRequest(profile="vllm_qwen36-27b-nvfp4", targets=[4096])
    run = store.create_run(request, expand_matrix(request))
    point = expand_matrix(request)[0]
    control = FakeControl()
    executor = LocalPerfPointExecutor(control=control, benchmark=FakeBenchmark())

    executor.execute_point(run_id=run["run_id"], point=point, request=request, store=store, cancel_requested=lambda: False)

    assert control.calls[0] == ("stop", "vllm_qwen36-27b-nvfp4")
    assert store.get_run(run["run_id"])["matrix"][0]["status"] == "completed"
```

- [ ] **Step 5: Implement control wrapper and local executor**

In `llmnode/perf/lab_runner.py`, add:

```python
from pathlib import Path
import os
import subprocess
import time

import httpx

from ..config import load_settings
from ..diagnostics import get_container_logs
from .probe_backend import parse_vllm_startup_metrics
from .benchmark import run_benchmark


class ControlFacade:
    def __init__(self, *, python_bin: str = "/home/heshan/.conda/envs/paper2any/bin/python"):
        self.python_bin = python_bin

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
        subprocess.run(
            [self.python_bin, "-m", "llmnode.control", *args],
            check=True,
            env=self._env(profile, overrides),
        )

    def stop(self, profile: str) -> None:
        self._run_control(profile, ["stop"])

    def start(self, profile: str, overrides: dict[str, object]) -> None:
        self._run_control(profile, ["start", "--service", "vllm", "--daemon"], overrides)

    def wait_healthy(self, profile: str) -> bool:
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
```

Before committing, verify `wait_healthy()` loads settings with the same environment used for `start()`. If not, pass the resolved backend URL from `_env()` into the health loop rather than relying on ambient process environment.

- [ ] **Step 6: Run tests**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_probe_backend.py tests/test_perf_lab_runner.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```bash
git add llmnode/perf/probe_backend.py llmnode/perf/lab_runner.py tests/test_probe_backend.py tests/test_perf_lab_runner.py
git commit -m "接入性能实验室本地执行器"
```

---

### Task 6: Benchmark Concurrency Support

**Files:**
- Modify: `llmnode/perf/benchmark.py`
- Modify: `llmnode/perf/models.py`
- Modify: `scripts/benchmark_backend.py`
- Test: `tests/test_perf_benchmark.py`

- [ ] **Step 1: Add CLI and summary tests**

Add to `tests/test_perf_benchmark.py`:

```python
def test_benchmark_cli_accepts_concurrency():
    from scripts.benchmark_backend import build_parser

    parser = build_parser()
    args = parser.parse_args(["--concurrency", "2"])

    assert args.concurrency == 2


def test_summarize_attempts_records_success_rate():
    summary = _summarize_attempts([
        {"kind": "measure", "result": "success", "latency_ms": 100.0, "completion_tokens_per_second": 10.0},
        {"kind": "measure", "result": "timeout"},
    ])

    assert summary["success_count"] == 1
    assert summary["error_count"] == 1
    assert summary["success_rate"] == 0.5
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_perf_benchmark.py -q
```

Expected: fail on missing concurrency and success-rate fields.

- [ ] **Step 3: Add concurrency parameter**

Modify `scripts/benchmark_backend.py`:

```python
    parser.add_argument("--concurrency", type=int, default=1)
```

Pass it to `run_benchmark()`:

```python
        concurrency=args.concurrency,
```

Modify `run_benchmark()` signature:

```python
    concurrency: int = 1,
```

Add `concurrency` to `BenchmarkRun` in `llmnode/perf/models.py`.

- [ ] **Step 4: Add success-rate summary fields**

Modify `_summarize_attempts()`:

```python
    success_count = sum(1 for item in measured if item.get("result") == "success")
    error_count = len(measured) - success_count
    summary["success_count"] = success_count
    summary["error_count"] = error_count
    summary["success_rate"] = success_count / len(measured) if measured else None
```

Add matching fields to `BenchmarkStepResult`.

- [ ] **Step 5: Implement minimal concurrency**

Keep `concurrency=1` behavior unchanged. For `concurrency > 1`, run the same prompt in a `ThreadPoolExecutor` per measured round and append each request as a separate attempt with `concurrency_index`.

Core shape inside the attempt loop:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed


def post_chat_completion_for_attempt(active_label: str) -> httpx.Response:
    return _run_with_sampling(
        samples,
        active_label,
        settings.vllm.backend_type,
        settings.vllm.container_name,
        sample_interval,
        lambda: httpx.post(
            f"{settings.gateway.backend_url.rstrip('/')}/v1/chat/completions",
            json={
                "model": settings.vllm.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            },
            timeout=settings.gateway.backend_request_timeout_seconds,
        ),
    )


def parse_attempt_response(response: httpx.Response) -> dict[str, Any]:
    payload = response.json()
    usage = payload.get("usage") if isinstance(payload, dict) else {}
    completion_tokens = usage.get("completion_tokens") if isinstance(usage, dict) else None
    return {
        "http_status": response.status_code,
        "prompt_tokens": usage.get("prompt_tokens") if isinstance(usage, dict) else None,
        "completion_tokens": completion_tokens,
        "total_tokens": usage.get("total_tokens") if isinstance(usage, dict) else None,
        "completion_tokens_per_second": None,
        "result": "success" if response.is_success else "error",
    }


def execute_attempt(active_label: str, kind: str, concurrency_index: int) -> dict[str, Any]:
    attempt: dict[str, Any] = {
        "kind": kind,
        "concurrency_index": concurrency_index,
        "result": "unknown",
    }
    response = post_chat_completion_for_attempt(active_label)
    attempt.update(parse_attempt_response(response))
    return attempt

if concurrency == 1:
    attempts.append(execute_attempt(active_label, kind, 1))
else:
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(execute_attempt, f"{active_label}-c{idx}", kind, idx)
            for idx in range(1, concurrency + 1)
        ]
        for future in as_completed(futures):
            attempts.append(future.result())
```

Do not share one `httpx.Client` across worker threads. Create a short-lived `httpx.Client` inside `execute_attempt()`.

- [ ] **Step 6: Run tests**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_perf_benchmark.py -q
```

Expected: all benchmark tests pass.

- [ ] **Step 7: Commit**

```bash
git add llmnode/perf/benchmark.py llmnode/perf/models.py scripts/benchmark_backend.py tests/test_perf_benchmark.py
git commit -m "支持性能测试并发参数"
```

---

### Task 7: Frontend Store And Navigation

**Files:**
- Modify: `web-console/src/store.tsx`
- Modify: `web-console/src/App.tsx`
- Modify: `web-console/src/components/Layout.tsx`
- Modify: `web-console/src/i18n.ts`
- Test: `web-console/src/components/Layout.test.tsx`

- [ ] **Step 1: Add frontend types and store methods**

In `web-console/src/store.tsx`, extend:

```ts
export type Page = 'overview' | 'usage' | 'keys' | 'models' | 'schedule' | 'performance';
```

Add types:

```ts
export interface PerfRunRequest {
  profile: string;
  targets: number[];
  max_tokens: number;
  warmup_runs: number;
  measure_runs: number;
  sample_interval: number;
  concurrency: number;
  restart_backend: boolean;
  matrix: Record<string, Array<number>>;
}

export interface PerfRunSummary {
  run_id: string;
  status: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  request: PerfRunRequest;
  matrix?: Array<Record<string, unknown>>;
  errors?: Array<Record<string, unknown>>;
}
```

Add state:

```ts
  const [perfRuns, setPerfRuns] = useState<PerfRunSummary[]>([]);
  const [activePerfRun, setActivePerfRun] = useState<PerfRunSummary | null>(null);
```

Add methods:

```ts
  async function refreshPerfRuns() {
    const payload = await requestJson<{runs: PerfRunSummary[]}>('/admin/perf/runs');
    setPerfRuns(payload.runs);
    return payload.runs;
  }

  async function createPerfRun(payload: PerfRunRequest) {
    const response = await requestJson<{run: PerfRunSummary}>('/admin/perf/runs', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    setActivePerfRun(response.run);
    void refreshPerfRuns();
    return response.run;
  }

  async function cancelPerfRun(runId: string) {
    const response = await requestJson<{run: PerfRunSummary}>(`/admin/perf/runs/${encodeURIComponent(runId)}/cancel`, {
      method: 'POST',
    });
    setActivePerfRun(response.run);
    void refreshPerfRuns();
    return response.run;
  }
```

Expose these values in provider context.

- [ ] **Step 2: Add i18n keys and navigation**

In `web-console/src/i18n.ts`, add:

```ts
performance: {zh: '性能实验室', en: 'Performance'},
```

Add layout nav key under `layout.nav`.

In `web-console/src/components/Layout.tsx`, import `Gauge` from `lucide-react` and add:

```tsx
{ id: 'performance', label: t('layout.nav.performance'), icon: Gauge },
```

- [ ] **Step 3: Add App route placeholder**

In `web-console/src/App.tsx`:

```tsx
import { PerformanceLabView } from './pages/PerformanceLabView';
```

Add case:

```tsx
case 'performance': return <PerformanceLabView />;
```

Create placeholder page:

```tsx
export function PerformanceLabView() {
  return <div>性能实验室</div>;
}
```

- [ ] **Step 4: Run frontend tests**

Run:

```bash
cd web-console
npm test -- --run src/components/Layout.test.tsx
```

Expected: existing layout tests pass after updating expected nav labels if needed.

- [ ] **Step 5: Commit**

```bash
git add web-console/src/store.tsx web-console/src/App.tsx web-console/src/components/Layout.tsx web-console/src/i18n.ts web-console/src/pages/PerformanceLabView.tsx web-console/src/components/Layout.test.tsx
git commit -m "接入性能实验室前端入口"
```

---

### Task 8: Performance Lab Frontend Page

**Files:**
- Modify: `web-console/src/pages/PerformanceLabView.tsx`
- Test: `web-console/src/pages/ConsoleViews.test.tsx`

- [ ] **Step 1: Add page test**

Add to `web-console/src/pages/ConsoleViews.test.tsx`:

```tsx
it('creates a performance lab run from the console', async () => {
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole('button', {name: /性能实验室|Performance/i}));
  await user.clear(screen.getByLabelText(/profile/i));
  await user.type(screen.getByLabelText(/profile/i), 'vllm_qwen36-27b-nvfp4');
  await user.click(screen.getByRole('button', {name: /开始测试|Start/i}));

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/admin/perf/runs'),
      expect.objectContaining({method: 'POST'}),
    );
  });
});
```

Use the existing test file's fetch mock style. Add mock response:

```ts
if (url.includes('/admin/perf/runs') && init?.method === 'POST') {
  return jsonResponse({run: {
    run_id: 'run-1',
    status: 'queued',
    created_at: '2026-06-02T00:00:00Z',
    started_at: null,
    finished_at: null,
    request: {
      profile: 'vllm_qwen36-27b-nvfp4',
      targets: [4096],
      max_tokens: 64,
      warmup_runs: 1,
      measure_runs: 3,
      sample_interval: 1,
      concurrency: 1,
      restart_backend: true,
      matrix: {},
    },
  }});
}
if (url.includes('/admin/perf/runs')) {
  return jsonResponse({runs: []});
}
```

- [ ] **Step 2: Implement page**

`web-console/src/pages/PerformanceLabView.tsx` should include:

```tsx
import React from 'react';
import { Play, Square } from 'lucide-react';
import { useAppContext } from '../store';

function parseTargets(value: string): number[] {
  return value
    .split(',')
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isFinite(item) && item > 0);
}

export function PerformanceLabView() {
  const { createPerfRun, cancelPerfRun, activePerfRun, perfRuns, t } = useAppContext();
  const [profile, setProfile] = React.useState('vllm_qwen36-27b-nvfp4');
  const [targets, setTargets] = React.useState('4096,32768,65536,131072,176128,262000');
  const [submitting, setSubmitting] = React.useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    try {
      await createPerfRun({
        profile,
        targets: parseTargets(targets),
        max_tokens: 64,
        warmup_runs: 1,
        measure_runs: 3,
        sample_interval: 1,
        concurrency: 1,
        restart_backend: true,
        matrix: {},
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <form onSubmit={submit} className="rounded-3xl border border-white/50 bg-white/55 p-6 shadow-sm backdrop-blur-md">
        <h2 className="text-2xl font-bold text-slate-900">{t('performance.title')}</h2>
        <label className="mt-5 block text-sm font-semibold text-slate-700">
          profile
          <input aria-label="profile" value={profile} onChange={(event) => setProfile(event.target.value)} className="mt-2 w-full rounded-xl border border-white/70 bg-white px-3 py-2" />
        </label>
        <label className="mt-4 block text-sm font-semibold text-slate-700">
          targets
          <textarea aria-label="targets" value={targets} onChange={(event) => setTargets(event.target.value)} className="mt-2 h-28 w-full rounded-xl border border-white/70 bg-white px-3 py-2" />
        </label>
        <button type="submit" disabled={submitting} className="mt-5 inline-flex items-center gap-2 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-50">
          <Play className="h-4 w-4" />
          {t('performance.start')}
        </button>
      </form>

      <section className="rounded-3xl border border-white/50 bg-white/55 p-6 shadow-sm backdrop-blur-md">
        <h3 className="text-xl font-bold text-slate-900">{t('performance.currentRun')}</h3>
        {activePerfRun ? (
          <div className="mt-4 space-y-3">
            <div className="font-mono text-sm">{activePerfRun.run_id}</div>
            <div className="text-sm text-slate-600">{activePerfRun.status}</div>
            <button type="button" onClick={() => cancelPerfRun(activePerfRun.run_id)} className="inline-flex items-center gap-2 rounded-full border border-red-200 bg-red-50 px-4 py-2 text-sm font-semibold text-red-700">
              <Square className="h-4 w-4" />
              {t('performance.cancel')}
            </button>
          </div>
        ) : (
          <p className="mt-4 text-sm text-slate-500">{t('performance.noRun')}</p>
        )}

        <h3 className="mt-8 text-xl font-bold text-slate-900">{t('performance.history')}</h3>
        <div className="mt-4 space-y-2">
          {perfRuns.map((run) => (
            <div key={run.run_id} className="rounded-2xl border border-white/70 bg-white/70 p-3">
              <div className="font-mono text-xs">{run.run_id}</div>
              <div className="text-xs text-slate-500">{run.status}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 3: Add i18n keys**

In `web-console/src/i18n.ts`:

```ts
performance: {
  title: {zh: '性能实验室', en: 'Performance Lab'},
  start: {zh: '开始测试', en: 'Start'},
  cancel: {zh: '取消任务', en: 'Cancel'},
  currentRun: {zh: '当前任务', en: 'Current Run'},
  noRun: {zh: '当前没有运行中的性能任务', en: 'No active performance run'},
  history: {zh: '历史任务', en: 'History'},
}
```

- [ ] **Step 4: Run frontend tests**

Run:

```bash
cd web-console
npm test -- --run src/pages/ConsoleViews.test.tsx
```

Expected: tests pass.

- [ ] **Step 5: Commit**

```bash
git add web-console/src/pages/PerformanceLabView.tsx web-console/src/pages/ConsoleViews.test.tsx web-console/src/i18n.ts
git commit -m "新增性能实验室前端页面"
```

---

### Task 9: Documentation And Final Verification

**Files:**
- Modify: `docs/blueprint/current.md`
- Modify: `docs/process/run.md`
- Modify: `docs/knowledge/model_context_performance.md`

- [ ] **Step 1: Update current blueprint**

In `docs/blueprint/current.md`, add a short section under existing management/diagnostics capabilities:

```markdown
- 性能实验室自动化矩阵已形成最小闭环：
  - 管理 API 可创建、查询、取消性能测试任务
  - 任务结果落盘到 `runtime/benchmarks/<run_id>/`
  - 启动失败、请求失败和连续采样均有结构化记录
  - 管理台提供性能实验室入口，用于发起测试和查看历史结果
```

- [ ] **Step 2: Update run process**

In `docs/process/run.md`, add an operator note:

```markdown
## 性能实验室

- 性能实验室会自动重启本地后端，运行前应确认没有生产推理请求正在使用该节点。
- 默认同一时间只允许一个性能任务。
- 长上下文测试可能持续数分钟，结果写入 `runtime/benchmarks/<run_id>/`。
- GPU 实测结果只代表当前机器、当前镜像、当前 profile 和当前模型文件。
```

- [ ] **Step 3: Update knowledge doc**

In `docs/knowledge/model_context_performance.md`, update section 11 from design note to implemented behavior:

```markdown
- 自动化矩阵已落地后，应优先通过 `/admin/perf/runs` 生成新结果。
- 手工测试仍可用于临时排障，但正式记录应引用 `runtime/benchmarks/<run_id>/summary.json`。
```

- [ ] **Step 4: Run backend tests**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest \
  tests/test_perf_lab_models.py \
  tests/test_perf_lab_store.py \
  tests/test_perf_lab_runner.py \
  tests/test_admin_perf_lab.py \
  tests/test_perf_benchmark.py \
  tests/test_probe_backend.py \
  -q
```

Expected: all selected backend tests pass.

- [ ] **Step 5: Run frontend tests**

Run:

```bash
cd web-console
npm test -- --run src/components/Layout.test.tsx src/pages/ConsoleViews.test.tsx
```

Expected: selected frontend tests pass.

- [ ] **Step 6: Manual smoke without GPU benchmark**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_admin_perf_lab.py -q
```

Expected: API lifecycle passes with fake executor.

- [ ] **Step 7: Optional manual GPU acceptance**

Only run after confirming the active node can be interrupted:

```bash
curl -sS -X POST http://127.0.0.1:15673/admin/perf/runs \
  -H "Authorization: Bearer <admin-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "profile": "vllm_qwen36-27b-nvfp4",
    "targets": [4096, 262000],
    "max_tokens": 64,
    "warmup_runs": 0,
    "measure_runs": 1,
    "sample_interval": 1,
    "concurrency": 1,
    "restart_backend": true,
    "matrix": {
      "gpu_memory_utilization": [0.55],
      "max_model_len": [262144],
      "max_num_seqs": [4]
    }
  }'
```

Expected:

- API returns a `run_id`.
- `GET /admin/perf/runs/<run_id>` eventually returns `completed` or `completed_with_errors`.
- `runtime/benchmarks/<run_id>/points/point-001/startup.json` includes vLLM startup memory fields.
- `runtime/benchmarks/<run_id>/points/point-001/samples.jsonl` contains multiple sample rows for the 256K request.

- [ ] **Step 8: Commit**

```bash
git add docs/blueprint/current.md docs/process/run.md docs/knowledge/model_context_performance.md
git commit -m "更新性能实验室运行文档"
```

---

## Implementation Notes

- Do not modify `config/defaults.yaml` as part of this feature unless a later task explicitly requires it.
- Do not persist matrix overrides back into `config/backends/*.yaml`; overrides are per-run runtime inputs.
- Keep GPU acceptance manual. It is too slow and environment-dependent for default tests.
- Prefer the existing Python environment: `/home/heshan/.conda/envs/paper2any/bin/python`.
- If a task discovers that a direct control function exists and is safer than subprocess, use the direct function but keep the same externally observable control behavior.

## Plan Self-Review

- Spec coverage: API, task model, matrix execution, startup parsing, benchmark口径, frontend page, storage, cancellation, error handling, and docs are all mapped to tasks.
- Scope: This plan intentionally keeps single-node execution and file-backed storage. Multi-node scheduling, K8s, model download, and cost estimation remain out of scope.
- Type consistency: `PerfRunRequest`, `PerfMatrixPoint`, `PerfRunStore`, `PerfLabRunner`, and frontend `PerfRunSummary` names are stable across tasks.
