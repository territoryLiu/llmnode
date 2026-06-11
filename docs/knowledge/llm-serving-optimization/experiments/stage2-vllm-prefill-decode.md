# 第二阶段实验报告：vLLM prefill / decode 与参数调优

> 文档定位：项目知识库中的 LLM serving 优化实验报告，不属于 `llmnode` 项目蓝图、契约或正式路线图。  
> 实验目标：在第一阶段 Qwen3.6-27B 量化基线之后，固定少数候选 profile，拉长输出长度，开始区分长上下文 prefill 压力和 decode 稳态表现。  
> 更新时间：2026-06-09。  
> 当前结论状态：第二阶段最小闭环已完成，已补 `AWQ-INT4 / NVFP4 + output=512` 重复测量、`NVFP4 gpu_memory_utilization=0.6` 对比，以及一个 `AWQ-INT4 64K + output=512` 流式 TTFT / TPOT 代表点；后续 Stage 4 已补 torch profiler top-kernel 证据。

相关专题：

- benchmark 口径见 [benchmark-methodology.md](../performance/benchmark-methodology.md)。
- KV cache 解释见 [kv-cache.md](../performance/kv-cache.md)。
- vLLM 参数见 [vllm-deep-dive.md](../serving/vllm-deep-dive.md)。
- 量化机制见 [quantization-deep-dive.md](../optimization/quantization-deep-dive.md)。
- 第一阶段基线见 [stage1-qwen27b.md](./stage1-qwen27b.md)。

## 1. 一页结论

本阶段围绕两个主候选 profile：

- `vllm_qwen36-27b-awq-int4`
- `vllm_qwen36-27b-nvfp4`

固定口径：

- 后端：`vLLM`
- GPU：按 A800 / Ampere 路线理解
- `max_model_len=262144`
- `max_num_seqs=4`
- `prompt tokens=16K / 64K`
- `max_tokens=512`
- `concurrency=1`
- benchmark 路径：直连后端 `http://127.0.0.1:15673`
- Python：`/home/heshan/.conda/envs/paper2any/bin/python`

本阶段最重要结论：

1. 第一阶段 `output=64` 的确偏短，更像“长 prefill 压力下的短输出体验指标”，不能直接代表 decode 稳态。
2. `output=512` 后，`completion tok/s` 明显上升，说明长 prompt 的固定 prefill 成本被更多输出 token 摊薄。
3. 重复测量后，`AWQ-INT4` 在 `16K/64K + output=512` 下仍明显快于本次 `NVFP4` 重复测量结果，同时保留更大的 KV cache 余量。
4. `AWQ-INT4 64K + output=512` 的流式测量显示 `TTFT=27,871.79 ms`、`TPOT=18.00 ms/token`、`E2E=37,071.76 ms`。这说明用户等待的主要部分在首 token 之前，也就是长上下文 prefill / 调度阶段，而不是 512 token decode 阶段本身。
5. `NVFP4 gpu_memory_utilization=0.6` 已确认生效，可用 KV cache 从 `17.38 GiB` 提升到 `21.36 GiB`，KV tokens 从 `70,560` 提升到 `87,024`，256K max concurrency 从 `1.07x` 提升到 `1.32x`。
6. 在本次有外部 GPU 进程干扰的环境下，`NVFP4 0.6` 没有体现速度收益；它的明确价值仍是容量和余量。

当前部署倾向：

> 对当前 A800 + Qwen3.6-27B + vLLM + 单并发长上下文场景，`AWQ-INT4` 是下一阶段更值得优先推进的候选；`NVFP4` 保留为长上下文容量和 FP4 路线对照，但在 A800 上不是原生 FP4 compute 路径。

需要保留的不确定性：

