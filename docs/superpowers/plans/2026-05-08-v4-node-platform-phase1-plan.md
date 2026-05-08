# V4 Node Platform Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working V4 slice that upgrades `llmnode` from a single-node control plane into a minimal node platform with a new `control-api`, node/runtime object model, and a refactored gateway that consumes control-plane runtime views.

**Architecture:** Phase 1 keeps single-machine deployment as the default and focuses on separating concerns rather than adding scale immediately. We introduce `control-api` as the node-platform fact source, keep `gateway-api` as the inference hot path, and extend `node-agent` so it can register/report against the control plane. The plan deliberately stops before deep `sub2api` management integration and before real multi-node scheduling complexity.

**Tech Stack:** Python 3.11, FastAPI, SQLite, httpx, Vue 3, Pinia, Element Plus, pytest

---

## File Structure

This phase adds a new control-plane slice without throwing away the current gateway and agent code.

- Existing `llmnode/api/app.py`
  Responsibility after Phase 1: inference-only gateway entrypoint that reads route/runtime views from control-plane state instead of owning all control-plane state inline.

- New `llmnode/control/app.py`
  Responsibility: `control-api` FastAPI app exposing node, artifact, profile, route, runtime-instance, and platform status endpoints for the local console.

- New `llmnode/control/models.py`
  Responsibility: control-plane dataclasses / pydantic models for `Node`, `ModelArtifact`, `RuntimeProfile`, `LogicalModelRoute`, `RuntimeInstance`.

- New `llmnode/control/service.py`
  Responsibility: read/write orchestration around storage helpers, node heartbeats, route views, and instance lifecycle state.

- Existing `llmnode/storage/db.py`
  Responsibility after Phase 1: expand SQLite schema to hold control-plane objects and route/runtime snapshots.

- Existing `llmnode/agent/service.py`
  Responsibility after Phase 1: still runs local backend control, but now also reports node heartbeat/inventory/runtime state to `control-api`.

- New `llmnode/control_main.py`
  Responsibility: uvicorn entrypoint for `control-api`.

- Existing `web-console/src/router/index.ts`
  Responsibility after Phase 1: point platform-oriented views at new control-plane concepts instead of only gateway/agent status.

- Existing `web-console/src/stores/overview.ts`
  Responsibility after Phase 1: fetch from `control-api` status endpoints, not only `gateway-api /admin/status`.

- Existing `web-console/src/views/*`
  Responsibility after Phase 1: repurpose current console to a node-platform console for nodes / artifacts / runtime profiles / runtime instances, while keeping current overview functionality.

- New `tests/test_control_api.py`
  Responsibility: verify control-plane CRUD/status endpoints.

- New `tests/test_node_reporting.py`
  Responsibility: verify `node-agent` reporting to `control-api`.

- Existing `tests/test_api_openai.py` and `tests/test_api_anthropic.py`
  Responsibility after Phase 1: verify gateway still serves inference and now routes via control-plane runtime view.

---

### Task 1: Add the control-plane schema and object model

**Files:**
- Create: `llmnode/control/models.py`
- Modify: `llmnode/storage/db.py`
- Test: `tests/test_control_storage.py`

- [ ] **Step 1: Write the failing storage tests**

Create `tests/test_control_storage.py` with:

