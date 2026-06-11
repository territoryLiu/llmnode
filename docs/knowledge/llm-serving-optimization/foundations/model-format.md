# 大模型文件格式、量化格式与推理框架

> 文档定位：项目知识库中的 LLM serving 优化基础专题，不属于 `llmnode` 项目蓝图、契约或正式路线图。  
> 目标：把 `safetensors / GGUF / AWQ / GPTQ / FP8 / NVFP4 / vLLM / SGLang / llama.cpp` 放到正确层级里，说明常见大模型格式有什么不同，以及三类推理框架各自适合什么模型和场景。  
> 更新时间：2026-06-08。涉及框架支持状态时，以官方文档、当前镜像版本和本机实测为准。

## 1. 先拆清楚三层概念

很多刚进入 LLM Infra 的人，会把这些词混在一起：

```text
GGUF / safetensors / AWQ / GPTQ / FP8 / NVFP4 / vLLM / SGLang / llama.cpp
```

它们其实属于三层：

| 层级 | 解决的问题 | 典型对象 |
|---|---|---|
| 模型文件格式 | 权重和元数据怎么存到磁盘上 | `safetensors`、`GGUF`、`bin`、`pt`、`nemo`、TensorRT-LLM engine |
| 量化/精度格式 | 权重、激活、KV cache 用什么数值精度 | `BF16`、`FP16`、`FP8`、`INT8`、`INT4`、`AWQ`、`GPTQ`、`NVFP4`、`Q4_K_M` |
| 推理框架 | 谁来加载模型、调度请求、运行 kernel、提供 API | `vLLM`、`SGLang`、`llama.cpp`、TensorRT-LLM、Transformers |

一句话记忆：

```text
safetensors / GGUF = 权重装在哪种文件盒子里
AWQ / GPTQ / FP8 / INT4 / NVFP4 = 权重或激活怎么压缩
vLLM / SGLang / llama.cpp = 谁来运行这个模型
```

常见误区：

| 误区 | 更准确的说法 |
|---|---|
| GGUF 是一种量化算法 | GGUF 是文件格式，里面可以存 F16、Q4_K_M、Q5_K_M、Q8_0 等不同量化张量 |
| AWQ/GPTQ 是文件格式 | AWQ/GPTQ 是 weight-only 量化方法，常以 HF checkpoint + `safetensors` 形式发布 |
| FP8 一定更快 | 要看硬件。A800 上常是 weight-only fallback，H100/H200 才是 FP8 主场 |
| vLLM/SGLang 只看文件后缀 | 它们更关心模型架构、配置、量化元数据、kernel 支持和运行参数 |
| llama.cpp 只能 CPU | llama.cpp 可以用 CUDA/Metal/Vulkan/OpenCL 等后端，但主格式仍是 GGUF |

## 2. 常见模型文件格式

### 2.1 总览

| 格式 | 常见文件 | 主生态 | 适合场景 | 关键特点 |
|---|---|---|---|---|
| HuggingFace checkpoint | `config.json` + `*.safetensors` | HF / vLLM / SGLang / Transformers | 服务化推理、训练、微调、主流开源模型分发 | 目录式，配置、tokenizer、权重分开 |
| `safetensors` | `model-00001.safetensors` | HF / vLLM / SGLang | 安全加载、快速加载、大模型分片 | 只存张量，不执行 Python 代码 |
| PyTorch checkpoint | `pytorch_model.bin`、`*.pt` | 旧 HF / PyTorch | 旧模型、研究代码 | 兼容广，但安全性和加载体验弱于 safetensors |
| GGUF | `*.gguf` | llama.cpp / Ollama / LM Studio | 本地部署、低显存、CPU/GPU 混合推理 | 单文件，内含 metadata、tokenizer、量化张量 |
| GGML / GGJT | `*.ggml`、旧格式 | 旧 llama.cpp | 历史模型 | 已基本被 GGUF 替代 |
| TensorRT-LLM engine | `*.engine` 或 engine 目录 | TensorRT-LLM | NVIDIA 生产部署、固定 shape/优化 engine | 构建成本高，运行性能强 |
| NeMo checkpoint | `*.nemo` 或 NeMo 目录 | NVIDIA NeMo / Megatron | 训练和大规模微调 | 偏训练/企业生态 |
| ONNX | `*.onnx` | ONNX Runtime / OpenVINO | 跨框架部署，小模型更多 | LLM 服务化主流程度低于 HF/vLLM/llama.cpp |

