# 大模型推理加速方法地图

> 文档定位：项目知识库中的 LLM serving 优化基础专题，不属于 `llmnode` 项目蓝图、契约或正式路线图。  
> 适用目标：提供大模型推理加速方法总图和索引。具体模型格式见 [model-format.md](./model-format.md)，硬件精度见 [hardware.md](./hardware.md)，benchmark 口径见 [../performance/benchmark-methodology.md](../performance/benchmark-methodology.md)。  
> 更新时间：2026-06-05。涉及框架支持状态时，以官方文档和本机实测为准。

## 1. 先建立总图

大模型推理加速不是只有“量化”。常见方法可以分成八层：

| 层级 | 解决的问题 | 典型方法 |
|---|---|---|
| 数值精度与权重量化 | 减少权重显存、提高 GEMM 吞吐 | FP8、FP4、NVFP4、INT8、INT4、AWQ、GPTQ、W8A8、W4A16 |
| KV cache 压缩 | 降低长上下文显存和带宽压力 | FP8 KV cache、INT8 KV cache、NVFP4 KV cache、KV cache reuse |
| 模型格式与运行生态 | 让模型适配不同推理框架 | HF safetensors、GGUF、TensorRT-LLM checkpoint |
| Attention / GEMM Kernel | 提升核心算子效率 | FlashAttention、PagedAttention、FlashInfer、Marlin、CUTLASS、Triton Kernel |
| 解码策略 | 减少每个 token 都跑完整大模型的成本 | Speculative Decoding、MTP、Medusa、EAGLE、NGram / Prompt Lookup |
| 调度与缓存 | 提高 GPU 利用率、减少重复计算 | Continuous batching、chunked prefill、prefix caching、CUDA Graph |
| 并行与通信 | 支撑更大模型或更高吞吐 | Tensor Parallel、Pipeline Parallel、Expert Parallel、Data Parallel、PD 分离 |
| 模型结构优化 | 从模型本身减少计算或访存 | GQA/MQA、MoE、MLA、蒸馏、剪枝、低秩化 |

所以你看到一个名词时，先问三个问题：

1. 它是在压缩权重、压缩 KV，还是改变解码流程？
2. 它依赖特定硬件、特定框架，还是只是模型文件格式？
3. 它主要改善显存、吞吐、首字延迟、长上下文，还是部署便利性？

## 2. 先区分四类东西

刚入门时最容易把“模型格式、量化方法、解码方法、运行框架”混在一起。先用下面这个分层记：

```text
safetensors / GGUF = 模型权重装在哪个盒子里
AWQ / GPTQ / FP8 / INT4 / NVFP4 = 盒子里的权重或激活怎么压缩
MTP / speculative decoding = 生成 token 的流程怎么加速
vLLM / SGLang / llama.cpp = 谁来运行这个模型
```

更准确地说：

| 对象 | 它是什么 | 常见生态 | 注意点 |
|---|---|---|---|
| `safetensors` | HuggingFace 生态常见权重存储格式 | vLLM / SGLang / Transformers | 本身不代表量化方法 |
| `GGUF` | llama.cpp 生态模型文件格式 | llama.cpp / Ollama | 是格式，不是量化算法 |
| AWQ / GPTQ | 权重量化算法 | vLLM / SGLang / TensorRT-LLM，也可能进入 GGUF 转换链 | 能不能快要看运行时 Kernel |
| FP8 / INT8 / INT4 / NVFP4 | 数值格式或量化形态 | 多个生态都可能支持 | 名字相同不代表实现相同 |
| MTP / Medusa / EAGLE | 解码加速方法 | vLLM / SGLang / TensorRT-LLM / llama.cpp 的不同路径 | 需要模型、预测头或调度支持 |
| vLLM / SGLang / llama.cpp | 推理框架 | 各自有不同模型加载、调度和 Kernel 路径 | 同一个模型在不同框架里性能可能差很多 |

