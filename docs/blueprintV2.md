# blueprintV2

## 1. 定位
- V2 不重做 V1，而是把 V1 升级为可长期维护的单机平台。
- V1 保持不变，继续作为最小可用入口和回退路径。
- V2 目标是把“能用的个人网关”收敛成“可运营、可观测、可扩展的本地 LLM 平台”。

## 2. 设计原则
- 单一职责：业务网关、节点控制、管理控制台职责分离。
- 单一事实源：业务数据统一落关系型数据库。
- 最小公开面：对外只保留少量稳定 API。
- 明确边界：网关不碰 Docker，节点不碰公网，控制台不直连存储。
- 可回退：脚本保留应急入口，但不再承载主流程。
- 双协议入口：`/v1/chat/completions` 面向 OpenAI 客户端，`/v1/messages` 面向 Claude Code。
- 内部单后端：两种协议统一转发到本机 `vLLM`，不分叉后端实现。
- 版本约束：V2 只支持 `vLLM` 一种推理后端，但代码结构应为 V3 的多后端驱动预留边界。

## 3. 总体架构
### 3.1 `gateway-api`
- 对外唯一业务入口。
- 负责：
  - OpenAI 兼容接口
  - 认证与鉴权
  - 模型路由
  - 配额与并发控制
  - FIFO 队列
  - 请求审计
  - 管理 API
  - SSE 聚合推送

### 3.2 `node-agent`
- 本机运行控制器。
- 负责：
  - Docker / 容器管理
  - vLLM 启停
  - 健康巡检
  - 自动恢复
  - GPU / 容器遥测
  - 状态机维护

### 3.3 `web-console`
- 管理员控制台。
- 负责：
  - 状态查看
  - API Key 管理
  - 模型路由管理
  - 调度管理
  - 请求日志
  - 服务控制
  - 告警查看

### 3.4 `storage`
- 设计上 PostgreSQL 作为唯一业务真相源。
- 当前单机实现先使用 SQLite 承载请求日志、模型路由和调度配置，便于在本机阶段快速落地。
- 保存：
  - API Key
  - 模型路由
  - 请求审计
  - 节点事件
  - 调度规则
  - 管理员配置

### 3.5 `runtime`
- 只保存运行时产物：
  - 日志
  - pid / socket
  - 缓存
  - 临时导出
- 不保存业务真相。

### 3.6 `config` 与 `models`
- `config/defaults.yaml` 是正式默认配置源。
- 环境变量仅作为运行时覆盖项，不再需要单独维护根目录 `.env.example`。
- 所有本地模型统一放在 `models/` 下，默认 `vLLM` 模型目录为 `models/Qwen/Qwen3.6-35B-A3B-FP8`。
- Python 主包采用 `llmnode/`，不再保留旧的 `src/vllm_claude` 作为主包路径。

## 4. 系统边界
- `gateway-api` 不直接操作 Docker。
- `node-agent` 不直接暴露公网。
- `web-console` 只访问 `gateway-api` 管理接口。
- `gateway-api` 与 `node-agent` 通过本机私有 HTTP 或 Unix Socket 通信。
- `scripts/*.sh` 只做调试和应急回退。
- V2 不引入 `llama.cpp`、`sglang` 或其它第二后端。

## 4.1 V2 对 V3 的预留边界
- `gateway-api` 内部应通过统一后端接口访问推理服务，而不是把 `vLLM` 请求细节散落在业务逻辑里。
- `node-agent` 内部应保留“驱动层”概念，但 V2 只落地 `vllm` 驱动。
- 模型路由表中可以保留 `backend_type` 字段，但 V2 固定只能取 `vllm`。
- 启动配置应区分：
  - 逻辑模型配置
  - 后端运行配置
  - 节点调度配置
- 这些预留只为了 V3 演进，V2 不对外暴露多后端能力。

## 5. 目录建议
- `llmnode/`
- `web-console/`
- `config/`
- `models/`
- `runtime/`
- `scripts/`
- `tests/`

## 6. 领域模型
### 6.1 API Key
- 字段：
  - `id`
  - `key_hash`
  - `name`
  - `status`
  - `scopes`
  - `rpm_limit`
  - `concurrency_limit`
  - `created_at`
  - `disabled_at`
  - `last_used_at`
  - `note`

### 6.2 Model Route
- 字段：
  - `id`
  - `logical_name`
  - `display_name`
  - `backend_name`
  - `backend_type`
  - `default_temperature`
  - `default_max_tokens`
  - `max_model_len`
  - `gpu_memory_utilization`
  - `enabled`
- 约束：
  - V2 中 `backend_type` 固定为 `vllm`
- 当前落地最小字段为：
  - `name`
  - `display_name`
  - `backend_model`
  - `backend_type`
  - `enabled`

### 6.3 Request Log
- 字段：
  - `request_id`
  - `api_key_id`
  - `auth_source`
  - `client_ip`
  - `user_agent`
  - `rejection_reason`
  - `protocol`
  - `logical_model`
  - `backend_model`
  - `status`
  - `queue_wait_ms`
  - `latency_ms`
  - `prompt_tokens`
  - `completion_tokens`
  - `error_message`

