# 第七阶段实验报告：FP8 KV 质量回归与 Nsight bring-up

> 文档定位：项目知识库中的 LLM serving 优化实验报告，不属于 `llmnode` 项目蓝图、契约或正式路线图。  
> 实验目标：对 `AWQ-INT4 + FP8 KV cache` 做最小质量回归，并开始 Nsight Systems / Nsight Compute 工具链 bring-up。  
> 更新时间：2026-06-10。  
> 当前结论状态：普通 AWQ baseline 与 FP8 KV 对照质量回归均已完成。FP8 KV 对照 `5` 项通过 `1` 项，相比普通 AWQ baseline 新增 `code_generation` 和 `math_reasoning` 两项退化；严格 JSON 和工具 JSON 在 baseline 中已经失败，本轮不算新增退化。`nsys` 已在 Nsight Compute 2026.1.1 包内找到，并已完成真实 vLLM server 短请求 timeline capture，以及一次 `AWQ-INT4 64K + output=512` 的 offline 请求窗口 capture；`/opt/anaconda3/bin/ncu` wrapper 不可用，但 Nsight Compute 2026.1.1 的真实二进制可挂载进 vLLM 容器启动。2026-06-10 已确认 `RmProfilingAdminOnly: 0`，旧的 `ERR_NVGPUCTRPERM` 权限阻塞已消失；但 `ncu` 冷启动包裹真实 `AWQ-INT4 64K + output=512` workload 时，会因为 profiler 额外显存开销把 vLLM 的可用 KV cache 压缩到不足以通过 engine 初始化，当前新的真实阻塞点已经转为“profiler overhead 导致的启动期显存预算不足”。当前 vLLM 镜像内仍未发现 `nsys/ncu`。

相关专题：

- FP8 KV 容量和速度对照见 [stage5-nvfp4-nointerference.md](./stage5-nvfp4-nointerference.md)。
- NVFP4 profiler 见 [stage6-nvfp4-profiler.md](./stage6-nvfp4-profiler.md)。
- profiler 方法见 [profiler-and-kernels.md](../performance/profiler-and-kernels.md)。

## 1. 质量回归设计

本轮使用 5 个最小用例：

| case | 目的 |
|---|---|
| `long_context_consistency` | 长上下文精确取数 |
| `code_generation` | 代码生成基本正确性 |
| `math_reasoning` | 数学推理基本正确性 |
| `structured_json` | 严格 JSON 输出 |
| `tool_call_json_stability` | 工具调用 JSON 稳定性 |

脚本：

```text
scripts/fp8_kv_quality_check.py
```

输出目录：

```text
runtime/data/benchmarks/manual-stage7-fp8-kv-quality/
```

注意：当前 Qwen/vLLM 响应把文本放在 `message.reasoning`，`message.content` 可能为 `null`。脚本已同时读取 `content / reasoning_content / reasoning`。

脚本支持两个入口：

```bash
/home/heshan/.conda/envs/paper2any/bin/python scripts/fp8_kv_quality_check.py run ...
/home/heshan/.conda/envs/paper2any/bin/python scripts/fp8_kv_quality_check.py compare ...
```

旧形式仍可用：

```bash
/home/heshan/.conda/envs/paper2any/bin/python scripts/fp8_kv_quality_check.py \
  --model qwen36-27b-awq-int4 \
  --output <output.json>
```

## 2. 普通 AWQ baseline

profile：

```text
vllm_qwen36-27b-awq-int4
```

输出：

```text
runtime/data/benchmarks/manual-stage7-fp8-kv-quality/awq-baseline.json
```

命令：

```bash
/home/heshan/.conda/envs/paper2any/bin/python scripts/fp8_kv_quality_check.py \
  --model qwen36-27b-awq-int4 \
  --output runtime/data/benchmarks/manual-stage7-fp8-kv-quality/awq-baseline.json
```

结果：

| case | passed | 说明 |
|---|---|---|
| `long_context_consistency` | yes | 找到 `team-0 / alpha-777 / 248` |
| `code_generation` | yes | 包含 `def stable_top_k`、`sorted`、`k <= 0` |
| `math_reasoning` | yes | 包含 `23.33` |
| `structured_json` | no | 内容包含目标字段，但输出混入 reasoning，整体不是合法 JSON |
| `tool_call_json_stability` | no | 开头有 JSON，但后续混入说明文字，整体不是合法 JSON |

baseline 判断：

- 当前模型/服务路径本身就存在严格 JSON 稳定性问题。
- 后续 FP8 KV 对照不能只看“是否严格 JSON 失败”，而应看是否比 baseline 更差，例如长上下文、代码、数学是否新增失败，JSON 失败形态是否明显恶化。

## 3. FP8 KV 对照结果

profile：

```text
vllm_qwen36-27b-awq-int4-fp8-kv
```

启动时发现外部 GPU 进程：

```text
3477885, /proj02/pengyao/envs/SFormer_clean/bin/python, 23462 MiB
```

后续复查时仍发现同类外部 GPU 进程：

```text
3584465, /proj02/pengyao/envs/SFormer_clean/bin/python, 23450 MiB
```

处理：

- 已停止本任务启动的 `qwen36-27b-awq-int4-fp8-kv-vllm` 容器。
- 未继续执行 FP8 KV 质量请求，避免形成受污染结果。
- 本任务相关 vLLM 容器当前均已退出；FP8 KV 质量对照的阻塞点是外部 GPU 进程，而不是本任务残留容器。

2026-06-10 GPU 空窗后已重新启动 FP8 KV profile 并完成对照。

启动日志：

```text
runtime/logs/qwen36-27b-awq-int4-fp8-kv-vllm-20260610-091113.log
```

启动侧证据：

| 字段 | 值 |
|---|---:|
| effective `kv_cache_dtype` | `fp8` |
| AWQ kernel | `MarlinLinearKernel for CompressedTensorsWNA16` |
| attention backend | `FLASHINFER` / `TRITON_ATTN` candidates，实际日志选择 `FLASHINFER` |
| model loading memory | `19.05 GiB` |
| model loading time | `10.583318 s` |
| torch.compile time | `74.81 s` |
| initial profiling / warmup | `97.23 s` |
| available KV cache memory | `22.01 GiB` |
| GPU KV cache size | `178,752 tokens` |
| max concurrency for `262,144` tokens/request | `2.68x` |
| CUDA graph pool memory | `0.48 GiB` |
| API startup | success |

