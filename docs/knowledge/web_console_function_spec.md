# Web Console 功能与需求全量说明

## 1. 文档目的

本文档用于完整说明当前 `web-console` 的实际功能、页面结构、数据来源、交互规则、运行要求、限制项与新前端重设计时必须保留的能力。

目标不是复述当前 UI 的视觉样式，而是把现有控制台的“产品能力”和“接口契约”讲清楚，方便后续采用另一套信息架构、交互布局或视觉体系重新设计前端。

本文档基于当前仓库实现整理，主要依据如下：

- `web-console/src/router/index.ts`
- `web-console/src/layouts/ConsoleLayout.vue`
- `web-console/src/stores/overview.ts`
- `web-console/src/views/*.vue`
- `web-console/src/types.ts`
- `llmnode/api/app.py`
- `config/defaults.yaml`
- `README.md`

## 2. 产品定位

`web-console` 是 `llmnode` 的本机管理控制台，定位是单机 LLM 网关的控制面板，不是面向普通终端用户的聊天界面。

它当前服务的核心对象是：

- 本机运维者
- 网关管理员
- 模型路由维护者
- API Key 管理者
- 排障与状态观察者

当前版本边界非常明确：

- V2 管理台已具备控制面能力
- 运行后端当前仍固定为 `vLLM`
- 管理台不是“多后端切换器”
- 管理台主要负责状态观察、配置维护、Key 管理、日志审计、调度修改、后端控制入口

## 3. 技术与运行前提

### 3.1 前端技术栈

- 框架：Vue 3
- 路由：Vue Router 4
- 状态管理：Pinia
- UI 组件：Element Plus
- 图表：ECharts
- 构建工具：Vite

### 3.2 默认运行地址

- `web-console` 开发服务默认端口：`5173`
- `gateway-api` 默认端口：`4000`
- `node-agent` 默认端口：`4010`

### 3.3 Vite 代理要求

前端开发环境通过 Vite 代理访问后端：

- `/admin` -> `http://127.0.0.1:4000`
- `/v1` -> `http://127.0.0.1:4000`

这意味着新前端至少需要支持两种接入方式：

1. 同源模式：直接请求当前域名下的 `/admin/*`、`/v1/*`
2. 指定 API Base 模式：手动指定后端基础地址

### 3.4 启动方式

当前推荐通过统一控制脚本启动：

```bash
bash scripts/control.sh start
```

启动后默认包括：

- `node-agent`
- `vLLM` 容器
- `gateway-api`
- `web-console`

## 4. 整体信息架构

当前控制台采用“单布局 + 6 个一级页面”的结构。

一级页面如下：

1. 仪表盘 `overview`
2. 使用记录 `usage`
3. API 密钥 `keys`
4. 模型路由 `models`
5. 调度设置 `schedule`
6. 系统状态 `status`

这 6 个页面已经构成当前产品的最小完整控制面范围。新前端可以重做导航形式，但不应随意删除这 6 类能力。

## 5. 全局布局与公共行为

### 5.1 公共布局结构

当前全局布局由 [ConsoleLayout.vue](/proj02/liuheshan/llmnode/web-console/src/layouts/ConsoleLayout.vue) 提供，分为两栏：

- 左侧固定导航栏
- 右侧工作区

右侧工作区又分为：

- 顶部页面标题区
- 全局状态提示区
- 页面主体内容区

### 5.2 全局导航内容

导航栏当前包含：

- 仪表盘
- 使用记录
- API 密钥
- 模型路由
- 调度设置
- 系统状态

每个导航项除了名称还有一条简短说明，说明当前页承担的职责。

### 5.3 全局顶栏信息

顶栏当前显示：

- 页面标题
- 页面副标题
- 后端状态标签
- 当前队列长度
- 当前日志条数
- 固定头像占位

其中头像当前没有实际业务含义，只是视觉占位，不属于必须保留功能。

### 5.4 全局初始化行为

页面首次挂载时会自动执行：

1. 请求 `/admin/status` 获取快照
2. 连接 `/admin/stream?interval=2` 获取实时快照流

这两个动作在新前端中也建议保留：

- 快照用于首屏稳定渲染
- SSE 用于实时刷新

### 5.5 全局异常提示

当以下任一值存在时，布局顶部会显示异常提示卡：

- `store.error`
- `snapshot.backend_error`

这说明新前端必须提供全局级错误曝光区，而不是把错误只埋在局部页面里。

