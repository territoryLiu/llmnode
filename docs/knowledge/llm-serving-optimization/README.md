# LLM 部署优化学习库

> 文档定位：这是 `docs/knowledge/` 下的 LLM serving 优化专题，属于项目知识库参考层，不属于 `llmnode` 项目蓝图、契约或正式路线图。  
> 目标：围绕当前 `llmnode` 的 vLLM / SGLang / llama.cpp 三后端，把大模型部署、性能实验、量化、KV cache、profiler 和 kernel 优化串成一套可复用知识库。  
> 使用原则：概念必须落到本机实验；所有框架支持状态以官方文档、当前镜像版本和本机实测为准。

## 阅读顺序

建议按下面顺序读：

| 顺序 | 文件 | 用途 |
|---:|---|---|
| 1 | [learning-log.md](./learning-log.md) | 总体学习路线和阶段目标 |
| 2 | [experiment-master-plan.md](./experiments/experiment-master-plan.md)（已归档） | 覆盖本专题全部目标的总实验方案 |
| 3 | [hardware.md](./foundations/hardware.md) | A800 / Ampere / Hopper / Blackwell 与精度支持 |
| 4 | [model-format.md](./foundations/model-format.md) | 模型文件格式、量化格式、vLLM/SGLang/llama.cpp 差异 |
| 5 | [accel-map.md](./foundations/accel-map.md) | 推理加速方法全景图 |
| 6 | [benchmark-methodology.md](./performance/benchmark-methodology.md) | 怎么测性能，怎么避免口径错误 |
| 7 | [kv-cache.md](./performance/kv-cache.md) | KV cache、长上下文容量和并发边界 |
| 8 | [vllm-deep-dive.md](./serving/vllm-deep-dive.md) | vLLM 调度、PagedAttention、参数和实验方向 |
| 9 | [quantization-deep-dive.md](./optimization/quantization-deep-dive.md) | BF16/FP8/AWQ/GPTQ/NVFP4/KV 量化 |
| 10 | [profiler-and-kernels.md](./performance/profiler-and-kernels.md) | 从 benchmark 走向 Nsight / torch profiler / kernel |
| 11 | [stage1-qwen27b.md](./experiments/stage1-qwen27b.md) | 第一阶段 Qwen3.6-27B 量化基线实验报告 |
| 12 | [stage2-vllm-prefill-decode.md](./experiments/stage2-vllm-prefill-decode.md) | 第二阶段 vLLM prefill / decode 与参数调优最小实测 |
| 13 | [stage3-awq-concurrency.md](./experiments/stage3-awq-concurrency.md) | 第三阶段 AWQ-INT4 并发阶梯实验报告 |
| 14 | [stage4-awq-profiler.md](./experiments/stage4-awq-profiler.md) | 第四阶段 AWQ-INT4 profiler 代表点 |
| 15 | [stage5-nvfp4-nointerference.md](./experiments/stage5-nvfp4-nointerference.md) | 第五阶段 NVFP4 无干扰复测与 FP8 KV cache 对照 |
| 16 | [stage6-nvfp4-profiler.md](./experiments/stage6-nvfp4-profiler.md) | 第六阶段 NVFP4 profiler 代表点 |
| 17 | [stage7-fp8-kv-quality-and-nsight.md](./experiments/stage7-fp8-kv-quality-and-nsight.md) | 第七阶段 FP8 KV 质量回归与 Nsight bring-up |

## 目录职责

| 目录 | 职责 | 不做什么 |
|---|---|---|
| `foundations/` | 基础概念、硬件、模型格式、加速地图 | 不展开具体 benchmark 和实验结论 |
| `serving/` | vLLM / SGLang / llama.cpp 等服务框架机制 | 不重复解释硬件精度和通用量化细节 |
| `performance/` | benchmark、KV cache、profiler、瓶颈定位方法 | 不写某一次实验的完整报告 |
| `optimization/` | 量化、speculative、MTP、并行等优化专题 | 不承担实验流水账 |
| `experiments/` | 阶段实验报告和实测结论 | 不重复大段基础概念，改为引用专题文档 |
| `experiments/experiment-master-plan.md`（已归档） | 把整个专题的实验目标、阶段顺序、成功标准和产物路径统一收口 | 不替代具体实验报告和专题方法文档 |

归口规则：

