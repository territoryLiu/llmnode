# 第三阶段实验报告：AWQ-INT4 并发阶梯

> 文档定位：项目知识库中的 LLM serving 优化实验报告，不属于 `llmnode` 项目蓝图、契约或正式路线图。  
> 实验目标：在第二阶段确认 `AWQ-INT4` 是优先候选后，验证它的显存效率是否能转成服务吞吐。  
> 更新时间：2026-06-09。  
> 当前结论状态：`AWQ-INT4 + 16K/64K + output=512 + concurrency=1/2/4` 无干扰并发阶梯已完成；后续 Stage 4 已完成 `AWQ-INT4 64K + output=512` 单请求 profiler 代表点。

相关专题：

- benchmark 口径见 [benchmark-methodology.md](../performance/benchmark-methodology.md)。
- KV cache 解释见 [kv-cache.md](../performance/kv-cache.md)。
- vLLM 参数见 [vllm-deep-dive.md](../serving/vllm-deep-dive.md)。
- 第二阶段结论见 [stage2-vllm-prefill-decode.md](./stage2-vllm-prefill-decode.md)。

## 1. 一页结论

本轮固定：

- profile：`vllm_qwen36-27b-awq-int4`
- 后端：`vLLM`
- `gpu_memory_utilization=0.55`
- `max_model_len=262144`
- `max_num_seqs=4`
- prompt：`16K / 64K`
- `max_tokens=512`
- `warmup=1`
- `measure=3`
- concurrency：`1 / 2 / 4`
- Python：`/home/heshan/.conda/envs/paper2any/bin/python`

最终无干扰结果：

| concurrency | prompt | success | latency avg | latency p50 | completion tok/s avg | completion tok/s p50 |
|---:|---:|---:|---:|---:|---:|---:|
| `1` | `16K` | `3/3` | `12,764.75 ms` | `12,602.36 ms` | `32.69` | `32.61` |
| `2` | `16K` | `6/6` | `19,800.32 ms` | `19,802.79 ms` | `22.65` | `22.54` |
| `4` | `16K` | `12/12` | `32,983.40 ms` | `33,343.98 ms` | `13.71` | `14.08` |
| `1` | `64K` | `3/3` | `36,391.39 ms` | `36,282.61 ms` | `10.84` | `10.42` |
| `2` | `64K` | `6/6` | `67,211.20 ms` | `66,841.13 ms` | `6.01` | `5.76` |
| `4` | `64K` | `12/12` | `129,076.35 ms` | `129,185.66 ms` | `3.48` | `3.51` |

当前判断：

1. AWQ-INT4 的显存效率能转成更高并发能力：`16K/64K + output=512` 在 `concurrency=4` 下全部成功，没有 OOM、timeout 或 HTTP error。
2. 并发升高后，单请求端到端延迟显著增加，单请求 `completion tok/s` 下降；这是 batching / queueing / prefill 竞争的结果，不代表单请求 decode kernel 变慢。
3. `64K` 比 `16K` 更快遇到并发代价：`64K concurrency=4` 平均延迟达到 `129.08 s`，说明长上下文并发主要受 prefill / KV / 调度压力限制。
4. AWQ-INT4 适合继续作为容量型和并发型候选，但要用 SLA 判断可接受并发，而不是只看成功率。
5. 本阶段完成后不应继续盲目加并发或扩量化格式，应对 `AWQ-INT4 64K + output=512` 做 profiler；该单请求 profiler 已在 Stage 4 完成，当前未解问题推进为并发场景下的 scheduler gap / queueing / GPU idle。

重要口径：

- 表里的 `completion tok/s` 是每个请求自己的端到端输出吞吐，不是系统总吞吐。
- 由于 benchmark 脚本当前按 attempt 汇总，系统总吞吐需另行按 wall-clock 批次时间和总 completion tokens 计算。
- 模型输出有时提前 `stop`，completion tokens 不固定为 512。

## 2. 启动侧证据

无干扰最终运行日志：

```text
runtime/logs/qwen36-27b-awq-int4-vllm-20260609-133539.log
```

启动侧字段：

