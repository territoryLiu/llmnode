# Gateway Native Pass-Through Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 gateway 默认行为从“默认适配/默认语义改写”收敛为“原生协议优先、默认透明转发、adapter 显式开启”，并完成协议能力、工具能力、错误语义与文档回流的渐进迁移。

**Architecture:** 先在运行时引入新的 route 语义模型与显式判定流程，保持旧字段兼容读取；再逐步把 adapter 从默认路径降为显式路径，拆分工具能力语义，最后迁移 DB / 管理台字段并清理旧的隐式兼容逻辑。整条实施链路以 `managed_local + vLLM` 为优先验证对象，同时保留 `llama.cpp / SGLang / external` 的保守声明策略。

**Tech Stack:** Python, FastAPI, Pydantic, SQLite, pytest, existing llmnode gateway/router/admin UI stack

---

## File Structure

本计划预期主要涉及以下文件：

- Modify: `llmnode/models.py`
  - 引入新的 route 运行时语义承载方式，兼容旧字段并派生 `native_protocols / adapter_policies / tool_policies / protocol_features`
- Modify: `llmnode/proxy/router.py`
  - 重写 route 判定主流程，区分 native pass-through、adapter opt-in、tool policy gate
- Modify: `llmnode/api/app.py`
  - 收敛 `/v1/messages`、`/v1/chat/completions`、`/v1/responses` 的 route-aware 调度与错误码输出
- Modify: `llmnode/storage/db.py`
  - 为后续持久化扩展 route 能力字段做迁移准备
- Modify: `tests/test_api_anthropic.py`
  - 固化 Anthropic function tool / builtin tool / count_tokens 的新语义
- Modify: `tests/test_api_responses.py`
  - 固化 responses 适配必须显式开启的约束
- Modify: `tests/test_model_routes_phase1.py`
  - 调整 route 能力判定与错误码回归
- Modify: `docs/contracts/backend-routing.md`
  - 回流正式契约描述
- Modify: `docs/blueprint/current.md`
  - 回流当前系统行为
- Create or Modify: `docs/superpowers/specs/2026-05-18-gateway-native-pass-through-design.md`
  - 若实现过程中边界有细化，回写 spec

若管理台阶段纳入本轮，还将涉及：

- Modify: `web-console/src/...`
  - 具体文件待实施前按当前 UI 结构定位，用于展示 `native_protocols / adapter_policies / tool_policies`

## Task 1: 建立 Route 新语义的运行时派生层

**Files:**
- Modify: `llmnode/models.py`
- Test: `tests/test_model_routes_phase1.py`

- [ ] **Step 1: 写失败测试，定义新能力语义的最小派生预期**

```python
def test_managed_local_vllm_route_derives_native_protocols():
    route = ModelRoute(
        name="qwen36-27b-awq-int4",
        display_name="Qwen",
        backend_model="qwen36-27b-awq-int4",
        backend_type="vllm",
        lifecycle_mode="managed_local",
    )

    runtime = route.runtime_capabilities()

    assert runtime["native_protocols"] == ["chat", "responses", "messages"]
    assert runtime["adapter_policies"] == []
    assert runtime["tool_policies"]["anthropic_function_tools"] is True
    assert runtime["tool_policies"]["builtin_tools"] is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_model_routes_phase1.py::test_managed_local_vllm_route_derives_native_protocols -v`
Expected: FAIL with missing method or missing runtime capability fields

- [ ] **Step 3: 在 `llmnode/models.py` 中写最小实现**

```python
@dataclass(frozen=True)
class ModelRoute:
    ...

    def runtime_capabilities(self) -> dict[str, Any]:
        if self.lifecycle_mode == "managed_local" and self.backend_type == "vllm":
            return {
                "native_protocols": ["chat", "responses", "messages"],
                "adapter_policies": [],
                "tool_policies": {
                    "openai_function_tools": True,
                    "anthropic_function_tools": True,
                    "builtin_tools": False,
                },
                "protocol_features": {
                    "stream": self.capabilities.supports_stream,
                    "count_tokens": True,
                    "json_schema": self.capabilities.supports_json_schema,
                    "previous_response_id": self.capabilities.supports_previous_response_id_native,
                },
            }
        ...
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_model_routes_phase1.py::test_managed_local_vllm_route_derives_native_protocols -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add llmnode/models.py tests/test_model_routes_phase1.py
git commit -m "feat: derive route runtime capabilities for native pass-through"
```

