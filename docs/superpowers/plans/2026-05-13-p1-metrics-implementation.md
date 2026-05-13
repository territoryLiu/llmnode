# P1 性能指标采集 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为网关请求链路补齐最小 P1 性能指标采集、Agent `/admin/diagnostics/metrics` 聚合端点，以及基于 `Qwen3.6-27B` 的默认实测配置。

**Architecture:** 指标写入统一放在 `gateway-api` 请求处理层，持久化到 `runtime/data/gateway.db` 的新表 `request_metrics`。Agent 第一版只负责读取同一个 SQLite 数据库并暴露 `/admin/diagnostics/metrics` 聚合结果；`queue_length` 先使用稳定回退值 `0`，实时跨进程队列长度留到后续增强。配置层同步把正式默认模型切到 `models/Qwen/Qwen3.6-27B`，vLLM 显存占用改为 `gpu_memory_utilization: 0.75`。

**Tech Stack:** Python, FastAPI, SQLite, pytest, httpx, YAML

---

### Task 1: 存储层增加 `request_metrics` 表与聚合函数

**Files:**
- Modify: `llmnode/storage/db.py`
- Test: `tests/test_storage_metrics.py`

- [ ] **Step 1: 写出会失败的存储层测试**

Create `tests/test_storage_metrics.py` with:

```python
from pathlib import Path

from llmnode.storage.db import (
    aggregate_request_metrics,
    init_db,
    write_request_metric,
)


def test_request_metrics_aggregation_counts_latency_and_throughput(tmp_path: Path):
    conn = init_db(tmp_path / "metrics.db")

    write_request_metric(
        conn,
        request_id="req-1",
        model_name="qwen36-27b",
        protocol="openai",
        status="ok",
        latency_ms=1000.0,
        prompt_tokens=10,
        completion_tokens=50,
        total_tokens=60,
        tokens_per_second=50.0,
        started_at="2026-05-13T10:00:00+00:00",
        finished_at="2026-05-13T10:00:01+00:00",
    )
    write_request_metric(
        conn,
        request_id="req-2",
        model_name="qwen36-27b",
        protocol="openai",
        status="ok",
        latency_ms=2000.0,
        prompt_tokens=12,
        completion_tokens=30,
        total_tokens=42,
        tokens_per_second=15.0,
        started_at="2026-05-13T10:00:02+00:00",
        finished_at="2026-05-13T10:00:04+00:00",
    )
    write_request_metric(
        conn,
        request_id="req-3",
        model_name="qwen36-27b",
        protocol="anthropic",
        status="timeout",
        latency_ms=3000.0,
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
        tokens_per_second=None,
        started_at="2026-05-13T10:00:05+00:00",
        finished_at="2026-05-13T10:00:08+00:00",
    )

    metrics = aggregate_request_metrics(conn)

    assert metrics["request_count"] == 3
    assert metrics["success_count"] == 2
    assert round(metrics["success_rate"], 4) == 0.6667
    assert metrics["avg_latency_ms"] == 2000.0
    assert metrics["p95_latency_ms"] == 3000.0
    assert metrics["p99_latency_ms"] == 3000.0
    assert metrics["tokens_observed_requests"] == 2
    assert round(metrics["throughput_tokens_per_s"], 4) == round(80 / 3, 4)
```

- [ ] **Step 2: 运行测试确认当前失败**

Run:

```bash
pytest tests/test_storage_metrics.py -q
```

Expected:

```text
FAILED tests/test_storage_metrics.py::test_request_metrics_aggregation_counts_latency_and_throughput
```

- [ ] **Step 3: 在 `db.py` 中新增建表、写入和聚合能力**

Update `llmnode/storage/db.py` with:

