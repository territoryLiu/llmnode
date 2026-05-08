# V2 API Key Detailed Design

**Date:** 2026-05-08  
**Status:** Draft for review  
**Scope:** `docs/blueprintV2.md` 中与 API Key、请求准入、请求审计、管理接口相关的 V2 详细设计补强

## 1. 目标

V2 需要把当前“单个静态网关 key”的最小鉴权方式，升级为可长期维护的控制面能力。目标不是构建完整 IAM 系统，而是在保持单机、单节点、单后端约束不变的前提下，补齐以下能力：

- 支持数据库持久化的 API Key 生命周期管理
- 保留配置级 break-glass 管理员 key 作为应急入口
- 为管理接口和推理接口建立最小 scope 模型
- 为 API Key 建立可执行的 `rpm_limit` 与 `concurrency_limit` 规则
- 将 key 身份与请求日志关联，形成最小审计闭环

本设计只覆盖 V2。V3 的多后端模型、分布式调度、复杂权限体系不在本次范围内。

## 2. 设计原则

- 日常主路径使用数据库 key；配置 key 仅作为应急入口
- 数据库不保存明文 key，只保存 `key_hash`
- 明文 secret 只在创建时返回一次，后续不可再次读取
- V2 权限模型保持最小化，只提供 `admin` 与 `inference` 两类 scope
- API Key 规则先于全局队列生效，避免超额 key 占用公共排队资源
- V2 的配额设计追求“易实现、易解释、易审计”，不追求平台级复杂度

## 3. Key 类型模型

V2 同时支持两类 key。

### 3.1 Break-Glass 管理员 Key

- 来源：`gateway.api_key` 配置项
- 角色：长期保留的 break-glass 管理员 key
- 用途：
  - 管理控制台失效时的应急入口
  - 数据库 key 体系异常时的恢复入口
  - 初始化和调试管理接口的兜底入口
- 权限：
  - 视为内建 `admin`
  - 可访问全部 `/admin/*` 接口
  - 可访问全部 `/v1/*` 业务接口
- 特殊规则：
  - 不出现在 `GET /admin/keys` 列表中
  - 不受 `rpm_limit` 与 `concurrency_limit` 限制
  - 请求日志中 `api_key_id = null`
  - 请求日志中 `auth_source = "bootstrap"`

### 3.2 数据库 Key

- 来源：管理员通过管理接口创建
- 角色：日常业务访问与控制面访问的主路径
- 权限：由 `scopes` 字段决定
- 配额：可受 `rpm_limit` 与 `concurrency_limit` 约束
- 请求日志中记录真实 `api_key_id`

## 4. API Key 数据模型

V2 的 API Key 主表包含以下字段。

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

### 4.1 字段定义

#### `id`

- 整数主键
- 只在系统内部和管理接口中使用

#### `key_hash`

- 明文 key 的哈希值
- 唯一
- 数据库不保存明文 key

#### `name`

- 人类可读标识
- 唯一
- 用于控制台展示、审计和运维定位

#### `status`

- 取值范围：
  - `active`
  - `disabled`

#### `scopes`

- JSON 数组
- V2 只允许以下枚举值：
  - `admin`
  - `inference`

#### `rpm_limit`

- 可空整数
- `null` 表示不限制
- 非空时表示该 key 最近 60 秒允许接受的最大请求数

#### `concurrency_limit`

- 可空整数
- `null` 表示不限制
- 非空时表示该 key 同时允许存在的最大活跃请求数

#### `created_at`

- 创建时间

#### `disabled_at`

- 仅在 `status = disabled` 时有值
- `active` 状态必须为 `null`

#### `last_used_at`

- 最近一次成功通过鉴权并进入业务准入流程的时间
- V2 保留该字段，便于后续审计扩展

#### `note`

- 可选备注
- 用于标识 key 的使用场景，例如 `console-admin`、`ci-runner`、`local-agent`

### 4.2 约束

- `key_hash` 唯一
- `name` 唯一
- `scopes` 不能为空数组
- `admin` 与 `inference` 可同时出现
- `rpm_limit`、`concurrency_limit` 若存在，则必须大于 0

## 5. 状态模型

V2 中 API Key 只保留两态，避免提前引入复杂状态机。

- `active`
- `disabled`

### 5.1 `active`

