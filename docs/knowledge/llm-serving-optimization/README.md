# LLM 部署优化学习库

> 文档定位：这是 `docs/knowledge/` 下的 LLM serving 优化专题，属于项目知识库参考层，不属于 `llmnode` 项目蓝图、契约或正式路线图。  
> 目标：围绕当前 `llmnode` 的 vLLM / SGLang / llama.cpp 三后端，把大模型部署、性能实验、量化、KV cache、profiler 和 kernel 优化串成一套可复用知识库。  
> 使用原则：概念必须落到本机实验；所有框架支持状态以官方文档、当前镜像版本和本机实测为准。

## 阅读顺序

建议按下面顺序读：

| 顺序 | 文件 | 用途 |
|---:|---|---|
| 1 | [learning-log.md](./learning-log.md) | 总体学习路线和阶段目标 |
| 2 | [experiment-master-plan.md](./experiments/experiment-master-plan.md) | 覆盖本专题全部目标的总实验方案 |
| 3 | [hardware.md](./foundations/hardware.md) | A800 / Ampere / Hopper / Blackwell 与精度支持 |
| 4 | [model-format.md](./foundations/model-format.md) | 模型文件格式、量化格式、vLLM/SGLang/llama.cpp 差异 |
| 5 | [accel-map.md](./foundations/accel-map.md) | 推理加速方法全景图 |
| 6 | [compute-primitives.md](./foundations/compute-primitives.md) | GEMM 与 FlashAttention 工作原理、量化加速原因 |
| 7 | [benchmark-methodology.md](./performance/benchmark-methodology.md) | 怎么测性能，怎么避免口径错误 |
| 8 | [kv-cache.md](./performance/kv-cache.md) | KV cache、长上下文容量和并发边界 |
| 9 | [vllm-deep-dive.md](./serving/vllm-deep-dive.md) | vLLM 调度、PagedAttention、参数和实验方向 |
| 10 | [quantization-deep-dive.md](./optimization/quantization-deep-dive.md) | BF16/FP8/AWQ/GPTQ/NVFP4/KV 量化 |
| 11 | [profiling-guide.md](./performance/profiling-guide.md) | Profiling 完整指南：方法论 + 实操 + 图形界面 |
| 12 | [stage1-2-qwen27b.md](./experiments/stage1-2-qwen27b.md) | Qwen3.6-27B 量化基线（含 prefill / decode 拆分） |
| 13 | [stage3-awq-concurrency.md](./experiments/stage3-awq-concurrency.md) | AWQ-INT4 并发阶梯实验报告 |
| 14 | [stage4-awq-profiler.md](./experiments/stage4-awq-profiler.md) | AWQ-INT4 profiler 代表点 |
| 15 | [stage5-nvfp4-profiler.md](./experiments/stage5-nvfp4-profiler.md) | NVFP4 profiler 代表点 |
| 16 | [stage6a-fp8-kv-benchmark.md](./experiments/stage6a-fp8-kv-benchmark.md) | FP8 KV 容量、速度与质量回归 |
| 17 | [stage6b-nsight-toolchain.md](./experiments/stage6b-nsight-toolchain.md) | Nsight 工具链 bring-up 与 64K ncu |
| 18 | [stage7-vllm-environment-and-config-decision.md](./experiments/stage7-vllm-environment-and-config-decision.md) | 环境核验与配置决策收口 |
| 19 | [stage8-launch-gap-and-queue-analysis.md](./experiments/stage8-launch-gap-and-queue-analysis.md) | launch gap / queue 归因 |
| 20 | [stage9-optimization-actions-and-deployment-boundaries.md](./experiments/stage9-optimization-actions-and-deployment-boundaries.md) | 优化动作链与上线边界 |

## 目录职责

| 目录 | 职责 | 不做什么 |
|---|---|---|
| `foundations/` | 基础概念、硬件、模型格式、加速地图 | 不展开具体 benchmark 和实验结论 |
| `serving/` | vLLM / SGLang / llama.cpp 等服务框架机制 | 不重复解释硬件精度和通用量化细节 |
| `performance/` | benchmark、KV cache、profiler、瓶颈定位方法 | 不写某一次实验的完整报告 |
| `optimization/` | 量化、speculative、MTP、并行等优化专题 | 不承担实验流水账 |
| `experiments/` | 阶段实验报告和实测结论 | 不重复大段基础概念，改为引用专题文档 |
| `experiments/experiment-master-plan.md` | 把整个专题的实验目标、阶段顺序、成功标准和产物路径统一收口 | 不替代具体实验报告和专题方法文档 |

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

## 文档维护规则

- 学习路线写进 `learning-log.md`。
- 通用概念写进对应专题目录。
- 具体实验写成 `experiments/01-06-*.md`。
- 已验证的项目长期结论再考虑回流到 `docs/blueprint/`、`docs/contracts/` 或 `docs/process/`。
- 不把推断写成已验证结论；没跑过就明确写“待实测”。
