# llmnode

`llmnode` 是一个单机本地 LLM 节点控制与网关系统。  
它对外统一兼容：

- `POST /v1/responses`
- `POST /v1/chat/completions`
- `POST /v1/messages`
- `GET /v1/models`

当前正式运行形态仍然是单机部署。  
当前实际使用哪个后端、模型与运行参数，由当前激活的 profile 和对应配置决定；`vLLM / llama.cpp / SGLang` 三后端已纳入统一控制面编排边界。

## 项目总览

- 当前系统真相：[docs/blueprint/current.md](/proj02/liuheshan/llmnode/docs/blueprint/current.md:1)
- 历史演进：[docs/blueprint/history.md](/proj02/liuheshan/llmnode/docs/blueprint/history.md:1)
- 未来规划：[docs/blueprint/roadmap.md](/proj02/liuheshan/llmnode/docs/blueprint/roadmap.md:1)
- 协作规则：[AGENTS.md](/proj02/liuheshan/llmnode/AGENTS.md:1)

## 正式入口

- 正式控制入口：`python -m llmnode.control`
- 正式运行流程：[docs/process/run.md](/proj02/liuheshan/llmnode/docs/process/run.md:1)
- 正式开发流程：[docs/process/development-workflow.md](/proj02/liuheshan/llmnode/docs/process/development-workflow.md:1)
- 正式部署边界：[docs/process/deployment.md](/proj02/liuheshan/llmnode/docs/process/deployment.md:1)
- 控制面契约：[docs/contracts/control-plane.md](/proj02/liuheshan/llmnode/docs/contracts/control-plane.md:1)
- 后端路由契约：[docs/contracts/backend-routing.md](/proj02/liuheshan/llmnode/docs/contracts/backend-routing.md:1)
- 术语表：[docs/glossary.md](/proj02/liuheshan/llmnode/docs/glossary.md:1)

## 最小启动

推荐环境：

```bash
conda activate paper2any
cd /proj02/liuheshan/llmnode
```

最小启动：

```bash
python -m llmnode.control start
```

更多运行命令、ready 判定、排障顺序和单服务调试方式统一看 [docs/process/run.md](/proj02/liuheshan/llmnode/docs/process/run.md:1)。

## 当前边界

- 当前运行真相以 `config/defaults.yaml` 中的激活 profile 为准
- 具体后端、模型目录和运行参数以 `config/backends/*.yaml` 为准
- 当前常用后端端口通常为 `15673`，如 profile 另有声明则以该 profile 为准
- 当前正式控制入口不再依赖 `scripts/*.sh`
- `docs/blueprint/roadmap.md` 是唯一未来规划入口
- `docs/knowledge/*` 是常驻参考层，不承担正式真相
- `docs/superpowers/*` 负责设计展开与实施计划，默认只服务进行中的工作，不再保留 `docs/blueprintV3.md` / `docs/blueprintV4.md`

## 阅读顺序

如果你是第一次进入这个仓库，建议按下面顺序阅读：

1. [docs/blueprint/current.md](/proj02/liuheshan/llmnode/docs/blueprint/current.md:1)
2. [docs/process/run.md](/proj02/liuheshan/llmnode/docs/process/run.md:1)
3. [docs/contracts/control-plane.md](/proj02/liuheshan/llmnode/docs/contracts/control-plane.md:1)
4. [docs/blueprint/roadmap.md](/proj02/liuheshan/llmnode/docs/blueprint/roadmap.md:1)

如果你是来继续开发，建议先看：

1. [AGENTS.md](/proj02/liuheshan/llmnode/AGENTS.md:1)
2. [docs/process/development-workflow.md](/proj02/liuheshan/llmnode/docs/process/development-workflow.md:1)
3. [docs/blueprint/current.md](/proj02/liuheshan/llmnode/docs/blueprint/current.md:1)
4. [docs/blueprint/roadmap.md](/proj02/liuheshan/llmnode/docs/blueprint/roadmap.md:1)

## 细节索引

- 控制命令、状态输出、`doctor / logs` 语义：
  [docs/contracts/control-plane.md](/proj02/liuheshan/llmnode/docs/contracts/control-plane.md:1)
- 模型路由与 `backend_type` 语义：
  [docs/contracts/backend-routing.md](/proj02/liuheshan/llmnode/docs/contracts/backend-routing.md:1)
  当前一期重构已正式拆分 `backend_type / upstream_protocol / lifecycle_mode`
  `/v1/responses` 已支持按 route 选择 `native responses`、`responses -> chat`、`responses -> messages` 三路径
- 三后端联调经验与已知问题：
  [docs/knowledge/backend_integration_qa.md](/proj02/liuheshan/llmnode/docs/knowledge/backend_integration_qa.md:1)
- 模型支持矩阵与 profile 命名：
  [docs/knowledge/model_context_performance.md](/proj02/liuheshan/llmnode/docs/knowledge/model_context_performance.md:1)
- 文档系统开发与回流规则：
  [docs/process/development-workflow.md](/proj02/liuheshan/llmnode/docs/process/development-workflow.md:1)