常见但需要修正的说法：

| 简化说法 | 更准确的说法 |
|---|---|
| vLLM / SGLang 只支持 safetensors | 主流路径是 HuggingFace checkpoint，常见文件是 safetensors；具体还要看框架支持的模型结构和量化格式 |
| llama.cpp 只支持 GGUF | 主流推理模型格式是 GGUF；转换和生态工具可能接触 HF 权重，但运行侧主要看 GGUF |
| AWQ / GPTQ / NVFP4 各种格式都能用 | 概念可跨生态，但工程上要看权重是否存在、框架是否能加载、硬件是否支持、Kernel 是否优化 |
| MTP 和 GGUF 是一回事 | GGUF 是格式，MTP 是解码加速；它们经常一起出现，是因为 llama.cpp/GGUF 社区很关注本地生成速度 |

对当前 `llmnode` 项目，先按下面理解：

| 项目方向 | 优先关注 |
|---|---|
| vLLM / SGLang | HF/safetensors 生态下的 FP8、AWQ、NVFP4、KV cache、调度 |
| llama.cpp | GGUF 生态下的 Q4_K_M、Q5_K_M、Q8_0、IQ/UD、speculative/MTP |
| 跨生态对比 | 不用只看名字，必须用同一 prompt、同一输出长度、同一统计口径实测 |

本节只保留总分层。模型文件格式、量化格式和三后端支持关系不要在这里继续展开，统一维护在 [model-format.md](./model-format.md)。

## 3. 术语速查表

| 名词 | 属于哪一类 | 一句话解释 | 主要收益 | 主要风险 |
|---|---|---|---|---|
| FP16 / BF16 | 基准精度 | 常见半精度推理格式 | 精度稳、兼容强 | 显存和带宽成本高 |
| FP8 | 浮点量化 | 8-bit 浮点权重/激活/KV | 显存低、Tensor Core 友好 | 依赖硬件与框架支持 |
| FP4 / NVFP4 | 4-bit 浮点量化 | NVIDIA 新一代低精度格式 | 极低显存、面向新 GPU | 支持范围更窄，需实测 |
| INT8 | 整数量化 | 8-bit 整数权重或激活 | 兼容较广、精度损失较小 | 不同 GPU 支持差异大 |
| INT4 | 整数量化 | 4-bit 整数量化 | 显存明显下降 | 反量化和精度风险更高 |
| W8A8 | 权重和激活量化 | weights 8-bit + activations 8-bit | 权重和计算都可受益 | 校准、Kernel 支持要求高 |
| W4A16 | weight-only 量化 | 权重 4-bit，激活仍 16-bit | 大幅省权重显存 | 计算前常要反量化 |
| W4A8 | 权重和激活混合低比特 | 权重 4-bit，激活 8-bit | 更激进的显存/带宽优化 | 更依赖硬件和框架 |
| AWQ | 权重量化算法 | Activation-aware Weight Quantization | INT4 常用，精度较稳 | 不是所有 Kernel 都快 |
| GPTQ | 权重量化算法 | 基于近似二阶信息的 PTQ | 离线量化成熟 | 量化耗时和兼容性要看模型 |
| SmoothQuant | W8A8 方法 | 平滑激活异常值，方便 INT8 | 适合 W8A8 | 需要校准和框架支持 |
| Marlin | 低比特 GEMM Kernel | 面向 GPTQ/AWQ 等权重量化的高效 Kernel | 低比特矩阵乘更快 | 模型、shape、GPU 有限制 |
| bitsandbytes | 量化/加载库 | 常见 LLM.int8、NF4、4bit 加载 | 使用方便 | 服务化吞吐未必最佳 |
| GGUF | 模型文件格式 | llama.cpp 生态格式，支持多种量化 | 部署简单、跨平台 | 不是量化算法本身 |
| Q4_K_M / Q5_K_M | GGUF 量化类型 | llama.cpp K-quants | 本地部署常用 | GPU 高并发弱于 vLLM 类服务 |
| IQ / UD 量化 | GGUF 生态量化策略 | 更细粒度或动态的 GGUF 量化 | 同体积精度可能更好 | 依赖具体工具链 |
| MTP | 解码加速 | Multi-Token Prediction，多 token 预测 | 降低 decode 次数 | 需要模型/预测头/框架调度支持 |
| Medusa | 解码加速 | 多个预测头给 draft tokens | 可提高生成吞吐 | 需要额外头或适配 |
| EAGLE | 解码加速 | 基于特征预测的 speculative 方法 | 接受率可能更好 | 系统复杂度更高 |
| Speculative Decoding | 解码加速大类 | 小模型或预测头先生成，大模型验证 | decode 加速 | 接受率低时收益下降 |
| Prefix Caching | 缓存复用 | 复用相同前缀的 KV cache | 多轮/重复 prompt 加速 | 命中率决定收益 |
| Chunked Prefill | 调度优化 | 把长 prompt prefill 切块调度 | 降低阻塞、改善混部 | 参数不当会影响吞吐 |
| PagedAttention | KV 管理 | vLLM 代表性 KV cache 分页管理 | 长上下文和批处理友好 | 框架内机制，不是独立量化 |

