# Usage Ledger And Aggregation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 `request_metrics` 基础上补齐正式 usage ledger，支持按模型、后端、API Key、日月年聚合，并为管理台提供稳定的 usage summary / trend / breakdown 视图。

**Architecture:** 继续使用 SQLite 作为唯一账本；`gateway-api` 在请求结束时补充写入 backend / key / cache usage 字段；`storage/db.py` 提供聚合查询函数；`api/app.py` 对外暴露 admin usage 视图；前端只消费视图结果，不自行重算业务口径。

**Tech Stack:** FastAPI, SQLite, pytest, React, Vitest

---

### Task 1: 扩展 request_metrics 表和写入路径

**Files:**
- Modify: `llmnode/storage/db.py`
- Modify: `llmnode/api/app.py`
- Test: `tests/test_storage_metrics.py`
- Test: `tests/test_api_metrics.py`

- [ ] **Step 1: 先写失败测试，要求新字段能被写入和读出**

```python
write_request_metric(
    conn,
    request_id="req_1",
    model_name="demo",
    protocol="openai",
    status="ok",
    latency_ms=10,
    prompt_tokens=1,
    completion_tokens=2,
    total_tokens=3,
    tokens_per_second=0.2,
    backend_type="vllm",
    api_key_id=7,
    cache_creation_tokens=5,
    cache_read_tokens=6,
    cache_miss_tokens=None,
    error_code=None,
    status_detail=None,
    started_at="2026-05-14T10:00:00+00:00",
    finished_at="2026-05-14T10:00:01+00:00",
)
```

- [ ] **Step 2: 运行测试确认当前失败**

Run: `pytest tests/test_storage_metrics.py tests/test_api_metrics.py -k metrics -v`
Expected: FAIL，提示 `write_request_metric()` 参数缺失或表结构缺列

- [ ] **Step 3: 通过 `_ensure_columns()` 扩展 `request_metrics`**

```python
_ensure_columns(
    conn,
    "request_metrics",
    {
        "backend_type": "TEXT",
        "api_key_id": "INTEGER",
        "cache_creation_tokens": "INTEGER",
        "cache_read_tokens": "INTEGER",
        "cache_miss_tokens": "INTEGER",
        "error_code": "TEXT",
        "status_detail": "TEXT",
    },
)
```

- [ ] **Step 4: 扩展 `_extract_usage()` 和 `_record_request_metric()`**

```python
def _extract_usage(payload: dict[str, Any]) -> dict[str, int | None]:
    usage = payload.get("usage") or {}
    cache = usage.get("cache") or {}
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cache_creation_tokens": cache.get("creation_tokens"),
        "cache_read_tokens": cache.get("read_tokens"),
        "cache_miss_tokens": cache.get("miss_tokens"),
    }
```

- [ ] **Step 5: 把 `backend_type` 与 `api_key_id` 一并写入账本**

```python
_record_request_metric(
    request.app,
    request_id=request_id,
    model_name=payload.model,
    protocol="openai",
    status="ok",
    started_at=started_at,
    finished_at=finished_at,
    response_payload=result,
    backend_type=request.app.state.ctx.backend_client.backend_type,
    api_key_id=auth.api_key_id,
)
```

- [ ] **Step 6: 运行测试**

Run: `pytest tests/test_storage_metrics.py tests/test_api_metrics.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add llmnode/storage/db.py llmnode/api/app.py tests/test_storage_metrics.py tests/test_api_metrics.py
git commit -m "feat: extend usage ledger schema"
```

### Task 2: 实现 usage 聚合查询层

**Files:**
- Modify: `llmnode/storage/db.py`
- Test: `tests/test_storage_metrics.py`

- [ ] **Step 1: 先写失败测试，覆盖 summary、trend、breakdown**

```python
summary = aggregate_request_metrics(conn)
assert summary["request_count"] == 2
assert "cache_read_tokens" in summary

trend = aggregate_usage_trend(conn, granularity="day")
assert trend[0]["bucket"] == "2026-05-14"

grouped = aggregate_usage_breakdown(conn, group_by="backend_type")
assert grouped[0]["group"] == "vllm"
```

- [ ] **Step 2: 保留 `aggregate_request_metrics()` 兼容入口，但内部升级**

```python
def aggregate_request_metrics(
    conn: sqlite3.Connection,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    rows = _select_request_metric_rows(conn, date_from=date_from, date_to=date_to)
    latencies = [float(row["latency_ms"]) for row in rows if row["latency_ms"] is not None]
    return {
        "request_count": len(rows),
        "success_count": sum(1 for row in rows if row["status"] == "ok"),
        "avg_latency_ms": (sum(latencies) / len(latencies)) if latencies else 0.0,
        "cache_creation_tokens": sum(row["cache_creation_tokens"] or 0 for row in rows),
        "cache_read_tokens": sum(row["cache_read_tokens"] or 0 for row in rows),
        "cache_miss_tokens": sum(row["cache_miss_tokens"] or 0 for row in rows),
    }
```

- [ ] **Step 3: 新增趋势与分组查询函数**

