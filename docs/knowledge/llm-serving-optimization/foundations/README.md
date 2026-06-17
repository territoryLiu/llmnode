# Foundations

基础概念目录，只回答“这是什么、属于哪一层、和当前实验有什么关系”。

| 文件 | 职责 |
|---|---|
| [hardware.md](./hardware.md) | A800 / Ampere / Hopper / Blackwell、精度支持和硬件路径 |
| [model-format.md](./model-format.md) | 模型文件格式、量化格式、vLLM/SGLang/llama.cpp 支持关系 |
| [accel-map.md](./accel-map.md) | 推理加速方法地图和索引 |
| [compute-primitives.md](./compute-primitives.md) | GEMM 与 FlashAttention 工作原理、GPU 微架构（SM/CUDA Core/Tensor Core/Warp）、存储层次、推理执行模型、量化加速原因 |

不要在这里写完整实验报告。实验结论放到 `../experiments/`，性能方法放到 `../performance/`。
