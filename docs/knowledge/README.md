# 知识库索引

本目录存放与 `llmnode` 项目相关的技术选型知识、工程经验和环境说明。

这些文档不是正式契约，也不是当前运行状态说明。  
它们的定位是：**帮助理解“为什么这样做”和“有哪些经验可参考”的常驻参考层**。

---

## 文档列表

| 文件 | 内容摘要 |
|------|----------|
| [api_protocol_reference.md](api_protocol_reference.md) | 三种对外接口协议（/v1/chat/completions、/v1/responses、/v1/messages）的规范对比、字段映射与转换策略 |
| [llm_development.md](llm_development.md) | Dense 与 MoE 模型资源特点、单卡边界与后端框架选型建议 |
| [docker_deployment.md](docker_deployment.md) | 三后端（vLLM / llama.cpp / SGLang）Docker 部署方案与环境约束说明 |
| [model_format_conversion.md](model_format_conversion.md) | safetensors → GGUF 转换流程与量化参数速查 |
| [quantization_comparison.md](quantization_comparison.md) | Q4_K_M vs FP8 量化对比、硬件适配与决策树 |
| [backend_integration_qa.md](backend_integration_qa.md) | 三后端联调验证 Q&A：已知问题、解决方案与验证结果汇总 |

---

## 使用说明

- 这类文档可以长期保留，但默认只承担参考作用，不承担正式真相。
- 本目录适合保留：技术选型背景、环境经验、联调 Q&A、格式转换说明、方案对比资料。
- 本目录不应承载：当前正式状态、正式控制命令语义、正式流程、正式契约字段定义、未来优先级判断。
- 信息以记录为主，不一定实时更新。具体版本号和镜像 tag 以实际验证为准。
- 如果某个知识点已被提升为正式约束，应回流到 `docs/blueprint/current.md`、`docs/contracts/` 或 `docs/process/`。
- 与当前运行状态相关的信息，请以 `docs/blueprint/current.md` 为准。
