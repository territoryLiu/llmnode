# KV Cache 与长上下文容量

> 文档定位：项目知识库中的 LLM serving 优化专题，服务长上下文、显存容量、并发能力和 KV cache 量化实验。  
> 目标：讲清楚 KV cache 是什么、为什么 64K/128K/256K 会慢、vLLM 启动日志里的 KV 指标该怎么读。  
> 当前重点：解释 Qwen3.6-27B 第一阶段里 `KV memory / KV tokens / maximum concurrency` 的正确口径。

## 1. KV cache 是什么

Transformer decode 时，每生成一个 token，都需要关注之前的 token。为了避免每一步重复计算历史 token 的 Key 和 Value，推理框架会缓存每层 attention 的 K/V：

```text
KV cache = 每层历史 token 的 Key / Value 张量
```

它解决的是：

> decode 时不要重复算历史 token 的 K/V。

它带来的问题是：

> 上下文越长，KV cache 越大，显存和 HBM 带宽压力越高。

## 2. Prefill 和 Decode 里的 KV

| 阶段 | KV cache 行为 | 性能影响 |
|---|---|---|
| Prefill | 处理整个 prompt，并把所有 prompt token 的 K/V 写入 cache | prompt 越长，写入越多，TTFT 越高 |
| Decode | 每步读取历史 KV，并追加新 token 的 K/V | 上下文越长，每步读的 KV 越多 |

长上下文慢，通常不是一个原因，而是组合：

- prefill 算法量更大
- attention 访存更重
- KV cache 写入/读取更多
- GPU HBM 带宽压力更大
- 调度和分页管理更复杂

## 3. KV cache 显存近似公式

简化公式：

```text
KV bytes ~= layers * tokens * kv_heads * head_dim * 2(K+V) * bytes_per_element
```

需要注意：

- `kv_heads` 不是一定等于 attention heads，GQA/MQA 会减少 KV heads。
- Tensor Parallel 可能切分或复制部分 KV，取决于模型结构和框架实现。
- vLLM 的 paged KV 会按 block 分配，不是每个 token 完全连续增长。
- CUDA graph、runtime workspace、allocator 碎片也会吃显存。

所以这个公式适合理解方向，不适合替代框架日志。

## 4. GQA / MQA 为什么重要

| Attention 结构 | KV heads | KV cache 压力 |
|---|---:|---|
| MHA | 接近 attention heads | 最大 |
| GQA | 少于 attention heads | 明显降低 |
| MQA | 通常很少 KV heads | 更低 |

同样是 27B，不同模型结构的 KV cache 成本可能差很多。因此不要用一个模型的 `KV tokens` 线性外推另一个模型。

## 5. vLLM 日志怎么看

常见关键行：

```text
Model loading took ... GiB memory
Available KV cache memory: ... GiB
GPU KV cache size: ... tokens
Maximum concurrency for 262,144 tokens per request: ...x
```

含义：

| 日志项 | 含义 | 注意 |
|---|---|---|
| `Model loading took` | 权重加载后占用显存 | 不等于总显存占用 |
| `Available KV cache memory` | vLLM 规划给 KV cache 的显存池 | 不是单条请求实际消耗 |
| `GPU KV cache size` | KV 池可容纳的内部 token/block 容量指标 | 不能直接线性外推最大 prompt |
| `Maximum concurrency for ...` | 按指定 max len 估算的并发余量 | `1.07x` 是贴边，不是稳定多并发 |

第一阶段里要特别记住：

> `KV memory / KV tokens` 是启动侧 KV cache 池容量，不是“真正 256K 请求已经消耗的 KV”。

## 6. 为什么不能线性外推 `GPU KV cache size tokens`

原因包括：

1. vLLM 的 token/block 容量是内部规划口径。
2. 请求的 prompt、输出、系统提示、chat template 都会影响实际 token。
3. 不同模型的 attention 结构、GQA/MQA、layer 数不同。
4. 不同 dtype 的 KV cache bytes 不同。
5. 框架会预留 runtime 和调度空间。
6. 有些指标在长请求过程中可能返回 null 或不稳定。

正确做法：

- 启动侧看 `Maximum concurrency` 和 KV 不足错误。
- 请求侧看服务端是否实际跑通。
- 过程侧看 GPU 显存峰值和 `GPU KV cache usage`。
- 结论里区分“容量判断可过”和“服务端实测通过”。

## 7. 第一阶段 Qwen3.6-27B 的 KV 解释

| profile | weight memory | KV memory | 判断 |
|---|---:|---:|---|
| `BF16` | `51.1 GiB` | `14.13 GiB` | 权重太大，`max_model_len=262144` 启动失败 |
| `FP8` | `28.87 GiB` | `20.5 GiB` | KV 池更大，但 A800 FP8 fallback 速度不占优 |
| `NVFP4` | `24.05 GiB` | `17.38 GiB` | 接近 256K 单请求边界，`1.07x` 很贴边 |
| `AWQ-INT4` | `19.05 GiB` | `22.38 GiB` | KV 池最大，值得测上下文和并发 |

方向性结论：

```text
权重量化省出的显存，很大一部分会变成 KV cache 容量和并发余量。
```

但不能写成严格等式，因为 `gpu_memory_utilization`、runtime、CUDA graph 和碎片也影响分配。

## 8. KV cache 量化

KV cache 量化的目标：

```text
减少 KV cache 显存和带宽压力
```

它和权重量化不同：

| 方向 | 压缩对象 | 主要收益 |
|---|---|---|
| 权重量化 | 模型参数 | 降低权重显存，可能提升 GEMM |
| KV cache 量化 | 历史 token 的 K/V | 降低长上下文显存和 attention 访存 |

第二阶段可以考虑：

```text
--kv-cache-dtype fp8
```

但必须补质量回归，因为 KV 精度会影响 attention 结果，尤其长上下文、代码、数学和结构化输出。

## 9. 长上下文实验建议

| 实验 | 固定项 | 变量 | 目的 |
|---|---|---|---|
| 上下文阶梯 | AWQ、output 256、并发 1 | `16K/32K/64K/128K/192K/256K` | 找速度曲线和失败边界 |
| KV dtype 对比 | AWQ 或 NVFP4 | `auto/fp8` | 看 KV 压缩收益和质量风险 |
| 显存参数对比 | NVFP4 | `gpu_memory_utilization=0.55/0.6` | 看 256K 余量 |
| 并发阶梯 | AWQ | `1/2/4/8` | 看 KV 池是否转化为吞吐 |

## 10. 相关文档

- [Benchmark 方法论](./benchmark-methodology.md)
- [vLLM 深入](../serving/vllm-deep-dive.md)
- [第一阶段实验报告](../experiments/stage1-qwen27b.md)
