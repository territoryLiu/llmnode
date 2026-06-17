# 第六阶段实验报告：NVFP4 Profiler 代表点

> 文档定位：项目知识库中的 LLM serving 优化实验报告，不属于 `llmnode` 项目蓝图、契约或正式路线图。  
> 实验目标：对 `NVFP4 64K + output=512` 做 torch profiler，与 Stage 4 的 AWQ profiler 对齐，判断热点是否同样落在 Marlin GEMM 和 FlashAttention。  
> 更新时间：2026-06-09。  
> 当前结论状态：`concurrency=1` trace 已采集并完成三表分析；证据显示 NVFP4 与 AWQ 一样由 Marlin GEMM 和 FlashAttention 主导，但 decode 中普通 BF16 GEMM 占比更显著。

相关专题：

- AWQ profiler 证据见 [stage4-awq-profiler.md](./stage4-awq-profiler.md)。
- NVFP4 无干扰 benchmark 见 [stage1-2-qwen27b.md](./stage1-2-qwen27b.md)。
- profiler 方法见 [profiling-guide.md](../performance/profiling-guide.md)。
- benchmark 口径见 [benchmark-methodology.md](../performance/benchmark-methodology.md)。

## 1. 一页结论

本轮 fixed shape：

| 项 | 值 |
|---|---|
| profile | `vllm_qwen36-27b-nvfp4-profiler` |
| backend | `vLLM` |
| model | `qwen36-27b-nvfp4` |
| prompt tokens | `65,536` |
| output tokens | `512` |
| concurrency | `1` |
| gpu_memory_utilization | `0.55`（当时配置；现已切换到 `0.6` 作为默认） |
| profiler | vLLM torch profiler |

核心结论：

1. `prefill` 最大热点仍是 Marlin GEMM，GPU time `16,354.79 ms`，占 `61.6%`。
2. `prefill` 第二热点仍是 FlashAttention，GPU time `6,257.06 ms`，占 `23.6%`。
3. `decode` 最大热点是小 batch Marlin GEMM，GPU time `4,617.48 ms`，占 `41.3%`。
4. `decode` 中普通 BF16 GEMM 更明显，GPU time `2,666.47 ms`，占 `23.9%`；FlashAttention 为 `1,404.99 ms`，占 `12.6%`。
5. overlap table 没有超过 `1.0%` 阈值的明确 GPU idle / overlap 机会。
6. fuse table 中 `vLLM-origin DSV3 router GEMM` 命中不应直接当作 Qwen3.6-27B 的真实优化结论；这类行需要后续人工源码核对。

与 AWQ 的关系：

- Stage 4 AWQ 和本轮 NVFP4 的方向一致：长上下文 `64K + output=512` 都由 Marlin GEMM + FlashAttention 主导。
- 这说明当前瓶颈更像 Qwen3.6-27B 当前 vLLM/A800/长上下文 shape 下的共同热点，而不是 AWQ 独有现象。
- NVFP4 在 benchmark 上接近 AWQ，但 profiler 没有显示一个“明显更轻”的 kernel 结构；它仍然落在 Marlin + attention 的同类瓶颈中。

## 2. 控制面和启动

新增 profiler profile：

```text
config/backends/vllm_qwen36-27b-nvfp4-profiler.yaml
config/backends/vllm_qwen36-27b-nvfp4-profiler-c4.yaml
```

启动命令：

```bash
VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE=vllm_qwen36-27b-nvfp4-profiler \
  /home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control start --service vllm --daemon
```

启动日志：

```text
runtime/logs/qwen36-27b-nvfp4-profiler-vllm-20260609-170734.log
```

启动侧证据：

| 字段 | 值 |
|---|---:|
| profiler_config | `{"profiler":"torch","torch_profiler_dir":"/tmp/vllm-profile"}` |
| NVFP4 kernel | `MarlinNvFp4LinearKernel` |
| available KV cache memory | `17.38 GiB` |
| GPU KV cache size | `70,560 tokens` |
| max concurrency for `262,144` tokens/request | `1.07x` |
| API startup | success |

## 3. 采集方式

Profiler API：

```bash
curl -sS -X POST http://127.0.0.1:15673/start_profile

VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE=vllm_qwen36-27b-nvfp4-profiler \
  /home/heshan/.conda/envs/paper2any/bin/python scripts/benchmark_backend.py \
  --profile vllm_qwen36-27b-nvfp4-profiler \
  --targets 65536 \
  --max-tokens 512 \
  --concurrency 1 \
  --warmup-runs 0 \
  --measure-runs 1 \
  --sample-interval 1 \
  --output-dir runtime/data/benchmarks/manual-stage6-nvfp4-profiler

curl -sS -X POST http://127.0.0.1:15673/stop_profile
```

benchmark 结果目录：

```text
runtime/data/benchmarks/manual-stage6-nvfp4-profiler/20260609-171249-vllm_qwen36-27b-nvfp4-profiler/
```

trace 目录：

```text
runtime/data/profiles/stage6-nvfp4-profiler/
```

trace 文件：

