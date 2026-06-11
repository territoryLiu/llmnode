# 第十二阶段实验报告：优化动作链与上线边界收口

> 文档定位：项目知识库中的 LLM serving 优化实验报告，不属于 `llmnode` 项目蓝图、契约或正式路线图。  
> 实验目标：完成 `experiment-master-plan.md` 里 `V4 / V5` 的第一轮收口，把现有 benchmark / profiler / `nsys` / 质量回归证据转成工程动作链、上线边界和最小回归模板。  
> 更新时间：2026-06-11。  
> 当前结论状态：已完成第二轮决策收口；已吸收 Stage 8 clean `64K + 512` `Marlin / FlashAttention` `LaunchStats` 结果，当前不再把 `V2` 当作阻塞项。

相关专题：

- 总方案见 [experiment-master-plan.md](../experiment-master-plan.md)
- 主配置决策见 [stage10-vllm-environment-and-config-decision.md](./stage10-vllm-environment-and-config-decision.md)
- launch gap / queue 归因见 [stage11-launch-gap-and-queue-analysis.md](./stage11-launch-gap-and-queue-analysis.md)
- `64K + 512` 同形状 `ncu` 现状见 [stage8-ncu-64k-same-shape.md](./stage8-ncu-64k-same-shape.md)

## 1. 一页结论

当前这条 vLLM 主线，在补齐 `64K + 512` 同形状 `ncu` 核心证据后，可以收口出一版更明确的工程决策：

1. 默认上线候选继续定为 `AWQ-INT4`，不是 `NVFP4`。
2. `NVFP4` 保留，但角色是同形状对照与 FP4 路线观察项，不替代主基线。
3. `AWQ + FP8 KV cache` 继续只做容量实验配置，当前禁止当作默认上线配置。
4. `64K + 512` 的 `Marlin / FlashAttention` 同形状 `ncu LaunchStats` 已打通；下一步不是继续扩 benchmark，而是把结果转成瓶颈解释。
5. 上线边界已经能写成一份最小手册：默认 profile、并发档位、长上下文边界、环境检查、以及每次变更后的最小回归模板。

## 2. 证据范围

本轮只使用 Stage 2-11 的已有证据：

1. Stage 2：
   - `AWQ / NVFP4` 单并发 `16K / 64K + 512`
   - `NVFP4 0.55 / 0.6` 容量对照
2. Stage 3：
   - `AWQ-INT4` `c1 / c2 / c4` 并发阶梯
3. Stage 4 / Stage 6：
   - `AWQ / NVFP4` profiler 热点长期收敛到 `Marlin + FlashAttention`
4. Stage 5 / Stage 7：
   - `AWQ + FP8 KV` 容量提升与质量退化
5. Stage 8：
   - `64K + 512` same-shape workload 已可稳定构造
   - clean `Marlin` `LaunchStats` 已可导入
   - clean `FlashAttention` `LaunchStats` 已可导入
   - KV cache 观测：`21.12 GiB` 可用、`86,240 tokens`、`66,048 tokens/request` 最大并发 `5.01x`
6. Stage 10：
   - 环境核验与主配置决策
7. Stage 11：
   - launch gap / queue 第一轮归因

本轮不新增新的 benchmark；Nsight 证据来自 Stage 8 clean 复测产物。

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

1. 用 Stage 8 clean `LaunchStats` 解释 Stage 11 的 launch gap / queue 现象。
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
| `64K` `ncu` 与现有 Stage 11 一致，仍以 queue + launch/sync gap 为主 | 优先回到调度与阶段切换解释，而不是马上做更底层 patch |

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

## 9. 已确认

1. `AWQ-INT4` 已具备默认上线候选所需的第一轮证据闭环。
2. `NVFP4` 当前仍是观察项，不是默认基线。
3. `FP8 KV` 当前仍只能作为容量实验配置。
4. `64K + 512` 同形状 `ncu LaunchStats` 已完成，不再是阻塞项。
5. 现在已经足够固定一套最小回归模板与上线前环境检查。

## 10. 仍不确定

1. 只凭 `LaunchStats` 还不能最终判断 `64K` 主代表点的底层限制更偏 memory behavior 还是 occupancy / shared memory / registers。
2. 仓库默认 profile 是否应正式改到 `AWQ-INT4`，这需要单独做配置更新与验证。
3. 未来是否要把 `NVFP4` 升为容量优先场景的正式备选上线配置，还缺更强证据。

## 11. 下一步

- 下一次只改什么变量：
  Stage 11 / Stage 12 的解释链，把 clean `LaunchStats` 转成优化动作判断。
- 预期要验证什么：
  是否需要继续补 `Occupancy / MemoryWorkloadAnalysis`；如果不需要，当前主线可以进入上线回归模板固化。
- 当前阶段不再优先做什么：
  不再扩更多 benchmark 版本，不优先攻克 server-side attach，不先盲调上层参数
