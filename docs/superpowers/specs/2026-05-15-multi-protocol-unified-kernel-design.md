# 多协议入口与统一执行内核设计

## 0. 文档定位

这份设计稿只回答下面几件事：

1. 为什么当前网关需要从“单后端、单协议假设”升级到“多协议入口、单执行内核”。
2. 对外三种协议入口应如何共存。
3. 模型路由、会话状态、上游适配层应如何重构。
4. 第一阶段实施范围、迁移顺序、风险点和回滚点是什么。

它不负责：

- 重复当前系统现状，那是 `docs/blueprint/current.md`
- 记录未来优先级，那是 `docs/blueprint/roadmap.md`
- 代替后续执行拆分，那应进入对应 `plan`

## 1. 背景

当前系统已经对外提供：

- `POST /v1/chat/completions`
- `POST /v1/messages`
- `POST /v1/responses`
- `GET /v1/models`

但内部真实执行链路仍然主要建立在以下假设之上：

- 默认只有一个主后端
- 路由语义主要由 `backend_type + backend_model` 表达
- OpenAI 风格请求主要按 `/v1/chat/completions` 转发
- `/v1/responses` 当前仍主要是 facade，而不是按模型能力选择 native responses 或 chat adapter

这套结构足以支持当前的单机本地推理网关主路径，但不足以覆盖下面的目标场景：

- Codex 只能稳定使用 `/v1/responses`
- Claude Code 更适合使用 `/v1/messages`
- 其他 OpenAI-compatible 客户端仍主要使用 `/v1/chat/completions`
- 同一个网关既要服务 OpenAI 官方模型，也要服务本地或兼容后端上的 Qwen 模型
- 不同模型的上游协议能力并不一致：
  - OpenAI 官方模型原生支持 `/v1/responses`
  - 本地 Qwen/vLLM 路线当前更稳定的是 `/v1/chat/completions`
  - Claude 原生客户端仍依赖 `/v1/messages`

因此，本次改造的核心不是增加一个接口，而是把系统从“多入口、各自直连”的结构升级为“多协议入口、统一执行内核、按模型能力选择上游协议”的结构。

## 2. 目标

本设计的目标是：

- 保持三种外部协议入口同时存在：
  - `/v1/responses`
  - `/v1/chat/completions`
  - `/v1/messages`
- 将三种外部请求先归一化为统一内部请求对象
- 根据逻辑模型绑定的 route 能力，选择合适的上游协议：
  - native responses
  - native chat
  - native messages
- 让 Codex 可以无感知地访问：
  - OpenAI 官方 responses-native 模型
  - 本地或兼容后端上的 Qwen chat-native 模型
- 保持 Claude Code 与现有 chat 客户端可继续使用，不因 Codex 支持而回归
- 让 `previous_response_id` 从局部 facade 能力升级为统一会话层能力
- 为后续 external upstream、更多模型和更多客户端预留稳定边界

## 3. 非目标

本设计第一阶段不追求下面能力：

- 不实现完整 OpenAI Agent 平台
- 不实现 built-in tools 的真实执行器
- 不保证 `/v1/responses` 与所有上游协议的无损互转
- 不在第一阶段重写 `node-agent`、`control.py` 的完整生命周期模型
- 不在第一阶段完成三种入口的完全统一执行链替换
- 不在第一阶段引入复杂凭据管理 UI

第一阶段只解决一个明确问题：

- 在不破坏现有 `Claude Code + chat 客户端` 的前提下，让 Codex 可以稳定使用同一个网关访问 OpenAI 官方模型和本地 Qwen 模型

## 4. 设计原则

### 4.1 多协议入口保留

系统不把外部协议统一收敛到 `/v1/responses`。  
三种入口都继续保留，因为客户端协议不是网关可以强制统一的。

### 4.2 内部统一的是执行模型，不是外部 URL

统一的不是：

- 入口 URL
- 原始请求字段

统一的是：

- 规范化请求对象
- 规范化结果对象
- route resolver
- capability guard
- upstream adapter registry
- conversation state

### 4.3 路由字段必须区分“本地后端类型”和“上游协议类型”

当前的 `backend_type` 语义过重。  
本次设计要求拆开：

- `backend_type`
  只表达本地受控推理后端类型
- `upstream_protocol`
  只表达真正对上游发请求时使用的协议
- `lifecycle_mode`
  表达该 route 属于本地受控还是外部上游

### 4.4 能力不做静默吞掉

当某条 route 不支持某种能力时，应显式失败，而不是伪装成功。  
例如：

- `responses + built-in tools` 打到 chat-native Qwen route 时，应返回明确的 unsupported error
- `json_schema` 在不支持的 route 上只能 best-effort 或拒绝，不应伪装成 fully supported

## 5. 目标架构

### 5.1 总体结构

系统按下面几层组织：

