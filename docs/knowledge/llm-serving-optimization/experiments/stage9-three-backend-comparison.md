# 第九阶段实验报告：三后端统一对比与优化落地

> 文档定位：项目知识库中的 LLM serving 优化实验报告，不属于 `llmnode` 项目蓝图、契约或正式路线图。
> 实验目标：把 benchmark / profiler 方法从 vLLM 扩展到 SGLang 和 llama.cpp，形成三后端统一对比结论，并产出可执行的优化动作链。
> 创建时间：2026-06-10。
> 当前结论状态：待执行。

相关专题：

- benchmark 方法见 [benchmark-methodology.md](../performance/benchmark-methodology.md)
- vLLM 机制见 [vllm-deep-dive.md](../serving/vllm-deep-dive.md)
- 量化机制见 [quantization-deep-dive.md](../optimization/quantization-deep-dive.md)
- Stage 1-7 基线与 profiler 结论见各阶段报告

## 实验目标

- 本阶段要回答的问题：
  1. SGLang 在同模型（Qwen3.6-35B-A3B-FP8）上的 TTFT / TPOT / completion tok/s 和 vLLM 差异多大？
  2. llama.cpp GGUF 在轻量部署场景（4K/16K + 256）下的基线表现如何？
  3. 三个后端的 KV cache 管理、并发扩展和 scheduler 行为有什么本质差异？
  4. 基于以上对比，最优的部署配置和下一步优化方向是什么？

## 统一矩阵

| backend | profile | model | shape |
|---|---|---|---|
| vLLM | `vllm_qwen36-35b-a3b-fp8` | Qwen3.6-35B-A3B-FP8 | `16K + 512`, `64K + 512` |
| SGLang | `sglang_qwen36-35b-a3b-fp8` | Qwen3.6-35B-A3B-FP8 | `16K + 512`, `64K + 512` |
| llama.cpp | `llama.cpp_qwen36-35b-a3b-q4km` | Qwen3.6-35B-A3B-GGUF Q4_K_M | `4K + 256`, `16K + 256` |

## 固定条件

- GPU: NVIDIA A800 80GB PCIe
- concurrency: 1 -> 2 -> 4
- warmup / measure: 1 / 3
- sample interval: 1.0s

## 统一指标

- TTFT
- TPOT / ITL
- completion tok/s
- E2E latency
- success rate
- KV cache size / usage
- GPU memory utilization

## 结果

### vLLM 基线（35B-A3B-FP8）

| case | metric | value | notes |
|---|---|---|---|

### SGLang（35B-A3B-FP8）

| case | metric | value | notes |
|---|---|---|---|

### llama.cpp（35B-A3B Q4_K_M GGUF）

| case | metric | value | notes |
|---|---|---|---|

### 三后端对比总结

| 维度 | vLLM | SGLang | llama.cpp |
|---|---|---|---|
| 部署复杂度 | | | |
| 短上下文吞吐 | | | |
| 长上下文效率 | | | |
| 并发扩展 | | | |
| KV cache 管理 | | | |
| 资源占用 | | | |

## 已确认

- 

## 仍不确定

- 

## 优化动作链

基于全部 9 个阶段的实验结论，给出可执行的优化决策：

| 决策维度 | 结论 | 依据 |
|---|---|---|
| 量化选择 | | |
| 后端选择 | | |
| 参数调优 | | |
| 调度策略 | | |
| kernel 路径 | | |

## 下一步

- 下一次只改什么变量：
- 预期要验证什么：