- 本阶段当时没有 Nsight / torch profiler top-kernel 证据；后续 Stage 4 已确认 `AWQ-INT4 64K + output=512` 单请求中 Marlin AWQ GEMM 是 prefill 和 decode 的最大 GPU 时间来源，FlashAttention 是主要次级热点。
- `NVFP4` 重复测量和 `0.6` 对比期间同机存在非本任务 GPU 进程，约占 `21.9 GiB` 显存，可能影响耗时和波动；因此 NVFP4 速度结论应按“受干扰环境下的实测”理解。
- 重复测量中模型有时提前 `stop`，实际 completion tokens 不总是 512；`completion tok/s` 仍是端到端输出吞吐，不等于纯 decode TPOT。

## 2. 启动侧证据

### 2.1 NVFP4，`gpu_memory_utilization=0.55`

日志：`runtime/logs/qwen36-27b-nvfp4-vllm-20260609-105623.log`

| 字段 | 值 |
|---|---:|
| vLLM version | `0.19.2rc1.dev134+gfe9c3d6c5` |
| served model | `qwen36-27b-nvfp4` |
| quantization | `compressed-tensors` |
| NVFP4 kernel | `MarlinNvFp4LinearKernel` |
| attention backend | `FLASH_ATTN` |
| chunked prefill | enabled, `max_num_batched_tokens=8192` |
| model loading memory | `24.05 GiB` |
| model loading time | `5.517451 s` |
| torch.compile time | `66.17 s` |
| initial profiling / warmup | `94.83 s` |
| available KV cache memory | `17.38 GiB` |
| GPU KV cache size | `70,560 tokens` |
| max concurrency for `262,144` tokens/request | `1.07x` |
| API startup | success |

### 2.2 NVFP4，`gpu_memory_utilization=0.6`

日志：`runtime/logs/qwen36-27b-nvfp4-vllm-20260609-111249.log`

| 字段 | 值 |
|---|---:|
| vLLM version | `0.19.2rc1.dev134+gfe9c3d6c5` |
| served model | `qwen36-27b-nvfp4` |
| effective `gpu_memory_utilization` | `0.6` |
| model loading memory | `24.05 GiB` |
| model loading time | `7.291438 s` |
| torch.compile time | `76.40 s` |
| initial profiling / warmup | `106.18 s` |
| available KV cache memory | `21.36 GiB` |
| GPU KV cache size | `87,024 tokens` |
| max concurrency for `262,144` tokens/request | `1.32x` |
| API startup | success |

说明：`llmnode.control status` 读取 profile 文件时仍显示 `gpu_memory_util 0.55`，但启动日志的 non-default args 明确包含 `gpu_memory_utilization: 0.6`，且 KV cache 规划结果也与 `0.6` 一致。因此本次参数是否生效以启动日志为准。

### 2.3 AWQ-INT4，`gpu_memory_utilization=0.55`

| 字段 | 值 |
|---|---:|
| vLLM version | `0.19.2rc1.dev134+gfe9c3d6c5` |
| served model | `qwen36-27b-awq-int4` |
| quantization | `compressed-tensors` |
| AWQ kernel | `MarlinLinearKernel for CompressedTensorsWNA16` |
| attention backend | `FLASH_ATTN` |
| chunked prefill | enabled, `max_num_batched_tokens=8192` |
| model loading memory | `19.05 GiB` |
| available KV cache memory | `22.38 GiB` |
| GPU KV cache size | `90,944 tokens` |
| max concurrency for `262,144` tokens/request | `1.38x` |
| API startup | success |

重要边界：

- vLLM 日志明确提示当前 GPU 没有原生 FP4 compute，NVFP4 走 weight-only FP4 + Marlin 路径。
- AWQ-INT4 走 `CompressedTensorsWNA16 + MarlinLinearKernel` 路径。
- `GPU KV cache size tokens` 是启动侧容量诊断，不应线性外推最大 prompt tokens。
- NVFP4 的 `1.07x` 表示 `256K` 单请求余量贴边；`0.6` 提升到 `1.32x` 后更适合作为 256K 单请求稳定性配置。

## 3. 重复测量结果

### 3.1 AWQ-INT4，`output=512`，`measure=3`