当前 `llmnode` 最该关心两类：

1. `HF checkpoint + safetensors`：对应 vLLM / SGLang 主线。
2. `GGUF`：对应 llama.cpp 主线。

### 2.2 HuggingFace checkpoint

HF checkpoint 通常是一个目录，而不是单个权重文件。

典型结构：

```text
Qwen3.6-27B/
├── config.json
├── tokenizer.json
├── tokenizer_config.json
├── generation_config.json
├── model-00001-of-000xx.safetensors
├── model-00002-of-000xx.safetensors
└── model.safetensors.index.json
```

每类文件的作用：

| 文件 | 作用 |
|---|---|
| `config.json` | 模型结构配置，如层数、hidden size、attention heads、rope、max position 等 |
| `tokenizer.json` / `tokenizer.model` | tokenizer 本体 |
| `tokenizer_config.json` | tokenizer 配置和 chat template 相关信息 |
| `generation_config.json` | 默认生成参数 |
| `*.safetensors` | 权重张量 |
| `*.index.json` | 大模型分片索引，说明每个 tensor 在哪个分片里 |

优点：

- HuggingFace、Transformers、vLLM、SGLang 都以它为主流输入。
- 适合训练、微调、量化、服务化推理。
- 模型结构和 tokenizer 信息清楚，生态工具多。

缺点：

- 文件多，部署不如 GGUF 单文件简单。
- BF16/FP16 权重体积很大，例如 27B BF16 权重大约 50GB 级别。
- 不同量化模型的 `quantization_config`、kernel 和框架支持差异很大，需要实测。

### 2.3 safetensors

`safetensors` 是 HF 生态里常见的安全张量存储格式。

它解决的是：

```text
怎么安全、快速地保存和加载 tensor
```

它不解决的是：

```text
模型怎么推理
模型量化成什么精度
模型支持多长上下文
```

特点：

| 项 | 说明 |
|---|---|
| 安全性 | 不执行任意 Python pickle 代码 |
| 加载 | 支持快速读取和分片加载 |
| 内容 | 主要存 tensor，不负责完整运行逻辑 |
| 生态 | HF / Transformers / vLLM / SGLang 主流支持 |

注意：

- `safetensors` 可以存 BF16、FP16、FP8、AWQ、GPTQ、compressed-tensors 等不同权重。
- 看到 `.safetensors` 后缀，只能说明文件容器，不代表模型是原始精度还是量化模型。

### 2.4 PyTorch `.bin` / `.pt`

早期 HF 模型常见：

```text
pytorch_model.bin
```

或研究代码里的：

```text
model.pt
checkpoint.pt
```

特点：

- PyTorch 生态兼容性强。
- 旧模型和训练中间产物常见。
- 可能依赖 pickle，安全性和分发体验不如 safetensors。
- 在生产推理里，能转成 safetensors 通常更推荐转。

### 2.5 GGUF

GGUF 是 llama.cpp / ggml 生态的主力模型格式。它通常是单文件：

```text
Qwen3.6-35B-A3B-Q4_K_M.gguf
DeepSeek-R1-Q8_0.gguf
Llama-3.1-8B-Instruct-Q5_K_M.gguf
```

GGUF 文件通常包含：

- 模型张量
- 模型 metadata
- tokenizer 信息
- 架构标识
- 上下文、rope、特殊 token 等配置
- 每个 tensor 的量化类型

优点：

- 单文件部署，非常适合本地推理。
- 支持大量 llama.cpp 量化类型，如 `Q4_K_M`、`Q5_K_M`、`Q8_0`、`IQ` 等。
- 支持 mmap，CPU/内存友好。
- 适合 CPU、Mac、消费级 GPU、低显存机器、边缘设备。

缺点：

