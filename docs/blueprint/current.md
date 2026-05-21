# 当前蓝图

## 0. 文档定位

这份文档不是愿景说明，也不是版本历史回顾，而是 `llmnode` 当前真实运行状态的压缩总图。  
它只回答四个问题：

1. 项目现在到底运行到了哪一步。
2. 哪些能力已经落地，哪些仍处于设计目标或迁移中。
3. 当前主链路、正式控制入口和真相源边界是什么。
4. 当前阶段最应该优先补什么。

它不负责：

- 解释版本如何演进，那是 [history.md](history.md)。
- 规划未来优先级，那是 [roadmap.md](roadmap.md)。
- 展开重大设计与迁移方案，那是相关 `docs/superpowers/specs/*.md`。
- 记录具体实施拆分，那是相关 `docs/superpowers/plans/*.md`。

建议阅读顺序：

- [README.md](../../README.md)
- [history.md](history.md)
- [docs/contracts/control-plane.md](../contracts/control-plane.md)
- [docs/process/run.md](../process/run.md)
- [docs/glossary.md](../glossary.md)

## 1. 当前阶段判断

一句话判断：

- `llmnode` 已经不是”能不能起服务”的原型，而是”三后端正式路径均已完成线上联调验证、控制面已收口，当前重点转向配置真相收口、route 边界澄清与管理面补厚的单机推理网关”。

这意味着当前阶段的真实特点是：

- 对外协议已经稳定，主链路已经成立。
- 控制入口已经从 shell 脚本收口到 Python 控制面。
- 当前运行路径仍明确偏向 `vLLM` 单后端正式路径。
- 后续主要矛盾不再是“有没有服务”，而是“控制面是否足够完整、多后端是否能有序引入、文档和配置边界是否足够清楚”。

## 2. 当前系统定位

当前系统的真实定位可以概括为三层：

- 网关层：对外提供统一 API、鉴权、路由、审计和协议兼容。
- 控制层：通过 `node-agent` 和 `python -m llmnode.control` 管理本机推理后端生命周期。
- 治理层：通过管理台、日志、SQLite、配置文件与正式文档维持一致性。

从产品定位上看，当前系统更准确的定义不是“实验脚本集”，而是“单机本地 LLM 节点控制与网关系统”的雏形成品：

- 首要职责不是解释大模型概念，而是稳定提供本地推理接入与控制能力。
- `web-console`、控制面、配置、日志、健康检查和后端容器管理都属于正式能力的一部分。
- `node-agent` 当前已区分“期望运行”和“用户手动停止”，手动 stop 后不会再把后端当作故障自动拉起。
- 当前重点不在多节点和分布式，而在单机路径的可维护、可诊断和可扩展。

## 3. 当前正式主链路

当前正式主链路按执行顺序可以理解为：

1. `python -m llmnode.control start`
   拉起 `node-agent`、`vLLM`、`gateway-api`，并在产品态通过 `gateway-api` 提供 `/console/` 静态管理台
2. `python -m llmnode.control status`
   查看控制面摘要、HTTP 健康和当前栈状态
3. `python -m llmnode.control doctor`
   检查环境、依赖、端口、Docker、日志与建议动作
4. `python -m llmnode.control logs`
   查看关键服务日志
5. `python -m llmnode.control stop`
   执行有序停机

这条链路的目标不是只把服务拉起来，而是形成：

- 可预测的启动路径
- 可扫描的状态输出
- 可回放的日志入口
- 可诊断的环境体检
- 可继续扩展到多后端的控制骨架

## 4. 当前正式产物面

当前被视为正式产物或正式运行面的一组对象包括：

- 对外 API：
  - `GET /v1/models`
  - `POST /v1/responses`
  - `POST /v1/chat/completions`
  - `POST /v1/messages`
- 控制面命令：
  - `start`
  - `stop`
  - `restart`
  - `status`
  - `env`
  - `doctor`
  - `logs`
  - `create-inference-key`
  - `rotate-inference-key`
  - `inference-key-status`
  - `create-api-key`（兼容旧入口）
  - `create-admin-key`
  - `rotate-admin-key`
  - `admin-key-status`
- 管理台：
  - 总览状态卡片
  - 实时 SSE 面板
  - 请求表
  - 节点事件表
  - 趋势图
- 运行产物：
  - `runtime/data`
  - `runtime/logs`
  - `runtime/run`
  - 默认情况下，SQLite 主库是 `runtime/data/gateway.db`
  - 如果显式覆盖 `VLLM_CLAUDE_RUNTIME_DIR`，默认主库会随之移动到 `<runtime_dir>/data/gateway.db`

