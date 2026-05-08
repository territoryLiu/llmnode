# V2 Completion Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining V2 control-plane loop by adding gateway admin endpoints for events, logs, and restart, wiring restart into the web console, and syncing `blueprintV2.md` to the real implementation state.

**Architecture:** Keep the current FastAPI + SQLite + Vue structure. `gateway-api` remains the only public admin surface, `node-agent` remains the local executor, and `web-console` continues to consume `admin/status` plus SSE snapshots. Add one explicit agent control base URL, one restart helper in the gateway, one minimal restart action in the Pinia store, and treat `/admin/logs` as the V2 alias of request audit logs.

**Tech Stack:** Python 3.11, FastAPI, SQLite, httpx, pytest, Vue 3, Pinia, Element Plus, Vitest, Vite, `/home/heshan/.conda/envs/paper2any/bin/python`

---

## Scope Guardrails

- This plan implements only `docs/superpowers/specs/2026-05-08-v2-completion-core-design.md`.
- Follow `AGENTS.md` repo rhythm: finish implementation first, then add and run tests in one verification block near the end.
- Do not pull in Prometheus, PostgreSQL migration, request-log schema expansion, or V3 multi-backend work.
- Keep `web-console` on the existing snapshot + SSE model; do not redesign the console store architecture.
- Current `git status --short` shows the repository as untracked in this workspace, so this plan intentionally skips commit checkpoints until the repo is attached to normal Git history.

## File Map

- `config/defaults.yaml`: add the explicit agent control base URL default
- `llmnode/config.py`: load the new gateway control URL setting
- `llmnode/api/app.py`: add agent restart helper plus `/admin/events`, `/admin/logs`, `/admin/services/restart`
- `web-console/src/types.ts`: add the restart response type
- `web-console/src/stores/overview.ts`: add the restart action and reuse existing auth/header plumbing
- `web-console/src/views/SystemStatusView.vue`: add the restart button and inline error state
- `docs/blueprintV2.md`: sync V2 status sections to current reality
- `tests/test_smoke.py`: cover the new gateway config default
- `tests/test_admin_control_plane.py`: backend endpoint coverage for events, logs, and restart
- `web-console/src/stores/overview.test.ts`: frontend store coverage for restart dispatch

### Task 1: Add gateway-side agent control plumbing and admin control endpoints

**Files:**
- Modify: `config/defaults.yaml`
- Modify: `llmnode/config.py`
- Modify: `llmnode/api/app.py`
- Test later: `tests/test_smoke.py`, `tests/test_admin_control_plane.py`

- [ ] **Step 1: Add an explicit agent control base URL to gateway config**

Update `config/defaults.yaml` so the gateway has both a status URL and a control base URL:

```yaml
gateway:
  host: 0.0.0.0
  port: 4000
  api_key: dev-key
  backend_url: http://127.0.0.1:8000
  backend_model: qwen36-35b-a3b
  agent_base_url: http://127.0.0.1:4010
  agent_status_url: http://127.0.0.1:4010/state
  require_agent_ready: false
  queue_limit: 8
  execution_limit: 1
```

Then extend `GatewaySettings` and `load_settings()` in `llmnode/config.py`:

```python
@dataclass
class GatewaySettings:
    host: str = "0.0.0.0"
    port: int = 4000
    api_key: str = "dev-key"
    backend_url: str = "http://127.0.0.1:8000"
    backend_model: str = "qwen36-35b-a3b"
    agent_base_url: str = "http://127.0.0.1:4010"
    agent_status_url: str = "http://127.0.0.1:4010/state"
    require_agent_ready: bool = False
    queue_limit: int = 8
    execution_limit: int = 1
```

```python
gateway=GatewaySettings(
    host=os.getenv("VLLM_CLAUDE_GATEWAY_HOST", gateway.get("host", "0.0.0.0")),
    port=int(os.getenv("VLLM_CLAUDE_GATEWAY_PORT", gateway.get("port", 4000))),
    api_key=os.getenv("VLLM_CLAUDE_GATEWAY_KEY", gateway.get("api_key", "dev-key")),
    backend_url=os.getenv("VLLM_CLAUDE_BACKEND_URL", gateway.get("backend_url", "http://127.0.0.1:8000")),
    backend_model=os.getenv("VLLM_CLAUDE_BACKEND_MODEL", gateway.get("backend_model", "qwen36-35b-a3b")),
    agent_base_url=os.getenv(
        "VLLM_CLAUDE_AGENT_BASE_URL",
        gateway.get("agent_base_url", "http://127.0.0.1:4010"),
    ),
    agent_status_url=os.getenv(
        "VLLM_CLAUDE_AGENT_STATUS_URL",
        gateway.get("agent_status_url", "http://127.0.0.1:4010/state"),
    ),
    require_agent_ready=os.getenv(
        "VLLM_CLAUDE_REQUIRE_AGENT_READY",
        str(gateway.get("require_agent_ready", False)),
    ).lower() in {"1", "true", "yes", "on"},
    queue_limit=int(os.getenv("VLLM_CLAUDE_QUEUE_LIMIT", gateway.get("queue_limit", 8))),
    execution_limit=int(os.getenv("VLLM_CLAUDE_EXECUTION_LIMIT", gateway.get("execution_limit", 1))),
)
```