- 硬件和精度支持：写到 [foundations/hardware.md](./foundations/hardware.md)。
- 模型文件格式和三后端支持关系：写到 [foundations/model-format.md](./foundations/model-format.md)。
- 加速方法全景图：写到 [foundations/accel-map.md](./foundations/accel-map.md)，只做地图和索引。
- benchmark 指标口径：写到 [performance/benchmark-methodology.md](./performance/benchmark-methodology.md)。
- KV cache 和长上下文容量：写到 [performance/kv-cache.md](./performance/kv-cache.md)。
- vLLM 机制和参数：写到 [serving/vllm-deep-dive.md](./serving/vllm-deep-dive.md)。
- 量化方法细节：写到 [optimization/quantization-deep-dive.md](./optimization/quantization-deep-dive.md)。
- 阶段性实测：写到 [experiments/](./experiments/)。

## 当前学习主线

当前最重要的问题不是“再认识更多名词”，而是打通下面这条链：

```text
选择模型和格式
-> 启动后端
-> 做可复现 benchmark
-> 拆 prefill / decode / TTFT / TPOT
-> 解释 KV cache 和显存边界
-> 判断量化是否真的有收益
-> 用 profiler 证明瓶颈
-> 再决定调参数、换框架或看 kernel
```

## 当前实验优先级

`Qwen3.6-27B` 第二阶段最小闭环已经补完：`AWQ-INT4 / NVFP4 + output=512` 重复测量、`NVFP4 gpu_memory_utilization=0.6` 对比、`AWQ-INT4 64K + output=512` TTFT / TPOT 代表点。

第三阶段 `AWQ-INT4` 并发阶梯已经完成：`concurrency=1/2/4` 均在无外部 GPU 负载环境下跑通，`16K/64K + output=512` 没有 OOM、timeout 或 HTTP error。

Stage 3 已补系统总 output tok/s 近似口径：`16K c1 -> c4` 约 `32.85 -> 53.33 tok/s`，`64K c1 -> c4` 约 `10.85 -> 13.79 tok/s`。这说明 `64K` 并发扩展很弱。

Stage 4 已完成 `AWQ-INT4 64K + output=512` 的 `concurrency=1` 与 `concurrency=4` torch profiler 代表点。证据显示：

1. `prefill`：AWQ Marlin GEMM 是最大热点，FlashAttention 是第二热点。
2. `decode`：AWQ Marlin GEMM 仍是最大热点，attention / FP16 GEMM / sampling 也有可见占比。
3. `concurrency=4` 日志有明确 `Running/Waiting` 排队过程，KV cache usage 峰值约 `74.7%`。
4. c1/c4 trace 都没有超过 `1.0%` 阈值的明确 GPU idle / overlap 机会。

Stage 5 已完成 `NVFP4 gpu_memory_utilization=0.55/0.6` 的无外部 GPU 进程复测：`64K + output=512` 平均延迟分别为 `39,020.31 ms / 38,120.15 ms`，端到端输出吞吐分别为 `12.71 / 11.81 tok/s`。这说明 Stage 2 的 NVFP4 速度结果确实被外部负载明显污染。`0.6` 的主要收益仍是容量，KV tokens 从 `70,560` 提升到 `87,024`，本轮没有证明它比 `0.55` 更快。

Stage 5 也完成了 `AWQ-INT4 + FP8 KV cache` 的容量和速度对照：KV tokens 从普通 AWQ 的 `90,944` 提到 `178,752`，256K max concurrency 从 `1.38x` 提到 `2.68x`；但 `64K + output=512` 单并发平均吞吐为 `9.52 tok/s`，低于普通 AWQ Stage 2 的 `10.88 tok/s`。因此它当前更像容量方案，不是单请求加速方案。

Stage 6 已完成 `NVFP4 64K + output=512` 的 torch profiler 代表点。证据显示：`prefill` 仍由 Marlin GEMM `61.6%` 和 FlashAttention `23.6%` 主导；`decode` 中 Marlin GEMM `41.3%`、普通 BF16 GEMM `23.9%`、FlashAttention `12.6%`。这说明 NVFP4 和 AWQ 共享 Marlin + attention 主热点，但 NVFP4 decode 的普通 BF16 GEMM 占比更明显。

