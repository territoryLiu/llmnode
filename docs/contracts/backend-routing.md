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
- `enabled`

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
- `enabled`
  - 控制逻辑模型是否对正式 API 暴露

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
- 启动后，模型路由会进入 SQLite 的 `model_routes` 表作为运行态存储
- 当前启动流程会以当前 catalog 重新 seed `model_routes`；因此现阶段更接近“配置派生的运行态 route”，而不是完整的长期持久化模型注册中心
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
- `/admin/models/{name}` 现已接受 `vllm / llama.cpp / sglang` 三个值（`_VALID_BACKEND_TYPES`）
- 协议入口当前的 route-aware 分发状态：
  - `/v1/responses`
    - 可按 route 选择 `native responses`、`responses -> chat` 或 `responses -> messages` 适配
  - `/v1/chat/completions`
    - `managed_local + chat` 继续走本地后端
    - `external + chat` 已可直连外部 `/v1/chat/completions`
  - `/v1/messages`
    - `managed_local + chat` 继续保留现有 anthropic facade 兼容路径
    - `external + messages` 已可直连外部 `/v1/messages`

因此当前结论是：字段层面已开始从“本地后端类型”与“上游协议类型”两层语义拆分；控制面（`control.py`、`service.py`）当前仍主要按 `backend_type` 驱动本地受控路径。

## 8. 运行时约束 / 校验入口

当前至少有这些运行时约束：

- 配置加载约束
  - `llmnode/models.py` 会为缺省路由补 `backend_type="vllm"`
  - `llmnode/models.py` 会为缺省路由补 `lifecycle_mode="managed_local"`
  - `llmnode/models.py` 会为缺省路由补 `upstream_protocol="chat"`
- 存储约束
  - `llmnode/storage/db.py` 中 `model_routes` 应持久化 `upstream_protocol / lifecycle_mode / capabilities_json`
- 管理面约束
  - `llmnode/api/app.py` 的 `/admin/models/{name}` 接受 `vllm / llama.cpp / sglang`
  - `lifecycle_mode` 仅允许 `managed_local / external`
  - `upstream_protocol` 仅允许 `responses / chat / messages`
  - `upstream_auth_kind` 仅允许 `none / bearer / x_api_key`
  - `managed_local` route 必须保留 `backend_type` 和 `backend_model`
  - `external` route 必须显式提供 `upstream_base_url` 和 `upstream_model`
  - 当 `upstream_auth_kind != none` 时，必须提供 `upstream_auth_ref`
  - 当 `upstream_auth_kind != none` 时，运行时必须能从 `os.environ[upstream_auth_ref]` 读到真实 secret，否则请求失败
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

## 10. 当前与未来的差异

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

## 11. 诊断 API 端点

Agent 服务（`llmnode/agent/service.py`）暴露以下诊断 API 端点：

- `GET /admin/diagnostics/gpu` - 获取 GPU 信息和 CUDA 版本
- `GET /admin/diagnostics/container` - 获取容器详细信息（状态、运行时长、重启次数）
- `GET /admin/diagnostics/model` - 获取模型信息（格式、配置）
- `GET /admin/diagnostics/metrics` - 获取基础性能指标聚合（请求数、成功率、延迟、吞吐、`queue_length`）
- `GET /admin/diagnostics/suggestions` - 获取智能建议（基于日志分析和系统状态）
- `GET /admin/diagnostics/status` - 获取完整诊断状态（聚合所有诊断信息）

这些端点供管理台前端和外部监控系统使用，返回 JSON 格式数据。

## 12. 管理台 API 端点

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

## 12. 长期扩展方向

后续三后端落地后，本契约应继续扩展：

- `container_image`
- `container_name`
- `profile_id`
- `healthcheck_kind`
- `tool_calling_capability`
- `streaming_capability`

## 13. 文档回流要求

如果路由字段或后端类型发生变化，应至少检查是否同步更新：

- `config/defaults.yaml`
- `config/backends/*.yaml`
- `llmnode/models.py`
- `llmnode/api/app.py`
- `llmnode/storage/db.py`
- `docs/blueprint/current.md`
- `docs/blueprint/roadmap.md`
- 本文
