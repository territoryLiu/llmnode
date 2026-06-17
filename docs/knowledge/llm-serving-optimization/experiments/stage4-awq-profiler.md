# 第四阶段实验报告：AWQ-INT4 Profiler 代表点

> 文档定位：项目知识库中的 LLM serving 优化实验报告，不属于 `llmnode` 项目蓝图、契约或正式路线图。  
> 实验目标：对 `AWQ-INT4 64K + output=512` 做 profiler，把长上下文慢拆成 prefill、decode、top CUDA kernels 和 scheduler gap。  
> 更新时间：2026-06-09。  
> 当前结论状态：`concurrency=1` 与 `concurrency=4` torch profiler trace 均已采集并完成三表分析；证据显示单请求和并发场景都以 AWQ Marlin GEMM 为主，长上下文 attention 是第二大项。

相关专题：

- profiler 方法见 [profiling-guide.md](../performance/profiling-guide.md)。
- benchmark 口径见 [benchmark-methodology.md](../performance/benchmark-methodology.md)。
- 第三阶段并发结论见 [stage3-awq-concurrency.md](./stage3-awq-concurrency.md)。
- 第一阶段 TTFT / TPOT 代表点见 [stage1-2-qwen27b.md](./stage1-2-qwen27b.md)。

## 1. 为什么现在做 profiler

前三阶段已经完成下面的收敛：

1. `AWQ-INT4` 在当前 A800 + Qwen3.6-27B + vLLM 路径下，比 `NVFP4` 更适合作为下一步主候选。
2. `AWQ-INT4 64K + output=512` 的流式代表点显示 `TTFT=27,871.79 ms`、`TPOT=18.00 ms/token`、`E2E=37,071.76 ms`，首 token 前成本占主导。
3. `AWQ-INT4 16K/64K + output=512 + concurrency=1/2/4` 都能跑通，但 `64K` 系统吞吐扩展很弱，`c1 -> c4` 只约 `10.85 -> 13.79 output tok/s`。

因此下一步不应继续扩更多量化格式或更高并发，而应证明瓶颈到底来自：

- prefill attention / chunked prefill
- Marlin AWQ GEMM
- KV cache 读写和长上下文 attention
- scheduler gap / GPU idle
- CPU 侧 tokenization、sampling 或响应处理

本轮 profiler 已经把主要瓶颈从“长上下文慢”收束为：

1. `prefill`：Marlin AWQ GEMM 是最大 GPU 时间来源，FlashAttention 是第二大来源。
2. `decode`：Marlin AWQ GEMM 仍是最大 GPU 时间来源，长上下文 attention、普通 FP16 GEMM、sampling softmax 也有可见占比。
3. `concurrency=4` 下，vLLM 日志明确显示排队过程：`Running:2 Waiting:2 -> Running:4 Waiting:0`，KV cache usage 峰值约 `74.7%`。
4. overlap 表没有超过 `1.0%` 报告阈值的明确 GPU idle / overlap 机会；当前证据不支持把主要问题归因于明显 GPU 空洞。

## 2. 固定实验对象

| 项 | 值 |
|---|---|
| profile | `vllm_qwen36-27b-awq-int4` |
| backend | `vLLM` |
| model | `qwen36-27b-awq-int4` |
| prompt tokens | `65536` |
| output tokens | `512` |
| concurrency | `1` |
| gpu_memory_utilization | `0.55` |
| max_model_len | `262144` |
| max_num_seqs | `4` |
| Python | `/home/heshan/.conda/envs/paper2any/bin/python` |

首轮只测 `concurrency=1`。原因：

- Stage 1 已经有同形状 TTFT / TPOT 代表点，便于对齐。
- Stage 3 已证明高并发下混入 queueing 和 batching，第一份 profiler 不应把系统调度和单请求阶段瓶颈混在一起。
- 如果单请求 trace 能定位 prefill 主热点，再扩展到 `concurrency=4` 看 scheduler gap。

