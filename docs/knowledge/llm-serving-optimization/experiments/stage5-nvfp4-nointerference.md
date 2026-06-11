# 第五阶段实验报告：NVFP4 无干扰复测与 FP8 KV cache 对照

> 文档定位：项目知识库中的 LLM serving 优化实验报告，不属于 `llmnode` 项目蓝图、契约或正式路线图。  
> 实验目标：复查 Stage 2 中受外部 GPU 负载干扰的 `NVFP4 64K + output=512` 结果，并对 `AWQ-INT4 + FP8 KV cache` 做容量和速度对照。  
> 更新时间：2026-06-09。  
> 当前结论状态：`NVFP4 gpu_memory_utilization=0.55/0.6` 均已完成无外部 GPU 进程复测；`AWQ-INT4 + FP8 KV cache` 已完成启动容量验证和 `64K + output=512` benchmark。质量回归还没有做。

相关专题：

- 第二阶段历史结果见 [stage2-vllm-prefill-decode.md](./stage2-vllm-prefill-decode.md)。
- AWQ profiler 证据见 [stage4-awq-profiler.md](./stage4-awq-profiler.md)。
- KV cache 解释见 [kv-cache.md](../performance/kv-cache.md)。
- vLLM 参数见 [vllm-deep-dive.md](../serving/vllm-deep-dive.md)。

## 1. 一页结论

本阶段完成了 `NVFP4 gpu_memory_utilization=0.55/0.6` 的无干扰复测：

| profile | gpu_memory_utilization | prompt | output cap | success | latency avg | completion tok/s avg | 外部 GPU 进程 |
|---|---:|---:|---:|---:|---:|---:|---|
| `vllm_qwen36-27b-nvfp4` | `0.55` | `64K` | `512` | `3/3` | `39,020.31 ms` | `12.71` | `0 MiB` |
| `vllm_qwen36-27b-nvfp4` | `0.6` | `64K` | `512` | `3/3` | `38,120.15 ms` | `11.81` | `0 MiB` |

和 Stage 2 受干扰结果相比：

| 条件 | latency avg | completion tok/s avg | 说明 |
|---|---:|---:|---|
| Stage 2，`0.55`，受干扰 | `58,132.42 ms` | `7.47` | 当时有非本任务 GPU 进程约 `21.9 GiB` |
| Stage 5，`0.55`，无干扰 | `39,020.31 ms` | `12.71` | benchmark 采样中 `other_processes_total_mb=0` |
| Stage 5，`0.6`，无干扰 | `38,120.15 ms` | `11.81` | benchmark 采样中 `other_processes_total_mb=0` |

结论：

1. Stage 2 的 NVFP4 速度结论确实被外部 GPU 负载显著污染。
2. 无干扰后，`NVFP4 0.55/0.6` 的 `64K + output=512` 端到端输出吞吐分别为 `12.71 / 11.81 tok/s`，已经接近或超过 Stage 2 的 `AWQ-INT4 64K + output=512` 结果 `10.88 tok/s`。
3. `0.6` 的明确收益仍然是容量：可用 KV cache 从 `17.38 GiB` 提到 `21.34 GiB`，KV tokens 从 `70,560` 提到 `87,024`，256K max concurrency 从 `1.07x` 提到 `1.32x`。本轮没有证明它比 `0.55` 更快。
4. `AWQ-INT4 + FP8 KV cache` 可启动，KV tokens 从普通 AWQ 的 `90,944` 提到 `178,752`，256K max concurrency 从 `1.38x` 提到 `2.68x`。
5. `AWQ-INT4 + FP8 KV cache` 在本轮 `64K + output=512` 单并发 benchmark 中平均 `43,461.40 ms`、`9.52 tok/s`，低于普通 AWQ Stage 2 的 `36,282.32 ms`、`10.88 tok/s`。因此它当前更像容量方案，不是单请求加速方案。
6. FP8 KV cache 质量回归还没有做，不能把它直接写成可上线配置。

## 2. `0.55` 无干扰复测

启动命令：

