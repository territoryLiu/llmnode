# Gateway Native Pass-Through First 设计方案

日期：2026-05-18

## 1. 背景

当前项目的 gateway 同时承担了统一入口、鉴权治理、协议兼容和 route-aware 分发职责。随着 `Claude Code`、`Codex`、`Cherry Studio` 等客户端接入，现有设计暴露出一个核心问题：

- 当客户端协议与后端协议本来已经原生兼容时，gateway 仍可能介入修改 payload；
- 这种修改会破坏客户端与后端之间已经成立的工具协议或消息语义；
- 当前默认后端 `vLLM` 已原生支持 `/v1/chat/completions`、`/v1/responses`、`/v1/messages` 以及 `/v1/messages/count_tokens`，但 gateway 仍保留了“默认适配/默认清洗”的旧路径；
- 最典型的问题是 Anthropic 风格 function tool（`name + description + input_schema`）曾被误判成 builtin tool，导致 Claude Code 工程能力退化。

因此，需要把 gateway 的主设计从“默认适配优先”调整为“原生协议优先、默认透明转发、适配显式开启”。

## 2. 设计目标

本方案目标如下：

1. 对于客户端协议与 route 原生支持协议一致的情况，gateway 不修改业务 payload，只做外围治理。
2. 对于协议不一致的情况，gateway 默认保守失败，而不是自动转换。
3. 将“原生协议支持”“适配策略”“工具能力”“协议辅助能力”拆成独立语义，避免旧字段混用。
4. 保留 adapter 能力，但必须由 route 显式启用。
5. 让日志与错误码可以直接反映：当前请求是原生透传、显式适配还是被拒绝。
6. 在不推翻现有运行栈的前提下，提供一条低风险渐进迁移路径。

## 3. 非目标

本方案不包含以下目标：

- 不重新设计 `llmnode.control`、node-agent、Docker 编排主逻辑；
- 不引入多节点调度；
- 不定义新的客户端 SDK；
- 不承诺为所有后端默认提供三协议原生支持；
- 不把 builtin tools 执行下放到 gateway；
- 不把当前 spec 直接视为长期真相源，后续稳定语义需回流到 `blueprint / contracts / process`。

## 4. 核心原则

### 4.1 Native Pass-Through First

只要 route 原生支持客户端协议，gateway 默认透明转发。

透明转发的含义是：

- 可以改外围路由信息，例如目标 model 名、上游认证头；
- 不改业务语义字段，例如 `messages`、`tools`、`tool_choice`、`tool_result`、`response_format`、`stream`。

### 4.2 Adapter Opt-In Only

如果客户端协议不在 route 原生支持集合内：

- 默认直接拒绝；
- 只有在 route 显式启用了某个 adapter 时，才允许转换。

这意味着 adapter 是可选能力，而不是默认兜底逻辑。

### 4.3 Governance Without Silent Mutation

gateway 可以做治理，但不能静默篡改语义。

- 支持则放行；
- 不支持则明确报错；
- 除 builtin tool metadata 的最小过滤外，不允许再出现“为了能过先剥字段”的兼容手段；
- 任何真正的 payload 改写，都必须进入显式 adapter 路径并被日志记录。

## 5. Route 能力模型重构

每条 route 的运行时能力拆成四组语义。

### 5.1 native_protocols

表示该 route 原生支持哪些客户端协议。

示例：

```json
["chat", "responses", "messages"]
```

运行时判定是否走 native pass-through，只看这组字段，不再从 `backend_type` 侧推。

### 5.2 adapter_policies

表示 route 显式允许哪些跨协议适配。

示例：

```json
["responses->chat", "responses->messages"]
```

默认值为空。为空表示不允许自动转换。

### 5.3 tool_policies

表示该 route 支持哪些工具语义。

建议拆成：

```json
{
  "openai_function_tools": true,
  "anthropic_function_tools": true,
  "builtin_tools": false
}
```

其中：

- `type == "function"` 视为 OpenAI function tools；
- `name + description + input_schema` 视为 Anthropic function tools；
- `bash_* / web_search_* / text_editor_*` 等视为 builtin tools。

### 5.4 protocol_features

表示协议级辅助能力，而不是主路由能力。

示例：

```json
{
  "stream": true,
  "json_schema": true,
  "previous_response_id": true,
  "count_tokens": true
}
```

这些能力用于 feature gate 和管理台展示，不参与“native 还是 adapted”的主决策。

## 6. Gateway 运行时决策流程

每次请求固定走以下六步：

1. 认证与治理前置  
   处理 API key、限流、并发、审计上下文。不碰业务 payload。

2. route 解析  
   根据逻辑模型名读取 route，并取得 `native_protocols / adapter_policies / tool_policies / protocol_features`。

3. 协议判定  
   - 若 `client_protocol in native_protocols`，进入 native path；
   - 否则检查 `adapter_policies`；
   - 若无命中，直接返回 `native_protocol_not_supported` 或 `adapter_not_enabled_for_route`。

4. 工具判定  
   识别请求中的工具类别，只做放行或拒绝：
   - OpenAI function tools；
   - Anthropic function tools；
   - builtin tools。

5. 执行路径  
   - native path：保持 payload 语义不变；
   - adapter path：仅在显式允许时执行映射。

6. 响应回传  
   - native path：尽量原样回传；
   - adapter path：做对应反向映射，并标记 adapted。

## 7. 分层策略

### 7.1 managed_local + vLLM

