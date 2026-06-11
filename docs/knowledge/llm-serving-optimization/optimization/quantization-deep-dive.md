# 量化深入：权重、激活、KV cache 与硬件路径

> 文档定位：项目知识库中的 LLM serving 优化专题，服务 Qwen3.6-27B / 35B-A3B 的量化实验。  
> 目标：理解为什么低比特不一定更快，如何区分 BF16、FP8、INT8、AWQ、GPTQ、NVFP4、GGUF 量化和 KV cache 量化。  
> 当前重点：解释 A800 上 FP8 不占优、AWQ 显存效率高、NVFP4 与 AWQ 速度接近。

## 1. 量化到底压缩什么

| 量化对象 | 例子 | 主要收益 | 风险 |
|---|---|---|---|
| 权重量化 | AWQ、GPTQ、FP8 weight-only | 降权重显存，可能降低权重带宽 | 反量化成本、kernel 支持 |
| 激活量化 | W8A8、FP8 W8A8 | 降计算和激活带宽 | 校准和精度风险 |
| KV cache 量化 | FP8 KV cache、INT8 KV cache | 降长上下文显存和 attention 访存 | 长上下文质量风险 |
| GGUF 量化 | Q4_K_M、Q5_K_M、Q8_0 | 本地部署体积/显存下降 | 生态和 kernel 路径不同 |

第一原则：

> 位数低不等于一定更快。速度取决于硬件、kernel、反量化、batch shape、prefill/decode 占比和 KV cache。

## 2. 常见精度和量化形态

| 名词 | 常见含义 | 当前 A800 判断 |
|---|---|---|
| BF16 / FP16 | 半精度基线 | 速度路径成熟，显存高 |
| FP8 W8A8 | 权重和激活都 FP8 | A800 不是真正主场 |
| FP8 W8A16 | 权重 FP8，激活 16-bit | A800 上常见 fallback |
| INT8 W8A8 | 权重和激活 INT8 | 需要校准和 kernel 支持 |
| AWQ INT4 | activation-aware weight-only INT4 | 当前显存效率强 |
| GPTQ INT4 | 二阶近似 weight-only INT4 | 生态广，速度看 kernel |
| NVFP4 / FP4 | 4-bit 浮点方向 | 更偏新 GPU，A800 需实测 |
| Q4_K_M / Q5_K_M | GGUF 量化类型 | llama.cpp 主线 |

## 3. Weight-only 量化为什么不一定提速

AWQ/GPTQ 常见形态：

```text
weights: 4-bit
activations: 16-bit
```

计算时通常需要：

```text
读取低比特权重 -> 反量化/解包 -> GEMM
```

如果低比特 kernel 很强，就可能快。  
如果反量化、访存布局或 shape 不友好，就可能只是省显存，不提速。

长上下文下还会遇到：

```text
prefill / attention / KV cache 成为瓶颈
```

这时权重变小，端到端速度也未必明显提高。

## 4. FP8 为什么要看硬件

FP8 的常见路径：

| 路径 | 说明 | 主场 |
|---|---|---|
| W8A8 FP8 | 权重和激活都 FP8 | Hopper / Ada / 更新 GPU |
| W8A16 FP8 | 权重 FP8，激活仍 16-bit | A800/A100 上常见 fallback |
| FP8 KV cache | KV cache 用 FP8 | 长上下文容量优化 |

当前 A800 上，第一阶段 FP8 慢于 BF16/AWQ/NVFP4 是合理现象。它不代表 FP8 本身不行，只代表：

> 当前硬件和当前 vLLM 路径下 FP8 不占优。

## 5. AWQ 和 GPTQ

| 项 | AWQ | GPTQ |
|---|---|---|
| 类别 | weight-only PTQ | weight-only PTQ |
| 思路 | 根据激活敏感性保护重要权重 | 用近似二阶信息降低误差 |
| 常见位宽 | INT4 | INT4 |
| 常见框架 | vLLM / SGLang / TensorRT-LLM | vLLM / SGLang / TensorRT-LLM |
| 速度关键 | Marlin/Machete 等 kernel | GPTQ Marlin 等 kernel |
| 质量关键 | 校准数据、保护比例、模型结构 | 校准数据、分组、误差传播 |

当前 Qwen3.6-27B 里：

- AWQ-INT4 权重显存最低。
- 16K 速度接近 BF16。
- 64K 与 NVFP4 差距很小。
- 值得继续测并发和上下文阶梯。

## 6. NVFP4 / FP4

NVFP4 / FP4 是更激进的低比特浮点方向。

要注意：

- 它更偏 Blackwell 等新架构方向。
- A800 上不是原生强项。
- 当前实测结果更多反映 vLLM 软件路径。
- 不能因为是 4-bit 就默认比 AWQ 快。

当前结论应保守写成：

> NVFP4 与 AWQ-INT4 在当前 16K/64K 短输出口径下速度接近；AWQ 显存效率更高，NVFP4 继续作为长上下文候选。

## 7. KV cache 量化

KV cache 量化适合长上下文，因为长 prompt 和多并发下 KV cache 会成为主要显存资源。

潜在收益：

- 更长上下文
- 更高并发
- 更低 HBM 读写压力

风险：

- 长上下文质量下降
- 数学/代码/结构化输出更敏感
- scaling factor 和量化粒度会影响结果

第二阶段建议把 `FP8 KV cache` 作为独立实验，而不是和权重量化混在一起。

## 8. 质量回归

性能实验之外，量化一定要做质量检查。

建议最小集：

| 场景 | 检查什么 |
|---|---|
| 中文长问答 | 是否漏答、重复、跑题 |
| 代码生成 | 语法、逻辑、能否运行 |
| 数学推理 | 中间步骤和答案 |
| JSON / tool calling | 格式是否稳定 |
| 长上下文检索 | 是否能引用后文信息 |
| reasoning 模型 | `<think>` / `reasoning_content` 是否正确 |

不要只看：

```text
tok/s
```

还要看：

```text
速度 / 显存 / 质量 / 稳定性
```

## 9. 当前实验建议

| 实验 | 模型 | 变量 | 目的 |
|---|---|---|---|
| AWQ 输出长度 | AWQ | `64/256/512` | 看 decode 占比变大后是否仍接近 BF16 |
| AWQ 并发 | AWQ | `1/2/4/8` | 看显存效率是否转成吞吐 |
| NVFP4 vs AWQ | NVFP4/AWQ | 固定 prompt/output | 判断差异是否大于噪声 |
| FP8 KV cache | AWQ/NVFP4 | `kv_cache_dtype=auto/fp8` | 看长上下文容量收益 |
| 质量回归 | AWQ/NVFP4/KV FP8 | 固定题集 | 判断量化是否可用 |

## 10. 相关文档

- [硬件与精度速查](../foundations/hardware.md)
- [KV cache 专题](../performance/kv-cache.md)
- [第一阶段实验报告](../experiments/stage1-qwen27b.md)