```bash
VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE=vllm_qwen36-27b-nvfp4 \
  /home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control start --service vllm --daemon
```

启动日志：

```text
runtime/logs/qwen36-27b-nvfp4-vllm-20260609-154408.log
```

启动侧证据：

| 字段 | 值 |
|---|---:|
| vLLM version | `0.19.2rc1.dev134+gfe9c3d6c5` |
| effective `gpu_memory_utilization` | `0.55` |
| NVFP4 kernel | `MarlinNvFp4LinearKernel` |
| model loading memory | `24.05 GiB` |
| available KV cache memory | `17.38 GiB` |
| GPU KV cache size | `70,560 tokens` |
| max concurrency for `262,144` tokens/request | `1.07x` |
| API startup | success |

benchmark 命令：

```bash
VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE=vllm_qwen36-27b-nvfp4 \
  /home/heshan/.conda/envs/paper2any/bin/python scripts/benchmark_backend.py \
  --profile vllm_qwen36-27b-nvfp4 \
  --targets 65536 \
  --max-tokens 512 \
  --concurrency 1 \
  --warmup-runs 0 \
  --measure-runs 3 \
  --sample-interval 2 \
  --output-dir runtime/data/benchmarks/manual-stage5-nvfp4-nointerference-gpu055
```

结果目录：

```text
runtime/data/benchmarks/manual-stage5-nvfp4-nointerference-gpu055/20260609-154941-vllm_qwen36-27b-nvfp4/
```

汇总：

| prompt | success | latency avg | latency p50 | latency min | latency max | completion tok/s avg | completion tok/s p50 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| `64K` | `3/3` | `39,020.31 ms` | `38,836.87 ms` | `37,505.05 ms` | `40,719.01 ms` | `12.71` | `12.57` |

测量轮次：

| latency | completion | finish_reason | completion tok/s |
|---:|---:|---|---:|
| `40,719.01 ms` | `512` | `length` | `12.57` |
| `37,505.05 ms` | `464` | `stop` | `12.37` |
| `38,836.87 ms` | `512` | `length` | `13.18` |

benchmark 采样证据显示：

- `other_processes_total_mb=0`
- `other_processes=[]`
- 后端进程显存约 `43.5-45.9 GiB`
- vLLM 周期性指标中出现 `GPU KV cache usage: 24.0%`

因此本条可以按“无外部 GPU 负载复测”使用。

## 3. `0.6` 无干扰复测

启动命令：

```bash
VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE=vllm_qwen36-27b-nvfp4 \
VLLM_CLAUDE_VLLM_GPU_MEMORY_UTILIZATION=0.6 \
  /home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control start --service vllm --daemon
```

启动日志：

```text
runtime/logs/qwen36-27b-nvfp4-vllm-20260609-162615.log
```

启动侧证据：

| 字段 | 值 |
|---|---:|
| effective `gpu_memory_utilization` | `0.6` |
| NVFP4 kernel | `MarlinNvFp4LinearKernel` |
| model loading memory | `24.05 GiB` |
| available KV cache memory | `21.34 GiB` |
| GPU KV cache size | `87,024 tokens` |
| max concurrency for `262,144` tokens/request | `1.32x` |
| API startup | success |

结果目录：

```text
runtime/data/benchmarks/manual-stage5-nvfp4-nointerference-gpu06/20260609-163107-vllm_qwen36-27b-nvfp4/
```

汇总：

| prompt | success | latency avg | latency p50 | latency min | latency max | completion tok/s avg | completion tok/s p50 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| `64K` | `3/3` | `38,120.15 ms` | `37,538.19 ms` | `35,989.88 ms` | `40,832.38 ms` | `11.81` | `12.36` |

测量轮次：

| latency | completion | finish_reason | completion tok/s |
|---:|---:|---|---:|
| `40,832.38 ms` | `512` | `length` | `12.54` |
| `37,538.19 ms` | `464` | `stop` | `12.36` |
| `35,989.88 ms` | `379` | `stop` | `10.53` |

benchmark 采样证据显示：

