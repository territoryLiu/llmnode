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

- `llmnode` 已经不是”能不能起服务”的原型，而是”三后端正式路径均已完成线上联调验证、控制面已收口，当前重点转向平台化控制面与管理台补厚的单机推理网关”。

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
- 当前重点不在多节点和分布式，而在单机路径的可维护、可诊断和可扩展。

## 3. 当前正式主链路

当前正式主链路按执行顺序可以理解为：

1. `python -m llmnode.control start`
   拉起 `node-agent`、`vLLM`、`gateway-api`、`web-console`
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

这意味着当前系统已经不是几个独立命令拼装，而是形成了：

- 对外服务层
- 本机控制层
- 运行治理层
- 管理台观察层

这一整条骨架。

## 6. 当前运行形态现状

当前默认正式运行路径仍然是：

- 推理后端：`vLLM`
- 默认模型目录：`models/Qwen/Qwen3.6-35B-A3B`

当前现实包括：

- `vLLM` 是正式主路径（默认 `backend_type: vllm`）
- 三后端均已完成线上联调验证（2026-05-12）：
  - `vLLM`：正常推理，`reasoning_content` / `content` 干净分离
  - `llama.cpp`：须使用 `full-cuda` 镜像，约 68 token/s，显存占用约 26GB，`reasoning_content` 正常
  - `SGLang`：需 `--reasoning-parser qwen3` 参数（`distro` 模块补丁已合入），`reasoning_content` 正常分离
- 三后端统一由 Python 控制面通过 Docker 编排，`control.py` 已完整感知三后端
- `web-console` 当前主要承担状态查看和日常配置入口
- 控制面诊断能力已增强（2026-05-12）：
  - `doctor` 命令支持三后端特定检查、GPU 信息、模型格式检测、智能建议
  - `status` 命令支持容器详细信息、推理参数展示、6 种栈状态
  - `logs` 命令支持实时跟踪、错误高亮、关键词搜索
  - Agent 服务暴露诊断 API 端点（`/admin/diagnostics/*`）
  - 管理台前端已对齐三后端状态展示

## 7. 当前配置与真相源边界

当前明确成立的真相源边界是：

- 运行默认值：`config/defaults.yaml`
- 模型路由目录：`config/models.yaml`
- Python 控制入口：`llmnode/control.py`
- 网关配置加载：`llmnode/config.py`
- 当前系统真相：本文

这意味着如果出现“README 说法、旧蓝图说法、代码行为不一致”的情况，优先应对照：

1. 当前代码与配置真实行为
2. `docs/contracts/*.md`
3. `docs/process/*.md`
4. 本文与 `README.md`

## 8. 当前后端边界

当前代码实现支持：

- `vLLM`（默认，`backend_type: vllm`）
- `llama.cpp`（`backend_type: llama.cpp`）
- `SGLang`（`backend_type: sglang`）

当前明确边界：

- 三后端的 ContainerSpec 与 BackendDriver 均已落地
- 切换后端通过 `config/defaults.yaml` 的 `vllm.backend_type` 字段或对应环境变量控制
- 三后端均已完成线上联调验证（2026-05-12），详见 [docs/knowledge/backend_integration_qa.md](../knowledge/backend_integration_qa.md)
- 管理面 `/admin/models/{name}` 现已接受 `vllm / llama.cpp / sglang` 三个值

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

当前仍处于收口期的内容包括：

- 历史归档 `docs/blueprint/archive/*`
- 知识性文档 `docs/knowledge/*`
- 过程设计与计划 `docs/superpowers/*`

它们当前仍保留，但已经不应被当作项目日常总入口。

额外边界：

- 不再保留 `docs/blueprintV3.md` 或 `docs/blueprintV4.md`
- 未来规划统一看 `docs/blueprint/roadmap.md`
- 设计展开与实施计划统一进入 `docs/superpowers/*`

## 10. 当前最该优先补的点

已完成：

- 三后端代码实现全部落地（ContainerSpec / BackendDriver / service.py / control.py / api/app.py 均已按 `backend_type` 动态路由）
- 多后端配置与实现之间的一致性已收敛（`config/defaults.yaml` 与代码路由行为对齐）
- 对外 API 已扩展支持三种接口协议：`/v1/chat/completions`、`/v1/responses`、`/v1/messages`
- **三后端线上联调验证已完成（2026-05-12）**：vLLM / llama.cpp / SGLang 各自跑通推理链路，`reasoning_content` / `content` 干净分离已确认
- **控制面诊断能力增强已完成（2026-05-12）**：
  - `doctor` 命令支持三后端特定检查、GPU 信息、模型格式检测、智能建议
  - `status` 命令支持容器详细信息、推理参数展示、6 种栈状态
  - `logs` 命令支持实时跟踪、错误高亮、关键词搜索
  - Agent 服务暴露诊断 API 端点（`/admin/diagnostics/*`）
  - 管理台前端已对齐三后端状态展示

当前最值得继续补厚的方向包括：

- 文档系统第二轮收口（`docs/knowledge/*`、`docs/superpowers/*` 的定位与清理）
- 诊断建议的持续优化（新增错误模式识别）
- 性能指标采集（请求总数、延迟、吞吐量）