### 5.6 SSE 连接状态

当前左下角和部分页面会显式展示 SSE 是否连接成功：

- `SSE 已连接`
- `SSE 未连接`

因此实时连接状态属于显式功能，不应隐藏。

## 6. 全局数据模型

控制台的核心数据来自 `AdminSnapshot`。

### 6.1 `AdminSnapshot` 结构

主要字段如下：

- `backend_type`：后端类型，当前实际为 `vllm`
- `backend_ready`：后端是否健康可用
- `backend_error`：后端探活错误文本
- `backend_container`：后端容器快照
- `agent_state`：节点代理状态
- `require_agent_ready`：请求是否强依赖 agent ready
- `queue_length`：当前等待队列长度
- `models`：逻辑模型列表
- `logs`：最近请求日志
- `events`：最近节点事件
- `runtime`：运行时配置快照

### 6.2 `runtime` 子结构

`runtime` 进一步包含：

- `gateway`
- `agent`
- `schedule`
- `vllm`
- `model_routes`

这意味着当前控制台本质上同时承载两类信息：

1. 实时状态信息
2. 运行配置镜像

新前端建议把这两类信息在界面层明确区分，避免“状态”和“配置”混在一起不好理解。

### 6.3 本地持久化项

前端当前将两个字段持久化到浏览器本地存储：

- `vllm-console-api-base`
- `vllm-console-api-key`

这两个设置影响所有管理接口请求。

因此新前端必须支持：

- 管理 API Base 可配置
- 管理 API Key 可配置
- 刷新后可恢复

## 7. 鉴权与访问要求

### 7.1 管理接口鉴权

所有 `/admin/*` 接口都要求 `admin` scope。

当前前端默认通过请求头发送：

```http
Authorization: Bearer <apiKey>
```

### 7.2 默认管理 Key

当前默认值是：

- `dev-key`

这是 bootstrap 管理员 key，对应 `config/defaults.yaml` 中的 `gateway.api_key`。

### 7.3 两类 Key 的概念区分

系统当前存在两类 key：

1. bootstrap 管理员 key
2. 数据库 API key

区别如下：

- bootstrap key 长期存在，默认用于初始管理
- 数据库 key 由管理台创建
- 数据库中仅保存 `key_hash`
- 新建数据库 key 的明文 secret 只返回一次

新前端设计必须把这两类 key 的角色区分清楚，避免用户误以为“页面展示的所有 key 就是全部访问凭证”。

## 8. 数据刷新与实时机制

### 8.1 快照请求

接口：

- `GET /admin/status`

用途：

- 首屏加载
- 手动刷新后重新拉取
- 修改配置后同步最新状态

### 8.2 SSE 实时流

接口：

- `GET /admin/stream?interval=2`

用途：

- 每隔固定时间推送最新 `snapshot`
- 当前前端只消费 `event = snapshot`

### 8.3 当前实现方式

当前不是浏览器 `EventSource`，而是：

- `fetch`
- 读取 `ReadableStream`
- 手动解析 SSE chunk

这意味着新前端实现可以继续沿用当前方式，也可以改为原生 `EventSource` 或更稳健的流式封装，但必须满足以下要求：

- 能持续接收 snapshot 事件
- 能处理中途断流
- 能显式显示连接状态
- 能手动重连

### 8.4 当前历史趋势缓存策略

前端会把最近快照转换成时间点历史数据，仅保留最近 `48` 个点。

记录字段：

- `queueLength`
- `failureCount`

这不是后端历史接口，而是前端内存级短时趋势缓存。新前端如果需要更丰富图表，可以扩展，但至少应保留这种轻量级短周期运行趋势观察能力。

## 9. 页面一：仪表盘

文件：

- [OverviewView.vue](/proj02/liuheshan/llmnode/web-console/src/views/OverviewView.vue)

### 9.1 页面目标

仪表盘负责提供“进入控制台后的第一屏总览”，核心是快速判断系统是否健康、是否有异常、最近流量如何、最近发生了什么。

### 9.2 当前功能组成

仪表盘包含以下模块：

1. KPI 卡片
2. 工具栏卡片
3. 模型分布图
4. 队列与失败趋势图
5. 最近请求列表
6. 快捷操作入口说明
7. 最近节点事件
8. 异常请求聚合

### 9.3 KPI 卡片

当前显示 4 个关键指标：

- 后端状态
- 总请求数
- 模型数
- 队列长度

