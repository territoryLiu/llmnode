# 第一阶段实验报告：Qwen3.6-27B 量化推理基线

> 文档定位：项目知识库中的 LLM serving 优化实验报告，不属于 `llmnode` 项目蓝图、契约或正式路线图。  
> 实验目标：在当前 `llmnode` 项目里，用同一 Qwen3.6-27B 模型族、同一 vLLM 后端、同一 benchmark 口径，对比 BF16、FP8、NVFP4、AWQ-INT4 的显存、速度和稳定性。  
> 更新时间：2026-06-05。  
> 当前结论状态：第一阶段已能回答“哪些量化值得继续看”，但还不能回答“真正瓶颈 kernel 是什么”。

相关专题：

- benchmark 口径见 [benchmark-methodology.md](../performance/benchmark-methodology.md)。
- KV cache 解释见 [kv-cache.md](../performance/kv-cache.md)。
- vLLM 参数见 [vllm-deep-dive.md](../serving/vllm-deep-dive.md)。
- 量化机制见 [quantization-deep-dive.md](../optimization/quantization-deep-dive.md)。
- A800 精度支持见 [hardware.md](../foundations/hardware.md)。

## 1. 一页结论

本轮固定条件：

- 后端：`vLLM`
- GPU：按 A800 / Ampere 路线理解
- `prompt tokens`：`16K / 64K`
- `output tokens`：`64`
- `concurrency`：`1`
- 统计口径：`tok/s` 指 `completion tok/s`，不是 prefill throughput，也不是纯 decode throughput

本轮最重要结论：

1. 权重显存最低的是 `AWQ-INT4`，权重显存约 `19.05 GiB`。
2. 16K 速度最高的是原始 `BF16` 临时 128K baseline，平均 `9.52 tok/s`；量化模型里 16K 最高的是 `AWQ-INT4`，平均 `9.08 tok/s`。
3. 64K 速度最高的仍是原始 `BF16` 临时 128K baseline，平均 `2.60 tok/s`；量化模型里 64K 最高的是 `NVFP4`，平均 `2.19 tok/s`。
4. `FP8` 在当前 A800 上表现最弱，主要原因不是 FP8 概念本身弱，而是 A800 没有原生 FP8 Tensor Core，vLLM 走 weight-only FP8 + Marlin fallback。
5. `AWQ-INT4` 显存最低，但 64K 速度略低于 `NVFP4`，说明“显存更低”不等于“长上下文更快”。
6. 当前第一阶段没有证明“量化能明显提速”，但证明了“量化能明显降低权重显存，并让 256K 容量边界更可行”。
7. 后续不要继续盲目扩更多量化格式，应进入第二阶段：固定少数候选 profile，拉长输出，拆分 prefill / decode / TTFT，并测试 vLLM 参数。

一句话判断：

> 这轮不是量化失败，而是实验口径更偏长上下文 prefill。量化主要解决容量和部署边界，当前速度瓶颈很可能在 prefill、attention / KV cache 访存和 vLLM 调度，而不是单纯权重显存。

对当前 A800 + 27B + 单并发长上下文场景，量化收益优先级应按下面理解：

```text
显存容量 > 上下文容量 > 并发能力 > 速度
```

不要按下面这个短推理直觉理解：

```text
速度 > 显存
```

本轮最有工程价值的发现不是“哪个最快”，而是：AWQ-INT4 用约 `19.05 GiB` 权重显存接近了 BF16 的 16K 速度，同时比 BF16 少用约 `32.05 GiB` 权重显存。这说明它在当前机器上是非常强的显存效率候选。

## 2. 当前输出是否太短

是的，`output tokens=64` 对“量化是否加速”这个问题偏短。

`16K / 64K prompt + 64 output` 的特点是：输入很长，输出很短。端到端延迟里，prefill 会占很大比例，decode 阶段只有 64 个 token，量化对 decode 或权重读取的收益不容易充分展开。因此本轮 `completion tok/s` 更像“长 prefill 压力下的短输出体验指标”，不适合直接判断某个量化格式的纯生成速度。