运行质量对照：

```bash
/home/heshan/.conda/envs/paper2any/bin/python scripts/fp8_kv_quality_check.py run \
  --model qwen36-27b-awq-int4 \
  --output runtime/data/benchmarks/manual-stage7-fp8-kv-quality/awq-fp8-kv.json
```

对照输出：

```text
runtime/data/benchmarks/manual-stage7-fp8-kv-quality/awq-fp8-kv.json
runtime/data/benchmarks/manual-stage7-fp8-kv-quality/awq-vs-fp8-kv-comparison.json
```

FP8 KV 单独结果：

| case | passed | 说明 |
|---|---|---|
| `long_context_consistency` | yes | 找到 `team-0 / alpha-777 / 248` |
| `code_generation` | no | 输出包含思考过程，且 512 token 截断前没有出现 `def stable_top_k` |
| `math_reasoning` | no | 推理到 `7 / 30 = 0.233333...`，但 512 token 截断前没有输出 `23.33` |
| `structured_json` | no | 包含目标字段，但整体不是合法 JSON |
| `tool_call_json_stability` | no | 开头有 JSON，但后续混入说明文字，整体不是合法 JSON |

和普通 AWQ baseline 自动对照：

```bash
/home/heshan/.conda/envs/paper2any/bin/python scripts/fp8_kv_quality_check.py compare \
  --baseline runtime/data/benchmarks/manual-stage7-fp8-kv-quality/awq-baseline.json \
  --candidate runtime/data/benchmarks/manual-stage7-fp8-kv-quality/awq-fp8-kv.json \
  --output runtime/data/benchmarks/manual-stage7-fp8-kv-quality/awq-vs-fp8-kv-comparison.json
```

对照结论：

| case | baseline | FP8 KV | 是否新增退化 |
|---|---|---|---|
| `long_context_consistency` | pass | pass | no |
| `code_generation` | pass | fail | yes |
| `math_reasoning` | pass | fail | yes |
| `structured_json` | fail | fail | no |
| `tool_call_json_stability` | fail | fail | no |

当前判断：

- FP8 KV cache 的容量收益仍然成立，但质量回归不通过。
- 本轮不能把 `AWQ-INT4 + FP8 KV cache` 写成可上线配置。
- 新增退化集中在代码生成和数学推理两个 baseline 通过的用例上；这比 JSON 稳定性失败更严重，因为 JSON 两项在普通 AWQ baseline 中已经失败。
- 由于失败输出都在 512 token 内出现“思考过程挤占最终答案”的形态，后续如果继续调查，需要区分 `FP8 KV 精度退化`、`reasoning parser / 输出字段行为`、`max_tokens 截断` 三类因素。

## 4. Nsight bring-up 状态

宿主机检查：

| 工具 | 结果 |
|---|---|
| `nsys` | PATH 未发现；已在 Nsight Compute 包内找到 `/opt/anaconda3/pkgs/nsight-compute-2026.1.1.2-h934865d_0/nsight-compute-2026.1.1/host/target-linux-x64/nsys`，版本 `2026.1.1.0` |
| `/opt/anaconda3/bin/ncu` | wrapper 存在，但运行时报 `nsight-compute directory is not found` |
| `/opt/anaconda3/pkgs/nsight-compute-2026.1.1.2-h934865d_0/nsight-compute-2026.1.1/ncu` | 可用，版本 `2026.1.1.0` |
| `/opt/anaconda3/nsight-compute/2022.3.0/ncu` | 可用，版本 `2022.3.0.0` |
| NVIDIA driver profiling flag | `/proc/driver/nvidia/params` 中 `RmProfilingAdminOnly: 1` |

vLLM 镜像检查：

```bash
docker run --rm --entrypoint /bin/sh vllm/vllm-openai:nightly -lc \
  'command -v nsys || true; command -v ncu || true'
```

结果：未发现 `nsys` / `ncu`。

当前含义：

- Nsight Systems 二进制已找到，CUDA smoke timeline capture 已跑通；下一步才是对 vLLM 请求 workload 做正式 timeline。
- Nsight Compute 可以先从宿主真实二进制做最小 bring-up，推荐优先使用 `2026.1.1` 路径；不要使用 `/opt/anaconda3/bin/ncu` wrapper。
- Nsight Compute 更适合单 kernel 指标，不是完整请求 timeline；CPU/GPU timeline、scheduler queue、kernel launch gap 和 stream overlap 仍需要 Nsight Systems。
- 当前普通沙箱下 `/home/heshan/.conda/envs/paper2any/bin/python` 的 `torch.cuda.is_available()` 为 `False`；真实 CUDA 采样需要宿主 GPU 可见环境。
- vLLM 容器内 `python3 + torch` 可以看到 CUDA：`torch.cuda.is_available() == True`，GPU 为 `NVIDIA A800 80GB PCIe`。

推荐的 Nsight Compute 路径：

```bash
/opt/anaconda3/pkgs/nsight-compute-2026.1.1.2-h934865d_0/nsight-compute-2026.1.1/ncu
```

已完成的最小 `ncu` 启动预检：

```bash
/opt/anaconda3/pkgs/nsight-compute-2026.1.1.2-h934865d_0/nsight-compute-2026.1.1/ncu \
  --target-processes all \
  --set default \
  --export /tmp/llmnode-ncu-smoke \
  --force-overwrite true \
  /bin/true
```

结果：

- `ncu` 可以启动并正常退出。
- 因 `/bin/true` 没有 CUDA kernel，输出 `No kernels were profiled`，这不代表 Nsight Compute 采样失败。
- `ncu` 尝试写入 `/home/heshan/Documents/NVIDIA Nsight Compute/2026.1.1/Sections` 时有权限 warning；后续建议显式设置 `HOME=/tmp` 或其他可写目录。
- 当前还没有完成 Marlin / FlashAttention 的真实 kernel 采样。

