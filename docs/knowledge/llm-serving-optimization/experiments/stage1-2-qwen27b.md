# 第一阶段实验报告：Qwen3.6-27B 量化推理基线

> 文档定位：项目知识库中的 LLM serving 优化实验报告，不属于 `llmnode` 项目蓝图、契约或正式路线图。  
> 实验目标：在当前 `llmnode` 项目里，用同一 Qwen3.6-27B 模型族、同一 vLLM 后端、同一 benchmark 口径，对比 BF16、FP8、NVFP4、AWQ-INT4 的显存、速度和稳定性。  
> 更新时间：2026-06-12（NVFP4 数据更新为 gpu_memory_utilization=0.6 干净环境测量）。  
> 当前结论状态：第一阶段已能回答"哪些量化值得继续看"，但还不能回答"真正瓶颈 kernel 是什么"。

相关专题：

- benchmark 口径见 [benchmark-methodology.md](../performance/benchmark-methodology.md)。
- KV cache 解释见 [kv-cache.md](../performance/kv-cache.md)。
- vLLM 参数见 [vllm-deep-dive.md](../serving/vllm-deep-dive.md)。
- 量化机制见 [quantization-deep-dive.md](../optimization/quantization-deep-dive.md)。
- A800 精度支持见 [hardware.md](../foundations/hardware.md)。

## 1. 一页结论

本轮固定条件：

- 后端：`vLLM`
- GPU：A800 / Ampere
- `prompt tokens`：`16K / 64K`
- `output tokens`：`512`（max_tokens，streaming 测量）
- `concurrency`：`1`
- 统计口径：streaming SSE 计时，拆分 TTFT / prefill / decode / TPOT

本轮最重要结论：

1. **权重显存最低的是 `AWQ-INT4`**，约 `19.05 GiB`，比 BF16 少 `62.7%`。
2. **Decode 速度最快的是 `AWQ-INT4`**：TPOT=16.13ms（62 tok/s at 16K），比 BF16（36.72ms）快 2.3 倍。
3. **E2E 延迟最低的是 `AWQ-INT4`**：16K+512 平均 14,244ms，比 BF16（23,207ms）快 39%。
4. **Prefill 速度最快的是 `BF16`**：TTFT=4,442ms at 16K，无反量化开销。量化模型中 NVFP4 ≈ AWQ-INT4，FP8 最慢。
5. **`FP8` 在当前 A800 上表现最弱**：A800 没有原生 FP8 Tensor Core，vLLM 走 weight-only FP8 + Marlin fallback。
6. **16K 场景 decode 是主导**（BF16 占 80.9%），**64K 场景 prefill 是主导**（量化模型都 >70%）。
7. 所有 profile 从 16K 到 64K 的 TTFT 增长约 4.8-5.0 倍，说明瓶颈高度一致：prefill、attention、KV cache，而不是某一个量化格式独有的问题。
8. **`output=64` 的旧结论（"BF16 最快"）只在 prefill 主导的短输出场景成立**。当 decode 充分展开后，AWQ-INT4 的轻量权重读取优势充分体现。

一句话判断：

> AWQ-INT4 不仅显存效率最高，在 decode 充分展开的交互式场景下速度也最快。量化主要解决容量和部署边界，但在较长输出场景下，量化的 decode 速度优势也很明显。

对当前 A800 + 27B + 单并发长上下文场景，量化收益优先级：

```text
显存容量 > 上下文容量 > 并发能力 > 速度
```

本轮最有工程价值的发现：AWQ-INT4 用约 `19.05 GiB` 权重显存，decode 速度反而最快（62 tok/s），E2E 延迟最低（14,244ms at 16K+512）。它在当前机器上是显存效率和速度的双重最优候选。

## 2. 实验对象

本阶段使用同一模型族：

| 角色 | 模型目录 | profile |
|---|---|---|
| 原始基准 | `models/Qwen/Qwen3.6-27B` | `vllm_qwen36-27b` |
| FP8 | `models/Qwen/Qwen3.6-27B-FP8` | `vllm_qwen36-27b-FP8` |
| NVFP4 | `models/Qwen/Qwen3.6-27B-NVFP4` | `vllm_qwen36-27b-nvfp4` |
| AWQ-INT4 | `models/Qwen/Qwen3.6-27B-AWQ-INT4` | `vllm_qwen36-27b-awq-int4` |

这个选择是合理的：