这些内容的正式约束分别由下列文档解释：

- [控制面契约](../contracts/control-plane.md)
- [后端路由契约](../contracts/backend-routing.md)
- [运行流程](../process/run.md)
- [部署流程](../process/deployment.md)

## 5. 当前系统骨架

当前主干服务角色已经比较清楚，至少包括下面几个对象：

- `gateway-api`
  - 鉴权
  - API 协议兼容
  - 模型路由
  - 请求审计
  - `/v1/responses` native/chat/messages 三路径兼容
- `node-agent`
  - 后端启停
  - 容器健康检查
  - 自动恢复
  - 容器状态采样
- `llmnode.control`
  - 统一控制入口
  - 整栈管理
  - 单服务控制
  - 环境诊断
  - 日志汇总查看
- `web-console`
  - 管理台入口
  - 控制面可视化
  - 配置与观察界面
  - 产品态默认由 `gateway-api` 挂载静态构建产物；Vite 只作为显式 dev 模式入口

这意味着当前系统已经不是几个独立命令拼装，而是形成了：

- 对外服务层
- 本机控制层
- 运行治理层
- 管理台观察层

这一整条骨架。

## 6. 当前运行形态现状

当前运行形态应按下面理解：

- 实际使用哪个后端、模型目录和端口，由当前激活的 `active_backend_profile` 与对应 profile 配置决定
- `config/defaults.yaml` 只负责声明当前激活的 profile
- `config/backends/*.yaml` 才是具体“后端 + 模型”运行参数来源

当前现实包括：

- 当前代码实现支持 `vllm / llama.cpp / sglang` 三种本地受控后端
- 当前已落地的 profile 分层清晰：
  - `config/backends/vllm_qwen36-27b-FP8.yaml`
  - `config/backends/vllm_qwen36-35b-a3b-fp8.yaml`
  - `config/backends/vllm_qwen36-35b-a3b.yaml`
  - `config/backends/llama.cpp_qwen36-35b-a3b-q4km.yaml`
  - `config/backends/llama.cpp_qwen36-35b-a3b-f16.yaml`
  - `config/backends/sglang_qwen36-35b-a3b-fp8.yaml`
  - `config/backends/vllm_qwen36-27b.yaml`
- 三后端均已完成线上联调验证（2026-05-12）：
  - `vLLM`：正常推理，`reasoning_content` / `content` 干净分离
  - `llama.cpp`：须使用 `full-cuda` 镜像，约 68 token/s，显存占用约 26GB，`reasoning_content` 正常
  - `SGLang`：需 `--reasoning-parser qwen3` 参数（`distro` 模块补丁已合入），`reasoning_content` 正常分离
- 三后端统一由 Python 控制面通过 Docker 编排，`control.py` 已完整感知三后端
- `web-console` 当前主要承担状态查看和日常配置入口，正式默认入口为 `http://127.0.0.1:4000/console/`
- 控制面诊断能力已增强（2026-05-12）：
  - `doctor` 命令支持三后端特定检查、GPU 信息、模型格式检测、智能建议
  - `status` 命令支持容器详细信息、推理参数展示、6 种栈状态
  - `logs` 命令支持实时跟踪、错误高亮、关键词搜索
  - Agent 服务暴露诊断 API 端点（`/admin/diagnostics/*`）
  - 管理台前端已对齐三后端状态展示
- 最小 P1 性能指标采集已落地（2026-05-13）：
  - 网关会为成功、拒绝和无 `usage` 的请求落库 `request_metrics`
  - Agent 暴露 `GET /admin/diagnostics/metrics`
  - 当前聚合指标包括请求数、成功率、平均/分位延迟、吞吐和稳定回退 `queue_length`
- API Key 管理台能力已补齐（2026-05-14）：
  - 后端 API key 列表和创建接口返回 `masked_key` 脱敏字段
  - key 列表接口附带 `usage_summary`（总请求数、总 Token 数）
  - 新增 `/admin/overview/readiness` 端点，统一下发 Base URL 和就绪状态
  - 管理台密钥页面展示 Base URL 卡片、复制按钮、密钥显示/隐藏切换
  - 历史 key 列表中展示 masked_key 和用量统计
- 正式 usage ledger 已落地（2026-05-15）：
  - `request_metrics` 表支持 `backend_type`、`api_key_id`、cache token 字段
  - 聚合查询支持按模型 / 后端 / API Key / 日月年维度输出 summary / trend / breakdown
  - 管理面新增 `/admin/overview/usage` 与 `/admin/keys/{id}/usage` 视图端点
  - 管理台总览与请求记录页已接入总 Token、缓存 Token、趋势图和后端分布
  - 流式请求会在 stream 结束后补写 metric，缺失 usage 字段时保持 `null`，不伪装为 `0`