```python
from pathlib import Path

from llmnode.storage.db import (
    init_db,
    create_node,
    list_nodes,
    create_runtime_profile,
    list_runtime_profiles,
    create_model_artifact,
    list_model_artifacts,
    create_logical_model_route,
    list_logical_model_routes,
)


def test_create_and_list_nodes(tmp_path: Path):
    conn = init_db(tmp_path / "gateway.db")
    node = create_node(
        conn,
        {
            "name": "local-node",
            "mode": "local",
            "endpoint": "http://127.0.0.1:4010",
            "status": "ready",
            "labels": ["default"],
            "agent_version": "0.1.0",
        },
    )
    assert node["name"] == "local-node"
    rows = list_nodes(conn)
    assert len(rows) == 1
    assert rows[0]["mode"] == "local"


def test_create_profiles_artifacts_and_routes(tmp_path: Path):
    conn = init_db(tmp_path / "gateway.db")
    profile = create_runtime_profile(
        conn,
        {
            "backend_type": "vllm",
            "profile_name": "default-vllm",
            "launch_config": {"gpu_memory_utilization": 0.6},
            "resource_policy": {"exclusive": True},
            "feature_flags": {"tool_calling": True},
        },
    )
    artifact = create_model_artifact(
        conn,
        {
            "name": "qwen36-main",
            "family": "qwen",
            "format": "hf",
            "model_path": "models/Qwen/Qwen3.6-35B-A3B-FP8",
            "backend_compatibility": ["vllm"],
            "size_bytes": 0,
        },
    )
    route = create_logical_model_route(
        conn,
        {
            "logical_name": "claude-sonnet-4-5-20250929",
            "display_name": "Claude Sonnet 4.5",
            "target_node_name": "local-node",
            "artifact_name": artifact["name"],
            "runtime_profile_name": profile["profile_name"],
            "enabled": True,
            "protocol_capabilities": {"anthropic": True, "openai": True},
        },
    )
    assert route["logical_name"] == "claude-sonnet-4-5-20250929"
    assert len(list_runtime_profiles(conn)) == 1
    assert len(list_model_artifacts(conn)) == 1
    assert len(list_logical_model_routes(conn)) == 1
```

- [ ] **Step 2: Run the storage tests to verify they fail**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_control_storage.py -q
```

Expected: FAIL with missing tables or helper functions.

- [ ] **Step 3: Add the control-plane dataclasses and schema helpers**

Create `llmnode/control/models.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Node:
    name: str
    mode: str
    endpoint: str
    status: str
    labels: list[str]
    agent_version: str
    last_heartbeat_at: str | None = None


@dataclass(frozen=True)
class ModelArtifact:
    name: str
    family: str
    format: str
    model_path: str
    backend_compatibility: list[str]
    size_bytes: int


@dataclass(frozen=True)
class RuntimeProfile:
    backend_type: str
    profile_name: str
    launch_config: dict[str, Any]
    resource_policy: dict[str, Any]
    feature_flags: dict[str, Any]


@dataclass(frozen=True)
class LogicalModelRoute:
    logical_name: str
    display_name: str
    target_node_name: str
    artifact_name: str
    runtime_profile_name: str
    enabled: bool
    protocol_capabilities: dict[str, Any]
```

Extend `llmnode/storage/db.py` with tables and JSON helpers for:

```sql
nodes
runtime_profiles
model_artifacts
logical_model_routes
runtime_instances
```

Also add CRUD helpers named exactly as used in the test.

- [ ] **Step 4: Run the storage tests to verify they pass**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_control_storage.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add llmnode/control/models.py llmnode/storage/db.py tests/test_control_storage.py
git commit -m "feat: add v4 control plane schema"
```

### Task 2: Introduce `control-api` and the platform status surface

**Files:**
- Create: `llmnode/control/app.py`
- Create: `llmnode/control_main.py`
- Create: `tests/test_control_api.py`
- Modify: `llmnode/config.py`

- [ ] **Step 1: Write the failing control API tests**

Create `tests/test_control_api.py` with:

```python
import asyncio

import httpx

from llmnode.control.app import create_control_app


def test_control_status_and_nodes_endpoints_exist():
    async def run():
        app = create_control_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            status = await client.get("/control/status", headers={"Authorization": "Bearer dev-key"})
            assert status.status_code == 200
            payload = status.json()
            assert payload["platform_mode"] == "single-node"

            nodes = await client.get("/control/nodes", headers={"Authorization": "Bearer dev-key"})
            assert nodes.status_code == 200
            assert isinstance(nodes.json()["nodes"], list)

    asyncio.run(run())
```

- [ ] **Step 2: Run the control API tests to confirm failure**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_control_api.py -q
```

Expected: FAIL because `llmnode.control.app` does not exist yet.

- [ ] **Step 3: Implement the initial `control-api`**

Create `llmnode/control/app.py` with a `create_control_app()` factory that:

- loads settings
- initializes SQLite
- seeds a `local-node`
- exposes:
  - `GET /health/liveliness`
  - `GET /control/status`
  - `GET /control/nodes`
  - `GET /control/runtime-profiles`
  - `GET /control/artifacts`
  - `GET /control/routes`
  - `GET /control/runtime-instances`

Add `llmnode/control_main.py`:

```python
from uvicorn import run

