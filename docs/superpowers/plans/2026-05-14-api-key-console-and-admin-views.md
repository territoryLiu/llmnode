# API Key Console And Admin Views Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有 API Key CRUD 雏形补成正式管理台能力，支持脱敏 key 展示、新建当次显示/隐藏/复制明文、Base URL 展示复制、关联用量展示，并保持哈希存储安全边界。

**Architecture:** 后端继续以 `api_keys` 表存哈希和元信息，不新增可逆明文；`api/app.py` 返回 `masked_key` 与 key usage summary；`web-console` 只在新建当次本地保存 `secret`，对历史 key 仅展示 `masked_key`；Base URL 统一由 admin overview 下发。

**Tech Stack:** FastAPI, SQLite, pytest, React, Vitest

---

### Task 1: 扩展 API key 返回模型与存储辅助函数

**Files:**
- Modify: `llmnode/storage/db.py`
- Modify: `llmnode/api/app.py`
- Test: `tests/test_storage_api_keys.py`
- Test: `tests/test_admin_api_keys.py`

- [ ] **Step 1: 先写失败测试，要求列表返回 masked_key 而非 secret**

```python
listed = await client.get("/admin/keys", headers={"Authorization": "Bearer dev-key"})
row = listed.json()["keys"][0]
assert row["masked_key"].startswith("ln_")
assert "secret" not in row
assert "key_hash" not in row
```

- [ ] **Step 2: 运行测试确认当前失败**

Run: `pytest tests/test_admin_api_keys.py tests/test_storage_api_keys.py -v`
Expected: FAIL，当前返回结构没有 `masked_key`

- [ ] **Step 3: 在 `db.py` 增加 masked key 生成辅助函数或通过创建路径回填**

```python
def mask_api_key(secret: str) -> str:
    if len(secret) <= 10:
        return secret
    return f"{secret[:6]}***{secret[-4:]}"
```

- [ ] **Step 4: 扩展 `_sanitize_api_key_row()` 与创建响应**

```python
def _sanitize_api_key_row(row: dict[str, Any], *, masked_key: str | None = None) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "masked_key": masked_key or f"key_{row['id']}",
        "status": row["status"],
        "scopes": row["scopes"],
        "rpm_limit": row["rpm_limit"],
        "concurrency_limit": row["concurrency_limit"],
        "created_at": row["created_at"],
        "disabled_at": row["disabled_at"],
        "last_used_at": row["last_used_at"],
        "note": row["note"],
    }
```

```python
response = JSONResponse({
    "key": _sanitize_api_key_row(row, masked_key=mask_api_key(secret)),
    "secret": secret,
})
```

- [ ] **Step 5: 为历史 key 定义稳定 masked_key 生成策略**

```python
masked_key = f"ln_saved_{row['id']}"
```
要求：masked key 必须稳定、可展示、不可反推出明文；不要为了 masked_key 去存储可逆明文。

- [ ] **Step 6: 运行测试**

Run: `pytest tests/test_admin_api_keys.py tests/test_storage_api_keys.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add llmnode/storage/db.py llmnode/api/app.py tests/test_storage_api_keys.py tests/test_admin_api_keys.py
git commit -m "feat: return masked api key metadata"
```

### Task 2: 暴露 admin readiness/key overview 视图与 Base URL

**Files:**
- Modify: `llmnode/api/app.py`
- Test: `tests/test_api_openai.py`
- Test: `tests/test_admin_api_keys.py`

- [ ] **Step 1: 先写失败测试，要求 overview/readiness 返回 Base URL**

```python
resp = await client.get("/admin/overview/readiness", headers={"Authorization": "Bearer dev-key"})
payload = resp.json()
assert payload["base_urls"]["local"] == "http://127.0.0.1:4000"
assert "lan" in payload["base_urls"]
```

- [ ] **Step 2: 在 `api/app.py` 新增 readiness overview 视图**

```python
@app.get("/admin/overview/readiness")
async def admin_readiness_overview(request: Request):
    _resolve_auth(request, "admin")
    state = await request.app.state.fetch_agent_state()
    return {
        "readiness": state,
        "base_urls": {
            "local": "http://127.0.0.1:4000",
            "lan": "http://10.18.90.100:4000",
        },
    }
```

- [ ] **Step 3: 把 key usage summary 合并到 `/admin/keys` 列表返回**

```python
response = JSONResponse({
    "keys": [
        {
            **_sanitize_api_key_row(row),
            "usage_summary": aggregate_usage_for_api_key(request.app.state.db, api_key_id=row["id"])["summary"],
        }
        for row in list_api_keys(request.app.state.db)
    ]
})
```

