# 长上下文压测采集与 Gateway 超时修复设计

## 0. 文档定位

这份设计文档服务于 `llmnode` 当前两项直接相关的工程收口工作：

1. 修复 `gateway` 在长上下文非流式请求上的上游固定超时
2. 建立一套面向 `vLLM / llama.cpp / SGLang` 三后端的结构化压测与资源采集能力

它回答的是：

- 当前 `256K` 经 `gateway` 失败的根因是什么
- 应该如何修复这个超时边界，而不是继续依赖魔法数字
- 一套长期可复用的后端直连压测工具应该采哪些指标
- 三后端在指标采集上的统一层与差异层怎么拆
- 原始数据应该如何落盘，后续如何回流到 `docs/knowledge/model_context_performance.md`

它不负责：

- 直接替代 `docs/knowledge/model_context_performance.md` 成为长期知识记录
- 定义多机、多节点或 K8s 场景下的基准平台
- 展开逐任务实施清单，那应进入 `docs/superpowers/plans/*.md`

## 1. 背景与问题定义

当前仓库已经有 `docs/knowledge/model_context_performance.md` 作为长上下文与单并发性能记录层，但实际执行仍依赖临时命令和人工整理，存在三类问题。

### 1.1 gateway 对长非流式请求的上游超时过短

当前 `llmnode/proxy/backend.py` 中 `post_json()` 固定使用：

- `httpx.AsyncClient(base_url=self.base_url, timeout=120)`

这在短请求和中等上下文下没有问题，但对长上下文单条请求已经形成实际故障边界。

本次已确认的真实现象是：

- `models/Qwen/Qwen3.6-27B-FP8`
- 直连 `vLLM` 的 `262000 prompt tokens + max_tokens=64`
- 完整请求时延约 `199282 ms`
- 经 `gateway` 在约 `120067 ms` 返回 `500`
- `runtime/logs/gateway.log` 中可见根因是 `httpcore.ReadTimeout`

因此，这不是模型失败，也不是后端挂掉，而是网关先于后端结果返回之前超时。

### 1.2 当前压测流程不可复用

现有性能记录能形成文档，但过程依赖：

- 手工构造 prompt
- 临时 Python 命令发请求
- 人工读取容器日志
- 手工从 `nvidia-smi` 和日志里拼显存与 KV cache 信息

这带来的问题是：

- 同一个模型下次复测很难完全复现
- 三后端结果口径难统一
- 很难保留原始证据层
- 文档与原始数据之间没有稳定映射

### 1.3 资源采集还缺少正式结构

当前最缺的不是“再多跑几次”，而是把原始指标正式落下来，至少应能稳定回答：

- 每个阶梯请求的 prompt/completion/时延/tok/s 是多少
- 当前后端自己吃了多少显存
- 非当前后端进程又吃了多少显存
- `vLLM` 的 KV cache 使用率与启动期容量是多少
- `llama.cpp / SGLang` 在缺少统一 KV 百分比口径时，本轮到底采到了什么，缺了什么

## 2. 设计目标

第一版设计目标限定为“单机三后端直连压测的结构化证据层 + gateway 长请求超时修复”：

- 修掉 `gateway` 对长非流式请求的固定 `120s` 上游超时
- 建立一套可重复执行的 benchmark 工具
- 主产物是结构化原始数据，而不是直接写文档
- 同时支持：
  - `vLLM`
  - `llama.cpp`
  - `SGLang`
- 统一采集：
  - 每个阶梯请求结果
  - GPU 总显存
  - 当前后端进程显存
  - 非当前后端进程显存汇总与明细
  - 后端可获得的 KV cache / throughput 指标

## 3. 设计范围

### 3.1 包含

- `gateway` 非流式上游 timeout 的可配置化
- 长请求默认 timeout 的上调
- 直连后端 benchmark 入口
- 目标 token prompt 构造
- benchmark 运行期间的周期采样
- 三后端日志与运行信息解析
- 结构化输出：
  - `summary.json`
  - `samples.jsonl`