- 主生态是 llama.cpp / Ollama / LM Studio，不是 vLLM/SGLang 的主路线。
- 新模型结构需要 llama.cpp 先支持，不能保证所有 HF 模型都能直接转换后正确跑。
- 服务化高并发、复杂调度、多 GPU 并行通常不如 vLLM/SGLang 主线成熟。

重点：

> GGUF 是格式，不是量化算法。`Q4_K_M`、`Q5_K_M`、`Q8_0` 才是 GGUF 里常见的量化类型。

### 2.6 TensorRT-LLM engine

TensorRT-LLM 的核心路径通常不是直接把 HF 目录丢进去跑，而是经过转换、构建 engine，再部署。

特点：

| 项 | 说明 |
|---|---|
| 优势 | NVIDIA GPU 上性能强，适合生产优化 |
| 代价 | 构建流程复杂，engine 和硬件/shape/版本绑定更强 |
| 适合 | 固定模型、固定硬件、追求极致吞吐和延迟 |
| 不适合 | 学习初期频繁换模型、换上下文、换量化方案 |

当前 `llmnode` 的三后端路线是 `vLLM / llama.cpp / SGLang`，TensorRT-LLM 可以作为后续扩展，不是当前主线。

## 3. 常见量化和精度格式

### 3.1 总览

| 名词 | 层级 | 常见载体 | 一句话解释 | 主要收益 |
|---|---|---|---|---|
| BF16 / FP16 | 精度 | HF / safetensors / GGUF | 半精度基线 | 精度稳、kernel 成熟 |
| FP8 | 精度/量化 | HF / safetensors / compressed-tensors | 8-bit 浮点，可用于权重/激活/KV | 新 GPU 上吞吐和显存收益 |
| INT8 / W8A8 | 量化 | HF / safetensors | 权重和激活都 8-bit | 计算和显存都可能受益 |
| INT4 / W4A16 | 量化 | AWQ/GPTQ/GGUF | 权重 4-bit，激活仍 16-bit | 显著省权重显存 |
| AWQ | 量化方法 | HF checkpoint / safetensors | Activation-aware weight quantization | INT4 常用，精度较稳 |
| GPTQ | 量化方法 | HF checkpoint / safetensors | 二阶近似 PTQ | 旧生态广，模型覆盖多 |
| Marlin | kernel 路径 | vLLM / SGLang 等 | 低比特 GEMM kernel | 让 AWQ/GPTQ/FP8 等更快 |
| NVFP4 / FP4 | 低比特浮点 | 新 GPU / 特定框架路径 | 4-bit 浮点方向 | 新架构低精度推理 |
| Q4_K_M / Q5_K_M / Q8_0 | GGUF 量化类型 | GGUF | llama.cpp 常用量化 | 本地部署显存/质量折中 |

### 3.2 BF16 / FP16

这是服务化推理的常见基线。

优点：

- 兼容性强。
- 精度稳定。
- 在 A800 上 BF16/FP16 Tensor Core 路径成熟。

缺点：

- 权重显存高。
- 长上下文下留给 KV cache 的空间少。

当前 Qwen3.6-27B 第一阶段里，BF16 是速度上限参考，但不是 256K 主候选。

### 3.3 FP8

FP8 是 8-bit 浮点。它可以用于：

- 权重
- 激活
- KV cache

但实际收益强烈依赖硬件和框架。

在 Hopper / H100 / H200 上，FP8 更接近主场。  
在 A800 / Ampere 上，vLLM 常见的是 `W8A16 weight-only FP8 + Marlin` fallback，不是完整 `W8A8 FP8 Tensor Core` 路径。

因此：

| 硬件 | FP8 判断 |
|---|---|
| A800 / A100 | 可以省权重显存，但速度不一定好 |
| H100 / H200 | 值得重点评估 |
| B200 / GB200 | 需要重新评估 FP8 / FP4 / NVFP4 的组合 |

### 3.4 AWQ

AWQ 是 Activation-aware Weight Quantization，属于 weight-only 量化方法。常见形态是 INT4 / W4A16：

```text
weights: INT4
activations: FP16/BF16
```

优点：