第二阶段应该保留 `64 output` 作为历史对照，但新增更长输出：

| output tokens | 用途 | 建议 |
|---:|---|---|
| `64` | 保留第一阶段口径，便于对比 | 继续保留 |
| `256` | 让 decode 占比变大，观察量化是否开始有收益 | 推荐加入 |
| `512` | 更接近长回答或代码生成场景 | 推荐加入 |
| `1024` | 压测 decode 稳态，但单轮耗时明显变长 | 只对 1 到 2 个候选 profile 做 |

如果目标是“几百字回答体验”，建议从 `max_tokens=512` 开始。中文几百字通常不一定需要 512 个 token，但 512 可以给模型足够输出空间，也能让 decode 阶段更有统计意义。

## 3. 实验对象

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

## 4. 实验口径

本轮 benchmark 固定：

| 项 | 值 |
|---|---|
| 后端 | `vLLM` |
| prompt tokens | `16,384` / `65,536` |
| output tokens | `64` |
| concurrency | `1` |
| warmup | `1` |
| measure | `3` |
| token 统计 | 以服务端返回的 `usage.prompt_tokens` 为准 |

本轮记录字段：

- 启动是否成功
- 权重显存
- 可用 KV cache 显存
- vLLM 启动日志中的 KV token 容量
- `completion tok/s`
- 端到端延迟
- 是否 OOM / timeout / readiness 异常

## 5. 启动侧证据

| profile | max model len | weight memory | loading time | KV memory | KV tokens | max concurrency for 262,144 tokens/request | notes |
|---|---:|---:|---:|---:|---:|---:|---|
| `vllm_qwen36-27b` | `262144` | `51.1 GiB` | `50.330138 s` | `14.13 GiB` | 未分配成功 | 不支持 262,144 | failed: needs 16.17 GiB KV cache; available 14.13 GiB; estimated max len 228,928 |
| `vllm_qwen36-27b` | `131072` | `51.1 GiB` | `7.650631 s` | `14.13 GiB` | `57,232` | `1.73x for 131,072` | temporary baseline; torch.compile 58.26s |
| `vllm_qwen36-27b-FP8` | `262144` | `28.87 GiB` | `24.820321 s` | `20.5 GiB` | `83,888` | `1.27x` | no native FP8 compute; weight-only FP8 via Marlin |
| `vllm_qwen36-27b-nvfp4` | `262144` | `24.05 GiB` | `5.441500 s` | `17.38 GiB` | `70,560` | `1.07x` | startup clean |
| `vllm_qwen36-27b-awq-int4` | `262144` | `19.05 GiB` | `25.587820 s` | `22.38 GiB` | `90,944` | `1.38x` | compressed-tensors WNA16; MarlinLinearKernel; torch.compile 70.18s |

关键解释：

- `KV memory / KV tokens` 是 vLLM 启动时规划出来的 KV cache 池容量口径，不是单条 256K 请求实际消耗的 KV。
- 不能用 `GPU KV cache size tokens` 线性外推“最大可服务 prompt tokens”或“256K 实际显存消耗”。
- `maximum concurrency for 262,144 tokens/request` 可以作为启动侧容量提示，但工程上应保守理解：`1.07x` 就是单并发贴边可用，不代表可以稳定多并发。
- 启动侧容量证据不等于 16K / 64K 速度结论，速度仍以 benchmark 表为准。

## 6. Benchmark 结果