- 都来自 Qwen3.6-27B 模型族，变量相对可控。
- 都有对应 vLLM profile，能沿用项目控制面。
- 覆盖了当前最值得先学的三类量化形态：FP8、NVFP4、AWQ-INT4。
- 原始 BF16 可以作为速度上限参考，虽然它不是稳定 256K 候选。

需要保留的不确定性：

- 这些模型虽同属 27B 家族，但量化格式、权重布局和 kernel 路径不同。
- BF16 的速度对照使用了 `max_model_len=131072` 临时覆盖，和其他量化 profile 的 `262144` 启动配置并不完全一致。
- 当前结果只代表 A800 + 当前 vLLM nightly + 当前模型权重格式，不能直接外推到 H100/H200/B200。

## 3. 实验口径

本轮主口径使用 streaming 测量，拆分 prefill / decode：

| 项 | 值 |
|---|---|
| 后端 | `vLLM` |
| prompt tokens | `16,384` / `65,536` |
| output tokens | `512`（max_tokens） |
| concurrency | `1` |
| warmup | `1` |
| measure | `3` |
| 计时方式 | streaming SSE，首 delta 事件 = TTFT |
| prompt 构建 | `build_prompt_for_target`，附加详细回答后缀（~20 tokens 额外开销） |
| token 统计 | 以服务端返回的 `usage.prompt_tokens` 为准 |

本轮记录字段：

- TTFT（首 token 延迟，≈ prefill 耗时）
- prefill 耗时
- decode 耗时
- TPOT（每 token 延迟）
- decode tok/s
- E2E latency
- completion tokens
- 启动侧：权重显存、KV memory、KV tokens、max concurrency

## 4. 启动侧证据

| profile | max model len | weight memory | loading time | KV memory | KV tokens | max concurrency for 262,144 tokens/request | notes |
|---|---:|---:|---:|---:|---:|---:|---|
| `vllm_qwen36-27b` | `262144` | `51.1 GiB` | `50.330138 s` | `14.13 GiB` | 未分配成功 | 不支持 262,144 | failed: needs 16.17 GiB KV cache; available 14.13 GiB; estimated max len 228,928 |
| `vllm_qwen36-27b` | `131072` | `51.1 GiB` | `7.650631 s` | `14.13 GiB` | `57,232` | `1.73x for 131,072` | temporary baseline; torch.compile 58.26s |
| `vllm_qwen36-27b-FP8` | `262144` | `28.87 GiB` | `24.820321 s` | `20.5 GiB` | `83,888` | `1.27x` | no native FP8 compute; weight-only FP8 via Marlin |
| `vllm_qwen36-27b-nvfp4` | `262144` | `24.05 GiB` | `5.441500 s` | `21.34 GiB` | `87,024` | `1.32x` | `gpu_memory_utilization=0.6`，startup clean |
| `vllm_qwen36-27b-awq-int4` | `262144` | `19.05 GiB` | `25.587820 s` | `22.38 GiB` | `90,944` | `1.38x` | compressed-tensors WNA16; MarlinLinearKernel; torch.compile 70.18s |

关键解释：

- `KV memory / KV tokens` 是 vLLM 启动时规划出来的 KV cache 池容量口径，不是单条 256K 请求实际消耗的 KV。
- 不能用 `GPU KV cache size tokens` 线性外推"最大可服务 prompt tokens"或"256K 实际显存消耗"。
- `maximum concurrency for 262,144 tokens/request` 可以作为启动侧容量提示，但工程上应保守理解：`1.32x` 是有余量但不代表可以稳定多并发。

## 5. Benchmark 结果：16K / 64K + 512 streaming

### 5.1 结果汇总

| profile | prompt | TTFT (ms) | prefill (ms) | decode (ms) | TPOT (ms) | decode tok/s | E2E (ms) | completion tokens |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `BF16` | 16K | `4,441.84` | `4,441.84` | `18,764.69` | `36.72` | `27.23` | `23,206.91` | `512` |
| `BF16` | 64K | `22,439.65` | `22,439.65` | `19,990.91` | `39.12` | `25.56` | `42,430.92` | `512` |
| `FP8` | 16K | `6,426.07` | `6,426.07` | `11,079.09` | `21.68` | `46.12` | `17,505.55` | `512` |
| `FP8` | 64K | `30,963.90` | `30,963.90` | `12,222.81` | `23.94` | `41.78` | `43,187.14` | `512` |
| `NVFP4` | 16K | `5,727.91` | `5,727.91` | `9,399.02` | `19.95` | `50.13` | `15,126.93` | `472` |
| `NVFP4` | 64K | `27,983.33` | `27,983.33` | `8,438.35` | `22.28` | `44.88` | `36,421.68` | `379` |
| `AWQ-INT4` | 16K | `6,002.99` | `6,002.99` | `8,240.68` | `16.13` | `62.01` | `14,244.00` | `512` |
| `AWQ-INT4` | 64K | `29,127.58` | `29,127.58` | `9,351.07` | `18.34` | `54.54` | `38,479.01` | `511` |