第二轮已补 `concurrency=4`。原因：

- Stage 3 的最大未解问题是 `64K c1 -> c4` 系统吞吐扩展弱。
- `concurrency=4` 与 Stage 3 的最慢点一致，可以直接解释排队、KV 压力和并发下 top kernels。

## 3. 当前控制面限制

项目正式控制入口是：

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control
```

本阶段开始时，`llmnode` 控制面会从 `VLLMContainerSpec.command` 生成 vLLM 启动参数，但还没有暴露 vLLM torch profiler 配置字段，例如：

- `--profiler-config`
- `torch_profiler_dir`
- profiler trace 目录挂载

为了保持正式入口，已补最小控制面能力：

- `BackendSettings.profiler_config`
- `BackendSettings.profiler_host_dir`
- `VLLMContainerSpec.command` 追加 `--profiler-config`
- `VLLMContainerSpec.volumes` 追加 profiler 可写挂载
- 专用 profile：`config/backends/vllm_qwen36-27b-awq-int4-profiler.yaml`

本阶段没有改默认 profile；普通 vLLM profile 不设置 profiler 字段时，启动命令和挂载保持原行为。

如果后续再采 profiler，有两条可选路径：

| 路径 | 优点 | 风险 |
|---|---|---|
| 临时扩展控制面支持 profiler 参数 | 保持正式入口，复现性好 | 需要改代码和测试 |
| 手工起一次 profiler 专用 vLLM 容器 | 快速采 trace，不污染正式配置 | 绕过正式入口，需清楚记录命令和清理步骤 |

本轮采用第一条路径，并通过正式入口启动：

```bash
VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE=vllm_qwen36-27b-awq-int4-profiler \
  /home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control start --service vllm --daemon
```

`concurrency=4` 使用独立 profile，避免覆盖单请求 trace：

```bash
VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE=vllm_qwen36-27b-awq-int4-profiler-c4 \
  /home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control start --service vllm --daemon
```

## 4. 推荐采集方式

专用 profiling profile 使 vLLM 启动时包含：

```text
--profiler-config {"profiler":"torch","torch_profiler_dir":"/tmp/vllm-profile"}
```

同时把宿主机目录挂载到容器内：

```text
runtime/data/profiles/stage4-awq-profiler -> /tmp/vllm-profile
```

服务 ready 后，按 vLLM profiler API 采集：

```bash
curl -sS -X POST http://127.0.0.1:15673/start_profile

VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE=vllm_qwen36-27b-awq-int4 \
  /home/heshan/.conda/envs/paper2any/bin/python scripts/benchmark_backend.py \
  --profile vllm_qwen36-27b-awq-int4 \
  --targets 65536 \
  --max-tokens 512 \
  --concurrency 1 \
  --warmup-runs 0 \
  --measure-runs 1 \
  --sample-interval 1 \
  --output-dir runtime/data/benchmarks/manual-stage4-awq-profiler

