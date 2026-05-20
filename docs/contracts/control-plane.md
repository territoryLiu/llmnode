# 控制面契约

## 0. 文档定位

这份文档只定义 `python -m llmnode.control` 这套正式控制入口应稳定提供什么。  
它回答的是：

1. 正式控制面有哪些命令。
2. 每类命令至少应输出什么信息。
3. 单服务控制和整栈控制的边界是什么。
4. 什么属于正式行为，什么只是当前实现细节。

它不负责：

- 描述当前系统整体状态，那是 `docs/blueprint/current.md`
- 描述未来多后端规划，那是 `docs/blueprint/roadmap.md`
- 展开具体实现代码结构，那是相关 `spec / plan`

## 1. 正式入口

正式入口统一为：

```bash
python -m llmnode.control <action>
```

当前控制面不再依赖 shell 脚本层。

## 2. 命令集合

控制面当前正式命令包括：

- `start`
- `stop`
- `restart`
- `status`
- `env`
- `doctor`
- `logs`
- `create-api-key`

如果后续新增命令，应同步更新：

- 本文
- `docs/process/run.md`
- `docs/blueprint/current.md`
- 相关测试

只有当控制面的最小启动方式、总入口或关键边界发生变化时，才需要同步更新 `README.md`。

## 3. 总体输出要求

- 输出优先服务终端直接阅读
- 结构应以标题块和摘要块为主
- 关键状态不应只藏在日志里
- 同一类信息应尽量稳定出现在同一段落
- 诊断输出应优先帮助定位“下一步该做什么”

## 4. `start`

### 职责
- 启动正式整栈运行路径

### 默认目标
- `node-agent`
- 推理后端
- `gateway-api`
- `web-console`

### 输出要求
- 显示启动阶段
- 显示关键地址
- 显示关键日志路径
- 启动失败时应能给出错误信息和清理行为

## 5. `stop`

### 职责
- 有序停止整栈

### 输出要求
- 显示停止阶段
- 显示各组件停止结果
- 最后给出整栈停止摘要

## 6. `restart`

### 职责
- 对整栈执行 stop + start
- 支持在显式声明时只重启控制面，不触碰当前推理后端

### 输出要求
- 保留完整阶段输出
- 明确告诉用户当前执行的是重启路径

### 当前扩展参数

```bash
python -m llmnode.control restart --exclude-backend
```

语义：

- 只重启 `node-agent`、`gateway-api`、`web-console`
- 不主动停止当前推理后端容器
- 适用于“刷新控制面 / 网关 / 前端状态，但尽量不打断已加载模型”的场景

## 7. `status`

### 职责
- 输出当前控制面视角下的运行状态摘要

### 必须提供
- 当前项目路径
- 当前 Python 环境
- 当前后端类型（vllm / llama.cpp / sglang）
- 关键 HTTP 健康状态
- 关键进程摘要
- 容器详细信息（名称、镜像、状态、运行时长、重启次数）
- 推理参数（根据 backend_type 动态展示）
- 总结态：
  - `stopped` - 所有服务都不可达
  - `starting` - agent 可达，但 backend 容器不存在
  - `warming` - agent 可达，backend 容器运行中，但 HTTP 不可达（模型加载中）
  - `partial` - 部分服务可达，但不是全部
  - `ready` - 所有服务可达
  - `degraded` - 所有服务可达，但有警告（如容器重启次数 > 0）

## 8. `env`

### 职责
- 输出当前运行环境和关键路径

### 必须提供
- 项目路径
- Python 解释器
- runtime/log/run 目录
- 模型目录
- 关键服务 URL
- 前端目录

## 9. `doctor`

### 职责
- 提供系统级体检与建议动作

### 必须提供
- Python / Docker / npm / `ss` 可用性
- 模型目录与前端目录检查
- GPU 信息（GPU 数量、型号、显存、利用率、CUDA 版本）
- 模型格式检测（HuggingFace / GGUF / unknown）
- 模型配置解析（model_type / num_hidden_layers / hidden_size）
- 端口检查
- HTTP 健康检查
- 运行产物检查
- Docker 容器 / 镜像检查
- 容器详细诊断（状态、重启次数、资源限制、最近日志）
- 三后端特定检查（根据 backend_type 动态调整）
- 智能建议（识别常见错误模式，给出可执行命令）

### 输出目标
- 用户不需要再自己把检查结果翻译成命令
- 应尽量直接告诉用户下一步最值得执行什么
- 使用视觉符号（✓/✗/⚠/ℹ）提升可读性