- Readiness 语义与热身期错误边界已收口（2026-05-15）：
  - `node-agent` 已正式区分 `http_ready` 与 `inference_ready`
  - 后端 HTTP 可达但推理探针未通过时，状态为 `warming_up`
  - 网关在未就绪时返回 `503 + Retry-After`，`detail` 使用固定枚举 `backend_warming_up / backend_not_ready / agent_state_unavailable / agent_not_ready`
  - `agent_events` 已记录结构化 readiness 事件，包含 `event_type`、`readiness_state`、`http_ready`、`inference_ready` 与 `metadata_json`
  - 热身探针失败与恢复至少会落库 `stream_not_ready`、`backend_recovered` 事件，供管理台与排障读取
- API Key 正式边界已收紧（2026-05-15）：
  - 网关已移除默认 `dev-key` / bootstrap key 放行路径
  - 正式鉴权只接受数据库中的 API key，默认必须先创建密钥才能使用
  - 新建真实密钥统一使用 `sk-<64hex>` 格式
  - 历史列表展示的 `masked_key` 已改为 `sk-****` 风格，不再使用 `ln_saved_n`
  - admin key 已从普通推理 key 语义中拆出：
    - 数据库内只允许存在一把
    - 名字固定为 `admin`
    - scope 固定为 `admin`
    - 不再通过 `runtime/data/web-console-admin.key` 落地
  - 控制面新增 `create-admin-key / rotate-admin-key / admin-key-status` 作为正式 admin key 管理路径
  - 通用 `create-api-key` 当前只承担 inference-only 推理 key 创建，不再用于创建 admin key
  - 管理台改为通过右上角“管理员”入口录入或更新本地保存的 admin key
- 多协议路由管理面已打通（2026-05-15）：
  - `/admin/models` 与管理台模型页已支持编辑 `lifecycle_mode / upstream_protocol / upstream_base_url / upstream_model / upstream_auth_kind / upstream_auth_ref / capabilities_json`
  - 本地受控 route 与外部上游 route 已有明确校验边界：
    - `managed_local` 必须保留 `backend_type / backend_model`
    - `external` 必须提供 `upstream_base_url / upstream_model`
  - 管理台模型页已从“单字段映射表”升级为 route 配置卡片，可直接配置 external responses/chat/messages 上游
  - route 能力开关已支持在管理台声明 `responses / chat / messages / stream / tools / previous_response_id / json_schema`
- route 注册表平台化 phase 1 已落地（2026-05-18）：
  - `model_routes` 已升级为单机节点上的长期 route 注册表
  - route 新增记录 `source_kind / source_ref / stale`，区分 `profile_seed` 与 `manual`
  - 启动 seed 已改为增量同步，不再清空 manual route
  - 不再属于当前激活 profile 的 `profile_seed` route 会标记 `stale=1` 且自动 `enabled=false`
  - `/admin/models` 已支持 external route 新增与 manual route 删除
  - `profile_seed` route 当前允许编辑和禁用，但不允许物理删除或直接转换成 manual external route
- route 管理闭环 phase 2 已开始补厚（2026-05-18）：
  - 管理台模型页现已对 `stale + profile_seed` route 显示明确治理提示
  - 管理台模型页现已明确写出这类 route 当前允许和不允许的治理动作
  - 管理台模型页会展示 `source_ref` 对应的来源 profile
  - `profile_seed` route 的 `lifecycle_mode` 已在前端锁定，不再允许直接改成 `external`
  - `stale + profile_seed` route 当前也不允许直接重新启用；如需恢复，应切回来源 profile，或新建 manual route
  - 管理台总览页已新增 route 治理摘要，可直接看到 `stale / manual / profile_seed` 数量
- Claude Code 本地兼容边界已补齐协议透传（2026-05-18）：
  - `/v1/messages` 的 `managed_local + chat` facade 现已保留 Anthropic / Claude Code 风格的 function tool 定义（`name + description + input_schema`）并透传到本地后端
  - `/v1/messages/count_tokens` 已提供最小兼容实现，避免 Claude Code 在工程模式探测时直接 404
  - 默认附带的 builtin tool 元数据（如 `bash_* / web_search_* / text_editor_*`）仍会被过滤；真正未开放的仍是 builtin tools，而不是 Anthropic function tools
  - 启动 seed 的 route reconcile 结果现已接入 `/admin/events`，至少可观察到 `route_marked_stale` 与 `route_manual_preserved`
