# Readiness Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `llmnode` 能准确表达后端热身窗口，向客户端返回标准 `503 + Retry-After`，并把 `http_ready / inference_ready` 区分为正式状态语义。

**Architecture:** 由 `node-agent` 成为 readiness 状态的最终裁决者，负责 HTTP 健康与极小推理探针；`gateway-api` 只消费 agent 状态并向客户端输出标准错误语义；SQLite 记录结构化状态事件供管理台和排障使用。

**Tech Stack:** FastAPI, httpx, SQLite, pytest

---

### Task 1: 扩展 AgentState 与事件模型

**Files:**
- Modify: `llmnode/agent/state.py`
- Modify: `llmnode/storage/db.py`
- Test: `tests/test_agent.py`

- [ ] **Step 1: 先写失败测试，描述新的 state 形状**

```python
def test_agent_state_exposes_readiness_flags():
    state = AgentState()
    assert state.status == "stopped"
    assert state.http_ready is False
    assert state.inference_ready is False
    assert state.retry_after_seconds is None
```

- [ ] **Step 2: 运行测试确认当前失败**

Run: `pytest tests/test_agent.py -k readiness_flags -v`
Expected: FAIL，提示 `AgentState` 缺少 `http_ready`、`inference_ready` 或 `retry_after_seconds`

- [ ] **Step 3: 扩展 AgentState 与 agent_events 字段**

```python
@dataclass
class AgentState:
    status: str = "stopped"
    desired_state: str = "running"
    backend_ready: bool = False
    http_ready: bool = False
    inference_ready: bool = False
    retry_after_seconds: int | None = None
    last_transition_at: str = ""
    last_probe_error: str = ""
    last_probe_latency_ms: float | None = None
```

```python
_ensure_columns(
    conn,
    "agent_events",
    {
        "event_type": "TEXT",
        "readiness_state": "TEXT",
        "http_ready": "INTEGER",
        "inference_ready": "INTEGER",
        "metadata_json": "TEXT",
    },
)
```

- [ ] **Step 4: 扩展 `write_agent_event()` 和 `list_agent_events()` 返回结构**

```python
def write_agent_event(
    conn: sqlite3.Connection,
    status: str,
    reason: str | None = None,
    *,
    event_type: str | None = None,
    readiness_state: str | None = None,
    http_ready: bool | None = None,
    inference_ready: bool | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO agent_events(
            status, reason, event_type, readiness_state, http_ready, inference_ready, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            status,
            reason,
            event_type or status,
            readiness_state or status,
            None if http_ready is None else int(http_ready),
            None if inference_ready is None else int(inference_ready),
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )
    conn.commit()
```

- [ ] **Step 5: 运行相关测试**

Run: `pytest tests/test_agent.py -v`
Expected: PASS，且现有 agent 测试没有因状态结构扩展而退化

- [ ] **Step 6: Commit**

```bash
git add llmnode/agent/state.py llmnode/storage/db.py tests/test_agent.py
git commit -m "feat: extend agent readiness state model"
```

### Task 2: 在 agent 中引入 HTTP-ready 与 inference-ready 双阶段判定

**Files:**
- Modify: `llmnode/agent/service.py`
- Modify: `llmnode/proxy/vllm_client.py`
- Test: `tests/test_agent.py`

- [ ] **Step 1: 先写失败测试，覆盖 warming_up 到 ready 的状态跃迁**

```python
async def fake_health(_):
    return True

async def fake_probe(*_args, **_kwargs):
    return {"ok": True, "latency_ms": 12.5}

resp = await client.get("/state")
assert resp.json()["status"] == "ready"
assert resp.json()["http_ready"] is True
assert resp.json()["inference_ready"] is True
```

- [ ] **Step 2: 先写一个“HTTP 通了但推理未就绪”的失败测试**

```python
async def fake_health(_):
    return True

async def fake_probe(*_args, **_kwargs):
    raise RuntimeError("stream not ready")

payload = (await client.get("/state")).json()
assert payload["status"] == "warming_up"
assert payload["http_ready"] is True
assert payload["inference_ready"] is False
```

- [ ] **Step 3: 在 `service.py` 增加极小推理探针**

```python
async def _probe_inference() -> tuple[bool, float | None, str | None]:
    started = datetime.now(timezone.utc)
    try:
        await app.state.backend_driver.probe(app.state.backend_url)
        latency_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
        return True, latency_ms, None
    except Exception as exc:
        latency_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
        return False, latency_ms, str(exc)
```

```python
if http_ready and not inference_ready:
    app.state.agent.mark("warming_up", "backend http ready, inference probe pending")
```

- [ ] **Step 4: 给 backend client 或 driver 增加标准探针入口**

```python
def build_messages_request(model: str, prompt: str) -> dict:
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1,
        "stream": False,
    }
```

- [ ] **Step 5: 调整 `/state` 返回字段**

```python
return {
    "status": app.state.agent.status,
    "http_ready": app.state.agent.http_ready,
    "inference_ready": app.state.agent.inference_ready,
    "retry_after_seconds": app.state.agent.retry_after_seconds,
    "last_probe_error": app.state.agent.last_probe_error,
    "last_probe_latency_ms": app.state.agent.last_probe_latency_ms,
}
```

- [ ] **Step 6: 运行测试**

Run: `pytest tests/test_agent.py -v`
Expected: PASS，新增 warming_up / ready 测试通过