### 5.2 Decode 速度（TPOT）排名

| prompt | AWQ-INT4 | NVFP4 | FP8 | BF16 |
|---|---:|---:|---:|---:|
| 16K TPOT | `16.13 ms` | `19.95 ms` | `21.68 ms` | `36.72 ms` |
| 16K tok/s | `62.01` | `50.13` | `46.12` | `27.23` |
| 64K TPOT | `18.34 ms` | `22.28 ms` | `23.94 ms` | `39.12 ms` |
| 64K tok/s | `54.54` | `44.88` | `41.78` | `25.56` |

Decode 阶段 BF16 最慢，AWQ-INT4 最快。原因：量化模型的权重体积更小，decode 阶段每步的权重读取量更少，TPOT 更低。BF16 虽然 kernel 路径成熟，但每步要读取完整 BF16 权重，在 decode 的 memory-bound 场景下反而吃亏。

### 5.3 Prefill 速度（TTFT）排名

| prompt | BF16 | NVFP4 | AWQ-INT4 | FP8 |
|---|---:|---:|---:|---:|
| 16K | `4,442 ms` | `5,728 ms` | `6,003 ms` | `6,426 ms` |
| 64K | `22,440 ms` | `27,983 ms` | `29,128 ms` | `30,964 ms` |

BF16 prefill 最快（kernel 路径成熟，无反量化开销）。量化模型中 NVFP4 ≈ AWQ-INT4，FP8 最慢。

### 5.4 Prefill vs Decode 时间占比

| profile | prompt | prefill 占比 | decode 占比 |
|---|---|---:|---:|
| `BF16` | 16K | `19.1%` | `80.9%` |
| `BF16` | 64K | `52.9%` | `47.1%` |
| `FP8` | 16K | `36.7%` | `63.3%` |
| `FP8` | 64K | `71.7%` | `28.3%` |
| `NVFP4` | 16K | `37.9%` | `62.1%` |
| `NVFP4` | 64K | `76.8%` | `23.2%` |
| `AWQ-INT4` | 16K | `42.1%` | `57.9%` |
| `AWQ-INT4` | 64K | `75.7%` | `24.3%` |

16K 场景：decode 是主导（尤其 BF16 占 80.9%）。64K 场景：prefill 变成主导（所有量化模型都 >70%）。

这意味着：

- 在 16K 交互式场景，decode 速度（TPOT）对用户体验影响最大 → AWQ-INT4 优势明显。
- 在 64K 长上下文场景，prefill（TTFT）是主要等待时间 → BF16 的 prefill 优势更重要，但量化模型的 E2E 差距缩小。

### 5.5 16K → 64K 的 TTFT 增长倍数

| profile | 16K TTFT | 64K TTFT | 倍数 |
|---|---:|---:|---:|
| `BF16` | `4,442` | `22,440` | `5.05x` |
| `FP8` | `6,426` | `30,964` | `4.82x` |
| `NVFP4` | `5,728` | `27,983` | `4.89x` |
| `AWQ-INT4` | `6,003` | `29,128` | `4.85x` |

所有 profile 的 TTFT 从 16K 到 64K 都增长约 4.8-5.0 倍，与 prompt token 增长倍数（约 4x）接近但略高，说明 prefill 不是严格线性，有额外 attention / KV cache 开销。

### 5.6 显存效率对比

以 BF16 为参照：

| profile | weight memory | 比 BF16 少用 | decode tok/s (16K) | decode tok/s (64K) | E2E (16K+512) | 判断 |
|---|---:|---:|---:|---:|---:|---|
| `BF16` | `51.1 GiB` | `0 GiB` | `27.23` | `25.56` | `23,207 ms` | 速度上限参考，256K 启动失败 |
| `FP8` | `28.87 GiB` | `22.23 GiB / 43.5%` | `46.12` | `41.78` | `17,506 ms` | A800 fallback 路径，价值较低 |
| `NVFP4` | `24.05 GiB` | `27.05 GiB / 52.9%` | `50.13` | `44.88` | `15,127 ms` | 长上下文主候选之一 |
| `AWQ-INT4` | `19.05 GiB` | `32.05 GiB / 62.7%` | `62.01` | `54.54` | `14,244 ms` | 显存效率 + 速度双重最优 |