已完成的容器内 CUDA smoke 预检：

```bash
docker run --rm --gpus all \
  -e HOME=/tmp \
  -v /opt/anaconda3/pkgs/nsight-compute-2026.1.1.2-h934865d_0/nsight-compute-2026.1.1:/host-ncu:ro \
  --entrypoint /bin/bash \
  vllm/vllm-openai:nightly \
  -lc '<write a tiny torch matmul script>; /host-ncu/ncu --verbose --log-file stderr --target-processes all --section LaunchStats --launch-count 5 -- python3 /tmp/ncu_torch_smoke.py'
```

预检结论：

- 不加 `ncu` 时，同一容器内 Torch CUDA matmul 可以正常运行。
- 加 `ncu` 后，进程能连接到 Nsight Compute：`Connected to process ... (/usr/bin/python3.12)`。
- 首个 CUDA API 触发硬件计数器权限错误：

```text
ERR_NVGPUCTRPERM - The user does not have permission to access NVIDIA GPU Performance Counters on the target device 0.
```

因此当前 Nsight Compute 的真实阻塞点已经从“找不到工具”收束为：

```text
需要 GPU performance counter 权限，才能采集 SM occupancy / memory bandwidth / stall 等指标。
```

在该权限打开之前，不应把 Nsight Compute 写成已完成 Marlin / FlashAttention 代表 kernel 采样。

### 4.1 Nsight Systems smoke

`nsys` 路径：

```bash
/opt/anaconda3/pkgs/nsight-compute-2026.1.1.2-h934865d_0/nsight-compute-2026.1.1/host/target-linux-x64/nsys
```

已完成容器内 Torch CUDA matmul timeline capture：

```bash
docker run --rm --gpus all \
  -e HOME=/tmp \
  -v /opt/anaconda3/pkgs/nsight-compute-2026.1.1.2-h934865d_0/nsight-compute-2026.1.1:/host-ncu:ro \
  -v /tmp:/host-tmp \
  --entrypoint /bin/bash \
  vllm/vllm-openai:nightly \
  -lc '<write a tiny torch matmul script>; /host-ncu/host/target-linux-x64/nsys profile --force-overwrite=true --sample=none --trace=cuda,nvtx,osrt --output=/host-tmp/llmnode-nsys-container-smoke python3 /tmp/nsys_torch_smoke.py'
```

产物：

```text
/tmp/llmnode-nsys-container-smoke.nsys-rep
/tmp/llmnode-nsys-container-smoke.sqlite
```

`nsys stats` 已能读出：

| 报告 | 证据 |
|---|---|
| CUDA API Summary | 看到 `cudaLaunchKernel`、`cudaMalloc`、`cudaDeviceSynchronize` 等 |
| CUDA GPU Kernel Summary | 看到 `ampere_sgemm_128x64_nn`，20 次实例 |
| CUDA GPU MemOps Summary | 看到 CUDA memset 和 Device-to-Host memcpy |
| OS Runtime Summary | 看到 poll/ioctl/stat/open/read 等 CPU runtime 事件 |

这个 smoke 只证明 Nsight Systems 工具链可用；它还不是 vLLM 请求 timeline，因此还不能回答 scheduler queue、CUDA graph、kernel launch gap、H2D/D2H 和 stream overlap 在真实 serving workload 下的表现。

### 4.2 vLLM server timeline smoke

为了确认 `nsys` 不只是能采小 Torch 脚本，也能覆盖 vLLM serving 进程，本轮用 `nsys profile` 包裹一个临时 vLLM 容器：

```text
container: qwen36-27b-awq-int4-nsys-smoke-vllm
host port: 15674
model: Qwen3.6-27B-AWQ-INT4
request: prompt=17 tokens, max_tokens=32
trace: cuda,nvtx,osrt
cuda graph trace: graph
```

说明：

- 这是一次短请求 timeline smoke，不是 Stage 4/6 的 `64K + output=512` 同形状 profile。
- 这次为了让 `nsys` 包裹 server 主进程，使用了独立临时 Docker 容器，没有修改正式控制入口。
- 第一次手动 `docker stop` 太早导致容器 `137` 退出且没有生成报告；第二次等待 `--duration=420` 自然结束，报告正常生成。

请求结果：

```text
HTTP 200
prompt_tokens=17
completion_tokens=32
finish_reason=length
```

产物：

```text
/tmp/llmnode-nsys-vllm-smoke.nsys-rep
/tmp/llmnode-nsys-vllm-smoke.sqlite
```

启动侧证据：

| 字段 | 值 |
|---|---:|
| model loading memory | `19.05 GiB` |
| model loading time | `11.567377 s` |
| torch.compile time | `7.93 s`，第二次启动命中 compile cache |
| initial profiling / warmup | `7.24 s` |
| available KV cache memory | `22.38 GiB` |
| GPU KV cache size | `90,944 tokens` |
| max concurrency for `262,144` tokens/request | `1.38x` |
| CUDA graph pool memory | `0.08 GiB actual / 0.11 GiB estimated` |
| API startup | success |

`nsys stats` 摘要：

Top CUDA kernels：

| Kernel family | Total time | Instances | 说明 |
|---|---:|---:|---|
| FlashAttention `flash_fwd_kernel` | `3,867.07 ms` | `27` | 最大 GPU kernel family |
| Marlin `marlin::Marlin` | `2,058.91 ms` | `2,048` | 量化 GEMM 主路径之一 |
| `triton_red_fused__to_copy_add_marlin_gemm_rms_norm_3` | `1,506.55 ms` | `7,880` | Marlin/RMSNorm 融合相关 |
| `triton_red_fused__to_copy_add_copy__marlin_gemm_rms_norm_5` | `1,439.69 ms` | `3,640` | Marlin/RMSNorm 融合相关 |
| vectorized fill kernel | `677.46 ms` | `28,501` | 启动/初始化/运行期辅助 kernel |

Top CUDA APIs：

| API | Total time | Calls |
|---|---:|---:|
| `cudaMemcpyAsync` | `3,671.23 ms` | `10,524` |
| `cudaDeviceSynchronize` | `3,158.05 ms` | `1,038` |
| `cudaStreamSynchronize` | `1,638.42 ms` | `5,037` |
| `cudaEventSynchronize` | `741.49 ms` | `120` |
| `cudaLaunchKernel` | `654.85 ms` | `45,442` |

