# 第六阶段（b）实验报告：Nsight 工具链 bring-up 与 64K 同形状 ncu

> 文档定位：项目知识库中的 LLM serving 优化实验报告，不属于 `llmnode` 项目蓝图、契约或正式路线图。
> 实验目标：打通 Nsight Systems / Nsight Compute 工具链，在 `64K + 512` 主代表点上取得 Marlin / FlashAttention 的 ncu section 证据。
> 更新时间：2026-06-11。
> 当前结论状态：Nsight Systems 已覆盖 c1/c2/c4 server-side timeline；Nsight Compute 已在 `64K + 512` 同形状上取得 clean Marlin 与 FlashAttention LaunchStats；server-side attach 路径已摸排但未完全打通。

相关专题：

- AWQ profiler 见 [stage4-awq-profiler.md](./stage4-awq-profiler.md)。
- NVFP4 profiler 见 [stage5-nvfp4-profiler.md](./stage5-nvfp4-profiler.md)。
- FP8 KV 容量、速度与质量回归见 [stage6a-fp8-kv-benchmark.md](./stage6a-fp8-kv-benchmark.md)。
- 总方案见 [experiment-master-plan.md](./experiment-master-plan.md)。

## 1. 工具链定位

| 工具 | 用途 | 适用场景 |
|---|---|---|
| Nsight Systems (`nsys`) | CPU/GPU timeline、CUDA API、kernel、memops、CUDA graph | 请求级端到端分析、scheduler queue、launch gap、stream overlap |
| Nsight Compute (`ncu`) | 单 kernel 深度指标（SM occupancy、memory throughput、warp stall） | kernel 级瓶颈诊断 |

宿主工具路径：

| 工具 | 路径 | 版本 |
|---|---|---|
| `nsys` | `/opt/anaconda3/pkgs/nsight-compute-2026.1.1.2-h934865d_0/nsight-compute-2026.1.1/host/target-linux-x64/nsys` | 2026.1.1.0 |
| `ncu`（推荐） | `/opt/anaconda3/pkgs/nsight-compute-2026.1.1.2-h934865d_0/nsight-compute-2026.1.1/ncu` | 2026.1.1.0 |
| `ncu`（旧版） | `/opt/anaconda3/nsight-compute/2022.3.0/ncu` | 2022.3.0.0 |
| `ncu`（wrapper） | `/opt/anaconda3/bin/ncu` | 不可用，报 `nsight-compute directory is not found` |

vLLM 镜像内未预装 `nsys` / `ncu`，需从宿主挂载进容器。

GPU：`NVIDIA A800 80GB PCIe`。

## 2. Nsight Systems（timeline 分析）

### 2.1 容器内 smoke

用最小 Torch CUDA matmul 验证 `nsys` 工具链可用：

```bash
docker run --rm --gpus all \
  -e HOME=/tmp \
  -v /opt/anaconda3/pkgs/nsight-compute-2026.1.1.2-h934865d_0/nsight-compute-2026.1.1:/host-ncu:ro \
  -v /tmp:/host-tmp \
  --entrypoint /bin/bash \
  vllm/vllm-openai:nightly \
  -lc '...; /host-ncu/host/target-linux-x64/nsys profile --force-overwrite=true --sample=none --trace=cuda,nvtx,osrt --output=/host-tmp/llmnode-nsys-container-smoke python3 /tmp/nsys_torch_smoke.py'
```

产物：`/tmp/llmnode-nsys-container-smoke.nsys-rep`、`.sqlite`

`nsys stats` 已能读出 CUDA API Summary、GPU Kernel Summary（`ampere_sgemm_128x64_nn`）、GPU MemOps Summary、OS Runtime Summary。

### 2.2 vLLM server 短请求 timeline

用 `nsys profile` 包裹临时 vLLM 容器，验证能覆盖真实 serving 进程：

```text
container: qwen36-27b-awq-int4-nsys-smoke-vllm
model: Qwen3.6-27B-AWQ-INT4
request: prompt=17 tokens, max_tokens=32
trace: cuda,nvtx,osrt
```

产物：`/tmp/llmnode-nsys-vllm-smoke.nsys-rep`、`.sqlite`

Top CUDA kernels：

