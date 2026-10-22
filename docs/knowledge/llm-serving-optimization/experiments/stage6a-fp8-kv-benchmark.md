# 第六阶段（a）实验报告：FP8 KV 容量、速度与质量回归

> 文档定位：项目知识库中的 LLM serving 优化实验报告，不属于 `llmnode` 项目蓝图、契约或正式路线图。
> 实验目标：评估 `AWQ-INT4 + FP8 KV cache` 的容量收益、速度表现和输出质量。
> 更新时间：2026-06-12。
> 当前结论状态：FP8 KV 容量翻倍（`90,944` → `178,752` tokens），但单请求速度无提升（`9.52 tok/s` vs 普通 AWQ `54.54 tok/s`）；质量回归 `5` 项通过 `1` 项，相比普通 AWQ baseline 新增 `code_generation` 和 `math_reasoning` 两项退化。`AWQ-INT4 + FP8 KV cache` 当前不能作为可上线配置。

相关专题：

- 第一阶段量化基线见 [stage1-2-qwen27b.md](./stage1-2-qwen27b.md)。
- Nsight 工具链 bring-up 见 [stage6b-nsight-toolchain.md](./stage6b-nsight-toolchain.md)。

## 1. 一页结论

| 维度 | 普通 AWQ | AWQ + FP8 KV | 判断 |
|---|---|---|---|
| KV tokens | `90,944` | `178,752` | **容量翻倍** |
| 256K max concurrency | `1.38x` | `2.68x` | **并发上限提升** |
| 64K 单请求 tok/s | `54.54` | `9.52` | **速度大幅下降** |
| 质量（5 项） | 3 pass / 2 fail | 1 pass / 4 fail | **新增 2 项退化** |
| 可上线？ | 是（主基线） | 否 | 仅作容量实验配置 |

## 2. FP8 KV 容量与速度 benchmark

### 2.1 启动侧证据

profile：

```text
config/backends/vllm_qwen36-27b-awq-int4-fp8-kv.yaml
```

启动命令：

```bash
VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE=vllm_qwen36-27b-awq-int4-fp8-kv \
  /home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control start --service vllm --daemon
```

启动日志：

```text
runtime/logs/qwen36-27b-awq-int4-fp8-kv-vllm-20260609-163417.log
```

| 字段 | 值 |
|---|---:|
| effective `kv_cache_dtype` | `fp8` |
| AWQ kernel | `MarlinLinearKernel for CompressedTensorsWNA16` |
| model loading memory | `19.05 GiB` |
| available KV cache memory | `22.01 GiB` |
| GPU KV cache size | `178,752 tokens` |
| max concurrency for `262,144` tokens/request | `2.68x` |
| API startup | success |

### 2.2 容量对比

| profile | kv_cache_dtype | available KV cache | KV tokens | 256K max concurrency |
|---|---|---:|---:|---:|
| `vllm_qwen36-27b-awq-int4` | `auto` | `22.38 GiB` | `90,944` | `1.38x` |
| `vllm_qwen36-27b-awq-int4-fp8-kv` | `fp8` | `22.01 GiB` | `178,752` | `2.68x` |

FP8 KV cache 将 KV tokens 从 `90,944` 提升到 `178,752`（约 2x），256K max concurrency 从 `1.38x` 提升到 `2.68x`。容量收益明确。

### 2.3 速度 benchmark

benchmark 命令：

```bash
VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE=vllm_qwen36-27b-awq-int4-fp8-kv \
  /home/heshan/.conda/envs/paper2any/bin/python scripts/benchmark_backend.py \
  --profile vllm_qwen36-27b-awq-int4-fp8-kv \
  --targets 65536 \
  --max-tokens 512 \
  --concurrency 1 \
  --warmup-runs 0 \
  --measure-runs 3 \
  --sample-interval 2 \
  --output-dir runtime/data/benchmarks/manual-stage6-awq-fp8-kv
```

结果目录：

```text
runtime/data/benchmarks/manual-stage6-awq-fp8-kv/20260609-163920-vllm_qwen36-27b-awq-int4-fp8-kv/
```

汇总：

| prompt | success | latency avg | latency p50 | latency min | latency max | completion tok/s avg | completion tok/s p50 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| `64K` | `3/3` | `43,461.40 ms` | `43,952.99 ms` | `41,668.70 ms` | `44,762.50 ms` | `9.52` | `9.34` |

测量轮次：

| latency | completion | finish_reason | completion tok/s |
|---:|---:|---|---:|
| `44,762.50 ms` | `418` | `stop` | `9.34` |
| `43,952.99 ms` | `490` | `stop` | `11.15` |
| `41,668.70 ms` | `336` | `stop` | `8.06` |

benchmark 采样证据：

- `other_processes_total_mb=0`
- `other_processes=[]`
- vLLM 周期性指标中出现 `GPU KV cache usage: 9.8%`

### 2.4 速度判断

- 单请求 `64K + output=512` 速度为 `9.52 tok/s`，普通 AWQ streaming 为 `54.54 tok/s`，**速度大幅下降**。
- FP8 KV cache 是容量方案，不是单请求加速方案。
- 容量翻倍的代价是单请求 decode 速度降低（FP8 反量化开销 + attention 计算精度差异）。

## 3. 质量回归

### 3.1 回归设计

本轮使用 5 个最小用例：

| case | 目的 |
|---|---|
| `long_context_consistency` | 长上下文精确取数 |
| `code_generation` | 代码生成基本正确性 |
| `math_reasoning` | 数学推理基本正确性 |
| `structured_json` | 严格 JSON 输出 |
| `tool_call_json_stability` | 工具调用 JSON 稳定性 |