CUDA memops：

| Copy kind | Total time | Count | Total size |
|---|---:|---:|---:|
| Host-to-Device | `2,454.19 ms` | `4,867` | `23,751.01 MB` |
| Device-to-Host | `830.40 ms` | `655` | `3,420.98 MB` |
| Device-to-Device | `462.03 ms` | `4,986` | `381,599.66 MB` |

CUDA graph evidence：

| Event | Count |
|---|---:|
| `Graph Creation` | `1,185` |
| `GraphExec Creation` | `395` |

当前判断：

- Nsight Systems 已经不再只是工具链 smoke，已经能采到真实 vLLM server 的 CUDA API / GPU kernel / memops / CUDA graph 信息。
- 这份短请求 timeline 方向上再次支持 FlashAttention + Marlin 是主热点家族。
- 由于 capture 覆盖了 server 启动、compile、warmup、CUDA graph capture 和一次短请求，不能直接当作 `64K + output=512` 请求阶段占比结论。
- 下一步若要回答 scheduler queue、kernel launch gap 和 stream overlap，应缩小 capture window：只采 API ready 后的一段请求 workload，并加入 NVTX 或日志时间戳对齐。

### 4.3 Offline 请求窗口 capture：`AWQ-INT4 64K + output=512`

为了把 Stage 4 的 torch profiler top-kernel 证据推进到 Nsight Systems timeline，本轮又做了一次 offline vLLM capture：

```text
model: Qwen3.6-27B-AWQ-INT4
workload: prompt≈64K, max_tokens=512, concurrency=1
capture range: cudaProfilerStart() -> cudaProfilerStop()
trace: cuda,nvtx,osrt
cuda graph trace: graph
```

产物：

```text
/tmp/llmnode-nsys-vllm-offline-awq-64k-512.nsys-rep
/tmp/llmnode-nsys-vllm-offline-awq-64k-512.sqlite
/tmp/llmnode-nsys-vllm-offline-awq-64k-512-summary.json
```

请求结果：

| 字段 | 值 |
|---|---:|
| target prompt tokens | `65,536` |
| actual prompt tokens | `65,535` |
| max tokens | `512` |
| completion tokens | `369` |
| finish reason | `stop` |
| request seconds | `43.18 s` |
| completion tok/s | `8.55` |
| `cudaProfilerStart()` | `0` |
| `cudaProfilerStop()` | `0` |

启动侧证据：

| 字段 | 值 |
|---|---:|
| model loading memory | `19.05 GiB` |
| model loading time | `11.100494 s` |
| torch.compile time | `97.22 s` |
| initial profiling / warmup | `126.43 s` |
| available KV cache memory | `20.88 GiB` |
| GPU KV cache size | `85,456 tokens` |
| max concurrency for `262,144` tokens/request | `1.29x` |
| CUDA graph pool memory | `0.04 GiB actual / 0.07 GiB estimated` |

`nsys stats` 摘要：

Top CUDA kernels：

| Kernel family | Total time | Instances | 占 GPU kernel time | 说明 |
|---|---:|---:|---:|---|
| Marlin | `19,438.24 ms` | `16,640` | `68.1%` | AWQ 量化 GEMM 主热点 |
| FlashAttention splitkv | `6,667.15 ms` | `64` | `23.4%` | 长上下文 attention 主热点 |
| Ampere FP16 GEMM | `552.01 ms` | `564` | `1.9%` | 次级 GEMM |
| merge inverse | `302.72 ms` | `192` | `1.1%` | 次级 kernel |
| `chunk_fwd_kernel_o` | `207.11 ms` | `192` | `0.7%` | hybrid / chunk 相关 |

Top CUDA APIs：

| API | Total time | Calls | 占 CUDA API time |
|---|---:|---:|---:|
| `cudaLaunchKernel` | `19,419.87 ms` | `26,185` | `51.1%` |
| `cudaEventSynchronize` | `11,717.62 ms` | `746` | `30.8%` |
| `cuLaunchKernel` | `4,360.64 ms` | `1,924` | `11.5%` |
| `cuModuleLoadData` | `1,060.37 ms` | `8` | `2.8%` |
| `cuLaunchKernelEx` | `654.87 ms` | `3,033` | `1.7%` |
| `cudaMemcpyAsync` | `352.29 ms` | `8,427` | `0.9%` |
| `cudaGraphLaunch` | `223.89 ms` | `369` | `0.6%` |

CUDA memops：

| Copy kind | Total time | Count | Total size |
|---|---:|---:|---:|
| Device-to-Device | `51.75 ms` | `3,894` | `39,329.516 MB` |
| Host-to-Device | `10.47 ms` | `4,160` | `27.721 MB` |
| Device-to-Host | `0.59 ms` | `372` | `0.001 MB` |

CUDA graph evidence：

| Event | Count |
|---|---:|
| `CUPTI_ACTIVITY_KIND_GRAPH_TRACE` rows | `368` |
| `cudaGraphLaunch` calls | `369` |

当前判断：

- 这是目前最接近 Stage 4 同形状的 Nsight Systems 证据：`AWQ-INT4 64K + output=512` 的请求窗口内，GPU kernel time 仍由 Marlin 和 FlashAttention 主导。
- 这份报告能回答请求窗口内的 CUDA API、GPU kernel、memops 和 CUDA graph 情况；相比 4.2 的 server 短请求，它不再被启动、compile、warmup 主体污染。
- 这份报告仍不能替代 server-side scheduler queue 分析，因为它使用 offline `LLM.generate()`，没有 HTTP server、网关和多请求排队链路。
- `cudaLaunchKernel` API time 很高，说明后续值得继续用 Nsight Systems GUI 或 SQLite 细查 launch gap 和 CPU/GPU 重叠，但不能仅凭 summary 判断 GPU idle。

### 4.4 Server-side 请求窗口 capture：`AWQ-INT4 64K + output=512, concurrency=2`

