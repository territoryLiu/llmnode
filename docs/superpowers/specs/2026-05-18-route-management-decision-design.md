# Route 管理边界决策设计

## 0. 文档定位

本文只服务 [`docs/blueprint/roadmap.md`](../../blueprint/roadmap.md) 中 route 主线的任务 4-6：

- 决定 route 继续轻量运行态，还是升级成长期持久化管理
- 若进入平台路，明确新增 route、删除 route、seed 同步策略的正式边界

它不负责：

- 复述当前系统现状，那是 [`docs/blueprint/current.md`](../../blueprint/current.md)
- 定义当前已落地契约，那是 [`docs/contracts/backend-routing.md`](../../contracts/backend-routing.md)
- 直接充当实施清单，那应另写 `plan`

## 1. 背景与问题

当前仓库已经具备下面这些能力：

- `model_routes` SQLite 表已承载 route 运行态字段
- `/admin/models` 已支持编辑 route 关键字段
- route 已支持 `managed_local / external` 生命周期语义
- `/v1/responses`、`/v1/chat/completions`、`/v1/messages` 已支持 route-aware 分发

但当前系统对 route 的正式叙事仍混用了两套模型：

- 一套说法把 route 视为“当前激活 profile 派生出的运行态缓存”
- 另一套说法又把管理台编辑、外部上游 route 和长期字段存储当成“正式可管理对象”

这种混用会直接导致三个问题：

1. 启动 seed 仍会把 route 当成可整表重建的缓存，和长期编辑语义冲突
2. 新增 / 删除 route 没有正式产品语义，后续实现容易继续堆例外
3. `profile`、`catalog`、`model_routes`、管理台操作之间的真相边界不清楚

## 2. 决策结论

正式选型采用：

- 平台路，但分阶段推进

具体含义是：

- `model_routes` 从“配置派生出的临时运行态表”升级为“单机节点上的长期 route 注册表”
- `config/defaults.yaml + config/backends/*.yaml` 继续负责本地受控后端的默认供给
- 启动 seed 的职责从“覆盖现有 route 表”改成“同步默认本地供给并保留人工管理项”
- 任务 5、6 统一按长期 route 管理对象的方向展开，不再继续混用“只可编辑现有 route”与“完整模型管理中心”两套说法

不选轻量路的原因：

- 当前管理台已经不是纯观察界面，而是实际编辑 route 的治理入口
- external upstream route 已经是正式功能，不能再要求它伪装成 profile 派生物
- 如果继续停在轻量运行态，新增 / 删除 / 持久化冲突将长期没有正式语义

## 3. 设计目标

本设计要达成的目标只有这些：

1. 明确 `profile`、`catalog`、`model_routes`、管理面修改各自的责任边界
2. 把 route 的正式真相源收口到 `model_routes`
3. 把启动 seed 改成增量同步，而不是整表重建
4. 为新增 / 删除 route 定义可落地的正式语义
5. 在不引入多节点和复杂编排的前提下，完成单机平台路最小闭环

本设计明确不做：

- 多节点 route 管理
- K8s 编排
- managed_local 新实例注册与资源编排
- profile 文件反写
- 一步到位的大而全模型注册中心

## 4. 对象边界与状态来源

### 4.1 `profile`

来源：

- [`config/defaults.yaml`](../../../config/defaults.yaml)
- [`config/backends/*.yaml`](../../../config/backends)

职责：

- 声明当前激活的本地受控后端默认供给
- 提供 `backend_type / model_name / host_port / model_dir` 等默认参数

边界：

- `profile` 不是完整 route 注册表
- 不保存 external route
- 不保存用户手工新增的逻辑模型

### 4.2 `catalog`

来源：

- [`llmnode/models.py`](../../../llmnode/models.py) 中的 `load_model_catalog()`

职责：

- 把当前激活 profile 转成默认本地 route 候选项

边界：

