# 第十一阶段实验报告：launch gap 与 queue 深化归因

> 文档定位：项目知识库中的 LLM serving 优化实验报告，不属于 `llmnode` 项目蓝图、契约或正式路线图。  
> 实验目标：完成 `experiment-master-plan.md` 里 `V3` 的第一轮闭环，把已有 `nsys` 证据从“看到了 gap / queue”推进到“gap 属于哪一类、影响在哪个阶段、下一步该调度还是该继续看 kernel”。  
> 更新时间：2026-06-11。  
> 当前结论状态：已完成第二轮证据收口；已吸收 Stage 8 clean `64K + 512` `Marlin / FlashAttention` `LaunchStats` 结果，用于更新 V3 的下一步判断。

相关专题：

- 总方案见 [experiment-master-plan.md](./experiment-master-plan.md)
- Nsight bring-up 与 server-side `64K + 512` capture 见 [stage7-fp8-kv-quality-and-nsight.md](./stage7-fp8-kv-quality-and-nsight.md)
- AWQ 并发与 profiler 代表点见 [stage3-awq-concurrency.md](./stage3-awq-concurrency.md)、[stage4-awq-profiler.md](./stage4-awq-profiler.md)

## 1. 一页结论

本轮最重要的结论有四条：

1. 当前 `64K` 长请求的主要等待并不来自“GPU 没活干”，而是来自长 prefill 分批进入 Running、随后才逐步转入 decode 稳态。
2. `c2` 和 `c4` 的共同点是：GPU kernel 仍长期由 `Marlin + FlashAttention` 主导，同时 CUDA API 时间里 `cudaLaunchKernel + cudaEventSynchronize` 占比很高，说明 launch / sync gap 是真实存在的。
3. `c4` 的关键新增现象不是热点换了，而是出现了明确 `Running/Waiting` 分段：
   `2/2 -> 3/1 -> 4/0`。这说明 queue 的主来源是长 prefill 和批次切换，而不是 decode 末段才突然拥塞。
4. `64K + 512` 同形状 `ncu LaunchStats` 已补齐；现有证据更支持先把 queue + launch/sync gap 与 `Marlin / FlashAttention` 的 low-level 形态串起来，再决定是否补更深 section 或调上层参数。

## 2. 证据范围

本轮只使用已经存在的实测证据：

1. Stage 7 `server-side c2`：
   - `AWQ-INT4 64K + output=512, concurrency=2`
   - wall `79.22 s`
   - `Running=2 / Waiting=0`
   - KV usage 峰值约 `37.3%`
2. Stage 7 `server-side c4`：
   - `AWQ-INT4 64K + output=512, concurrency=4`
   - wall `136.84 s`
   - `Running=2 / Waiting=2 -> 3 / 1 -> 4 / 0`
   - KV usage 峰值约 `74.7%`
3. Stage 7 `nsys stats` 摘要：
   - kernel family
   - CUDA API 占比
   - CUDA graph evidence
4. Stage 3 / Stage 4：
   - AWQ `c1/c2/c4` 并发结果
   - AWQ `64K` profiler 热点长期收敛到 `Marlin + FlashAttention`
5. Stage 8：
   - clean `64K + 512` `Marlin` `LaunchStats`
   - clean `64K + 512` `FlashAttention` `LaunchStats`
   - KV cache 观测：`21.12 GiB` 可用、`86,240 tokens`、`66,048 tokens/request` 最大并发 `5.01x`

本轮不新增任何新的 `.nsys-rep`、`.sqlite` 或 GPU 采样文件。

## 3. gap 分类表