为了补 4.3 缺少 server scheduler 链路的问题，本轮又用 `nsys launch/start/stop` 做了一次 server-side capture：

```text
container: qwen36-27b-awq-int4-nsys-server-c2
model: Qwen3.6-27B-AWQ-INT4
server: vLLM OpenAI API
workload: prompt≈64K, max_tokens=512, concurrency=2
capture control: nsys launch -> API ready -> nsys start -> concurrent requests -> nsys stop
trace: cuda,nvtx,osrt
cuda graph trace: graph
```

产物：

```text
/tmp/llmnode-nsys-vllm-server-awq-64k-c2-512.nsys-rep
/tmp/llmnode-nsys-vllm-server-awq-64k-c2-512.sqlite
/tmp/llmnode-nsys-vllm-server-awq-64k-c2-512-summary.json
```

注意：宿主端口 `15675` 显示有 Docker 映射，但本轮从宿主访问失败；最终在容器内通过 `127.0.0.1:8000` 发请求。这个路径仍覆盖 vLLM API server、engine scheduler 和 GPU workload，但不覆盖宿主到容器的网络路径。

请求结果：

| 字段 | 值 |
|---|---:|
| target prompt tokens | `65,536` |
| actual prompt tokens | `65,535` |
| max tokens | `512` |
| concurrency | `2` |
| wall seconds | `79.22 s` |
| request 0 | `200 OK`, `512` completion tokens, `79.22 s`, `finish_reason=length` |
| request 1 | `200 OK`, `369` completion tokens, `73.45 s`, `finish_reason=stop` |

启动侧证据：

| 字段 | 值 |
|---|---:|
| model loading memory | `19.05 GiB` |
| model loading time | `11.773987 s` |
| torch.compile time | `100.08 s` |
| initial profiling / warmup | `123.15 s` |
| available KV cache memory | `22.38 GiB` |
| GPU KV cache size | `90,944 tokens` |
| max concurrency for `262,144` tokens/request | `1.38x` |
| CUDA graph pool memory | `0.08 GiB actual / 0.11 GiB estimated` |

vLLM scheduler 日志：

| Time | Prompt throughput | Generation throughput | Running | Waiting | GPU KV cache usage |
|---|---:|---:|---:|---:|---:|
| `02:18:14` | `6553.5 tok/s` | `0.4 tok/s` | `2` | `0` | `28.3%` |
| `02:18:24` | `0.0 tok/s` | `0.2 tok/s` | `2` | `0` | `32.8%` |
| `02:18:34` | `6552.8 tok/s` | `21.9 tok/s` | `2` | `0` | `37.3%` |
| `02:18:44` | `0.0 tok/s` | `51.3 tok/s` | `1` | `0` | `18.9%` |

结论：

- `concurrency=2` 下两个 64K 请求都进入 Running，没有出现 Waiting 队列。
- GPU KV cache usage 峰值约 `37.3%`，本轮 c2 没有触到 KV 容量上限。
- 这份 c2 报告本身不足以证明 scheduler queue 堵塞，因此后续又补了 4.5 的 `concurrency=4` capture。

`nsys stats` 摘要：

Top CUDA kernels：

| Kernel family | Total time | Instances | 占 GPU kernel time | 说明 |
|---|---:|---:|---:|---|
| Marlin | `38,574.43 ms` | `32,768` | `68.3%` | AWQ 量化 GEMM 主热点 |
| FlashAttention splitkv | `13,300.27 ms` | `272` | `23.5%` | 长上下文 attention 主热点 |
| Ampere FP16 GEMM | `846.68 ms` | `1,296` | `1.5%` | 次级 GEMM |
| merge inverse | `574.30 ms` | `816` | `1.0%` | 次级 kernel |
| `chunk_fwd_kernel_o` | `415.86 ms` | `816` | `0.7%` | hybrid / chunk 相关 |

Top CUDA APIs：

| API | Total time | Calls | 占 CUDA API time |
|---|---:|---:|---:|
| `cudaLaunchKernel` | `38,073.34 ms` | `51,618` | `42.3%` |
| `cudaEventSynchronize` | `35,828.14 ms` | `1,578` | `39.8%` |
| `cuLaunchKernelEx` | `9,084.09 ms` | `8,658` | `10.1%` |
| `cuLaunchKernel` | `4,904.99 ms` | `7,200` | `5.5%` |
| `cudaMemcpyAsync` | `965.30 ms` | `12,562` | `1.1%` |
| `cudaGraphLaunch` | `103.21 ms` | `576` | `0.1%` |

CUDA memops：

| Copy kind | Total time | Count | Total size |
|---|---:|---:|---:|
| Device-to-Device | `97.84 ms` | `5,985` | `78,665.798 MB` |
| Host-to-Device | `15.03 ms` | `6,049` | `65.436 MB` |
| Device-to-Host | `0.90 ms` | `528` | `0.004 MB` |

CUDA graph evidence：

| Event | Count |
|---|---:|
| `CUPTI_ACTIVITY_KIND_GRAPH_TRACE` rows | `576` |
| `cudaGraphLaunch` calls | `576` |

当前判断：

- server-side c2 和 offline c1 的 Nsight 结论一致：请求窗口内 GPU kernel time 仍由 Marlin 和 FlashAttention 主导。
- c2 证明了并发运行和请求间重叠窗口，但不单独构成 scheduler queue 证据。
- 明确的 Waiting 队列证据见 4.5 的 `concurrency=4` capture。

### 4.5 Server-side 请求窗口 capture：`AWQ-INT4 64K + output=512, concurrency=4`

为了明确观察 scheduler queue，本轮继续做了 server-side c4 capture：

```text
container: qwen36-27b-awq-int4-nsys-server-c4
model: Qwen3.6-27B-AWQ-INT4
server: vLLM OpenAI API
workload: prompt≈64K, max_tokens=512, concurrency=4
capture control: nsys launch -> API ready -> nsys start -> concurrent requests -> nsys stop
trace: cuda,nvtx,osrt
cuda graph trace: graph
```

产物：

```text
/tmp/llmnode-nsys-vllm-server-awq-64k-c4-512.nsys-rep
/tmp/llmnode-nsys-vllm-server-awq-64k-c4-512.sqlite
/tmp/llmnode-nsys-vllm-server-awq-64k-c4-512-summary.json
```