- gateway 原生透传治理模型已切换到 phase 1（2026-05-18）：
  - 正式原则已改为 `native pass-through first`，只要 route 原生支持客户端协议，gateway 默认不改业务 payload 语义
  - `adapter opt-in only` 已生效；协议转换不再默认兜底，只允许 route 显式开启的 adapter 生效
  - 当前兼容边界按 `client_protocol + route 能力声明` 判定，而不是按 `Claude Code / Codex / Cherry Studio` 这类客户端品牌做专门 payload 魔改
  - `managed_local + vLLM` 当前按 `chat / responses / messages` 三协议原生支持处理
  - route 运行时语义已拆成 `native_protocols / adapter_policies / tool_policies / protocol_features`
  - 工具治理已拆成 `OpenAI function / Anthropic function / builtin tools` 三类，默认仍拒绝 builtin tools
  - `request_logs` 已开始记录 `execution_mode / adapter_selected / request_mutation` 等结构化元数据，供管理面排查协议路径
- route runtime 语义推荐默认与管理闭环已收口到统一真相源（2026-05-19）：
  - `ModelRoute.recommended_runtime_semantics()` 已成为推荐 runtime 默认的正式派生入口
  - `/admin/status` 与 `/admin/models` 当前会为每条 route 返回 `recommended_runtime_semantics`
  - 管理台模型页当前优先消费后端返回的推荐默认，不再只依赖前端本地 helper
  - 管理台已具备基于推荐默认的风险提示、协议切换自动套用、恢复推荐默认闭环
  - `upsert_model_route()` 当前会在调用方未显式提供 runtime 四层字段时自动补齐推荐默认再落库，避免 direct write / CLI / seed 路径把 runtime 语义写成空值
- 配置真相源与测试基线继续收口（2026-05-18）：
  - `tests/test_smoke.py` 已改为围绕 repo 当前激活 profile 与 profile 文件解析断言配置行为，不再断言固定默认模型名
  - `load_settings()` 在自定义 defaults/backends 场景下，若本地 active profile 缺字段，现会优先回退到 repo 中同名 profile，而不是串回 repo 默认 profile
- 三协议入口的 route-aware 上游分发已补到 phase1 最小闭环（2026-05-18）：
  - `/v1/responses` 当前先按 route 的 `native_protocols` 判定：
    - 原生支持 `responses` 时走 native upstream `/v1/responses`
    - 仅在 route 显式开启时，才允许 `responses -> chat` 或 `responses -> messages` 适配
    - 未声明原生支持且未显式开启 adapter 时，默认保守失败
  - `/v1/chat/completions` 已可按 route 直连 external chat upstream
  - `/v1/messages` 已可按 route 直连 external messages upstream
  - external upstream 鉴权已不再发送占位 token；`upstream_auth_ref` 当前按环境变量名解析真实 secret
  - 现有本地 vLLM 主路径当前按原生三协议处理：
    - `managed_local + vLLM` 继续服务 `/v1/chat/completions`
    - `managed_local + vLLM` 原生服务 `/v1/responses`
    - `managed_local + vLLM` 原生兼容 `/v1/messages` 入口

当前模型与 profile 边界应这样理解：

- 没有独立于配置之外的“默认模型”概念
- 当前激活哪个 backend profile，就以该 profile 所声明的模型目录、模型名和后端参数作为运行真相
- 现有若干 Qwen / GGUF / SGLang profile 属于可选运行路径，不应再在正式文档里写成固定默认模型
- `DeepSeek-V4-Flash`、`gemma-4-31B-it` 当前仍未进入正式 profile 路径

与模型能力相关的长期参考仍分开放置：

- 性能与长上下文记录见 [docs/knowledge/model_context_performance.md](../knowledge/model_context_performance.md)
- 格式转换、量化与部署建议见 [docs/knowledge/model_format_conversion.md](../knowledge/model_format_conversion.md)

## 7. 当前配置与真相源边界

当前明确成立的真相源边界是：

- 当前激活 profile 选择：`config/defaults.yaml`
- 后端与模型 profile 目录：`config/backends/*.yaml`
- Python 控制入口：`llmnode/control.py`
- 网关配置加载：`llmnode/config.py`
- 当前系统真相：本文

当前安全边界补充：

- `config/defaults.yaml` 中 `gateway.api_key` 已默认置空，不再作为正式 bootstrap 鉴权入口
- 首把管理员密钥的正式创建路径是本地控制命令 `python -m llmnode.control create-admin-key`
- 浏览器端仅保存用户手工输入的 `sk-...` 密钥，不再默认预填 `dev-key`

