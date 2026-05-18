# 部署流程

## 0. 文档定位

这份文档只回答“当前项目支持哪些正式部署形态，以及各自边界是什么”。  
它负责：

- 当前正式支持的部署模板
- 每种模板的最小前置条件、启动方式与检查点
- 当前真实已落地行为与未来部署方向的边界

它不负责：

- 解释开发节奏，那是 `docs/process/development-workflow.md`
- 解释系统现状全貌，那是 `docs/blueprint/current.md`
- 展开三后端 Docker 方案细节，那是相关 `docs/superpowers/specs/*.md`

## 1. 当前部署总原则

当前项目的真实部署前提是：

- 正式控制入口统一为 `python -m llmnode.control`
- 当前正式运行形态仍然是单机部署
- 控制面运行在本地 Python 环境中
- 推理后端由控制面通过 Docker 拉起和管理

当前最小依赖通常包括：

- Python 环境：`/home/heshan/.conda/envs/paper2any/bin/python`
- Docker
- 已准备好的模型目录
- `config/defaults.yaml`
- `config/backends/*.yaml`
- 如果需要整栈前端界面，则还需要 `web-console` 前端依赖

## 2. 当前正式支持的部署模板

## 2.1 模板 A：本地单机整栈部署

适用场景：

- 日常本机使用
- 需要同时使用控制面、网关和前端管理台
- 需要一条最完整、最接近正式运行体验的运行路径

最小前置条件：

- 已激活 `paper2any` 环境
- Docker 可用
- 当前激活 profile 所需的目标模型目录已准备好
- `web-console` 依赖已安装

最小启动方式：

```bash
python -m llmnode.control start
```

启动后检查：

- `http://127.0.0.1:15673/v1/models` 正常，表示当前激活后端 ready
- `http://127.0.0.1:4000/v1/models` 正常，表示对外主链路 ready
- `http://127.0.0.1:5173` 可访问，表示前端入口 ready
- `python -m llmnode.control status` 能看到整栈摘要
- 后端热身窗口期内，推理请求会返回 `503 + Retry-After`，表示 Agent 已就绪但后端模型仍在加载中
- readiness 相关事件可通过 agent 事件流读取，至少包括 `stream_not_ready` 和恢复后的 `backend_recovered`
- 管理台密钥页面通过 `/admin/overview/readiness` 获取 Base URL（本地地址 / 局域网地址），供客户端复制使用

它不适用于：

- 只想调试控制面或网关，不想拉起前端
- 前端依赖未安装的环境
- 想把 route 管理能力误当成完整模型注册中心的场景

## 2.2 模板 B：本地后端 / 控制面优先部署

适用场景：

- 调试 `node-agent`、`gateway-api` 和当前激活后端这条主链路
- 暂时不依赖 `web-console`
- 需要分服务排障或逐段验证启动问题

最小前置条件：

- 已激活 `paper2any` 环境
- Docker 可用
- 模型目录已准备好
- 不要求前端 ready

最小启动方式：

```bash
python -m llmnode.control start --service agent --daemon
python -m llmnode.control start --service vllm --daemon
python -m llmnode.control start --service gateway --daemon
```

启动后检查：

- `python -m llmnode.control doctor`
- `python -m llmnode.control status`
- `http://127.0.0.1:15673/v1/models`
- `http://127.0.0.1:4000/v1/models`

它不适用于：

- 需要管理台交互配置的场景
- 需要验证整栈体验的场景
- 需要把“网关可用”误判为“整个整栈都 ready”的场景

## 2.3 模板 C：单机三后端 Docker 化部署

适用场景：

- 需要在单机上切换或验证 `vLLM / llama.cpp / SGLang`
- 为三后端统一控制面做部署与排障
- 讨论 Python 控制面如何与多个官方 Docker 后端交互

当前方向：

- 三个后端分别使用各自官方 Docker 镜像或官方容器方案
- Python 控制面负责容器启停、状态读取、健康检查、日志与路由治理
- 当前目标仍然是单机三后端 Docker 化，不是多节点编排

当前边界：

- 三后端代码、控制面和联调验证已落地
- 当前仍应把它理解为“单机切换 / 单机治理”能力，而不是多后端同时编排平台
- 当前不应把三后端支持误写成“多节点或 K8s 级平台能力”

它不适用于：

- 把 roadmap 直接当成交付现状
- 假设系统已经具备多后端切换与统一健康检查能力
- 假设当前已经有 K8s 或多机部署方案

## 3. 当前部署边界

当前明确不负责：

- 模型自动下载
- 多节点编排
- K8s 部署体系
- 自动格式转换流水线
- 云上集群治理

用户仍需自行负责：

- 准备模型目录
- 准备本机 Python 与 Docker 环境
- 按模板选择是否安装并启用前端依赖

## 4. 部署形态变化后的回流要求

如果部署形态、启动对象或正式边界发生变化，至少要同步检查：

- 本文
- `docs/process/run.md`
- `docs/contracts/control-plane.md`
- `docs/blueprint/current.md`

如果变化已经影响项目总入口、最小启动方式或文档阅读顺序，再额外同步 `README.md`。