请求结果：

| 字段 | 值 |
|---|---:|
| target prompt tokens | `65,536` |
| actual prompt tokens | `65,535` |
| max tokens | `512` |
| concurrency | `4` |
| wall seconds | `136.84 s` |
| request 0 | `200 OK`, `369` completion tokens, `136.84 s`, `finish_reason=stop` |
| request 1 | `200 OK`, `369` completion tokens, `133.32 s`, `finish_reason=stop` |
| request 2 | `200 OK`, `369` completion tokens, `133.55 s`, `finish_reason=stop` |
| request 3 | `200 OK`, `369` completion tokens, `133.72 s`, `finish_reason=stop` |

启动侧证据：

| 字段 | 值 |
|---|---:|
| model loading memory | `19.05 GiB` |
| model loading time | `11.496300 s` |
| torch.compile time | `95.60 s` |
| initial profiling / warmup | `123.74 s` |
| available KV cache memory | `22.38 GiB` |
| GPU KV cache size | `90,944 tokens` |
| max concurrency for `262,144` tokens/request | `1.38x` |
| CUDA graph pool memory | `0.08 GiB actual / 0.11 GiB estimated` |

vLLM scheduler 日志：

| Time | Prompt throughput | Generation throughput | Running | Waiting | GPU KV cache usage |
|---|---:|---:|---:|---:|---:|
| `02:30:06` | `6553.1 tok/s` | `0.1 tok/s` | `2` | `2` | `21.7%` |
| `02:30:16` | `0.0 tok/s` | `0.3 tok/s` | `2` | `2` | `28.3%` |
| `02:30:26` | `0.0 tok/s` | `0.3 tok/s` | `2` | `2` | `35.2%` |
| `02:30:36` | `6553.2 tok/s` | `0.4 tok/s` | `3` | `1` | `42.5%` |
| `02:30:46` | `0.0 tok/s` | `0.6 tok/s` | `3` | `1` | `49.4%` |
| `02:30:56` | `0.0 tok/s` | `0.4 tok/s` | `3` | `1` | `53.9%` |
| `02:31:06` | `6553.3 tok/s` | `0.7 tok/s` | `4` | `0` | `61.2%` |
| `02:31:16` | `0.0 tok/s` | `0.9 tok/s` | `4` | `0` | `68.0%` |
| `02:31:26` | `0.0 tok/s` | `0.6 tok/s` | `4` | `0` | `72.5%` |
| `02:31:36` | `6553.1 tok/s` | `99.8 tok/s` | `4` | `0` | `74.7%` |

结论：

- `concurrency=4` 明确制造出 Waiting 队列，开始阶段为 `Running=2 / Waiting=2`，随后变为 `Running=3 / Waiting=1`，最后进入 `Running=4 / Waiting=0`。
- KV cache usage 峰值约 `74.7%`，和 Stage 4 AWQ c4 profiler 日志方向一致。
- c4 请求的首段 generation throughput 很低，直到最后阶段才升到 `99.8 tok/s`，说明长 prefill 和排队阶段仍主导用户等待。

`nsys stats` 摘要：

Top CUDA kernels：

| Kernel family | Total time | Instances | 占 GPU kernel time | 说明 |
|---|---:|---:|---:|---|
| Marlin | `78,109.16 ms` | `65,792` | `68.5%` | AWQ 量化 GEMM 主热点 |
| FlashAttention splitkv | `27,405.82 ms` | `528` | `24.0%` | 长上下文 attention 主热点 |
| merge inverse | `1,163.97 ms` | `1,584` | `1.0%` | 次级 kernel |
| `chunk_gated_delta_rule_fwd_kernel_h_blockdim64` | `873.28 ms` | `1,584` | `0.8%` | hybrid / chunk 相关 |
| `chunk_fwd_kernel_o` | `824.02 ms` | `1,584` | `0.7%` | hybrid / chunk 相关 |

Top CUDA APIs：

| API | Total time | Calls | 占 CUDA API time |
|---|---:|---:|---:|
| `cudaLaunchKernel` | `78,734.77 ms` | `88,531` | `48.2%` |
| `cudaEventSynchronize` | `53,134.89 ms` | `1,199` | `32.5%` |
| `cuLaunchKernelEx` | `18,501.38 ms` | `14,316` | `11.3%` |
| `cuLaunchKernel` | `10,060.63 ms` | `14,850` | `6.2%` |
| `cudaMemcpyAsync` | `1,874.21 ms` | `10,689` | `1.1%` |
| `cudaGraphLaunch` | `90.08 ms` | `369` | `0.1%` |

CUDA memops：

| Copy kind | Total time | Count | Total size |
|---|---:|---:|---:|
| Device-to-Device | `184.25 ms` | `5,396` | `157,346.952 MB` |
| Host-to-Device | `15.10 ms` | `4,891` | `112.198 MB` |
| Device-to-Host | `0.66 ms` | `402` | `0.006 MB` |

CUDA graph evidence：

| Event | Count |
|---|---:|
| `CUPTI_ACTIVITY_KIND_GRAPH_TRACE` rows | `369` |
| `cudaGraphLaunch` calls | `369` |

时间线补充：

| 指标 | 值 | 含义 |
|---|---:|---|
| kernel span | `134,422.68 ms` | 从第一个 kernel 开始到最后一个 kernel 结束 |
| request wall time | `136,844.11 ms` | 4 个并发请求总墙钟时间 |
| kernel span / request wall | `98.2%` | 请求窗口大部分时间都有 GPU kernel 活动 |
| total inter-kernel gap | `20,432.92 ms` | kernel 序列内部累计空洞 |
| gap / kernel span | `15.2%` | kernel 时间线内部仍有可见空洞 |
| gaps > `1 ms` | `387` | 中小 launch/sync 空洞不少 |
| gaps > `10 ms` | `380` | 说明不是只存在极少数超长空洞 |
| gaps > `100 ms` | `9` | 阶段切换或同步更明显 |
| gaps > `1000 ms` | `6` | 对应长 prefill / queueing / decode 切换类空洞 |
| active kernel streams | `1` | 只有 stream `7` 承载主要 kernel |

