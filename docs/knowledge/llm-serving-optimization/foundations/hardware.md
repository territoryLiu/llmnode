# 主流 AI 硬件与精度速查

> 文档定位：项目知识库中的 LLM serving 优化基础专题，不属于 `llmnode` 项目蓝图、契约或正式路线图。  
> 使用方式：帮助理解大模型部署时不同 GPU / AI 加速器的显存、带宽、精度支持和框架生态差异。当前本机 A800 只是其中一个案例。  
> 注意：硬件规格、出口限制、云厂商 SKU、框架支持都会变化。部署前以 `nvidia-smi`、框架启动日志、官方规格页和本机实测为准。

## 1. 最重要结论

对 LLM 部署优化来说，硬件不要只看 “TFLOPS”。更重要的是：

```text
显存容量
显存带宽
低精度 Tensor Core / Matrix Core 路径
KV cache 容量
多卡互联
软件生态
```

粗略记忆：

| 硬件代际 | 代表卡 | LLM 部署关键词 |
|---|---|---|
| NVIDIA Ampere | A100 / A800 | BF16/FP16/INT8/INT4 成熟，FP8 不是原生主场 |
| NVIDIA Ada | L40S / RTX 6000 Ada / RTX 4090 | FP8 路径可用性比 Ampere 好，但显存和带宽不如 H100/H200 |
| NVIDIA Hopper | H100 / H200 / H800 / H20 | FP8 主场，Transformer Engine，H200 显存更适合长上下文 |
| NVIDIA Blackwell | B200 / GB200 / B300 | FP4/FP8 主场，MoE 和推理吞吐重点方向 |
| AMD CDNA 3 | MI300X / MI325X | 大显存和高带宽强，ROCm 生态要单独验证 |
| 云厂商自研 | TPU / Trainium / Maia 等 | 云内生态强，本地 llmnode 路线通常不直接覆盖 |

当前 `llmnode` 的本机实验仍按 A800 / Ampere 理解：

```text
A800 + Qwen3.6-27B + vLLM + 单并发长上下文

量化价值优先级：
显存容量 > 上下文容量 > 并发能力 > 速度
```

## 2. 主流硬件总览

| 厂商 | 代表硬件 | 显存级别 | 低精度主线 | 软件生态 | 适合场景 |
|---|---|---:|---|---|---|
| NVIDIA | A100 / A800 | 40GB / 80GB HBM2e | BF16、FP16、TF32、INT8、INT4 | CUDA、vLLM、SGLang、TensorRT-LLM 最成熟 | 成熟部署、训练、推理、教学实验 |
| NVIDIA | L40S / RTX 6000 Ada | 48GB GDDR6 | FP8、FP16、INT8 | CUDA，数据中心 PCIe 推理 | 中小模型推理、图形+AI 混合 |
| NVIDIA | RTX 4090 / 5090 等消费卡 | 24GB / 32GB 级别 | FP16、FP8/FP4 视架构而定 | CUDA 生态好，但服务化限制多 | 本地开发、原型、低成本实验 |
| NVIDIA | H100 / H800 | 80GB HBM3 | FP8、BF16、FP16、INT8 | CUDA 主线，Transformer Engine | 大模型训练、高吞吐推理 |
| NVIDIA | H200 | 141GB HBM3e | FP8、BF16、FP16、INT8 | CUDA 主线 | 长上下文、RAG、大 batch 推理 |
| NVIDIA | H20 | 96GB HBM3 级别 | Hopper 低精度能力但规格受限 | CUDA 主线 | 受限市场里的 Hopper 路线，需实测 |
| NVIDIA | B200 / GB200 | 192GB HBM3e 级别 | FP4、FP8、FP6、INT8 | CUDA / TensorRT-LLM 新主线 | 新一代推理、MoE、超大模型 |
| AMD | MI300X | 192GB HBM3 | BF16、FP16、FP8、INT8 | ROCm、vLLM/SGLang 支持需按版本验证 | 大显存推理、训练、开源生态替代 |
| AMD | MI325X / MI350 系列 | 256GB / 144GB+ 级别 | FP8、FP16、BF16、MXFP4 等新路线 | ROCm 快速演进 | 大显存和新低精度方向，需实测 |
| Google | TPU v5 / v6 系列 | 云内规格 | BF16、INT8 等 | XLA / JAX / TensorFlow / PyTorch-XLA | Google Cloud 内训练和推理 |
| AWS | Trainium / Inferentia | 云内规格 | BF16、FP8 等视代际 | Neuron SDK | AWS 内成本优化 |