```python
import math

def init_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS request_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            model_name TEXT NOT NULL,
            status TEXT NOT NULL,
            protocol TEXT NOT NULL,
            error_message TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS request_metrics (
            request_id TEXT PRIMARY KEY,
            model_name TEXT NOT NULL,
            protocol TEXT NOT NULL,
            status TEXT NOT NULL,
            latency_ms REAL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            tokens_per_second REAL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    return conn


def write_request_metric(
    conn: sqlite3.Connection,
    *,
    request_id: str,
    model_name: str,
    protocol: str,
    status: str,
    latency_ms: float | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
    tokens_per_second: float | None,
    started_at: str,
    finished_at: str | None,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO request_metrics(
            request_id,
            model_name,
            protocol,
            status,
            latency_ms,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            tokens_per_second,
            started_at,
            finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            request_id,
            model_name,
            protocol,
            status,
            latency_ms,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            tokens_per_second,
            started_at,
            finished_at,
        ),
    )
    conn.commit()


def _percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * ratio) - 1))
    return ordered[index]


def aggregate_request_metrics(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT status, latency_ms, completion_tokens
        FROM request_metrics
        ORDER BY created_at ASC
        """
    ).fetchall()
    request_count = len(rows)
    success_count = sum(1 for row in rows if row[0] == "ok")
    latencies = [float(row[1]) for row in rows if row[1] is not None]
    token_rows = [(float(row[1]), int(row[2])) for row in rows if row[1] is not None and row[2] is not None]
    total_completion_tokens = sum(item[1] for item in token_rows)
    total_latency_seconds = sum(item[0] / 1000.0 for item in token_rows)
    return {
        "request_count": request_count,
        "success_count": success_count,
        "success_rate": (success_count / request_count) if request_count else 0.0,
        "avg_latency_ms": (sum(latencies) / len(latencies)) if latencies else 0.0,
        "p95_latency_ms": _percentile(latencies, 0.95) or 0.0,
        "p99_latency_ms": _percentile(latencies, 0.99) or 0.0,
        "throughput_tokens_per_s": (
            total_completion_tokens / total_latency_seconds
            if total_latency_seconds > 0
            else 0.0
        ),
        "tokens_observed_requests": len(token_rows),
    }
```

- [ ] **Step 4: 运行测试确认存储层通过**

Run:

```bash
pytest tests/test_storage_metrics.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Commit**

```bash
git add llmnode/storage/db.py tests/test_storage_metrics.py
git commit -m "feat: 增加请求指标存储与聚合"
```

### Task 2: 网关在非流式请求链路写入 metrics

**Files:**
- Modify: `llmnode/api/app.py`
- Test: `tests/test_api_metrics.py`

- [ ] **Step 1: 写出会失败的 API 成功请求 metrics 测试**

Create `tests/test_api_metrics.py` with:

```python
import asyncio

import httpx

from llmnode.api.app import create_app
from llmnode.proxy.vllm_client import VLLMClient
from llmnode.storage.db import aggregate_request_metrics


class UsageFakeClient(VLLMClient):
    def __init__(self):
        super().__init__(base_url="http://fake")

    async def health(self) -> bool:
        return True

    async def post_json(self, path, payload):
        return {
            "id": "resp_1",
            "object": "chat.completion",
            "model": payload["model"],
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 22,
                "total_tokens": 33,
            },
        }