当前判断：

- c4 server-side Nsight 证据补齐了 scheduler queue：本轮能明确看到 Waiting 队列和 Running/Waiting 转换。
- kernel 占比仍高度稳定：c1 offline、c2 server、c4 server 都是 Marlin 约 `68%`，FlashAttention 约 `23-24%`。
- c4 请求窗口虽然几乎被 GPU kernel 覆盖，但 kernel 内部累计空洞仍有约 `20.43 s`；这说明问题不是“GPU 大段完全空闲”，而是大量细碎 launch/sync gap 叠加。
- 当前 trace 中所有主要 kernel 都落在同一个 CUDA stream 上，没有看到多流 kernel overlap 证据；因此 “stream overlap 不足” 在这份 trace 上更像“没有被实际用起来”，而不是“多流已经存在但利用率低”。
- 当前 Nsight Systems 已覆盖 CPU/GPU timeline 数据、CUDA API、kernel、memops、CUDA graph 和 server scheduler 日志；还未完成的是 Nsight Compute 的 SM occupancy / memory bandwidth / stall。

### 4.6 GPU Metrics 权限验证

为了确认低层指标是否只能依赖 `ncu`，还是也能通过 `nsys gpu metrics` 拿到，本轮又做了一次最小 smoke：

```text
tool: nsys profile
extra switches: --gpu-metrics-devices=...
workload: container 内最小 CUDA matmul
```

结果：

```text
Illegal --gpu-metrics-devices argument: cuda-visible.
Insufficient privilege, see https://developer.nvidia.com/ERR_NVGPUCTRPERM.
```

当前含义：

- `ncu` 采 SM occupancy / memory bandwidth 会被 `ERR_NVGPUCTRPERM` 阻止。
- `nsys gpu metrics` 这条替代路径也被同一类 GPU performance counter 权限阻止。
- 因此在当前机器权限不变的前提下，`SM occupancy / memory bandwidth / stall` 仍然无法继续补齐。

### 4.7 Nsight Compute 权限放开后的真实进展

2026-06-10 再次复查宿主机参数：

```bash
cat /proc/driver/nvidia/params | rg 'RmProfilingAdminOnly|RestrictProfiling'
```

结果：

```text
RmProfilingAdminOnly: 0
```

这说明旧的 GPU performance counter 权限阻塞已经消失。随后又做了三类 `ncu` 真实尝试：

1. `ncu` 包裹真实 `AWQ-INT4 64K + output=512` offline workload：
   - `ncu` 能连接真实 Python / EngineCore 进程；
   - 但 vLLM 在 warmup 结束后只剩 `5.06 GiB` 可用 KV cache；
   - 对 `max_model_len=262144` 的初始化直接失败，报错估计最大可服务长度仅约 `79,968`。
2. 同一路径把 `max_model_len` 收到 `70,000`：
   - 仍然能连接真实进程；
   - 但 warmup 后可用 KV cache 进一步只有 `3.19 GiB`；
   - 初始化仍失败，估计最大可服务长度约 `49,392`。
3. 切到更小但仍是真实 vLLM generate 链路的 `AWQ-INT4 16K + output=512`：
   - 在释放正式 AWQ 服务占卡后，`max_model_len=32768` 可以完整跑通；
   - 请求侧结果为 `16384` prompt tokens、`512` completion tokens、`finish_reason=length`；
   - 端到端输出吞吐约 `10.17 tok/s`；
   - 但第一次使用 `cudaProfilerStart/Stop + --profile-from-start off` 时，`ncu` 最终给出 `No kernels were profiled`，说明这条 capture 组合对当前 vLLM workload 不可靠。
4. 对同一个 `16K + output=512` 真实 workload 改用更窄的 kernel filter：
   - `--kernel-name "regex:.*Marlin.*"`；
   - `--section LaunchStats --section Occupancy --section MemoryWorkloadAnalysis`；
   - `--launch-count 6 --profile-from-start on`。
   这次 `ncu` 已能稳定进入真实 kernel profiling，并对 `Marlin` 输出 section。

本轮拿到的一组代表性 `Marlin` 指标如下：

| 指标 | 结果 |
|---|---|
| kernel family | `Marlin<...>` |
| launch shape | `grid=(108,1,1), block=(256,1,1)` |
| stream | `Stream 7` |
| registers per thread | `255` |
| dynamic shared memory per block | `166.91 KiB` |
| waves per SM | `1` |
| theoretical occupancy | `12.5%` |
| achieved occupancy | `12.5%` |
| achieved active warps per SM | `8.0` |
| memory throughput | `447.53 - 490.95 GB/s` |
| max bandwidth | `23.79% - 25.37%` |
| mem busy | `25.72% - 25.81%` |
| mem pipes busy | `11.43% - 11.47%` |
| L2 hit rate | `62.52% - 62.54%` |
| local/shared spilling | `0` |

`ncu` 的自动建议也比较稳定：

- 当前 kernel 每个 SM 只能驻留 `1` 个 block；
- occupancy 主要受 `registers` 和 `shared memory` 双重限制；
- 如果存在 `__syncthreads()`，建议至少提高到每个 SM `2` 个 block，避免单 block 等待时硬件空转。

5. 对同一个 `16K + output=512` 真实 workload 再改用 attention 过滤：
   - `--kernel-name "regex:.*flash.*|.*Flash.*|.*fmha.*|.*attention.*"`；
   - `--section LaunchStats --section Occupancy --section MemoryWorkloadAnalysis`；
   - `--launch-count 6 --profile-from-start on`。
   这次 `ncu` 已能稳定进入真实 `flash::flash_fwd_kernel` profiling，并输出 section。

本轮拿到的一组代表性 `FlashAttention` 指标如下：

