# Qwen3.8 投机解码对照实验设计

## 目标

在单张 NVIDIA A800 80GB 上，对 Qwen3.8-27B 的 AWQ-INT4、NVFP4、DFlash2 和内置 MTP 做可复现的同口径对照，回答哪条路线适合当前机器和 Claude/Codex 长上下文负载。

## 候选

1. AWQ-INT4，无投机。
2. AWQ-INT4 + DFlash2，7 draft tokens。
3. NVFP4，无投机。
4. NVFP4 + DFlash2，7 draft tokens。
5. NVFP4 + 内置 MTP，3 speculative tokens。
6. NVFP4 + 内置 MTP，7 speculative tokens。

失败启动、OOM、框架拒绝或不兼容同样进入结果，不从报告中删除。

## 固定条件

- GPU：单张 A800 80GB，运行前必须空闲。
- 框架：同一 `vllm/vllm-openai:nightly` 本地镜像和版本。
- 输入：64K tokens。
- 输出：强制 800 tokens，`min_tokens=max_tokens` 且 `ignore_eos=true`。
- 并发：1、2、3。
- 每个矩阵点：1 次 warmup，3 个测量批次。
- Prefix Cache：开启；每个候选重启后先 warmup，测量值不混用其他候选的缓存。
- 固定主模型最大长度、GPU memory utilization、max_num_seqs、采样参数和 endpoint。

## 指标

- 每请求 TTFT、TPOT、decode tok/s、端到端延迟。
- 每批聚合 output tok/s。
- completion token 数与成功率。
- 启动权重显存、KV cache 容量、最大上下文并发提示。
- GPU 显存峰值、KV cache usage 峰值。
- 投机接受指标（框架日志可提供时记录 acceptance length/rate）。

## 编排边界

- 主模型继续只读挂载到 `/model`。
- 独立草稿模型通过可选 `speculative_model_dir` 只读挂载到 `/draft-model`。
- profile 中的 `speculative_config.model` 显式使用 `/draft-model`。
- 未配置草稿目录时，原有 vLLM profile 行为不变。

## 回滚

- 默认激活 profile 不改变。
- 每个实验结束后停止后端；任一候选失败不影响其他候选继续执行。
- 删除实验 profile 或清空 `speculative_model_dir/speculative_config` 即可回到普通推理。

## 产物

- 原始结果和日志：`runtime/data/benchmarks/qwen38-speculative-ab-20260820/`。
- 正式实验报告：`docs/knowledge/llm-serving-optimization/experiments/stage11-qwen38-speculative-decoding.md`。
- 实验索引同步到 `docs/knowledge/llm-serving-optimization/experiments/README.md`。