表里的非本机硬件是部署选型参考，不代表当前 `llmnode` 已经支持或验证。

## 3. NVIDIA 架构对比

### 3.1 架构总览

| 架构 | 代表卡 | 低精度特点 | 对 LLM 的意义 |
|---|---|---|---|
| Volta | V100 | FP16 Tensor Core | 旧训练卡，现代 LLM 推理不再是主力 |
| Turing | T4 | INT8 推理成熟 | 老推理卡，适合小模型和传统推理 |
| Ampere | A100 / A800 | BF16、TF32、INT8、INT4 成熟 | 当前很多存量集群主力 |
| Ada | L40S / RTX 6000 Ada / RTX 4090 | FP8 Tensor Core 路线可用，GDDR 显存 | 中小模型推理和本地开发 |
| Hopper | H100 / H200 | FP8 Transformer Engine | FP8 LLM 训练/推理主场 |
| Blackwell | B200 / GB200 / B300 | FP4/FP8、第五代 Tensor Core | 新一代低精度推理和 MoE 主场 |

### 3.2 A100 / A800

| 项 | A100 / A800 重点 |
|---|---|
| 架构 | Ampere |
| 显存 | 40GB / 80GB HBM2e，A100 80GB 官方页标注超过 2TB/s 带宽 |
| 精度主线 | BF16、FP16、TF32、INT8、INT4 |
| FP8 | 不是 Hopper 式原生 W8A8 FP8 Tensor Core 主场 |
| 优势 | 存量多、CUDA 生态成熟、训练和推理都稳 |
| 短板 | 长上下文大模型容易受显存和 KV cache 限制；FP8 不占主场 |

A800 可以理解为 A100 的受限版本之一，常见差异集中在互联/出口合规相关规格。对单卡 LLM 推理，最重要的是它仍属于 Ampere 路线。

当前本机结论：

- BF16 快是合理的。
- FP8 慢于 BF16/AWQ/NVFP4 不奇怪。
- AWQ-INT4 的价值主要是省权重显存，给 KV cache 和上下文容量让路。

### 3.3 L40S / RTX Ada

| 项 | Ada 重点 |
|---|---|
| 代表 | L40S、RTX 6000 Ada、RTX 4090 |
| 显存 | L40S/RTX 6000 Ada 常见 48GB，RTX 4090 常见 24GB |
| 显存类型 | GDDR，不是 HBM |
| 精度 | FP8 Tensor Core 路线比 Ampere 更有意义 |
| 优势 | 成本相对低、CUDA 生态好、适合中小模型和推理 |
| 短板 | 显存容量和带宽不如 H100/H200，长上下文大模型受限 |

适合：

- 7B/14B/32B 级模型开发和部署。
- 本地或中小规模服务。
- 不追求 256K 超长上下文和高并发的场景。

### 3.4 H100 / H800 / H200 / H20

| 项 | Hopper 重点 |
|---|---|
| 代表 | H100、H800、H200、H20 |
| 显存 | H100 常见 80GB HBM3；H200 官方标注 141GB HBM3e、4.8TB/s |
| 精度 | FP8 是核心能力之一 |
| 特性 | Transformer Engine、NVLink/NVSwitch、多实例和高带宽 |
| 优势 | FP8 训练/推理、高吞吐服务、长上下文比 A100/A800 更友好 |
| 短板 | 成本高，供应和合规限制多 |

H100/H200 的关键差异：

- H100 是 Hopper 主力训练/推理卡。
- H200 在 HBM 容量和带宽上更适合长上下文、RAG、大 batch 推理。
- 如果第一阶段 A800 上 FP8 不理想，不能外推到 H100/H200。

H20/H800 属于受限市场常见 SKU，具体性能、互联和部署限制必须按实际机器验证。

### 3.5 B200 / GB200 / B300

| 项 | Blackwell 重点 |
|---|---|
| 代表 | B200、GB200、B300 / Blackwell Ultra |
| 显存 | B200 级别通常围绕 192GB HBM3e；Blackwell Ultra 可到更高容量 |
| 精度 | FP4、FP8、FP6、INT8 是主线 |
| 特性 | 第五代 Tensor Core、NVLink 5、MoE 和大规模推理优化 |
| 优势 | 新一代低精度推理、MoE、超大模型、高吞吐 |
| 短板 | 新硬件、新软件栈，部署成本和版本约束更高 |

