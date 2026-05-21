# 历史演进

## 0. 文档定位

这份文档只记录“版本或阶段之间发生了什么变化”，不重复完整蓝图，也不承担未来规划。  
它主要回答：

1. 这一阶段相比上一阶段改了什么。
2. 为什么这些变化重要。
3. 这些变化怎样改变了系统阶段判断。
4. 如果要看当时完整设计，应该跳到哪份历史蓝图。

它不负责：

- 描述当前完整状态，那是 [current.md](current.md)。
- 规划未来优先级，那是 [roadmap.md](roadmap.md)。
- 展开尚未落地的设计方案，那是相关 `docs/superpowers/specs/*.md`。
- 用长篇叙事重复完整蓝图。

## 1. 使用方法

如果你想回答不同问题，建议这样跳转：

- 看“现在是什么”：去 [current.md](current.md)
- 看“下一步做什么”：去 [roadmap.md](roadmap.md)
- 看“准备怎么设计”：去相关 `docs/superpowers/specs/*.md`
- 看“接下来怎么执行”：去相关 `docs/superpowers/plans/*.md`
- 看“某一阶段完整历史快照长什么样”：去 `docs/blueprint/archive/*.md`

阅读历史快照时要注意：

- `docs/blueprint/archive/*.md` 保留的是当时语境，不保证术语仍代表当前方向。
- 其中出现的旧控制方式、旧后端边界、旧部署假设，应按历史背景理解，不能直接覆盖 `current.md / roadmap.md` 的当前口径。

## 2. 什么时候更新这份文档

只有当变化足以改变“阶段判断”或“里程碑认知”时，才应更新本文件。常见触发包括：

- 主链路形态发生明显变化
- 控制入口发生重大变化
- 正式产物版图发生扩展
- 真相源边界发生重大变化
- 一个长期提案已经落地，并改变了系统成熟度判断

下面这些情况通常不应直接更新 `history.md`：

- 只是补一条局部命令
- 只是文案顺序微调
- 只是仍在讨论中的方案
- 只是局部字段变化

这些内容更适合进入：

- [roadmap.md](roadmap.md)
- 相关 `docs/superpowers/specs/*.md`
- 相关契约或流程文档

## 3. 阶段索引

### V1

- 阶段判断：
  `llmnode` 仍偏原型期，核心目标是让本地网关链路先能跑通。
- 关键变化：
  对外协议开始对齐 OpenAI 与 Claude Code。
- 为什么重要：
  从这一步开始，项目不再只是单模型实验，而是有了统一网关方向。
- 对后续意味着什么：
  后续会围绕网关、鉴权、后端生命周期和正式运行路径继续收口。
- 对应历史蓝图：
  [archive/v1-full.md](archive/v1-full.md)

### V2

- 阶段判断：
  项目开始从“能跑”推进到“可控制、可治理、可观察”的平台化阶段。
- 关键变化：
  引入 `node-agent`、`web-console`、控制面、日志、API Key 和管理接口。
- 为什么重要：
  系统开始从简单代理，转向可维护的单机节点系统。
- 对后续意味着什么：
  后续重点不再只是起服务，而是补足控制、诊断、配置、路由和管理面。
- 对应历史蓝图：
  [archive/v2-full.md](archive/v2-full.md)

### 当前阶段

- 阶段判断：
  三后端正式路径均已完成线上联调验证，控制入口已统一，当前重点转向平台化控制面与管理台补厚。
- 关键变化：
  `python -m llmnode.control` 已成为正式控制入口；
  shell 脚本兼容层被移除；
  文档系统开始从零散蓝图文件收敛到正式分层；
  `V3 / V4` 不再保留独立蓝图文件，未来规划统一回流到 `roadmap.md`，设计展开统一转入 `docs/superpowers/*`。
- 为什么重要：
  这标志着项目开始具备更清晰的长期维护形态，而不是继续叠加临时入口。
- 对后续意味着什么：
  后续重点转向：
  - 管理台与三后端状态展示对齐
  - 控制面诊断能力提升（`doctor / logs / status`）
  - 文档系统继续补厚
- 补充里程碑（2026-05）：
  三后端代码实现全部落地：`ContainerSpec / BackendDriver / service.py / control.py / api/app.py` 均已按 `backend_type` 动态路由；`gpu_memory_utilization` 改为 `0.9`；运行配置已进一步向 profile 驱动收口；GGUF 转换链路（f16 → Q4_K_M）已完成。
- 补充里程碑（2026-05-12）：
  **三后端线上联调验证全部完成**：vLLM / llama.cpp / SGLang 各自跑通推理链路，`reasoning_content` / `content` 干净分离已确认。主要发现：llama.cpp 须用 `full-cuda` 镜像（`:full` 为纯 CPU），验证约 68 token/s / 26GB VRAM；SGLang 需 `--reasoning-parser qwen3` 参数（非特性缺失，仅启动命令遗漏）；旧容器复用会导致启动参数变更不生效（需先 `docker rm`）。详见 [docs/knowledge/backend_integration_qa.md](../knowledge/backend_integration_qa.md)。
- 补充里程碑（2026-05-13）：
  **文档系统第二轮收口已完成**：`docs/knowledge/*` 已固定为常驻参考层，`docs/superpowers/*` 已固定为进行中工作区；`README.md` 的失效文档入口已清理，文档边界统一回流到 `development-workflow / glossary / current / roadmap`。这标志着文档系统从”第一轮分层”进入”第二轮边界固化”阶段。