| Kernel family | Total time | Instances |
|---|---:|---:|
| FlashAttention `flash_fwd_kernel` | `3,867.07 ms` | `27` |
| Marlin `marlin::Marlin` | `2,058.91 ms` | `2,048` |
| `triton_red_fused__to_copy_add_marlin_gemm_rms_norm_3` | `1,506.55 ms` | `7,880` |
| `triton_red_fused__to_copy_add_copy__marlin_gemm_rms_norm_5` | `1,439.69 ms` | `3,640` |

判断：FlashAttention + Marlin 是主热点家族。但此 capture 覆盖了 server 启动、compile、warmup，不能直接当作请求阶段占比结论。

### 2.3 Offline 请求窗口 capture：`AWQ-INT4 64K + output=512`

用 `cudaProfilerStart/Stop` 缩小 capture window 到纯请求阶段：

```text
model: Qwen3.6-27B-AWQ-INT4
workload: prompt≈64K, max_tokens=512, concurrency=1
capture range: cudaProfilerStart() -> cudaProfilerStop()
```

产物：`/tmp/llmnode-nsys-vllm-offline-awq-64k-512.nsys-rep`、`.sqlite`、`-summary.json`

请求结果：`65535` prompt tokens、`369` completion tokens、`43.18 s`、`8.55 tok/s`

Top CUDA kernels：

| Kernel family | Total time | Instances | 占 GPU kernel time |
|---|---:|---:|---:|
| Marlin | `19,438.24 ms` | `16,640` | `68.1%` |
| FlashAttention splitkv | `6,667.15 ms` | `64` | `23.4%` |
| Ampere FP16 GEMM | `552.01 ms` | `564` | `1.9%` |
| merge inverse | `302.72 ms` | `192` | `1.1%` |

Top CUDA APIs：

| API | Total time | Calls | 占 CUDA API time |
|---|---:|---:|---:|
| `cudaLaunchKernel` | `19,419.87 ms` | `26,185` | `51.1%` |
| `cudaEventSynchronize` | `11,717.62 ms` | `746` | `30.8%` |
| `cuLaunchKernel` | `4,360.64 ms` | `1,924` | `11.5%` |
| `cudaGraphLaunch` | `223.89 ms` | `369` | `0.6%` |

判断：请求窗口内 GPU kernel time 仍由 Marlin 和 FlashAttention 主导。此报告不再被启动/compile/warmup 污染，但仍使用 offline `LLM.generate()`，不覆盖 server scheduler 链路。

### 2.4 Server-side c2 capture：`AWQ-INT4 64K + output=512, concurrency=2`

用 `nsys launch/start/stop` 做 server-side capture：

```text
container: qwen36-27b-awq-int4-nsys-server-c2
workload: prompt≈64K, max_tokens=512, concurrency=2
capture control: nsys launch -> API ready -> nsys start -> concurrent requests -> nsys stop
```

产物：`/tmp/llmnode-nsys-vllm-server-awq-64k-c2-512.nsys-rep`、`.sqlite`、`-summary.json`

请求结果：

| request | status | completion tokens | wall time |
|---|---|---:|---:|
| 0 | 200 OK | 512 | 79.22 s |
| 1 | 200 OK | 369 | 73.45 s |

vLLM scheduler 日志：两个 64K 请求都进入 Running，没有 Waiting 队列。KV cache usage 峰值约 `37.3%`。

Top CUDA kernels：

| Kernel family | Total time | Instances | 占 GPU kernel time |
|---|---:|---:|---:|
| Marlin | `38,574.43 ms` | `32,768` | `68.3%` |
| FlashAttention splitkv | `13,300.27 ms` | `272` | `23.5%` |

### 2.5 Server-side c4 capture：`AWQ-INT4 64K + output=512, concurrency=4`

```text
container: qwen36-27b-awq-int4-nsys-server-c4
workload: prompt≈64K, max_tokens=512, concurrency=4
```

产物：`/tmp/llmnode-nsys-vllm-server-awq-64k-c4-512.nsys-rep`、`.sqlite`、`-summary.json`

请求结果：4 个请求全部完成，wall time `136.84 s`。

vLLM scheduler 日志：

| Time | Running | Waiting | GPU KV cache usage |
|---:|---:|---:|---:|
| `02:30:06` | 2 | 2 | 21.7% |
| `02:30:36` | 3 | 1 | 42.5% |
| `02:31:06` | 4 | 0 | 61.2% |
| `02:31:36` | 4 | 0 | 74.7% |

