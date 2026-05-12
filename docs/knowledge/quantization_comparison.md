# 量化方案对比：Q4_K_M vs FP8（GPU 推理）

核心结论：**没有绝对的"谁更快"，取决于硬件、并发需求和精度要求。**

---

## 1. 关键差异速览

| 维度 | llama.cpp + Q4_K_M | vLLM + FP8 |
|------|-------------------|-----------|
| **量化类型** | 4-bit 整数块量化（每32元素一组，带scale） | 8-bit 浮点（E4M3，per-tensor/per-channel） |
| **硬件要求** | 任意支持 CUDA 的 N 卡（GTX 10xx+） | FP8 加速需 Hopper/Ada（H100/40xx），旧卡退化为 W8A16 |
| **显存占用** | ~4.5GB（7B 模型） | ~8-9GB（7B 模型，含 KV cache 优化） |
| **单请求延迟** | 略优（简单内核，开销小） | 相当或略高（复杂调度） |
| **高并发吞吐** | 线性下降（批处理弱） | 高并发提升显著（PagedAttention + Continuous Batching） |
| **长上下文** | 显存碎片较严重 | PagedAttention 显存利用率更高 |
| **精度损失** | ~2-3% perplexity 提升 | ~1-2% perplexity 提升（FP8 动态量化） |
| **部署复杂度** | 单二进制 + GGUF，简单 | 需 Python 环境 + 依赖 + 模型转换 |

---

## 2. 技术原理

### Q4_K_M 量化机制（llama.cpp）

- 分组量化：每32个权重为一组，独立计算 scale
- 格式：4-bit 整数 + 16-bit scale（每块）
- 优势：精度/体积平衡好，CPU/GPU 通用
- 劣势：反量化需额外计算，GPU 上无法完全利用 Tensor Core

RTX 4090 单请求速度参考：**80-120 tok/s**（7B 模型）

### FP8 量化机制（vLLM）

- 格式：FP8 E4M3（1 sign + 4 exp + 3 mantissa），范围 ±448
- Weights：静态 per-channel（转换时计算）
- Activations：动态 per-token（推理时计算）
- 优势：原生支持 NVIDIA FP8 Tensor Core（H100/4090），计算密度更高
- 限制：旧架构（Turing/Ampere）仅支持 weight-only FP8，加速有限

H100 上参考效果：~2× 延迟降低，吞吐提升 1.6×（70B 模型）

---

## 3. 实测数据参考

场景：RTX 4090 + Llama-3-8B + 512 tokens 生成

| 配置 | 首字延迟 | 生成速度 | 显存占用 | 并发10请求吞吐 |
|------|----------|----------|----------|---------------|
| llama.cpp Q4_K_M (CUDA) | ~0.4s | 95 tok/s | 5.2 GB | ~45 tok/s |
| vLLM FP16 | ~0.3s | 85 tok/s | 16 GB | ~420 tok/s |
| vLLM FP8 (W8A8) | ~0.3s | 105 tok/s | 10 GB | ~580 tok/s |

> 不同 prompt 长度波动 ±15%。消费级卡（RTX 3060 12GB）场景：llama.cpp Q4_K_M 约 42 tok/s，vLLM FP8 无法启用（需 compute capability ≥8.9）。

---

## 4. 硬件选型决策树

```
你的硬件是？
├─ NVIDIA H100 / RTX 4090 / 4080（Ada Lovelace+）
│  ├─ 需要高并发 API 服务 → vLLM + FP8
│  ├─ 单用户/离线使用 → llama.cpp Q4_K_M（更简单，延迟略低）
│  └─ 精度敏感（代码/数学） → 先测 Q8_0 vs FP8，再决定
│
├─ NVIDIA RTX 30xx / 20xx / Tesla V100（Ampere/Turing）
│  ├─ vLLM FP8 退化为 W8A16，加速有限
│  └─ 推荐 llama.cpp Q4_K_M（兼容性好，性能稳定）
│
├─ AMD GPU / Intel Arc
│  ├─ vLLM 支持有限（主要优化 CUDA）
│  └─ llama.cpp（支持 ROCm/Vulkan/SYCL）
│
└─ Apple Silicon（M1/M2/M3/M4）
   ├─ vLLM 无原生 Metal 支持
   └─ llama.cpp + Metal 后端（统一内存优势）
```

---

## 5. 实用配置

### llama.cpp Q4_K_M（GPU）

```bash
docker run --rm --gpus all \
  -p 8080:8080 \
  -v /proj02/liuheshan/llmnode/models:/models \
  ghcr.io/ggml-org/llama.cpp:b5471-cuda \
  /app/llama-server \
  -m /models/gemma/gemma-4-31b-it-Q4_K_M.gguf \
  --host 0.0.0.0 \
  --port 8080 \
  -ngl 999 \
  -c 4096
```

`-ngl 999` 表示将所有层卸载到 GPU；根据显存大小适当调整。

### vLLM FP8 启用条件

```bash
# 1. 检查硬件 compute capability（需 8.9 或更高）
python -c "import torch; print(torch.cuda.get_device_capability(0))"

# 2. 启动（使用已预量化的 FP8 checkpoint）
docker run --rm --gpus all \
  --ipc=host \
  -p 8000:8000 \
  -v /proj02/liuheshan/llmnode/models:/models \
  vllm/vllm-openai:v0.8.5 \
  --model /models/Qwen/Qwen3.6-35B-A3B-FP8 \
  --quantization fp8 \
  --host 0.0.0.0 \
  --port 8000
```

> 注意：`--quantization fp8` 在线量化仅支持 weight-only（W8A16），无法发挥 FP8 完整加速；完整 FP8（W8A8）需预量化 checkpoint。

---

## 6. 按使用目标选型

| 目标 | 推荐方案 |
|------|----------|
| 本地聊天/开发测试 | llama.cpp + Q4_K_M（简单、兼容、够用） |
| 生产环境 API 服务 | vLLM + FP8（高并发、低延迟） |
| 精度优先（科研/代码） | 先测 Q8_0 vs FP8 vs FP16，选精度达标的最快方案 |
| 多卡集群成本敏感 | vLLM + FP8（显存 ↓50% = 卡数 ↓50%） |

---

## 7. 常见问题

**Q：能把 llama.cpp 的 Q4 GGUF 直接给 vLLM 用吗？**  
A：不行。vLLM 不支持 GGUF 格式，其内核优化针对 HuggingFace 权重布局设计。

**Q：FP8 精度够用吗？**  
A：多数任务足够。Llama-3-8B 在 GSM8K 上，FP8 vs FP16 准确率差异 <1%；代码生成/数学推理建议用 Q8_0 或 FP16 验证。

**Q：为什么 4090 跑 vLLM FP8 没加速？**  
A：检查三点：① 驱动 ≥535 + CUDA 12.1+；② 模型确实是 FP8 checkpoint（非在线量化）；③ `nvidia-smi` 看到 fp8 kernel 而非 fp16 fallback。
