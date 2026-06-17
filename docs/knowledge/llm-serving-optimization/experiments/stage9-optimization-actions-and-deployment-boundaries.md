# 第九阶段实验报告：优化动作链与上线边界收口

> 文档定位：项目知识库中的 LLM serving 优化实验报告，不属于 `llmnode` 项目蓝图、契约或正式路线图。
> 实验目标：完成 `experiment-master-plan.md` 里 `V4 / V5` 的第一轮收口，把现有 benchmark / profiler / `nsys` / 质量回归证据转成工程动作链、上线边界和最小回归模板。
> 更新时间：2026-06-11。
> 当前结论状态：已完成第二轮决策收口；已吸收 Stage 6b clean `64K + 512` `Marlin / FlashAttention` `LaunchStats` 结果，当前不再把 `V2` 当作阻塞项。

相关专题：

- 总方案见 [experiment-master-plan.md](./experiment-master-plan.md)
- 主配置决策见 [stage7-vllm-environment-and-config-decision.md](./stage7-vllm-environment-and-config-decision.md)
- launch gap / queue 归因见 [stage8-launch-gap-and-queue-analysis.md](./stage8-launch-gap-and-queue-analysis.md)
- `64K + 512` 同形状 `ncu` 现状见 [stage6b-nsight-toolchain.md](./stage6b-nsight-toolchain.md)

## 1. 一页结论

当前这条 vLLM 主线，在补齐 `64K + 512` 同形状 `ncu` 核心证据后，可以收口出一版更明确的工程决策：

1. 默认上线候选继续定为 `AWQ-INT4`，不是 `NVFP4`。
2. `NVFP4` 保留，但角色是同形状对照与 FP4 路线观察项，不替代主基线。
3. `AWQ + FP8 KV cache` 继续只做容量实验配置，当前禁止当作默认上线配置。
4. `64K + 512` 的 `Marlin / FlashAttention` 同形状 `ncu LaunchStats` 已打通；下一步不是继续扩 benchmark，而是把结果转成瓶颈解释。
5. 上线边界已经能写成一份最小手册：默认 profile、并发档位、长上下文边界、环境检查、以及每次变更后的最小回归模板。

## 2. 证据范围

本轮只使用已有证据：

1. Stage 1-2：
   - `AWQ / NVFP4` 单并发 `16K / 64K + 512`
   - `NVFP4 0.6` 容量与速度对照
2. Stage 3：
   - `AWQ-INT4` `c1 / c2 / c4` 并发阶梯
3. Stage 4 / Stage 5：
   - `AWQ / NVFP4` profiler 热点长期收敛到 `Marlin + FlashAttention`
4. Stage 6a：
   - `AWQ + FP8 KV` 容量、速度与质量退化
5. Stage 6b：
   - `64K + 512` same-shape workload 已可稳定构造
   - clean `Marlin` `LaunchStats` 已可导入
   - clean `FlashAttention` `LaunchStats` 已可导入
   - KV cache 观测：`21.12 GiB` 可用、`86,240 tokens`、`66,048 tokens/request` 最大并发 `5.01x`
6. Stage 7：
   - 环境核验与主配置决策
7. Stage 8：
   - launch gap / queue 第一轮归因

本轮不新增新的 benchmark；Nsight 证据来自 Stage 6b clean 复测产物。

## 3. 保留 / 观察 / 禁用 清单

| 类别 | profile | 当前处理 | 原因 |
|---|---|---|---|
| 保留 | `vllm_qwen36-27b-awq-int4` | 默认上线候选 / 主分析基线 | 权重显存最低，`64K + 512` 主口径最完整，并发与 profiler / `nsys` 证据最全 |
| 观察 | `vllm_qwen36-27b-nvfp4` | 同形状对照 / FP4 路线观察项 | 单并发有竞争力，但主线证据仍弱于 AWQ，尚不足以替代默认基线 |
| 禁用默认上线 | `vllm_qwen36-27b-awq-int4-fp8-kv` | 仅容量实验配置 | 容量收益成立，但质量回归已有新增退化，当前不能直接上线 |

## 4. 默认上线边界

### 4.1 默认 profile 与参数

当前推荐的默认部署基线：

