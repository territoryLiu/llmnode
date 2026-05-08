# V2 Completion Core 设计说明

## 1. 背景

`docs/blueprintV2.md` 定义了 V2 要把当前项目从“可用的个人网关”收敛为“可运营、可观测、可扩展的本地 LLM 平台”。当前代码已经完成了以下基础能力：

- `gateway-api` 已提供：
  - `/v1/models`
  - `/v1/chat/completions`
  - `/v1/messages`
  - `/admin/status`
  - `/admin/stream`
  - `/admin/request-logs`
  - `/admin/keys` CRUD
  - `/admin/models`
  - `/admin/schedule`
- `node-agent` 已提供：
  - `/state`
  - `/events`
  - `/manage/start`
  - `/manage/stop`
  - `/manage/restart`
- `web-console` 已具备总览、系统状态、使用记录、模型路由、调度、API Key 管理的基础版本。

但 `blueprintV2` 中仍有三类问题没有收口：

1. 网关控制面接口未补齐：
   - `GET /admin/events`
   - `GET /admin/logs`
   - `POST /admin/services/restart`
2. 管理闭环还不够完整：
   - `web-console` 对节点控制仍缺少统一的 restart 入口
   - `gateway-api` 尚未成为完整的唯一管理入口
3. 文档与现状出现偏差：
   - `/admin/keys` 已完成，但文档仍有“预留/未完成”描述
   - API Key 前端筛选搜索已完成，但文档仍标为未完成

本设计只解决上述“控制面闭环”问题，不扩张到其他子系统。

## 2. 本轮目标

本轮将 V2 的“完成”先定义为：

- 管理控制台只通过 `gateway-api` 即可查看请求日志、节点事件和运行状态
- 管理控制台可通过 `gateway-api` 发起一次后端 restart
- restart 后的状态变化可通过现有快照和 SSE 继续观察
- `blueprintV2.md` 与当前实现重新对齐，成为后续 V2 收尾阶段的可信基线

## 3. 非目标

以下内容明确不纳入本轮：

- Prometheus、metrics、alerts
- `request_logs` 审计字段扩展到完整画像
- SQLite 到 PostgreSQL 的迁移
- `node-agent` 更复杂的恢复编排或人工确认机制
- V3 的多后端能力、`llama.cpp` 接入、双后端路由
- 新的任务系统、命令队列、异步任务跟踪表

## 4. 范围定义

### 4.1 纳入本轮

- 在 `gateway-api` 中新增或补齐以下管理接口：
  - `GET /admin/events`
  - `GET /admin/logs`
  - `POST /admin/services/restart`
- 在 `web-console` 中补一个可用的 restart 交互入口
- 保持现有 `/admin/status` 与 `/admin/stream` 作为状态观察主通道
- 更新 `docs/blueprintV2.md`，修正文档状态

### 4.2 不纳入本轮

- 新增 `/admin/services/start` 与 `/admin/services/stop`
- 为日志、事件增加复杂筛选 DSL 或分页体系
- 将前端从 snapshot 模式整体重构为多 store、多明细接口模式

## 5. 设计原则

- 唯一管理入口：`web-console` 只访问 `gateway-api`
- 执行与展示解耦：控制命令只负责“受理”，状态收敛依赖现有快照与 SSE
- 最小变更：优先复用现有数据库表、store、视图和状态快照
- 文档对齐优先：先把 V2 当前真实边界写清楚，再进入 V3

## 6. 目标架构

### 6.1 角色分工

#### `web-console`

- 不直接调用 `node-agent`
- 继续通过现有 Pinia store 发管理请求
- 继续以 `/admin/status` 和 `/admin/stream` 作为总览状态来源

#### `gateway-api`

- 作为唯一公开管理入口
- 聚合三类管理数据：
  - 本地数据库中的 `request_logs`
  - 本地数据库中的 `agent_events`
  - `node-agent` 的控制能力
- 负责 admin 认证、错误归一和响应格式稳定

#### `node-agent`

- 继续作为本机后端执行器
- 暴露本机私有控制接口
- 不承担前端适配和公开认证逻辑

### 6.2 控制面数据边界

- `request_logs` 仍以 `gateway.db` 中的 `request_logs` 表为事实源
- `agent_events` 仍以 `gateway.db` 中的 `agent_events` 表为事实源
- restart 操作仍由 `node-agent` 真正执行，`gateway-api` 只负责转发和暴露统一入口

## 7. 接口设计

### 7.1 `GET /admin/events`

用途：

- 返回最近节点事件列表
- 供系统状态页和其他管理视图按需读取历史事件

行为：

- 需要 `admin` scope
- 从网关本地数据库读取 `agent_events`
- 默认返回最近 N 条事件，保持与当前 `list_agent_events()` 的最小模型一致

响应形态：

```json
{
  "events": [
    {
      "id": 12,
      "status": "recovering",
      "reason": "manual restart requested",
      "created_at": "2026-05-08 17:10:00"
    }
  ]
}
```

说明：

- 本轮不引入 `status_before`、`status_after`、`recovery_attempt` 等更细粒度事件字段
- 如果没有数据，返回空数组而不是报错

### 7.2 `GET /admin/logs`

用途：

- 提供 V2 文档口径中的“管理日志接口”
- 在本轮定义为请求审计日志，而不是系统文件日志或进程 stdout/stderr

行为：

- 需要 `admin` scope
- 复用当前 `request_logs` 查询逻辑
- 返回结构与 `/admin/request-logs` 对齐

响应形态：