- 至少一组 `vLLM` 真实命令级验证

### 3.2 不包含

- 默认 benchmark `gateway`
- 自动回写 `docs/knowledge/model_context_performance.md`
- 前端管理台可视化
- 多并发压测平台
- CPU / RAM / 磁盘监控
- Prometheus / Grafana 集成
- 成本估算

## 4. 方案选择

本次采用“库层 + 薄脚本入口”方案。

### 4.1 备选方案

- 方案 A：纯独立脚本
- 方案 B：直接做成 `llmnode.control` 正式子命令
- 方案 C：库层 + 薄脚本入口

### 4.2 选择理由

如果走纯独立脚本，首版落地会很快，但后续：

- timeout 修复逻辑
- benchmark 逻辑
- 三后端日志解析
- GPU 显存归类

都会散在脚本中，不利于复用和测试。

如果直接做成 `llmnode.control` 正式子命令，虽然最符合长期入口统一方向，但这轮工作会被：

- CLI 契约设计
- 控制面状态输出风格
- 子命令参数兼容

额外放大，拖慢交付。

因此第一版更合适的结构是：

- 采集能力放进 `llmnode` 包内，形成可测试的库层
- 用一个薄脚本直接触发 benchmark
- 后续如果需要升级为 `python -m llmnode.control benchmark`，可以直接复用同一套库逻辑

## 5. 正式对象模型

本设计定义 4 个正式对象：

1. `BenchmarkRun`
2. `BenchmarkStepResult`
3. `SamplePoint`
4. `GpuProcessBreakdown`

### 5.1 BenchmarkRun

代表一次完整 benchmark run。

至少包含：

- `run_id`
- `started_at`
- `finished_at`
- `active_backend_profile`
- `backend_type`
- `model_name`
- `model_dir`
- `container_name`
- `endpoint`
- `max_tokens`
- `targets`
- `status`
- `errors`

### 5.2 BenchmarkStepResult

代表单个阶梯的汇总结果。

至少包含：

- `label`
- `target_prompt_tokens`
- `actual_prompt_tokens`
- `completion_tokens`
- `latency_ms`
- `completion_tokens_per_second`
- `http_status`
- `result`
- `backend_metrics`

其中：

- `result` 只表达 `success / timeout / error`
- 不把未知字段伪装成 `0`

### 5.3 SamplePoint

代表 benchmark 过程中的一次周期采样。

至少包含：

- `ts`
- `active_step`
- `gpu_total_used_mb`
- `backend_process_used_mb`
- `other_processes_total_mb`
- `other_processes`
- `kv_cache_usage_percent`
- `prompt_throughput_tokens_per_s`
- `generation_throughput_tokens_per_s`

说明：

- `kv_cache_usage_percent` 对 `llama.cpp / SGLang` 允许为 `null`
- 没拿到就明确记 `null/unknown`，不做伪造估算

### 5.4 GpuProcessBreakdown

代表本轮 GPU 显存归因。

至少包含：

- `backend_processes`
- `backend_process_used_mb`
- `other_processes_total_mb`
- `other_processes`

每条 `other_processes` 至少记录：

- `pid`
- `process_name`
- `used_memory_mb`

## 6. 组件边界

### 6.1 llmnode/perf/benchmark.py

负责 benchmark 主流程编排：

- 读取 profile
- 预检查
- 串行执行各阶梯请求
- 启停采样
- 汇总结果
- 写出结构化文件

它不负责：

- 直接解析所有后端日志细节
- 直接调用 `nvidia-smi` 文本解析细节

### 6.2 llmnode/perf/prompt_builder.py

负责构造接近目标 token 数的 prompt。

它负责：

- 加载 tokenizer
- 生成 `4K / 32K / 64K / 128K / 256K` 等目标 prompt
- 返回实际 prompt token 数

它不负责：

- 发请求
- 记录性能指标

### 6.3 llmnode/perf/probe_gpu.py

负责 GPU 显存采样。

它负责：

