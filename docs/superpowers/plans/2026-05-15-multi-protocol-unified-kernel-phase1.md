# Multi-Protocol Unified Kernel Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 升级模型路由语义并把 `/v1/responses` 重构为按模型选择 native responses 或 responses-to-chat 的双路径执行链，同时保持现有 `/v1/chat/completions` 与 `/v1/messages` 主链路不回归。

**Architecture:** 第一阶段不重写整套控制面，而是在现有网关中新增 route 语义、capability guard、统一请求结果对象和两个最小 adapter。`/v1/responses` 先接入新执行链，OpenAI 官方模型走 native responses，上游 chat-native 的本地 Qwen 走 responses-to-chat 适配，并用扩展后的 `response_states` 支持 native/local 两种 `previous_response_id` 续接。

**Tech Stack:** Python 3.11, FastAPI, httpx, SQLite, pytest, existing llmnode gateway modules

---

## File Map

**Create:**
- `llmnode/proxy/executor.py`
- `llmnode/proxy/adapters/__init__.py`
- `llmnode/proxy/adapters/native_responses.py`
- `llmnode/proxy/adapters/responses_to_chat.py`
- `tests/test_model_routes_phase1.py`
- `tests/test_api_responses_native.py`
- `docs/superpowers/plans/2026-05-15-multi-protocol-unified-kernel-phase1.md`

**Modify:**
- `llmnode/models.py`
- `llmnode/storage/db.py`
- `llmnode/proxy/backend.py`
- `llmnode/proxy/router.py`
- `llmnode/api/app.py`
- `llmnode/protocols/openai_responses.py`
- `tests/test_api_responses.py`
- `docs/contracts/backend-routing.md`
- `docs/blueprint/current.md`
- `README.md`

**Do Not Modify In Phase 1:**
- `llmnode/agent/backend.py`
- `llmnode/agent/service.py`
- `llmnode/control.py`

---

### Task 1: Extend Route Contract and Persistence

**Files:**
- Modify: `llmnode/models.py`
- Modify: `llmnode/storage/db.py`
- Modify: `docs/contracts/backend-routing.md`
- Test: `tests/test_model_routes_phase1.py`

- [ ] **Step 1: Write the failing route contract tests**

```python
from pathlib import Path

from llmnode.models import ModelRoute
from llmnode.storage.db import init_db, list_model_routes, upsert_model_route


def test_model_route_supports_upstream_protocol_fields(tmp_path: Path):
    conn = init_db(tmp_path / "gateway.db")
    upsert_model_route(
        conn,
        {
            "name": "gpt-4o",
            "display_name": "GPT-4o",
            "enabled": True,
            "lifecycle_mode": "external",
            "backend_type": None,
            "backend_model": None,
            "upstream_protocol": "responses",
            "upstream_base_url": "https://api.openai.com/v1",
            "upstream_model": "gpt-4o",
            "upstream_auth_kind": "bearer",
            "upstream_auth_ref": "openai-prod",
            "capabilities_json": {
                "supports_responses": True,
                "supports_chat": True,
                "supports_messages": False,
                "supports_stream": True,
                "supports_function_tools": True,
                "supports_builtin_tools": True,
                "supports_previous_response_id_native": True,
                "supports_json_schema": True,
            },
        },
    )
    row = list_model_routes(conn)[0]
    assert row["lifecycle_mode"] == "external"
    assert row["upstream_protocol"] == "responses"
    assert row["upstream_auth_kind"] == "bearer"
    assert row["capabilities_json"]["supports_previous_response_id_native"] is True


def test_model_route_defaults_keep_managed_local_chat_shape():
    route = ModelRoute(
        name="qwen36-27b-fp8",
        display_name="Qwen 27B FP8",
        backend_model="qwen36-27b-fp8",
    )
    assert route.lifecycle_mode == "managed_local"
    assert route.upstream_protocol == "chat"
    assert route.upstream_model == "qwen36-27b-fp8"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_model_routes_phase1.py -v`