- `catalog` 是启动时的供给输入，不是最终真相源
- 它不能代表系统内全部 route 的全集

### 4.3 `model_routes`

来源：

- [`llmnode/storage/db.py`](../../../llmnode/storage/db.py) 中的 `model_routes` 表

职责：

- 作为正式 route 注册表
- 保存当前节点可管理、可暴露、可路由的逻辑模型对象

边界：

- 这里才是网关、管理台、存储层共享的正式 route 真相

### 4.4 管理面修改

来源：

- [`/admin/models`](../../../llmnode/api/app.py)

职责：

- 对 `model_routes` 做增删改
- 不直接改 profile 文件

边界：

- 管理面改动的是节点当前 route 注册表，不是反写配置目录

### 4.5 正式状态来源关系

正式规定如下：

- 当前激活 profile 决定默认本地供给是什么
- `load_model_catalog()` 只负责把默认供给翻译成 seed 输入
- 启动时，seed 只做默认本地供给同步
- 网关路由、`/v1/models` 暴露、`/admin/models` 展示都以 `model_routes` 为准
- external route、手工新增 route、被禁用 route 都只存在于 `model_routes` 层，不要求回写 profile

## 5. 同步规则

### 5.1 启动 seed

启动 seed 不再负责重建整表，只负责把当前激活 profile 对应的默认本地 route 同步进 `model_routes`。

正式规则：

- 不再删除“当前 catalog 中不存在”的全部 route
- 不再把 `model_routes` 当成可随时整体覆盖的缓存
- external route、手工新增 route、历史保留但已禁用 route 不因重启消失

### 5.2 同名 route 的覆盖规则

对于 seed 与现有 route 同名的情况：

- 若现有 route 是 `profile_seed`，允许按 seed 规则更新受托管字段
- 若现有 route 是 `manual`，不自动覆盖，应跳过并记录冲突

seed 可更新的受托管字段限定为：

- `backend_type`
- `backend_model`
- `upstream_model`
- `upstream_base_url`
- `display_name`

seed 不应无条件覆盖的人工治理字段包括：

- `enabled`
- `capabilities_json`
- `upstream_auth_kind`
- `upstream_auth_ref`

### 5.3 人工新增 route

人工新增 route 直接进入 `model_routes`，作为长期注册表对象保存。

phase 1 只开放：

- `lifecycle_mode=external` 的 route 创建

phase 1 明确不开放：

- `managed_local` create

原因：

- 当前本地受控后端生命周期仍由 profile + control plane 决定
- 如果开放 `managed_local` create，用户会自然理解为系统会管理新的本地实例
- 但当前控制面并没有相应的实例注册、容器编排和资源分配语义

### 5.4 删除 route

删除语义采用显式管理规则，不再依赖 seed 隐式清表。

正式规则：

- `manual` route 可物理删除
- `profile_seed` route phase 1 不允许物理删除，只允许 `enabled=false`

这样定义的原因是：

- 若当前 profile 仍提供某个 managed_local route，物理删除后会在下次启动再次出现
- 在没有 tombstone 机制前，把 `profile_seed` route 的正式“移除”语义定义为禁用，更可预测

## 6. 存储、API 与管理台变更

### 6.1 存储层变更

为 `model_routes` 新增治理字段：

- `source_kind TEXT NOT NULL DEFAULT 'profile_seed'`
- `source_ref TEXT`
- `stale INTEGER NOT NULL DEFAULT 0`

字段语义：

- `source_kind`
  - `profile_seed`
  - `manual`
- `source_ref`
  - 对 `profile_seed` 保存 profile 名
  - 对 `manual` phase 1 可为空
- `stale`
  - 标记该 route 是否已不再属于当前激活 profile 的默认供给

### 6.2 seed 行为改造

[`seed_model_routes()`](../../../llmnode/storage/db.py) 应从“整表重建”改成“按 `source_kind` 增量同步”：