## 4. 数值精度与权重量化

### 4.1 FP16 / BF16：基准线

FP16 和 BF16 是常见的半精度推理基线。它们的优势是精度稳定、框架支持成熟；劣势是权重显存、带宽和 KV cache 成本较高。

学习时不要一上来只看量化模型。先知道 FP16/BF16 的速度和显存，后面才能判断 FP8、INT4 到底省了多少。

### 4.2 FP8

FP8 是 8-bit 浮点量化，常见于 Hopper、Ada、Blackwell 等较新 GPU 路径。它既可以用于权重，也可以用于激活和 KV cache，具体支持取决于框架和硬件。

适合场景：

- 高并发服务
- 支持 FP8 Tensor Core 的 GPU
- vLLM / TensorRT-LLM / SGLang 等服务框架
- 对精度有要求，但又希望显存和吞吐优于 FP16/BF16

注意点：

- FP8 不等于一定比 INT4 更省显存。
- FP8 的优势通常来自硬件 Tensor Core 和成熟 Kernel。
- 需要验证质量，不要只看速度。

当前项目关联：

- `Qwen3.6-35B-A3B-FP8` 是当前项目里很适合做基线分析的 profile。

### 4.3 FP4 / NVFP4 / MXFP4

FP4 是 4-bit 浮点方向，NVFP4 是 NVIDIA 生态中的低精度格式之一。相比 INT4，FP4/NVFP4 试图保留浮点表达范围，同时把位宽压到 4-bit。

适合场景：

- 新架构 GPU
- 对权重显存非常敏感
- 框架已经有配套 Kernel 和量化路径

注意点：

- 支持范围明显比 FP8 窄。
- 不能只看“4-bit”就断言一定快。
- 低比特格式常常受反量化、Kernel、访存布局影响。

当前项目关联：

- 当前在线 profile 是 `Qwen3.6-27B-NVFP4`。
- 这个 profile 已经能跑 `256K`，但长上下文端到端延迟仍然很高，说明“容量可用”和“体验好”不是同一件事。

### 4.4 INT8 与 W8A8

INT8 是 8-bit 整数量化。W8A8 表示权重 8-bit、激活 8-bit，是比单纯权重量化更完整的计算加速路径。

适合场景：

- NVIDIA Turing / Ampere / Ada / Hopper 等支持 INT8 计算的 GPU
- 需要权重和激活都降精度
- 有校准数据，能接受校准和质量验证成本

注意点：

- W8A8 要处理激活异常值，常见方法包括 SmoothQuant。
- 某些新架构或框架版本会更推荐 FP8 而不是 INT8。
- INT8 是否更快取决于 Kernel 和硬件路径。