```json
{
  "logs": [
    {
      "id": 101,
      "request_id": "req_123",
      "model_name": "qwen3",
      "status": "ok",
      "protocol": "openai",
      "error_message": null,
      "created_at": "2026-05-08 17:09:30",
      "api_key_id": 3,
      "auth_source": "db",
      "client_ip": "127.0.0.1",
      "user_agent": "curl/8.5.0",
      "rejection_reason": null
    }
  ]
}
```

说明：

- V2 阶段允许 `/admin/logs` 与 `/admin/request-logs` 等价
- 文档中必须明确这一点，避免被误解为“系统文件日志下载接口”

### 7.3 `POST /admin/services/restart`

用途：

- 为 `web-console` 提供统一的 restart 入口
- 由 `gateway-api` 代表管理员调用 `node-agent /manage/restart`

行为：

- 需要 `admin` scope
- `gateway-api` 以内部 HTTP 调用 `node-agent`
- 命令受理成功后立即返回，不等待整个恢复流程结束
- 恢复进展由 `/admin/status` 和 `/admin/stream` 观察

成功响应建议：

```json
{
  "accepted": true,
  "service": "backend",
  "action": "restart",
  "agent_status": "recovering"
}
```

说明：

- 本轮不做长轮询等待 ready
- 本轮不返回任务 ID
- 本轮不引入异步任务表

## 8. 数据流设计

### 8.1 查看事件

1. `web-console` 调用 `GET /admin/events`
2. `gateway-api` 校验 admin 权限
3. `gateway-api` 从本地数据库查询 `agent_events`
4. 返回事件列表给前端

### 8.2 查看日志

1. `web-console` 调用 `GET /admin/logs`
2. `gateway-api` 校验 admin 权限
3. `gateway-api` 从本地数据库查询 `request_logs`
4. 返回日志列表给前端

### 8.3 重启服务

1. `web-console` 调用 `POST /admin/services/restart`
2. `gateway-api` 校验 admin 权限
3. `gateway-api` 调用 `node-agent /manage/restart`
4. `node-agent` 执行 restart 并写入事件
5. `gateway-api` 返回“命令已受理”
6. 前端继续通过 `/admin/status` 或 `/admin/stream` 观察状态变化

## 9. 错误处理

### 9.1 `GET /admin/events`

- 查询成功但无数据：返回 `200` + 空数组
- 数据库异常：返回 `500`

### 9.2 `GET /admin/logs`

- 查询成功但无数据：返回 `200` + 空数组
- 数据库异常：返回 `500`

### 9.3 `POST /admin/services/restart`

- `gateway-api` 无法连接 `node-agent`：返回 `503`
- `node-agent` 返回非 2xx：返回 `502` 或 `503`
- 命令受理后恢复过程缓慢：不在本接口阻塞等待，由状态流体现

错误语义要求：

- 错误消息应清楚表明是“控制接口不可达”还是“restart 执行失败”
- 不在本轮引入复杂错误枚举

## 10. 前端设计

### 10.1 总体策略

- 保持当前 store 和 snapshot 驱动方式
- 只做最小接线，不做控制台架构重构

### 10.2 `stores/overview.ts`

新增或补齐以下能力：

- `fetchEvents()`
- `fetchLogs()`，或保留 snapshot 中 `logs` 的现有消费方式
- `restartService()`

约束：

- `restartService()` 成功后不等待最终 ready
- 成功后应触发一次 `fetchSnapshot()`，并继续依赖 SSE 观察后续变化

### 10.3 `SystemStatusView.vue`

新增一个 restart 入口：

- 按钮点击触发 `restartService()`
- 操作完成后刷新当前快照
- 按钮失败时展示可理解的错误消息

### 10.4 `UsageRecordsView.vue`

本轮不要求重构为独立日志 store：

- 可以继续消费 snapshot 中的 `logs`
- 如果后续需要按 blueprint 口径切到 `/admin/logs`，作为后续增量调整处理

## 11. 文档修正要求

需要更新 `docs/blueprintV2.md`，至少包括：

- 将 `/admin/keys` 从“预留/未完成”改为“已完成”
- 将 API Key 页面缺少筛选/搜索的描述删除或改为已完成
- 明确 `GET /admin/events`、`GET /admin/logs`、`POST /admin/services/restart` 的实现状态
- 明确本轮完成的是 V2 控制面闭环
- 明确 Prometheus、PostgreSQL、V3 多后端仍处于后续阶段

## 12. 验收标准

### 12.1 后端

- `GET /admin/events` 可通过 admin key 访问
- `GET /admin/events` 在无数据时返回空数组
- `GET /admin/logs` 可通过 admin key 访问
- `GET /admin/logs` 与 `/admin/request-logs` 的主数据一致
- `POST /admin/services/restart` 可通过 admin key 访问
- `POST /admin/services/restart` 能成功转发到 `node-agent /manage/restart`
- `node-agent` 不可达时，restart 返回 `503`
- `node-agent` 返回异常时，restart 返回 `502` 或 `503`

### 12.2 前端

- 系统状态页可以触发 restart
- restart 后前端不会阻塞等待最终 ready
- restart 后总览页或状态页可以继续通过现有 snapshot / SSE 观察状态推进
- 使用记录页不因本轮接口补齐产生回归

### 12.3 文档

- `docs/blueprintV2.md` 能真实反映当前实现状态
- V2 剩余事项与 V3 工作边界被重新写清楚

## 13. 完成后的状态

本轮完成后，项目应达到以下状态：

- `gateway-api` 成为真正完整的公开管理入口
- `web-console` 能完成“查看状态、查看请求日志、查看节点事件、发起 restart”的最小闭环
- `blueprintV2.md` 从过时描述恢复为可信基线
- 团队可以在此基础上继续做：
  - V2 observability 补强
  - V2 storage 迁移
  - V3 多后端开发