| 字段 | 值 |
|---|---:|
| served model | `qwen36-27b-awq-int4` |
| vLLM version | `0.19.2rc1.dev134+gfe9c3d6c5` |
| quantization | `compressed-tensors` |
| AWQ kernel | `MarlinLinearKernel for CompressedTensorsWNA16` |
| attention backend | `FLASH_ATTN` |
| chunked prefill | enabled, `max_num_batched_tokens=8192` |
| model loading memory | `19.05 GiB` |
| available KV cache memory | `22.38 GiB` |
| GPU KV cache size | `90,944 tokens` |
| max concurrency for `262,144` tokens/request | `1.38x` |
| API startup | success |

无干扰阶梯运行期间，`nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader` 只看到本任务 `VLLM::EngineCore`，未看到外部 GPU 计算进程。

## 3. `concurrency=1`

结果目录：

```text
runtime/data/benchmarks/manual-stage3-awq-concurrency-c1/20260609-115037-vllm_qwen36-27b-awq-int4/
```

命令：

```bash
VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE=vllm_qwen36-27b-awq-int4 \
  /home/heshan/.conda/envs/paper2any/bin/python scripts/benchmark_backend.py \
  --profile vllm_qwen36-27b-awq-int4 \
  --targets 16384 65536 \
  --max-tokens 512 \
  --concurrency 1 \
  --warmup-runs 1 \
  --measure-runs 3 \
  --sample-interval 2 \
  --output-dir runtime/data/benchmarks/manual-stage3-awq-concurrency-c1
```

| prompt | success | latency avg | latency p50 | latency min | latency max | completion tok/s avg | completion tok/s p50 | tok/s min | tok/s max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `16K` | `3/3` | `12,764.75 ms` | `12,602.36 ms` | `11,697.64 ms` | `13,994.27 ms` | `32.69` | `32.61` | `30.01` | `35.44` |
| `64K` | `3/3` | `36,391.39 ms` | `36,282.61 ms` | `35,860.04 ms` | `37,031.52 ms` | `10.84` | `10.42` | `10.23` | `11.88` |

测量轮次：

| prompt | concurrency index | latency | completion | finish_reason | completion tok/s |
|---|---:|---:|---:|---|---:|
| `16K` | `1` | `12,602.36 ms` | `411` | `stop` | `32.61` |
| `16K` | `1` | `13,994.27 ms` | `496` | `stop` | `35.44` |
| `16K` | `1` | `11,697.64 ms` | `351` | `stop` | `30.01` |
| `64K` | `1` | `37,031.52 ms` | `440` | `stop` | `11.88` |
| `64K` | `1` | `36,282.61 ms` | `378` | `stop` | `10.42` |
| `64K` | `1` | `35,860.04 ms` | `367` | `stop` | `10.23` |

## 4. `concurrency=2`

结果目录：

```text
runtime/data/benchmarks/manual-stage3-awq-concurrency-c2-clean/20260609-134245-vllm_qwen36-27b-awq-int4/
```

命令：

```bash
VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE=vllm_qwen36-27b-awq-int4 \
  /home/heshan/.conda/envs/paper2any/bin/python scripts/benchmark_backend.py \
  --profile vllm_qwen36-27b-awq-int4 \
  --targets 16384 65536 \
  --max-tokens 512 \
  --concurrency 2 \
  --warmup-runs 1 \
  --measure-runs 3 \
  --sample-interval 2 \
  --output-dir runtime/data/benchmarks/manual-stage3-awq-concurrency-c2-clean
```

| prompt | success | latency avg | latency p50 | latency min | latency max | completion tok/s avg | completion tok/s p50 | tok/s min | tok/s max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `16K` | `6/6` | `19,800.32 ms` | `19,802.79 ms` | `18,577.97 ms` | `20,859.59 ms` | `22.65` | `22.54` | `19.97` | `24.68` |
| `64K` | `6/6` | `67,211.20 ms` | `66,841.13 ms` | `66,534.99 ms` | `69,165.94 ms` | `6.01` | `5.76` | `5.58` | `7.40` |

测量轮次：