| 项目 | 当前建议 |
|---|---|
| backend | vLLM |
| profile | `vllm_qwen36-27b-awq-int4` |
| `gpu_memory_utilization` | `0.55` |
| `max_model_len` | `262144` |
| `max_num_seqs` | `4` |
| attention backend | `FLASH_ATTN` |
| AWQ kernel | `MarlinLinearKernel for CompressedTensorsWNA16` |

说明：

- 这是一条“当前最稳的主线”，不是“所有问题都已经最优”的意思。
- 仓库默认激活 profile 目前仍是 `NVFP4`，这和当前主线决策不一致；当前文档只收口工程建议，不自动等同于仓库默认值已经同步。

### 4.2 长上下文边界

| 主题 | 当前建议 |
|---|---|
| `64K` | 视为当前主代表点，已稳定可测、可分析、可回归 |
| `256K` | 仍按“贴边能力”理解，不能当作默认稳定服务承诺 |
| `64K + 512` 同形状 `ncu` | clean `Marlin / FlashAttention` `LaunchStats` 已完成；更深 section 按需补 |

当前判断：

> `64K` 是当前应承诺、应持续回归、应作为优化主代表点的长度；`256K` 仍更像容量上限附近能力，不适合写成默认 SLA。

### 4.3 并发边界

| 并发档位 | 当前判断 |
|---|---|
| `c1` | 默认性能回归基线 |
| `c2` | 仍属可接受的主观察档位；没有明显 Waiting 队列 |
| `c4` | 可跑通，但已出现明确 Waiting 队列与显著等待放大，适合作为压力/容量观察档位，不适合作为默认交互式 SLA |

当前判断：

> 如果目标是交互式稳定延迟，默认对外口径不应直接用 `64K c4`；它更适合作为容量与排队压力观测点。

## 5. 下一轮优化动作链

### 5.1 先做什么

1. 用 Stage 6b clean `LaunchStats` 解释 Stage 8 的 launch gap / queue 现象。
2. 判断是否需要继续补 `Occupancy / MemoryWorkloadAnalysis`；如果优化动作仍停留在参数和调度层，暂不深采。
3. 维持 `AWQ-INT4` 主线，不在这时切默认基线到 `NVFP4`。

### 5.2 暂时不先做什么

1. 不先盲调 `max_num_seqs`
2. 不先盲调 graph 开关
3. 不先扩更多量化版本
4. 不把 `FP8 KV` 重新包装成默认上线候选

### 5.3 `V2` 成功后的分叉

| 条件 | 下一步 |
|---|---|
| 只需要上线边界与回归模板 | 不继续深采；保留当前 `LaunchStats` 作为主热点 section 证据 |
| 需要判断 `Marlin` 是否被 registers / shared memory / occupancy 限制 | 补 `Occupancy`，优先 offline 单进程 + eager 路径 |
| 需要判断 `FlashAttention` memory behavior | 补 `MemoryWorkloadAnalysis`，优先 offline 单进程 + eager 路径 |
| `64K` `ncu` 与现有 Stage 8 一致，仍以 queue + launch/sync gap 为主 | 优先回到调度与阶段切换解释，而不是马上做更底层 patch |

## 6. GPU 环境与上线前检查

### 6.1 不可省略的环境检查

每次要做真实性能结论前，至少先做：

```bash
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
```

原因：

- 这个仓库已经多次遇到外部 GPU 进程干扰
- 受污染窗口下即使请求能成功，也不能直接把性能与容量结论当作干净证据

### 6.2 当前环境规则

| 情况 | 当前处理 |
|---|---|
| 非提权 `doctor` 报 GPU / 镜像缺失 | 不采信，改用宿主提权环境复核 |
| GPU 上有外部大进程 | 不做新的主结论采样，只做摸排或文档收口 |
| managed 服务默认 profile 与主线建议不一致 | 允许存在，但必须在报告中明确指出 |

## 7. 最小回归模板

### 7.1 性能回归

至少固定：

1. `16K + 512`
2. `64K + 512`

用途：

- `16K + 512` 用于快速回归已知 `ncu` 成功代表点
- `64K + 512` 用于主代表点与真实优化收益判断

### 7.2 并发回归

至少固定：

1. `c1`
2. `c2`
3. `c4`

用途：

- `c1`：默认性能口径
- `c2`：观察重叠但不形成明显 Waiting 的中间档
- `c4`：观察 queue、KV usage 与长 prefill 放大

### 7.3 质量回归

至少固定：