Expected: FAIL because `ModelRoute` and `model_routes` persistence do not yet expose `lifecycle_mode`, `upstream_protocol`, `upstream_auth_kind`, or `capabilities_json`.

- [ ] **Step 3: Write minimal implementation in `llmnode/models.py`**

```python
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class ModelCapabilities:
    supports_responses: bool = False
    supports_chat: bool = True
    supports_messages: bool = False
    supports_stream: bool = True
    supports_function_tools: bool = True
    supports_builtin_tools: bool = False
    supports_previous_response_id_native: bool = False
    supports_json_schema: bool = False


@dataclass(frozen=True)
class ModelRoute:
    name: str
    display_name: str
    backend_model: str | None = None
    backend_type: str | None = "vllm"
    enabled: bool = True
    lifecycle_mode: str = "managed_local"
    upstream_protocol: str = "chat"
    upstream_base_url: str | None = None
    upstream_model: str | None = None
    upstream_auth_kind: str = "none"
    upstream_auth_ref: str | None = None
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)

    def resolved_upstream_model(self) -> str | None:
        return self.upstream_model or self.backend_model
```

- [ ] **Step 4: Write minimal persistence changes in `llmnode/storage/db.py`**

```python
_ensure_columns(
    conn,
    "model_routes",
    {
        "lifecycle_mode": "TEXT NOT NULL DEFAULT 'managed_local'",
        "upstream_protocol": "TEXT NOT NULL DEFAULT 'chat'",
        "upstream_base_url": "TEXT",
        "upstream_model": "TEXT",
        "upstream_auth_kind": "TEXT NOT NULL DEFAULT 'none'",
        "upstream_auth_ref": "TEXT",
        "capabilities_json": "TEXT NOT NULL DEFAULT '{}'",
    },
)
```

```python
def _decode_model_route_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "name": row[0],
        "display_name": row[1],
        "backend_model": row[2],
        "backend_type": row[3],
        "enabled": bool(row[4]),
        "lifecycle_mode": row[5],
        "upstream_protocol": row[6],
        "upstream_base_url": row[7],
        "upstream_model": row[8],
        "upstream_auth_kind": row[9],
        "upstream_auth_ref": row[10],
        "capabilities_json": json.loads(row[11]) if row[11] else {},
    }
```

- [ ] **Step 5: Update admin/read path and contract doc**

```md
- `backend_type`
  - 只描述本地受控推理后端类型
- `upstream_protocol`
  - 描述实际对上游发请求所用协议
- `lifecycle_mode`
  - 描述该 route 是本地受控还是外部上游
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_model_routes_phase1.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add tests/test_model_routes_phase1.py llmnode/models.py llmnode/storage/db.py docs/contracts/backend-routing.md
git commit -m "feat: 扩展模型路由协议语义"
```

---

### Task 2: Add Unified Executor Types and Capability Guard

**Files:**
- Create: `llmnode/proxy/executor.py`
- Modify: `llmnode/proxy/router.py`
- Test: `tests/test_model_routes_phase1.py`

- [ ] **Step 1: Write the failing executor tests**

```python
from llmnode.models import ModelCapabilities, ModelRoute
from llmnode.proxy.executor import NormalizedRequest
from llmnode.proxy.router import ensure_route_supports_request, select_upstream_adapter


def test_chat_native_route_selects_responses_to_chat_adapter():
    route = ModelRoute(
        name="qwen36-27b-fp8",
        display_name="Qwen",
        backend_model="qwen36-27b-fp8",
        upstream_protocol="chat",
        capabilities=ModelCapabilities(
            supports_responses=False,
            supports_chat=True,
            supports_stream=True,
            supports_function_tools=True,
        ),
    )
    req = NormalizedRequest(client_protocol="responses", model="qwen36-27b-fp8", messages=[])
    assert select_upstream_adapter(route, req) == "responses_to_chat"


def test_chat_native_route_rejects_builtin_tools():
    route = ModelRoute(
        name="qwen36-27b-fp8",
        display_name="Qwen",
        backend_model="qwen36-27b-fp8",
        upstream_protocol="chat",
        capabilities=ModelCapabilities(
            supports_builtin_tools=False,
            supports_function_tools=True,
        ),
    )
    req = NormalizedRequest(
        client_protocol="responses",
        model="qwen36-27b-fp8",
        messages=[],
        tools=[{"type": "web_search"}],
    )
    ensure_route_supports_request(route, req)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_model_routes_phase1.py -v`