### 诊断 API 家族
- Agent 诊断 API 当前至少包括：
  - `GET /admin/diagnostics/gpu`
  - `GET /admin/diagnostics/container`
  - `GET /admin/diagnostics/model`
  - `GET /admin/diagnostics/metrics`
  - `GET /admin/diagnostics/suggestions`
  - `GET /admin/diagnostics/status`
- 其中 `metrics` 负责暴露基础性能指标聚合，不改变 `doctor` 命令面向终端的正式输出职责
- `GET /admin/diagnostics/status` 和 `GET /state` 的 readiness 响应字段：
  - `http_ready`: HTTP 健康检查是否通过
  - `inference_ready`: 推理探针是否通过
  - `retry_after_seconds`: 建议客户端重试等待秒数
  - `readiness_state`: 当前 readiness 状态（`stopped / starting / warming_up / ready / degraded / recovering / alerting`）
  - `last_probe_error`: 最近一次探针失败原因
  - `last_probe_latency_ms`: 最近一次探针延迟（毫秒）
  - `last_transition_at`: 上次状态切换时间
- `GET /events` 返回的 agent readiness 事件至少包含：
  - `event_type`: 结构化事件名，例如 `stream_not_ready / backend_ready / backend_recovered / backend_error`
  - `readiness_state`: 该事件对应的 readiness 状态
  - `http_ready` / `inference_ready`: 事件发生时的布尔快照
  - `metadata`: 附加探针信息，如 `last_probe_error`、`last_probe_latency_ms`、`retry_after_seconds`

### 三后端特定检查
- **vLLM**: GPU 可用性、显存容量、模型格式（HuggingFace）、镜像版本
- **llama.cpp**: 镜像类型（full-cuda）、模型文件存在性、模型格式（GGUF）、n_gpu_layers 合理性
- **SGLang**: reasoning_parser 参数、tp_size 与 GPU 数量匹配、镜像版本

## 10. `logs`

### 职责
- 提供统一日志查看入口

### 支持目标
- `agent`
- `gateway`
- `web-console`
- `vllm`（固定别名，指向当前激活的推理后端日志，不论实际 `backend_type` 是 `vllm / llama.cpp / sglang`）
- `backend`（通用别名，根据实际 backend_type 自动映射）
- `all`

### 必须提供
- 日志目标
- 日志文件路径
- 最近若干行内容

### 增强功能
- `--follow` / `-f`: 实时跟踪日志（类似 tail -f）
- `--grep <pattern>`: 按关键词或正则表达式过滤日志行
- `--ignore-case` / `-i`: 忽略大小写搜索
- `--no-highlight`: 禁用错误高亮
- 错误高亮：自动识别并高亮 ERROR/WARN/INFO 关键词（红色/黄色/绿色）

### 当前原则
- 默认更适合”快速定位和预览”
- 支持实时跟踪用于调试场景
- 不是长时间驻留式日志查看器

## 11. 单服务控制

当前控制面应支持单服务控制：

```bash
python -m llmnode.control start --service gateway --daemon
python -m llmnode.control start --service agent --daemon
python -m llmnode.control start --service vllm --daemon
python -m llmnode.control stop --service gateway
python -m llmnode.control stop --service agent
python -m llmnode.control stop --service vllm
```

当前边界：

- `gateway / agent` 支持前台与后台运行
- `vllm` 当前更偏 daemon 风格

## 12. `create-api-key`

### 职责
- 在本地 SQLite 账本中创建正式 API key
- 为首把管理员密钥初始化提供无 bootstrap 后门的正式入口

### 典型用法

```bash
python -m llmnode.control create-api-key --name console-admin --scope admin
python -m llmnode.control create-api-key --name hybrid --scope admin --scope inference
```

### 输出要求
- 显示创建结果标题
- 显示 key id / name / status / scopes
- 显示数据库路径
- 显示一次性明文密钥

### 当前边界
- 真实密钥格式统一为 `sk-<64hex>`
- 未创建数据库密钥前，网关不应再接受默认 `dev-key` 或其他 bootstrap key
- 该命令是首把管理员密钥的正式初始化路径

## 13. 命令变更后的回流要求

如果控制面发生变化，至少要检查是否同步更新：

- 本文
- `docs/process/run.md`
- `docs/blueprint/current.md`
- `tests/test_control.py`

如果变化已经影响项目总入口、最小启动方式或关键边界，再额外同步 `README.md`。