- [ ] **Step 2: Add a focused restart helper inside `create_app()`**

Inside `llmnode/api/app.py`, store the new setting on `app.state` and add one helper for the control path:

```python
app.state.agent_base_url = settings.gateway.agent_base_url
app.state.agent_status_url = settings.gateway.agent_status_url
```

```python
async def restart_agent_backend() -> dict[str, Any]:
    base_url = str(app.state.agent_base_url or "").rstrip("/")
    if not base_url:
        raise HTTPException(status_code=503, detail="agent control unavailable")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{base_url}/manage/restart")
            resp.raise_for_status()
    except httpx.ConnectError as exc:
        raise HTTPException(status_code=503, detail="agent control unavailable") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="agent restart failed") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="agent control unavailable") from exc

    payload = resp.json() if resp.content else {}
    return {
        "accepted": True,
        "service": "backend",
        "action": "restart",
        "agent_status": payload.get("status", "recovering"),
    }
```

Expose the helper for endpoint use:

```python
app.state.restart_agent_backend = restart_agent_backend
```

- [ ] **Step 3: Add `/admin/logs` and `/admin/events` as stable admin endpoints**

In `llmnode/api/app.py`, keep `/admin/request-logs` intact and add the V2-completion aliases next to it:

```python
@app.get("/admin/request-logs")
async def admin_request_logs(request: Request, limit: int = 50):
    _resolve_auth(request, "admin")
    request_id = _request_id(request)
    response = JSONResponse({"logs": list_request_logs(request.app.state.db, limit=limit)})
    response.headers["x-request-id"] = request_id
    return response


@app.get("/admin/logs")
async def admin_logs(request: Request, limit: int = 50):
    _resolve_auth(request, "admin")
    request_id = _request_id(request)
    response = JSONResponse({"logs": list_request_logs(request.app.state.db, limit=limit)})
    response.headers["x-request-id"] = request_id
    return response


@app.get("/admin/events")
async def admin_events(request: Request, limit: int = 50):
    _resolve_auth(request, "admin")
    request_id = _request_id(request)
    response = JSONResponse({"events": list_agent_events(request.app.state.db, limit=limit)})
    response.headers["x-request-id"] = request_id
    return response
```

Do not change the shape of `list_request_logs()` or `list_agent_events()` in this slice.

- [ ] **Step 4: Add `/admin/services/restart` and keep it non-blocking**

Still in `llmnode/api/app.py`, add the new admin control route:

```python
@app.post("/admin/services/restart")
async def admin_restart_service(request: Request):
    _resolve_auth(request, "admin")
    request_id = _request_id(request)
    payload = await request.app.state.restart_agent_backend()
    response = JSONResponse(payload)
    response.headers["x-request-id"] = request_id
    return response
```

Rules for this step:
- do not wait for the backend to become `ready`
- do not add a task table or async job ID
- keep status observation on `/admin/status` and `/admin/stream`

### Task 2: Wire restart into the web console without changing the snapshot model

**Files:**
- Modify: `web-console/src/types.ts`
- Modify: `web-console/src/stores/overview.ts`
- Modify: `web-console/src/views/SystemStatusView.vue`
- Test later: `web-console/src/stores/overview.test.ts`

- [ ] **Step 1: Add a typed restart response in `types.ts`**

Append this interface to `web-console/src/types.ts` near the other admin response types:

```ts
export interface AdminServiceActionResponse {
  accepted: boolean
  service: string
  action: string
  agent_status: string
}
```

- [ ] **Step 2: Add `restartService()` to the overview store**

In `web-console/src/stores/overview.ts`, import the new response type and expose one minimal action:

```ts
import type {
  AdminApiKeyCreatePayload,
  AdminApiKeyCreateResponse,
  AdminApiKeyListResponse,
  AdminApiKeyUpdatePayload,
  AdminApiKeyUpdateResponse,
  AdminServiceActionResponse,
  AdminSnapshot,
  MetricPoint,
} from '@/types'
```

```ts
async function restartService() {
  return (await sendAdminJson('/admin/services/restart', 'POST', {})) as AdminServiceActionResponse
}
```

Add it to the returned store API:

```ts
return {
  apiBase,
  apiKey,
  backendStatus,
  error,
  history,
  lastUpdated,
  loading,
  recentErrors,
  requestCount,
  snapshot,
  streamConnected,
  applySnapshot,
  connectStream,
  disconnectStream,
  fetchApiKeys,
  fetchSnapshot,
  createApiKey,
  deleteApiKey,
  restartService,
  updateModelRoute,
  updateApiKey,
  updateSchedule,
}
```

- [ ] **Step 3: Add a restart button and inline error handling to `SystemStatusView.vue`**

Switch the script to use `ref` and add one action handler:

```ts
<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'

import { useOverviewStore } from '@/stores/overview'

const store = useOverviewStore()
const { snapshot } = storeToRefs(store)

const events = computed(() => snapshot.value?.events ?? [])
const runtime = computed(() => snapshot.value?.runtime ?? null)
const restarting = ref(false)
const restartError = ref('')

async function restartBackend() {
  restarting.value = true
  restartError.value = ''
  try {
    await store.restartService()
    await store.fetchSnapshot()
  } catch (err) {
    restartError.value = err instanceof Error ? err.message : String(err)
  } finally {
    restarting.value = false
  }
}
</script>
```

Update the status panel header block so the action sits beside the existing backend label:

```vue
<div class="status-panel__head">
  <div>
    <p class="table-card__eyebrow">系统状态</p>
    <h3>节点代理与恢复事件</h3>
  </div>
  <div class="filter-card__right">
    <span>backend: {{ snapshot?.backend_type ?? 'vllm' }}</span>
    <el-button :loading="restarting" type="warning" @click="restartBackend">
      重启后端
    </el-button>
  </div>
</div>
```

Then show restart failures without redesigning the page:

```vue
<div v-if="restartError" class="status-empty">{{ restartError }}</div>
```

Do not add new CSS unless the existing layout clearly breaks. Reuse `filter-card__right` and `status-empty`.

### Task 3: Sync `blueprintV2.md` to the real V2 completion state

**Files:**
- Modify: `docs/blueprintV2.md`
- Reference: `docs/superpowers/specs/2026-05-08-v2-completion-core-design.md`

- [ ] **Step 1: Rewrite the admin API status sections**

Replace the outdated `9.3 当前已实现` / `9.4 当前预留` split so it matches the code after Task 1:

```md
### 9.3 当前已实现
- `GET /admin/status`
- `GET /admin/stream`
- `GET /admin/request-logs`
- `GET /admin/logs`
- `GET /admin/events`
- `GET /admin/keys`
- `POST /admin/keys`
- `PATCH /admin/keys/{id}`
- `DELETE /admin/keys/{id}`
- `GET /admin/models`
- `PATCH /admin/models/{name}`
- `GET /admin/schedule`
- `PATCH /admin/schedule`
- `POST /admin/services/restart`
```

If you keep a “预留” subsection, it must only list interfaces that truly do not exist yet.

- [ ] **Step 2: Fix the “当前已落地 / 当前未完成” sections**

Update `14. 当前已落地` and `15. 当前未完成` so they reflect the completed API key work and this control-plane slice. Make sure the Markdown includes these truths:

```md
- 数据库 API Key 已支持 `GET /admin/keys`、`POST /admin/keys`、`PATCH /admin/keys/{id}`、`DELETE /admin/keys/{id}`。
- `web-console` 已完成总览页、使用记录页、模型路由页、调度页、系统状态页和 API Key 管理页的基础可用版本。
- `gateway-api` 已补齐 `GET /admin/logs`、`GET /admin/events`、`POST /admin/services/restart`，形成控制面闭环。
```

```md
- `storage` 从 SQLite 向 PostgreSQL 的正式迁移。
- `gateway-api` 的更严格审计字段与请求画像。
- Prometheus 指标导出与告警闭环。
- `node-agent` 更细粒度恢复编排和人工确认机制。
```

Remove the stale line that says the API Key page still lacks filters and search.

- [ ] **Step 3: Tighten the acceptance wording**

Update the V2 acceptance bullets so they explicitly describe the current semantics:

```md
- `GET /admin/logs` 当前返回请求审计日志，V2 阶段与 `GET /admin/request-logs` 保持等价。
- 管理控制台只通过 `gateway-api` 即可查看状态、请求日志、节点事件并发起 restart。
- `POST /admin/services/restart` 返回命令受理结果，后续恢复过程通过状态快照和 SSE 观察。
```

Do not add PostgreSQL, Prometheus, or V3 bullets into this acceptance section.

### Task 4: Add verification coverage and run the final checks

**Files:**
- Modify: `tests/test_smoke.py`
- Create: `tests/test_admin_control_plane.py`
- Modify: `web-console/src/stores/overview.test.ts`

- [ ] **Step 1: Add a smoke test for the new gateway config default**

Extend `tests/test_smoke.py` with a dedicated assertion for the new control URL:

```python
def test_settings_loads_agent_control_defaults():
    settings = load_settings()
    assert settings.gateway.agent_base_url == "http://127.0.0.1:4010"
    assert settings.gateway.agent_status_url == "http://127.0.0.1:4010/state"
```

- [ ] **Step 2: Add backend admin control-plane endpoint coverage**

Create `tests/test_admin_control_plane.py` with focused coverage for events, logs, restart success, and restart failure:

```python
import asyncio
from unittest.mock import patch

import httpx

from llmnode.api.app import create_app
from llmnode.storage.db import write_agent_event


class FakeRestartClient:
    def __init__(self, response: httpx.Response | None = None, error: Exception | None = None):
        self._response = response
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url: str):
        if self._error is not None:
            raise self._error
        return self._response
```

```python
def test_admin_events_endpoint_returns_rows():
    async def run():
        app = create_app()
        write_agent_event(app.state.db, "ready", "backend healthy")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/admin/events", headers={"Authorization": "Bearer dev-key"})
            assert resp.status_code == 200
            assert resp.json()["events"][0]["status"] == "ready"

    asyncio.run(run())
```

```python
def test_admin_logs_alias_matches_request_logs():
    async def run():
        app = create_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer dev-key"},
                json={
                    "model": "claude-sonnet-4-5-20250929",
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            logs_resp = await client.get("/admin/logs", headers={"Authorization": "Bearer dev-key"})
            request_logs_resp = await client.get("/admin/request-logs", headers={"Authorization": "Bearer dev-key"})
            assert logs_resp.status_code == 200
            assert logs_resp.json()["logs"] == request_logs_resp.json()["logs"]

    asyncio.run(run())
```

```python
def test_admin_restart_service_returns_accepted_payload():
    async def run():
        app = create_app()
        response = httpx.Response(200, json={"status": "recovering"})
        transport = httpx.ASGITransport(app=app)
        with patch("llmnode.api.app.httpx.AsyncClient", return_value=FakeRestartClient(response=response)):
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.post("/admin/services/restart", headers={"Authorization": "Bearer dev-key"})
                assert resp.status_code == 200
                assert resp.json()["accepted"] is True
                assert resp.json()["agent_status"] == "recovering"

    asyncio.run(run())
```

```python
def test_admin_restart_service_returns_503_when_agent_is_unreachable():
    async def run():
        app = create_app()
        error = httpx.ConnectError("boom")
        transport = httpx.ASGITransport(app=app)
        with patch("llmnode.api.app.httpx.AsyncClient", return_value=FakeRestartClient(error=error)):
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.post("/admin/services/restart", headers={"Authorization": "Bearer dev-key"})
                assert resp.status_code == 503
                assert resp.json()["detail"] == "agent control unavailable"

    asyncio.run(run())
```

- [ ] **Step 3: Add frontend store coverage for restart dispatch**

Extend `web-console/src/stores/overview.test.ts` with one new case:

```ts
it('sends restart command to the admin services endpoint', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      accepted: true,
      service: 'backend',
      action: 'restart',
      agent_status: 'recovering',
    }),
  })
  vi.stubGlobal('fetch', fetchMock)

  const store = useOverviewStore()
  const result = await store.restartService()

  expect(fetchMock).toHaveBeenCalledWith('/admin/services/restart', {
    method: 'POST',
    headers: {
      Authorization: 'Bearer dev-key',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({}),
  })
  expect(result.accepted).toBe(true)
  expect(result.agent_status).toBe('recovering')
})
```

- [ ] **Step 4: Run the final backend and frontend verification block**

Run the backend tests from `/proj02/liuheshan/llmnode` using the required Python environment:

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m pytest -q
```

Expected:
- all Python tests pass
- the total passes increase above the previously verified `44 passed`

Run the frontend unit tests from `/proj02/liuheshan/llmnode/web-console`:

```bash
npm run test
```

Expected:
- Vitest passes
- the new `restartService` store test is included

Run the frontend production build from `/proj02/liuheshan/llmnode/web-console`:

```bash
npm run build
```

Expected:
- Vite build succeeds
- the existing chunk-size warning may still appear, but there should be no new type or compile errors

## Self-Review Checklist

- Spec coverage:
  - Task 1 covers `GET /admin/events`, `GET /admin/logs`, `POST /admin/services/restart`
  - Task 2 covers the web console restart entry point
  - Task 3 covers `blueprintV2.md` sync
  - Task 4 covers backend tests, frontend tests, and final verification
- Placeholder scan:
  - no `TODO`, `TBD`, or “fill this in later” text should remain in the implementation edits
- Consistency:
  - use `agent_base_url` consistently for control actions
  - keep `agent_status_url` only for readiness/status fetches
  - keep `/admin/logs` and `/admin/request-logs` response shapes identical in this slice
