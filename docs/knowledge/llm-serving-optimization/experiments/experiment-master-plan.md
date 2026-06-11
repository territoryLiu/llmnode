# vLLM Serving 性能分析与优化总实验方案（已归档）

> **状态：已归档。** 本方案所有退出标准已于 2026-06-11 全部完成，后续不再更新，仅供回溯查阅。  
> 文档定位：`docs/knowledge/llm-serving-optimization/` 的主线总方案，只服务当前 `llmnode` 项目的 `vLLM + Qwen3.6-27B`。  
> 目标：以”资深大模型部署工程师”的工作方式，完成从配置筛选、指标解释、瓶颈归因到上线边界与优化动作的完整闭环。  
> 当前范围：不再承担 `SGLang / llama.cpp` 的统一路线规划，也不再要求把所有量化版本反复重测一遍。

## 1. 当前做到哪一步了

当前主线已经不是“从零搭实验”，而是进入收口阶段。

### 1.1 已完成的阶段

| 阶段 | 目标 | 当前状态 | 结果文档 |
|---|---|---|---|
| Stage 1-7 | 基线、并发、profiler、FP8 KV、Nsight bring-up | 已完成 | `experiments/stage1` 到 `stage7` |
| V0 | 环境与证据清点 | 已完成 | [stage10-vllm-environment-and-config-decision.md](./experiments/stage10-vllm-environment-and-config-decision.md) |
| V1 | 主配置决策收口 | 已完成第一轮 | [stage10-vllm-environment-and-config-decision.md](./experiments/stage10-vllm-environment-and-config-decision.md) |
| V3 | launch gap / queue 归因 | 已完成第一轮 | [stage11-launch-gap-and-queue-analysis.md](./experiments/stage11-launch-gap-and-queue-analysis.md) |
| V4 | 从证据到优化动作 | 已完成第一轮 | [stage12-vllm-optimization-actions-and-deployment-boundaries.md](./experiments/stage12-vllm-optimization-actions-and-deployment-boundaries.md) |
| V5 | 上线边界与回归模板 | 已完成第一轮 | [stage12-vllm-optimization-actions-and-deployment-boundaries.md](./experiments/stage12-vllm-optimization-actions-and-deployment-boundaries.md) |

### 1.2 当前核心收口项

| 阶段 | 目标 | 当前状态 |
|---|---|---|
| V2 | `64K + 512` 同形状 `Nsight Compute` 闭环 | 已完成闭环：clean `LaunchStats` + register 压力诊断 + 优化动作判断 |

所有工作包均已完成第一轮闭环。V2 的最终闭环结论：

1. 两个主热点 kernel（Marlin / FlashAttention）的共同瓶颈是 **register 压力（255/thread）**，不是 shared memory。
2. Marlin HBM 利用率仅 22-25%（单请求 decode），但受 workload 特性（batch_size=1, 算术强度极低）和 L2 hit rate（62.5%）限制。
3. 255 register 策略可能是 Marlin 的 ILP 优化有意选择，不是简单浪费。
4. **当前最可操作的优化方向在调度层**（chunked prefill、并发限制），不在 kernel 层。

```text
主配置、主指标、主瓶颈、主上线边界都已有闭环；
64K 主代表点的 ncu 低层证据已补齐并转成优化动作判断；
下一步是调度层实测，不是继续深采 kernel section。
```

## 2. 当前稳定结论

下面这些结论已经足够稳定，后续默认沿用，不再反复推倒重来。

### 2.1 配置角色

| profile | 当前角色 | 是否默认上线候选 |
|---|---|---|
| `vllm_qwen36-27b-awq-int4` | 默认主基线 / 主分析基线 | 是 |
| `vllm_qwen36-27b-nvfp4` | 同形状对照 / FP4 路线观察项 | 否 |
| `vllm_qwen36-27b-awq-int4-fp8-kv` | 容量实验配置 | 否 |

### 2.2 代表 workload

| workload | 用途 |
|---|---|
| `16K + 512` | 快速回归、已打通的 `ncu` 代表点 |
| `64K + 512` | 当前主代表点，覆盖长上下文、KV 压力、decode 占比、queue 与 profiler 代表性 |

### 2.3 主要热点与现象

1. 主热点长期收敛到 `Marlin GEMM + FlashAttention`。
2. `64K` 的问题不是“GPU 大量完全空闲”，而是：
   - 单流主热点长期占主导；
   - 同时存在明显 launch / sync gap；
   - `c4` 下还有清晰的 `Running / Waiting` 分段。
