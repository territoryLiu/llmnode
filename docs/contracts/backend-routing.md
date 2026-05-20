# 后端路由契约

## 0. 文档定位

这份文档只定义逻辑模型如何映射到具体推理后端。  
它回答的是：

1. `backend_type` 的正式语义是什么。
2. `upstream_protocol` 与 `lifecycle_mode` 的正式语义是什么。
3. 哪些字段属于正式路由契约。
4. 当前已落地和未来目标分别是什么。

它不负责：

- 描述完整系统现状，那是 `docs/blueprint/current.md`
- 描述未来优先级，那是 `docs/blueprint/roadmap.md`
- 展开某一后端的详细启动设计，那是相关 `spec`

## 1. 这份契约服务哪条正式链路

当前它服务的正式链路是：

1. 客户端请求逻辑模型名
2. `gateway-api` 读取当前 `ModelRoute`
3. 路由层根据 route 字段决定目标上游和本地后端语义
4. 请求被转发到实际推理服务

当前对外暴露的是逻辑模型名；`backend_model`、`backend_type`、`upstream_protocol` 与 `lifecycle_mode` 属于网关、控制面、管理台和存储层共同理解的内部正式字段。

## 2. 目标

- 定义逻辑模型如何映射到具体推理后端
- 保证客户端不需要感知后端差异
- 为管理台、控制面、数据库和网关提供统一字段语义

## 3. 当前契约来源 / 代码锚点

当前正式锚点至少包括：

- `config/defaults.yaml`
  - 当前激活 profile 选择入口
- `config/backends/*.yaml`
  - 每个“后端 + 模型”组合的正式参数来源
- `llmnode/models.py`
  - `ModelRoute` 数据结构
  - `load_model_catalog()` 默认值与加载逻辑
  - `model_routes_for_admin()` 管理台读取视图
- `llmnode/api/app.py`
  - 启动时把模型目录写入运行态
  - `/admin/models` 读取与更新入口
  - `/admin/models` 管理接口的三后端路由支持
- `llmnode/storage/db.py`
  - `model_routes` 表结构与持久化字段

如果这些位置的字段语义不一致，应以代码真实行为为准，并把文档回流补齐。

## 4. 当前状态

- 当前正式运行路径默认仍为 `vLLM`
- 模型目录与路由初值以当前激活 profile 为主
- `backend_type` 现已正式支持 `vllm / llama.cpp / sglang` 三个值，三后端均已完成线上联调验证（2026-05-12）
- `/admin/models/{name}` 管理接口已接受三个值（`_VALID_BACKEND_TYPES`）

## 5. 正式字段

当前至少包括：

- `name`
- `display_name`
- `backend_model`
- `backend_type`
- `lifecycle_mode`
- `upstream_protocol`
- `upstream_base_url`
- `upstream_model`
- `upstream_auth_kind`
- `upstream_auth_ref`
- `capabilities_json`
- `native_protocols_json`
- `adapter_policies_json`
- `tool_policies_json`
- `protocol_features_json`
- `recommended_runtime_semantics`
- `enabled`
- `source_kind`
- `source_ref`
- `stale`

后续如果扩展容器与 profile，应继续保证这些字段仍然存在且语义稳定。

字段语义：

- `name`
  - 逻辑模型标识，也是客户端看到的正式模型名
- `display_name`
  - 管理台展示名，不改变正式路由键
- `backend_model`
  - 实际传给后端的模型标识
- `backend_type`
  - 表示这条路由绑定到哪类本地受控推理后端
- `lifecycle_mode`
  - 表示该 route 属于本地受控还是外部上游
- `upstream_protocol`
  - 表示该 route 实际对上游发请求时使用的协议
- `upstream_base_url`
  - 表示该 route 请求发往的上游根地址
- `upstream_model`
  - 表示实际发给上游的模型标识
- `upstream_auth_kind`
  - 表示访问上游时采用的鉴权方式