```python
def aggregate_usage_trend(conn, *, granularity: str = "day") -> list[dict[str, Any]]:
    bucket_expr = {
        "day": "substr(created_at, 1, 10)",
        "month": "substr(created_at, 1, 7)",
        "year": "substr(created_at, 1, 4)",
    }[granularity]
    rows = conn.execute(
        f"""
        SELECT {bucket_expr} AS bucket, COUNT(*) AS request_count, SUM(total_tokens) AS total_tokens
        FROM request_metrics
        GROUP BY 1
        ORDER BY 1
        """
    ).fetchall()
    return [{"bucket": row[0], "request_count": row[1], "total_tokens": row[2]} for row in rows]

def aggregate_usage_breakdown(conn, *, group_by: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT {group_by} AS grouping_value, COUNT(*) AS request_count, SUM(total_tokens) AS total_tokens
        FROM request_metrics
        GROUP BY 1
        ORDER BY total_tokens DESC
        """
    ).fetchall()
    return [{"group": row[0], "request_count": row[1], "total_tokens": row[2]} for row in rows]

def aggregate_usage_for_api_key(conn, *, api_key_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS request_count, SUM(total_tokens) AS total_tokens, SUM(cache_read_tokens) AS cache_read_tokens
        FROM request_metrics
        WHERE api_key_id = ?
        """,
        (api_key_id,),
    ).fetchone()
    return {
        "summary": {
            "api_key_id": api_key_id,
            "request_count": row[0],
            "total_tokens": row[1],
            "cache_read_tokens": row[2],
        }
    }
```

- [ ] **Step 4: 确保 null usage 与历史老数据不会被伪装成 0**

```python
SUM(cache_read_tokens) AS cache_read_tokens,
COUNT(cache_read_tokens) AS cache_read_observed_requests
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_storage_metrics.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add llmnode/storage/db.py tests/test_storage_metrics.py
git commit -m "feat: add usage aggregation queries"
```

### Task 3: 暴露 admin usage 视图 API

**Files:**
- Modify: `llmnode/api/app.py`
- Test: `tests/test_api_metrics.py`
- Test: `tests/test_api_openai.py`

- [ ] **Step 1: 先写失败测试，要求 `/admin/overview/usage` 返回 summary / trend / breakdown**

```python
resp = await client.get("/admin/overview/usage", headers={"Authorization": "Bearer dev-key"})
payload = resp.json()
assert "summary" in payload
assert "trend" in payload
assert "breakdown" in payload
```

- [ ] **Step 2: 再写一个单 key 用量端点失败测试**

```python
resp = await client.get(f"/admin/keys/{key_id}/usage", headers={"Authorization": "Bearer dev-key"})
assert resp.status_code == 200
assert resp.json()["summary"]["api_key_id"] == key_id
```

- [ ] **Step 3: 在 `api/app.py` 新增 overview usage 端点**

```python
@app.get("/admin/overview/usage")
async def admin_usage_overview(request: Request, granularity: str = "day"):
    _resolve_auth(request, "admin")
    return {
        "summary": aggregate_request_metrics(request.app.state.db),
        "trend": aggregate_usage_trend(request.app.state.db, granularity=granularity),
        "breakdown": {
            "models": aggregate_usage_breakdown(request.app.state.db, group_by="model_name"),
            "backends": aggregate_usage_breakdown(request.app.state.db, group_by="backend_type"),
            "api_keys": aggregate_usage_breakdown(request.app.state.db, group_by="api_key_id"),
        },
    }
```

- [ ] **Step 4: 增加单 key 用量视图端点**

```python
@app.get("/admin/keys/{key_id}/usage")
async def admin_key_usage(request: Request, key_id: int):
    _resolve_auth(request, "admin")
    return aggregate_usage_for_api_key(request.app.state.db, api_key_id=key_id)
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_api_metrics.py tests/test_api_openai.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add llmnode/api/app.py tests/test_api_metrics.py tests/test_api_openai.py
git commit -m "feat: expose admin usage overview APIs"
```

### Task 4: 把 usage 视图接到管理台总览和用量页

**Files:**
- Modify: `web-console/src/store.tsx`
- Modify: `web-console/src/pages/UsageRecordsView.tsx`
- Modify: `web-console/src/pages/OverviewView.tsx`
- Modify: `web-console/src/i18n.ts`
- Test: `web-console/src/components/Layout.test.tsx`

- [ ] **Step 1: 先写前端失败测试，要求 overview 和 usage 页面消费新接口**

```tsx
expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/admin/overview/usage'), expect.anything())
expect(screen.getByText(/tokens/i)).toBeInTheDocument()
```

- [ ] **Step 2: 在 store 中新增 usage overview 状态与请求方法**

```tsx
interface UsageOverview {
  summary: {
    request_count: number
    success_count: number
    total_tokens: number | null
    cache_read_tokens: number | null
    cache_creation_tokens: number | null
    cache_miss_tokens: number | null
  }
  trend: Array<{bucket: string; total_tokens: number}>
  breakdown: {
    models: Array<{group: string; total_tokens: number}>
    backends: Array<{group: string; total_tokens: number}>
    api_keys: Array<{group: string; total_tokens: number}>
  }
}
```

```tsx
async function refreshUsageOverview() {
  const payload = await requestJson<UsageOverview>('/admin/overview/usage')
  setUsageOverview(payload)
}
```

- [ ] **Step 3: 用聚合结果替换 UsageRecordsView 里“只看 requestLogs”的 KPI**

```tsx
const totalTokens = usageOverview?.summary.total_tokens ?? 0
const cacheReadTokens = usageOverview?.summary.cache_read_tokens ?? null
```

- [ ] **Step 4: 在 OverviewView 补 trends / breakdown 图表的数据源**

```tsx
const tokenTrend = usageOverview?.trend ?? []
const backendBreakdown = usageOverview?.breakdown.backends ?? []
```

- [ ] **Step 5: 运行前端测试与类型检查**

Run: `cd web-console && npm test`
Expected: PASS

Run: `cd web-console && npm run lint`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web-console/src/store.tsx web-console/src/pages/UsageRecordsView.tsx web-console/src/pages/OverviewView.tsx web-console/src/i18n.ts web-console/src/components/Layout.test.tsx
git commit -m "feat: surface usage overview in console"
```
