# blueprintV4

## 1. 定位
- V4 在 V3 的单机双后端基础上，升级为独立可部署的节点平台。
- 目标不是把 `llmnode` 扩展成完整商业平台，而是把它做成：
  - 自带前后端
  - 独立可安装、可运维、可服务
  - 默认单节点，支持未来 1~3 节点扩展
  - 可被 `sub2api` 之类的上层平台纳管
- V4 的职责严格停留在节点层、runtime 层、gateway 层，不承担支付、订阅、用户和复杂多租户逻辑。

## 2. V4 目标
- 提供完整的独立部署前后端体验。
- 在现有 `gateway-api`、`node-agent`、`web-console` 之上引入 `control-api`。
- 把本地模型部署从“脚本 + 配置 + 单机抽象”升级为“节点对象 + artifact + runtime profile + instance”。
- 保持对 OpenAI / Claude 客户端兼容。
- 为未来接入 `sub2api` 提供 northbound 管理接口与稳定推理接口。

## 3. 核心原则
- 默认对个人和小团队单节点一体化部署优化。
- 架构上允许小规模多节点，但不设计成大规模集群平台。
- 控制面、推理入口、节点执行层边界清晰。
- `gateway-api` 保持薄，负责热路径业务入口，不承担复杂控制面逻辑。
- `control-api` 是节点层事实源。
- `node-agent` 是单节点执行源。
- `web-console` 只访问控制面，不直接操纵节点内部状态。
- 上层平台只通过稳定的 northbound 管理接口和标准推理接口接入。

## 4. 版本边界
### 4.1 V4 要做
- `control-api` 作为独立控制面。
- `gateway-api` 继续作为推理业务入口。
- `node-agent` 支持节点注册、心跳、inventory 上报、命令执行。
- `backend-driver` 统一本地多后端运行抽象。
- `Node`、`ModelArtifact`、`RuntimeProfile`、`LogicalModelRoute`、`RuntimeInstance` 等核心对象。
- 一体化部署体验。
- 小规模多节点预留。
- northbound / southbound 接口边界。
- 未来 `sub2api` 接入能力。

### 4.2 V4 不做
- 支付、充值、订单、订阅。
- 用户注册登录体系。
- 复杂多租户。
- 大规模分布式调度。
- 跨节点全局队列一致性。
- 委托式复杂策略执行。
- 自动下载模型权重。
- 完整 Kubernetes / 多机房 / 高可用平台设计。

## 5. 总体架构
### 5.1 接入层
- `web-console`
- OpenAI / Claude 兼容客户端
- 未来上层平台（如 `sub2api`）

### 5.2 控制层
- `control-api`
- 负责：
  - 节点注册与发现
  - 模型 artifact 注册
  - runtime profile 管理
  - 逻辑模型编排
  - API Key、调度、审计、事件
  - 节点能力与实例状态汇总
  - northbound 管理接口

### 5.3 网关层
- `gateway-api`
- 负责：
  - `/v1/models`
  - `/v1/chat/completions`
  - `/v1/messages`
  - 鉴权
  - 路由解析
  - 队列、并发与轻量配额
  - 推理请求审计

### 5.4 节点运行层
- `node-agent`
- `backend-driver`
- 本地 runtime 采集与状态上报

## 6. 核心分层
### 6.1 接入层
- 展示控制台
- 发起管理请求
- 发起推理请求
- 接入 northbound 管理能力

### 6.2 控制层
- 维护节点层事实源
- 生成目标运行状态
- 管理 southbound 命令生命周期
- 提供 northbound 管理视图

### 6.3 网关层
- 消费控制面路由视图
- 处理推理热路径
- 不直接控制 runtime 进程

### 6.4 节点运行层
- 负责单节点执行
- 上报资源、实例、错误状态
- 执行启停和扫描命令

## 7. 核心对象模型
### 7.1 `Node`
- `id`
- `name`
- `mode`
- `endpoint`
- `status`
- `labels`
- `agent_version`
- `last_heartbeat_at`

### 7.2 `NodeCapabilitySnapshot`
- `node_id`
- `backend_types`
- `gpu_summary`
- `cpu_summary`
- `ram_bytes`
- `disk_bytes`
- `supports_tool_calling`
- `supports_vision`
- `sampled_at`

### 7.3 `ModelArtifact`
- `id`
- `name`
- `family`
- `format`
- `model_path`
- `backend_compatibility`
- `size_bytes`

### 7.4 `RuntimeProfile`
- `id`
- `backend_type`
- `profile_name`
- `launch_config`
- `resource_policy`
- `feature_flags`

### 7.5 `LogicalModelRoute`
- `id`
- `logical_name`
- `display_name`
- `target_node_id` 或 `target_selector`
- `artifact_id`
- `runtime_profile_id`
- `enabled`
- `protocol_capabilities`

### 7.6 `RuntimeInstance`
- `id`
- `node_id`
- `artifact_id`
- `runtime_profile_id`
- `backend_type`
- `status`
- `listen_endpoint`
- `health_state`
- `last_error`
- `started_at`