from .config import load_settings
from .control.app import create_control_app


def main() -> None:
    app = create_control_app()
    settings = load_settings()
    run(app, host=settings.control.host, port=settings.control.port)


if __name__ == "__main__":
    main()
```

Extend `llmnode/config.py` with:

```python
@dataclass
class ControlSettings:
    host: str = "127.0.0.1"
    port: int = 4020
```

and include it in `AppSettings`.

- [ ] **Step 4: Run the control API tests to verify pass**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_control_api.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add llmnode/control/app.py llmnode/control_main.py llmnode/config.py tests/test_control_api.py
git commit -m "feat: add control api skeleton"
```

### Task 3: Teach `node-agent` to register and report to the control plane

**Files:**
- Modify: `llmnode/agent/service.py`
- Modify: `llmnode/agent/state.py`
- Create: `tests/test_node_reporting.py`

- [ ] **Step 1: Write the failing node-reporting tests**

Create `tests/test_node_reporting.py` with:

```python
import asyncio

import httpx

from llmnode.agent.service import create_agent_app


def test_agent_exposes_control_report_payload():
    async def run():
        app = create_agent_app(enable_monitor=False)

        async def fake_health(_):
            return True

        app.state.backend_driver.health = fake_health
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/report")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["node"]["name"] == "local-node"
            assert payload["runtime"]["backend_type"] == "vllm"

    asyncio.run(run())
```

- [ ] **Step 2: Run the node-reporting tests to confirm failure**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_node_reporting.py -q
```

Expected: FAIL because `/report` does not exist.

- [ ] **Step 3: Implement a minimal node reporting surface**

Extend `llmnode/agent/service.py` with:

- agent-local node identity:

```python
app.state.node_name = "local-node"
app.state.node_mode = "local"
```

- a new endpoint:

```python
@app.get("/report")
async def report():
    return {
        "node": {
            "name": app.state.node_name,
            "mode": app.state.node_mode,
            "endpoint": f"http://{settings.agent.host}:{settings.agent.port}",
            "status": app.state.agent.status,
        },
        "runtime": {
            "backend_type": app.state.backend_type,
            "backend_ready": app.state.agent.backend_ready,
        },
    }
```

Also extend `AgentState` with any fields needed to support clean reporting.

- [ ] **Step 4: Run the node-reporting tests to verify pass**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_node_reporting.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add llmnode/agent/service.py llmnode/agent/state.py tests/test_node_reporting.py
git commit -m "feat: add node agent reporting surface"
```

### Task 4: Make `control-api` consume agent reports and expose a runtime view

**Files:**
- Modify: `llmnode/control/app.py`
- Create: `llmnode/control/service.py`
- Modify: `llmnode/storage/db.py`
- Test: `tests/test_control_runtime_view.py`

- [ ] **Step 1: Write the failing runtime-view tests**

Create `tests/test_control_runtime_view.py` with:

```python
import asyncio

import httpx

from llmnode.control.app import create_control_app


def test_control_runtime_view_returns_local_runtime_instance():
    async def run():
        app = create_control_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            sync = await client.post(
                "/control/sync/local-node",
                headers={"Authorization": "Bearer dev-key"},
                json={
                    "node": {
                        "name": "local-node",
                        "mode": "local",
                        "endpoint": "http://127.0.0.1:4010",
                        "status": "ready",
                    },
                    "runtime": {
                        "backend_type": "vllm",
                        "backend_ready": True,
                        "instance_name": "qwen36-main",
                        "listen_endpoint": "http://127.0.0.1:8000",
                    },
                },
            )
            assert sync.status_code == 200

            view = await client.get("/control/runtime-view", headers={"Authorization": "Bearer dev-key"})
            assert view.status_code == 200
            payload = view.json()
            assert len(payload["instances"]) == 1
            assert payload["instances"][0]["listen_endpoint"] == "http://127.0.0.1:8000"

    asyncio.run(run())
```