这意味着如果出现“README 说法、旧蓝图说法、代码行为不一致”的情况，优先应对照：

1. 当前代码与配置真实行为
2. `docs/contracts/*.md`
3. `docs/process/*.md`
4. 本文与 `README.md`

## 8. 当前后端边界

当前代码实现支持：

- `vLLM`（`backend_type: vllm`）
- `llama.cpp`（`backend_type: llama.cpp`）
- `SGLang`（`backend_type: sglang`）

当前明确边界：

- 三后端的 ContainerSpec 与 BackendDriver 均已落地
- 切换后端通过 `config/defaults.yaml` 的 `active_backend_profile` 或对应环境变量控制
- 三后端均已完成线上联调验证（2026-05-12），详见 [docs/knowledge/backend_integration_qa.md](../knowledge/backend_integration_qa.md)
- 管理面 `/admin/models/{name}` 现已接受 `vllm / llama.cpp / sglang` 三个值
- 当前激活 profile 仍决定本地受控 route 的默认供给
- 启动时会把该默认供给增量同步到 SQLite 的 `model_routes`
- `model_routes` 现已作为长期 route 注册表保存 manual route、stale 状态与治理字段
- `model_routes` 当前也会持久化 route 的 runtime 四层治理字段：
  - `native_protocols_json`
  - `adapter_policies_json`
  - `tool_policies_json`
  - `protocol_features_json`
- 当前 phase 1 已形成 external route 新增、manual route 删除、profile seed 增量同步的最小管理闭环

## 9. 当前文档系统状态

当前文档系统已经完成第一轮正式分层：

- `README.md`
  作为项目唯一总入口
- `docs/blueprint/current.md`
  作为当前真相入口
- `docs/blueprint/history.md`
  作为演进摘要入口
- `docs/blueprint/roadmap.md`
  作为未来规划入口
- `docs/contracts/*.md`
  作为正式契约层
- `docs/process/*.md`
  作为流程层
- `docs/glossary.md`
  作为术语层

当前仍保留但已完成边界收口的内容包括：

- 历史归档 `docs/blueprint/archive/*`
- 知识性文档 `docs/knowledge/*`
- 过程设计与计划 `docs/superpowers/*`

它们当前仍保留，但边界已经明确：

- `docs/knowledge/*` 是常驻参考层，不承担正式真相
- `docs/superpowers/*` 是进行中工作区，不作为长期沉淀层

额外边界：

- 不再保留 `docs/blueprintV3.md` 或 `docs/blueprintV4.md`
- 未来规划统一看 `docs/blueprint/roadmap.md`
- 设计展开与实施计划统一进入 `docs/superpowers/*`

## 10. 当前最该优先补的点

已完成：

- 三后端代码实现全部落地（ContainerSpec / BackendDriver / service.py / control.py / api/app.py 均已按 `backend_type` 动态路由）
- 多后端配置与实现之间的一致性已收敛（`config/defaults.yaml + config/backends/*.yaml` 与代码路由行为对齐）
- 对外 API 已扩展支持三种接口协议：`/v1/chat/completions`、`/v1/responses`、`/v1/messages`
- 一期路由重构已开始把模型语义拆为三层：
  - `backend_type`：本地受控推理后端类型
  - `upstream_protocol`：对上游发请求时使用的协议
  - `lifecycle_mode`：本地受控 route 与外部上游 route 的生命周期归属
- `/v1/responses` 当前已具备最小三路径能力（2026-05-15）：
  - external route 可按 `upstream_protocol=responses` 走原生 upstream `/v1/responses`
  - 本地 Qwen 等 chat-native route 继续走 `responses -> chat` 适配
  - messages-native route 现已可走 `responses -> messages` 适配
  - `previous_response_id` 已支持 native upstream continuation 与 local replay continuation 两种基础模式
- **三后端线上联调验证已完成（2026-05-12）**：vLLM / llama.cpp / SGLang 各自跑通推理链路，`reasoning_content` / `content` 干净分离已确认
- **控制面诊断能力增强已完成（2026-05-12）**：
  - `doctor` 命令支持三后端特定检查、GPU 信息、模型格式检测、智能建议
  - `status` 命令支持容器详细信息、推理参数展示、6 种栈状态
  - `logs` 命令支持实时跟踪、错误高亮、关键词搜索
  - Agent 服务暴露诊断 API 端点（`/admin/diagnostics/*`）
  - 管理台前端已对齐三后端状态展示

当前最值得继续补厚的方向包括：

- route 管理闭环补厚：继续补管理动作与治理语义，而不是重新讨论 stale/source 边界
- 节点平台化预留：保持单机前提下继续收口对象边界