| gap 类型 | 主要出现阶段 | 证据来源 | 估计影响 | 当前判断 |
|---|---|---|---|---|
| prefill 批次切换 | `c4` server-side 长请求进入 Running 的前半段 | Stage 7 `c4`：`Running=2/Waiting=2 -> 3/1 -> 4/0`，同时 prompt throughput 分三段出现 | 高 | 已确认；这是 Waiting 持续存在的主来源 |
| decode 调度切换 | `c2/c4` 后半段 decode 收尾 | Stage 7 `c2/c4` 中 generation throughput 都是在后半段才明显升高 | 中 | 已确认存在，但不是首要瓶颈 |
| CUDA event / sync | 整个请求窗口，长请求更明显 | Stage 7 `c2` 中 `cudaEventSynchronize` 占 CUDA API time `39.8%`，`c4` 中占 `32.5%` | 中到高 | 已确认；是 launch/sync gap 的核心候选之一 |
| kernel launch / runtime dispatch | 整个请求窗口 | Stage 7 `c2` 中 `cudaLaunchKernel + cuLaunchKernelEx + cuLaunchKernel` 合计约 `57.9%` CUDA API time；`c4` 中约 `65.7%` | 中到高 | 已确认；和 event/sync 一起构成主要 API 层 gap |
| graph launch / runtime | steady-state decode 与重复执行阶段 | Stage 7 `c2/c4` 都存在 `cudaGraphLaunch` 和 graph trace，但占 CUDA API time 仅约 `0.1%` | 低到中 | 已确认在用，但当前不足以单独解释主要等待 |

## 4. queue 行为表

| concurrency | Running/Waiting 变化 | KV usage 峰值 | wall time | 判断 |
|---|---|---:|---:|---|
| `2` | 基本维持 `Running=2 / Waiting=0` | 约 `37.3%` | 约 `79.22 s` | 没有形成明显 Waiting 队列，主要是并发重叠，不是排队主导 |
| `4` | `Running=2 / Waiting=2 -> 3 / 1 -> 4 / 0` | 约 `74.7%` | 约 `136.84 s` | 明确形成 Waiting 队列，长 prefill 与批次切换共同放大等待时间 |

## 5. 为什么当前更像阶段性 queue + launch/sync gap，而不是“GPU 空转”

### 5.1 `c2` 已经说明问题不只是 queue

如果主要问题只是 queue，那么 `c2` 在没有 Waiting 队列时，理论上不应再看到明显的 launch/sync 代价。

但 Stage 7 `c2` 仍然显示：

- `Marlin` 占 GPU kernel time 约 `68.3%`
- `FlashAttention` 占 GPU kernel time 约 `23.5%`
- `cudaLaunchKernel` 占 CUDA API time 约 `42.3%`
- `cudaEventSynchronize` 占 CUDA API time 约 `39.8%`

这说明：

> 即使没有 Waiting 队列，长请求本身也已经有显著的 launch / sync gap。

因此 `c4` 的额外变慢不是凭空出现的第二种问题，而是在已有 launch/sync gap 之上，再叠加 queue 和长 prefill 分批进入 Running。

### 5.2 `c4` 说明 queue 的主来源在前半段

Stage 7 `c4` 的 scheduler 日志有一个非常关键的顺序：

1. 先长时间停留在 `Running=2 / Waiting=2`
2. 再进入 `Running=3 / Waiting=1`
3. 最后才达到 `Running=4 / Waiting=0`
4. generation throughput 直到最后阶段才升到 `99.8 tok/s`

这说明当前排队主因不是 decode 后半段，而是：

- 长 prefill 把请求分批推进入 Running
- Running 数上来之前，Waiting 队列会持续存在
- 真正高 generation throughput 的阶段出现在更后面

因此当前对用户等待时间影响最大的不是 decode 收尾，而是：

> prefill 主导的首段 wall time + 分批进入 Running 的调度过程。

### 5.3 graph 在用，但不是主解释

Stage 7 `c2/c4` 都有明确 graph 证据：

- `CUPTI_ACTIVITY_KIND_GRAPH_TRACE`
- `cudaGraphLaunch`

但它们在 CUDA API time 中都只占约 `0.1%`。

所以当前更合理的判断是：

1. graph 已经启用
2. graph 不是完全无效
3. 但当前主要等待并不是“graph launch 本身太慢”
4. 主要代价仍更像 kernel launch / runtime dispatch + event/sync + 阶段切换