- 显存节省明显。
- 4-bit 权重量化里精度通常较稳。
- vLLM / SGLang 对 AWQ 有常见支持路径。

风险：

- 不保证一定更快。
- 速度取决于 Marlin、Machete 或具体框架 kernel。
- 长上下文时，瓶颈可能转移到 prefill、attention、KV cache。

当前 A800 + Qwen3.6-27B 结论：

> AWQ-INT4 是显存效率冠军，值得继续做并发和上下文阶梯实验。

### 3.5 GPTQ

GPTQ 也是成熟的 weight-only PTQ 方法。它用近似二阶信息降低量化误差。

特点：

- 生态时间较长。
- 模型覆盖广。
- 常见于 HF 社区量化模型。
- 能否快取决于 `gptq_marlin` 等 kernel 路径。

和 AWQ 的关系：

| 项 | AWQ | GPTQ |
|---|---|---|
| 思路 | 保护激活敏感的重要权重 | 二阶近似 PTQ |
| 常见位宽 | INT4 | INT4 |
| 生态 | 新模型官方量化常见 | 老社区模型覆盖多 |
| 速度 | 取决于 kernel | 取决于 kernel |

### 3.6 NVFP4 / FP4

NVFP4 / FP4 是更激进的 4-bit 浮点方向。它更偏新 GPU 和新框架路径。

注意：

- 不是看到 `4-bit` 就一定比 AWQ/GPTQ 快。
- A800 不是 NVFP4 的理想硬件主场。
- 当前结果应按“当前 vLLM + 当前模型 + 当前 kernel 路径”理解。

当前第一阶段里，NVFP4 与 AWQ-INT4 的 16K/64K 速度接近，不能过度解读 `2.19 vs 2.13 tok/s`。

### 3.7 GGUF 量化类型

GGUF 生态里常见的是：

| 类型 | 大致定位 |
|---|---|
| `F16` / `BF16` | 高精度，文件大 |
| `Q8_0` | 接近高质量，体积约半精度的一半左右 |
| `Q6_K` | 高质量量化，体积仍较大 |
| `Q5_K_M` | 质量和体积折中偏质量 |
| `Q4_K_M` | 本地部署常用平衡点 |
| `Q3_K_M` / `Q3_K_S` | 更省空间，质量风险更大 |
| `IQ` 系列 | 更细的低比特量化路线，需按模型实测 |

常见经验：

- 本地聊天：`Q4_K_M` 常是起点。
- 更重视质量：试 `Q5_K_M` / `Q6_K` / `Q8_0`。
- 显存极紧：试 `Q3` / `IQ`，但必须做质量回归。

## 4. 三个推理框架支持什么

### 4.1 总览矩阵

| 维度 | vLLM | SGLang | llama.cpp |
|---|---|---|---|
| 主格式 | HF checkpoint / safetensors | HF checkpoint / safetensors | GGUF |
| API 风格 | OpenAI-compatible server | OpenAI-compatible server + SGLang runtime | llama-server OpenAI-like API / CLI |
| 核心优势 | 高吞吐服务、PagedAttention、continuous batching、生产生态 | RadixAttention、prefix caching、Agent/结构化输出、PD 分离、快速迭代 | 本地部署、低显存、CPU/GPU 混合、跨平台、GGUF 生态 |
| 常见模型 | Llama、Qwen、DeepSeek、GLM、Mistral、Gemma、VLM、embedding 等，按官方支持表为准 | Llama、Qwen、DeepSeek、Kimi、GLM、Gemma、Mistral、VLM、embedding/reward/diffusion 等，按官方支持表为准 | Llama、Qwen、Mistral、Gemma、Phi、DeepSeek distill、GLM 等，取决于 llama.cpp 架构支持 |
| 常见量化 | AWQ、GPTQ、FP8、INT8、bitsandbytes、compressed-tensors、GGUF 等，支持状态随版本变 | AWQ、GPTQ、FP8、INT4、torchao、GGUF 等，支持状态随版本变 | GGUF 内置量化，如 Q4_K_M、Q5_K_M、Q8_0、IQ 等 |
| 多 GPU / 分布式 | 强 | 强，尤其服务化和 PD/EP 方向活跃 | 有 GPU offload 和多 GPU 能力，但主战场不是大规模服务化 |
| 长上下文 | 强，KV 管理成熟 | 强，RadixAttention/prefix caching 方向突出 | 能跑长上下文，但速度和显存取决于 GGUF、后端和参数 |
| 本地低显存 | 可以，但依赖模型和量化 | 可以，但不是最轻路线 | 最强 |
| 生产高并发 API | 强 | 强 | 可用，但通常不是首选 |

