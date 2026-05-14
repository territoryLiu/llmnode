# Readiness、Usage Ledger 与 API Key 管理台设计

## 0. 文档定位

这份设计文档服务于 `llmnode` 当前路线图中的三项收口工作：

1. 启动窗口期与 readiness 加固
2. 平台级用量与 Token 指标采集
3. API Key 管理与管理台补厚

它回答的是：

- 启动窗口期应该如何定义正式状态语义
- 用量统计应该以什么数据模型落库与聚合
- API Key 应该如何在不破坏安全边界的前提下提供管理台体验
- Agent / Gateway / SQLite / Web Console 的职责边界如何拆分
- 第一版要做什么，不做什么，如何验收

它不负责：

- 直接替代 `current / contracts / process` 成为长期真相
- 展开逐任务实施清单，那应进入 `docs/superpowers/plans/*.md`
- 定义多节点、计费、配额和导出等后续平台化能力

## 1. 背景与问题定义

当前系统已经具备单机三后端正式主链路，但还有三类明显缺口：

### 1.1 启动窗口期错误语义不准确

- 当前后端在 `/v1/models` 已返回 `200` 时，首个 Claude 流式请求仍可能失败
- 现有 ready 判定偏粗，只看了 HTTP 可达，没有区分“可探活”和“可稳定推理”
- 对客户端而言，这会把可重试的热身窗口误表现为普通 `500`

### 1.2 用量指标只有基础版，没有形成正式账本

- 当前已有 `request_metrics` 基础表和 `GET /admin/diagnostics/metrics`
- 但还不能稳定回答：
  - 哪个模型用了多少 token
  - 哪种后端更忙
  - 哪个 API Key 使用量最高
  - 某天、某月、某年的趋势如何
  - cache 命中与未命中 token 分别是多少

### 1.3 API Key 已可存储，但还不是正式管理能力

- 当前已有 API Key 存储和基础 CRUD 雏形
- 但仍缺少：
  - 脱敏展示
  - 新建当次显示 / 隐藏 / 复制明文
  - Base URL 展示与复制
  - 关联用量展示
  - 与管理台整体口径一致的视图模型

## 2. 设计目标

第一版设计目标限定为“单机管理台可运营”：

- 对客户端准确表达后端热身与可重试状态
- 以 SQLite 为正式真相源，形成可聚合的用量账本
- 在不引入可逆明文存储的前提下，把 API Key 管理做成正式管理台能力
- 让前端消费后端视图模型，而不是自己拼状态和统计口径

## 3. 设计范围

### 3.1 包含

- readiness 状态语义拆分
- 启动后极小推理探针
- `503 + Retry-After + detail` 的网关对外语义
- request-level usage ledger 扩展
- 按模型 / 后端 / API Key / 日月年聚合
- API Key 列表、创建、编辑、禁用、删除
- 新建当次 key 的显示 / 隐藏 / 复制
- 管理台 Base URL 展示与复制
- readiness / usage / key usage 的管理视图

### 3.2 不包含

- 计费系统
- 配额系统
- 成本估算
- 导出中心
- 告警中心
- 多节点平台
- 历史 key 明文恢复

## 4. 方案选择

本次采用“共享核心先行”方案。

### 4.1 备选方案

- 方案 A：共享核心先行
- 方案 B：接口补丁优先
- 方案 C：事件账本优先

### 4.2 选择理由

本次不是只补一个页面或一个端点，而是要把：

- readiness 语义
- usage 口径
- 管理台交互

一次性对齐。

如果走接口补丁优先，最容易出现：

- UI 显示 ready，但网关仍在 warmup
- Key 页面有用量，统计页口径却不同
- 后端日志和管理台状态名称不一致

如果走事件账本优先，第一版又会被基础设施复杂度拖慢。

因此第一版应先定义共享正式对象，再拆实施计划。

## 5. 正式对象模型

本设计定义 4 个正式对象：

1. `ReadinessState`
2. `UsageLedger`
3. `ApiKeyRegistry`
4. `AdminViewModel`

### 5.1 ReadinessState