- `upstream_auth_ref`
  - 表示访问上游时引用的凭据标识
  - phase1 当前正式语义：环境变量名，而不是数据库内嵌 secret
- `capabilities_json`
  - 表示该 route 可声明的协议与能力边界
- `native_protocols_json`
  - 表示该 route 当前持久化的原生协议声明
- `adapter_policies_json`
  - 表示该 route 当前持久化的协议适配白名单
- `tool_policies_json`
  - 表示该 route 当前持久化的工具治理开关
- `protocol_features_json`
  - 表示该 route 当前持久化的协议特性开关
- `recommended_runtime_semantics`
  - 表示控制面基于 route 基础字段派生出的推荐 runtime 默认
  - 当前由 `llmnode/models.py` 的 `ModelRoute.recommended_runtime_semantics()` 生成
  - 当前用于管理台的“风险提示 / 恢复推荐默认 / 协议切换默认值”闭环
- `enabled`
  - 控制逻辑模型是否对正式 API 暴露
- `source_kind`
  - 表示该 route 来自 profile seed 还是人工管理
- `source_ref`
  - 表示该 route 的来源引用；对 `profile_seed` 当前为 profile 名
- `stale`
  - 表示该 route 是否已脱离当前激活 profile 的默认供给

## 6. `backend_type`

### 当前正式值
- `vllm`
- `llama.cpp`
- `sglang`

### 约束
- `backend_type` 是客户端不可见、但网关和控制面必须理解的内部正式字段
- 它决定：
  - 目标本地后端驱动
  - 健康检查逻辑
  - 管理台状态展示维度

第一阶段补充约束：

- `backend_type` 只描述本地受控推理后端类型，不再单独承担上游协议语义
- `upstream_protocol` 描述实际对上游发请求时使用的协议
- `lifecycle_mode` 描述该 route 是本地受控还是外部上游

## 7. 当前真实行为

当前真实行为应按下面理解：

- `config/defaults.yaml` 只决定当前激活的 backend profile
- `config/backends/*.yaml` 提供模型目录、端口与后端参数初值
- 当前激活哪个 profile，就使用哪个 profile 所声明的后端、模型与运行参数；不存在脱离配置单独定义的“默认模型”
- `llmnode/models.py` 中 `ModelRoute.backend_type` 默认值是 `vllm`
- 如果 profile 里未显式写 `backend_type`，加载后会默认落成 `vllm`
- 对现有本地受控 route，`lifecycle_mode` 默认应为 `managed_local`
- 对现有本地受控 route，`upstream_protocol` 默认应为 `chat`
- 启动后，模型路由会进入 SQLite 的 `model_routes` 表作为长期 route 注册表
- 当前启动流程只会把当前 catalog 增量同步到 `model_routes`
- `profile_seed` route 不再属于当前 catalog 时，会标记 `stale=1` 且自动 `enabled=false`
- `manual` route 不因重启被清空
- 管理面应逐步扩展为可更新 `display_name / backend_model / backend_type / lifecycle_mode / upstream_protocol / enabled`
- 管理台与 `/admin/models/{name}` 现已可更新：
  - `display_name`
  - `backend_model`
  - `backend_type`
  - `enabled`
  - `lifecycle_mode`
  - `upstream_protocol`
  - `upstream_base_url`
  - `upstream_model`
  - `upstream_auth_kind`
  - `upstream_auth_ref`
  - `capabilities_json`
- `/admin/models` 现已支持：
  - `POST /admin/models`
    - phase 1 仅允许创建 `external` route
  - `DELETE /admin/models/{name}`
    - phase 1 仅允许删除 `source_kind=manual` 的 route
- 管理台 phase 2 当前已额外提供：
  - 对 `stale + profile_seed` route 的显式治理提示
  - 对 `stale + profile_seed` route 的允许动作 / 不允许动作显式说明
  - `source_ref` 的来源 profile 展示
  - 对 `profile_seed` route 的前端 `lifecycle_mode` 锁定，避免直接改成 `external`
  - 对 `stale + profile_seed` route 的前端启用开关锁定，避免直接重新启用
  - 总览页 route 治理摘要，直接汇总 `stale / manual / profile_seed` 数量
  - 启动 seed 的 reconcile 结果会写入 `agent_events`，当前至少包括：
    - `route_marked_stale`
    - `route_manual_preserved`