### 4.2 vLLM

vLLM 的定位：

> 面向在线服务和高吞吐推理的 LLM serving 框架。

它的核心能力：

- PagedAttention / KV cache 管理
- continuous batching
- prefix caching
- chunked prefill
- speculative decoding
- OpenAI-compatible API server
- 多 GPU 并行
- 多种量化路径
- VLM、embedding、reward model 等扩展支持

vLLM 主要吃什么模型：

| 模型形态 | 支持情况 |
|---|---|
| HF BF16/FP16 checkpoint | 主流支持 |
| HF safetensors 分片模型 | 主流支持 |
| AWQ / GPTQ | 常见支持路径 |
| FP8 / compressed-tensors | 支持，但硬件和版本影响很大 |
| bitsandbytes | 支持部分路径 |
| GGUF | vLLM 文档有量化支持项，但不是它的主路线；遇到复杂模型或新 GGUF 量化应优先实测 |
| TensorRT-LLM engine | 不是 vLLM 的主输入格式 |

适合 vLLM 的场景：

- 生产 API 服务
- 多用户并发
- 多 GPU
- 需要 OpenAI API 兼容
- 需要服务化监控、调度、吞吐
- HF checkpoint 生态模型

不太适合：

- 极低显存本地聊天
- 想直接跑各种社区 GGUF
- 只想一个二进制快速离线体验

当前 `llmnode` 里的 vLLM 角色：

- 正式默认主后端。
- Qwen3.6-27B / 35B-A3B 的 FP8、NVFP4、AWQ、BF16 profile 都主要走 vLLM。
- 当前 A800 上，FP8 要按 fallback 路径理解，AWQ/NVFP4 更值得继续实测。

### 4.3 SGLang

SGLang 的定位：

> 面向高性能 serving、结构化生成、Agent 场景和长上下文复用的推理框架。

它的核心能力：

- RadixAttention / prefix caching
- zero-overhead CPU scheduler
- continuous batching
- chunked prefill
- speculative decoding
- prefill-decode disaggregation
- tensor / pipeline / expert / data parallel
- structured outputs
- multi-LoRA batching
- OpenAI-compatible API

SGLang 主要吃什么模型：

| 模型形态 | 支持情况 |
|---|---|
| HF BF16/FP16 checkpoint | 主流支持 |
| HF safetensors 分片模型 | 主流支持 |
| AWQ / GPTQ | 文档列为常见支持方向，具体看版本和模型 |
| FP8 / INT4 / torchao 等 | 支持路径活跃，版本变化快 |
| GGUF | 文档中有支持项，但不是最核心主路线；复杂模型建议实测 |
| VLM / embedding / reward / diffusion | SGLang 支持范围扩展较快，按官方支持表确认 |

适合 SGLang 的场景：

- Agent / tool calling / structured output
- 有大量共享前缀的 workload
- 长上下文、多轮对话、prefix cache 命中高
- 想测试 PD 分离、EP、MoE 服务化路径
- 想对比 vLLM 的调度和缓存策略

不太适合：

- 只想最简单跑一个 GGUF 文件。
- 不愿跟随较快变化的版本和参数。

当前 `llmnode` 里的 SGLang 角色：

- 第三候选后端。
- 适合作为 vLLM 的服务化对照。
- 对 Qwen reasoning parser、structured output、prefix cache、PD 分离等方向值得继续验证。

### 4.4 llama.cpp

llama.cpp 的定位：

> 面向本地部署、低显存、跨平台和 GGUF 生态的轻量推理框架。

它的核心能力：