### 4.5 INT4、W4A16、W4A8

INT4 常见于 weight-only 量化。W4A16 表示权重 4-bit、激活 16-bit；W4A8 表示权重 4-bit、激活 8-bit。

适合场景：

- 显存紧张
- 单机本地部署
- 需要把更大模型塞进有限显存
- 对吞吐要求不是唯一目标

注意点：

- Weight-only 量化省显存明显，但计算时可能需要反量化。
- 如果低比特 GEMM Kernel 不好，可能“显存省了，速度没快”。
- 长上下文下 KV cache 可能变成主瓶颈，权重变小不等于 256K 就快。

当前项目关联：

- `Qwen3.6-35B-A3B-AWQ-4bit`
- `Qwen3.6-27B-AWQ-INT4`

### 4.6 AWQ

AWQ 是一种权重量化方法，重点是根据激活分布保护重要权重，常用于 INT4 / W4A16 场景。

适合场景：

- 想用 4-bit 权重量化，但希望精度比粗暴 INT4 更稳
- vLLM、TensorRT-LLM、AutoAWQ、llama.cpp 生态中的部分转换链路

注意点：

- AWQ 是量化算法，不等于某一种文件格式。
- AWQ 模型要看运行时是否有高效 Kernel。
- AWQ 在短上下文和长上下文下的收益可能不同。

### 4.7 GPTQ

GPTQ 是另一类成熟的离线权重量化算法，常见于 INT4 权重量化。它用近似二阶信息降低量化误差。

适合场景：

- 离线量化
- 追求较好精度的 weight-only 低比特模型
- 有现成 GPTQ checkpoint 可直接使用

注意点：

- GPTQ 模型加载和 Kernel 支持要看框架。
- GPTQ 不自动保证端到端最快。
- `gptq_marlin` 这类组合通常比普通 GPTQ 路径更强调 Kernel 性能。

### 4.8 Marlin、AWQ Marlin、GPTQ Marlin

Marlin 更接近低比特矩阵乘 Kernel 优化路径。它常和 GPTQ/AWQ 这类量化权重配合，用于提高低比特 GEMM 效率。

你可以这样理解：

- AWQ/GPTQ：解决“怎么把权重量化得尽量准”
- Marlin：解决“量化后怎么乘得更快”

这是很重要的分层。面试里如果能讲清楚这点，会比单纯背名词强很多。

### 4.9 bitsandbytes、NF4、QLoRA

bitsandbytes 常见于训练和推理加载场景，支持 LLM.int8、4-bit、NF4 等。NF4 和 QLoRA 更常出现在低成本微调里，但也会影响推理加载和显存。

注意点：

- QLoRA 主要是训练/微调方案，不应简单当成推理加速方案。
- bitsandbytes 方便，但在高并发服务吞吐上不一定是最优路径。

## 5. GGUF 与 llama.cpp 生态

GGUF 是模型文件格式，不是量化算法。它属于 llama.cpp / Ollama 等生态，支持多种 tensor encoding 和量化类型。

常见 GGUF 类型：

| 类型 | 大致含义 | 适合场景 |
|---|---|---|
| F16 / BF16 | 半精度 | 精度基线 |
| Q8_0 | 8-bit | 高精度、本地部署 |
| Q6_K | 6-bit K-quant | 精度优先但想省显存 |
| Q5_K_M | 5-bit K-quant | 精度和体积平衡 |
| Q4_K_M | 4-bit K-quant | 本地部署常用平衡点 |
| Q4_K_S | 更小的 4-bit | 显存更紧张 |
| Q3_K / Q2_K | 更低 bit | 极限压缩，质量风险高 |
| IQ 系列 | 更细粒度低比特 | 需要具体实测 |
| UD 系列 | 动态/分层量化策略 | 同体积质量可能更好 |

当前项目里要注意：