目标是把“进程活着 / HTTP 通了 / 可稳定推理”明确拆开。

#### 正式状态

- `stopped`
  - 后端未运行
- `starting`
  - 已拉起，但 HTTP 还不可用
- `warming_up`
  - `/v1/models` 或健康检查已通，但推理探针未通过
- `ready`
  - 推理探针通过，流式首包稳定
- `degraded`
  - 曾经 ready，但近期探针或真实请求出现可恢复异常
- `error`
  - 后端不可用，且不属于可重试热身窗口

#### 对外布尔语义

- `http_ready`
- `inference_ready`

#### 设计原则

- `ready` 不再等于“HTTP 可达”
- `http_ready=true` 且 `inference_ready=false` 是正式允许存在的中间态
- 启动窗口期优先建模为 `warming_up`，而不是普通失败

#### 事件建议

- `backend_starting`
- `backend_http_ready`
- `backend_warming_up`
- `backend_ready`
- `stream_not_ready`
- `backend_recovered`
- `backend_error`

### 5.2 UsageLedger

目标是把当前基础 `request_metrics` 提升成正式账本。

#### 每条请求至少记录

- `request_id`
- `started_at`
- `finished_at`
- `protocol`
- `model_name`
- `backend_type`
- `api_key_id`
- `status`
- `latency_ms`
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `cache_creation_tokens`
- `cache_read_tokens`
- `cache_miss_tokens`
- `tokens_per_second`

#### 字段原则

- 后端返回了就原样落库
- 后端没返回就记 `null`
- 不把未知伪装成 `0`

#### 第一版聚合维度

- 按 `model_name`
- 按 `backend_type`
- 按 `api_key_id`
- 按 `day / month / year`

### 5.3 ApiKeyRegistry

目标是把“能创建 key”升级成“可长期管理的正式对象”。

#### 每个 key 的正式字段

- `id`
- `name`
- `masked_key`
- `status`
- `created_at`
- `last_used_at`
- `disabled_at`
- `note`
- `rpm_limit`
- `concurrency_limit`

#### 安全边界

- 明文 key 只在创建当次返回
- 列表默认只返回 `masked_key`
- 不新增服务端可逆明文读取能力
- 历史 key 不支持重新揭示明文
- “显示 / 隐藏”只针对新建当次在前端本地会话中的明文

### 5.4 AdminViewModel

目标是让前端拿到正式视图，不自己发明业务语义。

#### 第一版提供的视图

- `readiness summary`
- `usage summary + trend + breakdown`
- `api key list + key usage summary`

#### 视图层还负责统一下发

- `local_base_url = http://127.0.0.1:4000`
- `lan_base_url = http://10.18.90.100:4000`

## 6. 组件边界

### 6.1 node-agent

`node-agent` 负责“后端是否真的可用”。

它负责：

- 启停后端容器
- 轮询基础 HTTP 健康
- 执行极小推理探针
- 维护 `ReadinessState`
- 产出 readiness 相关事件

它不负责：

- 直接给用户返回 `503`
- 统计 API Key 维度用量
- 决定管理台如何展示

### 6.2 gateway-api

`gateway-api` 负责“对外语义、鉴权、记账入口”。

它负责：

- 根据 agent 暴露的 readiness 结果决定是否放行
- `inference_ready=false` 时返回 `503 + Retry-After + detail`
- 抽取响应里的 usage / cache 字段
- 写入 `UsageLedger`
- 更新 `api_keys.last_used_at`

它不负责：

- 自己定义另一套 readiness
- 自己做复杂报表聚合
- 保存可逆明文 key

### 6.3 SQLite

第一版继续沿用 SQLite，不引入新存储。

它承担两层职责：

- 明细层：请求账本、key 对象、状态事件
- 视图层：管理台直接消费的聚合查询

### 6.4 web-console

`web-console` 只负责展示与交互。

它负责：

- readiness 卡片与事件展示
- usage 趋势、分组与筛选
- key 的创建、编辑、禁用、删除
- 新建当次 key 的显示 / 隐藏 / 复制
- Base URL 展示与复制

它不负责：