- `/admin/models/{name}` 现已接受 `vllm / llama.cpp / sglang` 三个值（`_VALID_BACKEND_TYPES`）
- 协议入口当前的 route-aware 分发状态：
  - `/responses` 与 `/v1/responses`
    - `/responses`（无 `/v1/` 前缀）已作为 `/v1/responses` 的别名路由注册，供 Codex 等客户端直接使用
    - 两条路由指向同一 handler，走相同的 native/adapter 分发逻辑
    - 先按 route 的 `native_protocols` 判定是否原生支持 `responses`
    - 仅当 route 显式声明 `adapter_policies` 时，才允许 `responses -> chat` 或 `responses -> messages`
    - 若既非原生支持、也未显式开启 adapter，则返回 `native_protocol_not_supported` 或 `adapter_not_enabled_for_route`
  - `/v1/chat/completions`
    - `managed_local + vLLM` 当前按原生 chat path 走本地后端
    - `external + chat` 已可直连外部 `/v1/chat/completions`
  - `/v1/messages`
    - `managed_local + vLLM` 当前按原生 messages path 服务本地后端
    - 仍保留 Claude Code builtin metadata 的最小过滤；但 Anthropic function tools 已按原生语义透传，不再被误判成 builtin
    - `/v1/messages/count_tokens` 已提供最小兼容实现，供 Claude Code 等客户端做协议探测
    - 当前已验证本地后端可通过 `/v1/messages` 返回 `tool_use`；`managed_local + vllm` route 的 `builtin_tools` 现已默认开启（`True`），与 `openai_function_tools / anthropic_function_tools` 保持一致
    - `external + messages` 已可直连外部 `/v1/messages`

- route 运行时治理语义当前正式分成四层：
  - `native_protocols`
  - `adapter_policies`
  - `tool_policies`
  - `protocol_features`
- 在持久化与管理面返回里，这四层当前正式对应：
  - `native_protocols_json`
  - `adapter_policies_json`
  - `tool_policies_json`
  - `protocol_features_json`
- `recommended_runtime_semantics` 当前表示这四层的推荐默认：
  - `managed_local + vllm`
    - 默认原生支持 `chat / responses / messages`
    - 默认不启用 adapter
    - 默认 `tool_policies`：`openai_function_tools: True`，`anthropic_function_tools: True`，`builtin_tools: True`
  - `external`
    - 默认 `native_protocols_json = [upstream_protocol]`
    - 默认 `adapter_policies_json = []`
    - 默认 `protocol_features_json.count_tokens = (upstream_protocol == "messages")`
    - 默认 `tool_policies` 由 `capabilities.supports_function_tools` 和 `capabilities.supports_builtin_tools` 决定
- 其中工具治理当前正式拆成三类：
  - `openai_function_tools`
  - `anthropic_function_tools`
  - `builtin_tools`
- gateway 当前正式原则：
  - `native pass-through first`
  - `adapter opt-in only`
  - `governance without silent mutation`
- 客户端兼容当前正式按“协议类型”治理，而不是按“客户端品牌”治理：
  - `Claude Code`
  - `Codex`
  - `Cherry Studio`
  - 其他 `chat / responses / messages` 客户端
- 只要 route 原生支持客户端协议，gateway 当前不应因为请求来自某个特定客户端品牌，就额外重写业务 payload

因此当前结论是：字段层面已开始从“本地后端类型”与“上游协议类型”两层语义拆分；控制面（`control.py`、`service.py`）当前仍主要按 `backend_type` 驱动本地受控路径。

## 8. 运行时约束 / 校验入口

当前至少有这些运行时约束：