Expected: FAIL because `NormalizedRequest`, `ensure_route_supports_request`, and `select_upstream_adapter` do not yet exist.

- [ ] **Step 3: Write minimal executor types**

```python
from dataclasses import dataclass
from typing import Any


@dataclass
class NormalizedRequest:
    client_protocol: str
    model: str
    messages: list[dict[str, Any]]
    system_prompt: Any | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any = None
    stream: bool = False
    max_output_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    response_format: dict[str, Any] | None = None
    previous_response_id: str | None = None
    raw_request: dict[str, Any] | None = None
```

- [ ] **Step 4: Write minimal route guard and adapter selection**

```python
def ensure_route_supports_request(route: ModelRoute, req: NormalizedRequest) -> None:
    if req.stream and not route.capabilities.supports_stream:
        raise HTTPException(status_code=400, detail="stream_not_supported_for_model")
    for tool in req.tools or []:
        if tool.get("type") != "function" and not route.capabilities.supports_builtin_tools:
            raise HTTPException(status_code=400, detail="unsupported_builtin_tools")
        if tool.get("type") == "function" and not route.capabilities.supports_function_tools:
            raise HTTPException(status_code=400, detail="unsupported_function_tools")


def select_upstream_adapter(route: ModelRoute, req: NormalizedRequest) -> str:
    if route.upstream_protocol == "responses":
        return "native_responses"
    if route.upstream_protocol == "chat" and req.client_protocol == "responses":
        return "responses_to_chat"
    raise HTTPException(status_code=400, detail="unsupported_route_protocol_combination")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_model_routes_phase1.py -v`
Expected: PASS, with builtin tool rejection asserting `HTTPException.detail == "unsupported_builtin_tools"`

- [ ] **Step 6: Commit**

```bash
git add tests/test_model_routes_phase1.py llmnode/proxy/executor.py llmnode/proxy/router.py
git commit -m "feat: 增加统一执行器与能力守卫"
```

---

### Task 3: Add Per-Route Backend Calls and Native Responses Adapter

**Files:**
- Modify: `llmnode/proxy/backend.py`
- Create: `llmnode/proxy/adapters/__init__.py`
- Create: `llmnode/proxy/adapters/native_responses.py`
- Create: `tests/test_api_responses_native.py`

- [ ] **Step 1: Write the failing native responses tests**

```python
import asyncio
import httpx

from llmnode.api.app import create_app
from llmnode.security import hash_api_key
from llmnode.storage.db import create_api_key, upsert_model_route


def test_native_responses_route_posts_to_upstream_responses():
    async def run():
        app = create_app()
        calls = []

        async def fake_post_json_to(base_url, path, payload, headers=None):
            calls.append((base_url, path, payload, headers))
            return {
                "id": "resp_upstream_1",
                "object": "response",
                "status": "completed",
                "model": payload["model"],
                "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "ok"}]}],
                "usage": {"input_tokens": 3, "output_tokens": 5, "total_tokens": 8},
            }

        app.state.post_json_to = fake_post_json_to
        upsert_model_route(
            app.state.db,
            {
                "name": "gpt-4o",
                "display_name": "GPT-4o",
                "enabled": True,
                "lifecycle_mode": "external",
                "backend_type": None,
                "backend_model": None,
                "upstream_protocol": "responses",
                "upstream_base_url": "https://api.openai.com/v1",
                "upstream_model": "gpt-4o",
                "upstream_auth_kind": "bearer",
                "upstream_auth_ref": "openai-prod",
                "capabilities_json": {"supports_responses": True, "supports_stream": True, "supports_previous_response_id_native": True},
            },
        )
        create_api_key(app.state.db, name="resp-native", key_hash=hash_api_key("sk-native"), scopes=["inference"])
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/responses",
                headers={"Authorization": "Bearer sk-native"},
                json={"model": "gpt-4o", "input": "hello"},
            )
            assert resp.status_code == 200
            assert calls[0][1] == "/v1/responses"

    asyncio.run(run())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_responses_native.py -v`
