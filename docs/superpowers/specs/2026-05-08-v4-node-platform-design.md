# V4 Node Platform Design

**Date:** 2026-05-08  
**Status:** Draft for review  
**Scope:** `llmnode` 从 V3 的单机双后端控制面，升级为独立可部署的节点平台，并为未来作为 `sub2api` 下游节点平台接入预留清晰边界

## 1. 目标

V4 的目标不是把 `llmnode` 直接扩展成一个支付、订阅、用户、结算齐全的商业平台，而是把它升级为一个：

- 独立可部署
- 自带前后端
- 面向个人与小团队
- 默认单节点、可演进到 1~3 节点
- 可被上层平台接管

的本地大模型节点平台。

V4 需要同时满足两类目标：

- 作为独立平台，可以完成节点管理、模型注册、运行 profile 管理、实例启停、推理网关、审计与控制台
- 作为下游节点平台，未来可以被 `sub2api` 之类的上层平台通过稳定接口管理与调用

## 2. 总定位

V4 的定位是：

- **独立可部署的节点控制平台**
- **节点层 / runtime 层 / gateway 层产品**
- **不是平台层商业系统**

V4 的角色边界如下：

- `llmnode` 负责：
  - 节点注册
  - 本地模型与后端运行
  - 推理实例控制
  - 兼容网关入口
  - 轻量 API Key、审计、调度
  - 管理控制台
  - 上层平台可接入的 northbound 管理接口
- `sub2api` 或未来其它上层平台负责：
  - 用户体系
  - 支付与充值
  - 订阅、套餐与复杂结算
  - 复杂多租户
  - 多平台统一调度与商业化运营

## 3. V4 与 V1/V2/V3 的关系

- `V1`：单后端原型，只求可用
- `V2`：单机控制面，平台化但仍固定 `vLLM`
- `V3`：单机双后端，加入 `llama.cpp`，建立本地多后端抽象
- `V4`：从“单机双后端控制面”升级为“独立节点平台”

V4 不替代前序版本的核心接口约定，而是在保持 OpenAI / Claude 兼容入口不变的前提下，引入：

- `control-api`
- 节点对象模型
- 运行实例对象模型
- southbound / northbound 边界
- 小规模多节点预留

## 4. 设计原则

- 默认对单节点一体化部署优化
- 架构上允许 1~3 节点接入，但不做大规模集群
- 控制面、推理入口、节点执行层边界清晰
- `gateway-api` 保持薄，不承担节点编排职责
- `node-agent` 负责执行，不负责制定全局策略
- `control-api` 负责控制面事实源
- `web-console` 只访问控制面
- 上层平台只通过 northbound 管理接口与标准推理接口接入
- 不把支付、订阅、用户体系倒灌进节点平台

## 5. 版本边界

### 5.1 V4 要做

- 引入 `control-api` 作为独立控制面
- 保留 `gateway-api` 作为推理业务入口
- 强化 `node-agent` 的节点注册、上报、执行职责
- 建立统一的多后端 `backend-driver` 抽象
- 引入节点对象模型、artifact 对象模型、runtime profile、实例对象模型
- 提供一体化管理前端
- 支持单节点一体化部署
- 支持 1~3 节点的小规模接入预留
- 暴露 northbound 管理接口，支持未来 `sub2api` 集成

### 5.2 V4 不做

- 支付、充值、订单、订阅
- 用户注册登录体系
- 复杂多租户
- 大规模分布式调度
- 跨节点全局队列一致性
- 委托式复杂策略执行
- 自动下载模型权重
- 完整 Kubernetes / 多机房 / 高可用平台设计

## 6. 总体架构

V4 采用四层结构。

### 6.1 接入层

- `web-console`
- OpenAI / Claude 兼容客户端
- 未来上层平台（如 `sub2api`）

职责：

- 展示控制台
- 发起管理请求
- 发起推理请求
- 接入稳定的 northbound 管理能力

### 6.2 控制层

- `control-api`

职责：

- 节点注册与发现
- 模型 artifact 注册
- runtime profile 管理
- 逻辑模型编排
- API Key、调度、审计、事件
- 节点能力与实例状态汇总
- 为 `gateway-api` 提供可消费的路由视图
- 为未来上层平台提供 northbound 管理接口

### 6.3 网关层

- `gateway-api`

职责：

- 提供 `/v1/models`
- 提供 `/v1/chat/completions`
- 提供 `/v1/messages`
- 认证鉴权
- 路由解析
- 队列与并发控制
- 轻量准入与审计

约束：

- 不直接承担节点编排
- 不直接维护另一套节点事实源
- 不直接控制推理后端进程

### 6.4 节点运行层

- `node-agent`
- `backend-driver`
- 本地 runtime 采集与状态上报

职责：

- 启停本地推理实例
- 执行健康检查
- 上报资源与实例状态
- 执行控制命令
- 处理本地模型 inventory 探测

