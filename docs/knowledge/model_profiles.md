# 模型支持矩阵与 Profile 命名

本文档用于说明当前仓库里每个模型适合走哪个后端、推荐使用哪个 profile 文件，以及配置时该填什么模型名。

它是 `docs/knowledge/*` 参考层文档，不替代正式真相源。正式激活入口仍然是：

- `config/defaults.yaml`
- `config/backends/*.yaml`

---

## 配置规则

当前正式规则：

- `config/defaults.yaml` 只负责选择 `active_backend_profile`
- 每个 `config/backends/*.yaml` 只描述一个“后端 + 模型”组合
- 文件名推荐格式：
  - `vllm_<model-name>.yaml`
  - `llama.cpp_<model-name>.yaml`
  - `sglang_<model-name>.yaml`
- `/v1/models` 对外直接暴露 profile 里的真实 `model_name`
- 当前正式默认后端端口统一为 `15673`

示例：

```yaml
active_backend_profile: vllm_qwen36-35b-a3b-fp8
```

---

## 当前模型支持矩阵

| 模型目录 / 文件 | 推荐后端 | 推荐 profile | `model_name` | 当前建议 | 备注 |
|---|---|---|---|---|---|
| `models/Qwen/Qwen3.6-35B-A3B-FP8` | `vllm` | `config/backends/vllm_qwen36-35b-a3b-fp8.yaml` | `qwen36-35b-a3b-fp8` | 正式默认 | 已验证单并发 256K；`gpu_memory_utilization=0.65` 合适 |
| `models/Qwen/Qwen3.6-35B-A3B-FP8` | `sglang` | `config/backends/sglang_qwen36-35b-a3b-fp8.yaml` | `qwen36-35b-a3b-fp8` | 试验中 | 当前记录已完成启动观测，但未拿到稳定 ready |
| `models/Qwen/Qwen3.6-35B-A3B` | `vllm` | `config/backends/vllm_qwen36-35b-a3b.yaml` | `qwen36-35b-a3b` | 可选 | 非 FP8 版本，参数较保守，默认只给到 `128K` |
| `models/Qwen/Qwen3.6-27B` | `vllm` | `config/backends/vllm_qwen36-27b.yaml` | `qwen36-27b` | 历史保留 | 当前不建议继续作为正式默认模型 |
| `models/Qwen/Qwen3.6-35B-A3B-GGUF/qwen36-35b-a3b-q4km.gguf` | `llama.cpp` | `config/backends/llama.cpp_qwen36-35b-a3b-q4km.yaml` | `qwen36-35b-a3b` | 可选 | 适合低显存 / GGUF 路线；已验证单条 256K |
| `models/Qwen/Qwen3.6-35B-A3B-GGUF/qwen36-35b-a3b-f16.gguf` | `llama.cpp` | `config/backends/llama.cpp_qwen36-35b-a3b-f16.yaml` | `qwen36-35b-a3b-f16` | 备选 | 体积更大，当前只保留保守 profile |
| `models/deepseek/DeepSeek-V4-Flash` | 待定，倾向 `llama.cpp`/专用实现 | 暂无正式 profile | 暂无 | 未纳入正式路径 | 现目录是 HuggingFace 权重和官方推理代码，不适合直接照搬当前 `vllm` 默认参数 |
| `models/gemini/gemma-4-31B-it` | 待定 | 暂无正式 profile | 暂无 | 未纳入正式路径 | 先确认 tokenizer / chat template / 长上下文上限再补 profile |

---

## 已落地 Profile

当前仓库已提供：

- `config/backends/vllm_qwen36-35b-a3b-fp8.yaml`
- `config/backends/sglang_qwen36-35b-a3b-fp8.yaml`
- `config/backends/vllm_qwen36-35b-a3b.yaml`
- `config/backends/vllm_qwen36-27b.yaml`
- `config/backends/llama.cpp_qwen36-35b-a3b-q4km.yaml`
- `config/backends/llama.cpp_qwen36-35b-a3b-f16.yaml`

---

## 选型说明

### `Qwen3.6-35B-A3B-FP8`

- 当前优先使用 `vLLM`
- 原因：
  - 已完成真实 4K 到 256K 五档单并发验证
  - 当前机器上 `gpu_memory_utilization=0.65` 即可稳定跑到 `256K`
  - 相比 `llama.cpp q4km`，长上下文性能更好

### `Qwen3.6-35B-A3B-GGUF`

- 当前优先使用 `llama.cpp`
- 原因：
  - GGUF 是 llama.cpp 正式强项
  - `q4km` 已在当前机器上验证单条 `256K`
  - 更适合作为“低显存 / 兼容性优先”的替代路线

### `DeepSeek-V4-Flash`

- 当前不要直接套 `vllm_qwen*` 参数
- 原因：
  - 目录结构里带有官方 `inference/` 与自定义编码实现
  - 是否适配当前 `vllm / llama.cpp / sglang` 控制面，还需要单独验证
  - 如果后续要走 `llama.cpp` 或 CPU 内存优先路线，也应先完成格式转换与性能验证，再补正式 profile

---

## 维护规则

新增模型时，建议同步完成三件事：

1. 在 `config/backends/` 新增对应 profile 文件
2. 在本文补一行支持矩阵
3. 在 [models_max_len.md](/proj02/liuheshan/llmnode/docs/knowledge/models_max_len.md) 补上下文与性能实测记录