结果目录：

```text
runtime/data/benchmarks/manual-stage2-awq-output512-repeat/20260609-103257-vllm_qwen36-27b-awq-int4/
```

命令：

```bash
VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE=vllm_qwen36-27b-awq-int4 \
  /home/heshan/.conda/envs/paper2any/bin/python scripts/benchmark_backend.py \
  --profile vllm_qwen36-27b-awq-int4 \
  --targets 16384 65536 \
  --max-tokens 512 \
  --warmup-runs 1 \
  --measure-runs 3 \
  --sample-interval 2 \
  --output-dir runtime/data/benchmarks/manual-stage2-awq-output512-repeat
```

| prompt | success | latency avg | latency p50 | latency min | latency max | completion tok/s avg | completion tok/s p50 | tok/s min | tok/s max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `16K` | `3/3` | `12,741.69 ms` | `12,558.78 ms` | `11,702.88 ms` | `13,963.39 ms` | `32.75` | `32.73` | `29.99` | `35.52` |
| `64K` | `3/3` | `36,282.32 ms` | `36,067.51 ms` | `35,775.57 ms` | `37,003.88 ms` | `10.88` | `10.48` | `10.26` | `11.89` |

测量轮次：

| prompt | latency | completion | finish_reason | completion tok/s |
|---|---:|---:|---|---:|
| `16K` | `12,558.78 ms` | `411` | `stop` | `32.73` |
| `16K` | `13,963.39 ms` | `496` | `stop` | `35.52` |
| `16K` | `11,702.88 ms` | `351` | `stop` | `29.99` |
| `64K` | `37,003.88 ms` | `440` | `stop` | `11.89` |
| `64K` | `36,067.51 ms` | `378` | `stop` | `10.48` |
| `64K` | `35,775.57 ms` | `367` | `stop` | `10.26` |

### 3.2 NVFP4，`gpu_memory_utilization=0.55`，`output=512`，`measure=3`

结果目录：

```text
runtime/data/benchmarks/manual-stage2-nvfp4-output512-repeat-escalated/20260609-110445-vllm_qwen36-27b-nvfp4/
```

命令：

```bash
VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE=vllm_qwen36-27b-nvfp4 \
  /home/heshan/.conda/envs/paper2any/bin/python scripts/benchmark_backend.py \
  --profile vllm_qwen36-27b-nvfp4 \
  --targets 16384 65536 \
  --max-tokens 512 \
  --warmup-runs 1 \
  --measure-runs 3 \
  --sample-interval 2 \
  --output-dir runtime/data/benchmarks/manual-stage2-nvfp4-output512-repeat-escalated
```

| prompt | success | latency avg | latency p50 | latency min | latency max | completion tok/s avg | completion tok/s p50 | tok/s min | tok/s max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `16K` | `3/3` | `22,885.83 ms` | `22,908.62 ms` | `21,826.23 ms` | `23,922.62 ms` | `19.87` | `20.25` | `17.96` | `21.40` |
| `64K` | `3/3` | `58,132.42 ms` | `59,795.67 ms` | `54,704.69 ms` | `59,896.89 ms` | `7.47` | `7.89` | `5.98` | `8.55` |

测量轮次：

| prompt | latency | completion | finish_reason | completion tok/s |
|---|---:|---:|---|---:|
| `16K` | `23,922.62 ms` | `512` | `length` | `21.40` |
| `16K` | `21,826.23 ms` | `392` | `stop` | `17.96` |
| `16K` | `22,908.62 ms` | `464` | `stop` | `20.25` |
| `64K` | `59,795.67 ms` | `472` | `stop` | `7.89` |
| `64K` | `54,704.69 ms` | `327` | `stop` | `5.98` |
| `64K` | `59,896.89 ms` | `512` | `length` | `8.55` |

说明：