Expected: FAIL because the app does not yet support route-specific `/v1/responses` upstream calls.

- [ ] **Step 3: Add per-route backend helpers**

```python
async def post_json_to(base_url: str, path: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=base_url, timeout=300) as client:
        response = await client.post(path, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()


async def stream_bytes_from(base_url: str, path: str, payload: dict[str, Any], headers: dict[str, str] | None = None):
    async with httpx.AsyncClient(base_url=base_url, timeout=None) as client:
        async with client.stream("POST", path, json=payload, headers=headers) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                if chunk:
                    yield chunk
```

- [ ] **Step 4: Add native responses adapter**

```python
async def execute_native_responses(route: ModelRoute, req: NormalizedRequest, post_json_to, headers: dict[str, str]) -> dict[str, Any]:
    payload = dict(req.raw_request or {})
    payload["model"] = route.resolved_upstream_model()
    return await post_json_to(route.upstream_base_url, "/v1/responses", payload, headers=headers)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_api_responses_native.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_api_responses_native.py llmnode/proxy/backend.py llmnode/proxy/adapters/__init__.py llmnode/proxy/adapters/native_responses.py
git commit -m "feat: 增加原生 responses 上游适配"
```

---

### Task 4: Upgrade Response State for Native and Local Continuation

**Files:**
- Modify: `llmnode/storage/db.py`
- Modify: `tests/test_storage_responses.py`

- [ ] **Step 1: Write the failing response state tests**

```python
from pathlib import Path

from llmnode.storage.db import get_response_state, init_db, upsert_response_state


def test_response_state_persists_native_and_local_continuation_fields(tmp_path: Path):
    conn = init_db(tmp_path / "gateway.db")
    upsert_response_state(
        conn,
        response_id="resp_1",
        request_id="req_1",
        model_name="gpt-4o",
        input_items=[{"role": "user", "content": "hello"}],
        output_items=[{"type": "message", "role": "assistant"}],
        messages=[{"role": "user", "content": "hello"}],
        parent_response_id="resp_0",
        route_name="gpt-4o",
        client_protocol="responses",
        upstream_protocol="responses",
        upstream_response_id="resp_upstream_1",
        request_payload={"model": "gpt-4o", "input": "hello"},
        output_payload={"id": "resp_1"},
    )
    row = get_response_state(conn, "resp_1")
    assert row["parent_response_id"] == "resp_0"
    assert row["route_name"] == "gpt-4o"
    assert row["upstream_response_id"] == "resp_upstream_1"
    assert row["request_payload"]["model"] == "gpt-4o"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_storage_responses.py -v`
Expected: FAIL because the new response state fields are missing.

- [ ] **Step 3: Extend the schema and helper signatures**

```python
_ensure_columns(
    conn,
    "response_states",
    {
        "parent_response_id": "TEXT",
        "route_name": "TEXT",
        "client_protocol": "TEXT",
        "upstream_protocol": "TEXT",
        "upstream_response_id": "TEXT",
        "request_json": "TEXT",
        "output_json": "TEXT",
    },
)
```

- [ ] **Step 4: Update read/write helpers**