| profile | prompt tokens | actual prompt tokens | weight memory | KV memory | KV tokens | tok/s avg | latency avg | result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `vllm_qwen36-27b` | 16K | `16,384` | `51.1 GiB` | `14.13 GiB` | `57,232` | `9.52` | `6,721.10 ms` | success with max_model_len=131072 |
| `vllm_qwen36-27b` | 64K | `65,536` | `51.1 GiB` | `14.13 GiB` | `57,232` | `2.60` | `24,570.78 ms` | success with max_model_len=131072 |
| `vllm_qwen36-27b-FP8` | 16K | `16,384` | `28.87 GiB` | `20.5 GiB` | `83,888` | `8.20` | `7,808.08 ms` | success |
| `vllm_qwen36-27b-FP8` | 64K | `65,536` | `28.87 GiB` | `20.5 GiB` | `83,888` | `1.99` | `32,210.21 ms` | success |
| `vllm_qwen36-27b-nvfp4` | 16K | `16,384` | `24.05 GiB` | `17.38 GiB` | `70,560` | `9.03` | `7,090.06 ms` | success |
| `vllm_qwen36-27b-nvfp4` | 64K | `65,536` | `24.05 GiB` | `17.38 GiB` | `70,560` | `2.19` | `29,204.86 ms` | success |
| `vllm_qwen36-27b-awq-int4` | 16K | `16,384` | `19.05 GiB` | `22.38 GiB` | `90,944` | `9.08` | `7,051.71 ms` | success |
| `vllm_qwen36-27b-awq-int4` | 64K | `65,536` | `19.05 GiB` | `22.38 GiB` | `90,944` | `2.13` | `30,051.95 ms` | success |

### 6.1 显存换速度

以 BF16 临时 baseline 为参照，量化模型的速度没有明显超过 BF16，但显存效率非常明显：

| profile | weight memory | 比 BF16 少用权重显存 | 16K tok/s | 16K 相对 BF16 | 64K tok/s | 64K 相对 BF16 | 判断 |
|---|---:|---:|---:|---:|---:|---:|---|
| `BF16` | `51.1 GiB` | `0 GiB` | `9.52` | 基准 | `2.60` | 基准 | 速度上限参考，不适合作为 256K 候选 |
| `FP8` | `28.87 GiB` | `22.23 GiB / 43.5%` | `8.20` | `-13.9%` | `1.99` | `-23.5%` | A800 fallback 路径，对当前机器价值较低 |
| `NVFP4` | `24.05 GiB` | `27.05 GiB / 52.9%` | `9.03` | `-5.1%` | `2.19` | `-15.8%` | 量化长上下文主候选之一 |
| `AWQ-INT4` | `19.05 GiB` | `32.05 GiB / 62.7%` | `9.08` | `-4.6%` | `2.13` | `-18.1%` | 显存效率冠军，性价比很高 |

这张表比单看速度更重要。AWQ-INT4 在 16K 下只比 BF16 慢约 `4.6%`，但权重显存少约 `62.7%`。因此不能说 AWQ 没意义，反而应该说：在当前 A800 上，AWQ 是非常有价值的容量型方案。

### 6.2 16K 到 64K 的下降比例

| profile | 16K tok/s | 64K tok/s | 64K / 16K |
|---|---:|---:|---:|
| `BF16` | `9.52` | `2.60` | `27.3%` |
| `FP8` | `8.20` | `1.99` | `24.3%` |
| `NVFP4` | `9.03` | `2.19` | `24.3%` |
| `AWQ-INT4` | `9.08` | `2.13` | `23.5%` |

四个 profile 从 16K 到 64K 都下降到约 `1/4`，这个一致性很有价值。它说明长上下文下大家很可能卡在相似瓶颈上：prefill、attention、KV cache、HBM 带宽或调度，而不是某一个权重量化格式独有的问题。

这个判断目前仍是推断。要把它从“合理推断”变成“已验证结论”，第二阶段需要补 TTFT / prefill / decode 拆分，最好再对代表性点采 profiler。

### 6.3 KV 容量收益

