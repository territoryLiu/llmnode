# 性能实验室与自动化矩阵设计

## 1. 背景

当前仓库已经具备基础 benchmark 能力：

- `scripts/benchmark_backend.py` 可对指定 token 长度执行单并发阶梯测试。
- `llmnode/perf/benchmark.py` 已能记录服务端 `usage.prompt_tokens / completion_tokens / total_tokens`。
- benchmark 已支持请求期间连续采样，结果落盘到 `runtime/benchmarks/<run_id>/`。
- 控制面已修复运行中容器 spec 漂移问题，启动时会按当前 profile 校验容器参数。

这些能力仍不足以支撑系统化性能验证。当前性能测试主要依赖人工切 profile、人工 stop/start、人工读日志、人工整理文档，容易出现配置漂移、token 口径混乱、失败样本丢失和结果不可复现的问题。

## 2. 目标

本设计目标是增加一个“性能实验室”完整闭环：

1. 通过管理 API 创建性能测试任务。
2. 支持按 profile 和参数矩阵自动执行多组配置。
3. 每组配置执行 `stop -> start -> healthcheck -> 启动日志解析 -> benchmark -> 连续采样 -> summary`。
4. 启动失败、请求失败、超时和取消都生成结构化结果。
5. 管理台提供“性能实验室”页面，用于配置测试、观察进度、查看历史和比较结果。

本轮不做多节点调度、K8s 编排、模型下载、成本估算或推荐系统式自动调参。

## 3. 用户场景

### 3.1 单模型长上下文验证

操作者选择 `vllm_qwen36-27b-nvfp4`，配置：

- `targets = [4096, 32768, 65536, 131072, 176128, 262000]`
- `max_tokens = 64`
- `gpu_memory_utilization = [0.5, 0.55, 0.6]`
- `max_model_len = [262144]`

系统自动跑完矩阵，并明确展示哪些配置无法启动、哪些配置能跑通 `256K`、各长度速度和峰值显存。

### 3.2 参数余量比较

操作者比较同一模型在 `gpu_memory_utilization=0.55` 和 `0.6` 下的：

- 权重显存
- 可用 KV 显存
- vLLM maximum concurrency
- 端到端时延
- `completion tok/s`
- 峰值 GPU / KV usage

### 3.3 模型横向比较

操作者比较 AWQ、NVFP4、FP8 等 profile 在相同 token 长度下的速度与显存占用。前端只展示实测结果，不根据 `GPU KV cache size tokens` 线性推导最大上下文。

## 4. 非目标

- 不做分布式 worker。
- 不允许多个性能任务同时抢占同一张 GPU。
- 不把性能实验室接入普通推理 API。
- 不把本地 tokenizer 估算当作最终 token 结论。
- 不通过前端直接操作 Docker，所有生命周期动作必须经过控制面。
- 不把长上下文实测命令纳入普通 CI。

## 5. 后端架构

### 5.1 API

新增管理 API：

- `POST /admin/perf/runs`
  - 创建性能测试任务。
  - 返回 `run_id`、初始状态和结果路径摘要。
- `GET /admin/perf/runs`
  - 返回历史任务列表，默认按创建时间倒序。
- `GET /admin/perf/runs/{run_id}`
  - 返回任务 summary、矩阵点状态和聚合指标。
- `GET /admin/perf/runs/{run_id}/samples`
  - 返回采样曲线，可按矩阵点过滤。
- `POST /admin/perf/runs/{run_id}/cancel`
  - 请求取消运行中的任务。

这些接口沿用现有 admin 鉴权，不新增新的认证机制。

### 5.2 任务模型

任务状态：

- `queued`
- `running`
- `completed`
- `completed_with_errors`
- `failed`
- `cancel_requested`
- `cancelled`

矩阵点状态：

- `pending`
- `starting`
- `startup_failed`
- `healthy`
- `benchmarking`
- `benchmark_failed`
- `completed`
- `cancelled`

同一时间只允许一个性能任务处于 `queued / running / cancel_requested`。如果已有任务未结束，新建任务返回 `409`。

### 5.3 请求参数

`POST /admin/perf/runs` 请求体包含：

- `profile`: 当前后端 profile 名称。
- `targets`: prompt token 目标列表。
- `max_tokens`: 输出 token 上限。
- `warmup_runs`: 预热轮数。
- `measure_runs`: 统计轮数。
- `sample_interval`: 采样间隔。
- `concurrency`: 并发请求数，默认 `1`。
- `restart_backend`: 是否自动重启后端，默认 `true`。
- `matrix`: 参数矩阵。

`matrix` 当前支持：

- `gpu_memory_utilization`
- `max_model_len`
- `max_num_seqs`

矩阵展开后，每个点都会生成独立结果。未指定 `matrix` 时，只测试当前 profile 的现有参数。

### 5.4 执行流

每个矩阵点按顺序执行：

1. 解析 profile。
2. 应用参数覆盖。
3. 如果 `restart_backend=true`，调用控制面停止当前后端。
4. 启动后端。
5. 轮询 `/v1/models` 做健康检查。
6. 抓取并解析启动日志。
7. 如果启动失败，写入 `startup.json / errors.json`，进入下一个矩阵点。
8. 如果健康检查通过，执行 benchmark。
9. 写入 `summary.json / samples.jsonl`。
10. 汇总矩阵点结果。

取消请求只在安全检查点生效：