AWQ-INT4 用最少的权重显存（19.05 GiB），却有最快的 decode 速度（62 tok/s）和最低的 E2E 延迟（14,244ms at 16K+512）。这说明在 decode 充分展开的场景下，量化不仅省显存，还能提速。

### 5.7 KV 容量收益

| profile | weight memory | KV memory | 相对 BF16 的 KV memory 增量 | 解释 |
|---|---:|---:|---:|---|
| `BF16` | `51.1 GiB` | `14.13 GiB` | 基准 | 权重太大，256K 启动失败 |
| `FP8` | `28.87 GiB` | `20.5 GiB` | `+6.37 GiB` | 权重显存下降后，KV 池更大 |
| `NVFP4` | `24.05 GiB` | `21.34 GiB` | `+7.21 GiB` | `gpu_memory_utilization=0.6`，256K max concurrency=1.32x |
| `AWQ-INT4` | `19.05 GiB` | `22.38 GiB` | `+8.25 GiB` | 最低权重显存带来最大 KV 池 |

方向上可以说：量化省下的显存，很大一部分会转化为 vLLM 可用于 KV cache 的空间。但这里不能写成严格等式，因为不同 profile 的 `gpu_memory_utilization` 不完全相同，vLLM 还会预留 runtime、CUDA graph、碎片和其他开销。

## 6. 结果解读

### 6.1 为什么 AWQ-INT4 decode 最快

AWQ-INT4 权重只有 4-bit，decode 阶段每步需要读取的权重数据量最少。在 decode 的 memory-bound 场景下（每步只生成 1 个 token，GEMM 的 compute 密度低），权重读取量直接决定 TPOT。BF16 虽然 kernel 路径成熟，但每步要读 16-bit 权重，在 decode 场景下反而吃亏。

Prefill 阶段则相反：BF16 一次性处理整个 prompt，GEMM 的 compute 密度高，kernel 路径成熟的 BF16 反而最快。量化模型的反量化开销在 prefill 阶段更明显。

### 6.2 FP8 为什么在 A800 上最弱

A800 / Ampere 没有原生 FP8 Tensor Core，当前日志提示走 fallback：

```text
Your GPU does not have native support for FP8 computation but FP8 quantization is being used.
Weight-only FP8 compression will be used leveraging the Marlin kernel.
```

因此当前 FP8 结果应写成：

> A800 上的 fallback 路径结果，不代表 H100/H200 上的原生 FP8 结果。

后续可以保留 FP8 作为对照，但不建议在当前机器上继续投入大量实验时间。

### 6.3 AWQ-INT4 和 NVFP4 怎么选

| 对比 | NVFP4 | AWQ-INT4 | 差异 |
|---|---:|---:|---:|
| 16K decode tok/s | `50.13` | `62.01` | AWQ 快 `23.7%` |
| 64K decode tok/s | `44.88` | `54.54` | AWQ 快 `21.5%` |
| 16K E2E | `15,127 ms` | `14,244 ms` | AWQ 快 `6.2%` |
| weight memory | `24.05 GiB` | `19.05 GiB` | AWQ 少 `5.0 GiB` |

在 output=512 口径下，AWQ-INT4 在 decode 速度和显存效率上都优于 NVFP4。两者差距在 decode 阶段约 20%，不是噪声能解释的。

NVFP4 仍值得保留的原因：

- 它在 `gpu_memory_utilization=0.6` 下具备单条 256K 容量余量（1.32x），已从"贴边可用"提升到"有余量"。
- NVIDIA 生态对 FP4 的原生支持在 Blackwell 上更强，未来可能有更多优化。
- 作为不同量化路线的对照，有助于理解 kernel 层差异。

### 6.4 NVFP4 的容量边界

NVFP4 使用 `gpu_memory_utilization=0.6`，256K max concurrency 为 `1.32x`，有合理余量。

> 真实请求还会包含系统提示、工具模板、输出 token、采样和 runtime 波动，工程上仍应保守理解。

## 7. 第一阶段回答的问题

