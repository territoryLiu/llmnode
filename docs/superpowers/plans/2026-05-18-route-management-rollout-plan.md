# Route 管理平台化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `model_routes` 从启动时可整表重建的运行态缓存，升级为单机节点上的长期 route 注册表，并分阶段补齐 external route 新增、manual route 删除和 stale 管理能力。

**Architecture:** 后端继续以 SQLite `model_routes` 作为单机 route 真相源，但引入 `source_kind / source_ref / stale` 来表达对象来源和同步状态。启动 seed 由“全表重建”改成“profile_seed 增量同步”，管理 API 与管理台在 phase B/C 逐步开放 external create、manual delete，并把 `profile_seed` 与 `manual` 的动作边界显式展示出来。

**Tech Stack:** Python, FastAPI, SQLite, React, Vitest, pytest

---

## 文件结构

### 后端核心

- Modify: `llmnode/models.py`
  - 为 `ModelRoute` 增加来源与 stale 字段
  - 对 `model_route_from_row()`、`model_routes_for_admin()` 做序列化对齐
- Modify: `llmnode/storage/db.py`
  - 为 `model_routes` 表增量补列
  - 重写 `seed_model_routes()` 为增量同步逻辑
  - 增加 `delete_model_route()` 或等价 helper
- Modify: `llmnode/api/app.py`
  - 补 `POST /admin/models`
  - 补 `DELETE /admin/models/{name}`
  - 收紧 `PATCH /admin/models/{name}` 的对象身份边界

### 测试

- Modify: `tests/test_storage_model_routes.py`
  - 覆盖新的 seed 行为、manual route 保留、stale 标记
- Modify: `tests/test_api_openai.py`
  - 若已覆盖 admin models 相关接口，补 create/delete 场景
- Create or Modify: `tests/test_admin_model_routes.py`
  - 独立覆盖 `/admin/models` create/patch/delete 边界
- Modify: `tests/test_smoke.py`
  - 如需补 route metadata smoke 断言，仅限最小新增

### 前端

- Modify: `web-console/src/store.tsx`
  - 扩展 `ModelRouteRow` 类型与 `createModelRoute` / `deleteModelRoute` API 调用
- Modify: `web-console/src/pages/ModelRoutesView.tsx`
  - 展示 `source_kind / stale`
  - 增加 external route 创建入口
  - 对 delete 动作做条件显示
- Modify: `web-console/src/i18n.ts`
  - 补 route 来源、stale、create/delete 文案
- Modify: `web-console/src/pages/ConsoleViews.test.tsx`
  - 覆盖 create/delete 与来源标识 UI

### 文档回流

- Modify: `docs/blueprint/current.md`
  - 回流 route 注册表正式边界
- Modify: `docs/contracts/backend-routing.md`
  - 回流 `source_kind / source_ref / stale` 与 API 行为
- Modify: `docs/process/run.md`
  - 如 seed 行为对启动观察和排障有新语义，补最小说明

## Task 1: 后端数据模型与存储迁移

**Files:**
- Modify: `llmnode/models.py`
- Modify: `llmnode/storage/db.py`
- Test: `tests/test_storage_model_routes.py`

- [ ] **Step 1: 写失败测试，表达 `model_routes` 需要保留 manual route 而不是被 seed 清掉**

