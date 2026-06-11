# 知识库索引

本目录存放与 `llmnode` 项目相关的技术选型知识、工程经验、环境说明和实验复盘。

这些文档不是正式契约，也不是当前运行状态说明。  
它们的定位是：**帮助理解“为什么这样做”和“有哪些经验可参考”的常驻参考层**。

---

## 阅读路径

如果是第一次读，建议按下面顺序进入：

1. 先看 [runtime-and-backends/backend_integration_qa.md](runtime-and-backends/backend_integration_qa.md)，理解三后端联调中的已知问题和解决方式。
2. 再看 [runtime-and-backends/docker_deployment.md](runtime-and-backends/docker_deployment.md)，理解 vLLM / llama.cpp / SGLang 的容器化部署边界。
3. 需要接口协议时，看 [protocols/api_protocol_reference.md](protocols/api_protocol_reference.md)。
4. 需要模型、格式、上下文性能背景时，看模型与性能分组。
5. 需要做 LLM serving 性能实验或调优时，看 [llm-serving-optimization/README.md](llm-serving-optimization/README.md)。

---

## 主题分组

### LLM serving 优化专题

| 入口 | 内容摘要 |
|------|----------|
| [llm-serving-optimization/README.md](llm-serving-optimization/README.md) | LLM serving 优化学习路线、目录职责、当前实验优先级 |
| [llm-serving-optimization/learning-log.md](llm-serving-optimization/learning-log.md) | 推理部署、性能分析、量化调优、profiler 和 kernel 优化学习过程 |
| [llm-serving-optimization/foundations/README.md](llm-serving-optimization/foundations/README.md) | 硬件、模型格式、推理加速方法基础入口 |
| [llm-serving-optimization/performance/README.md](llm-serving-optimization/performance/README.md) | benchmark、KV cache、profiler 与 kernel 分析入口 |
| [llm-serving-optimization/serving/README.md](llm-serving-optimization/serving/README.md) | vLLM / SGLang / llama.cpp serving 框架专题入口 |
| [llm-serving-optimization/optimization/README.md](llm-serving-optimization/optimization/README.md) | 量化与推理优化专题入口 |
| [llm-serving-optimization/experiments/README.md](llm-serving-optimization/experiments/README.md) | Qwen3.6-27B 阶段实验报告入口 |

### 后端集成与运行经验

| 文件 | 内容摘要 |
|------|----------|
| [runtime-and-backends/README.md](runtime-and-backends/README.md) | 后端集成与运行经验入口 |
| [runtime-and-backends/backend_integration_qa.md](runtime-and-backends/backend_integration_qa.md) | 三后端联调验证 Q&A：已知问题、解决方案与验证结果汇总 |
| [runtime-and-backends/docker_deployment.md](runtime-and-backends/docker_deployment.md) | 三后端（vLLM / llama.cpp / SGLang）Docker 部署方案与环境约束说明 |

### 协议与 API 参考

| 文件 | 内容摘要 |
|------|----------|
| [protocols/README.md](protocols/README.md) | 协议与 API 参考入口 |
| [protocols/api_protocol_reference.md](protocols/api_protocol_reference.md) | 三种对外接口协议（/v1/chat/completions、/v1/responses、/v1/messages）的规范对比、字段映射与转换策略 |

### 模型、格式与上下文性能

| 文件 | 内容摘要 |
|------|----------|
| [models-and-formats/README.md](models-and-formats/README.md) | 模型、格式与上下文性能入口 |
| [models-and-formats/llm_development.md](models-and-formats/llm_development.md) | Dense 与 MoE 模型资源特点、单卡边界与后端框架选型建议 |
| [models-and-formats/model_format_conversion.md](models-and-formats/model_format_conversion.md) | HF / safetensors -> GGUF 转换、UD / Q4 / FP8 量化对比、MTP 与部署建议 |
| [models-and-formats/model_context_performance.md](models-and-formats/model_context_performance.md) | 各模型在当前机器上的上下文长度可用性与单并发性能记录 |

---

## 使用说明

- 这类文档可以长期保留，但默认只承担参考作用，不承担正式真相。
- 本目录适合保留：技术选型背景、环境经验、联调 Q&A、格式转换说明、方案对比资料、学习路线、实验复盘。
- 本目录不应承载：当前正式状态、正式控制命令语义、正式流程、正式契约字段定义、未来优先级判断。
- 信息以记录为主，不一定实时更新。具体版本号和镜像 tag 以实际验证为准。
- 如果某个知识点已被提升为正式约束，应回流到 `docs/blueprint/current.md`、`docs/contracts/` 或 `docs/process/`。
- 与当前运行状态相关的信息，请以 `docs/blueprint/current.md` 为准。