Stage 7 已完成 `FP8 KV cache` 最小质量回归，并开始 Nsight bring-up。普通 AWQ baseline 在 5 个质量用例中通过长上下文、代码、数学 3 项，但严格 JSON 和工具 JSON 因 reasoning 混入失败；FP8 KV 对照只通过长上下文 1 项，相比 baseline 新增 `code_generation` 和 `math_reasoning` 两项退化。因此 `AWQ-INT4 + FP8 KV cache` 当前仍只能视为容量实验配置，不能作为可上线配置。`nsys` 已在 Nsight Compute 2026.1.1 包内找到，并已完成真实 vLLM server 短请求 timeline capture，能生成 `.nsys-rep/.sqlite`，`nsys stats` 可读 CUDA API、GPU kernel、memops 和 CUDA graph 信息；短请求报告中 FlashAttention 与 Marlin 仍是主要 kernel 家族。随后又完成一次 `AWQ-INT4 64K + output=512` offline 请求窗口 capture，使用 `cudaProfilerStart/Stop` 收窄采集范围；请求窗口内 Marlin 占 GPU kernel time `68.1%`，FlashAttention splitkv 占 `23.4%`，CUDA graph trace `368` 行，`cudaGraphLaunch` `369` 次。之后补了一次 server-side `64K + output=512, concurrency=2` capture：两个请求均 `200 OK`，wall time `79.22 s`，vLLM 日志显示 `Running=2 / Waiting=0`，KV usage 峰值约 `37.3%`；Nsight 中 Marlin 占 `68.3%`，FlashAttention splitkv 占 `23.5%`。进一步又补了 server-side `concurrency=4` capture：4 个请求全部 `200 OK`，wall time `136.84 s`，vLLM 日志明确出现 `Running=2 / Waiting=2 -> Running=3 / Waiting=1 -> Running=4 / Waiting=0`，KV usage 峰值约 `74.7%`；Nsight 中 Marlin 占 `68.5%`，FlashAttention splitkv 占 `24.0%`。基于 c4 `.sqlite` 继续拆时间线后，可以再定量补充：kernel span 已覆盖请求 wall time 的 `98.2%`，但 kernel 内部累计 gap 仍约 `20.43 s`，占 kernel span `15.2%`；主要 kernel 全落在同一个 CUDA stream 上，没有看到多流 kernel overlap 证据。这说明当前瓶颈更像大量细碎 launch/sync gap 叠加在单流主热点之上。`/opt/anaconda3/bin/ncu` wrapper 不可用，但 Nsight Compute 2026.1.1 真实二进制可挂载进 vLLM 容器启动。2026-06-10 已确认 `RmProfilingAdminOnly: 0`，旧的 GPU counter 权限阻塞已消失；新的真实难点变成 `ncu` 对 vLLM 冷启动 / warmup 的额外显存与 replay 开销。当前 `64K + output=512` 同形状 workload 在 `ncu` 包裹下会因为 KV cache 预算被挤压而初始化失败；不过更小的 `16K + output=512` 真实 workload 已能在 `ncu` 下完整跑通，而且已经成功拿到真实 `Marlin` kernel` 与 `flash_fwd_kernel` 的 `LaunchStats / Occupancy / MemoryWorkloadAnalysis`。其中 Marlin 代表点显示：`achieved occupancy=12.5%`、`registers/thread=255`、`dynamic shared memory/block=166.91 KiB`、`memory throughput≈447.53-490.95 GB/s`、`L2 hit rate≈62.5%`；FlashAttention 代表点显示：`achieved occupancy≈12.43%`、`dynamic shared memory/block=49.15 KiB`、`memory throughput≈19.09-19.29 GB/s`、`L2 hit rate≈98.6%`。因此 Nsight Compute 已经不是“没开展”，而是进入“真实 Marlin/FlashAttention 低层指标已拿到，64K 同形状点仍待补齐”的阶段。

下一阶段建议继续围绕 `Qwen3.6-27B` 做：

1. `FP8 KV cache 质量追因`：如继续研究，优先区分 FP8 KV 精度退化、reasoning 输出混入、`max_tokens=512` 截断三类因素。
2. `Nsight Systems`：server-side `concurrency=4` 和 Waiting 队列已补；下一步应继续深入现有 `.nsys-rep/.sqlite`，把 launch gap 细分到阶段切换和同步点，或引入 NVTX 标注 prefill/decode。
3. `Nsight Compute`：不再先纠结权限，转而优先收敛 capture 方法。当前真实 workload 下的 `Marlin` 和 `FlashAttention` section 都已拿到，下一步尝试 attach 或把当前 kernel-filter capture 方法迁移到 `64K + output=512` 同形状代表点。

## 文档维护规则

- 学习路线写进 `learning-log.md`。
- 通用概念写进对应专题目录。
- 具体实验写成 `experiments/stageN-*.md`。
- 已验证的项目长期结论再考虑回流到 `docs/blueprint/`、`docs/contracts/` 或 `docs/process/`。
- 不把推断写成已验证结论；没跑过就明确写“待实测”。