```python
from pathlib import Path

from llmnode.storage.db import init_db, list_model_routes, seed_model_routes, upsert_model_route


def test_seed_model_routes_keeps_manual_routes_and_marks_old_profile_routes_stale(tmp_path: Path):
    conn = init_db(tmp_path / "gateway.db")
    upsert_model_route(
        conn,
        {
            "name": "manual-openai",
            "display_name": "Manual OpenAI",
            "backend_model": None,
            "backend_type": None,
            "enabled": True,
            "lifecycle_mode": "external",
            "upstream_protocol": "responses",
            "upstream_base_url": "https://api.openai.com/v1",
            "upstream_model": "gpt-4.1",
            "upstream_auth_kind": "bearer",
            "upstream_auth_ref": "OPENAI_KEY",
            "capabilities_json": {"supports_responses": True},
            "source_kind": "manual",
            "source_ref": None,
            "stale": 0,
        },
    )
    upsert_model_route(
        conn,
        {
            "name": "old-seeded",
            "display_name": "Old Seeded",
            "backend_model": "old-model",
            "backend_type": "vllm",
            "enabled": True,
            "lifecycle_mode": "managed_local",
            "upstream_protocol": "chat",
            "upstream_base_url": "http://127.0.0.1:8000/v1",
            "upstream_model": "old-model",
            "upstream_auth_kind": "none",
            "upstream_auth_ref": None,
            "capabilities_json": {},
            "source_kind": "profile_seed",
            "source_ref": "old_profile",
            "stale": 0,
        },
    )

    seed_model_routes(
        conn,
        [
            {
                "name": "new-seeded",
                "display_name": "New Seeded",
                "backend_model": "new-model",
                "backend_type": "vllm",
                "enabled": True,
                "lifecycle_mode": "managed_local",
                "upstream_protocol": "chat",
                "upstream_base_url": "http://127.0.0.1:9000/v1",
                "upstream_model": "new-model",
                "upstream_auth_kind": "none",
                "upstream_auth_ref": None,
                "capabilities_json": {},
                "source_kind": "profile_seed",
                "source_ref": "new_profile",
                "stale": 0,
            },
        ],
    )

    routes = {item["name"]: item for item in list_model_routes(conn)}
    assert routes["manual-openai"]["source_kind"] == "manual"
    assert routes["manual-openai"]["enabled"] is True
    assert routes["old-seeded"]["stale"] is True
    assert routes["old-seeded"]["enabled"] is False
    assert routes["new-seeded"]["source_ref"] == "new_profile"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=/proj02/liuheshan/llmnode pytest tests/test_storage_model_routes.py::test_seed_model_routes_keeps_manual_routes_and_marks_old_profile_routes_stale -v`  
Expected: FAIL，原因应是 `source_kind / stale` 字段不存在，或 seed 仍然删掉 manual route

- [ ] **Step 3: 最小修改 `ModelRoute` 与数据库列定义**

在 `llmnode/models.py` 的 `ModelRoute` 中新增字段：

```python
source_kind: str = "profile_seed"
source_ref: str | None = None
stale: bool = False
```

在 `model_route_from_row()` 和 `model_routes_for_admin()` 中同步读写：

```python
source_kind=row.get("source_kind", "profile_seed"),
source_ref=row.get("source_ref"),
stale=bool(row.get("stale", False)),
```

在 `llmnode/storage/db.py` 的 `_ensure_columns()` 中给 `model_routes` 增列：

```python
{
    "source_kind": "TEXT NOT NULL DEFAULT 'profile_seed'",
    "source_ref": "TEXT",
    "stale": "INTEGER NOT NULL DEFAULT 0",
}
```

- [ ] **Step 4: 重写 `seed_model_routes()` 为增量同步**

在 `llmnode/storage/db.py` 中把当前差集删除逻辑移除，改成：

```python
def seed_model_routes(conn: sqlite3.Connection, routes: list[dict[str, Any]]) -> None:
    desired_names = {route["name"] for route in routes}
    existing = {item["name"]: item for item in list_model_routes(conn)}

    for name, current in existing.items():
        if current.get("source_kind", "profile_seed") == "profile_seed" and name not in desired_names:
            conn.execute(
                "UPDATE model_routes SET stale = 1, enabled = 0 WHERE name = ?",
                (name,),
            )

    for route in routes:
        current = existing.get(route["name"])
        if current and current.get("source_kind") == "manual":
            continue
        payload = {
            **route,
            "source_kind": "profile_seed",
            "source_ref": route.get("source_ref"),
            "stale": 0,
        }
        upsert_model_route(conn, payload)

    conn.commit()
```

- [ ] **Step 5: 扩展 `upsert_model_route()` 与 `list_model_routes()`**

在 `llmnode/storage/db.py` 中把新增字段串到 SQL：

```python
INSERT INTO model_routes(
    name, display_name, backend_model, backend_type, enabled,
    lifecycle_mode, upstream_protocol, upstream_base_url, upstream_model,
    upstream_auth_kind, upstream_auth_ref, capabilities_json,
    source_kind, source_ref, stale
)
```

以及：

```python
SELECT name, display_name, backend_model, backend_type, enabled,
       lifecycle_mode, upstream_protocol, upstream_base_url, upstream_model,
       upstream_auth_kind, upstream_auth_ref, capabilities_json,
       source_kind, source_ref, stale
FROM model_routes
```

- [ ] **Step 6: 运行测试确认通过**