- 配置加载约束
  - `llmnode/models.py` 会为缺省路由补 `backend_type="vllm"`
  - `llmnode/models.py` 会为缺省路由补 `lifecycle_mode="managed_local"`
  - `llmnode/models.py` 会为缺省路由补 `upstream_protocol="chat"`
- 存储约束
  - `llmnode/storage/db.py` 中 `model_routes` 应持久化 `upstream_protocol / lifecycle_mode / capabilities_json / native_protocols_json / adapter_policies_json / tool_policies_json / protocol_features_json / source_kind / source_ref / stale`
  - `upsert_model_route()` 当前正式会在调用方未显式提供 runtime 四层字段时，按 `ModelRoute.runtime_capabilities()` 自动补齐后再落库
- 管理面约束
  - `llmnode/api/app.py` 的 `/admin/models/{name}` 接受 `vllm / llama.cpp / sglang`
  - `lifecycle_mode` 仅允许 `managed_local / external`
  - `upstream_protocol` 仅允许 `responses / chat / messages`
  - `upstream_auth_kind` 仅允许 `none / bearer / x_api_key`
  - `managed_local` route 必须保留 `backend_type` 和 `backend_model`
  - `external` route 必须显式提供 `upstream_base_url` 和 `upstream_model`
  - 当 `upstream_auth_kind != none` 时，必须提供 `upstream_auth_ref`
  - 当 `upstream_auth_kind != none` 时，运行时必须能从 `os.environ[upstream_auth_ref]` 读到真实 secret，否则请求失败
  - `POST /admin/models` phase 1 仅允许 `external` route create
  - `DELETE /admin/models/{name}` phase 1 仅允许删除 `manual` route
  - `profile_seed` route 不允许直接转换为 manual external route
  - 管理台前端当前会把 `profile_seed` route 的 `lifecycle_mode` 选择器锁定，防止用户走到后端 409 才知道不允许转换
  - 管理台前端当前会对 `stale + profile_seed` route 展示“已脱离当前 profile 默认供给、需人工确认”的治理提示
  - `stale + profile_seed` route 当前不允许直接重新启用；如需恢复，应切回来源 profile，或新建 `manual` route 承接
  - `/admin/status` 与 `GET /admin/models` 当前会为每条 route 返回 `recommended_runtime_semantics`
  - 启动 seed 的 route reconcile 结果当前会作为结构化事件写入 `/admin/events`
  - `route_marked_stale` 事件当前至少包含 `route_name / source_kind / source_ref / action=marked_stale`
  - `route_manual_preserved` 事件当前至少包含 `route_name / source_kind / source_ref / action=preserved`
  - `request_logs` 当前应保留 `metadata_json`，至少可记录 `client_protocol / execution_mode / adapter_selected / request_mutation`
- API 暴露约束
  - `enabled=false` 的逻辑模型不应出现在正式模型列表里

这些约束意味着：

- 字段层面应同时表达：
  - 本地受控后端类型
  - 实际上游协议类型
  - route 生命周期归属
- `backend_type` 仍决定 ContainerSpec、BackendDriver、健康检查和状态展示的本地受控链路行为
- external upstream 的鉴权 secret 当前不入库，只保留引用名，运行时由网关进程从环境变量解析

## 9. 路由职责

- `gateway-api` 负责把客户端请求路由到逻辑模型绑定的后端
- 后端差异不应直接暴露给客户端
- 同一逻辑模型在任一时刻应只绑定一个正式后端目标

## 10. Gateway 治理边界

gateway 当前正式允许做的事情：

- 鉴权
- 限流与并发治理
- 逻辑模型到 route 的解析
- 上游目标地址与 model 名映射
- 上游鉴权头注入
- 审计与日志记录
- 基于 route 能力做放行、拒绝或显式 adapter 决策

gateway 当前不应做的事情：

- 因为客户端来自 `Claude Code / Codex / Cherry Studio` 就静默改写协议语义
- 在 route 已原生支持客户端协议时重写业务 payload 主体
- 把未显式启用的 adapter 当成默认兜底路径
- 通过剥字段、改字段把“不支持”伪装成“兼容”