- 不再执行全表差集删除
- 只 upsert 当前 catalog 对应的 `profile_seed` route
- 若已存在同名 `manual` route，则拒绝覆盖并记录冲突
- 若旧 `profile_seed` route 不再属于当前 catalog，则标记：
  - `stale=1`
  - `enabled=false`

### 6.3 管理 API

保留现有：

- `PATCH /admin/models/{name}`

新增：

- `POST /admin/models`
  - phase 1 仅允许创建 `lifecycle_mode=external`
  - 拒绝同名 route
  - 拒绝 `managed_local` create
- `DELETE /admin/models/{name}`
  - phase 1 仅允许删除 `source_kind=manual` 的 route
  - 对 `profile_seed` route 返回冲突，并提示使用禁用

对 `PATCH /admin/models/{name}` 的新增约束：

- 不允许通过 patch 修改 route 身份来源
- 不允许把 `profile_seed` route 直接转换成 `manual external`
- 不允许把 `manual` route 直接转换成 profile 托管对象

### 6.4 管理台变更

管理台模型页应新增：

- route 来源标识
  - `Profile Seed`
  - `Manual`
- stale 状态提示
- 动作限制可视化
  - `profile_seed`：允许编辑、允许禁用、不允许删除
  - `manual`：允许编辑、允许禁用、允许删除
- 新建 route 入口
  - phase 1 仅提供 external route 表单

## 7. 迁移、兼容与回滚

### 7.1 数据库迁移

迁移方式沿用当前仓库风格：

- 通过启动时增量补列完成
- 不做破坏式重建

旧库的初始迁移规则：

- 现有 route 默认标记为 `source_kind=profile_seed`
- `source_ref` 先写当前 `active_backend_profile`
- `stale=0`

这不能百分百恢复历史来源，但比把旧数据统一伪装成 `manual` 更安全。

### 7.2 兼容过渡

迁移后的兼容要求：

- 现有 `PATCH /admin/models/{name}` 继续可用
- 现有 `/v1/models` 和三协议路由分发继续从 `model_routes` 读
- 已有 route 编辑结果不再因重启被 seed 静默覆盖

这次迁移的核心不是更换读取路径，而是把 `model_routes` 从缓存提升为正式注册表。

### 7.3 profile 切换

当 `active_backend_profile` 切换时：

- 若新 profile 生成的新 route 名与旧 route 不同：
  - 新 route upsert 为 `profile_seed`
  - 旧 `profile_seed` route 不删除
  - 若已不属于当前 catalog，则标记 `stale=1` 且 `enabled=false`
- 若新旧 profile 的 route 名相同但参数不同：
  - 视为同一 profile-managed route 更新
  - 按受托管字段同步
- `manual` route 不因 profile 切换而被删除或覆盖

### 7.4 回滚策略

回滚分两层：

- 代码回滚
  - 旧代码可以忽略新增列继续读取 SQLite
- 行为回滚
  - 迁移期允许保留一个受控开关，临时回退到旧式全量 seed

但该开关只作为迁移保险丝，不进入长期正式能力叙事。

## 8. 风险与缓解

### 风险 1：旧库 route 来源无法完全追溯

缓解：

- 首轮统一归类为 `profile_seed`

### 风险 2：profile 切换后 stale route 残留增多

缓解：

- 自动 `enabled=false`
- 管理台显式标记 stale 状态

### 风险 3：manual route 与新 profile seed 同名冲突

缓解：

- 启动时拒绝覆盖
- 记录冲突并要求人工处理

### 风险 4：用户误解 managed_local create 能力

缓解：

- phase 1 明确不开放 `managed_local` create
- 在 API 与管理台中都写清限制

## 9. 推荐实施顺序

推荐按下面顺序进入 `plan`：

1. phase A：route 注册表正式化与增量 seed
2. phase B：external route 新增能力
3. phase C：manual route 删除能力与 stale 管理

managed_local create / delete 不进入本轮。