- [ ] **Step 7: Commit**

```bash
git add llmnode/agent/service.py llmnode/proxy/vllm_client.py tests/test_agent.py
git commit -m "feat: add dual-stage readiness probing"
```

### Task 3: 让 gateway 输出标准 503、Retry-After 与 detail 枚举

**Files:**
- Modify: `llmnode/api/app.py`
- Modify: `llmnode/proxy/router.py`
- Test: `tests/test_api_openai.py`
- Test: `tests/test_api_anthropic.py`

- [ ] **Step 1: 先写失败测试，覆盖 agent warming_up 时的错误语义**

```python
async def fake_agent_state():
    return {
        "status": "warming_up",
        "http_ready": True,
        "inference_ready": False,
        "retry_after_seconds": 5,
    }

resp = await client.post(
    "/v1/chat/completions",
    headers={"Authorization": "Bearer dev-key"},
    json={
        "model": "qwen36-35b-a3b-fp8",
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 16,
    },
)
assert resp.status_code == 503
assert resp.headers["Retry-After"] == "5"
assert resp.json()["detail"] == "backend_warming_up"
```

- [ ] **Step 2: 再补一个 Anthropic 流式路径失败测试**

```python
resp = await client.post(
    "/v1/messages",
    headers={"Authorization": "Bearer dev-key"},
    json={
        "model": "qwen36-35b-a3b-fp8",
        "max_tokens": 16,
        "stream": True,
        "messages": [{"role": "user", "content": "hello"}],
    },
)
assert resp.status_code == 503
assert resp.json()["detail"] in {"backend_warming_up", "backend_not_stream_ready"}
```

- [ ] **Step 3: 把 `ensure_agent_ready()` 改成返回结构化 readiness 上下文**

```python
async def ensure_agent_ready() -> dict[str, Any]:
    state = await app.state.fetch_agent_state()
    if not state:
        raise HTTPException(status_code=503, detail="agent state unavailable")
    if state.get("inference_ready") is False:
        retry_after = str(state.get("retry_after_seconds") or 5)
        detail = "backend_warming_up" if state.get("http_ready") else "backend_not_stream_ready"
        raise HTTPException(status_code=503, detail=detail, headers={"Retry-After": retry_after})
    return state
```

- [ ] **Step 4: 删除 router 中重复且过粗的 `backend_client.health()` ready 闸门**

```python
async def proxy_openai_chat(payload: Dict[str, Any], ctx: GatewayContext) -> Dict[str, Any]:
    resolve_route(payload["model"], ctx.models)
    return await ctx.backend_client.post_json("/v1/chat/completions", payload)
```

- [ ] **Step 5: 运行网关 API 测试**

Run: `pytest tests/test_api_openai.py tests/test_api_anthropic.py -v`
Expected: PASS，且旧的正常转发测试不回归

- [ ] **Step 6: Commit**

```bash
git add llmnode/api/app.py llmnode/proxy/router.py tests/test_api_openai.py tests/test_api_anthropic.py
git commit -m "feat: return structured readiness retry signals"
```

### Task 4: 扩展 diagnostics 与管理台快照，回流状态事件

**Files:**
- Modify: `llmnode/agent/service.py`
- Modify: `llmnode/api/app.py`
- Modify: `tests/test_agent.py`
- Modify: `tests/test_api_openai.py`
- Modify: `docs/contracts/control-plane.md`
- Modify: `docs/process/run.md`

- [ ] **Step 1: 先写失败测试，要求 diagnostics/status 含新字段**

```python
resp = await client.get("/admin/diagnostics/status")
payload = resp.json()
assert "http_ready" in payload
assert "inference_ready" in payload
assert "retry_after_seconds" in payload
```

- [ ] **Step 2: 在 agent diagnostics 响应里补充 readiness 字段**

```python
return {
    "backend_type": app.state.backend_type,
    "readiness_state": app.state.agent.status,
    "http_ready": app.state.agent.http_ready,
    "inference_ready": app.state.agent.inference_ready,
    "retry_after_seconds": app.state.agent.retry_after_seconds,
    "last_transition_at": app.state.agent.last_transition_at,
    "last_probe_error": app.state.agent.last_probe_error,
    "last_probe_latency_ms": app.state.agent.last_probe_latency_ms,
    "gpu": gpu_payload,
    "container": container_payload,
    "model": model_payload,
}
```

- [ ] **Step 3: 在 admin snapshot 中透传 agent readiness 与最近事件**

```python
"agent_state": {
    "status": state.get("status"),
    "http_ready": state.get("http_ready"),
    "inference_ready": state.get("inference_ready"),
    "retry_after_seconds": state.get("retry_after_seconds"),
},
```

- [ ] **Step 4: 更新正式文档，写清三层 ready 判断和 503 语义**

```md
- `http_ready=true` 但 `inference_ready=false` 表示后端仍在热身
- 对外业务请求应返回 `503 Service Unavailable`
- 应带 `Retry-After`
```

- [ ] **Step 5: 运行验证**

Run: `pytest tests/test_agent.py tests/test_api_openai.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add llmnode/agent/service.py llmnode/api/app.py tests/test_agent.py tests/test_api_openai.py docs/contracts/control-plane.md docs/process/run.md
git commit -m "docs: align readiness diagnostics and run semantics"
```
