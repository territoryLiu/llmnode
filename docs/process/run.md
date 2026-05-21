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
python -m llmnode.control create-admin-key
python -m llmnode.control start
```

说明：

- 当前网关不再内置默认 `dev-key`
- 首次使用前，需要先通过本地控制命令创建唯一的数据库管理员密钥
- 创建后请保存输出的明文 `sk-...` 密钥；管理台与 API 调用都依赖它
- `start` 默认使用产品态管理台：如果 `web-console/dist` 不存在，会自动执行 `npm run build`，并由 `gateway-api` 在 `/console/` 提供静态管理台
- 如果需要忽略已有 `web-console/dist` 并强制重新构建静态管理台，使用 `python -m llmnode.control start --rebuild-web-console`
- 如需 Vite 开发服务器，显式使用 `python -m llmnode.control start --web-console-mode dev`
- 产品态管理台通过右上角“管理员”入口录入或更新本地保存的 admin key，不再依赖 `runtime/data/web-console-admin.key`

## 3. 常用命令

```bash
python -m llmnode.control create-admin-key
python -m llmnode.control create-inference-key --name worker
python -m llmnode.control rotate-admin-key
python -m llmnode.control admin-key-status
python -m llmnode.control rotate-inference-key --name worker
python -m llmnode.control inference-key-status --name worker
python -m llmnode.control status
python -m llmnode.control doctor
python -m llmnode.control logs --target all --lines 20
python -m llmnode.control restart --exclude-backend
python -m llmnode.control start --rebuild-web-console
python -m llmnode.control stop
```

## 3.1 运行时目录与数据库路径

默认情况下，运行时产物根目录是仓库下的 `runtime/`，至少包括：

- `runtime/data`
- `runtime/logs`
- `runtime/run`

当前正式 SQLite 主库默认位于：

- `runtime/data/gateway.db`

如果通过环境变量覆盖运行时根目录：

```bash
export VLLM_CLAUDE_RUNTIME_DIR=/path/to/custom-runtime
```

则当前默认数据库路径也会跟着变为：

- `/path/to/custom-runtime/data/gateway.db`

补充边界：

- `VLLM_CLAUDE_DB_PATH` 优先级高于 `VLLM_CLAUDE_RUNTIME_DIR`
- 如果显式设置了 `VLLM_CLAUDE_DB_PATH`，则数据库以该路径为准
- 测试环境不应再把临时测试库写入仓库 `runtime/data/`

## 4. 默认启动对象

- `node-agent`
- 推理后端（默认 `vLLM`，可通过 `config/defaults.yaml` 的 `active_backend_profile` 切换到其他后端或模型）
- `gateway-api`
- `web-console` 静态管理台（产品态默认由 `gateway-api` 挂载到 `/console/`）

补充运行时 route 语义：

- 启动时 route seed 已改为增量同步，而不是清空重建 `model_routes`
- 当前激活 profile 只决定本地受控默认供给，不再覆盖 manual route
- profile 切换后，旧 `profile_seed` route 可能被标记为 `stale` 且自动 `disabled`
- stale route 不会自动消失，需在管理台确认是否保留或继续禁用
- 管理台模型页当前会对 `stale + profile_seed` route 直接显示治理提示和来源 profile
- `stale + profile_seed` route 当前不能直接重新启用；如需恢复，应切回来源 profile，或新建 manual route
- 管理台总览页当前会汇总 `stale / manual / profile_seed` 数量，方便先做排障前判断
- 启动 seed 的 reconcile 结果当前也会进入 `/admin/events`
  - `route_marked_stale` 表示旧 `profile_seed` route 已被标记为 stale 并自动禁用
  - `route_manual_preserved` 表示已有 manual route 在本次启动 seed 中被保留

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

- 当前常见 profile 使用 `15673`
- 如某个 profile 显式声明了其他端口，则以具体 `config/backends/*.yaml` 为准

这说明推理后端已可服务，但还不等于整个对外入口都已可用。

### 5.2 对外主链路 ready

至少满足：

- `http://127.0.0.1:4000/v1/models` 能通过网关正常返回

这说明：

- 推理后端可用
- `gateway-api` 可用
- 当前对外推理主链路已经成立

### 5.3 整栈 ready

如果本次是整栈启动，还应额外确认：

- `http://127.0.0.1:4000/console/` 可访问

因此更稳妥的理解是：

- `<host_port>` 正常（按当前后端类型确认）：后端 ready
- `4000` 正常：对外主链路 ready
- `4000/console/` 也正常：产品态整栈入口基本齐备
- `5173` 只表示显式 dev 模式下的 Vite 管理台入口正常

在此之前，即使：

- `agent` 已经存活
- `gateway` 已经监听
- `web-console` 页面已经打开

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

如果你想重启控制面但不碰当前推理后端，可以使用：

```bash
python -m llmnode.control restart --exclude-backend
```

这条命令当前会只重启：

- `node-agent`
- `gateway-api`
- `web-console` 静态入口检查或显式 dev 模式下的 Vite 进程

不会主动停止或重新拉起当前推理后端容器。

## 8. API Key 初始化

推荐初始化命令：

```bash
python -m llmnode.control create-admin-key
```

初始化后的使用边界：

- 对外 API 和管理台都只认数据库中的 API key
- 真实密钥统一为 `sk-<64hex>`
- admin key 现在是独立受控凭证：
  - 数据库内只允许存在一把
  - 名字固定为 `admin`
  - scope 固定为 `admin`
  - 不出现在普通 `/admin/keys` 列表中
- 推荐使用 `create-inference-key / rotate-inference-key / inference-key-status` 管理推理 key
- 旧 `create-api-key` 仅作为兼容入口保留，且只允许 `--scope inference`
- `web-console` 产品态通过浏览器本地保存的 `vllm-console-api-key` 向管理接口发送 `x-api-key`
