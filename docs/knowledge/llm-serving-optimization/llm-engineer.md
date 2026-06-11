# 资深大模型部署优化工程师技能图谱

> 文档定位：`docs/knowledge/llm-serving-optimization/` 下的技能框架参考，不属于 `llmnode` 项目蓝图、契约或正式路线图。  
> 目标：梳理从"能分析"到"能动手改"再到"能做架构决策"的完整能力阶梯。  
> 更新时间：2026-06-11。

## 1. 能力分级总览

```text
Level 1: Profiler 级 — 能发现瓶颈在哪
Level 2: Kernel 级 — 能自己写/改代码解决瓶颈
Level 3: 架构级 — 能设计整个 serving 方案并做技术选型
```

---

## 2. Level 1：Profiler 级（已基本掌握）

### 2.1 Benchmark 方法论

- 控变量实验设计（每次只改一个变量）
- 核心指标体系：TTFT、TPOT/ITL、E2E latency、completion tok/s、QPS、P50/P90/P99
- 长上下文 vs 短上下文的 benchmark 口径差异
- 并发阶梯测试方法
- 结果复现与环境隔离（GPU 干净窗口验证）

### 2.2 量化选型与权衡

- 精度格式：BF16 / FP16 / FP8 / INT8 / INT4 / FP4
- 量化方法：AWQ / GPTQ / SmoothQuant / FP8 KV cache
- 硬件与精度的匹配关系：Ampere 不原生支持 FP8，Hopper 是 FP8 主场，Blackwell 是 FP4/FP8 主场
- 量化的价值优先级：显存容量 > 上下文容量 > 并发能力 > 速度（取决于硬件和场景）
- 质量回归方法：长上下文一致性、代码生成、数学推理、结构化输出

### 2.3 KV Cache 内存模型

- KV cache 的作用与计算：`2 × num_layers × num_kv_heads × head_dim × seq_len × bytes_per_elem`
- GQA / MQA 对 KV cache 成本的影响
- PagedAttention 的内存管理机制
- KV cache 容量 vs 速度的权衡
- 从 vLLM 启动日志读取 KV cache 状态

### 2.4 推理框架机制（vLLM）

- 请求生命周期：HTTP → tokenizer → scheduler → prefill → decode → sampling → response
- 核心机制：PagedAttention、continuous batching、prefix caching、chunked prefill、CUDA Graph
- 关键参数：`max_model_len`、`gpu_memory_utilization`、`max_num_seqs`、`max_num_batched_tokens`

### 2.5 Profiler 工具链

- **torch profiler**：PyTorch operator → CUDA kernel 映射，快速定位热点算子
- **Nsight Systems (nsys)**：timeline 视图、CPU/GPU 重叠、CUDA API 占比、kernel 家族分布
- **Nsight Compute (ncu)**：单 kernel 级 detail——occupancy、register、shared memory、memory throughput、L2 hit rate
- 三层工具的使用顺序：torch profiler → nsys → ncu（从粗到细）

### 2.6 瓶颈归因能力

- 瓶颈分类：compute-bound / HBM bandwidth-bound / scheduling gap / KV cache pressure / dequantization overhead / communication bottleneck
- Launch gap 归因：prefill 批次切换、decode 调度切换、CUDA event/sync、kernel launch/runtime dispatch
- 从 profiler 数据推导优化方向的能力

---

## 3. Level 2：Kernel 级（待补）

### 3.1 CUDA 编程基础

- 编程模型：grid / block / warp / thread 层次
- 内存层次：register → shared memory → L2 cache → HBM，各级带宽和延迟
- Shared memory：bank conflict、padding、同步原语
- Warp 级原语：`__shfl_sync`、warp reduce、coalesced memory access
- Occupancy 计算：register / shared memory / block size 如何决定每 SM 活跃 warp 数
- 实战能力：能手写一个简单的 GEMM 或 softmax kernel

### 3.2 Triton 编程