1. 长上下文一致性
2. 代码生成
3. 数学推理
4. 结构化输出 / JSON 稳定性

说明：

- `FP8 KV` 路线至少已经在代码生成和数学推理上出现新增退化
- 这些回归不应在新的 profile 变更后被省略

## 8. 当前工程边界表

| 主题 | 当前建议 |
|---|---|
| 默认 profile | `vllm_qwen36-27b-awq-int4` |
| 观察 profile | `vllm_qwen36-27b-nvfp4` |
| 实验 profile | `vllm_qwen36-27b-awq-int4-fp8-kv` |
| 默认性能回归 | `16K + 512`、`64K + 512` |
| 默认并发回归 | `c1 / c2 / c4` |
| 默认质量回归 | 长上下文、代码、数学、结构化输出 |
| 不可省略环境检查 | `nvidia-smi` 外部 GPU 进程核验 |
| 当前不允许直接声称上线可用的配置 | `FP8 KV cache` 路线 |

## 9. V2 最终闭环：从 LaunchStats 到瓶颈判断与优化动作

### 9.1 Occupancy 瓶颈诊断

基于 Stage 6b clean `64K + 512` `LaunchStats`，结合 A800 硬件规格（108 SMs, 每 SM 65,536 registers, 每 SM 164 KiB configurable shared memory），做出如下判断：

**Marlin GEMM：**

| 指标 | 值 | 含义 |
|---|---|---|
| Registers Per Thread | `255` | 接近上限，每 block 需 255×256=65,280 registers |
| 每 SM 可放 block 数 | `1` | 65,280 < 65,536，刚好 1 个 |
| 实际 occupancy | `12.5%` | 1/8，与 ncu 实测一致 |
| 瓶颈根源 | **register 压力** | 不是 shared memory（166.91 KiB 虽高但不是主因） |

**FlashAttention：**

| 指标 | 值 | 含义 |
|---|---|---|
| Registers Per Thread | `255` | 同样接近上限，每 block 需 255×128=32,640 registers |
| 每 SM 可放 block 数 | `2` | 32,640×2=65,280 < 65,536 |
| 实际 occupancy | `12.5%` | 2/16，与 ncu 实测一致 |
| 瓶颈根源 | **register 压力** | shared memory 仅 49.15 KiB/block，远未触及限制 |

结论：**两个主热点 kernel 的共同瓶颈是 register 压力（255/thread），不是 shared memory。**

### 9.2 Memory 吞吐利用率

| Kernel | 实测吞吐 | A800 HBM 峰值 | 利用率 | L2 hit rate |
|---|---|---|---|---|
| Marlin | `~447-491 GB/s` | `~2,048 GB/s` | `22-25%` | `62.5%` |
| FlashAttention | `~19 GB/s` | - | 极低 | `98.6%`（几乎全 L2） |

- Marlin 只用了约 1/4 的 HBM 带宽，远未饱和。
- FlashAttention 几乎完全命中 L2（98.6%），瓶颈不在 HBM 带宽而在 L2 cache 带宽或计算。
- 低 occupancy → 活跃 warp 少 → 内存延迟隐藏不足 → HBM 利用率低。

### 9.3 关键权衡：occupancy vs ILP

Marlin 的 255 registers/thread 不一定是"浪费"。Weight-only dequantization kernel 的经典设计是：每个线程在 register 中缓存更多 weight fragment，减少重复内存访问，用指令级并行（ILP）替代 warp 级并行。这是 **occupancy vs ILP** 的经典权衡：

- 高 register 用量 → 单线程 ILP 高 → 每次内存访问利用率高
- 低 occupancy → 活跃 warp 少 → 内存延迟隐藏差
- 净效果取决于 workload：memory-bound decode 场景下，ILP 策略可能已接近最优

当前 Marlin 吞吐 447-491 GB/s（22-25% HBM 利用率）看起来不高，但考虑到：
1. 单请求 decode batch_size=1，算术强度极低
2. L2 hit rate 62.5%，实际 HBM 访问量已被 L2 减少
3. 255 register 策略可能是 Marlin 作者在权衡后的最优选择

因此 **occupancy 不一定是当前可操作的优化点**。

### 9.4 优化动作判断

综合 Stage 6b（ncu）、Stage 8（launch gap / queue）、Stage 9（本节）的证据链：