- [ ] **Step 4: 运行测试**

Run: `pytest tests/test_admin_api_keys.py tests/test_api_openai.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add llmnode/api/app.py tests/test_admin_api_keys.py tests/test_api_openai.py
git commit -m "feat: add readiness overview and key summaries"
```

### Task 3: 在管理台补齐 key 列表、Base URL、显示隐藏复制交互

**Files:**
- Modify: `web-console/src/store.tsx`
- Modify: `web-console/src/pages/ApiKeysView.tsx`
- Modify: `web-console/src/i18n.ts`
- Test: `web-console/src/components/Layout.test.tsx`

- [ ] **Step 1: 先写前端失败测试，要求 key 页面展示 masked key 和 Base URL**

```tsx
expect(screen.getByText('http://127.0.0.1:4000')).toBeInTheDocument()
expect(screen.getByText(/masked/i)).toBeInTheDocument()
```

- [ ] **Step 2: 在 store 中扩展 ApiKeyRow 与 readiness overview 状态**

```tsx
export interface ApiKeyRow {
  id: number
  name: string
  masked_key: string
  usage_summary?: {
    total_requests: number
    total_tokens: number | null
  }
}
```

```tsx
const [readinessOverview, setReadinessOverview] = useState<ReadinessOverview | null>(null)
```

- [ ] **Step 3: 在 ApiKeysView 顶部展示 Base URL 卡片和复制按钮**

```tsx
<code>{readinessOverview?.base_urls.local}</code>
<button onClick={() => copyText(readinessOverview?.base_urls.local ?? '')}>
  <Copy />
</button>
```

- [ ] **Step 4: 给新建当次 secret 增加显示 / 隐藏切换**

```tsx
const [secretVisible, setSecretVisible] = useState(true)
<code>{secretVisible ? showNewSecret : '••••••••••••••'}</code>
<ToggleButton onClick={() => setSecretVisible((v) => !v)}>
  {secretVisible ? t('keys.hide') : t('keys.show')}
</ToggleButton>
```

- [ ] **Step 5: 在历史 key 列表中展示 masked_key、usage summary 和复制 masked key**

```tsx
<div className="font-mono text-xs">{key.masked_key}</div>
<button onClick={() => copyText(key.masked_key)} title={t('keys.copyMasked')}>
  <Copy className="w-4 h-4" />
</button>
```

- [ ] **Step 6: 运行前端测试与类型检查**

Run: `cd web-console && npm test`
Expected: PASS

Run: `cd web-console && npm run lint`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add web-console/src/store.tsx web-console/src/pages/ApiKeysView.tsx web-console/src/i18n.ts web-console/src/components/Layout.test.tsx
git commit -m "feat: enhance api key console interactions"
```

### Task 4: 回流文档与默认模型文档纠偏

**Files:**
- Modify: `docs/blueprint/current.md`
- Modify: `docs/blueprint/history.md`
- Modify: `docs/contracts/backend-routing.md`
- Modify: `docs/process/deployment.md`
- Modify: `docs/blueprint/roadmap.md`

- [ ] **Step 1: 先定位仍引用旧默认模型的文档**

Run: `rg -n "35b-a3b|27b-fp8|default profile|默认模型" docs config/defaults.yaml config/backends`
Expected: 输出里至少列出仍引用旧默认 profile 的 Markdown 文件路径，作为本任务后续修改清单

- [ ] **Step 2: 更新当前蓝图与历史文档**

```md
- 当前默认 profile 已切换为 `config/backends/vllm_qwen36-27b-FP8.yaml`
- API Key 管理台支持新建当次显示 / 隐藏 / 复制
- Usage 视图支持按模型 / 后端 / API Key 聚合
```

- [ ] **Step 3: 更新 routing / deployment 文档中的就绪与管理台行为**

```md
- 热身窗口期由 `503 + Retry-After` 表达
- 管理台 Base URL 由 admin overview 统一下发
```

- [ ] **Step 4: 做文档回归检查**

Run: `rg -n "Retry-After|warming_up|masked_key|127.0.0.1:4000|10.18.90.100:4000" docs`
Expected: 关键术语全部能在正式文档中找到

- [ ] **Step 5: Commit**

```bash
git add docs/blueprint/current.md docs/blueprint/history.md docs/contracts/backend-routing.md docs/process/deployment.md docs/blueprint/roadmap.md
git commit -m "docs: backfill key console and usage truth sources"
```