对应含义：

- 后端状态：`backend_ready` 的结果
- 总请求数：当前快照里 `logs.length`
- 模型数：当前逻辑模型数量
- 队列长度：当前等待请求数量

### 9.4 工具栏卡片

当前工具栏表面上显示两个下拉：

- 近 7 天 / 今日
- 按天 / 按小时

注意：这两个下拉当前只是静态占位，没有实际筛选逻辑。

这在新前端设计中必须明确处理：

- 要么删除这类伪交互
- 要么真正补齐统计时间维度能力

不建议继续保留“看起来能用但实际无效”的交互。

### 9.5 状态标签与最后更新时间

工具栏右侧展示：

- `agent_state.status`
- `lastUpdated`

新前端建议保留：

- 快照最后刷新时间
- agent 状态显式展示

### 9.6 模型分布图

图表用途：

- 按逻辑模型统计当前日志样本中的请求数量分布

实现特点：

- 基于 `snapshot.logs`
- 前端本地聚合
- 使用饼图
- 没有时间范围接口

因此它代表的是“当前拉到的最近日志样本分布”，不是长期统计报表。

### 9.7 队列与失败趋势图

图表用途：

- 观察最近一段时间的队列长度变化
- 间接观察 agent 失败累计值

实现特点：

- 数据来自前端内存中的快照历史
- 并非后端时序数据库

当前页面只绘制了 `queueLength` 字段，虽然历史点中也存了 `failureCount`。
如果新前端希望提升信息密度，可以考虑：

- 双曲线展示
- 标签切换
- 队列/失败计数分离展示

### 9.8 最近请求列表

显示最近 8 条请求，字段包括：

- `model_name`
- `protocol`
- `created_at`
- `status`
- `request_id`
- 若存在则展示 `rejection_reason`

它的作用是让管理员第一眼看到最近的流量类型与异常情况。

### 9.9 快捷操作区

当前仅作为说明卡片，展示可进入的管理能力：

- API 密钥
- 模型路由
- 调度
- 系统状态

注意：当前不是可点击的功能入口卡，而只是静态说明块。

如果新前端准备重构，建议把它升级为真正的快捷入口。

### 9.10 最近节点事件

显示最近 6 条 `events`：

- `status`
- `reason`
- `created_at`

这部分用于观察 agent 状态迁移，例如：

- ready
- recovering
- stopped

### 9.11 异常请求聚合

从最近日志中筛出 `status != ok` 的记录，最多取 5 条。

优先展示：

- `rejection_reason`
- 否则展示 `error_message`
- 再否则展示 `request_id`

该模块的价值在于快速看到最值得关注的问题，而不用先进完整日志页。

## 10. 页面二：使用记录

文件：

- [UsageRecordsView.vue](/proj02/liuheshan/llmnode/web-console/src/views/UsageRecordsView.vue)

### 10.1 页面目标

该页面用于请求审计与问题定位，负责展示最近请求日志，并提供筛选、搜索、刷新和重连能力。

### 10.2 当前数据来源

当前页面并没有单独调用 `/admin/request-logs`，而是直接复用 `snapshot.logs`。

这带来一个重要现实约束：

- 当前日志页展示的是 `/admin/status` 返回的最近日志样本
- 不是完整分页日志系统
- 样本数量当前后端默认限制为最近 20 条

因此如果新前端打算把日志页做成“正式审计台”，需要新增后端分页、时间范围和更多过滤支持。

### 10.3 页面顶部 KPI

当前显示：

- 总请求数
- 异常请求数
- 拒绝请求数
- 后台类型
- SSE 状态

### 10.4 管理连接配置区

该页面提供两个全局输入框：

- 管理员 API Key
- API Base

并提供两个动作：

- 刷新
- 重连 SSE

说明如下：

- 刷新：重新请求快照
- 重连 SSE：先刷新，再重新连接流

这块本质上是“管理接口连接设置面板”，并不只是日志页自身功能。

新前端重构时可以考虑把它上移为全局设置抽屉、顶部连接面板或首次接入向导，但功能不能丢。

### 10.5 筛选功能

当前支持以下筛选：

- 状态筛选：`all / ok / rejected / timeout / streaming`
- 协议筛选：`all / openai / anthropic`
- 拒绝原因筛选：`all / rpm_limit_exceeded / concurrency_limit_exceeded / queue_full / queue_timeout`
- 关键字搜索