```python
def upsert_response_state(
    conn,
    *,
    response_id: str,
    request_id: str,
    model_name: str,
    input_items: list[dict[str, Any]],
    output_items: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    parent_response_id: str | None = None,
    route_name: str | None = None,
    client_protocol: str | None = None,
    upstream_protocol: str | None = None,
    upstream_response_id: str | None = None,
    request_payload: dict[str, Any] | None = None,
    output_payload: dict[str, Any] | None = None,
) -> None:
    ...
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_storage_responses.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_storage_responses.py llmnode/storage/db.py
git commit -m "feat: 扩展 responses 会话状态存储"
```

---

### Task 5: Refactor `/v1/responses` Into Native and Chat Adapters

**Files:**
- Modify: `llmnode/api/app.py`
- Modify: `llmnode/protocols/openai_responses.py`
- Create: `llmnode/proxy/adapters/responses_to_chat.py`
- Modify: `tests/test_api_responses.py`
- Modify: `tests/test_api_responses_native.py`

- [ ] **Step 1: Write the failing API behavior tests**

```python
def test_native_route_uses_upstream_previous_response_id():
    ...
    assert calls[-1][2]["previous_response_id"] == "resp_upstream_1"


def test_chat_route_rejects_builtin_tools():
    ...
    assert resp.status_code == 400
    assert resp.json()["detail"] == "unsupported_builtin_tools"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_responses.py tests/test_api_responses_native.py -v`
Expected: FAIL because `/v1/responses` still assumes one execution path.

- [ ] **Step 3: Add request normalization helpers**

```python
def _normalize_responses_request(raw: dict[str, Any]) -> NormalizedRequest:
    payload = OpenAIResponsesRequest.model_validate(raw)
    return NormalizedRequest(
        client_protocol="responses",
        model=payload.model,
        messages=payload.to_chat_messages(),
        tools=payload.tools,
        tool_choice=payload.tool_choice,
        stream=payload.stream,
        max_output_tokens=payload.max_output_tokens,
        temperature=payload.temperature,
        top_p=payload.top_p,
        response_format=payload.output_format,
        previous_response_id=payload.previous_response_id,
        raw_request=raw,
    )
```

- [ ] **Step 4: Add route-aware `/v1/responses` execution**

```python
route = resolve_route(normalized.model, request.app.state.ctx.models)
ensure_route_supports_request(route, normalized)
adapter = select_upstream_adapter(route, normalized)
if adapter == "native_responses":
    result = await execute_native_responses(...)
else:
    result = await execute_responses_to_chat(...)
```

- [ ] **Step 5: Add native/local continuation split**

```python
if route.capabilities.supports_previous_response_id_native and normalized.previous_response_id:
    previous_state = get_response_state(...)
    raw["previous_response_id"] = previous_state["upstream_response_id"]
elif normalized.previous_response_id:
    previous_state = get_response_state(...)
    previous_messages = list(previous_state["messages"])
```

- [ ] **Step 6: Add `responses_to_chat` adapter**

```python
async def execute_responses_to_chat(route, req, previous_messages, ctx):
    chat_payload = build_chat_payload(route, req, previous_messages)
    result = await proxy_openai_chat(chat_payload, ctx)
    return result
```

- [ ] **Step 7: Run focused tests to verify they pass**

Run: `pytest tests/test_api_responses.py tests/test_api_responses_native.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add tests/test_api_responses.py tests/test_api_responses_native.py llmnode/api/app.py llmnode/protocols/openai_responses.py llmnode/proxy/adapters/responses_to_chat.py
git commit -m "feat: 重构 responses 为双路径执行链"
```

---

### Task 6: Add Streaming and Metrics Coverage for the Two Responses Paths

**Files:**
- Modify: `tests/test_api_responses.py`
- Modify: `tests/test_api_metrics.py`
- Modify: `llmnode/api/app.py`