- 允许鉴权
- 允许进入 scope 校验
- 允许参与配额判断

### 5.2 `disabled`

- 鉴权直接失败
- 不允许进入后续业务准入流程
- 记录 `disabled_at`

### 5.3 删除语义

V2 不引入 `deleted` 状态。

- 删除动作通过 `DELETE /admin/keys/{id}` 执行
- 删除采用物理删除
- 回收站、软删除、恢复功能不在 V2 范围内

## 6. Scope 模型

V2 的 scope 体系保持最小化。

### 6.1 `admin`

- 允许访问全部 `/admin/*`
- 允许访问全部 `/v1/*`

### 6.2 `inference`

- 允许访问：
  - `GET /v1/models`
  - `POST /v1/chat/completions`
  - `POST /v1/messages`
- 不允许访问任何 `/admin/*`

### 6.3 Scope 判定规则

- break-glass key 固定视为 `admin`
- 数据库 key 的 `scopes` 决定权限
- 缺失所需 scope 时返回 `403 Forbidden`
- key 缺失、无效或禁用时返回 `401 Unauthorized`

## 7. 鉴权流程

### 7.1 Token 提取

网关从以下请求头中提取 token：

- `Authorization: Bearer <token>`
- `x-api-key: <token>`

若同时存在，以 `Authorization` 为准。

### 7.2 鉴权顺序

1. 提取 token
2. 若 token 命中 `gateway.api_key`，按 break-glass key 处理
3. 若未命中 break-glass key，则对 token 计算哈希
4. 用 `key_hash` 查询数据库
5. 若未找到记录，返回 `401`
6. 若找到但 `status = disabled`，返回 `401`
7. 若 key 有效，继续执行 scope 校验
8. scope 通过后，继续执行调度、agent、配额和并发准入

### 7.3 哈希规则

V2 采用固定哈希规则：

- 对明文 key 进行 UTF-8 编码
- 使用 SHA-256 计算摘要
- 以小写十六进制字符串形式存储到 `key_hash`

V2 不引入额外的密钥托管或加密设施；目标是确保数据库中不保存明文 key，并保证实现简单、稳定、可复现。

## 8. CRUD 契约

### 8.1 `GET /admin/keys`

- 作用：返回全部数据库 key 的脱敏列表
- 权限：`admin`
- 不返回明文 secret

返回示例：

```json
{
  "keys": [
    {
      "id": 1,
      "name": "console-admin",
      "status": "active",
      "scopes": ["admin"],
      "rpm_limit": null,
      "concurrency_limit": null,
      "created_at": "2026-05-08T12:00:00Z",
      "disabled_at": null,
      "last_used_at": null,
      "note": "main console key"
    }
  ]
}
```

### 8.2 `POST /admin/keys`

- 作用：创建数据库 key
- 权限：`admin`
- 服务端生成明文 secret
- 数据库只保存 `key_hash`
- 响应中明文 secret 只返回一次

请求示例：

```json
{
  "name": "ci-inference",
  "scopes": ["inference"],
  "rpm_limit": 120,
  "concurrency_limit": 2,
  "note": "CI runner"
}
```

响应示例：

```json
{
  "key": {
    "id": 12,
    "name": "ci-inference",
    "status": "active",
    "scopes": ["inference"],
    "rpm_limit": 120,
    "concurrency_limit": 2,
    "created_at": "2026-05-08T12:00:00Z",
    "disabled_at": null,
    "last_used_at": null,
    "note": "CI runner"
  },
  "secret": "ln_live_xxxxxxxxx"
}
```

### 8.3 `PATCH /admin/keys/{id}`

- 作用：修改现有 key 的元数据
- 权限：`admin`
- 允许修改：
  - `name`
  - `status`
  - `scopes`
  - `rpm_limit`
  - `concurrency_limit`
  - `note`
- 不支持在 V2 中读取或重发明文 secret

### 8.4 `DELETE /admin/keys/{id}`

- 作用：删除数据库 key
- 权限：`admin`
- V2 使用物理删除
- break-glass key 不可通过该接口删除

## 9. 请求准入顺序

API Key 相关规则应被纳入 V2 的统一请求准入链路中。  
推荐顺序如下：