- GGUF 原生支持
- CPU 推理强
- GPU offload
- CUDA / Metal / Vulkan / OpenCL 等多后端
- mmap 加载
- 量化类型非常丰富
- 单二进制和轻量 server 体验好
- 支持本地聊天、边缘部署、开发测试

llama.cpp 主要吃什么模型：

| 模型形态 | 支持情况 |
|---|---|
| GGUF | 主流、原生 |
| HF safetensors | 通常需要先转换为 GGUF |
| Q4_K_M / Q5_K_M / Q8_0 / IQ 等 | 主流 |
| AWQ / GPTQ HF checkpoint | 不是直接主路线，通常走转换或另找 GGUF 版本 |
| FP8 / NVFP4 | 要看 GGUF/ggml 是否已有对应量化类型和后端支持，不能按 vLLM 逻辑套用 |

适合 llama.cpp 的场景：

- 本地聊天
- 单用户低延迟体验
- Mac / Windows / Linux / CPU / 消费级 GPU
- 低显存部署
- 快速试模型
- GGUF 社区模型

不太适合：

- 大规模生产 API 高并发
- 多机多卡高吞吐服务
- 需要和 HF/vLLM 的复杂量化元数据完全对齐

当前 `llmnode` 里的 llama.cpp 角色：

- 第二后端。
- 适合验证 GGUF / Q4_K_M / Q5_K_M / MTP / speculative 等本地部署路线。
- 和 vLLM 的对比重点不应只看 tok/s，还要看显存、部署复杂度、并发、长上下文稳定性。

## 5. 三后端怎么选

### 5.1 按模型文件选

| 你手里的模型 | 优先框架 |
|---|---|
| HF 目录 + `*.safetensors` | vLLM / SGLang |
| 官方 AWQ / GPTQ / FP8 HF checkpoint | vLLM / SGLang，先查量化支持 |
| 单个 `*.gguf` | llama.cpp |
| GGUF Q4_K_M / Q5_K_M / Q8_0 | llama.cpp |
| TensorRT-LLM engine | TensorRT-LLM |
| 旧 `pytorch_model.bin` | 先尝试 Transformers/vLLM，必要时转 safetensors |

### 5.2 按部署目标选

| 目标 | 优先选择 | 原因 |
|---|---|---|
| 生产 OpenAI API 服务 | vLLM | 生态成熟，吞吐和调度强 |
| Agent / 结构化输出 / 前缀复用 | SGLang | RadixAttention、structured output、runtime 设计更贴近这类 workload |
| 本地聊天 / 低显存 / 单文件部署 | llama.cpp | GGUF 生态和跨平台体验最好 |
| A800 上跑 Qwen3.6-27B 长上下文 | vLLM + AWQ/NVFP4 | 当前已有实测基础 |
| 对比 GGUF 本地路线 | llama.cpp + Q4_K_M/Q5_K_M | 适合作为第四阶段方向 |
| 极致 NVIDIA 生产优化 | TensorRT-LLM | 构建复杂，但性能上限高 |

### 5.3 按硬件选

| 硬件 | 倾向 |
|---|---|
| A800 / A100 | BF16、AWQ/GPTQ INT4、INT8；FP8 只做对照或容量测试 |
| H100 / H200 | FP8 值得重点评估，vLLM/SGLang/TensorRT-LLM 都值得测 |
| B200 / GB200 | FP4 / NVFP4 / FP8 都要重新评估 |
| Mac / CPU / 消费级 GPU | llama.cpp + GGUF 优先 |
| 低显存单卡 | GGUF 或 AWQ/GPTQ，视目标框架决定 |

## 6. 当前 llmnode 项目里的落点

当前项目已经覆盖三条路线：

| 路线 | 当前代表 |
|---|---|
| vLLM + HF/safetensors | `Qwen3.6-27B`、`Qwen3.6-27B-FP8`、`Qwen3.6-27B-NVFP4`、`Qwen3.6-27B-AWQ-INT4` |
| SGLang + HF/safetensors | `Qwen3.6-35B-A3B-FP8` 等服务化候选 |
| llama.cpp + GGUF | `Qwen3.6-35B-A3B-GGUF/qwen36-35b-a3b-q4km.gguf` |

