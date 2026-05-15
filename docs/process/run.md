# 运行流程

## 0. 文档定位

这份文档只回答“怎么运行这个项目”。  
它负责：

- 最小启动方式
- 常用运行命令
- ready 判断
- 排障前的基本顺序

它不负责：

- 解释当前系统全貌，那是 `docs/blueprint/current.md`
- 解释未来规划，那是 `docs/blueprint/roadmap.md`
- 解释开发节奏，那是 `docs/process/development-workflow.md`

## 1. 推荐环境

```bash
conda activate paper2any
cd /proj02/liuheshan/llmnode
```

## 2. 最小启动

```bash
python -m llmnode.control create-api-key --name console-admin --scope admin
python -m llmnode.control start
```

说明：

- 当前网关不再内置默认 `dev-key`
- 首次使用前，需要先通过本地控制命令创建至少一把数据库管理员密钥
- 创建后请保存输出的明文 `sk-...` 密钥；管理台与 API 调用都依赖它

## 3. 常用命令

```bash
python -m llmnode.control create-api-key --name console-admin --scope admin
python -m llmnode.control status
python -m llmnode.control doctor
python -m llmnode.control logs --target all --lines 20
python -m llmnode.control stop
```

## 4. 默认启动对象

- `node-agent`
- 推理后端（默认 `vLLM`，可通过 `config/defaults.yaml` 的 `active_backend_profile` 切换到其他后端或模型）
- `gateway-api`
- `web-console`

## 5. ready 判定

不要把”某个进程活着”直接等同于”系统 ready”。  
当前更稳妥的判断应拆成三层：

### 5.0 Agent Readiness 状态语义

`node-agent` 通过双阶段探针判定后端就绪状态：

1. **HTTP 健康检查**：确认后端端口可达
2. **推理探针**：发送 `max_tokens=1` 的极小推理请求确认模型可服务

状态标志：
- `http_ready=true` 但 `inference_ready=false` 表示后端仍在热身（`warming_up`）
- `http_ready=true` 且 `inference_ready=true` 表示后端完全就绪（`ready`）
- `http_ready=false` 表示后端不可达（`degraded` / `stopped`）

客户端对接：
- 对外业务请求在未就绪时应返回 `503 Service Unavailable`
- 响应头携带 `Retry-After` 字段指示重试等待秒数
- `detail` 字段枚举值：
  - `backend_warming_up`：HTTP 可达但推理未就绪
  - `backend_not_ready`：后端 HTTP 不可达
  - `agent_state_unavailable`：agent 状态获取失败
  - `agent_not_ready`：agent 状态非 ready
- 事件面至少可观察到：
  - `stream_not_ready`：HTTP 已通，但推理探针仍未通过
  - `backend_recovered`：从 `warming_up / degraded / recovering` 恢复到 `ready`

### 5.1 推理后端 ready

至少满足：

- `http://127.0.0.1:<host_port>/v1/models` 返回正常

其中 `<host_port>` 由当前激活后端决定：

- 当前正式默认 profile：`15673`
- 其他 profile 也建议统一使用 `15673`，如需例外以具体 `config/backends/*.yaml` 为准

这说明推理后端已可服务，但还不等于整个对外入口都已可用。

### 5.2 对外主链路 ready

至少满足：

- `http://127.0.0.1:4000/v1/models` 能通过网关正常返回

这说明：

- 推理后端可用
- `gateway-api` 可用
- 当前对外推理主链路已经成立

### 5.3 默认整栈 ready

如果本次是默认整栈启动，还应额外确认：

- `web-console` 可访问

因此更稳妥的理解是：

- `<host_port>` 正常（按当前后端类型确认）：后端 ready
- `4000` 正常：对外主链路 ready
- `5173` 也正常：默认整栈入口基本齐备

在此之前，即使：

- `agent` 已经存活
- `gateway` 已经监听
- `web-console` 已经打开

系统仍可能处于 warmup 或 partial。

## 6. 推荐排障顺序

如果启动异常，建议按下面顺序排：

1. `python -m llmnode.control doctor`
2. `python -m llmnode.control status`
3. `python -m llmnode.control logs --target all --lines 50`

## 7. 单服务调试

如果不想拉整栈，也可以单独控制：

```bash
python -m llmnode.control start --service gateway --daemon
python -m llmnode.control start --service agent --daemon
python -m llmnode.control start --service vllm --daemon
python -m llmnode.control stop --service gateway
python -m llmnode.control stop --service agent
python -m llmnode.control stop --service vllm
```

## 8. API Key 初始化

推荐初始化命令：

```bash
python -m llmnode.control create-api-key --name console-admin --scope admin
```

如果同时需要让这把 key 调用推理接口，可以加上：

```bash
python -m llmnode.control create-api-key --name console-admin --scope admin --scope inference
```

初始化后的使用边界：

- 对外 API 和管理台都只认数据库中的 API key
- 真实密钥统一为 `sk-<64hex>`
- `web-console` 顶部可手工输入并保存这把 `sk-...` 密钥