Run: `PYTHONPATH=/proj02/liuheshan/llmnode pytest tests/test_storage_model_routes.py -v`  
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add llmnode/models.py llmnode/storage/db.py tests/test_storage_model_routes.py
git commit -m "feat: 将 model_routes 升级为长期注册表"
```

## Task 2: 后端 admin models create/delete API

**Files:**
- Modify: `llmnode/api/app.py`
- Modify: `llmnode/storage/db.py`
- Test: `tests/test_admin_model_routes.py`

- [ ] **Step 1: 写失败测试，表达 external route 可创建、manual route 可删除、profile_seed route 不可删除**

```python
def test_admin_can_create_external_route(client, admin_headers):
    response = client.post(
        "/admin/models",
        headers=admin_headers,
        json={
            "name": "openai-gpt-4.1",
            "display_name": "OpenAI GPT-4.1",
            "lifecycle_mode": "external",
            "upstream_protocol": "responses",
            "upstream_base_url": "https://api.openai.com/v1",
            "upstream_model": "gpt-4.1",
            "upstream_auth_kind": "bearer",
            "upstream_auth_ref": "OPENAI_KEY",
            "enabled": True,
            "capabilities_json": {"supports_responses": True},
        },
    )
    assert response.status_code == 200
    payload = response.json()["model"]
    assert payload["source_kind"] == "manual"
    assert payload["name"] == "openai-gpt-4.1"


def test_admin_cannot_delete_profile_seed_route(client, admin_headers):
    response = client.delete("/admin/models/qwen36-27b-fp8", headers=admin_headers)
    assert response.status_code == 409