curl -sS -X POST http://127.0.0.1:15673/stop_profile
```

实际执行时，普通沙箱网络不能稳定访问 Docker 发布端口，`curl` 和 benchmark 使用宿主网络提权环境执行。`stop_profile` HTTP 请求在 `30s` 超时，但日志显示已进入 `Stopping profiler...`，且 trace 文件最终完整写出并通过 gzip 完整性检查。

如果希望更干净地区分 prefill 和 decode，优先采两段：

| trace | prompt | output | 目的 |
|---|---:|---:|---|
| prefill | `65536` | `1` | 捕获长上下文 prefill / TTFT 主路径 |
| decode | `1` | `512` | 捕获稳定 decode / sampling 主路径 |

## 5. 实测结果

### 5.1 `concurrency=1`

benchmark 结果目录：

```text
runtime/data/benchmarks/manual-stage4-awq-profiler/20260609-150547-vllm_qwen36-27b-awq-int4-profiler/
```

trace 目录：

```text
runtime/data/profiles/stage4-awq-profiler/
```

trace 文件：

```text
runtime/data/profiles/stage4-awq-profiler/81077965cf44_1.async_llm.1780988808398032397.pt.trace.json.gz
runtime/data/profiles/stage4-awq-profiler/rank0.1780988821973778914.pt.trace.json.gz
```

profiler 原始表格输出：

```text
runtime/data/profiles/stage4-awq-profiler/profiler_out_0.txt
```

启动侧证据：

| 字段 | 值 |
|---|---:|
| vLLM version | `0.19.2rc1.dev134+gfe9c3d6c5` |
| profiler_config | `{"profiler":"torch","torch_profiler_dir":"/tmp/vllm-profile"}` |
| AWQ kernel | `MarlinLinearKernel for CompressedTensorsWNA16` |
| attention backend | `FLASH_ATTN` |
| model loading memory | `19.05 GiB` |
| available KV cache memory | `22.38 GiB` |
| GPU KV cache size | `90,944 tokens` |
| max concurrency for `262,144` tokens/request | `1.38x` |

请求结果：

| prompt | output | concurrency | latency | completion tok/s | finish_reason | result |
|---:|---:|---:|---:|---:|---|---|
| `64K` | `512` | `1` | `40,443.20 ms` | `12.66` | `length` | `success` |

运行日志中的阶段性吞吐：

| 阶段 | 日志字段 |
|---|---|
| prefill / 生成开始 | `Avg prompt throughput: 6553.3 tokens/s`、`Avg generation throughput: 5.0 tokens/s`、`GPU KV cache usage: 18.7%` |
| decode / 收尾 | `Avg generation throughput: 46.2 tokens/s`、`GPU KV cache usage: 0.0%` |

这些日志字段是 vLLM 周期性统计，不等同于精确 TTFT / TPOT，但和 Stage 2 的判断一致：长上下文请求前半段被 prefill 强烈主导，decode 稳态输出更快。

### 5.2 `concurrency=4`

benchmark 结果目录：

```text
runtime/data/benchmarks/manual-stage4-awq-profiler-c4/20260609-152358-vllm_qwen36-27b-awq-int4-profiler-c4/
```

trace 目录：

```text
runtime/data/profiles/stage4-awq-profiler-c4/
```

trace 文件：

```text
runtime/data/profiles/stage4-awq-profiler-c4/7b0a76d675be_1.async_llm.1780989992309673569.pt.trace.json.gz
runtime/data/profiles/stage4-awq-profiler-c4/rank0.1780990019425074953.pt.trace.json.gz
```

profiler 原始表格输出：

```text
runtime/data/profiles/stage4-awq-profiler-c4/profiler_out_0.txt
```

请求结果：

| prompt | output | concurrency | success | latency avg | latency p50 | latency min | latency max | completion tok/s avg |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `64K` | `512` | `4` | `4/4` | `128,780.22 ms` | `128,259.31 ms` | `127,202.56 ms` | `131,399.70 ms` | `3.22` |

测量轮次：

| concurrency index | latency | completion | finish_reason | completion tok/s |
|---:|---:|---:|---|---:|
| `1` | `127,202.56 ms` | `358` | `stop` | `2.81` |
| `3` | `128,094.18 ms` | `400` | `stop` | `3.12` |
| `4` | `128,424.45 ms` | `391` | `stop` | `3.04` |
| `2` | `131,399.70 ms` | `512` | `length` | `3.90` |

运行日志中的并发过程：

| 时间片现象 | 日志字段 |
|---|---|
| 初始排队 | `Running: 2 reqs, Waiting: 2 reqs` |
| 中间排队 | `Running: 3 reqs, Waiting: 1 reqs` |
| 满并发运行 | `Running: 4 reqs, Waiting: 0 reqs` |
| KV 峰值 | `GPU KV cache usage: 74.7%` |
| prefill 周期 | 多次出现 `Avg prompt throughput: 6553.x tokens/s` |
| decode 收尾 | 最高观测到 `Avg generation throughput: 136.2 tokens/s` |

解读：

- `concurrency=4` 并不是四个 64K 请求一开始就全部同时运行；vLLM 有明显排队和分批进入运行态。
- KV cache usage 峰值与 Stage 3 观测一致，约 `74.7%`，没有贴满 KV 池。
- 单请求延迟高主要来自长 prefill 分批调度和并发下共享 GPU，而不是 HTTP error、OOM 或明显 GPU idle。

## 6. Trace 分析口径

采集到 trace 后，用统一分析脚本生成三张表：

```bash
/home/heshan/.conda/envs/paper2any/bin/python \
  /home/heshan/.codex/skills/AI-Infra-Auto-Driven-SKILLS/skills/llm-torch-profiler-analysis/scripts/analyze_llm_torch_profile.py \
  --input runtime/data/profiles/stage4-awq-profiler