| 问题 | 回答 |
|---|---|
| 哪个权重显存最低 | `AWQ-INT4`，约 `19.05 GiB` |
| 哪个 decode 最快 | `AWQ-INT4`，TPOT=16.13ms（62 tok/s at 16K） |
| 哪个 E2E 最快 | `AWQ-INT4`，14,244ms at 16K+512 |
| 哪个 prefill 最快 | `BF16`，TTFT=4,442ms at 16K |
| 从 16K 到 64K 谁下降明显 | 所有 profile 的 TTFT 都增长约 4.8-5.0x，瓶颈高度一致 |
| AWQ 是否显存低且速度快 | 是，decode 充分展开后 AWQ-INT4 是速度 + 显存双重最优 |
| NVFP4 是否比 FP8 更适合当前机器 | 是，限于当前 A800 + vLLM 路径 |
| AWQ 和 NVFP4 谁更值得继续 | AWQ-INT4 更优；NVFP4 作为长上下文候选保留 |
| output=64 和 output=512 结论是否一致 | 不一致：output=64 时 BF16 最快，output=512 时 AWQ-INT4 最快 |

## 8. 后续阶段建议

| 阶段 | 主题 | 目标 |
|---|---|---|
| 第一阶段 | Qwen3.6-27B 量化基线 | 找出 FP8 / NVFP4 / AWQ-INT4 的真实表现 |
| 第二阶段 | vLLM prefill / decode 与参数调优 | 测输出长度、TTFT、decode、`gpu_memory_utilization`、`max_num_seqs`、chunked prefill |
| 第三阶段 | MTP / speculative decoding | 专门测 decode 加速，output 拉到 `512 / 1024` |
| 第四阶段 | llama.cpp 性能分析 | 扩展到 GGUF、Q4_K_M、`n_parallel`、MTP |
| 第五阶段 | profiler 和 Kernel | 用 Nsight / torch profiler 解释核心瓶颈 |

第一阶段之后可以进入第二阶段，但不建议同时展开第三、第四、第五阶段。当前最值得做的是把"输出太短"和"prefill / decode 没拆开"这两个口径补齐。

---

## 附录 A：output=64 非 streaming 原始结果（历史参考）

> 以下为 Stage 1 最初使用 `output=64`、非 streaming 请求的测量结果。该口径下 prefill 主导端到端延迟，decode 阶段没有充分展开，"BF16 最快"的结论只在短输出场景成立。主结论已由上方 `output=512` streaming 测量修正。

### A.1 测量口径

| 项 | 值 |
|---|---|
| 后端 | `vLLM` |
| prompt tokens | `16,384` / `65,536` |
| output tokens | `64` |
| concurrency | `1` |
| warmup | `1` |
| measure | `3` |
| 计时方式 | 非 streaming，一次性请求 |

### A.2 结果

| profile | prompt tokens | actual prompt tokens | tok/s avg | latency avg | result |
|---|---:|---:|---:|---:|---|
| `vllm_qwen36-27b` | 16K | `16,384` | `9.52` | `6,721.10 ms` | success with max_model_len=131072 |
| `vllm_qwen36-27b` | 64K | `65,536` | `2.60` | `24,570.78 ms` | success with max_model_len=131072 |
| `vllm_qwen36-27b-FP8` | 16K | `16,384` | `8.20` | `7,808.08 ms` | success |
| `vllm_qwen36-27b-FP8` | 64K | `65,536` | `1.99` | `32,210.21 ms` | success |
| `vllm_qwen36-27b-nvfp4` | 16K | `16,384` | `9.03` | `7,090.06 ms` | success |
| `vllm_qwen36-27b-nvfp4` | 64K | `65,536` | `2.19` | `29,204.86 ms` | success |
| `vllm_qwen36-27b-awq-int4` | 16K | `16,384` | `9.08` | `7,051.71 ms` | success |
| `vllm_qwen36-27b-awq-int4` | 64K | `65,536` | `2.13` | `30,051.95 ms` | success |

### A.3 与 output=512 结论的差异

| 维度 | output=64 结论 | output=512 结论 | 原因 |
|---|---|---|---|
| 最快 profile | BF16 | AWQ-INT4 | output=64 太短，decode 没展开；output=512 下 decode 速度优势充分体现 |
| BF16 排名 | 16K/64K 都最快 | 16K/64K decode 都最慢 | BF16 权重大，decode 每步读取量多 |
| AWQ-INT4 定位 | 显存低但速度不突出 | 显存低且速度最快 | decode 充分展开后，轻量权重的优势显现 |

这说明 `output tokens` 的选择对实验结论有决定性影响。短输出（`64`）更偏 prefill 压力测试，长输出（`512`）更接近真实交互式场景。
