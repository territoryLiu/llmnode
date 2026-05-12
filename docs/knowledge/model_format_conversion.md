# 模型格式转换：safetensors → GGUF

`llama.cpp` 不支持直接读取 safetensors 或 Hugging Face 格式权重，必须先转换为 GGUF 格式。

---

## 1. 转换方案对比

| 方案 | 适用场景 | 优点 | 缺点 |
|------|----------|------|------|
| 主机直接转换 | 个人开发、偶尔转换 | 最简单、最快、依赖可控 | 需主机安装 Python 环境 |
| `:full` 容器转换 | 需要环境隔离 | 不污染主机 | 镜像大，Python 依赖可能不全 |
| 专用转换镜像 | 团队/自动化流程 | 可复用、标准化 | 构建维护成本较高 |

---

## 2. 方案一：主机直接转换（推荐）

```bash
# 安装依赖
pip install -U transformers sentencepiece tiktoken huggingface-hub

# 克隆 llama.cpp 获取转换脚本
git clone --depth 1 https://github.com/ggml-org/llama.cpp
cd llama.cpp

# 执行转换
python convert_hf_to_gguf.py \
  /path/to/model \
  --outfile /path/to/output.gguf \
  --outtype q4_k_m
```

内存需求：FP16 转换约需 `模型参数量 × 2 bytes + 2GB`。31B 模型约需 64GB RAM。

---

## 3. 方案二：使用 `:full` 容器转换

```bash
docker run --rm \
  -v /path/to/hf_models:/hf_models \
  -v /path/to/gguf_output:/gguf_output \
  -v /path/to/llama.cpp:/llama.cpp \
  ghcr.io/ggml-org/llama.cpp:full \
  python3 /llama.cpp/convert_hf_to_gguf.py \
    /hf_models/model-name \
    --outfile /gguf_output/model.gguf \
    --outtype q4_k_m
```

注意：`:full` 镜像的 Python 环境可能缺少 `transformers` 等依赖，需提前验证或手动安装。

---

## 4. 方案三：专用转换镜像

```dockerfile
FROM python:3.11-slim
RUN pip install transformers sentencepiece tiktoken huggingface-hub
RUN git clone --depth 1 --branch b4406 https://github.com/ggml-org/llama.cpp /llama.cpp
WORKDIR /llama.cpp
ENTRYPOINT ["python3", "convert_hf_to_gguf.py"]
```

```bash
docker build -t hf-to-gguf -f Dockerfile.convert .
docker run --rm \
  -v /path/to/models:/hf_models \
  -v /path/to/output:/gguf_output \
  hf-to-gguf /hf_models/model-name \
  --outfile /gguf_output/model.gguf \
  --outtype q4_k_m
```

---

## 5. 量化类型速查

| 量化类型 | 体积 | 精度损失 | 推荐场景 |
|----------|------|----------|----------|
| `f16` | 最大（≈原始大小） | 无 | 精度基准测试 |
| `q8_0` | 大（约原始 50%） | 极小 | 精度优先 |
| `q4_k_m` | 中（约原始 25%） | 小（<1%） | 推荐平衡点 |
| `q4_k_s` | 较小 | 中 | 显存紧张 |
| `q2_k` | 最小 | 较大 | 极端显存受限 |

`q4_k_m` 是最常用的平衡点：精度损失 <1%，体积缩减约 50%，推理速度提升约 2 倍。

---

## 6. 主要模型的转换参数

| 模型 | `--vocab-type` | `--outtype` 推荐 |
|------|---------------|-----------------|
| Gemma 4 | `spm` | `q4_k_m` |
| Qwen3.6 | `bpe` | `q4_k_m` |
| Llama 3 | `bpe` | `q4_k_m` |
| DeepSeek | `bpe` | `q4_k_s` |

---

## 7. 转换后验证

```bash
# 验证 GGUF 文件可读（用 llama-cli 快速跑几个 token）
./build/bin/llama-cli -m model.gguf -p "Hello" -n 10
```

---

## 8. 常见错误

| 错误 | 原因 | 处理 |
|------|------|------|
| `unsupported architecture` | 模型架构未被 llama.cpp 支持 | 等待社区适配，或改用 vLLM |
| `Missing tokenizer file` | 模型目录缺少 tokenizer | 检查是否有 `tokenizer.model` 或 `tokenizer.json` |
| `Segmentation fault during inference` | 量化类型不兼容或 GGUF 版本过旧 | 尝试 `q5_k_m` 或更新 llama.cpp |
| 转换速度慢/内存不足 | 大模型转换内存需求高 | 确认可用 RAM，或分步量化 |

---

## 9. 工作流说明

转换是**构建时操作**（离线，在开发机完成），推理是**运行时操作**（用 Docker 镜像部署）。  
只需传输最终产物：`.gguf` 模型文件 + `docker save` 的镜像 tar，不传源码或中间文件。