- 补充里程碑（2026-05-14）：
  **profile 驱动配置收口与 API Key 管理台能力补齐**：激活 profile 与后端配置已继续向 `config/defaults.yaml + config/backends/*.yaml` 收口；API Key 管理台后端返回 `masked_key` 脱敏字段和 `usage_summary` 用量统计，新增 `/admin/overview/readiness` 端点统一下发 Base URL；管理台密钥页面支持 Base URL 展示/复制、新建密钥显示/隐藏切换、历史密钥 masked_key 和用量展示。
- 补充里程碑（2026-05-15）：
  **Usage Ledger 与聚合视图落地**：`request_metrics` 已扩展 `backend_type`、`api_key_id` 与 cache token 字段；后端聚合查询支持 summary / trend / breakdown / key usage；管理面新增 `/admin/overview/usage` 和 `/admin/keys/{id}/usage`；流式请求在 stream 结束后写入 metric；管理台总览和请求记录页已接入总 Token、缓存 Token、趋势图和后端分布；SQLite 迁移兼容与索引已补齐。
- 补充里程碑（2026-05-15）：
  **默认密钥后门已移除，API Key 初始化路径正式化**：网关已移除默认 `dev-key` / bootstrap key 放行，正式鉴权统一收敛到数据库 API key；真实密钥格式改为 `sk-<64hex>`，历史列表脱敏展示改为 `sk-****` 风格；控制面新增 `python -m llmnode.control create-api-key` 作为首把管理员密钥初始化路径；管理台顶部新增轻量 API key 输入入口，不再依赖默认预置密钥。
- 补充里程碑（2026-05-21）：
  **admin key 与推理 key 已正式分离**：控制面新增 `create-admin-key / rotate-admin-key / admin-key-status` 作为唯一 admin key 管理路径；数据库内只允许一把 `name=admin`、`scope=admin` 的控制面密钥；普通 `/admin/keys` 列表不再展示这把 admin key；`web-console` 不再依赖 `runtime/data/web-console-admin.key`，改为通过右上角“管理员”入口录入或更新本地保存的 admin key；static 模式若发现被接管的 Vite 进程会主动停止，不再保留 dev server。
- 补充里程碑（2026-05-15）：
  **Readiness 热身语义与结构化事件已正式化**：`node-agent` 已拆分 `http_ready / inference_ready` 双阶段就绪语义；网关在热身窗口返回 `503 + Retry-After`，并使用固定 `detail` 枚举；`agent_events` 已扩展 `event_type / readiness_state / http_ready / inference_ready / metadata_json`，其中热身失败和恢复路径会记录 `stream_not_ready`、`backend_recovered` 等结构化事件，管理台与排障接口可直接消费。
- 补充里程碑（2026-05-15）：
  **多协议统一内核一期最小闭环已落地**：模型 route 已正式拆分 `backend_type / upstream_protocol / lifecycle_mode` 三层语义；`/admin/models` 与管理台模型页可直接配置 external responses/chat/messages 上游；`/v1/responses` 已支持 native responses、`responses -> chat` 与 `responses -> messages` 三路径，`previous_response_id` 已支持 native/local 两类续接；`/v1/chat/completions` 与 `/v1/messages` 也已具备最小 route-aware external upstream 分发；external upstream 鉴权不再发送占位 token，`upstream_auth_ref` 当前按环境变量名解析真实 secret。
- 补充里程碑（2026-05-18）：
  **route 注册表平台化 phase 1 已落地**：`model_routes` 已从启动时可整表重建的运行态缓存升级为单机节点上的长期 route 注册表；新增 `source_kind / source_ref / stale` 用于表达 route 来源与同步状态；启动 seed 已改为 `profile_seed` 增量同步，不再清空 manual route；旧 profile route 会标记 `stale=1` 且自动禁用；`/admin/models` 与管理台模型页现已形成 `external route create + manual route delete` 的最小管理闭环，而 `profile_seed` route 当前只允许编辑和禁用，不允许物理删除或直接转换为 manual external route。
- 补充里程碑（2026-05-18）：
  **route phase 2 可观测性与配置回退语义已补齐一轮收口**：管理台总览与模型页之外，启动 seed 的 reconcile 结果现已进入 `/admin/events`，至少可观察 `route_marked_stale / route_manual_preserved`；同时配置加载与 smoke 测试已进一步统一到“当前激活 profile / 当前配置决定运行真相”，`load_settings()` 在自定义 defaults/backends 场景下若本地 active profile 缺字段，会优先回退到 repo 中同名 profile，而不再串回 repo 默认 profile。
- 对应历史蓝图：
  未来方向已回流到 [roadmap.md](roadmap.md)，相关正式边界已进入 [current.md](current.md) 与相关 `contracts / process` 文档。

## 4. 写阶段记录时的最小要求

后续新增阶段记录时，建议至少包含：

- 阶段名或版本名
- 阶段判断
- 关键变化
- 为什么重要
- 对当前系统判断的影响
- 对应完整设计入口

如果一条记录回答不了“为什么重要”，通常说明它更像实现细节，还不够成为阶段级变化。

## 5. 与设计稿和旧蓝图的关系

- 设计稿在落地前，应停留在相关 `docs/superpowers/specs/*.md`
- 设计稿落地后，如果改变了阶段判断，应回流到本文件
- 本文件只记录“变化摘要”，不保存完整设计现场
- 历史完整设计由 `docs/blueprint/archive/*.md` 保留；未落地的未来设计展开转入 `docs/superpowers/*`

一句话说：

- `specs` 回答“准备怎么设计”
- `history.md` 回答“最后发生了什么变化”
- `archive/*.md` 回答“当时完整是怎么想的”
