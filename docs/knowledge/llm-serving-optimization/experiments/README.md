# Experiments

实验报告目录，只记录“本次实验怎么测、测到了什么、结论和不确定性是什么”。

| 文件 | 职责 |
|---|---|
| [stage1-qwen27b.md](./stage1-qwen27b.md) | Qwen3.6-27B 量化推理基线 |
| [stage2-vllm-prefill-decode.md](./stage2-vllm-prefill-decode.md) | vLLM prefill / decode 拆分与参数调优最小实测 |
| [stage3-awq-concurrency.md](./stage3-awq-concurrency.md) | AWQ-INT4 并发阶梯实验 |
| [stage4-awq-profiler.md](./stage4-awq-profiler.md) | AWQ-INT4 64K profiler 代表点 |
| [stage5-nvfp4-nointerference.md](./stage5-nvfp4-nointerference.md) | NVFP4 无干扰复测与 FP8 KV cache 准备 |
| [stage6-nvfp4-profiler.md](./stage6-nvfp4-profiler.md) | NVFP4 64K profiler 代表点 |
| [stage7-fp8-kv-quality-and-nsight.md](./stage7-fp8-kv-quality-and-nsight.md) | FP8 KV 质量回归与 Nsight bring-up |
| [stage8-ncu-64k-same-shape.md](./stage8-ncu-64k-same-shape.md) | Nsight Compute 64K 同形状与 NVFP4 kernel 归因 |
| [stage9-three-backend-comparison.md](./stage9-three-backend-comparison.md) | 三后端统一对比与优化落地 |
| [stage10-vllm-environment-and-config-decision.md](./stage10-vllm-environment-and-config-decision.md) | vLLM 主线环境核验与主配置决策收口 |
| [stage11-launch-gap-and-queue-analysis.md](./stage11-launch-gap-and-queue-analysis.md) | launch gap 与 queue 深化归因 |
| [stage12-vllm-optimization-actions-and-deployment-boundaries.md](./stage12-vllm-optimization-actions-and-deployment-boundaries.md) | 优化动作链与上线边界收口 |

实验报告应引用专题文档，不重复大段基础概念：

- benchmark 口径见 `../performance/benchmark-methodology.md`
- KV cache 解释见 `../performance/kv-cache.md`
- vLLM 参数见 `../serving/vllm-deep-dive.md`
- 量化机制见 `../optimization/quantization-deep-dive.md`