| 层级 | 瓶颈 | 当前可操作性 | 动作 |
|---|---|---|---|
| **调度/队列** | 长 prefill 分批进入 Running + launch/sync gap | 中 | 优先调 `max_num_seqs`、chunked prefill size |
| **Kernel occupancy** | 255 registers/thread → 12.5% occupancy | 低 | Marlin 是第三方 kernel，当前无上游低 register 替代；改需自写 kernel |
| **Memory 吞吐** | Marlin 22-25% HBM 利用率 | 低 | 受 occupancy 限制，且单请求 decode 本身 memory-bound 特征决定 |
| **KV cache 容量** | 64K 场景下 KV 压力大 | 已有方案 | AWQ-INT4 已释放 22.38 GiB 给 KV，当前够用 |

**优先行动：先在调度层做文章，而不是 kernel 层。**

具体动作链（优先级从高到低）：

1. **chunked prefill 调优**：当前 64K prefill 是一整块进入调度，导致长等待。尝试设置 `max_num_batched_tokens` 把 prefill 切成更小 chunk，让 decode 请求更早插入。
2. **`max_num_seqs` 从 4 调到 2**：Stage 8 已证明 c4 有明确 Waiting 队列，c2 没有。如果目标是交互式延迟，限制并发到 2 可能更合理。
3. **CUDA stream 并行**：当前 Marlin + FlashAttention 在单 stream 串行。如果 vLLM 支持多 stream，可以让 prefill attention 和 GEMM 部分重叠（需框架层支持，非用户参数可调）。
4. **等待上游 kernel 优化**：Marlin 的低 occupancy 问题需要上游 Marlin 项目或 vLLM 社区提供低 register 版本的 kernel。关注 vLLM 的 kernel 更新。
5. **不建议自写 kernel**：投入产出比太低。Marlin 已是 AWQ 社区最优 kernel 之一，自写难以超越。

### 9.5 与 Stage 8 launch gap 的关联

Stage 8 发现：
- `cudaLaunchKernel + cuLaunchKernelEx` 合计占 CUDA API time ~58-66%
- `cudaEventSynchronize` 占 ~32-40%
- CUDA Graph 在用但只占 ~0.1%

这与 ncu 发现的低 occupancy 一致：
- 每个 kernel launch 后，因 occupancy 低，GPU 很快完成计算并等待下一次 launch
- `cudaEventSynchronize` 高占比说明 CPU 端在频繁等待 GPU 完成
- 减少 launch 次数（chunked prefill）或提高单 kernel 利用率（更高 occupancy）都能减少 gap

但 kernel 层改动门槛高，调度层改动门槛低。所以先调调度。

## 10. 已确认

1. `AWQ-INT4` 已具备默认上线候选所需的第一轮证据闭环。
2. `NVFP4` 当前仍是观察项，不是默认基线。
3. `FP8 KV` 当前仍只能作为容量实验配置。
4. `64K + 512` 同形状 `ncu LaunchStats` 已完成，不再是阻塞项。
5. 现在已经足够固定一套最小回归模板与上线前环境检查。
6. `V2` 已最终闭环：两个主热点 kernel 的共同瓶颈是 **register 压力（255/thread）**，不是 shared memory。
7. Marlin 的 255 register 策略可能是 ILP 优化的有意选择，不是简单的"浪费"。
8. 当前最可操作的优化方向在 **调度层**（chunked prefill、并发限制），不在 kernel 层。
9. Marlin HBM 利用率 22-25%（单请求 decode），远未饱和，但受 workload 特性限制。

## 11. 仍不确定

1. chunked prefill 对 `64K` 场景的实际 TTFT 改善幅度，需要实测。
2. `max_num_seqs=2` vs `4` 的交互式延迟差异，需要回归验证。
3. Marlin 未来是否会提供低 register 版本 kernel（关注上游 PR）。
4. `NVFP4` 在 Hopper / Blackwell 上的实际表现，是否值得在新硬件上重新评估。

## 12. 下一步

- 下一步只做什么：
  实测 chunked prefill 对 64K TTFT 的影响。只改 `max_num_batched_tokens` 一个变量。
- 当前阶段不再优先做什么：
  不再补 `Occupancy / MemoryWorkloadAnalysis`（当前证据已足够做调度层决策）。
  不再扩更多 benchmark 版本。
  不优先攻克 server-side ncu attach。
  不自写 kernel。
