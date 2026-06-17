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

## 4. 各层详细展开

各层加速方法的深入内容已拆分到对应专题文档：

| 层级 | 详细文档 |
|---|---|
| 数值精度与权重量化 | [../optimization/quantization-deep-dive.md](../optimization/quantization-deep-dive.md) |
| 模型格式与运行生态 | [./model-format.md](./model-format.md) |
| GGUF 与 llama.cpp 生态 | [../../models-and-formats/gguf-llamacpp-deploy.md](../../models-and-formats/gguf-llamacpp-deploy.md) |
| KV cache 量化与长上下文 | [../performance/kv-cache.md](../performance/kv-cache.md) |
| Attention / GEMM Kernel | [./compute-primitives.md](./compute-primitives.md) |
| 调度、缓存与服务级优化 | [../serving/vllm-deep-dive.md](../serving/vllm-deep-dive.md) |
| Profiling 与 Kernel 分析 | [../performance/profiling-guide.md](../performance/profiling-guide.md) |

## 5. 当前 llmnode 项目里的落点

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

## 6. 初学者容易混淆的点

| 简化说法 | 更准确的说法 |
|---|---|
| GGUF 是量化算法 | GGUF 是格式，`Q4_K_M`/`IQ`/`UD` 才是量化编码 |
| AWQ/GPTQ 一定更快 | AWQ/GPTQ 解决”质量尽量不掉”，速度取决于 Kernel、反量化、batch、框架 |
| INT4 省权重就省一切 | 长上下文下 KV cache 可能是显存大头，权重变小不等于 256K 就快 |
| MTP 加速一切 | MTP 主要加速 decode，不主要加速 prefill |
| FP8 一定比 INT8 快 | 不同 GPU 架构支持不同，需要实测 |

## 7. 参考资料

- 量化深入：[../optimization/quantization-deep-dive.md](../optimization/quantization-deep-dive.md)
- 模型格式：[./model-format.md](./model-format.md)
- GGUF 部署：[../../models-and-formats/gguf-llamacpp-deploy.md](../../models-and-formats/gguf-llamacpp-deploy.md)
- KV cache：[../performance/kv-cache.md](../performance/kv-cache.md)
- GEMM 与 FlashAttention：[./compute-primitives.md](./compute-primitives.md)
- vLLM 机制：[../serving/vllm-deep-dive.md](../serving/vllm-deep-dive.md)
- Profiling 工具：[../performance/profiling-guide.md](../performance/profiling-guide.md)
- 学习路线：[../learning-log.md](../learning-log.md)