1. 协议入口层
   - `responses ingress`
   - `chat ingress`
   - `messages ingress`

2. 内部统一执行层
   - `NormalizedRequest`
   - `RouteTarget`
   - `CapabilityGuard`
   - `Executor`

3. 上游适配层
   - `native_responses_adapter`
   - `native_chat_adapter`
   - `native_messages_adapter`
   - 第一阶段仅强制落地：
     - `native_responses_adapter`
     - `responses_to_chat_adapter`

4. 会话与状态层
   - `response_states`
   - `previous_response_id` 统一续接逻辑
   - route-aware 上游状态记录

5. 编码回包层
   - `responses encoder`
   - `chat encoder`
   - `messages encoder`

### 5.2 第一阶段重点

第一阶段只把 `/v1/responses` 接入统一执行层。  
`/v1/chat/completions` 与 `/v1/messages` 先保留现有主链路，只为后续迁移预留接口和数据模型。

## 6. 路由模型重构

### 6.1 新的正式路由语义

`ModelRoute` 至少包含：

- `name`
- `display_name`
- `enabled`
- `lifecycle_mode`
- `backend_type`
- `backend_model`
- `upstream_protocol`
- `upstream_base_url`
- `upstream_model`
- `upstream_auth_kind`
- `upstream_auth_ref`
- `capabilities`

### 6.2 字段定义

- `name`
  - 客户端看到的逻辑模型名
- `display_name`
  - 管理台展示名
- `enabled`
  - 控制逻辑模型是否对外暴露
- `lifecycle_mode`
  - `managed_local | external`
- `backend_type`
  - `vllm | llama.cpp | sglang`
  - 仅对 `managed_local` route 有意义
- `backend_model`
  - 本地后端接收的模型名
- `upstream_protocol`
  - `responses | chat | messages`
- `upstream_base_url`
  - 上游根地址
- `upstream_model`
  - 实际发给上游的模型标识
- `upstream_auth_kind`
  - `none | bearer | x_api_key`
- `upstream_auth_ref`
  - 上游凭据引用
- `capabilities`
  - 结构化能力声明

### 6.3 第一阶段兼容策略

旧路由自动迁移为：

- `lifecycle_mode=managed_local`
- `upstream_protocol=chat`
- `upstream_base_url` 取当前本地后端地址
- `upstream_model=backend_model`
- `upstream_auth_kind=none`

这样现有本地 Qwen 主路径不需要先改配置就能继续运行。

## 7. 能力模型

### 7.1 最小能力字段

第一阶段 `capabilities_json` 至少包含：

- `supports_responses`
- `supports_chat`
- `supports_messages`
- `supports_stream`
- `supports_function_tools`
- `supports_builtin_tools`
- `supports_previous_response_id_native`
- `supports_json_schema`

### 7.2 典型 route 能力

OpenAI 官方 responses-native route：

- `supports_responses=true`
- `supports_chat=true`
- `supports_stream=true`
- `supports_function_tools=true`
- `supports_builtin_tools=true`
- `supports_previous_response_id_native=true`
- `supports_json_schema=true`

本地 Qwen chat-native route：

- `supports_responses=false`
- `supports_chat=true`
- `supports_stream=true`
- `supports_function_tools=true`
- `supports_builtin_tools=false`
- `supports_previous_response_id_native=false`
- `supports_json_schema=false`

### 7.3 Capability Guard 规则

Capability Guard 在真正发请求前做检查。

第一阶段至少检查：

- 客户端入口协议是否允许被该 route 服务
- `stream` 是否支持
- `tools` 是否支持
- `built-in tools` 是否支持
- `previous_response_id` 是否走 native 还是 local fallback
- `json_schema` 是否支持

不支持时返回明确错误，而不是 silently degrade。

## 8. 统一内核对象

### 8.1 NormalizedRequest

无论来自 `/v1/responses`、`/v1/chat/completions` 还是 `/v1/messages`，都归一化为统一请求对象，至少包含：

- `client_protocol`
- `model`
- `messages`
- `system_prompt`
- `tools`
- `tool_choice`
- `stream`
- `max_output_tokens`
- `temperature`
- `top_p`
- `response_format`
- `previous_response_id`
- `raw_request`

### 8.2 NormalizedResult

统一执行结果至少包含：

- `route_name`
- `upstream_protocol`
- `upstream_response_id`
- `assistant_text`
- `tool_calls`
- `usage`
- `finish_reason`
- `raw_payload`

### 8.3 RouteTarget

执行器只依赖 `RouteTarget`，不直接耦合入口协议模型。

## 9. `/v1/responses` 第一阶段行为

### 9.1 route 选择

`/v1/responses` 收到请求后：

1. 解析请求
2. 归一化为 `NormalizedRequest`
3. 根据 `model` 解析 `RouteTarget`
4. 由 Capability Guard 判断：
   - 是否可 native responses
   - 是否可 responses-to-chat
   - 是否应拒绝