| 指标 | 结果 |
|---|---|
| kernel family | `flash_fwd_kernel<...>` |
| launch shape | `grid=(512,1,16), block=(128,1,1)` |
| stream | `Stream 7` |
| registers per thread | `255` |
| dynamic shared memory per block | `49.15 KiB` |
| waves per SM | `37.93` |
| theoretical occupancy | `12.5%` |
| achieved occupancy | `12.43%` |
| achieved active warps per SM | `7.96` |
| memory throughput | `19.09 - 19.29 GB/s` |
| max bandwidth | `42.34% - 42.35%` |
| mem busy | `55.01%` |
| mem pipes busy | `22.90%` |
| L2 hit rate | `98.56% - 98.69%` |
| L2 sector promotion misses | `46.80% - 49.27%` |
| local/shared spilling | `0` |

当前判断：

- Nsight Compute 已经不是“权限没开”的问题。`ncu` 现在能真实连接 vLLM workload。
- 新的真实阻塞点是两层：
  1. `ncu` replay / instrumentation 会显著放大 vLLM 冷启动与 warmup 的显存开销，使 `64K` 同形状 workload 在初始化阶段就失去足够的 KV cache 预算；
  2. 即使 `16K + 512` 这类较小真实 workload 能完整跑通，`cudaProfilerStart/Stop` 与当前 `ncu` capture 组合也可能抓不到 kernel。
- 当前已经补齐一部分最关键的低层证据：真实 vLLM workload 下的 `Marlin` kernel occupancy / memory workload / launch stats。
- 当前已经补齐另一部分关键低层证据：真实 vLLM workload 下的 `FlashAttention` kernel occupancy / memory workload / launch stats。
- 仍未补齐的是 `64K + 512` 同形状点上的 Nsight Compute 低层指标。
- 因此后续 Nsight Compute 的正确推进方向已经从“开权限”切换为：
  1. 优先尝试 attach 到已启动的服务进程，而不是每次从冷启动包整段 vLLM；
  2. 缩小 kernel filter / launch filter，避免整段 replay 带来的超长耗时；
  3. 在 `16K + 512` 这种已知能跑通的真实 workload 上已经拿到 Marlin 与 FlashAttention section，下一步回到 `64K` 同形状代表点。

## 5. Nsight 后续执行清单

### 5.1 Nsight Systems

当前 `nsys` 已跑通真实 vLLM server 短请求 timeline，已完成 `AWQ-INT4 64K + output=512` offline 请求窗口 capture，也已完成 server-side `concurrency=2/4` 请求窗口 capture。c4 已经制造出 Waiting 队列；`nsys gpu metrics` 的旧权限阻塞已不再是唯一关键问题，但当前主要精力应先放在已有 trace 的时间线解释和 `ncu` 的稳定 capture 方法上。下一步如果继续 Nsight Systems，应转向更细的 timeline 解释：

| 选项 | 目标 |
|---|---|
| 在 Nsight Systems GUI 或 SQLite 中细查 launch gap | 判断 `cudaLaunchKernel` / `cudaEventSynchronize` 高占比是否对应 CPU launch 空洞 |
| 对比 c2 与 c4 时间线 | 解释 Running/Waiting 转换对 GPU kernel 排布的影响 |
| 在 trace 中加入 NVTX 或阶段标签 | 区分 prefill / decode / warmup |

最小 capture 成功标准：

- 能导出 `.nsys-rep` 或 `.sqlite` 报告。
- 能看到 CPU/GPU timeline。
- 能定位 prefill / decode 期间 kernel 排布、launch gap 和 stream overlap。
- 若目标是 scheduler queue，必须使用 server 或多请求 workload；offline generate 只能作为 kernel/API/memops 证据。

### 5.2 Nsight Compute

Nsight Compute 可以先用宿主真实二进制做工具链验证：

```bash
/opt/anaconda3/pkgs/nsight-compute-2026.1.1.2-h934865d_0/nsight-compute-2026.1.1/ncu --version
```

建议后续采样时设置可写 `HOME`，避免 section 文件 warning 干扰日志：

```bash
HOME=/tmp \
/opt/anaconda3/pkgs/nsight-compute-2026.1.1.2-h934865d_0/nsight-compute-2026.1.1/ncu ...
```

下一步对 Marlin 或 FlashAttention 代表 kernel 做最小采样。目标不是替代 torch profiler，而是补齐这些指标：

| 指标 | 用途 |
|---|---|
| SM occupancy | 判断 kernel 是否受 occupancy 限制 |
| memory throughput | 判断是否接近 HBM/L2 带宽瓶颈 |
| warp stall reason | 判断等待原因 |
| Tensor Core / pipe utilization | 判断算力利用是否充分 |
| launch / section report | 确认采样权限和报告导出路径 |

当前前置条件：

| 条件 | 状态 |
|---|---|
| 宿主 Nsight Compute 真实二进制 | 已找到，可启动 |
| vLLM 容器内 CUDA | 可用 |
| `ncu` 挂载进 vLLM 容器 | 可启动 |
| GPU performance counter 权限 | 已满足，`RmProfilingAdminOnly: 0` |
| `64K + 512` 冷启动同形状采样 | 未完成；当前被 profiler 冷启动额外显存开销卡住 |
| `16K + 512` 真实 workload 完整运行 | 已完成 |
| Marlin kernel section | 已完成，已拿到 Occupancy / Memory Workload / LaunchStats |
| FlashAttention kernel section | 已完成，已拿到 Occupancy / Memory Workload / LaunchStats |

## 6. 下一步

1. 暂不推进 `AWQ-INT4 + FP8 KV cache` 作为可上线配置；若继续研究，需要先复测 `max_tokens` 更长或关闭 reasoning 混入的质量用例，确认新增失败是否来自 FP8 KV 精度还是输出截断/解析行为。
2. 如继续 Nsight Systems，优先深入已有 c4 `.sqlite/.nsys-rep`，细查 launch gap、stream overlap 和 Running/Waiting 转换期间的 GPU kernel 排布，而不是继续盲目加并发。
3. Nsight Compute 不再先纠结权限，直接围绕 capture 方法收敛：
   - 优先尝试 attach 到已启动的 vLLM 服务进程，避免冷启动 replay 挤掉 `64K` 代表点的 KV cache；
   - 继续把当前已验证的 kernel-filter capture 方法迁移到 `64K + output=512` 同形状点；
   - 确认低层指标是否和 Nsight Systems / torch profiler 的 Marlin + FlashAttention 热点判断一致。
