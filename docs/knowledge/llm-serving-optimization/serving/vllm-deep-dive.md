# vLLM 深入：调度、KV cache 与性能参数

> 文档定位：项目知识库中的 LLM serving 优化专题，服务 `llmnode` 的 vLLM 实验和调优。  
> 目标：理解 vLLM 为什么适合生产推理、关键参数如何影响显存和速度、第二阶段应该怎么测。  
> 注意：vLLM 版本变化很快，具体参数默认值、支持模型和量化路径以当前镜像和官方文档为准。

## 1. vLLM 的定位

vLLM 是面向在线 LLM serving 的推理框架。它最核心的目标是：

```text
在尽量可控的延迟下，提高 GPU 利用率和吞吐。
```

它适合：

- OpenAI-compatible API 服务
- 多用户并发
- HF checkpoint / safetensors 模型
- 长上下文
- 多 GPU
- 多种量化格式

当前 `llmnode` 中，vLLM 是正式默认主后端。

## 2. 核心机制

| 机制 | 解决的问题 | 对实验的影响 |
|---|---|---|
| PagedAttention | KV cache 分页管理，减少碎片和浪费 | 长上下文容量更可控 |
| Continuous batching | 动态把不同请求合进 batch | 并发吞吐更好，但调度影响延迟 |
| Prefix caching | 复用相同前缀的 KV cache | 系统提示、few-shot、多轮共享前缀会受益 |
| Chunked prefill | 把长 prompt prefill 切块 | 避免长 prefill 阻塞 decode |
| CUDA graph | 降低重复 launch 开销 | 可能增加显存占用 |
| Speculative decoding | draft model/方法先猜 token，大模型验证 | 主要优化 decode，依赖接受率 |
| Quantization | 降权重、激活或 KV 精度 | 收益取决于硬件和 kernel |

## 3. 请求生命周期

简化流程：

```text
HTTP request
-> tokenizer / chat template
-> scheduler queue
-> prefill
-> KV cache allocation/write
-> decode loop
-> sampling
-> stream / final response
```

指标对应：

| 阶段 | 相关指标 |
|---|---|
| 排队 + tokenization + prefill | TTFT |
| decode loop | TPOT / ITL / completion tok/s |
| 全流程 | E2E latency |
| KV allocation | GPU memory / KV usage / OOM |

## 4. 关键参数

### 4.1 `max_model_len`

含义：

> 单条请求允许的最大上下文长度上限。

影响：

- 越大，vLLM 需要规划更多 KV cache。
- 太大可能启动失败。
- 太小会拒绝长请求。

注意：

```text
prompt tokens + output tokens <= max_model_len
```

如果 prompt 已经 4096，输出还要 64，而 `max_model_len=4096`，请求会超限。

### 4.2 `gpu_memory_utilization`

含义：

> vLLM 可以使用多少 GPU 显存比例。

影响：

- 越高，KV cache 池可能越大。
- 过高可能挤压 CUDA graph、runtime、临时 buffer。
- 过低可能无法支撑长上下文。

当前 Qwen3.6-27B 例子：

| profile | 值 | 现象 |
|---|---:|---|
| BF16 | `0.85` | 权重太大，256K 仍失败 |
| NVFP4 | `0.55` | 256K 单请求边界贴边 |
| AWQ-INT4 | `0.55` | KV 池更大，值得测并发 |

### 4.3 `max_num_seqs`

含义：

> 调度器允许同时管理的最大序列数。

影响：

- 多并发能力。
- scheduler 行为。
- KV cache 竞争。
- 单并发时也可能影响某些调度路径。

实验建议：

```text
max_num_seqs = 1 / 4
```

先看单并发是否有差异，再测并发阶梯。

### 4.4 Chunked prefill

长 prompt prefill 很容易阻塞 decode。chunked prefill 会把 prefill 切块，让 decode 请求有机会穿插执行。

适合观察：

- TTFT
- TPOT
- P99 latency
- 多并发时的解码抖动

注意：它不一定让单条请求端到端更快，更多是改善混部和尾延迟。

### 4.5 Prefix caching

prefix caching 适合：

- 固定 system prompt
- 多请求共享相同长前缀
- 多轮对话
- RAG 模板重复

不适合：

- 每个请求 prompt 完全不同。

实验时要区分：

```text
冷 cache
热 cache
```

否则结果会混。

## 5. vLLM 日志重点

启动日志要抓：

```text
Using max model len
Model loading took
Available KV cache memory
GPU KV cache size
Maximum concurrency
CUDA graph
Marlin / quantization
ERROR / OOM / ValueError
```

解释：

| 日志 | 说明 |
|---|---|
| `Model loading took` | 权重显存 |
| `Available KV cache memory` | KV 池容量 |
| `GPU KV cache size` | 内部 KV token/block 容量指标 |
| `Maximum concurrency` | 容量估算，贴边值要谨慎 |
| `Marlin` | 低比特 kernel 路径 |
| `CUDA graph` | 图捕获及额外显存开销 |

## 6. 当前 A800 上的 vLLM 判断

第一阶段说明：

- BF16 速度快，但权重显存太高，不适合 256K 主候选。
- FP8 在 A800 上不是原生 W8A8 路径，继续深挖价值有限。
- AWQ-INT4 显存效率最好，适合测并发和上下文阶梯。
- NVFP4 和 AWQ 速度接近，NVFP4 可作为长上下文候选继续保留。

## 7. 第二阶段 vLLM 实验矩阵

| 实验 | profile | 变量 | 指标 |
|---|---|---|---|
| 输出长度阶梯 | AWQ / NVFP4 | `64/256/512` | TTFT、TPOT、E2E、tok/s |
| 上下文阶梯 | AWQ | `16K/32K/64K/128K/192K/256K` | TTFT、KV usage、成功率 |
| 并发阶梯 | AWQ | `1/2/4/8` | QPS、P90/P99、KV usage |
| 显存参数 | NVFP4 | `0.55/0.6` | 256K 余量、显存峰值 |
| KV cache dtype | AWQ/NVFP4 | `auto/fp8` | 容量、速度、质量 |
| max_num_seqs | AWQ | `1/4` | 单并发和多并发差异 |

## 8. 常见误区

| 误区 | 修正 |
|---|---|
| `max_model_len=256K` 就代表能稳定跑 256K | 还要看 KV 余量、输出、系统 prompt、并发 |
| `gpu_memory_utilization` 越高越好 | 太高可能挤压 runtime 和 CUDA graph |
| 量化一定提速 | 长上下文瓶颈可能在 KV / attention |
| 单并发结果能代表服务吞吐 | 多并发调度会改变行为 |
| prefix cache 自动让所有请求变快 | 只有共享前缀时才有明显收益 |

## 9. 相关文档

- [Benchmark 方法论](../performance/benchmark-methodology.md)
- [KV cache 专题](../performance/kv-cache.md)
- [量化深入](../optimization/quantization-deep-dive.md)