## Task 2: 将 Router 主判定改成 Native Pass-Through First

**Files:**
- Modify: `llmnode/proxy/router.py`
- Test: `tests/test_model_routes_phase1.py`

- [ ] **Step 1: 写失败测试，定义协议不一致时默认保守失败**

```python
def test_route_rejects_messages_when_not_in_native_protocols():
    route = ModelRoute(
        name="chat-only",
        display_name="Chat Only",
        lifecycle_mode="external",
        upstream_protocol="chat",
    )
    route_runtime = {
        "native_protocols": ["chat"],
        "adapter_policies": [],
        "tool_policies": {
            "openai_function_tools": True,
            "anthropic_function_tools": False,
            "builtin_tools": False,
        },
        "protocol_features": {"stream": True},
    }

    req = NormalizedRequest(client_protocol="messages", model="chat-only", messages=[])

    with pytest.raises(HTTPException) as exc_info:
        ensure_route_supports_request(route, req, runtime_caps=route_runtime)

    assert exc_info.value.detail == "native_protocol_not_supported"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_model_routes_phase1.py::test_route_rejects_messages_when_not_in_native_protocols -v`
Expected: FAIL because `ensure_route_supports_request` does not accept runtime capabilities or still emits old detail

- [ ] **Step 3: 修改 `llmnode/proxy/router.py` 的主判定逻辑**

```python
def ensure_route_supports_request(
    route: ModelRoute,
    req: NormalizedRequest,
    *,
    runtime_caps: dict[str, Any] | None = None,
) -> None:
    caps = runtime_caps or route.runtime_capabilities()
    native_protocols = caps["native_protocols"]

    if req.client_protocol not in native_protocols:
        raise HTTPException(status_code=400, detail="native_protocol_not_supported")

    if req.stream and not caps["protocol_features"].get("stream", False):
        raise HTTPException(status_code=400, detail="stream_not_supported_for_model")

    ...
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_model_routes_phase1.py::test_route_rejects_messages_when_not_in_native_protocols -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add llmnode/proxy/router.py tests/test_model_routes_phase1.py
git commit -m "feat: prefer native protocol pass-through in router"
```

## Task 3: 把 Adapter 从默认路径改成显式启用

**Files:**
- Modify: `llmnode/proxy/router.py`
- Modify: `llmnode/api/app.py`
- Test: `tests/test_api_responses.py`

- [ ] **Step 1: 写失败测试，定义 adapter 未启用时返回明确错误**

```python
def test_responses_to_chat_requires_explicit_adapter_policy():
    route = ModelRoute(
        name="chat-only",
        display_name="Chat Only",
        lifecycle_mode="external",
        upstream_protocol="chat",
    )
    runtime_caps = {
        "native_protocols": ["chat"],
        "adapter_policies": [],
        "tool_policies": {
            "openai_function_tools": True,
            "anthropic_function_tools": False,
            "builtin_tools": False,
        },
        "protocol_features": {"stream": True},
    }

    req = NormalizedRequest(client_protocol="responses", model="chat-only", messages=[])

    with pytest.raises(HTTPException) as exc_info:
        select_upstream_adapter(route, req, runtime_caps=runtime_caps)

    assert exc_info.value.detail == "adapter_not_enabled_for_route"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_api_responses.py::test_responses_to_chat_requires_explicit_adapter_policy -v`
Expected: FAIL because adapter selection still uses old fallback

- [ ] **Step 3: 修改 adapter 选择逻辑**

```python
def select_upstream_adapter(
    route: ModelRoute,
    req: NormalizedRequest,
    *,
    runtime_caps: dict[str, Any] | None = None,
) -> str:
    caps = runtime_caps or route.runtime_capabilities()
    allowed = set(caps["adapter_policies"])

    if req.client_protocol == "responses" and "responses->chat" in allowed:
        return "responses_to_chat"
    if req.client_protocol == "responses" and "responses->messages" in allowed:
        return "responses_to_messages"
    raise HTTPException(status_code=400, detail="adapter_not_enabled_for_route")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_api_responses.py::test_responses_to_chat_requires_explicit_adapter_policy -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add llmnode/proxy/router.py llmnode/api/app.py tests/test_api_responses.py
git commit -m "feat: require explicit adapter policy for protocol conversion"
```

## Task 4: 拆分工具能力语义