## 6. 为什么主 kernel 看起来集中在单 stream

这里需要区分“证据”与“推断”。

### 6.1 已确认的证据

1. Stage 7 的 `16K` `ncu` 代表点里，`Marlin` 和 `FlashAttention` 都落在同一条 stream。
2. Stage 7 `c2/c4` server-side `nsys` 中，主 kernel family 没有因为并发增加而切换成另一类并行热点，仍是 `Marlin + FlashAttention`。
3. `cudaGraphLaunch` 存在，说明当前执行路径已经部分 graph 化。

### 6.2 当前推断

基于这些证据，当前更像是：

> vLLM 在这条 AWQ `64K` 路径上，本来就是以单请求主算子串行为主，再叠加 scheduler 让多个请求分批进入 Running；并没有出现“靠多 stream 大规模摊平长 prefill”的执行形态。

这条判断目前是推断，不是完全由单条新 trace 直接证明的事实。  
Stage 8 clean `LaunchStats` 补齐后，这条判断可以进一步收口：

- 不要把当前问题简化成“多开几条 stream 就会好”
- `Marlin` 与 `FlashAttention` 的主热点 section 已能采到，下一步不是继续证明“能不能采”，而是判断是否需要 `Occupancy / MemoryWorkloadAnalysis` 来支撑 kernel-level 优化动作

## 7. 本阶段的工程决策

### 7.1 现在不建议先做什么

1. 不建议先盲调 `max_num_seqs`
2. 不建议先盲调 graph 开关
3. 不建议只凭 `LaunchStats` 就下结论说“问题主要在 kernel”或“问题主要在 scheduler”

原因：

- `V3` 已证明 queue 和 launch/sync gap 是同时存在的
- `V2` 已证明主热点 section 可采，但只凭 `LaunchStats` 还不足以最终判断 occupancy、寄存器/共享内存，还是 memory behavior

### 7.2 现在应该先做什么

1. 用 Stage 8 clean `LaunchStats` 更新优化解释：
   - `Marlin`: `Registers Per Thread=255`、`Dynamic Shared Memory Per Block=166.91 Kbyte/block`、`Waves Per SM=1`
   - `FlashAttention`: `Registers Per Thread=255`、`Dynamic Shared Memory Per Block=49.15 Kbyte/block`、`Waves Per SM=37.93`
   - 如果要继续下 kernel-level 结论，再补 `Occupancy / MemoryWorkloadAnalysis`
2. `V4` 暂时先按当前优先级准备：
   - 默认上线候选仍是 `AWQ-INT4`
   - `NVFP4` 继续作为观察项
   - `AWQ + FP8 KV` 继续作为实验配置

## 8. 已确认

1. `c4` 的 Waiting 队列是真实存在的，不是日志噪声。
2. queue 的主来源更像长 prefill 分批进入 Running，而不是 decode 尾部突发拥塞。
3. 即使在 `c2` 没有 Waiting 队列时，launch/sync gap 也已经明显存在。
4. graph 在用，但不是当前主要等待来源。
5. 当前 `V3` 的最合理下一步不是继续盲采更多 `nsys`，也不是继续证明 `ncu` 可采，而是把 clean `LaunchStats` 回流到 Stage 12 的优化动作判断。

## 9. 仍不确定

1. `64K` 主代表点的 `Marlin / FlashAttention` 更像 occupancy 限制，还是 memory behavior 限制；这需要更深 section 才能最终判断。
2. 单 stream 现象里，有多少是框架执行模型决定的，有多少仍能通过上层调度参数改善。
3. 是否需要真的引入 NVTX 阶段标签，来把 prefill / decode / scheduler gap 进一步对齐到时间线。

## 10. 下一步

- 下一次只改什么变量：
  解释链路，而不是 capture path。
- 预期要验证什么：
  是否需要补 `Occupancy / MemoryWorkloadAnalysis` 才能指导下一轮优化动作。
- 当前阶段不再优先做什么：
  不再继续盲采更多 `nsys` trace