- [ ] **Step 1: Write the failing stream and metrics tests**

```python
def test_native_responses_stream_keeps_event_framing():
    ...
    assert "event: response.output_text.delta" in body


def test_native_responses_metric_uses_protocol_responses():
    ...
    assert metric_row == ("responses", "ok")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_responses.py tests/test_api_metrics.py -v`
Expected: FAIL because the native path stream wrapping and metrics persistence are not fully covered.

- [ ] **Step 3: Write minimal stream/metrics integration changes**

```python
write_request_log(..., "responses", ...)
_record_request_metric(..., protocol="responses", ...)
```

```python
yield _format_sse_event("response.created", {...})
yield _format_sse_event("response.output_text.delta", {...})
yield _format_sse_event("response.completed", {...})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api_responses.py tests/test_api_metrics.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_api_responses.py tests/test_api_metrics.py llmnode/api/app.py
git commit -m "test: 补齐 responses 双路径流式与指标覆盖"
```

---

### Task 7: Documentation Backflow for Phase 1

**Files:**
- Modify: `README.md`
- Modify: `docs/blueprint/current.md`
- Modify: `docs/contracts/backend-routing.md`

- [ ] **Step 1: Write the doc updates**

```md
- `POST /v1/responses`
```

```md
- 当前 `/v1/responses` 已按模型 route 支持两类路径：
  - native responses upstream
  - responses-to-chat adapter
```

```md
- `backend_type` 只描述本地受控后端类型
- `upstream_protocol` 描述真正对上游发请求所用协议
```

- [ ] **Step 2: Run structure checks**

Run: `rg -n "/v1/responses|upstream_protocol|lifecycle_mode" README.md docs/blueprint/current.md docs/contracts/backend-routing.md`
Expected: matching lines in all three files

- [ ] **Step 3: Commit**

```bash
git add README.md docs/blueprint/current.md docs/contracts/backend-routing.md
git commit -m "docs: 回流多协议统一内核一期边界"
```

---

### Task 8: Final Verification

**Files:**
- Test: `tests/test_model_routes_phase1.py`
- Test: `tests/test_storage_responses.py`
- Test: `tests/test_api_responses.py`
- Test: `tests/test_api_responses_native.py`
- Test: `tests/test_api_openai.py`
- Test: `tests/test_api_metrics.py`

- [ ] **Step 1: Run focused route and state tests**

Run: `pytest tests/test_model_routes_phase1.py tests/test_storage_responses.py -v`
Expected: PASS

- [ ] **Step 2: Run responses protocol tests**

Run: `pytest tests/test_api_responses.py tests/test_api_responses_native.py -v`
Expected: PASS

- [ ] **Step 3: Run regression tests for existing gateway behavior**

Run: `pytest tests/test_api_openai.py tests/test_api_metrics.py -v`
Expected: PASS

- [ ] **Step 4: Run full phase 1 verification batch**

Run: `pytest tests/test_model_routes_phase1.py tests/test_storage_responses.py tests/test_api_responses.py tests/test_api_responses_native.py tests/test_api_openai.py tests/test_api_metrics.py -q`
Expected: all tests pass, no failures

- [ ] **Step 5: Final commit for any verification-driven fixes**

```bash
git add tests/test_model_routes_phase1.py tests/test_storage_responses.py tests/test_api_responses.py tests/test_api_responses_native.py tests/test_api_openai.py tests/test_api_metrics.py llmnode/models.py llmnode/storage/db.py llmnode/proxy/backend.py llmnode/proxy/router.py llmnode/proxy/executor.py llmnode/proxy/adapters/__init__.py llmnode/proxy/adapters/native_responses.py llmnode/proxy/adapters/responses_to_chat.py llmnode/api/app.py llmnode/protocols/openai_responses.py README.md docs/blueprint/current.md docs/contracts/backend-routing.md
git commit -m "feat: 完成多协议统一内核一期"
```