3. `AWQ + FP8 KV cache` 的容量收益成立，但当前不具备默认上线条件，因为速度无优势且质量回归已出现新增退化。

## 3. 现在不再做什么

为了把主线做完，下面这些内容从总方案里正式删掉，不再当作必做项：

1. 不再把 `SGLang / llama.cpp` 纳入这份主方案。
2. 不再要求把“各种版本的 Qwen3.6-27B”全部重跑一遍 `16K/64K + 512` 常规指标。
3. 不再继续把 `FP8` 权重版当作当前 A800 主线候选。
4. 不再把 `AWQ + FP8 KV cache` 当作常规速度候选重复测速。
5. 不再优先新增 benchmark 版本、更多量化版本或更多模型族。

正确策略已经收敛为：

```text
只保留少数主候选，
补齐 64K 主代表点证据，
然后把优化动作和上线边界做实。
```

## 4. 还需要不要继续测各种版本的 16K / 64K + 512 指标

结论：不需要再对“各种版本”全面普测。

后续只保留下面三类测试：

### 4.1 必保留的性能回归

只对主线配置和观察项保留固定回归：

| profile | `16K + 512` | `64K + 512` | 说明 |
|---|---|---|---|
| `AWQ-INT4` | 保留 | 保留 | 主线基线，必须持续可回归 |
| `NVFP4` | 可选 | 保留 | 作为同形状对照，重点保留 `64K` |
| `AWQ + FP8 KV` | 非默认 | 按需 | 只在容量或质量相关变更后复测，不做日常性能主回归 |

### 4.2 必保留的并发回归

只保留主线 profile 的 `c1 / c2 / c4`：

1. `c1`：默认性能基线
2. `c2`：观察无明显 Waiting 时的重叠情况
3. `c4`：观察 queue、KV usage 和长 prefill 放大

### 4.3 必保留的质量回归

1. 长上下文一致性
2. 代码生成
3. 数学推理
4. 结构化输出 / JSON

特别说明：

1. `AWQ-INT4` 不需要再因为“它是主线”而无限重跑所有组合。
2. `NVFP4` 不需要再补“所有长度、所有并发、所有指标”的对称矩阵，只保留能支撑角色判断的代表点。
3. `AWQ + FP8 KV` 只有在继续研究容量路线时才值得补测，且优先级低于 `V2`。

## 5. 剩余工作只保留五个包

`V0 / V1 / V3 / V4 / V5` 已有第一轮结果，但主计划仍保留为后续更新的落点。真正还要继续推进的工作如下。

### 5.1 V0：环境与证据清点

当前状态：已完成，可按需复查，不单独扩展。