- 非提权运行曾全部失败于 `[Errno 1] Operation not permitted`，正式结果取提权重跑目录。
- 本次 NVFP4 重复测量期间，`nvidia-smi` 观测到非本任务 Python 进程约占 `21.9 GiB` 显存，可能影响延迟和波动。

### 3.3 重复测量对比

| profile | prompt | success | latency avg | completion tok/s avg | KV memory | KV tokens | 256K max concurrency |
|---|---:|---:|---:|---:|---:|---:|---:|
| `AWQ-INT4` | `16K` | `3/3` | `12,741.69 ms` | `32.75` | `22.38 GiB` | `90,944` | `1.38x` |
| `NVFP4` | `16K` | `3/3` | `22,885.83 ms` | `19.87` | `17.38 GiB` | `70,560` | `1.07x` |
| `AWQ-INT4` | `64K` | `3/3` | `36,282.32 ms` | `10.88` | `22.38 GiB` | `90,944` | `1.38x` |
| `NVFP4` | `64K` | `3/3` | `58,132.42 ms` | `7.47` | `17.38 GiB` | `70,560` | `1.07x` |

当前判断：

- 重复测量没有支持“NVFP4 在长输出下更快”的方向；本次证据更支持 AWQ-INT4。
- AWQ-INT4 的显存效率优势仍然成立：权重更小，KV 池更大，256K 单请求余量更好。
- NVFP4 在 A800 上的 FP4 路径不是原生 compute，日志已提示 compute-heavy workload 可能退化。
- 由于输出长度存在提前 `stop`，tok/s 对比仍不是纯 decode 对比；AWQ 的流式 TTFT / TPOT 更适合解释 prefill 和 decode 的分界。

## 4. `gpu_memory_utilization=0.55 / 0.6` 对比

### 4.1 启动容量

| gpu_memory_utilization | 可用 KV 显存 | KV tokens | 256K max concurrency | 判断 |
|---:|---:|---:|---:|---|
| `0.55` | `17.38 GiB` | `70,560` | `1.07x` | 256K 单请求贴边 |
| `0.6` | `21.36 GiB` | `87,024` | `1.32x` | 256K 单请求余量更稳 |

容量结论明确：

> `gpu_memory_utilization=0.6` 的主要收益是 KV cache 容量和 256K 请求余量，不是已观察到的速度提升。

### 4.2 `64K + output=512` 测速

`0.6` 结果目录：

```text
runtime/data/benchmarks/manual-stage2-nvfp4-output512-gpu06/20260609-112209-vllm_qwen36-27b-nvfp4/
```

命令：

```bash
VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE=vllm_qwen36-27b-nvfp4 \
VLLM_CLAUDE_VLLM_GPU_MEMORY_UTILIZATION=0.6 \
  /home/heshan/.conda/envs/paper2any/bin/python scripts/benchmark_backend.py \
  --profile vllm_qwen36-27b-nvfp4 \
  --targets 65536 \
  --max-tokens 512 \
  --warmup-runs 1 \
  --measure-runs 3 \
  --sample-interval 2 \
  --output-dir runtime/data/benchmarks/manual-stage2-nvfp4-output512-gpu06
```

| gpu_memory_utilization | prompt | success | latency avg | latency p50 | latency min | latency max | completion tok/s avg | completion tok/s p50 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `0.55` | `64K` | `3/3` | `58,132.42 ms` | `59,795.67 ms` | `54,704.69 ms` | `59,896.89 ms` | `7.47` | `7.89` |
| `0.6` | `64K` | `3/3` | `60,879.01 ms` | `60,885.72 ms` | `55,671.28 ms` | `66,080.03 ms` | `7.26` | `7.75` |

`0.6` 测量轮次：

| latency | completion | finish_reason | completion tok/s |
|---:|---:|---|---:|
| `66,080.03 ms` | `512` | `length` | `7.75` |
| `55,671.28 ms` | `433` | `stop` | `7.78` |
| `60,885.72 ms` | `380` | `stop` | `6.24` |

判断：

