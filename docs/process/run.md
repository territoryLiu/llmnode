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
python -m llmnode.control start
```

## 3. 常用命令

```bash
python -m llmnode.control status
python -m llmnode.control doctor
python -m llmnode.control logs --target all --lines 20
python -m llmnode.control stop
```

## 4. 默认启动对象

- `node-agent`
- 推理后端（默认 `vLLM`，可通过 `config/defaults.yaml` 的 `vllm.backend_type` 字段切换为 `llama.cpp` 或 `sglang`）
- `gateway-api`
- `web-console`

## 5. ready 判定

不要把”某个进程活着”直接等同于”系统 ready”。  
当前更稳妥的判断应拆成三层：

### 5.1 推理后端 ready

至少满足：

- `http://127.0.0.1:<host_port>/v1/models` 返回正常

其中 `<host_port>` 由当前激活后端决定：

- `vLLM`：默认 `8000`
- `llama.cpp`：默认 `8080`
- `sglang`：默认 `30000`

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