对当前学习的意义：

- NVFP4 / FP4 的真正主场更偏 Blackwell。
- A800 上的 NVFP4 实测不能直接外推到 B200/GB200。
- 如果未来有 Blackwell 机器，第一优先级应重测 FP4/NVFP4、FP8、KV cache dtype 和 MoE serving。

## 4. AMD Instinct 路线

### 4.1 MI300X

| 项 | MI300X 重点 |
|---|---|
| 架构 | AMD CDNA 3 |
| 显存 | AMD 官方资料标注 192GB HBM3 |
| 带宽 | AMD 官方资料标注 5.3TB/s 峰值带宽 |
| 精度 | BF16、FP16、FP8、INT8 等矩阵能力 |
| 软件 | ROCm、HIP、Triton、vLLM/SGLang 支持随版本快速变化 |
| 优势 | 单卡大显存强，适合长上下文和大模型容量型场景 |
| 短板 | CUDA 生态之外，kernel、框架、镜像和算子支持需要更仔细验证 |

MI300X 的学习意义：

- 它不是 CUDA 路线，但大显存让它在长上下文推理上很有吸引力。
- 对比 NVIDIA 时，不能只看峰值算力，要看 ROCm 下目标框架是否跑通、kernel 是否成熟。

### 4.2 MI325X / MI350 系列

这些是 AMD 后续大显存/新低精度方向。常见讨论点包括更大 HBM 容量、HBM3E、更高带宽、FP8/MXFP4 等。

建议写法：

> 作为路线关注，具体部署前查官方规格和目标框架支持，不把网络资料里的单一峰值当成结论。

## 5. 云厂商自研芯片

| 硬件 | 生态 | 适合场景 | 对当前 llmnode 的意义 |
|---|---|---|---|
| Google TPU | XLA、JAX、TensorFlow、PyTorch-XLA | 云上训练和推理 | 不属于当前 Docker 三后端主线 |
| AWS Trainium / Inferentia | Neuron SDK | AWS 内成本优化 | 需要专门适配，不直接复用 CUDA/ROCm 经验 |
| Microsoft Maia | Azure 内部/云生态 | Azure AI workload | 更多是云平台路线 |

这些硬件很重要，但学习方式和本地 `vLLM / SGLang / llama.cpp` 不同。当前阶段可以先知道它们存在，不作为实验主线。

## 6. 精度格式与硬件关系

| 精度/量化 | Ampere A100/A800 | Ada L40S/RTX | Hopper H100/H200 | Blackwell B200/GB200 | AMD MI300X |
|---|---|---|---|---|---|
| BF16 / FP16 | 强 | 强 | 强 | 强 | 强 |
| TF32 | 强 | 强 | 强 | 强 | AMD 路线不同，需按 ROCm/框架看 |
| FP8 W8A8 | 不是主场 | 可评估 | 主场 | 主场 | 支持方向，需按 ROCm 实测 |
| FP8 W8A16 | 常见 fallback | 可用但需实测 | 可用 | 可用 | 视框架 |
| INT8 | 强 | 强 | 强 | 强 | 强 |
| INT4 weight-only | 可用，常配 Marlin 等 | 可用 | 可用 | 可用 | 视框架/kernel |
| FP4 / NVFP4 | 不是主场 | 不是主场 | 不是主场 | 主场 | AMD 有 MXFP4 等不同路线 |
| KV cache FP8 | 可试，容量方向 | 可试 | 值得测 | 值得测 | 值得测但要看框架 |

硬件判断原则：

```text
同一个量化名字，在不同硬件上可能是完全不同的 kernel 路径。
```

例如：

- A800 上 FP8 可能是 weight-only fallback。
- H100/H200 上 FP8 才更接近原生主线。
- B200/GB200 上 FP4/NVFP4 才更值得重测。
- MI300X 上要看 ROCm/vLLM/SGLang 当前版本。

## 7. LLM 部署选型建议

### 7.1 按模型规模

| 模型规模 | 常见硬件选择 | 说明 |
|---|---|---|
| 7B / 14B | L40S、RTX 4090/5090、A10/A100、MI 系列 | 本地和中小服务都可 |
| 27B / 32B / 35B | A100/A800 80GB、L40S 48GB 量化、H100/H200、MI300X | 长上下文需要看 KV cache |
| 70B / 72B | H100/H200、A100 多卡、MI300X、B200 | 单卡可行性取决于量化和上下文 |
| 100B+ / MoE | H100/H200 多卡、B200/GB200、MI300X 集群 | 并行、通信和调度成为主问题 |