- `0.6` 确实提升 KV cache 余量。
- 本轮没有观察到 `0.6` 相比 `0.55` 的速度提升。
- 考虑同机外部 GPU 进程干扰，这里不应得出“0.6 一定更慢”的结论；更稳妥说法是“本轮未证明 0.6 有速度收益”。

## 5. TTFT / TPOT 代表点

代表点：

- profile：`vllm_qwen36-27b-awq-int4`
- prompt：`65,536 tokens`
- `max_tokens=512`
- stream：enabled
- 输出：`runtime/data/benchmarks/manual-stage2-stream-ttft/awq-64k-512.json`

结果：

| 指标 | 值 |
|---|---:|
| prompt tokens | `65,536` |
| completion tokens | `512` |
| total tokens | `66,048` |
| finish_reason | `length` |
| delta events | `508` |
| TTFT | `27,871.79 ms` |
| E2E latency | `37,071.76 ms` |
| TPOT from usage | `18.00 ms/token` |
| avg inter-delta | `18.14 ms` |

解释：

- `E2E - TTFT` 约 `9.20 s`，对应 512 token decode。
- TTFT 占 E2E 约 `75.2%`，说明这个 `64K + 512` 场景主要等待发生在首 token 之前。
- TPOT 约 `18 ms/token`，折算 decode 阶段约 `55.5 tok/s`；这和端到端 `completion tok/s` 不是同一个口径。

因此，第一阶段和第二阶段端到端 `completion tok/s` 的核心误差来源已经明确：

> 长上下文请求里，端到端输出吞吐被 prefill / 首 token 前成本强烈稀释；如果不记录 TTFT / TPOT，就容易把 prefill 慢误读为 decode 慢。

## 6. 和第一阶段的关系

第一阶段 `output=64` 结果：

| profile | prompt | output cap | latency avg | completion tok/s avg |
|---|---:|---:|---:|---:|
| `NVFP4` | `16K` | `64` | `7,090.06 ms` | `9.03` |
| `NVFP4` | `64K` | `64` | `29,204.86 ms` | `2.19` |
| `AWQ-INT4` | `16K` | `64` | `7,051.71 ms` | `9.08` |
| `AWQ-INT4` | `64K` | `64` | `30,051.95 ms` | `2.13` |

第二阶段 `output=512` 重复测量结果：

| profile | prompt | output cap | latency avg | completion tok/s avg |
|---|---:|---:|---:|---:|
| `NVFP4` | `16K` | `512` | `22,885.83 ms` | `19.87` |
| `NVFP4` | `64K` | `512` | `58,132.42 ms` | `7.47` |
| `AWQ-INT4` | `16K` | `512` | `12,741.69 ms` | `32.75` |
| `AWQ-INT4` | `64K` | `512` | `36,282.32 ms` | `10.88` |

可以确认：

1. `output=64` 会显著放大 prefill 对 `completion tok/s` 的拖累。
2. `output=512` 更适合作为第二阶段主口径，但仍需要 TTFT / TPOT 才能拆清 prefill 和 decode。
3. `AWQ-INT4` 不是只省显存；在本次长输出重复测量里，它也明显优于 NVFP4。
4. `NVFP4 0.6` 是容量参数，不是当前已验证的加速参数。

不能确认：

1. 不能给出 top kernel。
2. 不能断言 `0.6` 在无外部干扰环境下速度一定不变。
3. 不能把端到端 `completion tok/s` 写成纯 decode speed。

## 7. 后续推进记录

第二阶段最小目标完成后，当时建议按下面顺序推进：

| 优先级 | 实验 | 固定项 | 变量 | 目的 |
|---:|---|---|---|---|
| 1 | AWQ 并发阶梯 | `AWQ-INT4`、`16K/64K`、`output=256/512` | `concurrency=1/2/4` | 看显存效率能否转成服务吞吐 |
| 2 | profiler 代表点 | `AWQ-INT4 64K + output=512` | Nsight / torch profiler | 拆 prefill / decode top kernels |
| 3 | 无干扰复测 NVFP4 | `NVFP4`、`64K`、`output=512` | `0.55/0.6` | 排除外部 GPU 进程干扰后重看速度 |
| 4 | FP8 KV cache | 先选 AWQ 或 NVFP4 一个 profile | `kv_cache_dtype` | 验证容量提升和质量风险 |