固定检查项：

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control env
/home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control status
/home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control doctor
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
```

使用规则：

1. 非提权 `doctor` 的 GPU / Docker 结论不能直接当真。
2. 任何新的真实性能结论前，都先看 `nvidia-smi` 外部占卡。
3. GPU 受污染时，只做方法摸排或文档收口，不写新的主结论。

### 5.2 V1：主配置决策收口

当前状态：已完成第一轮，不再扩成“大矩阵复测”。

当前唯一有效决策表：

| 类别 | profile |
|---|---|
| 默认上线候选 | `vllm_qwen36-27b-awq-int4` |
| 观察项 | `vllm_qwen36-27b-nvfp4` |
| 实验项 | `vllm_qwen36-27b-awq-int4-fp8-kv` |

后续只有在出现强反证时才更新这一表。

### 5.3 V2：`64K + 512` 同形状 `Nsight Compute` 闭环

当前状态：**已完成闭环**。clean `LaunchStats` 已拿到，register 压力诊断已完成，优化动作判断已写入 Stage 12 第 9 节。

#### 最终结论

1. 两个主热点 kernel 的共同瓶颈是 **register 压力（255/thread）**，不是 shared memory。
2. Marlin occupancy 12.5%（1 block/SM），FlashAttention 12.5%（2 block/SM）。
3. Marlin HBM 利用率 22-25%，远未饱和，但受 workload 特性和 L2 hit rate 限制。
4. 255 register 策略可能是 Marlin 的 ILP 优化有意选择。
5. 当前最可操作方向在调度层，不在 kernel 层。
6. 不再需要补 `Occupancy / MemoryWorkloadAnalysis`——当前证据已足够做调度层决策。

#### 当前已知边界

1. `max_model_len=66048` 是当前最有效的 same-shape 保护手段。
2. `VLLM_ENABLE_V1_MULTIPROCESSING=0` 可消掉 `spawn`。
3. `enforce_eager=True` 可关掉 `torch.compile + CUDA Graph` 干扰。
4. `server-under-ncu` 仍会在首个 instrumented API 前退出。
5. 真正可用的 attach 方向不是跨容器 attach，而是同一个 `launch` 容器里的 `launch + attach`。
6. `target-processes all` 下，同容器 attach 可能先命中短生命周期子进程，而不是稳定的 `APIServer`。
7. 即使 `application-only` 能稳定 attach 到 `APIServer`，真正执行 kernel 的关键进程仍会继续下沉到后续 `EngineCore` 子进程链。
8. 仅仅延后 `target-processes all` 的 attach 时机，仍不足以稳定绕开 `model_executor.models.registry` 子进程。
9. 把 `target-processes-filter` 正向收窄到 `regex:.*EngineCore.*` 虽能让 launch 接受，但当前会直接丢掉 attach 通道。
10. `target-processes-filter exclude:python3` 虽能绕开 `149` 并保留 `EngineCore`，但当前同样会直接丢掉 attach 通道。
11. 之前多轮 non-attach/offline `ncu` 失败混入了一个明确命令错误：`--force-overwrite true` 在 Nsight Compute 2026.1.1 中应写成无值 flag，错误写法会让 `true` 被当成目标程序，导致目标脚本没有真正执行。
12. 修正为 `--force-overwrite` 后，offline 单进程 + eager 路径已能导出历史样本：
    - `/tmp/llmnode-awq-16k512-param-marlin-lc1-fixed.ncu-rep`
    - `/tmp/llmnode-awq-64k512-param-marlin-lc1-fixed.ncu-rep`
13. GPU 空闲窗口下已完成 clean 样本：
    - `/tmp/llmnode-awq-64k512-clean-marlin-lc1.ncu-rep`
    - `/tmp/llmnode-awq-64k512-clean-flashattn-lc1.ncu-rep`

#### 下一步只做什么

1. 用 clean `Marlin / FlashAttention` `LaunchStats` 更新 Stage 11 / Stage 12 的瓶颈解释。
2. 判断是否值得继续补 `Occupancy / MemoryWorkloadAnalysis`；如果只需要上线边界，当前 `LaunchStats` 已够支撑“主热点可定位”的证据链。
3. 如果必须做 server-side 请求窗口，再继续同容器 `launch + attach`，重点解决 `APIServer -> EngineCore` 的 target-process 覆盖问题。
4. 暂时不把 `regex:.*EngineCore.*` 或 `exclude:python3` 当主突破口，因为当前都会让 attach 通道失效。

#### 这阶段不再做什么

1. 不再回退去重跑旧的 `16K` 常规 benchmark
2. 不再重复验证“默认 `262144` 会挤掉 KV cache”这种旧结论
3. 不在 GPU 受污染时把 `V2` 结果写成最终结论

#### 成功标准

1. 至少拿到一组 `64K + 512` 的 `Marlin` section：已完成 clean `LaunchStats`
2. 最好同时拿到 `FlashAttention` section：已完成 clean `LaunchStats`
3. 能给出 `16K` 与 `64K` 的同口径低层对比：已有初步同口径 `LaunchStats`
4. 能回答当前 `64K` 更像 occupancy / registers / shared memory 约束，还是 memory behavior 约束：仍需更深 section 才能下最终判断

当前方法摸排与证据见：

- [stage8-ncu-64k-same-shape.md](./experiments/stage8-ncu-64k-same-shape.md)

### 5.4 V3：launch gap / queue 归因深化

当前状态：已完成第一轮。V2 最终闭环后，Stage 11 的 gap 分类与 ncu register 压力诊断已关联（见 Stage 12 第 9.5 节），不再需要额外 `nsys` 采样。

后续只在以下情况继续：

1. 调度层实测（chunked prefill）后发现新的 gap 模式
2. 需要用 NVTX 阶段标签把 prefill / decode / scheduler gap 切得更清楚

当前有效结论见：

- [stage11-launch-gap-and-queue-analysis.md](./experiments/stage11-launch-gap-and-queue-analysis.md)

### 5.5 V4：从证据到优化动作

当前状态：**已完成第二轮更新**，已吸收 V2 最终闭环结论。

动作优先级（已更新）：

1. 保留 `AWQ-INT4` 主线
2. 保留 `NVFP4` 观察项
3. 禁止把 `FP8 KV` 包装成默认上线配置
4. ~~先补 `64K` 同形状 `ncu`~~ → **已完成**
5. 下一步方向已判断：**调度层优先**（chunked prefill、`max_num_seqs`），kernel 层等上游

当前收口见：

- [stage12-vllm-optimization-actions-and-deployment-boundaries.md](./experiments/stage12-vllm-optimization-actions-and-deployment-boundaries.md) 第 9 节

### 5.6 V5：上线边界与回归模板

当前状态：已完成第一轮，默认按下面边界执行。

| 主题 | 当前建议 |
|---|---|
| 默认 profile | `vllm_qwen36-27b-awq-int4` |
| 观察 profile | `vllm_qwen36-27b-nvfp4` |
| 实验 profile | `vllm_qwen36-27b-awq-int4-fp8-kv` |
| 默认性能回归 | `16K + 512`、`64K + 512` |
| 默认并发回归 | `c1 / c2 / c4` |
| 默认质量回归 | 长上下文、代码、数学、结构化输出 |
| 不可省略环境检查 | `nvidia-smi` 外部 GPU 进程核验 |

## 6. 后续执行顺序

`V0-V5` 均已完成第一轮闭环。V2 最终闭环已完成（register 压力诊断 + 优化动作判断）。

后续方向（不再是主线阻塞项，而是可选深化）：

1. **调度层实测**：chunked prefill 对 `64K` TTFT 的影响（只改 `max_num_batched_tokens`）
2. **并发边界确认**：`max_num_seqs=2` vs `4` 的交互式延迟回归
3. **上游追踪**：关注 Marlin / vLLM 是否提供低 register 版本 kernel
4. **新硬件评估**：如有 Hopper / Blackwell 环境，重新评估 NVFP4 / FP8 路线

当前主线不再有阻塞项。如果只能继续做一件事：

```text
实测 chunked prefill 对 64K TTFT 的影响，
验证调度层优化是否比 kernel 层更可操作。
```

## 7. 统一记录规则

所有后续实验继续统一记录：

1. model / profile / vLLM version
2. prompt tokens / output tokens / concurrency
3. warmup / measure
4. GPU 型号
5. 关键启动参数
6. 是否存在外部 GPU 干扰

统一指标：

1. `TTFT`
2. `TPOT / ITL`
3. `completion tok/s`
4. `E2E latency`
5. `success rate`
6. `KV cache size / usage`
7. `Running / Waiting`
8. `gpu_memory_utilization`

统一规则：

1. 写清哪些是实测，哪些只是推断。
2. 每轮只改一个主要变量。
3. GPU 受污染时不输出新的主结论。

## 8. 文档落点

| 类型 | 路径 |
|---|---|
| 总方案（已归档） | `docs/knowledge/llm-serving-optimization/experiments/experiment-master-plan.md` |
| 阶段实验报告 | `docs/knowledge/llm-serving-optimization/experiments/` |
| benchmark / KV / profiler 方法 | `docs/knowledge/llm-serving-optimization/performance/` |
| 量化与 KV 配置结论 | `docs/knowledge/llm-serving-optimization/optimization/` |
| vLLM 参数与机制 | `docs/knowledge/llm-serving-optimization/serving/` |

## 9. 退出标准

只有下面条件都满足，这条 `vLLM` 主线才算真正完成：

1. `AWQ-INT4 / NVFP4 / AWQ+FP8-KV` 的角色和边界不再摇摆。**[已完成]** — Stage 10 决策表已固定。
2. `64K + 512` 的 `torch profiler + nsys + ncu` 证据链完整。**[已完成]** — Stage 8 clean LaunchStats + Stage 12 register 压力诊断。
3. launch gap、queue 与单流主热点之间的关系已经足够指导动作。**[已完成]** — Stage 11 归因 + Stage 12 关联分析。
4. 已形成默认上线配置、观察配置和实验配置清单。**[已完成]** — Stage 12 第 3/4/8 节。
5. 已形成一条真实可执行的优化动作链，而不是停留在”知道热点是谁”。**[已完成]** — Stage 12 第 9.4 节：调度层优先（chunked prefill、max_num_seqs）、kernel 层等上游。