对“业务 payload 主体”的当前正式理解至少包括：

- `messages`
- `input`
- `tools`
- `tool_choice`
- `response_format`
- `stream`
- `previous_response_id`
- Anthropic function tool 的 `name / description / input_schema`

唯一仍允许的最小协议清理边界是：

- 对工程客户端默认附带的 builtin tool metadata 做最小过滤
- 该过滤只用于避免把 builtin tool 元数据误透传到不支持 builtin tools 的后端
- 该过滤不应影响 Anthropic function tools 的原生透传

### 10.1 Gateway vLLM 兼容归一化

在 native pass-through 模式下，Gateway 在转发请求到 vLLM 的 `/v1/responses` 之前，会对上游 payload 做以下最小归一化（不改变业务语义，仅消除 vLLM 实现的已知兼容差异）：

**a) `developer` role → `instructions` 合并**
- 原因：vLLM 将 `instructions` 和 `developer` input item 都转为 system message，Qwen3 等模型的 chat template 要求 system message 必须在最前面且只能有一条
- 行为：将 input 中所有 `role=developer` 的 item 的文本内容合并到 `instructions` 字段，并从 `input` 数组中移除

**b) Content 数组 → 保边界文本归一化**
- 原因：vLLM 的 Pydantic 校验接受单条 content 为数组格式的 input item，但拒绝多条；若直接裸拼文本，会抹掉原本分段边界
- 行为：仅对纯文本型 `content` 数组，提取所有 text block，并以空行分隔拼接为字符串；若 `content` 中包含 `input_image` 等非文本 block，则保留原数组结构与顺序，避免多模态信息被抹掉

**c) `reasoning` item → `instructions` 降级保留**
- 原因：vLLM 的 Pydantic 校验不允许 `input` 数组中包含 `type=reasoning` 的 item（无论是否设置 `instructions`）；但直接删除会丢失多轮推理上下文
- 行为：提取 `reasoning.summary` / `reasoning.content` 中可读文本，追加到 `instructions` 的显式 `reasoning context` 段，再从 `input` 数组中移除原始 `reasoning` item

**适用范围**：以上归一化仅在 `managed_local + vllm` 且走 native pass-through 路径时生效，不影响 external route 和 adapter 路径。

## 11. 工程客户端兼容边界

当前正式兼容边界如下：

- `Claude Code`
  - 走 `/v1/messages`
  - Anthropic function tools 当前按原生语义透传
  - `/v1/messages/count_tokens` 已提供最小兼容实现，供工程模式探测
  - builtin tools 对 `managed_local + vllm` route 现已默认开放（`builtin_tools: True`），不再返回 `builtin_tools_not_supported`；`external` route 仍按 `capabilities.supports_builtin_tools` 决定
- `Codex`
  - 走 `/responses`（裸路径，无 `/v1/` 前缀），已通过 `/responses` → `/v1/responses` 别名路由支持
  - 若其请求最终落在 route 原生支持的 `chat / responses / messages` 协议上，gateway 当前应按原生透传处理
  - Codex 的 `developer` role input item 和 `reasoning` item 会经 Gateway vLLM 兼容归一化（见 10.1 节）处理后透传
  - 不应因为其工程代理属性就引入额外 payload 语义改写
- `Cherry Studio` 等 chat 客户端
  - 若 route 原生支持 `chat` 或 `responses`，gateway 当前应直接按原生协议透传
  - 不应为此类客户端额外套一层协议转换或字段清洗

因此当前正式兼容原则不是“为某个客户端做专门魔改”，而是：

- 客户端选择协议
- route 声明原生支持或显式 adapter
- gateway 只负责治理和分发

## 12. 错误与日志语义

当前协议治理至少应在错误与日志中体现以下语义：

- 若客户端协议不在 route 的 `native_protocols` 中，且 route 未显式开启对应 adapter：
  - 返回 `native_protocol_not_supported` 或 `adapter_not_enabled_for_route`