- 调用 `nvidia-smi`
- 获取 GPU 总显存使用
- 获取 GPU 进程列表
- 归类“当前后端进程”与“其他进程”

它不负责：

- 解析后端日志
- 推断 KV cache 百分比

### 6.4 llmnode/perf/probe_backend.py

负责后端特定指标解析。

它负责：

- `vLLM`：
  - 启动日志中的 `Available KV cache memory`
  - `GPU KV cache size`
  - `Maximum concurrency ...`
  - 运行日志中的 `GPU KV cache usage`
  - `Avg prompt throughput`
  - `Avg generation throughput`
- `llama.cpp`：
  - `n_ctx`
  - `n_ctx_seq`
  - 其他可稳定识别的上下文/吞吐信息
- `SGLang`：
  - `KV Cache is allocated. #tokens`
  - 其他可稳定识别的 cache/throughput 信息

它不负责：

- 伪造统一的 KV cache 百分比口径

### 6.5 scripts/benchmark_backend.py

这是第一版对用户可直接执行的薄入口。

它负责：

- 解析 CLI 参数
- 调用 benchmark 库层
- 指定输出目录

它不负责：

- 承担复杂业务逻辑

## 7. 数据流与执行流程

### 7.1 benchmark 执行顺序

一次 run 的默认执行顺序：

1. 读取当前激活 profile
2. 解析：
   - `backend_type`
   - `model_name`
   - `host_port`
   - `container_name`
   - `model_dir`
3. 执行预检查：
   - 后端 `/v1/models` 可达
   - 容器存在且运行
   - `nvidia-smi` 可用
   - tokenizer 可加载
4. 对每个阶梯串行执行：
   - 构造 prompt
   - 启动采样
   - 发起单条非流式请求
   - 结束采样
   - 汇总该阶梯结果
5. 输出：
   - `summary.json`
   - `samples.jsonl`

### 7.2 输出目录

建议输出到：

- `runtime/data/benchmarks/<timestamp>-<profile>/summary.json`
- `runtime/data/benchmarks/<timestamp>-<profile>/samples.jsonl`

### 7.3 summary.json 结构

至少包含：

- `run_meta`
- `environment`
- `steps`
- `kv_cache_summary`
- `backend_memory_summary`
- `other_gpu_processes_summary`
- `errors`

### 7.4 samples.jsonl 结构

每行是一条 `SamplePoint`。

用途是：

- 保留证据层
- 便于后续二次生成 Markdown / 图表
- 允许人工复盘长请求期间资源变化

## 8. 三后端适配策略

### 8.1 vLLM

这是第一版指标最完整的后端。

可稳定采集：

- 响应 `usage`
- 启动期：
  - `Available KV cache memory`
  - `GPU KV cache size`
  - `Maximum concurrency for ... tokens per request`
- 运行期：
  - `GPU KV cache usage`
  - `Avg prompt throughput`
  - `Avg generation throughput`

### 8.2 llama.cpp

第一版可稳定采集：

- 响应 `usage`
- 日志中的：
  - `n_ctx`
  - `n_ctx_seq`
- GPU 进程显存

如果本轮日志里没有稳定可识别的 KV cache 百分比字段：

- 统一记为 `null`
- 不手算，不伪造

### 8.3 SGLang

第一版可稳定采集：

- 响应 `usage`
- 日志中的：
  - `KV Cache is allocated. #tokens`
- GPU 进程显存

如果没有稳定的 KV cache usage 百分比：

- 同样记为 `null`

### 8.4 字段缺失原则

所有后端统一遵守：

- 能确认的字段才写
- 没确认的字段写 `null` / `unknown`
- 不为了表面统一去伪造数字

## 9. 显存归类规则

“其他琐碎资源占用显存情况”第一版只统计：

- 非当前后端 GPU 进程的显存占用汇总与明细

### 9.1 当前后端进程

通过下面信息归类：

- 当前激活 profile 的 `container_name`
- 容器相关 GPU 进程
- 已知后端进程名特征

