# Experiments

这里保留 `llm-serving-optimization` 的完整实验记录，供回溯查证和深入阅读。

## 说明

- 上级目录 `0/` 放的是汇报型摘要文件（01-06），便于快速了解结论。
- 本目录保留完整的实验过程、数据和分析。
- 需要快速了解结论时，先读 `0/` 目录的汇报文件。

## 实验索引

| 编号 | 文件 | 主题 | 核心变量 |
|---:|---|---|---|
| 1-2 | [stage1-2-qwen27b.md](./stage1-2-qwen27b.md) | 量化基线 | BF16 / FP8 / NVFP4 / AWQ-INT4 |
| 3 | [stage3-awq-concurrency.md](./stage3-awq-concurrency.md) | AWQ 并发阶梯 | concurrency=1 / 2 / 4 |
| 4 | [stage4-awq-profiler.md](./stage4-awq-profiler.md) | AWQ profiler 热点 | 64K+512, c1 / c4 |
| 5 | [stage5-nvfp4-profiler.md](./stage5-nvfp4-profiler.md) | NVFP4 profiler 对照 | 同一 64K+512 工作负载 |
| 6a | [stage6a-fp8-kv-benchmark.md](./stage6a-fp8-kv-benchmark.md) | FP8 KV 容量、速度与质量回归 | AWQ baseline / AWQ+FP8 KV |
| 6b | [stage6b-nsight-toolchain.md](./stage6b-nsight-toolchain.md) | Nsight 工具链 bring-up | nsys timeline / ncu 64K 同形状 |
| 7 | [stage7-vllm-environment-and-config-decision.md](./stage7-vllm-environment-and-config-decision.md) | 环境核验与配置决策 | 宿主环境 / 默认 profile |
| 8 | [stage8-launch-gap-and-queue-analysis.md](./stage8-launch-gap-and-queue-analysis.md) | launch gap / queue 归因 | c2 / c4 scheduler 行为 |
| 9 | [stage9-optimization-actions-and-deployment-boundaries.md](./stage9-optimization-actions-and-deployment-boundaries.md) | 优化动作链与上线边界 | 调度层 / kernel 层决策 |

## 阅读顺序

建议按下面顺序读：

1. [stage1-2-qwen27b.md](./stage1-2-qwen27b.md) — 量化基线，建立 AWQ vs NVFP4 的基本判断
2. [stage3-awq-concurrency.md](./stage3-awq-concurrency.md) — AWQ 并发扩展行为
3. [stage4-awq-profiler.md](./stage4-awq-profiler.md) — AWQ 热点分析（torch profiler）
4. [stage5-nvfp4-profiler.md](./stage5-nvfp4-profiler.md) — NVFP4 对照
5. [stage6a-fp8-kv-benchmark.md](./stage6a-fp8-kv-benchmark.md) — FP8 KV 容量、速度与质量回归
6. [stage6b-nsight-toolchain.md](./stage6b-nsight-toolchain.md) — Nsight 工具链与 64K ncu
7. [stage7-vllm-environment-and-config-decision.md](./stage7-vllm-environment-and-config-decision.md) — 环境与配置收口
8. [stage8-launch-gap-and-queue-analysis.md](./stage8-launch-gap-and-queue-analysis.md) — 调度层瓶颈归因
9. [stage9-optimization-actions-and-deployment-boundaries.md](./stage9-optimization-actions-and-deployment-boundaries.md) — 最终优化决策

## 其他文件

| 文件 | 说明 |
|---|---|
| [experiment-master-plan.md](./experiment-master-plan.md) | 总实验方案，所有退出标准已于 2026-06-11 完成 |

## 目录原则

- 同一组变量、同一条判断链，尽量放在同一份文件里。
- 稳定结论和数据对比放在文件主体，踩坑过程和失败尝试放在后部"踩坑记录"。
- 编号连续（1-2 → 3 → 4 → 5 → 6a → 6b → 7 → 8 → 9），无跳号。