### 10.6 关键字搜索字段

搜索会匹配以下字段：

- `request_id`
- `model_name`
- `error_message`
- `client_ip`
- `user_agent`
- `rejection_reason`

### 10.7 表格字段

当前表格列包括：

- 时间 `created_at`
- Request ID
- 协议 `protocol`
- 模型 `model_name`
- 状态 `status`
- 来源
- 拒绝原因
- 错误
- 客户端

### 10.8 来源列逻辑

来源列由 `auth_source` 转换得到：

- `bootstrap` -> `bootstrap`
- `db` -> `db key`
- 其他 -> `unknown`

同时展示：

- `api_key_id`

这对于追踪某个数据库 key 发起的请求很重要，因此新前端要保留“认证来源 + key id”的组合信息。

### 10.9 客户端列内容

客户端列展示：

- `client_ip`
- `user_agent`

这对定位来源设备、脚本或 SDK 很有帮助。

### 10.10 设计约束

由于当前后端没有真正分页与高级检索，前端所有筛选都是对当前样本做本地过滤。

因此新前端文案上要避免误导，不能让用户误以为自己在搜索全量历史。

## 11. 页面三：API 密钥

文件：

- [ApiKeysView.vue](/proj02/liuheshan/llmnode/web-console/src/views/ApiKeysView.vue)

### 11.1 页面目标

该页面负责数据库 API Key 的完整生命周期管理，包括：

- 创建
- 查看
- 过滤
- 排序
- 编辑
- 启用/禁用
- 删除
- 查看最近一次返回的 secret

### 11.2 当前数据来源

主要接口：

- `GET /admin/keys`
- `POST /admin/keys`
- `PATCH /admin/keys/{id}`
- `DELETE /admin/keys/{id}`

### 11.3 顶部 KPI

当前显示：

- 数据库 Key 数
- 活跃 Key 数
- 推理 Scope Key 数
- 管理 Scope Key 数

注意：

- 这里不包含 bootstrap 管理员 key

### 11.4 创建新 Key

创建表单当前字段如下：

- `name`
- `scopes`
- `rpm_limit`
- `concurrency_limit`
- `note`

### 11.5 创建时校验规则

前后端共同体现出的规则：

- `name` 不能为空
- `scopes` 至少选择一个
- `scopes` 只允许 `admin`、`inference`
- `rpm_limit` 必须是正整数或 `null`
- `concurrency_limit` 必须是正整数或 `null`
- `note` 允许为空，空字符串会被归一化为 `null`

### 11.6 创建成功后的特殊行为

后端返回：

- `key`
- `secret`

其中 `secret` 明文只返回一次。

前端会把最近一次创建成功的信息展示在单独区域：

- key 名称
- 明文 secret
- 复制按钮
- 清空展示按钮

这是一个必须重点保留的功能，因为它直接影响用户能否拿到新 key 的真实凭据。

### 11.7 Secret 区域要求

新前端中，最近创建 secret 的展示区至少应满足：

- 明确提示“只显示一次”
- 提供复制功能
- 提供关闭/清空功能
- 避免用户刷新后误以为还可再次查看

### 11.8 Key 列表筛选

当前支持：

- 按状态筛选：`all / active / disabled`
- 按 scope 筛选：`all / admin / inference`
- 关键字搜索：名称或备注
- 排序字段：
  - 创建时间
  - 状态
  - RPM
  - 并发
- 排序方向：升序 / 降序

### 11.9 列表展示字段

当前表格列包括：

- 名称
- 状态
- Scopes
- RPM
- 并发
- 创建时间
- 备注
- 操作

### 11.10 行内编辑

当前支持对单条 Key 进行行内编辑，字段包括：

- `name`
- `scopes`
- `rpm_limit`
- `concurrency_limit`
- `note`

行内编辑状态下支持：

- 保存
- 取消

### 11.11 启用/禁用

当前通过切换 `status` 完成：

- `active`
- `disabled`

前端会根据当前状态给出对应按钮文案：

- 若当前为 `active`，按钮显示“禁用”
- 若当前为 `disabled`，按钮显示“启用”

### 11.12 删除

删除接口为真实删除，不是软删除按钮文案。

当前前端没有二次确认弹窗。

这意味着新前端在可用性上建议增加：

- 删除确认
- 风险提示

但业务能力仍然应保持为“可删除数据库 key”。

### 11.13 运行时意义