截至 Stage 5：

- AWQ 并发阶梯已在 [stage3-awq-concurrency.md](./stage3-awq-concurrency.md) 完成。
- profiler 代表点已在 [stage4-awq-profiler.md](./stage4-awq-profiler.md) 完成。
- NVFP4 `0.55/0.6` 无外部 GPU 进程复测已在 [stage5-nvfp4-nointerference.md](./stage5-nvfp4-nointerference.md) 完成。
- `AWQ-INT4 + FP8 KV cache` 容量和速度对照已在 [stage5-nvfp4-nointerference.md](./stage5-nvfp4-nointerference.md) 完成；容量收益明确，单请求速度没有提升，质量回归仍未做。
- 当前下一步已经推进为 NVFP4 同形状 profiler、FP8 KV cache 质量回归，以及必要时的 FP8 KV 并发容量测试。

推荐下一条实测主线：

```bash
VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE=vllm_qwen36-27b-awq-int4-fp8-kv \
  /home/heshan/.conda/envs/paper2any/bin/python scripts/benchmark_backend.py \
  --profile vllm_qwen36-27b-awq-int4-fp8-kv \
  --targets 65536 \
  --max-tokens 512 \
  --concurrency 2 \
  --warmup-runs 0 \
  --measure-runs 3 \
  --sample-interval 2 \
  --output-dir runtime/data/benchmarks/manual-stage6-awq-fp8-kv-c2
```

运行前必须用 `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader` 确认没有非本任务 GPU 进程。若目标是上线判断，应先补质量回归而不是继续只看吞吐。

## 8. 环境和验证记录

本次使用环境：

- Python：`/home/heshan/.conda/envs/paper2any/bin/python`
- 控制入口：`python -m llmnode.control`
- 后端容器：`qwen36-27b-nvfp4-vllm` / `qwen36-27b-awq-int4-vllm`
- 实测日期：2026-06-09

执行过的关键验证：

- `curl http://127.0.0.1:15673/v1/models` 轮询等待后端 ready。
- `scripts/benchmark_backend.py --profile vllm_qwen36-27b-awq-int4 --targets 16384 65536 --max-tokens 512 --warmup-runs 1 --measure-runs 3`。
- `scripts/benchmark_backend.py --profile vllm_qwen36-27b-nvfp4 --targets 16384 65536 --max-tokens 512 --warmup-runs 1 --measure-runs 3`。
- `VLLM_CLAUDE_VLLM_GPU_MEMORY_UTILIZATION=0.6` 启动 NVFP4，并从启动日志确认 `gpu_memory_utilization: 0.6`。
- `scripts/benchmark_backend.py --profile vllm_qwen36-27b-nvfp4 --targets 65536 --max-tokens 512 --warmup-runs 1 --measure-runs 3`。
- `/tmp/llmnode_stream_latency.py --profile vllm_qwen36-27b-awq-int4 --target 65536 --max-tokens 512`。
- `python -m llmnode.control stop --service vllm` 停止本任务启动的后端。
- `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader` 检查 GPU 进程。

注意：

- 普通沙箱运行 benchmark 会因 Docker/采样权限出现 `[Errno 1] Operation not permitted`，正式 benchmark 结果取提权运行目录。
- 本阶段 TTFT 临时脚本需要识别 vLLM stream 的 `delta.reasoning` 字段；只识别 `content` / `reasoning_content` 会漏计 reasoning 模型的流式 token。
- 停止本任务后仍可能存在非本任务 GPU 进程；这类进程不属于本实验，不在本报告中处理。