def test_chat_completions_write_metrics_for_success():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = UsageFakeClient()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer dev-key"},
                json={
                    "model": "claude-sonnet-4-5-20250929",
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            assert resp.status_code == 200
            metrics = aggregate_request_metrics(app.state.db)
            assert metrics["request_count"] == 1
            assert metrics["success_count"] == 1
            assert metrics["tokens_observed_requests"] == 1
            assert metrics["throughput_tokens_per_s"] > 0

    asyncio.run(run())
```

- [ ] **Step 2: 运行测试确认当前失败**

Run:

```bash
pytest tests/test_api_metrics.py::test_chat_completions_write_metrics_for_success -q
```

Expected:

```text
FAILED tests/test_api_metrics.py::test_chat_completions_write_metrics_for_success
```

- [ ] **Step 3: 在 `app.py` 中加入 metrics 记录辅助函数并接到成功链路**

Update `llmnode/api/app.py` imports and helpers with:

```python
from datetime import datetime, timezone

from ..storage.db import (
    list_agent_events,
    list_request_logs,
    write_request_metric,
    write_request_log,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _elapsed_ms(started_at: datetime, finished_at: datetime) -> float:
    return (finished_at - started_at).total_seconds() * 1000.0


def _extract_usage(payload: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None, None, None
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")
    return prompt_tokens, completion_tokens, total_tokens


def _record_request_metric(
    app: FastAPI,
    *,
    request_id: str,
    model_name: str,
    protocol: str,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    response_payload: dict[str, Any] | None = None,
) -> None:
    prompt_tokens, completion_tokens, total_tokens = _extract_usage(response_payload or {})
    latency_ms = _elapsed_ms(started_at, finished_at)
    tokens_per_second = None
    if completion_tokens is not None and latency_ms > 0:
        tokens_per_second = completion_tokens / (latency_ms / 1000.0)
    with suppress(Exception):
        write_request_metric(
            app.state.db,
            request_id=request_id,
            model_name=model_name,
            protocol=protocol,
            status=status,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            tokens_per_second=tokens_per_second,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
        )
```

Then in the non-stream `chat_completions` and `anthropic_messages` success path insert:

```python
started_at = datetime.now(timezone.utc)
result = await proxy_openai_chat(payload.to_backend_payload(payload.model), request.app.state.ctx)
finished_at = datetime.now(timezone.utc)
_record_request_metric(
    request.app,
    request_id=request_id,
    model_name=payload.model,
    protocol="openai",
    status="ok",
    started_at=started_at,
    finished_at=finished_at,
    response_payload=result,
)
```

Mirror the same structure for the `anthropic` handler.

- [ ] **Step 4: 运行成功请求 metrics 测试**

Run:

```bash
pytest tests/test_api_metrics.py::test_chat_completions_write_metrics_for_success -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Commit**

```bash
git add llmnode/api/app.py tests/test_api_metrics.py
git commit -m "feat: 在网关成功请求链路记录性能指标"
```

### Task 3: 网关为拒绝、超时和无 usage 成功请求补齐 metrics

**Files:**
- Modify: `llmnode/api/app.py`
- Modify: `tests/test_api_metrics.py`

- [ ] **Step 1: 写出拒绝与缺失 usage 的失败测试**

Append to `tests/test_api_metrics.py`:

```python
class NoUsageFakeClient(VLLMClient):
    def __init__(self):
        super().__init__(base_url="http://fake")

    async def health(self) -> bool:
        return True

    async def post_json(self, path, payload):
        return {
            "id": "resp_2",
            "object": "chat.completion",
            "model": payload["model"],
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        }


def test_queue_rejection_writes_metrics_record():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = UsageFakeClient()
        app.state.request_gate._queue_limit = 0
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer dev-key"},
                json={
                    "model": "claude-sonnet-4-5-20250929",
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            assert resp.status_code == 429
            metrics = aggregate_request_metrics(app.state.db)
            assert metrics["request_count"] == 1
            assert metrics["success_count"] == 0
            assert metrics["tokens_observed_requests"] == 0

    asyncio.run(run())


def test_success_without_usage_still_writes_latency_metrics():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = NoUsageFakeClient()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer dev-key"},
                json={
                    "model": "claude-sonnet-4-5-20250929",
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            assert resp.status_code == 200
            metrics = aggregate_request_metrics(app.state.db)
            assert metrics["request_count"] == 1
            assert metrics["success_count"] == 1
            assert metrics["tokens_observed_requests"] == 0
            assert metrics["avg_latency_ms"] > 0

    asyncio.run(run())
```

- [ ] **Step 2: 运行测试确认当前失败**

Run:

```bash
pytest tests/test_api_metrics.py::test_queue_rejection_writes_metrics_record tests/test_api_metrics.py::test_success_without_usage_still_writes_latency_metrics -q
```

Expected:

```text
FAILED tests/test_api_metrics.py::test_queue_rejection_writes_metrics_record
FAILED tests/test_api_metrics.py::test_success_without_usage_still_writes_latency_metrics
```

- [ ] **Step 3: 在拒绝、超时和异常分支补 metrics 记录**

Update the `chat_completions` and `anthropic_messages` handlers so each branch that already calls `write_request_log(...)` also calls `_record_request_metric(...)` with the same `request_id`, `payload.model`, and protocol.

Use the same pattern in `queue_full` and `queue_timeout` branches:

```python
finished_at = datetime.now(timezone.utc)
_record_request_metric(
    request.app,
    request_id=request_id,
    model_name=payload.model,
    protocol="openai",
    status="rejected",
    started_at=started_at,
    finished_at=finished_at,
)
```

For timeout branches, pass `status="timeout"`. For successful responses with no `usage`, do not special-case anything; `_extract_usage` already returns `None` values and `_record_request_metric` still writes latency.

- [ ] **Step 4: 运行 API metrics 全部测试**

Run:

```bash
pytest tests/test_api_metrics.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit**

```bash
git add llmnode/api/app.py tests/test_api_metrics.py
git commit -m "feat: 补齐失败与缺失usage请求的性能指标"
```

### Task 4: Agent 增加 `/admin/diagnostics/metrics` 聚合端点

**Files:**
- Modify: `llmnode/agent/service.py`
- Modify: `tests/test_agent.py`

- [ ] **Step 1: 写出会失败的 Agent metrics 端点测试**

Append to `tests/test_agent.py`:

```python
def test_agent_diagnostics_metrics_endpoint_returns_aggregated_values():
    async def run():
        app = create_agent_app(enable_monitor=False)
        transport = httpx.ASGITransport(app=app)

        from llmnode.storage.db import write_request_metric

        write_request_metric(
            app.state.db,
            request_id="req-1",
            model_name="qwen36-27b",
            protocol="openai",
            status="ok",
            latency_ms=1000.0,
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            tokens_per_second=20.0,
            started_at="2026-05-13T10:00:00+00:00",
            finished_at="2026-05-13T10:00:01+00:00",
        )

        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/admin/diagnostics/metrics")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["request_count"] == 1
            assert payload["success_count"] == 1
            assert payload["tokens_observed_requests"] == 1
            assert payload["throughput_tokens_per_s"] > 0
            assert "generated_at" in payload

    asyncio.run(run())
```

- [ ] **Step 2: 运行测试确认当前失败**

Run:

```bash
pytest tests/test_agent.py::test_agent_diagnostics_metrics_endpoint_returns_aggregated_values -q
```

Expected:

```text
FAILED tests/test_agent.py::test_agent_diagnostics_metrics_endpoint_returns_aggregated_values
```

- [ ] **Step 3: 在 Agent 暴露 metrics 聚合端点**

Update `llmnode/agent/service.py` imports and endpoint block with:

```python
from ..storage.db import (
    aggregate_request_metrics,
    init_db,
    list_agent_events,
    write_agent_event,
)
```

Then add:

```python
    @app.get("/admin/diagnostics/metrics")
    async def diagnostics_metrics():
        metrics = await app.state.run_sync(aggregate_request_metrics, app.state.db)
        metrics["queue_length"] = 0
        metrics["generated_at"] = _utc_now()
        return metrics
```

Keep the first version simple: return database aggregate plus stable `queue_length` fallback `0`. Do not add cross-process reads of gateway in this task; if a later code pass finds a safe way to query live gateway queue length, that enhancement belongs after this endpoint is working.

- [ ] **Step 4: 运行 Agent metrics 测试**

Run:

```bash
pytest tests/test_agent.py::test_agent_diagnostics_metrics_endpoint_returns_aggregated_values -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Commit**

```bash
git add llmnode/agent/service.py tests/test_agent.py
git commit -m "feat: 暴露诊断指标聚合端点"
```

### Task 5: 切换默认 27B 配置并补齐路由

**Files:**
- Modify: `config/defaults.yaml`
- Modify: `config/models.yaml`
- Modify: `README.md`

- [ ] **Step 1: 写出会失败的配置检查**

Run:

```bash
rg -n "Qwen3.6-35B-A3B|qwen36-35b-a3b|gpu_memory_utilization: 0.9" config/defaults.yaml config/models.yaml README.md
```

Expected:

```text
- 仍能看到 `Qwen3.6-35B-A3B`
- 仍能看到 `qwen36-35b-a3b`
- 仍能看到旧的 `gpu_memory_utilization`
```

- [ ] **Step 2: 更新正式默认模型和 vLLM 参数**

Apply these edits:

In `config/defaults.yaml`:

```yaml
gateway:
  host: 0.0.0.0
  port: 4000
  api_key: dev-key
  backend_url: http://127.0.0.1:8000
  backend_model: qwen36-27b
  agent_base_url: http://127.0.0.1:4010
  agent_status_url: http://127.0.0.1:4010/state
  require_agent_ready: false
  queue_limit: 8
  execution_limit: 1
vllm:
  backend_type: vllm
  container_name: qwen36-vllm
  image_name: vllm/vllm-openai:nightly
  model_dir: models/Qwen/Qwen3.6-27B
  model_file: ""
  model_name: qwen36-27b
  host_port: 8000
  gpu_memory_utilization: 0.75
  tensor_parallel_size: 1
  max_model_len: 262144
```

In `config/models.yaml` replace the final route with:

```yaml
  - name: qwen36-27b
    display_name: Qwen3.6 27B
    backend_model: qwen36-27b
    enabled: true
```

Update the three Claude-compatible entries so their `backend_model` is `qwen36-27b`.

In `README.md` update the “当前边界” block:

```md
- 默认模型目录：`models/Qwen/Qwen3.6-27B`
```

- [ ] **Step 3: 运行配置检查确认修改生效**

Run:

```bash
rg -n "Qwen3.6-27B|qwen36-27b|gpu_memory_utilization: 0.75|max_model_len: 262144" config/defaults.yaml config/models.yaml README.md
```

Expected:

```text
- 能看到 `Qwen3.6-27B`
- 能看到 `qwen36-27b`
- 能看到 `gpu_memory_utilization: 0.75`
- 能看到 `max_model_len: 262144`
```

- [ ] **Step 4: Commit**

```bash
git add config/defaults.yaml config/models.yaml README.md
git commit -m "feat: 切换默认27B部署配置"
```

### Task 6: 回流契约并完成测试验证

**Files:**
- Modify: `docs/contracts/backend-routing.md`
- Modify: `docs/contracts/control-plane.md`
- Modify: `docs/blueprint/current.md`
- Test: `tests/test_storage_metrics.py`
- Test: `tests/test_api_metrics.py`
- Test: `tests/test_agent.py`

- [ ] **Step 1: 写出会失败的文档检查**

Run:

```bash
rg -n "/admin/diagnostics/metrics|Qwen3.6-27B|性能指标采集" docs/contracts/backend-routing.md docs/contracts/control-plane.md docs/blueprint/current.md
```

Expected:

```text
- `backend-routing.md` 还没有 `/admin/diagnostics/metrics` 的正式描述
- `control-plane.md` 还没有诊断指标端点的正式描述
- `current.md` 还没有把 27B 默认模型写成当前状态
```

- [ ] **Step 2: 更新契约和当前蓝图**

In `docs/contracts/backend-routing.md` add the diagnostics endpoint and minimum metrics list:

```md
- `GET /admin/diagnostics/metrics` - 返回基础性能指标聚合：
  - 请求总数
  - 成功率
  - 平均延迟
  - P95 / P99 延迟
  - tokens/s
  - 队列长度
```

In `docs/contracts/control-plane.md` add under diagnostics-related output requirements:

```md
- Agent 诊断 API 端点应继续暴露 `/admin/diagnostics/*`
- 当性能指标采集落地后，应包括 `GET /admin/diagnostics/metrics`
```

In `docs/blueprint/current.md` update the current default model references to:

```md
- 默认模型目录：`models/Qwen/Qwen3.6-27B`
```

And in the “当前最值得继续补厚的方向” section, replace the pending bullet with:

```md
- 性能指标采集已具备最小落地点（请求总数、成功率、延迟、tokens/s、诊断端点），后续可继续补时间窗口与多维聚合
```

- [ ] **Step 3: 运行目标测试集**

Run:

```bash
pytest tests/test_storage_metrics.py tests/test_api_metrics.py tests/test_agent.py -q
```

Expected:

```text
all selected tests passed
```

- [ ] **Step 4: 运行一次最小代码搜索回归**

Run:

```bash
rg -n "/admin/diagnostics/metrics|request_metrics|qwen36-27b|Qwen3.6-27B" llmnode config docs tests
```

Expected:

```text
- 能看到新端点
- 能看到 `request_metrics`
- 能看到 27B 模型配置和文档回流
```

- [ ] **Step 5: Commit**

```bash
git add docs/contracts/backend-routing.md docs/contracts/control-plane.md docs/blueprint/current.md tests/test_storage_metrics.py tests/test_api_metrics.py tests/test_agent.py llmnode/storage/db.py llmnode/api/app.py llmnode/agent/service.py config/defaults.yaml config/models.yaml README.md
git commit -m "feat: 完成最小P1性能指标采集闭环"
```