当前学习优先级：

1. 继续用 vLLM 做第二阶段实验：拉长输出、拆 prefill/decode、测 AWQ/NVFP4。
2. 用 SGLang 对照 vLLM 的 prefix cache、structured output、reasoning parser、PD 分离方向。
3. 用 llama.cpp 作为 GGUF / 本地部署路线，不要和 vLLM 的服务化吞吐直接混为一个问题。

## 7. 常见问题

### 7.1 safetensors 能不能直接给 llama.cpp 跑

通常不直接跑。llama.cpp 主路线是 GGUF。HF/safetensors 模型一般需要先转换成 GGUF，再用 llama.cpp 加载。

### 7.2 GGUF 能不能给 vLLM 跑

vLLM 文档里有 GGUF 量化相关支持项，但它不是 vLLM 的主路线。复杂模型、VLM、新量化类型或社区 GGUF，建议优先用 llama.cpp。若要用 vLLM 跑 GGUF，必须按当前 vLLM 版本实测，不要默认可用。

### 7.3 AWQ 和 GGUF 是不是一类东西

不是。

```text
AWQ = 权重量化方法
GGUF = 文件格式
```

一个 AWQ 模型通常是 HF checkpoint；一个 GGUF 模型可能是 Q4_K_M、Q5_K_M、Q8_0，也可能是 F16。

### 7.4 FP8 和 GGUF Q8_0 是不是一样

不是。

`FP8` 是 8-bit 浮点，常见于新 GPU Tensor Core 路线。  
`Q8_0` 是 llama.cpp / GGUF 生态里的 8-bit 量化类型，运行路径和 kernel 完全不同。

### 7.5 为什么同样是 INT4，有的快，有的不快

因为 INT4 只是位宽，不代表完整运行路径。真实速度取决于：

- 权重布局
- 反量化成本
- GEMM kernel
- GPU 架构
- batch / sequence shape
- prefill 和 decode 占比
- KV cache 是否成为瓶颈

### 7.6 模型格式和 chat template 有什么关系

HF 目录通常有 `tokenizer_config.json`、`chat_template` 等信息。GGUF 也可能把 tokenizer 和模板信息写进 metadata。  
但是不同框架对 chat template、reasoning parser、tool call parser 的处理不完全一致。比如 Qwen reasoning 内容是否正确分离，不只看模型文件，还要看框架参数。

## 8. 建议记忆版

```text
HF checkpoint + safetensors = 服务化主流格式
GGUF = 本地部署主流格式

AWQ / GPTQ = INT4 weight-only 量化方法
FP8 = 新 GPU 低精度方向，A800 上要谨慎
NVFP4 / FP4 = 更偏新架构的 4-bit 浮点方向
Q4_K_M / Q5_K_M / Q8_0 = GGUF 生态量化类型

vLLM = 生产 API / 高吞吐 / HF 主线
SGLang = Agent / 结构化输出 / 前缀复用 / 服务化新路线
llama.cpp = GGUF / 本地部署 / 低显存 / 跨平台
```

当前 A800 + Qwen3.6-27B 的学习主线：

```text
先用 vLLM + AWQ/NVFP4 做长上下文和并发基线，
再用 SGLang 对照调度和 prefix cache，
最后用 llama.cpp/GGUF 做本地部署路线对比。
```

## 9. 参考资料

- Hugging Face Transformers GGUF 文档：<https://huggingface.co/docs/transformers/gguf>
- vLLM Quantization 文档：<https://docs.vllm.ai/en/stable/features/quantization/index.html>
- SGLang Quantization 文档：<https://docs.sglang.io/advanced_features/quantization.html>
- SGLang 项目介绍与支持能力：<https://sgl-project.github.io/>
- GGML GGUF 格式说明：<https://github.com/ggml-org/ggml/blob/master/docs/gguf.md>
- llama.cpp Docker / 工具说明：<https://github.com/ggml-org/llama.cpp/blob/master/docs/docker.md>
- 当前硬件背景：[hardware.md](./hardware.md)
- 当前加速方法地图：[accel-map.md](./accel-map.md)