- llama.cpp 使用 GGUF。
- vLLM 通常使用 HuggingFace safetensors 或框架支持的量化 checkpoint。
- 不要把 “GGUF” 和 “INT4/AWQ/GPTQ” 混为一谈。GGUF 是容器，里面可以有很多量化编码。

## 6. KV cache 量化与长上下文

长上下文下，权重显存不一定是最大问题。KV cache 会随着上下文长度增长，占用大量显存和带宽。

常见方法：

| 方法 | 作用 | 适合场景 |
|---|---|---|
| FP8 KV cache | 降低 KV cache 显存 | 长上下文、高并发 |
| INT8 KV cache | 用 INT8 存 KV | 硬件/框架支持时 |
| NVFP4 KV cache | 更低位宽 KV cache | 新 GPU / TensorRT-LLM 等路径 |
| Prefix caching | 复用已有前缀 KV | 多轮对话、相同系统 prompt |
| KV cache reuse | 复用上下文缓存 | Agent、RAG、代码任务 |
| PagedAttention | 分页管理 KV cache | vLLM 长上下文和批处理 |
| RadixAttention | 前缀树式缓存复用 | SGLang 场景 |

当前项目学习重点：

- `256K` 能跑通，不代表速度好。
- 如果 completion tok/s 从 `4K` 到 `256K` 急剧下降，通常要关注 prefill 成本、Attention 访存和 KV cache。
- 量化权重只能解决一部分问题，不能自动消除长上下文 KV 成本。

## 7. Attention 和 GEMM Kernel 加速

大模型推理里，核心计算集中在 GEMM、Attention、Norm、Rope、MoE expert GEMM 等路径。

常见方法：

| 方法 | 作用 | 你应该怎么理解 |
|---|---|---|
| FlashAttention | 优化 Attention 的访存和 softmax | 减少 HBM 往返 |
| PagedAttention | 管理 KV cache 分页 | vLLM 核心机制之一 |
| FlashInfer | 推理场景的 Attention/KV Kernel 库 | 常见于高性能推理优化 |
| FlashMLA | MLA 场景优化 | DeepSeek 等 MLA 架构相关 |
| CUTLASS GEMM | NVIDIA GEMM 模板库 | 高性能矩阵乘基础 |
| Triton Kernel | Python 风格写 GPU Kernel | 入门自定义算子常用 |
| CUDA Graph | 降低重复 kernel launch 开销 | decode 阶段形状稳定时有用 |
| fused kernel | 融合多个小算子 | 减少读写和 launch 开销 |

学习顺序建议：

1. 先看 GEMM 为什么重要。
2. 再看 Attention 为什么长上下文下容易受访存影响。
3. 再看 Norm / Rope 这类小算子为什么需要 fuse。
4. 最后再学 Triton / CUDA 自己写 Kernel。

## 8. 解码加速：MTP、Medusa、EAGLE、投机解码

传统自回归 decode 是一次生成一个 token。解码加速的核心思路是：先猜多个 token，再让主模型验证，减少大模型完整前向次数。

### 8.1 Speculative Decoding

投机解码是大类。常见形式：

- 小 draft model 先生成多个 token。
- 大模型一次验证多个 token。
- 接受的 token 直接保留，拒绝后回退。

适合场景：

- decode 阶段占主要耗时
- 输出较规律，draft 接受率高
- 有合适小模型或预测头

### 8.2 MTP

MTP 是 Multi-Token Prediction，多 token 预测。它可以理解为让模型或额外模块一次预测多个后续 token，再配合验证机制。

适合场景：

- 代码、日志、结构化文本、技术文档
- 长输出
- decode 阶段成为瓶颈

注意点：

- 需要模型、权重或框架支持。
- 接受率低时收益会下降。
- 它不主要解决 prefill 和 KV cache 显存问题。

### 8.3 Medusa

Medusa 使用多个预测头生成候选 token，再由主模型验证。它和 MTP 都属于“不要老老实实一个 token 一个 token 生成”的思路。