```text
runtime/data/profiles/stage6-nvfp4-profiler/rank0.1780996447265328150.pt.trace.json.gz
runtime/data/profiles/stage6-nvfp4-profiler/7a57df8cad18_1.async_llm.1780996434489999556.pt.trace.json.gz
```

分析输出：

```text
runtime/data/benchmarks/manual-stage6-nvfp4-profiler/analysis.txt
runtime/data/profiles/stage6-nvfp4-profiler/profiler_out_0.txt
```

说明：`runtime/data/profiles/stage6-nvfp4-profiler/` 由容器写入，宿主侧没有写权限，因此 `analysis.txt` 放在 benchmark 目录。

## 4. 请求结果

| prompt | output | concurrency | latency | completion tok/s | finish_reason | result |
|---:|---:|---:|---:|---:|---|---|
| `64K` | `512` | `1` | `41,221.68 ms` | `12.42` | `length` | `success` |

## 5. Kernel table

### 5.1 `prefill`

| Kernel | GPU time | Share | Launches | 判断 |
|---|---:|---:|---:|---|
| `marlin::Marlin<..., 256, 4, 16, 4, false, ...>` | `16,354.79 ms` | `61.6%` | `13,312` | 最大热点 |
| `flash_fwd_splitkv_kernel<..., true, ...>` | `6,257.06 ms` | `23.6%` | `128` | 第二热点 |
| `ampere_bf16_s16816gemm_bf16_128x256...` | `2,081.07 ms` | `7.8%` | `384` | 普通 BF16 GEMM |
| `merge_16x16_to_64x64_inverse_kernel` | `291.95 ms` | `1.1%` | `384` | 次级 FLA/GDN 相关项 |

### 5.2 `decode`

| Kernel | GPU time | Share | Launches | 判断 |
|---|---:|---:|---:|---|
| `marlin::Marlin<..., 256, 1, 8, 8, true, ...>` | `4,617.48 ms` | `41.3%` | `106,288` | 最大热点 |
| `ampere_bf16_s16816gemm_bf16_128x64...` | `2,666.47 ms` | `23.9%` | `24,528` | 普通 BF16 GEMM，NVFP4 decode 中占比明显 |
| `flash_fwd_splitkv_kernel<..., false, ...>` | `1,404.99 ms` | `12.6%` | `8,176` | decode attention |
| `ampere_bf16_s16816gemm_bf16_64x64...` | `720.02 ms` | `6.4%` | `511` | unquantized GEMM |
| `fused_recurrent_gated_delta_rule_packed_decode_kernel` | `231.88 ms` | `2.1%` | `24,528` | hybrid linear / GDN |
| `flash_fwd_splitkv_combine_kernel<..., true>` | `222.06 ms` | `2.0%` | `8,176` | attention combine |
| `SoftMaxForward` | `154.66 ms` | `1.4%` | `1,024` | sampling 相关 |

## 6. Overlap / fuse table

Overlap table：

| 结论 |
|---|
| 没有超过 `1.0%` reporting bar 的明确 overlap opportunity；如需正式 overlap 归因，需要 mapping/formal mode 或 Nsight Systems。 |

Fuse table：

| Pattern | 当前处理 |
|---|---|
| `vLLM-origin DSV3 router GEMM` | 需要人工核对；本报告不把它作为 Qwen3.6-27B 的优化结论。 |

原因：Stage 4 AWQ profiler 里也出现过类似命中，当时已经判断可能是假阳性或至少需要源码人工复核。本轮继续沿用这个边界。

## 7. 当前结论

| 问题 | 当前证据 | 判断 |
|---|---|---|
| NVFP4 是否也是 Marlin + FlashAttention 热点 | prefill 中 Marlin `61.6%`、FlashAttention `23.6%`；decode 中 Marlin `41.3%`、FlashAttention `12.6%` | 是 |
| NVFP4 是否和 AWQ 完全一样 | decode 中普通 BF16 GEMM 占 `23.9%`，比 AWQ c1 decode 里的 FP16/BF16 GEMM占比更突出 | 不完全一样 |
| 是否有明显 GPU idle / overlap 机会 | 单 trace overlap table 没有超过 `1.0%` 阈值的行 | 暂未发现 |
| 下一步是否该继续盲调参数 | profiler 指向 kernel/attention 主热点，不支持盲调参数 | 不建议 |

## 8. 下一步

优先级建议：

| 优先级 | 下一步 | 目的 |
|---:|---|---|
| 1 | FP8 KV cache 最小质量回归 | 现在只有容量/速度，没有质量证据 |
| 2 | Nsight Systems 最小 bring-up | 看 CPU/GPU timeline、queueing、kernel launch gap 和 stream overlap |
| 3 | 如继续 profiler，对 `NVFP4 profiler c4` 采 trace | 判断 NVFP4 并发下是否同样出现 Running/Waiting 和热点放大 |
| 4 | Nsight Compute 针对 Marlin / FlashAttention 代表 kernel | 看 SM occupancy、memory bandwidth、warp stall 等底层指标 |