- 自己推断 ready
- 自己二次计算 token 统计
- 自己发明 Base URL 规则

## 7. 请求流转

### 7.1 启动与热身链路

1. `python -m llmnode.control start` 拉起 `node-agent` 和后端
2. `node-agent` 轮询后端 HTTP 健康
3. HTTP 可达后进入 `warming_up`
4. `node-agent` 发极小推理探针
5. 探针通过后状态升到 `ready`
6. 所有状态变化写入事件

### 7.2 业务请求链路

1. 客户端请求进入 `gateway-api`
2. 网关完成鉴权并定位 `api_key_id`
3. 网关读取当前 readiness
4. 若 `inference_ready=false`，直接返回 `503 + Retry-After + detail`
5. 若可放行，请求转发到后端
6. 响应返回后抽取 usage / cache 字段
7. 网关写入 `UsageLedger`
8. 网关刷新 `last_used_at`

### 7.3 管理台查询链路

1. 前端请求管理视图接口
2. 后端从 SQLite 聚合查询读取 summary / trend / breakdown
3. 返回 readiness / usage / key list 视图
4. 前端只做筛选和展示，不重算业务语义

## 8. 接口设计草案

### 8.1 Agent 诊断接口

保留现有：

- `GET /admin/diagnostics/status`
- `GET /admin/diagnostics/metrics`

其中 `GET /admin/diagnostics/status` 需要扩展字段：

- `readiness_state`
- `http_ready`
- `inference_ready`
- `retry_after_seconds`
- `last_transition_at`
- `last_probe_error`
- `last_probe_latency_ms`

`GET /admin/diagnostics/metrics` 继续负责暴露聚合结果，不承担 readiness 推导职责。

第一版不新增单独的“warming 状态页”。

### 8.2 对外推理接口语义

保留现有正式对外路径：

- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/messages`

当 `inference_ready=false` 时：

- 返回 `503 Service Unavailable`
- 返回 `Retry-After`
- JSON `detail` 使用固定可识别值：
  - `backend_warming_up`
  - `backend_not_stream_ready`

热身窗口期不再继续统一表现为普通 `500`。

### 8.3 管理视图接口

第一版建议提供：

- `GET /admin/overview/readiness`
- `GET /admin/overview/usage`
- `GET /admin/api-keys`
- `POST /admin/api-keys`
- `PATCH /admin/api-keys/{id}`
- `DELETE /admin/api-keys/{id}`
- `GET /admin/api-keys/{id}/usage`

说明：

- `api-keys` 这一组路径当前已有雏形，第一版应扩返回，不重做路径
- Base URL 应由 overview 视图统一下发，不在前端硬编码推断

### 8.4 API Key 返回模型

当前 `_sanitize_api_key_row()` 只返回元信息。

第一版应返回：

- `id`
- `name`
- `masked_key`
- `status`
- `scopes`
- `rpm_limit`
- `concurrency_limit`
- `created_at`
- `disabled_at`
- `last_used_at`
- `note`

创建 key 时仅在当次响应中额外返回：

- `secret`
- `masked_key`

列表接口永远不返回历史 key 明文。

## 9. 存储设计草案

### 9.1 request_metrics 扩字段

优先扩现有 `request_metrics`，不新起平行表：

- `backend_type TEXT`
- `api_key_id INTEGER`
- `cache_creation_tokens INTEGER`
- `cache_read_tokens INTEGER`
- `cache_miss_tokens INTEGER`
- `error_code TEXT`
- `status_detail TEXT`

这样现有 `_record_request_metric()` 可以沿用，只是补充写入字段。

### 9.2 agent_events 扩字段

当前 `status + reason` 太粗，不足以区分 warming、stream recovery 等事件。

建议扩：

- `event_type TEXT`
- `readiness_state TEXT`
- `http_ready INTEGER`
- `inference_ready INTEGER`
- `metadata_json TEXT`

### 9.3 api_keys 不增加明文字段

第一版不在 `api_keys` 表里加入可逆明文。

如果需要支持“创建后短时显示”，只保留在前端内存或当前会话，不落库。

## 10. 聚合查询设计

第一版不只返回一个总汇总，而是至少支持 4 类聚合：

1. 总览汇总
   - 请求数
   - 成功率
   - 平均延迟
   - P95 / P99
   - tokens/s
2. 时间趋势
   - 按 `day / month / year`
3. 维度分组
   - 按 `model_name / backend_type / api_key_id`
4. 单 key 用量
   - 给 key 列表页和 key 详情侧边栏使用

现有 `aggregate_request_metrics()` 可以保留为兼容入口，但内部需要升级为：

- 支持时间窗口
- 支持 group-by 维度
- 支持 cache token 聚合字段

第一版不引入 materialized view，也不引入额外 OLAP 组件。

## 11. 风险与兼容性

### 11.1 兼容性原则

- 不改对外推理协议路径
- 重点改正错误语义与管理视图完整性
- SQLite 采用增量迁移，只加列，不做破坏性重建
- 历史缺失字段保持 `null`

### 11.2 主要风险

#### 探针过严

如果推理探针太重，后端会长期停留在 `warming_up`。

规避方式：

- 探针必须极小
- 低 token
- 固定模型
- 固定超时

#### 探针过松

如果只验证一次非流式，仍可能放过首个流式请求断开的窗口。

规避方式：

- readiness 既参考探针，也参考真实请求中的可恢复异常
- 允许进入 `degraded`

#### usage 字段不一致

不同后端返回 usage / cache 字段可能不完全一致。

规避方式：

- 字段允许 `null`
- 契约明确“未知不是 0”

#### 管理台口径漂移

如果前端自己重算统计，会出现列表与趋势不一致。

规避方式：

- 所有统计以后端聚合接口为准

#### key 安全倒退

如果为了显示密钥引入明文回读，会破坏当前哈希存储边界。

规避方式：

- 只允许新建当次显示
- 历史 key 永不回显明文

## 12. 非目标

第一版明确不做：

- 计费系统
- 配额系统
- 成本估算
- CSV / Excel 导出中心
- 告警中心
- 多节点平台
- 历史 key 明文恢复

## 13. 验收口径

### 13.1 P0 readiness

- 后端处于热身窗口时，Claude Code 类流式请求收到 `503`
- 响应包含 `Retry-After`
- `detail` 为固定可识别值，不再是模糊 `500`
- agent 状态能区分 `http_ready=true` 但 `inference_ready=false`
- 事件或日志里能直接看到：
  - `warming_up`
  - `stream_not_ready`
  - `backend_recovered`

### 13.2 P1 usage ledger

- 请求账本可记录 `model / backend / api_key / 时间`
- 能返回输入、输出、缓存命中、缓存未命中 token
- 缺失字段明确为 `null`
- 管理台可按 `日 / 月 / 年` 看趋势
- 可按 `model / backend / api_key` 看分组用量

### 13.3 P1 API Key 管理台

- Key 创建后能持续保存在库中
- 列表能显示：
  - 名称
  - 脱敏 key
  - 状态
  - 创建时间
  - 最后使用时间
  - 关联用量
- 支持新建当次显示 / 隐藏 / 复制明文
- 支持历史 key 的脱敏展示
- 支持复制 Base URL
- 支持创建、编辑、禁用、删除

### 13.4 整体体验

- 管理台不需要读日志就能看 readiness 和 usage
- 前端各页面统计口径一致
- 不引入可逆明文 key 存储

## 14. 建议实施顺序

1. 先做 `readiness hardening`
2. 再做 `usage ledger + aggregation`
3. 最后做 `api key console + admin view model`
4. 收尾统一做文档回流与管理台口径对齐

## 15. 文档回流要求

设计落地后，至少要检查是否同步更新：

- `docs/blueprint/current.md`
- `docs/blueprint/history.md`
- `docs/contracts/control-plane.md`
- `docs/contracts/backend-routing.md`
- `docs/process/run.md`
- `docs/process/deployment.md`

另外必须显式处理一个文档纠偏点：

- 如果配置真相已经切到 `27B-FP8`
- 那么仍写 `35B-A3B-FP8` 为默认路径的文档必须在实施中被显式回流修正