### 6.4 Agent Event
- 字段：
  - `event_id`
  - `status_before`
  - `status_after`
  - `reason`
  - `created_at`
  - `recovery_attempt`

### 6.5 Schedule
- 字段：
  - `timezone`
  - `work_days`
  - `start_time`
  - `end_time`
  - `auto_stop_enabled`
  - `auto_start_enabled`
  - `cooldown_minutes`
  - `alarm_lock_enabled`

## 7. 状态机
### 7.1 `node-agent`
- `stopped`
- `starting`
- `ready`
- `degraded`
- `recovering`
- `stopping`
- `off_hours`
- `alerting`

### 7.2 `gateway-api`
- `healthy`
- `degraded`
- `blocked_by_agent`
- `blocked_by_schedule`
- `blocked_by_quota`
- `blocked_by_queue`

### 7.3 状态联动
- `gateway-api` 只有在调度允许且 `node-agent=ready` 时放行业务请求。
- `node-agent` 是运行事实源，状态变化必须写入事件表。
- 控制台展示状态时间线和恢复记录。

## 8. 请求链路
### 8.1 业务请求
1. 客户端请求进入 `gateway-api`，协议可以是 OpenAI 或 Claude。
2. 校验 API Key、状态、权限。
3. 校验调度策略。
4. 校验 `node-agent` 状态。
5. 校验单 key `rpm_limit`。
6. 校验单 key `concurrency_limit`。
7. 进入全局 FIFO 队列或直接执行。
8. 选择模型路由并转发到本机 `vLLM`。
9. 落请求日志并返回 `request_id`。

### 8.2 管理请求
1. 管理员在 `web-console` 发起操作。
2. `web-console` 调用 `gateway-api` 管理接口。
3. `gateway-api` 根据权限调用 `node-agent`。
4. `node-agent` 执行容器操作并记录事件。
5. 控制台通过 SSE 获取状态变化。