- 矩阵点之间。
- 健康检查轮询期间。
- benchmark 单次请求结束后。

不强杀正在进行的 HTTP 长请求，避免留下难以归因的半状态。需要强制中断时由操作者使用正式控制入口停止服务。

### 5.5 结果目录

每个任务目录：

```text
runtime/benchmarks/<run_id>/
  run.json
  matrix.json
  summary.json
  points/
    <point_id>/
      startup.json
      summary.json
      samples.jsonl
      errors.json
```

字段原则：

- `run.json` 保存用户请求、任务状态、创建时间、完成时间。
- `matrix.json` 保存展开后的参数点。
- 根级 `summary.json` 保存跨矩阵汇总。
- 点级 `startup.json` 保存 vLLM 启动日志解析结果。
- 点级 `summary.json` 保存 benchmark 结果。
- 点级 `samples.jsonl` 保存连续 GPU / backend runtime 采样。
- 点级 `errors.json` 保存启动失败、请求失败、超时和解析失败。

## 6. 启动失败解析

vLLM 启动日志至少解析：

- `Model loading took ... GiB memory`
- `Available KV cache memory: ... GiB`
- `GPU KV cache size: ... tokens`
- `Maximum concurrency for ... tokens per request: ...x`
- KV 不足错误中的 required / available / suggested max model len
- OOM / CUDA out of memory
- 端口占用
- 模型路径不存在或配置加载失败

解析结果只作为启动与容量诊断，不直接外推最大 prompt tokens。

## 7. benchmark 口径

正式结果以服务端返回为准：

- `usage.prompt_tokens`
- `usage.completion_tokens`
- `usage.total_tokens`
- `finish_reason`
- HTTP 状态码
- 错误消息

本地 tokenizer 只用于构造目标 prompt。结果中保留：

- `target_prompt_tokens`
- `actual_prompt_tokens`
- `prompt_tokens`
- `prompt_token_mismatch`

如果本地 tokenizer 与服务端 usage 不一致，文档和前端必须突出显示，而不是静默覆盖。

## 8. 前端设计

新增页面：`性能实验室`。

页面区域：

- 配置区：
  - profile
  - targets
  - max_tokens
  - warmup / measure
  - sample_interval
  - concurrency
  - restart_backend
  - matrix 参数
- 运行区：
  - 当前任务状态
  - 当前矩阵点
  - 健康检查状态
  - 取消按钮
- 结果区：
  - 启动显存
  - 可用 KV 显存
  - maximum concurrency
  - 服务端 prompt tokens
  - completion tok/s
  - 端到端时延
  - 峰值 GPU 显存
  - 峰值 KV usage
- 历史区：
  - 历史任务列表
  - 同模型不同配置对比
  - 不同 profile 横向对比

前端不做 Docker 操作，也不根据 KV token 容量自行推导最大上下文。

## 9. 存储与并发

本轮使用文件系统落盘，不新增数据库表。原因：

- benchmark 结果较大，`samples.jsonl` 更适合文件。
- 当前主要目标是单机实验，不需要复杂查询。
- 后续如果需要跨任务聚合排行榜，再考虑把 summary 索引写入 SQLite。

任务状态以内存 + 文件双写为准：

- API 进程内维护当前任务状态。
- 每次状态变更同步写入 `run.json`。
- 服务重启后，可以从 `runtime/benchmarks` 读取历史任务，但未完成任务标记为 `failed` 或 `interrupted`。

## 10. 错误处理

- 新建任务时已有任务运行：返回 `409`。
- profile 不存在：返回 `400`。
- 参数矩阵为空或值非法：返回 `400`。
- 后端启动失败：矩阵点标记 `startup_failed`，任务可继续执行后续点。
- benchmark 请求超时：矩阵点标记 `benchmark_failed`，保留 timeout 错误。
- 采样失败：不终止任务，写入 sample 的 `backend_metrics.sample_error`。
- 取消任务：安全检查点生效，最终状态为 `cancelled`。

## 11. 测试计划

单元测试：

- 矩阵展开。
- 请求参数校验。
- 启动日志解析。
- 任务状态流转。
- summary 聚合。
- 取消状态处理。

API 测试：

- 创建任务成功。
- 重复创建返回 `409`。
- 查询历史列表。
- 查询任务详情。
- 查询 samples。
- 取消任务。

前端测试：

- 性能实验室页面渲染。
- 表单提交。
- 任务状态展示。
- 历史结果展示。
- 错误信息展示。

手动 GPU 验收：

- NVFP4 `0.55 / 262144` 单点跑通。
- `0.5 / 262144` 启动失败可结构化记录。
- `0.6 / 262144` 单点跑通。
- `samples.jsonl` 包含请求期间连续采样。

## 12. 实施顺序

1. 后端结果模型与矩阵展开模块。
2. performance run 文件存储。
3. 后台任务 runner。
4. 管理 API。
5. vLLM 启动失败解析增强。
6. benchmark 并发能力。
7. 前端性能实验室页面。
8. 文档回流到 `current / process / knowledge`。

## 13. 风险与约束

- 长上下文请求可能运行数分钟，API 必须异步返回任务状态，不能阻塞前端。
- 自动重启会影响当前推理服务，前端必须明确提示。
- 同机 GPU 资源不可并发抢占，默认只允许一个性能任务。
- 参数覆盖必须通过 profile 派生，不应直接修改仓库配置文件。
- 测试结果不能跨机器泛化，文档必须明确“当前机器实测”。