- 若请求包含 builtin tools，且 route 未显式允许（当前仅 `external` route 可能出现此情况）：
  - 返回 `builtin_tools_not_supported`

`request_logs.metadata_json` 当前至少应能表达：

- `client_protocol`
- `execution_mode`
  - `native`
  - `adapter`
- `adapter_selected`
- `request_mutation`

当前正式期望是：

- native pass-through 路径：
  - `execution_mode = native`
  - `request_mutation = false`
- adapter 路径：
  - `execution_mode = adapter`
  - `request_mutation = true`
  - `adapter_selected` 记录具体 adapter 名称

## 13. 当前与未来的差异

当前正式状态：

- 正式可写运行值：`vllm / llama.cpp / sglang`
- 控制面（`control.py`、`service.py`）与网关管理接口均已完整支持三后端
- 三后端均已完成线上联调验证（2026-05-12）：推理链路打通，`reasoning_content / content` 干净分离已确认
- 控制面诊断能力已增强（2026-05-12）：
  - `doctor` 命令支持三后端特定检查、GPU 信息、模型格式检测、智能建议
  - `status` 命令支持容器详细信息、推理参数展示、6 种栈状态
  - `logs` 命令支持实时跟踪、错误高亮、关键词搜索
  - Agent 服务暴露诊断 API 端点（`/admin/diagnostics/*`）
  - 管理台前端已对齐三后端状态展示

未来仍需补厚的方向：

- 诊断建议的持续优化（新增错误模式识别）
- 性能指标采集的多维分组与时间窗口查询
- route 生命周期管理闭环：新增 / 删除 / 持久化策略与 catalog 同步边界

## 14. 诊断 API 端点

Agent 服务（`llmnode/agent/service.py`）暴露以下诊断 API 端点：

- `GET /admin/diagnostics/gpu` - 获取 GPU 信息和 CUDA 版本
- `GET /admin/diagnostics/container` - 获取容器详细信息（状态、运行时长、重启次数）
- `GET /admin/diagnostics/model` - 获取模型信息（格式、配置）
- `GET /admin/diagnostics/metrics` - 获取基础性能指标聚合（请求数、成功率、延迟、吞吐、`queue_length`）
- `GET /admin/diagnostics/suggestions` - 获取智能建议（基于日志分析和系统状态）
- `GET /admin/diagnostics/status` - 获取完整诊断状态（聚合所有诊断信息）

这些端点供管理台前端和外部监控系统使用，返回 JSON 格式数据。

## 15. 管理台 API 端点

网关服务（`llmnode/api/app.py`）暴露以下管理台 API 端点：

- `GET /admin/overview/readiness` - 获取系统就绪状态和 Base URL 信息
  - 返回 `readiness`（Agent 状态）和 `base_urls`（`local` / `lan` 地址）
  - Base URL 由管理台统一下发，供客户端复制使用
- `GET /admin/keys` - 获取 API Key 列表
  - 返回 `masked_key` 脱敏字段，不含 secret 明文
  - 附带 `usage_summary`（总请求数、总 Token 数）
- `POST /admin/keys` - 创建 API Key
  - 返回 `masked_key` 和 `secret`（仅当次可见）
- `PATCH /admin/keys/{id}` - 更新 API Key 状态/名称/权限
- `DELETE /admin/keys/{id}` - 删除 API Key

## 16. 长期扩展方向

后续三后端落地后，本契约应继续扩展：

- `container_image`
- `container_name`
- `profile_id`
- `healthcheck_kind`
- `tool_calling_capability`
- `streaming_capability`

## 17. 文档回流要求

如果路由字段或后端类型发生变化，应至少检查是否同步更新：

- `config/defaults.yaml`
- `config/backends/*.yaml`
- `llmnode/models.py`
- `llmnode/api/app.py`
- `llmnode/storage/db.py`
- `docs/blueprint/current.md`
- `docs/blueprint/roadmap.md`
- 本文