### 8.4 EAGLE

EAGLE 是另一类 speculative decoding 方法，通常利用特征或轻量预测模块生成 draft。它的目标也是提高接受率和 decode 吞吐。

### 8.5 NGram / Prompt Lookup

这类方法从 prompt 或历史文本中找可复用片段作为 draft。对代码补全、重复文本、模板化输出可能有效。

## 9. 调度、缓存与服务级优化

如果你做服务端推理，只懂量化还不够。很多吞吐来自调度。

| 方法 | 作用 | 常见框架 |
|---|---|---|
| Continuous batching | 动态把请求拼成批 | vLLM / SGLang / TensorRT-LLM |
| In-flight batching | 运行中持续合批 | TensorRT-LLM 等 |
| Chunked prefill | 长 prompt 切块 | vLLM / SGLang |
| Prefix caching | 复用相同前缀 | vLLM / SGLang |
| RadixAttention | 前缀树 KV 复用 | SGLang |
| Disaggregated prefill/decode | prefill 和 decode 分离部署 | 大规模服务 |
| CUDA Graph | 固定 shape 减少调度开销 | vLLM / TensorRT-LLM 等 |
| Speculative scheduler | 和投机解码配合调度 | vLLM / SGLang / TensorRT-LLM |

当前项目里，这层对应：

- 性能实验室
- `max_num_seqs`
- 长上下文 benchmark
- gateway 和 backend 路径对比
- readiness 与 warming_up 诊断

## 10. 并行、通信与多 GPU

当单 GPU 放不下或吞吐不够时，会进入并行和通信优化。

| 方法 | 作用 | 风险 |
|---|---|---|
| Tensor Parallel | 把单层矩阵切到多 GPU | all-reduce 通信开销 |
| Pipeline Parallel | 按层切分 | pipeline bubble |
| Data Parallel | 多副本服务 | 权重复制占显存 |
| Expert Parallel | MoE 专家分布到多 GPU | 路由和 all-to-all 开销 |
| Context Parallel | 长上下文维度切分 | Attention 通信复杂 |
| PD 分离 | prefill 和 decode 分开 | 系统复杂度上升 |
| KV cache offload | KV 放 CPU/远端 | 延迟和带宽风险 |

这部分先不用急。等你能解释单 GPU 上 `4K -> 256K` 为什么变慢，再学多 GPU 才不会飘。

## 11. 模型结构层面的加速

有些加速不是推理框架做的，而是模型结构本身决定的。

| 方法 | 解释 | 影响 |
|---|---|---|
| GQA | 多个 query head 共享较少 KV head | 降低 KV cache 成本 |
| MQA | 所有 query head 共享 KV | 更省 KV，但表达能力需权衡 |
| MoE | 只激活部分专家 | 参数大但每 token 计算较少 |
| MLA | Multi-head Latent Attention | 降低 KV cache 压力，DeepSeek 相关 |
| 蒸馏 | 大模型教小模型 | 减少整体计算 |
| 剪枝 | 删除不重要参数或结构 | 需要质量验证 |
| 早退 | 部分 token 提前结束计算 | 实现复杂，质量风险 |

岗位要求里提到 GLM / Qwen / DeepSeek，就是希望你不只会跑框架，还能看懂模型结构为什么影响性能。

## 12. 当前 llmnode 项目里的落点

当前项目最适合先围绕这些方法学习：

| 项目对象 | 对应加速方法 | 学习问题 |
|---|---|---|
| `Qwen3.6-27B-NVFP4` | NVFP4 / vLLM / 长上下文 | 低比特能否改善 256K 体验？ |
| `Qwen3.6-35B-A3B-FP8` | FP8 | FP8 和 AWQ 在长上下文下谁更稳？ |
| `Qwen3.6-35B-A3B-AWQ-4bit` | AWQ / INT4 | 权重更小是否等于更快？ |
| `Qwen3.6-27B-AWQ-INT4` | AWQ-INT4 | 27B INT4 的瓶颈在哪里？ |
| `llama.cpp q4km.gguf` | GGUF / Q4_K_M | 本地轻量部署和服务化吞吐差异 |
| SGLang profile | SGLang / reasoning parser / KV | ready、KV 分配、请求稳定性 |
| 性能实验室 | benchmark / 调参矩阵 | 建立实测而不是猜测 |