| profile | weight memory | KV memory | 相对 BF16 的 KV memory 增量 | 解释 |
|---|---:|---:|---:|---|
| `BF16` | `51.1 GiB` | `14.13 GiB` | 基准 | 权重太大，256K 启动失败 |
| `FP8` | `28.87 GiB` | `20.5 GiB` | `+6.37 GiB` | 权重显存下降后，KV 池更大 |
| `NVFP4` | `24.05 GiB` | `17.38 GiB` | `+3.25 GiB` | 当前 `gpu_memory_utilization=0.55`，256K 单请求边界贴边 |
| `AWQ-INT4` | `19.05 GiB` | `22.38 GiB` | `+8.25 GiB` | 最低权重显存带来最大 KV 池 |

方向上可以说：量化省下的显存，很大一部分会转化为 vLLM 可用于 KV cache 的空间。  
但这里不能写成严格等式，因为不同 profile 的 `gpu_memory_utilization` 不完全相同，vLLM 还会预留 runtime、CUDA graph、碎片和其他开销。

## 7. 结果解读

### 7.1 为什么提速不明显

本轮的 prompt 很长，输出很短。对于 `16K / 64K prompt + 64 output`，端到端耗时主要被 prefill、attention 访存、KV cache 写入/读取、vLLM 调度和 runtime 开销影响。

量化最直接的收益是降低权重显存和权重读取压力。但当 prompt 很长时，瓶颈很容易从权重转移到 attention / KV cache / prefill。此时即使权重显存大幅下降，端到端速度也不会按比例提升。

另一个因素是量化格式本身可能引入额外 kernel 路径或反量化开销。尤其在 A800 上，FP8 不是原生 Tensor Core 路径，vLLM 日志明确提示使用 weight-only FP8 + Marlin fallback。因此 FP8 慢不代表 FP8 在所有硬件上都慢，只代表当前硬件和当前 vLLM 路径下不占优。

### 7.2 BF16 为什么反而最快

BF16 权重显存最高，但 kernel 路径成熟，数据类型是 A800 的强项。单并发、短输出的情况下，BF16 少了量化反解和特殊 kernel 路径成本，所以速度最高是合理的。

但 BF16 的问题也很明确：它不能以当前 `max_model_len=262144` 稳定启动，单卡 A800 上不适合作为 256K 服务候选。因此 BF16 更适合当速度上限参考，而不是本阶段最终部署选择。

### 7.3 AWQ-INT4 为什么显存最低但 64K 不最快

AWQ-INT4 的权重显存最低，说明它的容量优势很强。但长上下文速度不只由权重显存决定，还受 attention、KV cache、kernel 实现、反量化路径和调度影响。

本轮 AWQ-INT4 在 16K 略快于 NVFP4，但在 64K 略慢于 NVFP4。需要注意，这个差异非常小：

| 对比 | NVFP4 | AWQ-INT4 | 差异 |
|---|---:|---:|---:|
| 16K tok/s | `9.03` | `9.08` | AWQ 快约 `0.6%` |
| 64K tok/s | `2.19` | `2.13` | NVFP4 快约 `2.8%` |
| weight memory | `24.05 GiB` | `19.05 GiB` | AWQ 少约 `5.0 GiB` |

在 `measure=3` 的口径下，`2.8%` 很可能接近测试噪声，不能过度解读为“NVFP4 明确快于 AWQ”。更稳妥的说法是：

> 当前 16K / 64K 单并发短输出口径下，AWQ-INT4 和 NVFP4 速度接近；AWQ-INT4 显存效率更好，NVFP4 可作为长上下文候选继续保留。

### 7.4 NVFP4 当前为什么值得继续看

NVFP4 的权重显存明显低于 BF16，64K 又是量化模型里最快的一个。同时它在当前 `gpu_memory_utilization=0.55` 下具备单条 256K 容量边界。

它的缺点是并发余量贴边：`Maximum concurrency for 262,144 tokens/request: 1.07x`。工程上这更像“单并发可用”，不是“可稳定服务多并发”。第二阶段如果继续测 NVFP4，应重点看 `gpu_memory_utilization=0.55 / 0.6` 的容量、速度和稳定性差异。