### 9.2 其他进程

所有 GPU 进程中，排除当前后端进程后，剩余部分都视为：

- `other_processes`

### 9.3 汇总要求

至少给出：

- `backend_process_used_mb`
- `other_processes_total_mb`
- `other_processes[]`

这能直接回答：

- 模型自己用了多少显存
- 同机还有谁在争抢显存
- 为什么同模型两次压测结果可能不同

## 10. Gateway 超时修复设计

### 10.1 根因

当前非流式代理请求经过：

- `proxy_openai_chat()`
- `ctx.backend_client.post_json()`

最终落到：

- `httpx.AsyncClient(base_url=self.base_url, timeout=120)`

对长上下文非流式请求，这会在后端真正返回前提前失败。

### 10.2 修复策略

本次不采用“把 120 改成另一个硬编码数字”的一次性补丁，而采用：

- 给 `BackendClient` 的非流式上游请求 timeout 引入正式配置
- 健康检查 timeout 保持短超时
- 流式路径继续 `timeout=None`

### 10.3 默认值

第一版默认建议：

- 非流式 upstream timeout：`300s`
- 健康检查 timeout：保持现状
- 流式 timeout：`None`

这样做的原因：

- 当前已实测 `27B-FP8 256K` 直连约 `199s`
- 后续不同模型和后端在 `256K` 下可能更慢
- `300s` 比 `180s / 240s` 更稳妥
- 又避免默认无限等待

### 10.4 配置来源

timeout 必须走现有配置/环境体系，而不是写死在 benchmark 脚本里。

第一版允许的来源包括：

- `config/defaults.yaml`
- 或现有 settings 对应的 env 覆盖

正式真相应仍由项目配置体系统一管理。

## 11. CLI 设计

第一版脚本入口建议为：

- `scripts/benchmark_backend.py`

至少支持：

- 指定输出目录
- 指定阶梯列表
- 指定 `max_tokens`
- 指定采样间隔
- 指定是否覆盖当前 profile

默认行为：

- 使用当前激活 profile
- 只测直连后端
- 默认阶梯：
  - `4096`
  - `32768`
  - `65536`
  - `131072`
  - `262000`
- 采样间隔：`1s`

## 12. 测试与验收

### 12.1 timeout 修复

至少需要：

- 一个失败测试，覆盖非流式 upstream timeout 的配置化
- 一个验证，确认不再固定为 `120`
- 一次命令级验证，确认 `gateway 256K` 不再在 `120s` 左右报 `500`

### 12.2 benchmark 工具

至少需要：

- 结果 schema 测试
- GPU 进程归类测试
- 三后端日志解析测试
- prompt builder 测试

### 12.3 命令级验收

第一版至少完成：

- 用当前 `vLLM qwen36-27b-fp8` 跑一轮真实 benchmark
- 成功产出：
  - `summary.json`
  - `samples.jsonl`

## 13. 第一版不做的事

- 自动把 benchmark 结果改写回 `docs/knowledge/model_context_performance.md`
- benchmark `gateway`
- 管理台图表
- 多并发 / 压力测试
- CPU / RAM / IO 采集
- 统一抽象所有后端为同一套“完全一致”的 KV 指标

## 14. 风险与边界

### 14.1 日志口径不稳定

`vLLM / llama.cpp / SGLang` 的日志格式都可能变化，因此：

- 第一版必须把解析器设计成“尽量拿，拿不到就空”
- 不能把日志解析失败当成整个 benchmark 失败

### 14.2 GPU 进程归因不可能 100% 完美

容器进程和 GPU 子进程之间的映射可能受运行环境影响，因此：

- 第一版以“当前后端显存 + 其他进程显存”两级归类为主
- 不追求一次性做出复杂的容器级全链路显存拓扑

### 14.3 长请求仍可能非常慢

修复 `gateway timeout` 只意味着：

- 结果能等回来

不意味着：

- 长上下文体验已经足够好

性能问题仍应在 benchmark 层如实暴露，而不是在代理层掩盖。