- Triton 的 block-level 编程模型（vs CUDA 的 thread-level）
- 核心原语：`tl.load`、`tl.store`、`tl.dot`、`tl.where`、`tl.reduce`
- 能读懂 FlashAttention 的 Triton 源码
- 能写简单的 Triton kernel：elementwise、reduce、matmul
- 理解 Triton 的自动 tiling 和内存访问优化

### 3.3 常见 LLM Kernel 理解

- GEMM kernel：cuBLAS / Marlin / CUTLASS 的设计思路
- Attention kernel：FlashAttention v1/v2/v3 的 tiling 策略与 IO 复杂度
- Normalization kernel：RMSNorm / LayerNorm
- RoPE / positional encoding kernel
- Sampling kernel：top-k / top-p / temperature

---

## 4. Level 3：架构级（待补）

### 4.1 多 GPU 并行与通信

- Tensor Parallelism (TP)：weight 切分方式、通信量分析、AllReduce / AllGather
- Pipeline Parallelism (PP)：bubble 率、microbatch 调度
- Sequence Parallelism (SP)：Ring Attention 用于超长上下文
- NCCL 集合通信：带宽和延迟特性
- 多卡 profiling：ncu / nsys 在多卡场景下的用法

### 4.2 多推理框架对比

| 框架 | 核心特点 | 适用场景 |
|---|---|---|
| vLLM | PagedAttention、continuous batching、生态最成熟 | 通用在线推理 |
| SGLang | RadixAttention、constrained decoding、前缀缓存更强 | 多轮对话、结构化输出 |
| TensorRT-LLM | NVIDIA 官方、图优化、FP8 kernel 原生 | Hopper/Blackwell 高吞吐 |
| llama.cpp | CPU/混合推理、GGUF 生态 | 本地部署、边缘设备 |

### 4.3 Speculative Decoding

- 原理：小模型 draft → 大模型 verify，用计算换延迟
- 变体：Medusa（多头并行 draft）、EAGLE（feature-level draft）
- 关键指标：acceptance rate、speedup 上限
- 与 KV cache 的交互：verify 阶段的 KV 分配策略

### 4.4 Attention 机制演进

- MQA → GQA → MLA（Multi-Latent Attention）
- FlashAttention v1 → v2 → v3 的演进逻辑
- PagedAttention vs RadixAttention vs chunked attention
- Ring Attention / Sequence Parallelism 用于超长上下文

### 4.5 MoE 模型 Serving

- Expert routing 策略与 load balancing
- MoE 的显存特点：只有部分 expert 被激活
- Expert Parallelism (EP) vs Tensor Parallelism (TP)
- 通信模式：All-to-All 通信

### 4.6 生产级系统能力

- 负载均衡与 autoscaling：基于 QPS / latency 的扩缩容策略
- 多实例调度：GPU 粒度的 bin packing
- A/B 测试与灰度发布：模型版本切换
- 成本优化：spot instance、混合精度策略、批处理合并
- 可观测性：metrics → Prometheus/Grafana、tracing、告警

### 4.7 编译优化

- `torch.compile` 的工作原理和适用场景
- CUDA Graph 的作用：减少 kernel launch overhead
- XLA / TensorRT 图优化
- Triton 的编译流程与自动调优

---

## 5. 建议学习路径

```text
当前位置（Level 1 完成）
    │
    ▼
CUDA 基础 ──→ Triton 基础 ──→ 能写/改 kernel
    │
    ▼
多 GPU 并行（TP/PP/NCCL）──→ 能部署 70B+ 模型
    │
    ▼
SGLang / TensorRT-LLM 对比 ──→ 能做框架选型
    │
    ▼
Speculative Decoding + MoE ──→ 能优化主流架构
    │
    ▼
生产系统能力 ──→ 能独立设计 serving 架构
```

核心转变：

- **Level 1 → Level 2**：从"会分析"到"能动手改"——需要 CUDA/Triton 编程能力
- **Level 2 → Level 3**：从"能改 kernel"到"能做架构决策"——需要多框架视野和系统设计能力