脚本：

```text
scripts/fp8_kv_quality_check.py
```

输出目录：

```text
runtime/data/benchmarks/manual-stage7-fp8-kv-quality/
```

注意：当前 Qwen/vLLM 响应把文本放在 `message.reasoning`，`message.content` 可能为 `null`。脚本已同时读取 `content / reasoning_content / reasoning`。

脚本支持两个入口：

```bash
/home/heshan/.conda/envs/paper2any/bin/python scripts/fp8_kv_quality_check.py run ...
/home/heshan/.conda/envs/paper2any/bin/python scripts/fp8_kv_quality_check.py compare ...
```

### 3.2 普通 AWQ baseline

profile：

```text
vllm_qwen36-27b-awq-int4
```

命令：

```bash
/home/heshan/.conda/envs/paper2any/bin/python scripts/fp8_kv_quality_check.py \
  --model qwen36-27b-awq-int4 \
  --output runtime/data/benchmarks/manual-stage7-fp8-kv-quality/awq-baseline.json
```

结果：

| case | passed | 说明 |
|---|---|---|
| `long_context_consistency` | yes | 找到 `team-0 / alpha-777 / 248` |
| `code_generation` | yes | 包含 `def stable_top_k`、`sorted`、`k <= 0` |
| `math_reasoning` | yes | 包含 `23.33` |
| `structured_json` | no | 内容包含目标字段，但输出混入 reasoning，整体不是合法 JSON |
| `tool_call_json_stability` | no | 开头有 JSON，但后续混入说明文字，整体不是合法 JSON |

baseline 判断：

- 当前模型/服务路径本身就存在严格 JSON 稳定性问题。
- 后续 FP8 KV 对照不能只看"是否严格 JSON 失败"，而应看是否比 baseline 更差。

### 3.3 FP8 KV 对照

profile：

```text
vllm_qwen36-27b-awq-int4-fp8-kv
```

启动时发现外部 GPU 进程（已处理，等 GPU 空窗后重测）：

```text
3477885, /proj02/pengyao/envs/SFormer_clean/bin/python, 23462 MiB
```

2026-06-10 GPU 空窗后已重新启动并完成对照。

启动日志：

```text
runtime/logs/qwen36-27b-awq-int4-fp8-kv-vllm-20260610-091113.log
```

启动侧证据：

| 字段 | 值 |
|---|---:|
| effective `kv_cache_dtype` | `fp8` |
| AWQ kernel | `MarlinLinearKernel for CompressedTensorsWNA16` |
| attention backend | `FLASHINFER` |
| model loading memory | `19.05 GiB` |
| available KV cache memory | `22.01 GiB` |
| GPU KV cache size | `178,752 tokens` |
| max concurrency for `262,144` tokens/request | `2.68x` |
| API startup | success |

FP8 KV 单独结果：

| case | passed | 说明 |
|---|---|---|
| `long_context_consistency` | yes | 找到 `team-0 / alpha-777 / 248` |
| `code_generation` | no | 输出包含思考过程，且 512 token 截断前没有出现 `def stable_top_k` |
| `math_reasoning` | no | 推理到 `7 / 30 = 0.233333...`，但 512 token 截断前没有输出 `23.33` |
| `structured_json` | no | 包含目标字段，但整体不是合法 JSON |
| `tool_call_json_stability` | no | 开头有 JSON，但后续混入说明文字，整体不是合法 JSON |

### 3.4 对照结论

```bash
/home/heshan/.conda/envs/paper2any/bin/python scripts/fp8_kv_quality_check.py compare \
  --baseline runtime/data/benchmarks/manual-stage7-fp8-kv-quality/awq-baseline.json \
  --candidate runtime/data/benchmarks/manual-stage7-fp8-kv-quality/awq-fp8-kv.json \
  --output runtime/data/benchmarks/manual-stage7-fp8-kv-quality/awq-vs-fp8-kv-comparison.json
```

| case | baseline | FP8 KV | 是否新增退化 |
|---|---|---|---|
| `long_context_consistency` | pass | pass | no |
| `code_generation` | pass | fail | **yes** |
| `math_reasoning` | pass | fail | **yes** |
| `structured_json` | fail | fail | no |
| `tool_call_json_stability` | fail | fail | no |

新增退化集中在代码生成和数学推理两个 baseline 通过的用例上。失败形态均为"thinking tokens 挤占 512 token 预算，最终答案被截断"。

### 3.5 退化原因分析

FP8 KV 质量退化的因果链：

```
FP8 KV 精度损失
  → 每个 token 的 KV 存储有量化误差
  → 随 thinking token 累积，模型 attend 到的历史 KV 越来越"模糊"
  → 模型对推理不够确信，生成更多冗余 thinking steps
  → thinking tokens 更长，挤占 answer 的 token 预算
  → 512 token 截断前答案未输出
```

需要区分三类因素：
1. **FP8 KV 精度退化** — KV 量化误差累积导致生成路径偏移
2. **reasoning parser 行为** — thinking 和 answer 共享 `max_tokens` 预算
3. **max_tokens 截断** — 512 token 上限对带 thinking 的输出不够用

验证方法：加大 `max_tokens` 到 1024/2048，或关闭 thinking 模式重测。

## 4. 下一步

1. 暂不推进 `AWQ-INT4 + FP8 KV cache` 作为可上线配置。
2. 若继续研究，优先做：
   - 加大 `max_tokens` 复测，确认退化是 token 预算问题还是精度直接导致答案错误
   - 对比同一 prompt 下 AWQ 和 FP8 KV 的 thinking token 数量
   - 关闭 thinking 模式重测