### 7.2 按部署目标

| 目标 | 硬件倾向 | 原因 |
|---|---|---|
| 低成本开发 | RTX 4090/5090、L40S、A100 存量 | 成本和生态平衡 |
| 长上下文单卡 | H200、MI300X、B200 | 显存容量和带宽更重要 |
| FP8 高吞吐 | H100/H200/B200 | FP8 原生路径 |
| FP4/NVFP4 新低精度 | B200/GB200 | Blackwell 主场 |
| 存量集群优化 | A100/A800 | 重点看 BF16、AWQ/GPTQ、KV cache |
| 本地 GGUF | 消费级 NVIDIA、Apple Silicon、CPU | llama.cpp 生态 |

## 8. 当前 A800 实验解释

当前机器按 A800 / Ampere 路线理解。对本项目的 Qwen3.6-27B 实验：

1. A800 原生强项是 `BF16 / FP16 / TF32 / INT8 / INT4`。
2. A800 不支持 Hopper 那种原生 `W8A8 FP8 Tensor Core` 路径。
3. vLLM 在 A800 上加载 FP8 权重时，常见路径是 `W8A16 weight-only FP8 + Marlin`，不是完整 FP8 计算加速。
4. FP4 / NVFP4 更偏新 GPU 方向，在 A800 上要按具体 vLLM kernel 路径和实测结果理解，不能只凭“4-bit”判断一定更快。
5. 长上下文下，量化的主要价值经常不是速度，而是权重显存下降后给 KV cache、上下文长度和并发余量让路。

第一阶段关键现象：

| profile | weight memory | KV memory | 硬件解释 |
|---|---:|---:|---|
| `BF16` | `51.1 GiB` | `14.13 GiB` | BF16 路径成熟，速度快，但权重太大 |
| `FP8` | `28.87 GiB` | `20.5 GiB` | 权重下降，但 A800 上 FP8 fallback 速度不占优 |
| `NVFP4` | `24.05 GiB` | `17.38 GiB` | 软件路径可用，256K 单请求边界贴边 |
| `AWQ-INT4` | `19.05 GiB` | `22.38 GiB` | 显存效率最好，适合继续测容量和并发 |

## 9. 本机验证命令

用下面命令确认实际 GPU、驱动、显存和进程占用：

```bash
nvidia-smi
nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,memory.free --format=csv
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
```

用 Python 确认 PyTorch 看到的设备：

```bash
/home/heshan/.conda/envs/paper2any/bin/python - <<'PY'
import torch

print("cuda_available:", torch.cuda.is_available())
if torch.cuda.is_available():
    idx = torch.cuda.current_device()
    props = torch.cuda.get_device_properties(idx)
    print("name:", props.name)
    print("compute capability:", f"{props.major}.{props.minor}")
    print("total_memory_gib:", props.total_memory / 1024**3)
PY
```

用 vLLM 启动日志确认真实精度路径：

```bash
docker logs <container_name> 2>&1 | rg -n "FP8|Marlin|quantization|Model loading took|Available KV cache memory|GPU KV cache size|Maximum concurrency"
```

## 10. 参考资料

- NVIDIA A100 官方页面：<https://www.nvidia.com/en-us/data-center/a100/>
- NVIDIA A100 数据表：<https://www.nvidia.com/content/dam/en-zz/Solutions/Data-Center/a100/pdf/nvidia-a100-datasheet-nvidia-us-2188504-web.pdf>
- NVIDIA H200 官方页面：<https://www.nvidia.com/en-us/data-center/h200/>
- NVIDIA Blackwell 架构页面：<https://www.nvidia.com/en-us/data-center/technologies/blackwell-architecture/>
- NVIDIA DGX B200 官方页面：<https://www.nvidia.com/en-us/data-center/dgx-b200/>
- AMD MI300X 官方页面：<https://www.amd.com/en/products/accelerators/instinct/mi300/mi300x.html>
- AMD MI300X 数据表：<https://www.amd.com/content/dam/amd/en/documents/instinct-tech-docs/data-sheets/amd-instinct-mi300x-data-sheet.pdf>

## 11. 相关文档

- [加速方法地图](./accel-map.md)
- [模型格式与框架](./model-format.md)
- [KV cache 专题](../performance/kv-cache.md)
- [第一阶段实验报告：Qwen3.6-27B 量化推理基线](../experiments/stage1-qwen27b.md)