## 9. API 体系
### 9.1 业务 API
- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/messages`

### 9.2 网关管理 API
- `GET /admin/status`
- `GET /admin/request-logs`
- `GET /admin/keys`
- `POST /admin/keys`
- `PATCH /admin/keys/{id}`
- `DELETE /admin/keys/{id}`
- `GET /admin/models`
- `PATCH /admin/models/{name}`
- `GET /admin/schedule`
- `PATCH /admin/schedule`
- `GET /admin/logs`
- `GET /admin/events`
- `POST /admin/services/restart`

### 9.3 当前已实现
- `GET /admin/status`
- `GET /admin/stream`
- `GET /admin/request-logs`
- `GET /admin/logs`
- `GET /admin/events`
- `GET /admin/keys`
- `POST /admin/keys`
- `PATCH /admin/keys/{id}`
- `DELETE /admin/keys/{id}`
- `GET /admin/models`
- `PATCH /admin/models/{name}`
- `GET /admin/schedule`
- `PATCH /admin/schedule`
- `POST /admin/services/restart`

### 9.4 当前预留
- 更细粒度的服务管理接口
- 更复杂的恢复编排与人工确认流程

### 9.5 节点 API
- `GET /state`
- `GET /events`
- `POST /manage/start`
- `POST /manage/stop`
- `POST /manage/restart`
- `GET /health/liveliness`

## 10. 队列与准入
- 准入顺序：
  1. key 存活与权限
  2. 调度策略
  3. agent 状态
  4. key 并发与 RPM
  5. 全局执行槽位
  6. 上下文预算
  7. 队列容量
- 队列策略：
  - FIFO
  - 有限长度
  - 有限等待时间
  - 队列满立即拒绝
- 结果只分三类：
  - 执行
  - 允许排队
  - 直接拒绝

## 11. 调度与恢复
- 调度独立于请求处理。
- 默认时区 `Asia/Shanghai`。
- 默认工作日 09:00-18:00。
- 支持：
  - 自动停服
  - 自动拉起
  - 统一由 `config/defaults.yaml` 管理默认值，控制台可修改并回写运行配置
  - 冷却时间
  - 连续失败阈值
  - 告警锁定
  - 人工确认恢复
- 恢复期间不允许新请求进入执行区。

## 12. 可观测性
- 结构化日志。
- `request_id` 全链路贯穿。
- 至少记录：
  - 入口请求
  - 排队状态
  - 转发状态
  - 响应状态
  - 错误原因
  - 事件变化
- 指标最少包含：
  - 活跃请求数
  - 队列长度
  - RPM
  - 延迟 P50 / P95 / P99
  - GPU 利用率
  - 显存水位
  - 错误率
  - 自动恢复次数
  - 最近失败原因

## 13. 安全
- API Key 只存 hash，不存明文。
- 管理接口与业务接口分权。
- 节点接口仅限本机或内网。

## 14. 当前已落地
- `llmnode/` 作为 Python 主包路径，替代旧的 `src/vllm_claude`。
- `config/defaults.yaml` 作为正式默认配置源。
- `models/` 作为统一模型目录，默认 `vLLM` 模型指向 `models/Qwen/Qwen3.6-35B-A3B-FP8`。
- `POST /v1/chat/completions` 与 `POST /v1/messages` 已接通本机 `vLLM`。
- `gateway.api_key` 已作为长期保留的 break-glass 管理员 key 接入网关鉴权链路。
- 数据库 API Key 已支持 `GET /admin/keys`、`POST /admin/keys`、`PATCH /admin/keys/{id}`、`DELETE /admin/keys/{id}`。
- `/v1/*` 与 `/admin/*` 已支持 bootstrap key + 数据库 key 双通道鉴权，以及 `admin` / `inference` 最小 scope 校验。
- 数据库 key 的单 key `rpm_limit` 与 `concurrency_limit` 已接入运行时准入，且发生在全局队列之前。
- `request_logs` 已记录 `api_key_id`、`auth_source`、`client_ip`、`user_agent`、`rejection_reason`，可区分 bootstrap 与数据库 key 请求来源及拒绝原因。
- `GET /admin/status`、`GET /admin/stream`、`GET /admin/request-logs`、`GET /admin/logs`、`GET /admin/events` 已可供前端总览页、日志页和状态页使用。
- `GET /admin/models`、`PATCH /admin/models/{name}`、`GET /admin/schedule`、`PATCH /admin/schedule` 已可编辑控制台直接修改。
- `POST /admin/services/restart` 已通过 `gateway-api -> node-agent` 形成统一控制入口。
- `web-console` 已完成总览页、使用记录页、模型路由页、调度页、系统状态页和 API Key 管理页的基础可用版本。

## 15. 当前未完成
- `storage` 从 SQLite 向 PostgreSQL 的正式迁移。
- `node-agent` 的更细粒度管理接口、更复杂恢复编排与人工确认机制。
- `gateway-api` 的更严格审计字段与请求画像。
- Prometheus 指标导出与告警闭环。

## 16. 验收口径
- `GET /v1/models` 返回逻辑模型列表。
- `POST /v1/chat/completions` 与 `POST /v1/messages` 都可透传到本机 `vLLM`。
- `GET /admin/status` 能返回运行快照、调度配置和模型路由。
- `GET /admin/stream` 可持续推送 SSE 快照。
- `GET /admin/logs` 当前返回请求审计日志，V2 阶段与 `GET /admin/request-logs` 保持等价。
- 管理控制台只通过 `gateway-api` 即可查看状态、请求日志、节点事件并发起 restart。
- `POST /admin/services/restart` 返回命令受理结果，后续恢复过程通过状态快照和 SSE 观察。
- 控制台可修改模型路由和调度配置，并立即反映到状态快照。
- 模型默认目录和脚本默认目录都指向 `models/`。
- 仓库不再依赖根目录 `.env.example` 作为正式配置入口。
- 控制台需要管理员认证。
- bootstrap 管理员 key 与数据库 key 都能访问受支持的接口，且权限边界由最小 scope 控制。
- 管理接口返回数据库 key 脱敏列表，创建接口只在首次响应中返回明文 secret。
- 单 key 超 RPM 时返回 `429`，且不会占用全局队列资源。
- 单 key 超并发时返回 `429`，流式请求在整个流结束前持续占用其 key 并发槽位。

## 14. 配置
- 静态配置：YAML。
- 敏感配置：`.env`。
- 动态业务配置：PostgreSQL。
- `runtime/` 只存运行数据，不做配置真相源。

## 15. 部署
- 默认单机容器化部署。
- 仅一个 `vLLM` 实例同时工作。
- `gateway-api`、`node-agent`、`web-console` 独立部署。
- 脚本继续存在，但只做回退和排障。
- 模型文件可以人工准备，但 V2 仍只管理 `vLLM` 所需模型目录和启动参数。

## 16. 验收标准
- `GET /v1/models` 返回逻辑模型列表。
- `POST /v1/chat/completions` 可稳定透传到本机 `vLLM`。
- `POST /v1/messages` 可稳定透传到本机 `vLLM`，供 Claude Code 使用。
- 无 key、错误 key、禁用 key 正确拒绝。
- bootstrap 管理员 key 可访问全部 `/admin/*` 与 `/v1/*` 接口。
- 数据库 `inference` key 可以访问 `/v1/*`，但不能访问 `/admin/*`。
- `GET /admin/keys`、`POST /admin/keys`、`PATCH /admin/keys/{id}`、`DELETE /admin/keys/{id}` 可完成数据库 key 管理。
- 请求日志可区分 bootstrap 与数据库 key，并记录 `api_key_id`、`rejection_reason`。
- 单 key 超 RPM 正确拒绝。
- 单 key 超并发直接拒绝，不进入独立等待队列。
- 执行槽位满时进入 FIFO 队列。
- 队列满时直接拒绝。
- 排队超时返回明确错误。
- 手动杀掉 `vLLM` 后系统能检测并自动恢复。
- 恢复期间新请求不进入执行区。
- 非工作时段自动停模型且后台继续在线。
- 控制台状态、日志、指标可对账到单次请求。