**c4 明确制造出 Waiting 队列**：开始 `Running=2 / Waiting=2`，随后 `3/1`，最后 `4/0`。

Top CUDA kernels：

| Kernel family | Total time | Instances | 占 GPU kernel time |
|---|---:|---:|---:|
| Marlin | `78,109.16 ms` | `65,792` | `68.5%` |
| FlashAttention splitkv | `27,405.82 ms` | `528` | `24.0%` |

时间线补充：

| 指标 | 值 | 含义 |
|---|---:|---|
| kernel span | `134,422.68 ms` | 从第一个 kernel 开始到最后一个 kernel 结束 |
| request wall time | `136,844.11 ms` | 4 个并发请求总墙钟时间 |
| kernel span / request wall | `98.2%` | 请求窗口大部分时间都有 GPU kernel 活动 |
| total inter-kernel gap | `20,432.92 ms` | kernel 序列内部累计空洞 |
| gap / kernel span | `15.2%` | kernel 时间线内部仍有可见空洞 |
| gaps > `1 ms` | `387` | 中小 launch/sync 空洞不少 |
| gaps > `1000 ms` | `6` | 对应长 prefill / queueing / decode 切换类空洞 |
| active kernel streams | `1` | 只有 stream `7` 承载主要 kernel |

### 2.6 各次 nsys capture 横向对比

| capture | 类型 | 并发 | Marlin 占比 | FlashAttn 占比 | Waiting 队列 | KV usage 峰值 |
|---|---|---:|---:|---:|---|---:|
| server 短请求 | server | 1 | - | - | 无 | - |
| offline c1 | offline | 1 | 68.1% | 23.4% | 无 | - |
| server c2 | server | 2 | 68.3% | 23.5% | 无 | 37.3% |
| server c4 | server | 4 | 68.5% | 24.0% | 有（2→3→4） | 74.7% |

核心结论：

- GPU kernel 热点分布高度稳定：**Marlin 约 68%，FlashAttention 约 23-24%**，跨 capture 一致。
- c4 能明确观察到 Waiting 队列和 Running/Waiting 转换。
- kernel 时间线内部累计空洞约 15.2%，主要是大量细碎 launch/sync gap，不是 GPU 大段空闲。
- 所有主要 kernel 落在同一个 CUDA stream 上，没有多流 overlap 证据。

## 3. Nsight Compute（单 kernel 深度指标）

### 3.1 权限问题与解决

初始状态：`/proc/driver/nvidia/params` 中 `RmProfilingAdminOnly: 1`，`ncu` 采集 SM occupancy / memory bandwidth 会报 `ERR_NVGPUCTRPERM`。`nsys gpu metrics` 也被同一权限阻止。

2026-06-10 复查：`RmProfilingAdminOnly: 0`，权限阻塞已消失。

### 3.2 `16K + 512` 首次成功采样

权限放开后，在 `16K + output=512` 真实 vLLM workload 上首次成功取得 Marlin 和 FlashAttention 的 ncu section。

关键方法：
- `--kernel-name "regex:.*Marlin.*"` 或 `"regex:.*flash.*|.*Flash.*|.*fmha.*|.*attention.*"`
- `--section LaunchStats --section Occupancy --section MemoryWorkloadAnalysis`
- `--launch-count 6 --profile-from-start on`

Marlin（16K 代表点）：

| 指标 | 结果 |
|---|---|
| launch shape | `grid=(108,1,1), block=(256,1,1)` |
| registers per thread | `255` |
| dynamic shared memory per block | `166.91 KiB` |
| waves per SM | `1` |
| theoretical occupancy | `12.5%` |
| achieved occupancy | `12.5%` |
| memory throughput | `447.53 - 490.95 GB/s` |
| max bandwidth | `23.79% - 25.37%` |
| L2 hit rate | `62.52% - 62.54%` |

FlashAttention（16K 代表点）：

| 指标 | 结果 |
|---|---|
| launch shape | `grid=(512,1,16), block=(128,1,1)` |
| registers per thread | `255` |
| dynamic shared memory per block | `49.15 KiB` |
| waves per SM | `37.93` |
| theoretical occupancy | `12.5%` |
| achieved occupancy | `12.43%` |
| memory throughput | `19.09 - 19.29 GB/s` |
| max bandwidth | `42.34% - 42.35%` |
| L2 hit rate | `98.56% - 98.69%` |