- [ ] **Step 2: Run the runtime-view tests to confirm failure**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_control_runtime_view.py -q
```

Expected: FAIL because sync/runtime-view endpoints do not exist.

- [ ] **Step 3: Implement the first control-plane runtime-view flow**

Create `llmnode/control/service.py` with helpers for:

```python
def seed_local_node(...)
def upsert_node_report(...)
def build_runtime_view(...)
```

Add endpoints in `llmnode/control/app.py`:

- `POST /control/sync/{node_name}`
- `GET /control/runtime-view`

The first phase runtime view can be simple:

```json
{
  "instances": [
    {
      "logical_name": "claude-sonnet-4-5-20250929",
      "backend_type": "vllm",
      "listen_endpoint": "http://127.0.0.1:8000",
      "node_name": "local-node",
      "status": "ready"
    }
  ]
}
```

- [ ] **Step 4: Run the runtime-view tests to verify pass**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_control_runtime_view.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add llmnode/control/app.py llmnode/control/service.py llmnode/storage/db.py tests/test_control_runtime_view.py
git commit -m "feat: add control plane runtime view"
```

### Task 5: Refactor `gateway-api` to consume control-plane runtime view

**Files:**
- Modify: `llmnode/api/app.py`
- Modify: `llmnode/proxy/router.py`
- Modify: `llmnode/config.py`
- Test: `tests/test_api_openai.py`
- Test: `tests/test_api_anthropic.py`

- [ ] **Step 1: Extend gateway tests to assert runtime-view routing**

Update tests with a fake runtime view source:

```python
async def fake_runtime_view():
    return {
        "claude-sonnet-4-5-20250929": {
            "backend_type": "vllm",
            "listen_endpoint": "http://127.0.0.1:8000",
            "backend_model": "qwen36-35b-a3b",
        }
    }
```

Assert gateway route resolution uses this view instead of only in-memory `models`.