Key 管理页不只是 CRUD 页面，它直接影响运行时准入控制。当前 README 和实现共同表明数据库 key 已接入：

- scope 校验
- 单 key RPM 限流
- 单 key 活跃请求并发限制

因此新前端应明确表达这些字段的业务含义，而不是仅仅当做表单项。

## 12. 页面四：模型路由

文件：

- [ModelRoutesView.vue](/proj02/liuheshan/llmnode/web-console/src/views/ModelRoutesView.vue)

### 12.1 页面目标

该页面用于维护“逻辑模型名 -> 后端模型配置”的映射关系。

### 12.2 当前产品边界

虽然页面叫模型路由，但当前 V2 有明确限制：

- 只支持 `vllm`
- 不支持在前端切换多后端类型

后端接口也强制：

- `backend_type != vllm` 时直接报错

### 12.3 页面顶部信息

当前显示：

- 后端类型
- 模型目录/模型名
- 显存占用策略 `gpu_memory_utilization`
- 上下文长度 `max_model_len`

这些信息主要来自 `runtime.vllm`。

### 12.4 表格字段

当前模型列表字段包括：

- 逻辑模型 `name`
- 展示名称 `display_name`
- 后端模型 `backend_model`
- 后端类型 `backend_type`
- 是否启用 `enabled`
- 保存操作

### 12.5 可编辑字段

当前允许编辑：

- `display_name`
- `backend_model`
- `enabled`

### 12.6 保存行为

点击保存后调用：

- `PATCH /admin/models/{name}`

并在保存成功后刷新快照。

### 12.7 数据来源说明

页面展示的模型行来自：

- `snapshot.runtime.model_routes`

不是通过单独的 `/admin/models` 拉取。

### 12.8 新前端设计要求

新前端需要明确区分三层概念：

1. 逻辑模型名
2. 对外展示名
3. 后端实际模型名

否则用户容易误以为三者是同一个字段。

### 12.9 当前限制项

当前页面虽然存在“后端类型”字段，但业务上只是展示，不是真正的可选路由后端。

因此新前端不应误导出“多推理框架可切换”的感知，除非后端先升级到 V3。

## 13. 页面五：调度设置

文件：

- [ScheduleView.vue](/proj02/liuheshan/llmnode/web-console/src/views/ScheduleView.vue)

### 13.1 页面目标

该页面用于维护运行时工作日、工作时间窗口、自动启停和恢复相关的计划参数。

### 13.2 当前数据来源

主要来自：

- `snapshot.runtime.schedule`
- `snapshot.runtime.gateway`
- `snapshot.runtime.agent`

保存接口：

- `PATCH /admin/schedule`

### 13.3 顶部 KPI

当前展示：

- 时区
- 工作窗口
- 自动启停状态
- 冷却分钟数

### 13.4 说明区

页面中还有两块说明/配置摘要：

1. 调度策略摘要
2. V2 当前行为说明

其中 “V2 当前行为” 说明了一个重要边界：

- 目前仍以应用内调度为准
- 若未来迁移到 `systemd timer`，这里的配置仍应沿用

这意味着新前端设计时，调度页应更偏向“逻辑调度配置中心”，而不是与某种底层调度实现强绑定。

### 13.5 可编辑字段

当前支持编辑：

- `timezone`
- `work_days`
- `start_time`
- `end_time`
- `auto_stop_enabled`
- `auto_start_enabled`
- `cooldown_minutes`

### 13.6 工作日选项

当前固定支持：

- `mon`
- `tue`
- `wed`
- `thu`
- `fri`
- `sat`
- `sun`

### 13.7 保存行为

点击“保存调度”后，当前前端直接提交上述字段，不做复杂校验。

后端当前也仅做类型转换，没有严格时间格式校验、工作日取值校验或开始结束时间关系校验。

这意味着新前端如果希望提升质量，建议补充前端校验，但不能改掉字段语义本身。

### 13.8 与其他运行信息的关系

页面还展示：

- `gateway.backend_url`
- `gateway.queue_limit`
- `agent.host:port`
- `agent.poll_interval`
- `agent.auto_recover`
- `agent.recovery_threshold`

这些内容虽然不在本页编辑，但与调度和恢复策略紧密相关，因此建议在新前端中继续保留为上下文信息。

## 14. 页面六：系统状态

文件：

- [SystemStatusView.vue](/proj02/liuheshan/llmnode/web-console/src/views/SystemStatusView.vue)

### 14.1 页面目标