1. 提取 token
2. break-glass / 数据库 key 鉴权
3. scope 校验
4. 调度策略校验
5. `node-agent` 状态校验
6. `rpm_limit` 校验
7. `concurrency_limit` 校验
8. 全局执行槽位与 FIFO 队列
9. 模型路由与请求转发
10. 请求日志落库

关键约束：

- key 级规则先于全局队列
- 已超额 key 不应占用公共队列资源
- 流式请求在整个流结束前都占用其并发槽位

## 10. `rpm_limit` 规则

### 10.1 定义

- `rpm_limit = null`：不限制
- `rpm_limit = N`：最近 60 秒窗口内最多接受 `N` 个请求

### 10.2 统计窗口

- 使用滑动 60 秒窗口
- 不使用“自然分钟”边界统计

### 10.3 计数规则

计入 RPM 的请求：

- 已通过鉴权
- 已通过 scope 校验
- 已通过调度和 agent 状态校验
- 已被系统正式接受进入执行流程

不计入 RPM 的请求：

- 缺失 key
- key 无效
- key 被禁用
- scope 不足
- 调度不允许
- agent 不 ready

说明：

- 一旦请求通过上述前置校验并被接受，即使后端推理最终报错，该请求仍计入 RPM
- break-glass key 不受 RPM 限制

### 10.4 超限行为

- 超限返回 `429 Too Many Requests`
- 请求日志应记录 `rejection_reason = "rpm_limit_exceeded"`

## 11. `concurrency_limit` 规则

### 11.1 定义

- `concurrency_limit = null`：不限制
- `concurrency_limit = N`：该 key 同时最多允许存在 `N` 个活跃请求

### 11.2 活跃请求定义

活跃请求是指已经进入执行流程但尚未结束的请求，包括：

- 非流式请求：直到响应完成
- 流式请求：直到流结束

### 11.3 超限行为

- 当活跃请求数达到上限时，新请求直接返回 `429 Too Many Requests`
- V2 不为单个 key 建立独立等待队列
- 请求日志应记录 `rejection_reason = "concurrency_limit_exceeded"`

### 11.4 特殊规则

- break-glass key 不受并发限制
- key 级并发限制发生在全局队列之前

## 12. 请求日志补强

为了让 API Key 体系形成最小审计闭环，V2 的请求日志最少增加以下字段：

- `api_key_id`
- `auth_source`
- `client_ip`
- `user_agent`
- `rejection_reason`

### 12.1 字段语义

#### `api_key_id`

- 数据库 key 请求记录真实 id
- break-glass key 请求记录 `null`

#### `auth_source`

- 取值：
  - `bootstrap`
  - `database`

#### `client_ip`

- 来源 IP

#### `user_agent`

- 客户端标识

#### `rejection_reason`

- 用于记录被拒绝原因，例如：
  - `invalid_api_key`
  - `scope_denied`
  - `rpm_limit_exceeded`
  - `concurrency_limit_exceeded`
  - `queue_full`
  - `queue_timeout`

## 13. 对 `blueprintV2.md` 的修改范围

将本设计回填到 `docs/blueprintV2.md` 时，同步修改以下章节：

- `6.1 API Key`
- `6.3 Request Log`
- `8.1 业务请求`
- `9.2 网关管理 API`
- `9.4 当前预留`
- `10. 队列与准入`

其中：

- `6.1` 升级为 API Key 主设计章节
- `6.3` 明确请求日志新增字段
- `8.1` 明确准入顺序
- `9.2 / 9.4` 明确 API Key CRUD 契约
- `10` 明确 `rpm_limit` 与 `concurrency_limit` 的执行规则

## 14. V2 边界

本设计明确不包含以下内容：

- key rotation
- 多级角色体系
- 软删除与回收站
- 可恢复删除
- 更复杂的使用分析看板
- 多窗口或自定义窗口限流
- 跨节点配额共享

这些能力可留待 V2 后续迭代或更高版本处理。

## 15. 成功标准

当以下目标同时满足时，说明 V2 的 API Key 详细设计足以指导开发：

- break-glass key 与数据库 key 的边界清晰
- API Key 生命周期规则明确
- scope 规则明确
- `rpm_limit` 与 `concurrency_limit` 可直接开发
- 请求日志字段能支撑最小审计闭环
- `blueprintV2.md` 可据此补成实现级文档，而不是继续停留在字段草案阶段