**Files:**
- Modify: `llmnode/proxy/router.py`
- Modify: `llmnode/api/app.py`
- Test: `tests/test_api_anthropic.py`
- Test: `tests/test_model_routes_phase1.py`

- [ ] **Step 1: 写失败测试，区分 Anthropic function tools 与 builtin tools**

```python
def test_anthropic_function_tools_use_dedicated_error_code():
    route = ModelRoute(
        name="chat-only",
        display_name="Chat Only",
        backend_model="chat-only",
    )
    runtime_caps = {
        "native_protocols": ["messages"],
        "adapter_policies": [],
        "tool_policies": {
            "openai_function_tools": True,
            "anthropic_function_tools": False,
            "builtin_tools": False,
        },
        "protocol_features": {"stream": True},
    }
    req = NormalizedRequest(
        client_protocol="messages",
        model="chat-only",
        messages=[],
        tools=[{
            "name": "Read",
            "description": "Read files",
            "input_schema": {"type": "object"},
        }],
    )

    with pytest.raises(HTTPException) as exc_info:
        ensure_route_supports_request(route, req, runtime_caps=runtime_caps)

    assert exc_info.value.detail == "anthropic_function_tools_not_supported"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_model_routes_phase1.py::test_anthropic_function_tools_use_dedicated_error_code -v`
Expected: FAIL because old coarse error detail is still used

- [ ] **Step 3: 修改工具分类与报错**

```python
for tool in req.tools or []:
    tool_type = tool.get("type")
    if tool_type == "function":
        if not tool_policies["openai_function_tools"]:
            raise HTTPException(status_code=400, detail="openai_function_tools_not_supported")
        continue
    if tool_type is None and is_anthropic_function_tool(tool):
        if not tool_policies["anthropic_function_tools"]:
            raise HTTPException(status_code=400, detail="anthropic_function_tools_not_supported")
        continue
    if not tool_policies["builtin_tools"]:
        raise HTTPException(status_code=400, detail="builtin_tools_not_supported")
```

- [ ] **Step 4: 运行定向测试确认通过**

Run: `pytest tests/test_api_anthropic.py tests/test_model_routes_phase1.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add llmnode/proxy/router.py llmnode/api/app.py tests/test_api_anthropic.py tests/test_model_routes_phase1.py
git commit -m "feat: split route tool policy semantics by protocol family"
```

## Task 5: 收紧 `/v1/messages` 与 `count_tokens` 的 Native 语义

**Files:**
- Modify: `llmnode/api/app.py`
- Test: `tests/test_api_anthropic.py`

- [ ] **Step 1: 写失败测试，确保 native messages 路径不静默改写 Anthropic function tools**

```python
def test_native_messages_path_keeps_anthropic_function_tools_unmutated():
    ...
    assert captured_payload["tools"][0]["name"] == "Read"
    assert captured_payload["tools"][0]["input_schema"]["type"] == "object"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_api_anthropic.py::test_native_messages_path_keeps_anthropic_function_tools_unmutated -v`
Expected: FAIL if payload still gets stripped or mutated

- [ ] **Step 3: 修改 `/v1/messages` 入口，仅保留 builtin metadata 最小过滤**

```python
sanitized_raw = strip_claude_code_builtin_tools_for_managed_messages(route, raw)
payload = AnthropicMessagesRequest.model_validate(sanitized_raw)
# 后续不再对 anthropic function tools 做兼容性剥离
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_api_anthropic.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add llmnode/api/app.py tests/test_api_anthropic.py
git commit -m "fix: preserve anthropic function tools on native messages path"
```

## Task 6: 增加 execution_mode / mutation 结构化日志

**Files:**
- Modify: `llmnode/api/app.py`
- Test: `tests/test_api_metrics.py`

- [ ] **Step 1: 写失败测试，要求请求日志包含 execution mode**

```python
def test_request_log_marks_native_execution_mode():
    payload = fetch_latest_request_log(...)
    assert payload["metadata"]["execution_mode"] == "native"
    assert payload["metadata"]["request_mutation"] is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_api_metrics.py::test_request_log_marks_native_execution_mode -v`
Expected: FAIL because metadata fields are missing

- [ ] **Step 3: 在日志写入点补充结构化字段**