该页面用于集中展示节点代理状态、后端容器状态、运行参数摘要和恢复事件，并提供“重启后端”操作入口。

### 14.2 顶部 KPI

当前显示：

- 节点状态
- 后端就绪
- 容器状态
- 调度开关
- 队列深度

### 14.3 运行配置摘要

页面摘要展示：

- Gateway 后端 URL 与队列限制
- Agent 地址与轮询间隔
- VLLM 模型名与端口

### 14.4 恢复参数摘要

页面还展示：

- Auto Recover
- Auto Start
- Auto Stop
- 恢复阈值
- 工作时间窗口
- 时区

### 14.5 后端重启功能

这是系统状态页最核心的控制动作之一。

接口：

- `POST /admin/services/restart`

用途：

- 通过 agent 发起后端重启

返回结构包括：

- `accepted`
- `service`
- `action`
- `agent_status`

### 14.6 重启交互要求

当前前端行为：

- 点击后进入 loading
- 出错时在页面内显示 `restartError`
- 成功后重新请求快照

新前端至少应保留：

- 显式按钮
- 重启中状态
- 成功后刷新
- 失败可见错误反馈

### 14.7 后端容器状态

`backend_container` 当前可能包含：

- `exists`
- `running`
- `status`
- `name`
- `image`

但要注意：

- 该字段不是永远都有
- 只有当应用状态里挂载了容器驱动时才可能有值

因此新前端需要把它当成“可选增强信息”，而不是必然存在的数据。

### 14.8 事件时间线

页面底部按时间线方式展示 `events`：

- `status`
- `reason`
- `created_at`

这部分是观察 agent 恢复链路的核心证据之一，建议新前端继续保留“时间线”或“事件流”表达方式。

## 15. 后端管理接口清单

以下接口构成当前控制台的核心管理能力。

### 15.1 快照与实时

- `GET /admin/status`
- `GET /admin/stream`

### 15.2 日志与事件

- `GET /admin/request-logs`
- `GET /admin/logs`
- `GET /admin/events`

说明：

- `/admin/logs` 当前只是 `/admin/request-logs` 的别名

### 15.3 API Key

- `GET /admin/keys`
- `POST /admin/keys`
- `PATCH /admin/keys/{key_id}`
- `DELETE /admin/keys/{key_id}`

### 15.4 模型路由

- `GET /admin/models`
- `PATCH /admin/models/{name}`

### 15.5 调度

- `GET /admin/schedule`
- `PATCH /admin/schedule`

### 15.6 服务控制

- `POST /admin/services/restart`

## 16. 当前已实现能力与当前未实现能力

为了让重做前端时不误判范围，这里明确区分。

### 16.1 当前已实现能力

- 首屏状态快照加载
- SSE 周期性实时更新
- 全局异常提示
- 请求日志最近样本展示
- 本地筛选与搜索
- 数据库 API Key 全生命周期管理
- Key secret 一次性展示
- 逻辑模型路由编辑
- 调度参数编辑
- 后端重启操作
- 节点事件展示
- 后端容器状态展示（条件可用）

### 16.2 当前仅部分实现或弱实现

- 日志页是样本级，不是全量审计系统
- 趋势图是前端内存级，不是长期监控
- 调度编辑缺少严格表单校验
- 删除 Key 缺少二次确认
- 页面存在静态说明卡，不是真正可操作入口

### 16.3 当前明显属于占位/伪交互

- 仪表盘上的“近 7 天 / 今日”
- 仪表盘上的“按天 / 按小时”
- 仪表盘快捷操作卡只是静态块
- 顶栏头像无业务作用

如果要重做前端，建议不要继承这些伪交互。

## 17. 新前端必须保留的产品能力

无论采用什么新布局，以下能力应视为必须保留：

1. 管理接口接入配置
2. 管理员 API Key 输入与持久化
3. 首屏系统健康总览
4. SSE 实时状态同步
5. 队列长度与 agent 状态可见
6. 最近请求日志可浏览、可筛选、可搜索
7. 数据库 API Key 的创建、编辑、启用/禁用、删除
8. 新建 Key 的 secret 一次性展示与复制
9. 逻辑模型路由维护
10. 调度配置编辑
11. 系统状态与节点事件查看
12. 后端重启入口
13. 全局错误可见性

## 18. 新前端建议增强但不属于硬性必须的能力

以下是基于当前短板给出的增强建议：