| prompt | concurrency index | latency | completion | finish_reason | completion tok/s |
|---|---:|---:|---:|---|---:|
| `16K` | `1` | `19,013.79 ms` | `411` | `stop` | `21.62` |
| `16K` | `2` | `20,744.96 ms` | `512` | `length` | `24.68` |
| `16K` | `1` | `19,595.22 ms` | `437` | `stop` | `22.30` |
| `16K` | `2` | `20,859.59 ms` | `512` | `length` | `24.55` |
| `16K` | `2` | `18,577.97 ms` | `371` | `stop` | `19.97` |
| `16K` | `1` | `20,010.37 ms` | `456` | `stop` | `22.79` |
| `64K` | `2` | `66,851.10 ms` | `387` | `stop` | `5.79` |
| `64K` | `1` | `67,309.91 ms` | `402` | `stop` | `5.97` |
| `64K` | `1` | `66,831.16 ms` | `376` | `stop` | `5.63` |
| `64K` | `2` | `69,165.94 ms` | `512` | `length` | `7.40` |
| `64K` | `2` | `66,534.99 ms` | `371` | `stop` | `5.58` |
| `64K` | `1` | `66,574.09 ms` | `381` | `stop` | `5.72` |

## 5. `concurrency=4`

结果目录：

```text
runtime/data/benchmarks/manual-stage3-awq-concurrency-c4-clean/20260609-134931-vllm_qwen36-27b-awq-int4/
```

命令：

```bash
VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE=vllm_qwen36-27b-awq-int4 \
  /home/heshan/.conda/envs/paper2any/bin/python scripts/benchmark_backend.py \
  --profile vllm_qwen36-27b-awq-int4 \
  --targets 16384 65536 \
  --max-tokens 512 \
  --concurrency 4 \
  --warmup-runs 1 \
  --measure-runs 3 \
  --sample-interval 2 \
  --output-dir runtime/data/benchmarks/manual-stage3-awq-concurrency-c4-clean
```

| prompt | success | latency avg | latency p50 | latency min | latency max | completion tok/s avg | completion tok/s p50 | tok/s min | tok/s max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `16K` | `12/12` | `32,983.40 ms` | `33,343.98 ms` | `30,343.00 ms` | `34,100.25 ms` | `13.71` | `14.08` | `10.22` | `15.07` |
| `64K` | `12/12` | `129,076.35 ms` | `129,185.66 ms` | `126,902.52 ms` | `130,769.29 ms` | `3.48` | `3.51` | `2.92` | `3.94` |

说明：

- `64K concurrency=4` 运行期间，vLLM 日志中观测到 `GPU KV cache usage` 最高约 `74.7%`。
- 没有 OOM、timeout 或 HTTP error。
- 这个点证明 AWQ-INT4 的 KV 余量可以支撑 `4 x 64K` 级别请求，但端到端延迟已经较高。

## 6. 并发趋势

以 `concurrency=1` 为基准：

| prompt | concurrency | latency avg 相对 c1 | completion tok/s avg 相对 c1 |
|---|---:|---:|---:|
| `16K` | `1` | `1.00x` | `1.00x` |
| `16K` | `2` | `1.55x` | `0.69x` |
| `16K` | `4` | `2.58x` | `0.42x` |
| `64K` | `1` | `1.00x` | `1.00x` |
| `64K` | `2` | `1.85x` | `0.55x` |
| `64K` | `4` | `3.55x` | `0.32x` |

解读：

- 并发提升后，请求可以全部成功，但单请求延迟不是线性温和增长。
- `64K` 的并发代价更重，说明长上下文主要受 prefill / KV cache / 调度影响。
- 如果服务目标是交互式延迟，`64K concurrency=4` 很可能不可接受；如果目标是离线吞吐或批处理，它证明容量上可跑，但仍需系统总吞吐口径补充。

## 7. 系统吞吐近似口径

表里的 `completion tok/s` 是单请求端到端输出吞吐。为了补一个更接近服务侧的口径，这里用 `summary.json` 里的 measured attempts 近似计算系统总 output tok/s：

```text
system output tok/s ~= 所有成功 measured 请求的 completion tokens 总和
                    / 每个并发批次的最大 latency 之和
```

注意：

- benchmark 当前没有保存每个 attempt 的精确 start/end timestamp，因此这里是批次 wall-clock 近似值。
- 对 `concurrency=1`，该口径基本等价于单请求 tok/s。
- 对 `concurrency>1`，该口径比单请求 tok/s 更能表达系统整体输出能力。

无干扰结果：