### 3.3 推进到 `64K + 512` 主代表点

**旧阻塞点**：直接让 `ncu` 冷启动包裹默认 `max_model_len=262144` 的 vLLM，profiler overhead 会压缩可用 KV cache，导致 `64K` 初始化失败。

**核心方法调整**（三个变量）：

| 调整 | 设置 | 作用 |
|---|---|---|
| `max_model_len` | `66048`（从 262144 收窄） | 避免为 256K 预留无意义的 KV 预算 |
| `VLLM_ENABLE_V1_MULTIPROCESSING` | `0` | 消除 spawn 子进程，确保 ncu 追踪到真实 kernel |
| `enforce_eager` | `True` | 关闭 torch.compile + CUDA Graph，减少 ncu 采样干扰 |

**修正 `--force-overwrite` 参数误用**：

之前多轮 offline ncu 返回 `No kernels were profiled`，根因是 `--force-overwrite true` 的误用——`true` 被当成目标程序，实际脚本没执行。正确写法是无值 flag `--force-overwrite`。

**GPU 空闲窗口 clean 复测**：

在 `nvidia-smi` 返回空后，用 offline 单进程 + eager 路径重跑。

Marlin（64K clean）：

| 指标 | 结果 |
|---|---|
| Block Size | `256` |
| Grid Size | `108` |
| Registers Per Thread | `255` |
| Dynamic Shared Memory Per Block | `166.91 Kbyte/block` |
| Threads | `27,648` |
| Waves Per SM | `1` |

runtime：`176.78 s`、`2.90 tok/s`（ncu 包裹下，不等同于正常 serving 性能）

FlashAttention（64K clean）：

| 指标 | 结果 |
|---|---|
| Block Size | `128` |
| Grid Size | `8,192` |
| Registers Per Thread | `255` |
| Dynamic Shared Memory Per Block | `49.15 Kbyte/block` |
| Threads | `1,048,576` |
| Waves Per SM | `37.93` |

runtime：`184.96 s`、`2.77 tok/s`

KV cache 观测（clean 窗口稳定）：

| 指标 | 值 |
|---|---|
| Available KV cache memory | `21.12 GiB` |
| GPU KV cache size | `86,240 tokens` |
| Maximum concurrency for `66,048` tokens/request | `5.01x` |

### 3.4 Marlin 与 FlashAttention 的 64K LaunchStats 汇总

| 指标 | Marlin | FlashAttention |
|---|---|---|
| Block Size | 256 | 128 |
| Grid Size | 108 | 8,192 |
| Registers Per Thread | 255 | 255 |
| Dynamic Shared Memory | 166.91 KiB/block | 49.15 KiB/block |
| Waves Per SM | 1 | 37.93 |
| theoretical occupancy | 12.5% | 12.5% |
| achieved occupancy | 12.5% | 12.43% |
| memory throughput | 447-491 GB/s | 19.09-19.29 GB/s |
| L2 hit rate | 62.5% | 98.6% |

与 16K 样本形态一致，launch shape 不因 prompt 长度变化而改变。**16K 的指标可以外推到 64K 主代表点。**

## 4. Server-side attach 路径探索

### 4.1 server-under-ncu

用 `ncu` 包裹显式 Python API server 入口脚本：同一脚本在不包 `ncu` 时可以正常驻留，一旦改成 server-under-ncu，进程会在约 1 s 内退出：

```text
==LOG== Target process 18 terminated before first instrumented API call.
==WARNING== No kernels were profiled.
```

### 4.2 两步式 launch/attach 摸排

用 `ncu --mode=launch` 启动 server，再 `ncu --mode=attach`：

关键发现：
1. `launch` 本身能挂起来，进入 APIServer 启动流程
2. attach 必须在同一个 launch 容器内执行（跨容器 attach 找不到进程）
3. `target-processes all` 下 attach 可能优先命中短命子进程 `model_executor.models.registry`（PID 149），而不是稳定的 APIServer
4. `application-only` 能稳定连到 APIServer（PID 18），但真正执行 kernel 的 EngineCore 子进程仍未被覆盖
5. `target-processes-filter regex:.*EngineCore.*` 或 `exclude:python3` 都会让 attach 通道直接消失