```

`concurrency=1` 分析脚本输出：

```text
Mode: single-trace
Framework: vLLM
Input traces: runtime/data/profiles/stage4-awq-profiler/rank0.1780988821973778914.pt.trace.json.gz
```

`concurrency=4` 分析脚本输出：

```text
Mode: single-trace
Framework: vLLM
Input traces: runtime/data/profiles/stage4-awq-profiler-c4/rank0.1780990019425074953.pt.trace.json.gz
```

报告回答：

| 问题 | 证据 |
|---|---|
| prefill 占 E2E 多少 | Stage 2 流式代表点里 TTFT 占 E2E 约 `75.2%`；本轮 profiler 以 kernel 表解释 prefill 内部热点 |
| decode TPOT 是否稳定 | Stage 2 TPOT 为 `18.00 ms/token`；本轮 decode kernel 表显示主要时间在 Marlin / attention / sampling |
| top CUDA kernels 是什么 | kernel table |
| 是否有 GPU idle / scheduler gap | overlap-opportunity table 无超过 `1.0%` 阈值的行 |
| 是否存在可融合或已知优化机会 | fuse-pattern table 有命中，但存在模型族误归因风险，暂不作为明确优化结论 |

## 7. Kernel Table 摘要：`concurrency=1`

### 7.1 Prefill

| Kernel | GPU time | Share | Launches | 初步判断 |
|---|---:|---:|---:|---|
| `marlin::Marlin<...>` | `19,148.50 ms` | `69.5%` | `16,384` | AWQ Marlin GEMM 是 prefill 最大热点 |
| `flash_fwd_splitkv_kernel<...>` | `6,460.71 ms` | `23.5%` | `128` | 长上下文 FlashAttention 是第二大热点 |
| `merge_16x16_to_64x64_inverse_kernel` | `284.45 ms` | `1.0%` | `384` | GDN / hybrid linear 相关辅助热点 |

结论：

- 对 `AWQ-INT4 64K`，prefill 不是单纯 attention 慢；AWQ Marlin GEMM 占比更高。
- FlashAttention 仍然是明确第二热点，说明长上下文 attention 路径值得保留为后续分析对象。
- 如果后续要优化 prefill，优先对比 AWQ Marlin、BF16 GEMM、NVFP4 Marlin，以及 chunked prefill 参数，而不是只盯 KV cache。

### 7.2 Decode

| Kernel | GPU time | Share | Launches | 初步判断 |
|---|---:|---:|---:|---|
| `marlin::Marlin<...>` | `5,449.29 ms` | `58.7%` | `130,816` | decode 最大热点仍是 AWQ Marlin GEMM |
| `flash_fwd_splitkv_kernel<...>` | `1,419.66 ms` | `15.3%` | `8,176` | decode attention over KV 是第二大热点 |
| `ampere_fp16_s16816gemm_fp16_64x64...` | `720.42 ms` | `7.8%` | `511` | 未量化 FP16 GEMM / LM head 或相关 dense 路径 |
| `fused_recurrent_gated_delta_rule_packed_decode_kernel` | `229.64 ms` | `2.5%` | `24,528` | Qwen3.6 hybrid / GDN 路径相关 |
| `flash_fwd_splitkv_combine_kernel<...>` | `221.84 ms` | `2.4%` | `8,176` | split-KV attention combine |
| `cunn_SoftMaxForward` | `154.21 ms` | `1.7%` | `1,024` | top-k / top-p sampling |
| `gemv2T_kernel_val<...>` | `111.95 ms` | `1.2%` | `24,528` | decode 小 GEMV |
| `triton_red_fused__to_copy_add_marlin_gemm_rms_norm_3` | `102.19 ms` | `1.1%` | `24,528` | RMSNorm / Marlin 周边融合路径 |

结论：

- decode 并不是完全被 attention KV 读取主导；AWQ Marlin GEMM 仍占最大比例。
- attention 和 sampling 已经可见，但不是第一热点。
- Stage 2 的 `TPOT=18.00 ms/token` 与这里的 decode top kernels 一致：decode 有优化空间，但 Stage 2 的用户等待主要仍来自首 token 前。

## 8. Overlap / Fuse 表解读

Overlap Opportunity Table：

```text
No rows cleared the 1.0% reporting bar. Use mapping/formal mode for overlap attribution.
```

解读：

- 第一轮 trace 没有显示超过报告阈值的明确 GPU idle / overlap 机会。
- 这不等于“没有调度问题”，只说明当前单请求 profiler 证据不支持把主要瓶颈优先归因于 GPU 空洞。
- 如果要验证 Stage 3 `64K concurrency=4` 的 queueing / scheduler gap，需要另采 `concurrency=4` trace 或 Nsight Systems timeline。

Fuse Opportunity Table：

- 输出中命中了 `vLLM-origin DSV3 router GEMM`。
- 但当前模型是 `Qwen3.6-27B-AWQ-INT4`，trace 中也出现了 GDN / hybrid linear 相关 kernel；该 fuse pattern 可能是通用规则对相近 kernel cluster 的误归因。
- 因此本报告不把 DSV3 router GEMM 作为明确优化方向，只保留为“需要人工复核的分析脚本提示”。

## 9. Kernel Table 摘要：`concurrency=4`

### 9.1 Prefill

| Kernel | GPU time | Share | Launches | 初步判断 |
|---|---:|---:|---:|---|
| `marlin::Marlin<..., 256, 4, 16, 4, false, ...>` | `19,180.06 ms` | `69.4%` | `16,384` | 并发场景 prefill 最大热点仍是 AWQ Marlin GEMM |
| `flash_fwd_splitkv_kernel<...>` | `6,477.00 ms` | `23.4%` | `128` | FlashAttention 仍是第二大热点 |
| `merge_16x16_to_64x64_inverse_kernel` | `305.75 ms` | `1.1%` | `384` | GDN / hybrid linear 相关辅助热点 |

### 9.2 Decode

| Kernel | GPU time | Share | Launches | 初步判断 |
|---|---:|---:|---:|---|
| `marlin::Marlin<..., 256, 4, 16, 4, false, ...>` | `21,906.73 ms` | `65.9%` | `18,449` | 并发 decode 中大 batch/混合阶段 Marlin 是最大热点 |
| `flash_fwd_splitkv_kernel<..., true, ...>` | `6,937.97 ms` | `20.9%` | `144` | 长上下文 attention 是第二大热点 |
| `marlin::Marlin<..., 256, 1, 8, 8, true, ...>` | `1,224.34 ms` | `3.7%` | `29,131` | 小 batch / CUDA graph decode Marlin 路径 |
| `merge_16x16_to_64x64_inverse_kernel` | `350.39 ms` | `1.1%` | `433` | GDN / hybrid linear 辅助热点 |

### 9.3 All

| Kernel | GPU time | Share | Launches | 初步判断 |
|---|---:|---:|---:|---|
| `marlin::Marlin<..., 256, 4, 16, 4, false, ...>` | `37,017.14 ms` | `56.5%` | `30,831` | 全局最大热点 |
| `flash_fwd_splitkv_kernel<..., true, ...>` | `13,916.61 ms` | `21.2%` | `256` | 全局第二热点 |
| `marlin::Marlin<..., 256, 1, 8, 8, true, ...>` | `4,388.59 ms` | `6.7%` | `99,637` | 小 batch decode Marlin |
| `flash_fwd_splitkv_kernel<..., false, ...>` | `3,994.10 ms` | `6.1%` | `6,227` | decode attention |

结论：

- c4 和 c1 的 kernel 排名方向一致：Marlin AWQ GEMM 第一，FlashAttention 第二。
- c4 并发慢不是因为换成了完全不同的 kernel 瓶颈，而是同一组主热点在多请求、长 prefill、KV 占用和调度排队下被放大。
- c4 trace 仍未显示超过 `1.0%` 阈值的明确 overlap opportunity；排队主要体现在 vLLM scheduler 状态日志，而不是 kernel 表中的 GPU idle 行。

## 10. 当前结论

| 假设 | 当前证据 | 状态 |
|---|---|---|
| 长上下文主要慢在 prefill | Stage 2 TTFT 占 E2E 约 `75.2%`，本轮 prefill kernel 表显示 Marlin + FlashAttention 主导 | 已支持 |
| `64K concurrency=4` 吞吐扩展弱来自 prefill / KV / scheduler | c4 日志显示 `Running/Waiting` 排队，KV usage 峰值 `74.7%`，kernel 表仍由 Marlin + FlashAttention 主导 | 已支持 |
| AWQ Marlin GEMM 不是唯一瓶颈 | prefill 中 Marlin `69.5%`、FlashAttention `23.5%`；decode 中 Marlin `58.7%`、attention `15.3%` | 已支持 |
| 继续加并发收益有限 | Stage 3 `64K c1 -> c4` 系统吞吐只小幅提升 | 已有 benchmark 支持 |

## 11. 下一步

优先级建议：

| 优先级 | 下一步 | 目的 |
|---:|---|---|
| 1 | 对比 `AWQ-INT4` 与 `NVFP4` 的同形状 profiler 或无干扰 benchmark | 判断 Marlin GEMM 热点是 AWQ 路径特有，还是模型结构/shape 共同问题 |
| 2 | 尝试 `FP8 KV cache`，但只作为容量/attention 对照 | 看 attention/KV 部分是否下降，不能指望解决 Marlin GEMM 主热点 |
| 3 | 若要继续并发方向，改用 Nsight Systems timeline | 更直接看 CPU/GPU timeline、queueing 和请求阶段重叠 |

如果只能做一个实验，建议先做：

```text
NVFP4 64K + output=512 无干扰复测，并尽量用同一 profiler 口径和 AWQ 对照
```

理由：Stage 4 已解释 AWQ 单请求和 c4 并发热点；下一步要判断这是 AWQ Marlin 路径问题，还是 Qwen3.6-27B 在当前 vLLM/A800 下的共同结构问题。

## 12. 完成标准

Stage 4 完成时，应至少产出：

- profiler trace 路径：已完成。
- prefill / decode 或混合 trace 的 top kernels 表：已完成。
- 是否存在明显 GPU idle / scheduler gap：c1/c4 trace 均未见超过 `1.0%` 阈值的 overlap 机会；c4 vLLM 日志显示明确 Running/Waiting 排队。
- 一条明确下一步：NVFP4 64K+512 无干扰复测或同形状 profiler 对照。

没有 trace 前，不能把任何 kernel 层解释写成已验证结论。