## 8. Southbound 接口
- 定义：`control-api` 与 `node-agent` 的私有控制接口。
- 面向节点执行层。
- 不对普通客户端开放。

### 8.1 节点上报
- 注册
- 心跳
- 能力快照
- 本地模型 inventory
- 实例状态
- 节点事件

### 8.2 控制命令
- 启动实例
- 停止实例
- 重启实例
- 应用 runtime profile
- 重新扫描模型目录
- 拉取最新路由快照

### 8.3 原则
- V4 先使用 HTTP + token + 心跳 / 轮询。
- 不引入消息队列作为前提。
- `node-agent` 是执行者，不是策略制定者。
- `control-api` 是控制面事实源。

## 9. Northbound 接口
- 定义：给未来 `sub2api` 或其它上层平台使用的稳定管理接口。
- 面向平台集成。
- 稳定、版本化、边界清晰。

### 9.1 管理面能力
- 查询节点列表
- 查询节点健康与能力
- 查询逻辑模型列表
- 查询实例状态
- 触发受控操作

### 9.2 推理面能力
- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/messages`

## 10. 推理请求流
1. 客户端请求进入 `gateway-api`。
2. `gateway-api` 完成鉴权、准入与逻辑模型解析。
3. `gateway-api` 读取 `control-api` 提供的路由快照或缓存视图。
4. 获取目标 `RuntimeInstance`。
5. 直接代理到实例监听地址。
6. 回写审计与指标。

### 10.1 关键原则
- `node-agent` 不参与每个请求的热路径决策。
- 热路径消费的是控制面收敛后的运行视图。

## 11. 节点上报流
1. `node-agent` 启动。
2. 向 `control-api` 注册。
3. 周期性上报：
  - 心跳
  - 能力快照
  - 本地模型 inventory
  - 实例状态
  - 错误事件
4. `control-api` 更新节点层事实源。

## 12. 控制命令流
1. 管理员在 `web-console` 发起操作。
2. `web-console` 调用 `control-api`。
3. `control-api` 生成目标状态。
4. `node-agent` 获取待执行命令并执行。
5. 执行结果回报 `control-api`。

## 13. 部署形态
### 13.1 单机一体化
- 默认推荐。
- 一台机器上运行：
  - `control-api`
  - `gateway-api`
  - `node-agent`
  - `web-console`

### 13.2 单节点分进程
- 同一机器上将控制面与推理运行面分开部署。
- 强化边界与隔离。

### 13.3 小规模多节点
- 一个 `control-api`
- 多个 `node-agent`
- 一个或多个 `gateway-api`
- 只要求支持 1~3 节点范围内的小规模接入

## 14. `sub2api` 集成模式
### 14.1 标准上游模式
- `sub2api` 把 `llmnode` 当成普通 OpenAI / Claude 兼容上游。
- 只依赖标准推理接口。

### 14.2 受管节点模式
- `sub2api` 同时使用：
  - `llmnode` 的 northbound 管理接口
  - `llmnode` 的标准推理接口
- 这是 V4 的目标集成模式。

### 14.3 远期委托调度模式
- 上层平台在外部做更复杂的策略决策，再委托 `llmnode` 执行。
- V4 只预留边界，不在 V4 内部实现完整委托调度。

## 15. 验收标准
### 15.1 独立平台成立
- 单机上可完成一体化部署。
- 前端可完成节点、artifact、profile、实例管理。
- 推理接口继续兼容 OpenAI / Claude 客户端。

### 15.2 节点平台成立
- 默认存在 `local-node`。
- `node-agent` 可完成注册、心跳、inventory、实例状态上报。
- `control-api` 能维护节点层事实源。

### 15.3 多后端平台成立
- `vllm`、`llama.cpp` 均通过统一对象模型纳入控制面。
- `LogicalModelRoute` 不再直接耦合本地脚本。

### 15.4 集成边界成立
- `sub2api` 至少可使用标准上游模式接入。
- V4 文档中明确 northbound 管理接口。
- 上层平台无需直接访问 `node-agent`。

### 15.5 项目仍然精悍
- 默认部署路径简单。
- 不引入支付、用户体系和重型商业平台依赖。
- 不把 `llmnode` 做成 `sub2api` 的复制品。

## 16. 推荐开发顺序
1. 从 V3 中提炼 `control-api`。
2. 引入 `Node`、`RuntimeProfile`、`RuntimeInstance` 等核心对象。
3. 增强 `node-agent` 的注册、心跳、inventory 上报。
4. 让 `gateway-api` 改为消费控制面路由视图。
5. 完成前端控制台的节点 / artifact / profile / instance 管理。
6. 跑通单机一体化部署。
7. 跑通 1~3 节点的小规模接入。
8. 预留 northbound 接口并验证 `sub2api` 的标准上游接入。

## 17. 明确不做
- 支付与结算
- 用户注册登录
- 复杂多租户
- 大规模调度
- 跨节点强一致队列
- 商业化运营看板
- 自动下载权重
- 完整云原生高可用方案