1. 把“连接设置”从日志页提到全局设置层
2. 给 Key 删除增加确认弹窗
3. 给调度表单增加前端校验
4. 给模型路由增加编辑前后差异提示
5. 给 SSE 加入自动重连策略和重试提示
6. 给日志页补充分页和时间范围能力
7. 给仪表盘真正做成可点击的快捷入口
8. 区分“实时状态视图”和“配置管理视图”
9. 提供更明显的只读/可编辑状态切换
10. 对 `backend_container` 缺失时给出更清晰说明

## 19. 新前端信息架构建议

如果你准备采用“别的格局”重做，建议保留能力但重组结构。一个更稳的方向是：

### 19.1 一级导航建议

- 总览
- 运行状态
- 请求审计
- API Key 管理
- 模型路由
- 调度策略
- 系统控制

其中“运行状态”和“系统控制”可以继续合并，也可以拆开。

### 19.2 全局层建议

建议增加一个固定的全局控制条，统一放：

- API Base
- 管理 API Key
- SSE 状态
- 最后更新时间
- 全局错误提示

### 19.3 状态与配置分离

当前实现中状态和配置混在同一页面比较多。新设计建议分清：

- 当前发生了什么
- 系统是如何被配置成这样的

这会显著提升理解成本表现。

## 20. 文案与交互语义要求

新前端设计时，应避免以下误导：

- 不要把最近 20 条日志说成“全量历史”
- 不要把 `backend_type` 做成像是可以自由切换的选项
- 不要把前端短期缓存趋势图说成长期监控统计
- 不要把 bootstrap key 和数据库 key 混为同一种资源
- 不要在没有真实功能时放置像可操作控件一样的占位元素

建议保留以下关键语义：

- “最近日志样本”
- “一次性 secret”
- “逻辑模型”
- “后端模型”
- “工作时间窗口”
- “自动恢复”
- “agent 状态”

## 21. 异常与边界情况

新前端需要考虑以下边界：

### 21.1 后端不可达

表现：

- `/admin/status` 请求失败
- `store.error` 有值

要求：

- 首屏给出明确错误
- 允许用户修改 API Base / Key 后重试

### 21.2 SSE 中断

表现：

- 流断开
- `streamConnected = false`

要求：

- 明确显示离线
- 可手动重连
- 最好支持自动重试

### 21.3 后端健康检查失败

表现：

- `backend_ready = false`
- `backend_error` 有值

要求：

- 在总览和系统状态页都能明显看到

### 21.4 容器状态缺失

表现：

- `backend_container = null`

要求：

- 页面可降级展示
- 不应因为缺少容器信息导致整个系统状态页失效

### 21.5 新建 key 后用户未及时复制 secret

表现：

- 刷新后 secret 消失

要求：

- 必须有醒目提示“只显示一次”

## 22. 与当前实现强绑定的事实

以下事实在重做前端时必须知道，否则很容易设计出和后端不匹配的界面：

1. 当前所有页面共享同一个 `overview store`
2. 大多数页面依赖 `snapshot` 而不是独立细分接口
3. 日志页当前不是分页日志系统
4. 模型路由当前只支持 `vllm`
5. 调度配置已经写入数据库并持久化
6. 后端重启是通过 agent 转发执行，不是前端本地动作
7. 控制台默认假设本机或内网受信环境，不是完整多用户 SaaS 控制台

## 23. 重设计时的优先级建议

如果要按投入产出比排序，建议优先保证：

1. 全局连接配置与错误反馈
2. 总览与系统状态
3. API Key 管理
4. 请求日志浏览
5. 模型路由与调度编辑
6. 图表美化与高级统计

理由是：

- 前 4 项是当前控制台最核心的日常使用路径
- 后两项更偏配置维护和信息增强

## 24. 结论

当前 `web-console` 已经不是单纯的展示页，而是一个可用的本地控制面原型。它的核心价值不在现有布局本身，而在这几条能力链已经被打通：

- 状态快照 + SSE 实时更新
- API Key 全生命周期管理
- 模型路由维护
- 调度配置维护
- 请求与事件审计
- 后端重启控制

如果要基于本文档重做一个全新前端，最重要的是：

- 保留这些已打通的控制面能力
- 明确当前后端的真实边界
- 删掉伪交互
- 区分“实时状态”“历史样本”“运行配置”“控制动作”

这样新的界面即使结构完全不同，也不会偏离当前系统真实能力。
