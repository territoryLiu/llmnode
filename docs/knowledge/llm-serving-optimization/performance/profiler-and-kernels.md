# Profiler 与 Kernel 分析入门

> 文档定位：项目知识库中的 LLM serving 优化专题，帮助从 benchmark 结果走向 kernel 级瓶颈分析。  
> 目标：知道什么时候需要 profiler、Nsight Systems / Nsight Compute / torch profiler 分别看什么，以及如何把“模型慢”改写成可优化的问题。  
> 当前重点：为第二阶段从 `completion tok/s` 走向 prefill / decode / kernel 证据做准备。

## 1. 什么时候需要 profiler

先做 benchmark，再做 profiler。

适合上 profiler 的情况：

- 两个 profile 速度差异明显，但原因不清楚。
- 16K 到 64K 掉速严重，需要证明是 attention / KV / HBM。
- output 拉长后 decode 仍慢，需要看 GEMM 或 sampling。
- 多并发 P99 抖动，需要看调度空洞或 CPU/GPU overlap。
- 某个 kernel 或量化路径怀疑没有生效。

不适合一开始就 profiler：

- 服务还没稳定 ready。
- benchmark 口径没固定。
- token 数和输出长度不准确。
- 只跑一次，没有可复现现象。

## 2. 三类工具

| 工具 | 看什么 | 适合回答 |
|---|---|---|
| Nsight Systems | 时间线、CPU/GPU overlap、kernel 排布、空洞 | 慢在哪个阶段，GPU 是否空转 |
| Nsight Compute | 单个 kernel 的访存、occupancy、stall、指令 | 某个 kernel 为什么慢 |
| torch profiler | PyTorch operator、CUDA kernel 关联 | 框架层 operator 和 kernel 怎么对应 |

先用 Nsight Systems 找阶段和大热点，再用 Nsight Compute 深挖单 kernel。

## 3. Prefill / Decode 怎么看

| 阶段 | 现象 | profiler 重点 |
|---|---|---|
| Prefill | 大 prompt 一次性处理，TTFT 高 | attention、GEMM、Rope、Norm、KV 写入 |
| Decode | 每步生成一个 token，循环多次 | 小 batch GEMM、attention KV 读取、sampling、调度 |

长上下文 prefill 常见热点：

- attention kernel
- GEMM / matmul
- rope
- norm
- KV cache 写入
- memory copy / layout transform

decode 常见热点：

- attention over KV
- small GEMM
- sampling
- CPU scheduler gap
- kernel launch overhead

## 4. 常见瓶颈类型

| 瓶颈 | 表现 | 下一步 |
|---|---|---|
| 算力瓶颈 | Tensor Core 利用高，GEMM 占主导 | 看量化、batch、kernel |
| HBM 带宽瓶颈 | memory throughput 高，stall 多 | 看 KV cache、layout、quantization |
| 调度空洞 | GPU 时间线上有空白 | 看 batching、CPU scheduler、chunked prefill |
| KV cache 压力 | 长上下文掉速、显存贴边 | 看 KV dtype、prefix cache、上下文截断 |
| 反量化开销 | 低比特模型 kernel 多且碎 | 看 Marlin/Machete 路径 |
| 通信瓶颈 | 多 GPU 中 NCCL 时间高 | 看 TP/PP/EP、NVLink/PCIe |

## 5. 采样对象怎么选

不要对所有点都 profiler。第一轮只选 1 到 2 个代表点：

| 点 | 为什么选 |
|---|---|
| `AWQ + 64K prompt + 512 output` | 显存效率候选，decode 占比更合理 |
| `NVFP4 + 64K prompt + 512 output` | 长上下文候选，和 AWQ 对比 |
| `BF16 + 64K prompt + 512 output` | 速度上限参考 |
| `AWQ + 256K prompt + 64/256 output` | 长上下文极限 |

优先级：

```text
先固定一个模型和请求形状，
再比较不同量化或参数。
```

## 6. Profiler 报告模板

```markdown
## Profile 对象

- 后端：
- 模型：
- profile：
- prompt tokens：
- output tokens：
- concurrency：
- GPU：
- 命令：

## 总览

- TTFT：
- TPOT：
- E2E latency：
- GPU 利用率：
- 显存峰值：

## 时间线观察

- prefill 时间：
- decode 时间：
- 是否有 GPU 空洞：
- CPU 是否阻塞：

## Top kernels

| kernel | 阶段 | 时间占比 | 初步判断 |
|---|---|---:|---|

## 结论

- 已确认瓶颈：
- 仍是推断：
- 下一步验证：
```

## 7. 从 profiler 到优化动作

| 发现 | 可能动作 |
|---|---|
| prefill attention 占主导 | chunked prefill、FlashAttention 路径、上下文策略 |
| decode KV 读取占主导 | KV cache 量化、prefix cache、减少上下文 |
| 低比特 GEMM 慢 | 换量化 kernel、对比 BF16/AWQ/NVFP4 |
| GPU 空洞多 | 调度参数、并发、max_num_seqs、CPU 侧排查 |
| CUDA graph 占显存大 | 调整图捕获相关配置或显存参数 |
| sampling/CPU 明显 | 检查 tokenizer、stream、JSON/tool parsing |

## 8. 给芯片/编译器团队的问题描述

不要说：

```text
模型很慢。
```

要说：

```text
在 A800 上，Qwen3.6-27B-AWQ-INT4，vLLM，prompt=64K，output=512，concurrency=1。
prefill 阶段占 E2E 的 X%，Top kernel 是 Y，shape 是 Z。
Nsight 显示该 kernel memory stall 高 / Tensor Core 利用低 / launch gap 明显。
复现命令和 trace 路径如下。
```

## 9. 当前第二阶段建议

先不用追求完整 profiler 体系。最小闭环：

1. 跑 `AWQ + 64K prompt + 512 output`。
2. 记录 TTFT / TPOT / E2E。
3. 采一次 Nsight Systems 或 torch profiler。
4. 标出 prefill 和 decode 大致时间。
5. 列 top 5 kernels。
6. 判断下一步该看 KV cache、量化 kernel，还是调度。

## 10. 相关文档

- [Benchmark 方法论](./benchmark-methodology.md)
- [KV cache 专题](./kv-cache.md)
- [vLLM 深入](../serving/vllm-deep-dive.md)
