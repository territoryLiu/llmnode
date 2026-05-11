# V2 完整蓝图

> 说明：这是 V2 阶段的历史完整设计快照。它保留当时语境，不作为当前真相源。当前请优先阅读 `README.md`、`docs/blueprint/current.md` 和 `docs/blueprint/roadmap.md`。

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