### 9.2 OpenAI 官方模型路径

如果 route 的 `upstream_protocol=responses`：

- 直接发往上游 `/v1/responses`
- 若上游原生支持 `previous_response_id`，则优先透传
- 流式时优先透传或最小包装上游 responses SSE
- 保存 `upstream_response_id`

### 9.3 本地 Qwen 路径

如果 route 的 `upstream_protocol=chat` 且客户端入口为 `/v1/responses`：

- 把 `input` 转换为内部 `messages`
- 若带 `previous_response_id`，则从本地 `response_states` 恢复历史
- 构造 chat payload 发往上游 `/v1/chat/completions`
- 同步时将 chat completion 映射为 responses output
- 流式时将 chat SSE 包装为：
  - `response.created`
  - `response.output_text.delta`
  - `response.completed`

### 9.4 明确不支持的能力

对 chat-native route：

- `web_search`
- `code_interpreter`
- 其他 built-in tools

第一阶段统一显式拒绝。

## 10. 会话状态设计

### 10.1 目标

统一支持两种续接模式：

- native upstream continuation
- local replay continuation

### 10.2 `response_states` 扩展字段

至少增加：

- `parent_response_id`
- `route_name`
- `client_protocol`
- `upstream_protocol`
- `upstream_response_id`
- `request_json`
- `output_json`

### 10.3 续接策略

- 若 route `supports_previous_response_id_native=true`
  - 优先使用 `upstream_response_id`
- 否则
  - 使用本地保存的 `messages_json` 回放历史

### 10.4 第一阶段限制

第一阶段只保证：

- 文本消息续接
- 基础 tool call 块的延续性

不保证完整 built-in tools 状态机恢复。

## 11. Adapter Registry

### 11.1 结构

系统按两级分发：

1. ingress normalizer
   - `responses_ingress`
   - `chat_ingress`
   - `messages_ingress`

2. upstream adapter
   - `native_responses`
   - `native_chat`
   - `native_messages`

第一阶段只要求稳定落地：

- `responses_ingress`
- `native_responses`
- `responses_to_chat`

### 11.2 职责边界

- normalizer 只负责把外部协议转成 `NormalizedRequest`
- adapter 只负责与上游协议交互
- encoder 只负责把 `NormalizedResult` 转成外部协议响应
- capability guard 不应散落在 adapter 内部

## 12. 实施分期

### 12.1 阶段一：路由语义升级

目标：

- 扩 `model_routes`
- 扩 `ModelRoute`
- 保持旧行为不变

完成标志：

- 系统可以表达 managed_local route 和 external route
- 现有 chat/messages 主路径不回归

### 12.2 阶段二：`/v1/responses` 双路径

目标：

- native responses route 打通
- responses-to-chat route 打通
- 本地与 native 两类 `previous_response_id` 都可用

完成标志：

- Codex 可同时访问 OpenAI 官方模型和本地 Qwen 模型

### 12.3 阶段三：统一三入口执行链

目标：

- `/v1/chat/completions`
- `/v1/messages`
- `/v1/responses`

共用同一执行内核

完成标志：

- route resolver / capability guard / adapter registry 不再只服务 `/v1/responses`

### 12.4 阶段四：控制面升级

目标：

- 区分 `managed_local` 与 `external`
- external route 只做 reachability / auth 检查，不纳入本地容器生命周期

完成标志：

- 管理台和控制面能同时表达本地模型与外部上游模型

## 13. 风险与回滚

### 13.1 风险

主要风险包括：

- `backend_type` 与 `upstream_protocol` 语义混淆
- `/v1/responses` 被误做成完整 Agent 平台
- external route 凭据管理方式过早固化
- readiness 仍假设只有单一本地后端
- 三入口过早同时迁移导致回归面过大

### 13.2 回滚点

- 阶段一只扩字段，几乎可无损回滚
- 阶段二只替换 `/v1/responses` 主链路，其他入口不动，回滚面可控
- 阶段三之前不修改 agent/control 生命周期主逻辑，避免跨层联动回归

## 14. 验收标准

第一阶段至少满足：

- `/v1/responses` 可按 route 选择：
  - native responses
  - responses-to-chat
- Codex 可以访问 OpenAI 官方模型
- Codex 可以访问本地 Qwen 模型
- Claude Code 现有 `/v1/messages` 路径不回归
- chat 客户端现有 `/v1/chat/completions` 路径不回归
- `previous_response_id` 在 native route 和 chat route 下都能工作
- chat-native route 对 unsupported built-in tools 明确失败
- request log / metrics 保持稳定，并能记录 route-aware 信息

## 15. 文档回流要求

本设计落地后，至少需要同步：

- `README.md`
- `docs/blueprint/current.md`
- `docs/blueprint/roadmap.md`
- `docs/contracts/backend-routing.md`
- 相关 `process` 文档