## 7. 组件职责

### 7.1 `web-console`

负责：

- 节点列表与详情
- 模型 artifact 管理
- runtime profile 管理
- 逻辑模型与实例管理
- API Key / 调度 / 日志 / 事件
- northbound 集成状态展示

约束：

- 只调用 `control-api`
- 不直接调用 `node-agent`
- 不直接操纵本地 runtime

### 7.2 `control-api`

负责：

- 节点层事实源
- 逻辑模型编排
- 目标状态生成
- southbound 控制命令生命周期
- 审计与事件聚合
- northbound 管理接口

### 7.3 `gateway-api`

负责：

- 标准推理接口
- API Key 鉴权
- 逻辑模型到运行实例的路由
- 轻量配额、并发与排队
- 推理请求审计

### 7.4 `node-agent`

负责：

- 节点注册
- 心跳
- 能力上报
- 本地模型扫描
- 实例启停
- 健康检查
- 执行命令回报

### 7.5 `backend-driver`

每个 driver 只回答三件事：

- 如何启动
- 如何检查健康
- 如何返回运行时元数据

V4 预期至少支持：

- `vllm`
- `llama_cpp`

## 8. 部署形态

### 8.1 形态 A：单机一体化

默认推荐。

一台机器上部署：

- `control-api`
- `gateway-api`
- `node-agent`
- `web-console`

适合：

- 个人
- 小团队
- 本地开发和内部工具环境

### 8.2 形态 B：单节点分进程

仍然是一台机器，但控制层与推理层逻辑分开运行。

适合：

- 资源隔离
- 更明确的职责边界
- 更容易观察控制层与运行层差异

### 8.3 形态 C：小规模多节点

- 一个 `control-api`
- 多个 `node-agent`
- 一个或多个 `gateway-api`

V4 只要求支持：

- 少量远程节点接入
- 节点状态汇总
- 将逻辑模型绑定到特定节点或节点组

V4 不要求支持：

- 大规模节点池
- 多控制面主从
- 复杂一致性协议

## 9. 核心对象模型

### 9.1 `Node`

表示一个受控节点。

字段：

- `id`
- `name`
- `mode`：`local` / `remote`
- `endpoint`
- `status`
- `labels`
- `agent_version`
- `last_heartbeat_at`

### 9.2 `NodeCapabilitySnapshot`

表示节点当前能力快照。

字段：

- `node_id`
- `backend_types`
- `gpu_summary`
- `cpu_summary`
- `ram_bytes`
- `disk_bytes`
- `supports_tool_calling`
- `supports_vision`
- `sampled_at`

### 9.3 `ModelArtifact`

表示模型文件或模型目录本身。

字段：

- `id`
- `name`
- `family`
- `format`
- `model_path`
- `backend_compatibility`
- `size_bytes`

### 9.4 `RuntimeProfile`

表示某种后端运行配置模板。

字段：

- `id`
- `backend_type`
- `profile_name`
- `launch_config`
- `resource_policy`
- `feature_flags`

### 9.5 `LogicalModelRoute`

表示客户端看到的逻辑模型名与目标运行实例之间的映射。

字段：

- `id`
- `logical_name`
- `display_name`
- `target_node_id` 或 `target_selector`
- `artifact_id`
- `runtime_profile_id`
- `enabled`
- `protocol_capabilities`

### 9.6 `RuntimeInstance`

表示某个节点上的实际运行实例。

字段：

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

## 10. Southbound 接口

Southbound 定义为：

- `control-api` 与 `node-agent` 之间的私有控制接口
- 面向节点执行层
- 不对普通客户端开放

### 10.1 Southbound 能力

#### 节点上报

- 节点注册
- 心跳
- 能力快照
- 本地模型 inventory
- 实例状态
- 节点事件

#### 控制命令

- 启动实例
- 停止实例
- 重启实例
- 应用 runtime profile
- 重新扫描模型目录
- 拉取最新路由快照

### 10.2 Southbound 原则

- V4 先使用 HTTP + token + 心跳 / 轮询
- 不引入消息队列作为前提
- `node-agent` 是执行者，不是策略制定者
- `control-api` 是控制面事实源

## 11. Northbound 接口

Northbound 定义为：

- 给未来 `sub2api` 或其他上层平台使用的稳定管理接口
- 面向平台集成
- 稳定、版本化、边界清晰

### 11.1 管理面能力

- 查询节点列表
- 查询节点健康与能力
- 查询逻辑模型列表
- 查询实例状态
- 触发受控操作
  - 重启某逻辑模型
  - 重新同步某节点 inventory

### 11.2 推理面能力

`llmnode` 仍然通过标准推理接口对上提供服务：

- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/messages`

这意味着未来 `sub2api` 可以同时：

- 把 `llmnode` 作为标准推理上游
- 把 `llmnode` 作为受控节点平台

## 12. 核心请求流

### 12.1 推理请求流

1. 客户端请求进入 `gateway-api`
2. `gateway-api` 完成鉴权、准入与逻辑模型解析
3. `gateway-api` 读取 `control-api` 提供的路由快照或缓存视图
4. 获取目标 `RuntimeInstance`
5. 直接代理到实例监听地址
6. 回写审计与指标

关键原则：

- `node-agent` 不参与每个请求的热路径决策
- 热路径消费的是控制面收敛后的运行视图

### 12.2 节点状态上报流

1. `node-agent` 启动
2. 向 `control-api` 注册
3. 周期性上报心跳、能力、inventory、实例状态、错误事件
4. `control-api` 更新节点层事实源

### 12.3 控制命令流

1. 管理员通过 `web-console` 发起操作
2. `web-console` 请求 `control-api`
3. `control-api` 生成目标状态
4. `node-agent` 获取待执行命令并执行
5. 结果回报给 `control-api`

## 13. 部署流

V4 应把部署体验抽象成一条标准流程。

### 13.1 节点初始化

- 启动一体化实例
- 自动创建 `local-node`

### 13.2 资源发现

`node-agent` 扫描：

- 本地模型目录
- 可用后端
- GPU / CPU / RAM

### 13.3 注册 Artifact 与 Profile

管理员选择：

- 哪个模型目录作为 `ModelArtifact`
- 使用哪个 `RuntimeProfile`
- 绑定到哪个节点

### 13.4 生成 Logical Route

配置对外逻辑模型名并绑定：

- 节点
- artifact
- runtime profile

### 13.5 启动实例

- `control-api` 下发目标状态
- `node-agent` 启动实例
- 生成 `RuntimeInstance`

### 13.6 进入服务

- `/v1/models` 暴露逻辑模型
- 客户端开始调用

## 14. `sub2api` 集成模式

### 14.1 模式 A：标准上游模式

`sub2api` 把 `llmnode` 当作普通 OpenAI / Claude 兼容上游使用。

只依赖：

- `/v1/models`
- `/v1/chat/completions`
- `/v1/messages`

适合：

- 快速接入
- 先验证本地模型流量接入能力

### 14.2 模式 B：受管节点模式

`sub2api` 同时使用：

- `llmnode` 的 northbound 管理接口
- `llmnode` 的标准推理接口

能力包括：

- 查询节点列表
- 查询节点能力
- 查询逻辑模型
- 查询实例状态
- 触发受控操作

此模式是 V4 的目标集成模式。

### 14.3 模式 C：平台委托调度模式

上层平台在外部做更复杂的策略决策，再委托 `llmnode` 执行。

V4 只预留此模式边界，不在 V4 内部实现完整委托调度。

## 15. 接入与集成原则

- `sub2api` 不直接访问 `node-agent`
- `sub2api` 不直接控制本地 runtime 进程
- `sub2api` 不绕过 `control-api` 建立另一套节点事实
- `web-console` 只访问 `control-api`
- `gateway-api` 只处理推理流量入口
- `node-agent` 只负责单节点执行

## 16. 验收标准

### 16.1 独立平台成立

- 单机上可完成一体化部署
- 前端可完成节点、artifact、profile、实例管理
- 推理业务接口仍兼容 OpenAI / Claude 客户端

### 16.2 节点平台成立

- 默认存在 `local-node`
- `node-agent` 可完成注册、心跳、inventory、实例状态上报
- `control-api` 维护节点层事实源

### 16.3 多后端平台成立

- `vllm`、`llama.cpp` 均通过统一对象模型纳入控制面
- 逻辑模型路由不再直接耦合本地脚本

### 16.4 集成边界成立

- `sub2api` 至少可用“标准上游模式”接入
- V4 明确 northbound 管理接口边界
- 上层平台无需直接访问 `node-agent`

### 16.5 项目仍然精悍

- 默认部署路径简单
- 不引入支付、用户体系和重型商业平台依赖
- 不把 `llmnode` 扩展成 `sub2api` 的复制品

## 17. 推荐开发顺序

1. 从 V3 中提炼 `control-api`
2. 引入 `Node`、`RuntimeProfile`、`RuntimeInstance` 等核心对象
3. 增强 `node-agent` 的注册、心跳、inventory 上报
4. 让 `gateway-api` 改为消费控制面路由视图
5. 完成前端控制台的节点 / artifact / profile / instance 管理
6. 跑通单机一体化部署
7. 跑通 1~3 节点的小规模接入
8. 预留 northbound 接口并验证 `sub2api` 的标准上游接入

## 18. 明确不做

- 支付与结算
- 用户注册登录
- 复杂多租户
- 大规模调度
- 跨节点强一致队列
- 商业化运营看板
- 自动下载权重
- 完整云原生高可用方案