更谨慎的表述应该是：

> NVFP4 在当前配置下接近 256K 单请求边界，已经不是“轻松支持 256K”。真实请求还会包含系统提示、工具模板、输出 token、采样和 runtime 波动，因此工程上要按贴边配置处理。

### 7.5 FP8 当前应该如何看

FP8 在当前机器上不适合作为主线优化对象。原因是 A800 / Ampere 没有原生 FP8 Tensor Core，当前日志提示走 fallback：

```text
Your GPU does not have native support for FP8 computation but FP8 quantization is being used.
Weight-only FP8 compression will be used leveraging the Marlin kernel.
```

因此当前 FP8 结果应写成：

> A800 上的 fallback 路径结果，不代表 H100/H200 上的原生 FP8 结果。

后续可以保留 FP8 作为对照，但不建议在当前机器上继续投入大量实验时间。

## 8. 合理与不合理的地方

合理的地方：

1. 第一阶段只选 BF16、FP8、NVFP4、AWQ-INT4，变量足够少，能形成清楚基线。
2. 先测 16K 和 64K，而不是一开始就测 256K，节奏合理。
3. 用服务端 `usage.prompt_tokens` 校准实际 token 数，这比只信本地 tokenizer 更可靠。
4. 把 FP8 的 A800 fallback 前提写清楚，避免误判 FP8 本身。
5. 把 BF16 作为速度 baseline，而不是强行让它参与 256K 对比，这个判断合理。

需要修正或后续补强的地方：

1. `output tokens=64` 太短，不足以判断量化对 decode 的收益。
2. `KV tokens` 不能线性外推 256K 实际 KV 消耗，应只作为 vLLM 启动侧容量指标。
3. 当前缺少 TTFT、prefill time、decode time 拆分，所以还不能严谨解释瓶颈到底占比多少。
4. BF16 使用 `max_model_len=131072` 临时覆盖，和量化 profile 的 `262144` 不完全同口径；报告里必须继续标注。
5. 当前只测单并发，不能推导服务化吞吐、多用户稳定性或队列表现。
6. 当前没有 Nsight / torch profiler trace，kernel 层原因仍是推断，不是已验证事实。
7. `NVFP4 64K 最高` 这句话技术上正确，但容易误导；因为它只比 AWQ-INT4 快约 `2.8%`，当前更应写成 `NVFP4 ≈ AWQ-INT4`。

## 9. 第一阶段回答的问题

| 问题 | 回答 |
|---|---|
| 哪个权重显存最低 | `AWQ-INT4`，约 `19.05 GiB` |
| 哪个 16K 速度最高 | 全部 profile 中是 BF16；量化模型中是 `AWQ-INT4` |
| 哪个 64K 速度最高 | 全部 profile 中是 BF16；量化模型中是 `NVFP4` |
| 从 16K 到 64K 谁下降明显 | 所有 profile 都下降到约 `1/4`，说明瓶颈高度一致 |
| AWQ 是否显存低但速度不一定快 | 是 |
| NVFP4 是否比 FP8 更适合当前机器 | 是，限于当前 A800 + vLLM 路径 |
| AWQ 和 NVFP4 谁更值得继续 | 两者都值得；AWQ 显存效率更高，NVFP4 作为长上下文候选保留 |

## 10. 第二阶段实验报告应该做什么

第二阶段主题：

> 固定少数候选 profile，区分 prefill 和 decode，验证 vLLM 参数对长上下文性能和容量边界的影响。

建议第二阶段文件：

- [stage2-vllm-prefill-decode.md](./stage2-vllm-prefill-decode.md)

第二阶段不要继续扩大到很多量化格式。建议只保留：

| profile | 角色 |
|---|---|
| `vllm_qwen36-27b` | BF16 速度上限参考，只测能稳定启动的上下文 |
| `vllm_qwen36-27b-nvfp4` | 长上下文主候选 |
| `vllm_qwen36-27b-awq-int4` | 最低显存候选 |