- `other_processes_total_mb=0`
- `other_processes=[]`
- 后端进程显存约 `47.5-50.0 GiB`
- vLLM 周期性指标中出现 `GPU KV cache usage: 19.6%`

## 4. AWQ-INT4 + FP8 KV cache

本轮补了 vLLM 正式入口的 `kv_cache_dtype` 透传，并新增实验 profile：

```text
config/backends/vllm_qwen36-27b-awq-int4-fp8-kv.yaml
```

启动命令：

```bash
VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE=vllm_qwen36-27b-awq-int4-fp8-kv \
  /home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control start --service vllm --daemon
```

启动日志：

```text
runtime/logs/qwen36-27b-awq-int4-fp8-kv-vllm-20260609-163417.log
```

启动侧证据：

| 字段 | 值 |
|---|---:|
| effective `kv_cache_dtype` | `fp8` |
| AWQ kernel | `MarlinLinearKernel for CompressedTensorsWNA16` |
| model loading memory | `19.05 GiB` |
| available KV cache memory | `22.01 GiB` |
| GPU KV cache size | `178,752 tokens` |
| max concurrency for `262,144` tokens/request | `2.68x` |
| API startup | success |

和普通 AWQ 对比：

| profile | kv_cache_dtype | available KV cache | KV tokens | 256K max concurrency |
|---|---|---:|---:|---:|
| `vllm_qwen36-27b-awq-int4` | `auto` | `22.38 GiB` | `90,944` | `1.38x` |
| `vllm_qwen36-27b-awq-int4-fp8-kv` | `fp8` | `22.01 GiB` | `178,752` | `2.68x` |

benchmark 命令：

```bash
VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE=vllm_qwen36-27b-awq-int4-fp8-kv \
  /home/heshan/.conda/envs/paper2any/bin/python scripts/benchmark_backend.py \
  --profile vllm_qwen36-27b-awq-int4-fp8-kv \
  --targets 65536 \
  --max-tokens 512 \
  --concurrency 1 \
  --warmup-runs 0 \
  --measure-runs 3 \
  --sample-interval 2 \
  --output-dir runtime/data/benchmarks/manual-stage6-awq-fp8-kv
```

结果目录：

```text
runtime/data/benchmarks/manual-stage6-awq-fp8-kv/20260609-163920-vllm_qwen36-27b-awq-int4-fp8-kv/
```

汇总：

| prompt | success | latency avg | latency p50 | latency min | latency max | completion tok/s avg | completion tok/s p50 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| `64K` | `3/3` | `43,461.40 ms` | `43,952.99 ms` | `41,668.70 ms` | `44,762.50 ms` | `9.52` | `9.34` |

测量轮次：

| latency | completion | finish_reason | completion tok/s |
|---:|---:|---|---:|
| `44,762.50 ms` | `418` | `stop` | `9.34` |
| `43,952.99 ms` | `490` | `stop` | `11.15` |
| `41,668.70 ms` | `336` | `stop` | `8.06` |

benchmark 采样证据显示：

- `other_processes_total_mb=0`
- `other_processes=[]`
- vLLM 周期性指标中出现 `GPU KV cache usage: 9.8%`

判断：

- FP8 KV cache 是 KV 容量和 attention/KV 访存实验，不应期待它解决 Stage 4 里已经看到的 Marlin GEMM 主热点。
- 本轮容量收益明确，但单请求 `64K + output=512` 速度没有提升。
- 必须补质量回归，尤其长上下文、代码、数学和结构化输出；本报告没有验证质量。

## 5. 下一步

下一阶段建议：

1. 对 `NVFP4 0.55/0.6` 至少补一个同形状 torch profiler，与 Stage 4 AWQ profiler 对齐。
2. 对 `AWQ-INT4 + FP8 KV cache` 做最小质量回归，尤其长上下文、代码、数学和结构化输出。
3. 如果目标是提高服务容量，再测 `AWQ-INT4 + FP8 KV cache` 的 `concurrency=2/4`，而不是只看单请求速度。
4. 如果目标是解释并发 timeline，继续用 Nsight Systems 看 CPU/GPU 请求阶段重叠。