### 4.3 当前结论

```text
两步式 launch/attach 不是完全不能用，
但 vLLM server-side 真正发 kernel 的进程链会从 APIServer 继续下沉到 EngineCore；
只覆盖 APIServer 仍然不足以产出可复查的 kernel section。
```

offline 单进程 + eager 路径已足够产出 clean report，server-side attach 作为备用路线，待后续需要证明 OpenAI server 路径与 offline 存在差异时再攻。

## 5. 踩坑记录与方法论

以下记录在 bring-up 过程中遇到的关键问题和解法，供后续遇到同类问题时参考。

### 5.1 `--force-overwrite` 无值 flag

```bash
# 错误：true 被当成目标程序，脚本不执行
ncu --force-overwrite true python3 script.py

# 正确：无值 flag
ncu --force-overwrite python3 script.py
```

### 5.2 `max_model_len` 收窄策略

ncu 的 replay / instrumentation 会显著放大 vLLM 冷启动的显存开销。默认 `max_model_len=262144` 会因 profiler overhead 导致 64K 初始化失败。

解法：把 `max_model_len` 收到 `66048`（刚好容纳 65536 + 512），避免为 256K 预留无意义的 KV 预算。

### 5.3 `VLLM_ENABLE_V1_MULTIPROCESSING=0`

vLLM 默认 V1 multiprocessing 会把真实 CUDA kernel 放到子进程里，导致 `ncu` 追踪不到。

```bash
docker run ... -e VLLM_ENABLE_V1_MULTIPROCESSING=0 ...
```

设置后走 `InprocClient + UniProcExecutor` 单进程路径，日志中不再出现 `spawn` 覆盖 warning。

### 5.4 `enforce_eager=True`

关闭 `torch.compile + CUDA Graph`，减少 ncu 采样干扰。代价是速度从约 `12.44 tok/s` 拉低到约 `8.12 tok/s`，但它是更干净的 profiling 候选路径。

### 5.5 ncu 进程过滤

- `--target-processes all`：可能优先命中短命子进程
- `--target-processes application-only`：能绑到 APIServer，但不覆盖 EngineCore
- `--target-processes-filter regex:.*EngineCore.*`：attach 通道直接消失
- `--target-processes-filter exclude:python3`：attach 通道同样消失

当前推荐：直接用 offline 单进程路径，不依赖 attach。

### 5.6 `HOME` 目录

ncu 尝试写入 `~/Documents/NVIDIA Nsight Compute/` 时有权限 warning。建议显式设置：

```bash
docker run ... -e HOME=/tmp ...
```

## 6. 已确认

1. Nsight Systems 已覆盖 c1 offline、c2 server、c4 server 的 timeline，GPU kernel 热点分布跨 capture 一致（Marlin ~68%，FlashAttention ~23-24%）。
2. Nsight Compute 已在 `64K + 512` 同形状上取得 clean Marlin 与 FlashAttention LaunchStats，与 16K 样本形态一致。
3. 旧阻塞点（权限、KV cache 不足、`--force-overwrite` 误用）均已解决。
4. `max_model_len=66048` + 单进程 + eager 是当前最稳定的 ncu capture 方法。
5. server-side attach 路径已充分摸清，当前 offline 路径已够用。
6. 两个主热点 kernel 的共同瓶颈是 register 压力（255/thread），不是 shared memory。

## 7. 仍不确定

1. LaunchStats 是否足够，还是需要补 `Occupancy / MemoryWorkloadAnalysis`——取决于后续是否要把优化动作推进到 kernel 层。
2. server-side attach 是否存在可用的进程过滤策略——当前所有尝试都会导致 attach 通道消失或覆盖不到 EngineCore。
3. offline 路径与 OpenAI server 路径是否存在性能差异——如必须证明，需继续攻克 server-side attach。

## 8. 下一步

1. 用 clean LaunchStats 解释 Stage 8（原 Stage 11）的 launch gap / queue 现象。
2. 判断是否需要补 `Occupancy / MemoryWorkloadAnalysis`；如果优化动作仍停留在参数和调度层，暂不深采。
3. 如必须贴近真实 OpenAI server 请求路径，再继续攻克 server-side launch + attach。