| concurrency | prompt | measured reqs | total output tokens | approx wall-clock | approx system output tok/s | avg per-request tok/s |
|---:|---:|---:|---:|---:|---:|---:|
| `1` | `16K` | `3` | `1,258` | `38.29 s` | `32.85` | `32.69` |
| `1` | `64K` | `3` | `1,185` | `109.17 s` | `10.85` | `10.84` |
| `2` | `16K` | `6` | `2,699` | `61.61 s` | `43.80` | `22.65` |
| `2` | `64K` | `6` | `2,429` | `203.05 s` | `11.96` | `6.01` |
| `4` | `16K` | `12` | `5,444` | `102.08 s` | `53.33` | `13.71` |
| `4` | `64K` | `12` | `5,402` | `391.70 s` | `13.79` | `3.48` |

解读：

- `16K` 从 `c1 -> c4` 的系统输出吞吐约 `32.85 -> 53.33 tok/s`，有吞吐收益，但不是线性扩展。
- `64K` 从 `c1 -> c4` 只约 `10.85 -> 13.79 tok/s`，长上下文并发扩展很弱。
- `64K c4` 的容量可跑，但系统总吞吐收益有限、单请求延迟很高，下一步应优先用 profiler 拆 prefill / scheduler / KV 压力，而不是继续增加并发。

## 8. 曾经的受干扰结果

第一次 `concurrency=2` 运行目录：

```text
runtime/data/benchmarks/manual-stage3-awq-concurrency-c2/20260609-115437-vllm_qwen36-27b-awq-int4/
```

运行期间发现外部进程：

```text
908498, /proj02/pengyao/envs/SFormer_clean/bin/python, 28760 MiB
```

后续等待期间又出现：

```text
1047834, /proj02/pengyao/envs/SFormer_clean/bin/python, 28250 MiB
```

受干扰 `concurrency=2` 结果：

| prompt | success | latency avg | completion tok/s avg |
|---|---:|---:|---:|
| `16K` | `6/6` | `21,089.05 ms` | `21.71` |
| `64K` | `6/6` | `106,470.14 ms` | `3.49` |

这个结果只保留为环境噪声案例，不用于公平并发结论。

## 9. 后续推进记录

第三阶段 AWQ 并发阶梯完成后，当时建议：

| 优先级 | 实验 | 固定项 | 目的 |
|---:|---|---|---|
| 1 | profiler 代表点 | `AWQ-INT4 64K + output=512` | 拆 prefill / decode top kernels |
| 2 | NVFP4 无干扰复测 | `64K + output=512`、`0.55/0.6` | 排除早先外部负载干扰 |
| 3 | FP8 KV cache | AWQ 或 NVFP4 一个 profile | 验证容量收益和质量风险 |

截至 Stage 4，优先级 1 已完成，结论见 [stage4-awq-profiler.md](./stage4-awq-profiler.md)。当前下一步是：

| 优先级 | 实验 | 固定项 | 目的 |
|---:|---|---|---|
| 1 | 并发 profiler / Nsight Systems | `AWQ-INT4 64K + output=512 + concurrency=4` | 拆 scheduler gap / queueing / GPU idle |
| 2 | NVFP4 无干扰复测 | `64K + output=512`、`0.55/0.6` | 排除早先外部负载干扰 |
| 3 | FP8 KV cache | AWQ 或 NVFP4 一个 profile | 验证容量收益和质量风险 |

Stage 4 单请求 profiler 已拆出：

- prefill 最大热点：AWQ Marlin GEMM，第二热点：FlashAttention。
- decode 最大热点：AWQ Marlin GEMM，后续是 attention、FP16 GEMM、sampling softmax。
- 单请求 trace 未见超过 `1.0%` 阈值的明确 overlap / GPU idle 机会。
- 并发下的 scheduler gap / queueing / GPU idle 仍需 `concurrency=4` trace 或 Nsight Systems。

## 10. 环境和验证记录

本次使用环境：

- Python：`/home/heshan/.conda/envs/paper2any/bin/python`
- 控制入口：`python -m llmnode.control`
- 后端容器：`qwen36-27b-awq-int4-vllm`
- 实测日期：2026-06-09

已验证：

- `/v1/models` 返回 `qwen36-27b-awq-int4`。
- `concurrency=1/2/4` 三个无干扰结果目录均存在。
- `nvidia-smi` 在无干扰阶梯运行期间只看到本任务 `VLLM::EngineCore`。
- benchmark 状态均为 `completed`，errors 为空。
- 本任务结束后已停止 AWQ vLLM 后端。
