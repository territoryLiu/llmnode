# 模型、格式与上下文性能

本目录保留模型资源特征、格式转换、量化格式和上下文性能记录。

| 文件 | 内容摘要 |
|------|----------|
| [llm_development.md](llm_development.md) | Dense 与 MoE 模型资源特点、单卡边界与后端框架选型建议 |
| [model_format_conversion.md](model_format_conversion.md) | HF / safetensors -> GGUF 转换、UD / Q4 / FP8 量化对比、MTP 与部署建议 |
| [model_context_performance.md](model_context_performance.md) | 各模型在当前机器上的上下文长度可用性与单并发性能记录 |

这些文档用于保留模型与格式经验。当前正式 profile、模型路径和运行参数以 `config/defaults.yaml` 与 `config/backends/*.yaml` 为准。