```python
log_context["metadata"] = {
    "client_protocol": "messages",
    "execution_mode": execution_mode,
    "adapter_selected": adapter_selected,
    "tool_classes_detected": tool_classes_detected,
    "request_mutation": request_mutation,
    "mutation_reason": mutation_reason,
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_api_metrics.py::test_request_log_marks_native_execution_mode -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add llmnode/api/app.py tests/test_api_metrics.py
git commit -m "feat: record execution mode and mutation metadata in request logs"
```

## Task 7: 迁移 DB 与管理台字段

**Files:**
- Modify: `llmnode/storage/db.py`
- Modify: `llmnode/models.py`
- Modify: `llmnode/api/app.py`
- Modify: `web-console/src/...`
- Test: `tests/test_model_routes_phase1.py`

- [ ] **Step 1: 写失败测试，要求 model route 可持久化新能力字段**

```python
def test_model_route_persists_native_protocols_and_tool_policies(tmp_path):
    ...
    assert row["native_protocols_json"] == ["chat", "responses", "messages"]
    assert row["tool_policies_json"]["anthropic_function_tools"] is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_model_routes_phase1.py::test_model_route_persists_native_protocols_and_tool_policies -v`
Expected: FAIL because DB schema and API payload do not yet support new fields

- [ ] **Step 3: 增加持久化与管理台字段**

```python
# db schema migration / row mapping
"native_protocols_json": json.dumps(native_protocols),
"adapter_policies_json": json.dumps(adapter_policies),
"tool_policies_json": json.dumps(tool_policies),
"protocol_features_json": json.dumps(protocol_features),
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_model_routes_phase1.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add llmnode/storage/db.py llmnode/models.py llmnode/api/app.py web-console/src
git commit -m "feat: persist route native protocols and tool policies"
```

## Task 8: 回流正式文档并删除旧隐式语义

**Files:**
- Modify: `docs/contracts/backend-routing.md`
- Modify: `docs/blueprint/current.md`
- Modify: `docs/process/development-workflow.md`
- Test: `tests/test_api_anthropic.py`
- Test: `tests/test_api_responses.py`

- [ ] **Step 1: 写文档回流检查点**

```text
需要回流的正式语义：
- native pass-through first
- adapter opt-in only
- tool policies split
- builtin tools still rejected by default
```

- [ ] **Step 2: 修改正式文档**

```markdown
- `managed_local + vLLM` 默认按 `chat / responses / messages` 原生透传
- adapter 仅在 route 显式启用时允许生效
- 工具语义现按 OpenAI function / Anthropic function / builtin 分开治理
```

- [ ] **Step 3: 运行定向回归测试**

Run: `pytest tests/test_api_anthropic.py tests/test_api_responses.py tests/test_model_routes_phase1.py -q`
Expected: PASS

- [ ] **Step 4: 手动检查文档关键词**

Run: `rg -n "native pass-through|adapter opt-in|anthropic function|builtin tools" docs/contracts/backend-routing.md docs/blueprint/current.md docs/process/development-workflow.md`
Expected: matching lines in all three files

- [ ] **Step 5: Commit**

```bash
git add docs/contracts/backend-routing.md docs/blueprint/current.md docs/process/development-workflow.md
git commit -m "docs: backfill gateway native pass-through governance model"
```

## Self-Review

### Spec coverage

本计划已覆盖 spec 中以下关键部分：

- 原生协议优先：Task 1, Task 2
- adapter 显式开启：Task 3
- 工具能力语义拆分：Task 4, Task 5
- 错误语义与日志语义：Task 2, Task 3, Task 4, Task 6
- DB / 管理台迁移：Task 7
- 正式文档回流：Task 8

当前未展开到具体前端文件路径，是因为管理台结构在实施前需要按现状定位；这不影响计划范围，但执行 Task 7 前应先锁定具体 UI 文件。

### Placeholder scan

已避免使用 `TODO / TBD / implement later / add appropriate handling` 等占位式措辞。  
唯一保留的 `web-console/src/...` 是计划层面的路径待定位提醒，执行 Task 7 前必须先替换成实际文件路径，不可直接按省略路径实施。

### Type consistency

计划中统一使用以下运行时语义名称：

- `native_protocols`
- `adapter_policies`
- `tool_policies`
- `protocol_features`
- `execution_mode`
- `adapter_selected`
- `request_mutation`

后续实现中不得再引入同义但不同名的新字段，以免和 spec 漂移。

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-18-gateway-native-pass-through-rollout-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?