建议第一组学习实验：

1. 固定后端 `vLLM`。
2. 比较 `FP8 / AWQ-4bit / NVFP4`。
3. 固定输出长度 `64`。
4. 比较 `4K / 32K / 128K / 256K`。
5. 记录权重显存、KV cache、completion tok/s、端到端延迟。

## 13. 初学者容易混淆的点

### 13.1 GGUF 不是量化算法

GGUF 是格式。`Q4_K_M`、`Q5_K_M`、`IQ` 才是里面的量化编码或策略。

### 13.2 AWQ/GPTQ 不等于一定更快

AWQ/GPTQ 主要解决“低比特后质量尽量不掉”。端到端速度还取决于 Kernel、反量化、batch、prompt 长度和框架。

### 13.3 INT4 省权重，不省 KV cache

长上下文时，KV cache 可能成为显存和带宽大头。只把权重变小，不一定让 `256K` 变快。

### 13.4 MTP 主要加速 decode，不主要加速 prefill

如果请求慢在超长 prompt prefill，MTP 不一定是第一优先级。

### 13.5 FP8 和 INT8 谁快要看硬件

不同 GPU 架构支持不同。新硬件上 FP8/FP4 可能更有优势；旧硬件上 INT8 或 INT4 路径可能更现实。

## 14. 后续学习顺序

建议按这个顺序学：

1. 先弄懂 FP16/BF16、FP8、INT8、INT4 的数值差异。
2. 再弄懂 AWQ/GPTQ/SmoothQuant 是怎么做校准和误差控制的。
3. 再弄懂 GGUF 只是格式，vLLM/SGLang 常用 HF checkpoint。
4. 再看 KV cache 为什么决定长上下文容量。
5. 再看 FlashAttention/PagedAttention 为什么能优化 Attention。
6. 再看 MTP/Medusa/EAGLE 为什么能加速 decode。
7. 最后进入 CUDA/Triton Kernel 和 Nsight profiling。

## 15. 推荐记录模板

```markdown
## YYYY-MM-DD：某种加速方法学习记录

### 今天学习的方法

- 名称：
- 所属层级：
- 它解决的问题：

### 和其他方法的区别

- 它不是：
- 它和相近方法的区别：

### 当前项目里的对应对象

- profile：
- 后端：
- 模型：
- 关键参数：

### 实测或文档证据

- 权重显存：
- KV cache：
- tok/s：
- 端到端延迟：
- 错误率：

### 我的初步理解

- 主要收益：
- 主要限制：
- 下一步要验证：
```

## 16. 参考资料

- vLLM INT8 W8A8 文档：`https://docs.vllm.ai/en/v0.18.1/features/quantization/int8/`
- SGLang Quantization 文档：`https://docs.sglang.ai/advanced_features/quantization.html`
- TensorRT-LLM Quantization 文档：`https://nvidia.github.io/TensorRT-LLM/latest/features/quantization.html`
- TensorRT-LLM FP8 Quantization Guide：`https://nvidia.github.io/TensorRT-LLM/performance/performance-tuning-guide/fp8-quantization.html`
- llama.cpp README：`https://github.com/ggml-org/llama.cpp`
- llama.cpp Tensor Encoding Schemes：`https://github.com/ggml-org/llama.cpp/wiki/Tensor-Encoding-Schemes`
- 当前项目模型格式知识库：`docs/knowledge/models-and-formats/model_format_conversion.md`
- 当前项目长上下文性能记录：`docs/knowledge/models-and-formats/model_context_performance.md`