`FP8` 在第二阶段不建议作为主线继续投入，只保留一两个对照点即可。vLLM 官方文档也说明，W8A8 FP8 主要面向 Hopper / Ada，Ampere 上是 W8A16 weight-only FP8 + Marlin 路径；这和本轮日志完全一致。

建议实验矩阵：

| 维度 | 值 |
|---|---|
| prompt tokens | `4K / 16K / 64K / 128K`，NVFP4/AWQ 可加 `256K` |
| output tokens | `64 / 256 / 512`，候选最少再测一次 `1024` |
| concurrency | 第一轮仍用 `1`，第二轮再测 `2 / 4` |
| `gpu_memory_utilization` | NVFP4 测 `0.55 / 0.6`，AWQ 测 `0.55 / 0.6` |
| `max_num_seqs` | `1 / 4`，观察单并发是否受调度配置影响 |
| chunked prefill | 如果当前 vLLM 参数可控，做开关对比 |

第二阶段必须新增记录：

- TTFT
- prefill 耗时或近似 prefill throughput
- decode throughput
- end-to-end latency
- GPU 显存峰值
- vLLM `GPU KV cache usage` 峰值
- 错误率 / timeout / 503
- 启动日志中的 KV cache 和 maximum concurrency

建议新增三个小实验：

| 实验 | 固定项 | 变量 | 目的 |
|---|---|---|---|
| AWQ 并发阶梯 | `AWQ-INT4`、固定 prompt/output | `concurrency=1/2/4/8`，稳定后再考虑 `16` | 看最低显存方案能否换来更好服务吞吐 |
| AWQ 上下文阶梯 | `AWQ-INT4`、`concurrency=1` | `16K/32K/64K/128K/192K/256K` | 找真实上下文边界和速度曲线 |
| FP8 KV cache | 优先 `AWQ-INT4` 或 `NVFP4` | `kv_cache_dtype=auto/fp8` | 验证瓶颈转向 KV 后，KV cache 量化是否比继续权重量化更有收益 |

`FP8 KV cache` 是值得单独开的方向，但要先确认当前 vLLM 镜像、CUDA、模型和精度组合是否支持，并补质量回归。KV 量化可能提升容量和并发，但也可能引入精度风险，不能只看速度。

第二阶段最小完成标准：

1. 能说明 `output=64` 和 `output=512` 下，量化收益是否不同。
2. 能说明 NVFP4 的 `gpu_memory_utilization=0.55` 和 `0.6` 哪个更适合当前单卡部署。
3. 能说明 AWQ-INT4 是否只是省显存，还是在较长 decode 下也有速度优势。
4. 能说明当前主要瓶颈更像 prefill、decode、KV cache 还是调度。
5. 至少对一个代表性点补 profiler，例如 `NVFP4 + 64K prompt + 512 output`。

## 11. 后续阶段建议

| 阶段 | 主题 | 目标 |
|---|---|---|
| 第一阶段 | Qwen3.6-27B 量化基线 | 找出 FP8 / NVFP4 / AWQ-INT4 的真实表现 |
| 第二阶段 | vLLM prefill / decode 与参数调优 | 测输出长度、TTFT、decode、`gpu_memory_utilization`、`max_num_seqs`、chunked prefill |
| 第三阶段 | MTP / speculative decoding | 专门测 decode 加速，output 拉到 `512 / 1024` |
| 第四阶段 | llama.cpp 性能分析 | 扩展到 GGUF、Q4_K_M、`n_parallel`、MTP |
| 第五阶段 | profiler 和 Kernel | 用 Nsight / torch profiler 解释核心瓶颈 |

第一阶段之后可以进入第二阶段，但不建议同时展开第三、第四、第五阶段。当前最值得做的是把“输出太短”和“prefill / decode 没拆开”这两个口径补齐。