def test_admin_can_delete_manual_route(client, admin_headers):
    create = client.post(
        "/admin/models",
        headers=admin_headers,
        json={
            "name": "anthropic-claude",
            "display_name": "Anthropic Claude",
            "lifecycle_mode": "external",
            "upstream_protocol": "messages",
            "upstream_base_url": "https://api.anthropic.com",
            "upstream_model": "claude-sonnet",
            "upstream_auth_kind": "x_api_key",
            "upstream_auth_ref": "ANTHROPIC_KEY",
        },
    )
    assert create.status_code == 200

    delete = client.delete("/admin/models/anthropic-claude", headers=admin_headers)
    assert delete.status_code == 200
    assert delete.json() == {"deleted": True, "name": "anthropic-claude"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONPATH=/proj02/liuheshan/llmnode pytest tests/test_admin_model_routes.py -v`  
Expected: FAIL，原因应是缺少 `POST /admin/models` / `DELETE /admin/models/{name}`

- [ ] **Step 3: 增加存储层删除 helper**

在 `llmnode/storage/db.py` 中新增：

```python
def delete_model_route(conn: sqlite3.Connection, name: str) -> bool:
    cursor = conn.execute("DELETE FROM model_routes WHERE name = ?", (name,))
    conn.commit()
    return cursor.rowcount > 0
```

- [ ] **Step 4: 在 `llmnode/api/app.py` 增加 create payload 校验**

新增 helper，最小约束：

```python
def _validate_create_model_route_payload(payload: dict[str, Any]) -> ModelRoute:
    name = _normalize_name(payload["name"])
    display_name = _normalize_name(payload.get("display_name", name), "display_name")
    lifecycle_mode = str(payload["lifecycle_mode"]).strip()
    if lifecycle_mode != "external":
        raise HTTPException(status_code=400, detail="phase1 only supports external route creation")
    upstream_protocol = str(payload["upstream_protocol"]).strip()
    upstream_base_url = _normalize_optional_string(payload.get("upstream_base_url"), "upstream_base_url")
    upstream_model = _normalize_optional_string(payload.get("upstream_model"), "upstream_model")
    if not upstream_base_url or not upstream_model:
        raise HTTPException(status_code=400, detail="upstream_base_url and upstream_model are required")
    upstream_auth_kind = str(payload.get("upstream_auth_kind", "none")).strip()
    upstream_auth_ref = _normalize_optional_string(payload.get("upstream_auth_ref"), "upstream_auth_ref")
    if upstream_auth_kind != "none" and not upstream_auth_ref:
        raise HTTPException(status_code=400, detail="upstream_auth_ref is required when upstream_auth_kind is not none")
    capabilities_json = _normalize_capabilities_payload(payload.get("capabilities_json", {}), ModelRoute(name=name, display_name=display_name))
    return ModelRoute(
        name=name,
        display_name=display_name,
        backend_model=None,
        backend_type=None,
        enabled=_normalize_bool(payload.get("enabled", True), "enabled"),
        lifecycle_mode="external",
        upstream_protocol=upstream_protocol,
        upstream_base_url=upstream_base_url,
        upstream_model=upstream_model,
        upstream_auth_kind=upstream_auth_kind,
        upstream_auth_ref=upstream_auth_ref,
        capabilities=ModelCapabilities(**capabilities_json),
        source_kind="manual",
        source_ref=None,
        stale=False,
    )
```

- [ ] **Step 5: 增加 `POST /admin/models` 与 `DELETE /admin/models/{name}`**

在 `llmnode/api/app.py` 中加入：

```python
@app.post("/admin/models")
async def admin_create_model(request: Request):
    _resolve_auth(request, "admin")
    payload = _validate_create_model_route_payload(await _read_json_body(request))
    if payload.name in request.app.state.ctx.models:
        raise HTTPException(status_code=409, detail=f"model already exists: {payload.name}")
    request.app.state.ctx.models[payload.name] = payload
    upsert_model_route(request.app.state.db, _build_model_route_storage_payload(payload))
    response = JSONResponse({"model": model_routes_for_admin({payload.name: payload})[0]})
    response.headers["x-request-id"] = _request_id(request)
    return response


@app.delete("/admin/models/{name}")
async def admin_delete_model(request: Request, name: str):
    _resolve_auth(request, "admin")
    route = request.app.state.ctx.models.get(name)
    if route is None:
        raise HTTPException(status_code=404, detail=f"unknown model: {name}")
    if route.source_kind != "manual":
        raise HTTPException(status_code=409, detail="profile_seed routes cannot be deleted; disable them instead")
    delete_model_route(request.app.state.db, name)
    request.app.state.ctx.models.pop(name, None)
    response = JSONResponse({"deleted": True, "name": name})
    response.headers["x-request-id"] = _request_id(request)
    return response
```

- [ ] **Step 6: 收紧 patch 边界**

在 `_validate_update_model_route_payload()` 中增加规则：

```python
if route.source_kind == "profile_seed" and payload.get("lifecycle_mode") == "external":
    raise HTTPException(status_code=409, detail="profile_seed routes cannot be converted to manual external routes")
```

并确保 patch 结果保留：

```python
source_kind=route.source_kind,
source_ref=route.source_ref,
stale=route.stale,
```

- [ ] **Step 7: 运行测试确认通过**

Run: `PYTHONPATH=/proj02/liuheshan/llmnode pytest tests/test_admin_model_routes.py -v`  
Expected: PASS

- [ ] **Step 8: 提交**

```bash
git add llmnode/api/app.py llmnode/storage/db.py tests/test_admin_model_routes.py
git commit -m "feat: 增加 route 新增与删除管理接口"
```

## Task 3: 管理台 route 来源、stale、新增与删除动作

**Files:**
- Modify: `web-console/src/store.tsx`
- Modify: `web-console/src/pages/ModelRoutesView.tsx`
- Modify: `web-console/src/i18n.ts`
- Test: `web-console/src/pages/ConsoleViews.test.tsx`

- [ ] **Step 1: 写失败测试，表达模型页应展示来源并支持 manual route 删除**

```tsx
it('shows route source badges and delete action for manual routes', async () => {
  render(<App />);
  const user = userEvent.setup();

  const modelsTab = await screen.findByRole('button', {name: /models/i});
  await user.click(modelsTab);

  expect(await screen.findByText(/Profile Seed/i)).toBeInTheDocument();
  expect(await screen.findByText(/Manual/i)).toBeInTheDocument();
  expect(screen.getByRole('button', {name: /Delete anthropic-claude/i})).toBeInTheDocument();
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /proj02/liuheshan/llmnode/web-console && npm test -- src/pages/ConsoleViews.test.tsx`  
Expected: FAIL，原因应是来源标识和删除按钮不存在

- [ ] **Step 3: 扩展前端 store 类型与 API**

在 `web-console/src/store.tsx` 的 `ModelRouteRow` 中新增：

```ts
source_kind: 'profile_seed' | 'manual';
source_ref: string | null;
stale: boolean;
```

并补两个方法：

```ts
async function createModelRoute(payload: Partial<ModelRouteRow>) { ... }
async function deleteModelRoute(name: string) { ... }
```

- [ ] **Step 4: 在 `ModelRoutesView.tsx` 增加来源展示与条件动作**

最小 UI 规则：

```tsx
<span className="badge">{route.source_kind === 'manual' ? t('models.sourceManual') : t('models.sourceProfileSeed')}</span>
{route.stale ? <span className="badge badge-warning">{t('models.stale')}</span> : null}
{route.source_kind === 'manual' ? (
  <button onClick={() => void handleDelete(route.name)}>{t('common.delete')}</button>
) : null}
```

并补一个 external create 表单入口，字段仅包含：

```tsx
name, display_name, upstream_protocol, upstream_base_url, upstream_model, upstream_auth_kind, upstream_auth_ref
```

- [ ] **Step 5: 补国际化文案**

在 `web-console/src/i18n.ts` 补最小键：

```ts
'models.sourceProfileSeed': 'Profile Seed',
'models.sourceManual': 'Manual',
'models.stale': 'Stale',
'models.createRoute': 'Create Route',
'models.deleteRoute': 'Delete Route',
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd /proj02/liuheshan/llmnode/web-console && npm test -- src/pages/ConsoleViews.test.tsx`  
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add web-console/src/store.tsx web-console/src/pages/ModelRoutesView.tsx web-console/src/i18n.ts web-console/src/pages/ConsoleViews.test.tsx
git commit -m "feat: 增加 route 来源与 external route 管理界面"
```

## Task 4: 文档回流与命令级验证

**Files:**
- Modify: `docs/blueprint/current.md`
- Modify: `docs/contracts/backend-routing.md`
- Modify: `docs/process/run.md`

- [ ] **Step 1: 回流 current.md 的当前状态描述**

在 `docs/blueprint/current.md` 增加或改写以下事实：

```md
- `model_routes` 已升级为单机节点上的长期 route 注册表
- 启动 seed 只同步 profile 默认本地供给，不再清空 manual route
- phase 1 已支持 external route 新增与 manual route 删除
- `profile_seed` route 当前只支持编辑与禁用，不支持物理删除
```

- [ ] **Step 2: 回流 backend-routing 契约**

在 `docs/contracts/backend-routing.md` 增加：

```md
- `source_kind`：route 来源，`profile_seed / manual`
- `source_ref`：来源引用，profile seed 时为 profile 名
- `stale`：该 route 是否已脱离当前激活 profile 的默认供给
- `POST /admin/models` phase 1 仅允许 external create
- `DELETE /admin/models/{name}` phase 1 仅允许删除 manual route
```

- [ ] **Step 3: 回流 run.md 的启动与排障语义**

在 `docs/process/run.md` 增加最小说明：

```md
- 启动时 route seed 改为增量同步
- profile 切换后旧 profile route 可能被标记为 stale 且自动 disabled
- stale route 不会自动消失，需在管理台确认处理
```

- [ ] **Step 4: 运行最小回归检查**

Run: `rg -n "source_kind|profile_seed|manual route|stale" docs/blueprint/current.md docs/contracts/backend-routing.md docs/process/run.md`  
Expected: 输出包含新增文案，且无拼写分叉

- [ ] **Step 5: 运行本轮直接相关测试**

Run:

```bash
PYTHONPATH=/proj02/liuheshan/llmnode pytest tests/test_storage_model_routes.py tests/test_admin_model_routes.py -v
cd /proj02/liuheshan/llmnode/web-console && npm test -- src/pages/ConsoleViews.test.tsx
```

Expected:

- pytest PASS
- 前端测试 PASS

- [ ] **Step 6: 提交**

```bash
git add docs/blueprint/current.md docs/contracts/backend-routing.md docs/process/run.md
git commit -m "docs: 回流 route 注册表平台化边界"
```

## Self-Review

- Spec coverage:
  - route 决策、对象边界、seed 增量同步、external create、manual delete、stale 管理、文档回流都已对应到 Task 1-4
  - managed_local create/delete 明确不进入本计划
- Placeholder scan:
  - 未发现占位词或空步骤
  - 所有任务都给了明确文件和命令
- Type consistency:
  - 统一使用 `source_kind / source_ref / stale`
  - 统一使用 `profile_seed / manual`

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-18-route-management-rollout-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