这是当前系统主路径，应采用最强的原生透传策略。

默认建议：

```json
{
  "native_protocols": ["chat", "responses", "messages"],
  "adapter_policies": [],
  "tool_policies": {
    "openai_function_tools": true,
    "anthropic_function_tools": true,
    "builtin_tools": false
  },
  "protocol_features": {
    "stream": true,
    "count_tokens": true
  }
}
```

原则：

- 默认全走 native；
- 不因为系统里存在 adapter 就降级到适配路径；
- gateway 不修改工具协议内容。

### 7.2 managed_local + llama.cpp / SGLang

按真实能力声明，不跟随 `vLLM` 脑补支持。

原则：

- 原生支持什么就声明什么；
- `adapter_policies` 默认空；
- 若未来验证出更多原生能力，再逐步加。

### 7.3 external route

采用最保守策略。

原则：

- `native_protocols` 必须显式声明；
- `adapter_policies` 默认空；
- adapter 必须显式开启并在管理台带风险提示。

## 8. 配置模型与管理台重构

### 8.1 配置层

route 至少要能表达：

- 基础路由信息：
  - `name`
  - `lifecycle_mode`
  - `backend_type`
  - `backend_model`
  - `upstream_base_url`
  - `upstream_auth_kind`
  - `upstream_auth_ref`
- 协议层：
  - `native_protocols`
  - `adapter_policies`
- 工具层：
  - `tool_policies`
- 辅助能力层：
  - `protocol_features`

### 8.2 管理台

管理台不再以单一 `upstream_protocol` 作为核心视图，而应拆成：

1. 原生协议支持：多选 `chat / responses / messages`
2. 显式 adapter：多选，默认空
3. 工具能力：
   - OpenAI function tools
   - Anthropic function tools
   - builtin tools
4. 协议辅助能力：
   - stream
   - count_tokens
   - json_schema
   - previous_response_id

管理台需明确提示：

- adapter 会改变协议语义；
- builtin tools 开启风险高；
- 推荐优先走原生协议。

## 9. 错误语义与日志语义

### 9.1 错误码

建议新增或替换为：

- `native_protocol_not_supported`
- `adapter_not_enabled_for_route`
- `openai_function_tools_not_supported`
- `anthropic_function_tools_not_supported`
- `builtin_tools_not_supported`

避免继续使用过粗的：

- `unsupported_function_tools`
- `unsupported_builtin_tools`

### 9.2 结构化日志字段

每次请求至少记录：

```json
{
  "client_protocol": "messages",
  "route_name": "qwen36-27b-awq-int4",
  "execution_mode": "native",
  "native_protocols": ["chat", "responses", "messages"],
  "adapter_selected": null,
  "tool_classes_detected": ["anthropic_function"],
  "request_mutation": false
}
```

要求：

- `execution_mode` 仅允许 `native / adapted / rejected`
- 若 `request_mutation=true`，必须附带 `mutation_reason`
- 若 `execution_mode=adapted`，必须带 `adapter_selected`

## 10. 迁移路线

建议分五个阶段迁移。

### 阶段 1：运行时派生新语义

- 保留旧字段读取；
- 在内存中派生 `native_protocols / adapter_policies / tool_policies`；
- 对当前 `managed_local + vLLM` 派生为多协议原生支持。

### 阶段 2：adapter 改为显式开启

- 所有 adapter 使用前检查 `adapter_policies`；
- 未显式启用则保守失败。

### 阶段 3：拆分工具能力语义

- 将 `supports_function_tools / supports_builtin_tools` 迁移为更细的 `tool_policies`；
- 区分 OpenAI function、Anthropic function、builtin。

### 阶段 4：数据库与管理台字段正式迁移

- 持久化：
  - `native_protocols_json`
  - `adapter_policies_json`
  - `tool_policies_json`
  - `protocol_features_json`
- 管理台同步升级。

### 阶段 5：删除旧隐式兼容逻辑

- 删除默认 adapter 兜底；
- 删除旧的语义混用逻辑；
- 仅保留 builtin metadata 的最小过滤；
- 清理过时测试与文档。

## 11. 成功标准

落地后至少满足以下验收条件：

1. Claude Code -> `/v1/messages` -> vLLM：默认透明转发；
2. Cherry Studio -> `/v1/chat/completions` -> vLLM：默认透明转发；
3. route 不支持某协议时：明确失败，不偷偷转；
4. route 显式开启 adapter 时：日志明确 `execution_mode=adapted`；
5. Anthropic function tools 不再被误判为 builtin；
6. builtin tools 的拒绝语义与日志语义可单独识别。

## 12. 风险与权衡

### 风险

- 管理台与 DB 模型迁移需要额外工作量；
- 旧 route 的默认能力映射若不谨慎，可能短期暴露出更多“以前被自动适配掩盖”的问题；
- adapter 从默认兜底变为显式开启后，部分历史调用会从“勉强可用”变成“明确失败”。

### 权衡

这是一个有意的设计收紧：

- 短期会让不清晰的能力边界显性化；
- 长期会显著降低协议兼容排障成本；
- 对当前默认 `vLLM` 主链路，这是正确方向，因为它本来就已经具备原生多协议能力。

## 13. 后续回流建议

本 spec 稳定后，建议回流更新：

- `docs/contracts/backend-routing.md`
- `docs/blueprint/current.md`
- 必要时补充 `docs/process/development-workflow.md` 中与 route 能力声明相关的流程说明

