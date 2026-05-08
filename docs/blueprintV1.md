# blueprintV1

## 1. 目标
- 在单机上把本地 `vLLM` 包装成一个稳定、可用、可审计的个人 LLM 网关。
- 让 Claude Code、OpenAI 客户端和自写脚本都能连同一套后端。
- 优先级固定为：可用性 > 可恢复性 > 可审计性 > 可扩展性。

## 2. 设计原则
- 先跑通，再扩展。
- 只有一个实际推理后端：本机 `vLLM`。
- 只有一个主业务入口：`gateway-api`。
- 所有复杂能力尽量收敛到最少的运行时组件。
- 失败时宁可拒绝，也不要把后端打死。

## 3. 明确不做
- Web 控制台。
- PostgreSQL。
- 多模型多后端路由。
- Unix Socket 控制面。
- Prometheus / Grafana。
- RAG / Embedding / Persona。
- 浏览器、shell、联网搜索服务端执行。

## 4. 运行拓扑
### 4.1 `vLLM`
- 端口：`8000`
- 职责：真正的推理服务。
- 约束：只服务一个本机模型实例。

### 4.2 `gateway-api`
- 端口：`4000`
- 职责：
  - 对外暴露 Claude/OpenAI 兼容接口。
  - 做鉴权、模型别名、排队、日志。
  - 把请求转发给本机 `vLLM`。
  - 在可选模式下检查 `node-agent` 是否 ready。

### 4.3 `node-agent`
- 端口：`4010`
- 职责：
  - 检查 `vLLM` 健康。
  - 启停 `vLLM`。
  - 尝试自动恢复。
  - 暴露状态给 `gateway-api`。

## 5. 目录与职责
- `llmnode/api`
  - `gateway-api` 主应用。
- `llmnode/agent`
  - `node-agent` 主应用。
- `llmnode/proxy`
  - 后端转发和模型路由。
- `llmnode/protocols`
  - OpenAI / Anthropic 请求模型。
- `llmnode/runtime`
  - 请求门控与并发保护。
- `llmnode/storage`
  - SQLite 请求审计。
- `scripts`
  - 启停脚本和运行时路径定义。

## 6. 端到端请求流
### 6.1 Claude Code
1. Claude Code 把请求发到 `http://127.0.0.1:4000/v1/messages`。
2. `gateway-api` 从 `Authorization` 或 `x-api-key` 读取密钥。
3. `gateway-api` 将客户端模型名映射到本地后端模型名。
4. 如果启用了 `require_agent_ready`，先检查 `node-agent /state`。
5. 进入全局执行槽位或排队。
6. 转发到本机 `vLLM /v1/messages`。
7. 回包原样返回给客户端。
8. 写入 SQLite 请求日志。

### 6.2 OpenAI 客户端
1. 客户端请求 `POST /v1/chat/completions`。
2. `gateway-api` 做同样的鉴权、路由、排队、日志。
3. 转发到 `vLLM /v1/chat/completions`。
4. 返回 OpenAI 风格响应。

## 7. API 约定
### 7.1 业务接口
- `GET /v1/models`
  - 返回逻辑模型列表。
- `POST /v1/chat/completions`
  - OpenAI 兼容。
- `POST /v1/messages`
  - Claude Code 兼容。

### 7.2 管理接口
- `GET /admin/status`
  - 返回 `vLLM` 健康、队列长度、逻辑模型、`node-agent` 状态。
- `GET /admin/request-logs`
  - 返回最近请求日志。

### 7.3 节点接口
- `GET /state`
  - 返回 `node-agent` 运行状态。
- `GET /events`
  - 返回 `node-agent` 事件历史。
- `POST /manage/start`
  - 启动本机 `vLLM`。
- `POST /manage/stop`
  - 停止本机 `vLLM`。
- `POST /manage/restart`
  - 重启本机 `vLLM`。

## 8. 鉴权
- 支持两种头：
  - `Authorization: Bearer <key>`
  - `x-api-key: <key>`
- 默认只校验一个网关 key。
- key 错误直接返回 `401`。

## 9. 模型路由
- 逻辑模型名和后端模型名分离。
- 当前只保留一条真实后端映射：
  - `claude-sonnet-4-5-20250929` -> `qwen36-35b-a3b`
  - 其它 Claude 别名也指向同一个后端。
- 路由配置来源：`config/models.yaml`。
- 当前不做多后端。

## 10. 队列和并发
- 全局执行并发由 `execution_limit` 控制。
- 排队长度由 `queue_limit` 控制。
- 等待超时由 `wait_timeout` 控制。
- 规则：
  - 先到先排。
  - 队列满直接拒绝。
  - 排队超时返回 `504`。
  - 流式响应持有执行槽直到流结束。

## 11. `node-agent` 状态机
- 状态：
  - `stopped`
  - `starting`
  - `ready`
  - `degraded`
  - `recovering`
  - `alerting`
- 基本行为：
  - 健康时进入 `ready`。
  - 失败时进入 `degraded`。
  - 连续失败触发 `recovering`。
  - 自动恢复失败后进入 `alerting`。
- `gateway-api` 可配置为只在 `ready` 放行业务请求。

## 12. 数据与日志
- SQLite 路径：`runtime/data/gateway.db`
- 请求日志至少记录：
  - `request_id`
  - `model_name`
  - `protocol`
  - `status`
  - `error_message`
  - `created_at`
- 日志目标：
  - 请求审计。
  - 失败定位。
  - 未来对账。

## 13. 配置
- 静态配置：`config/defaults.yaml`
- 模型配置：`config/models.yaml`
- 环境变量覆盖：
  - 网关 key
  - 后端 URL
  - 后端模型名
  - 端口
  - 自动恢复参数
- 默认只支持单机单模型。

## 14. 运行脚本
- `scripts/start_vllm.sh`
  - 启动 `vLLM` 容器。
- `scripts/stop_vllm.sh`
  - 停止 `vLLM` 容器。
- `scripts/start_gateway.sh`
  - 启动 `gateway-api`。
- `scripts/start_agent.sh`
  - 启动 `node-agent`。

## 15. 测试策略
- 单元测试：
  - 模型路由。
  - 鉴权。
  - 队列。
  - 状态机。
- 集成测试：
  - `/v1/models`
  - `/v1/chat/completions`
  - `/v1/messages`
  - `/admin/status`
  - `/state`
- 手工验证：
  - `claude --bare -p hello`
  - `claude --bare -p "帮我解析一下当前项目"`

## 16. 验收标准
- `GET /v1/models` 正常返回。
- Claude Code 能走通 `hello`。
- Claude Code 能走通项目解析。
- `node-agent` 状态变化能影响 `gateway-api`。
- `vLLM` 异常后能进入降级并尝试恢复。
- 不需要依赖外部平台也能独立工作。

## 17. 备注
- V1 只要求“单机可用”。
- 任何平台化需求都不要倒灌进来。