- [ ] **Step 2: Run the gateway tests to confirm failure**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_api_openai.py tests/test_api_anthropic.py -q
```

Expected: FAIL after the tests are tightened.

- [ ] **Step 3: Implement runtime-view based routing**

Refactor `llmnode/api/app.py` so it can fetch a runtime view from `control-api`:

```python
app.state.control_runtime_view_url = settings.control.runtime_view_url
```

Add to config:

```python
runtime_view_url: str = "http://127.0.0.1:4020/control/runtime-view"
```

In `llmnode/proxy/router.py`, add a route-resolution path that consumes a flattened runtime view mapping:

```python
def resolve_runtime_route(model_name: str, runtime_view: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ...
```

Phase 1 assumption:
- runtime view stays local and single-target
- gateway still proxies to a single resolved backend endpoint per logical model

- [ ] **Step 4: Run the gateway tests to verify pass**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_api_openai.py tests/test_api_anthropic.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add llmnode/api/app.py llmnode/proxy/router.py llmnode/config.py tests/test_api_openai.py tests/test_api_anthropic.py
git commit -m "feat: route gateway through control plane runtime view"
```

### Task 6: Reframe the console around node-platform concepts

**Files:**
- Modify: `web-console/src/router/index.ts`
- Modify: `web-console/src/stores/overview.ts`
- Modify: `web-console/src/types.ts`
- Modify: `web-console/src/views/OverviewView.vue`
- Modify: `web-console/src/views/SystemStatusView.vue`
- Create: `web-console/src/views/NodesView.vue`
- Create: `web-console/src/views/ArtifactsView.vue`
- Create: `web-console/src/views/ProfilesView.vue`

- [ ] **Step 1: Write the failing frontend store tests**

Add tests that assert the console can fetch:
- `/control/status`
- `/control/nodes`
- `/control/runtime-profiles`
- `/control/artifacts`

Use fetch mocks and assert parsed shape.

- [ ] **Step 2: Run frontend tests to confirm failure**

Run:

```bash
cd /proj02/liuheshan/llmnode/web-console && npm test -- overview
```

Expected: FAIL after test updates because store only knows old `/admin/status`.

- [ ] **Step 3: Add control-plane types and store methods**

Extend `web-console/src/types.ts` with:

```ts
export interface ControlNode { ... }
export interface ControlArtifact { ... }
export interface ControlRuntimeProfile { ... }
export interface ControlStatusSnapshot { ... }
```

Extend `web-console/src/stores/overview.ts` with:

```ts
fetchControlStatus()
fetchNodes()
fetchArtifacts()
fetchRuntimeProfiles()
```

- [ ] **Step 4: Add first platform views**

Create:

- `web-console/src/views/NodesView.vue`
- `web-console/src/views/ArtifactsView.vue`
- `web-console/src/views/ProfilesView.vue`

Update routes so the console reflects:
- Overview
- Nodes
- Artifacts
- Profiles
- Usage
- System status

Repurpose `OverviewView.vue` and `SystemStatusView.vue` to show:
- platform mode
- local node
- runtime instances
- backend status

- [ ] **Step 5: Run frontend tests to verify pass**

Run:

```bash
cd /proj02/liuheshan/llmnode/web-console && npm test -- overview
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web-console/src/router/index.ts web-console/src/stores/overview.ts web-console/src/types.ts web-console/src/views/OverviewView.vue web-console/src/views/SystemStatusView.vue web-console/src/views/NodesView.vue web-console/src/views/ArtifactsView.vue web-console/src/views/ProfilesView.vue
git commit -m "feat: add v4 node platform console views"
```

### Task 7: Add entrypoints and scripts for unified Phase 1 startup

**Files:**
- Modify: `scripts/start_gateway.sh`
- Modify: `scripts/start_agent.sh`
- Create: `scripts/start_control.sh`
- Modify: `README.md`
- Test: `tests/test_smoke.py`

- [ ] **Step 1: Write/extend the smoke tests**

Add a smoke assertion that module entrypoints import cleanly:

```python
def test_control_entrypoint_imports():
    import llmnode.control_main  # noqa: F401
```

- [ ] **Step 2: Run smoke tests to confirm failure**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_smoke.py -q
```

Expected: FAIL because `llmnode.control_main` does not yet exist in the baseline checkout.

- [ ] **Step 3: Add scripts and docs**

Create `scripts/start_control.sh` mirroring existing start scripts:

```bash
#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "${DIR}/.env" ]]; then
  source "${DIR}/.env"
fi
if [[ -x "/home/heshan/.conda/envs/paper2any/bin/python" ]]; then
  exec /home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control_main
fi
exec python -m llmnode.control_main
```

Update `README.md` startup docs to:

```bash
bash scripts/start_control.sh
bash scripts/start_gateway.sh
bash scripts/start_agent.sh
```

And explain that Phase 1 V4 still defaults to a local single-node platform.

- [ ] **Step 4: Run smoke tests to verify pass**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest tests/test_smoke.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/start_control.sh scripts/start_gateway.sh scripts/start_agent.sh README.md tests/test_smoke.py
git commit -m "chore: add v4 phase1 startup entrypoints"
```

### Task 8: Run integrated verification and capture remaining Phase 2 work

**Files:**
- Modify: `docs/blueprintV4.md`
- Modify: `docs/superpowers/specs/2026-05-08-v4-node-platform-design.md`
- Test: `tests/test_control_storage.py`
- Test: `tests/test_control_api.py`
- Test: `tests/test_node_reporting.py`
- Test: `tests/test_control_runtime_view.py`
- Test: `tests/test_api_openai.py`
- Test: `tests/test_api_anthropic.py`

- [ ] **Step 1: Run the targeted V4 backend suite**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest \
  tests/test_control_storage.py \
  tests/test_control_api.py \
  tests/test_node_reporting.py \
  tests/test_control_runtime_view.py \
  tests/test_api_openai.py \
  tests/test_api_anthropic.py \
  tests/test_smoke.py -q
```

Expected: PASS

- [ ] **Step 2: Run the full backend suite**

Run:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest -q
```

Expected: PASS

- [ ] **Step 3: Update V4 docs with explicit Phase 2 backlog**

Add a Phase 2 note to `docs/blueprintV4.md` and the V4 spec covering:

- true remote node enrollment
- northbound auth hardening
- artifact/profile CRUD UI
- runtime instance command queue
- multi-node route selectors
- deeper `sub2api` managed-node integration

- [ ] **Step 4: Commit**

```bash
git add docs/blueprintV4.md docs/superpowers/specs/2026-05-08-v4-node-platform-design.md
git commit -m "docs: capture v4 phase1 and phase2 boundary"
```
