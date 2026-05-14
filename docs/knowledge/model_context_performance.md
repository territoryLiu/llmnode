# 模型上下文长度与单并发性能记录

本文档记录各模型在当前机器上的实际上下文长度可用性与单并发性能表现，作为长期参考层使用。

## 测试环境模板

- GPU:
- 后端:
- 部署参数:
- 测试日期:
- 测试方式:
- 备注:

---

## 模型记录模板

### `<模型路径>`

#### 部署参数

- served model:
- backend:
- 关键参数:

#### 可用性结论

- 最大已验证上下文:
- 是否单条通过 256K:
- 备注:

#### KV cache 与并发估算（可选）

- Available KV cache memory:
- GPU KV cache size:
- `256K tokens/request` 理论最大并发:
- 备注:

#### 单并发阶梯测试

| 阶梯 | 实测 prompt tokens | completion tokens | 总时延 ms | 估算 completion tok/s | 结论 |
|------|--------------------|-------------------|-----------|------------------------|------|
| 4K   |                    |                   |           |                        |      |
| 32K  |                    |                   |           |                        |      |
| 64K  |                    |                   |           |                        |      |
| 128K |                    |                   |           |                        |      |
| 256K |                    |                   |           |                        |      |

#### 观察

- 

---

## 当前机器

- GPU: `A800 80GB`
- 后端: `vLLM`
- 测试日期: `2026-05-13 ~ 2026-05-14`
- 测试方式: 单并发，请求直接打到 `http://127.0.0.1:15673/v1/chat/completions`
- 备注:
  - 本文时延包含完整请求往返，不仅是 decode 阶段
  - 当前 `Qwen3.6-35B-A3B-FP8` 会把推理内容写入 `reasoning` 字段，因此这组 `completion_tokens` 主要反映推理输出长度
  - `completion tok/s` 按 `completion_tokens / latency_seconds` 估算

### `models/Qwen/Qwen3.6-27B`

#### 部署参数

- served model: 未继续保留为当前正式在线配置
- backend: `vLLM`
- 关键参数:
  - `max_model_len=262144`
  - `gpu_memory_utilization=0.75`
  - `gpu_memory_utilization=0.85`

#### 可用性结论

- 最大已验证上下文: 未成功达到 `256K`
- 是否单条通过 256K: 否
- 备注:
  - `0.75 + 256K` 失败，更早，估算上限约 `98784`
  - `0.85 + 256K` 仍失败，但更接近成功，估算上限约 `228928`
  - vLLM 日志给出的关键信息：
    - available KV cache memory = `14.13 GiB`
    - `262144` 需要 `16.17 GiB`

#### 单并发阶梯测试

| 阶梯 | 实测 prompt tokens | completion tokens | 总时延 ms | 估算 completion tok/s | 结论 |
|------|--------------------|-------------------|-----------|------------------------|------|
| 4K   | 未测 | 未测 | 未测 | 未测 | 历史记录仅覆盖 256K 边界失败 |
| 32K  | 未测 | 未测 | 未测 | 未测 | 历史记录仅覆盖 256K 边界失败 |
| 64K  | 未测 | 未测 | 未测 | 未测 | 历史记录仅覆盖 256K 边界失败 |
| 128K | 未测 | 未测 | 未测 | 未测 | 历史记录仅覆盖 256K 边界失败 |
| 256K | 失败 | - | - | - | 未通过 |

#### 观察

- 27B 在这台 `A800 80GB` 上并不是“只要把 `gpu_memory_utilization` 提高到 0.85 就能稳定单条 256K”。
- 对这个模型，如果目标是稳定单条 256K，当前记录不建议再把它作为正式默认部署。

### `models/Qwen/Qwen3.6-27B-FP8`

#### 部署参数

- served model: `qwen36-27b-fp8`
- backend: `vLLM`
- 关键参数:
  - `max_model_len=262144`
  - `gpu_memory_utilization=0.65`
  - `max_num_seqs=4`
  - `max_tokens=64`
  - `shm_size=16g`
  - 单并发

#### 可用性结论

- 最大已验证上下文: `262000 prompt tokens`
- 是否单条通过 256K: 直连 `vLLM` 是；经 `gateway` 否
- 备注:
  - 当前在线实例 `qwen36-27b-fp8` 直连 `vLLM` 可完成单条 `256K`
  - 本轮直连 `4K / 32K / 64K / 128K / 256K` 五档都返回 `200 OK`
  - 经 `gateway` 的 `4K / 32K / 64K / 128K` 返回 `200 OK`
  - 经 `gateway` 的 `256K` 在约 `120067 ms` 返回 `500`
  - 这组返回里 `content` 基本为空，`completion_tokens=64` 主要反映推理输出长度

#### KV cache 与并发估算

- Available KV cache memory: `20.5 GiB`
- GPU KV cache size: `83,888 tokens`
- `256K tokens/request` 理论最大并发: `1.27x`
- 备注:
  - 以上数字来自当前在线实例启动日志，不是手工估算
  - 工程上更合理的规划是：
    - `256K` 按 `1` 个请求规划
    - `128K` 约 `2` 个
    - `64K` 理论 `4+`，但会被当前 `max_num_seqs=4` 卡到 `4` 个
  - 实际可用并发还会被输出长度、工具调用、碎片和 warmup 抖动进一步吃掉一部分

#### 单并发阶梯测试

| 阶梯 | 实测 prompt tokens | completion tokens | 总时延 ms | 估算 completion tok/s | 结论 |
|------|--------------------|-------------------|-----------|------------------------|------|
| 4K   | 4096   | 64 | 2815.66   | 22.73 | 通过 |
| 32K  | 32768  | 64 | 14540.58  | 4.40  | 通过 |
| 64K  | 65536  | 64 | 31212.95  | 2.05  | 通过 |
| 128K | 131072 | 64 | 74564.70  | 0.86  | 通过 |
| 256K | 262000 | 64 | 199282.12 | 0.32  | 通过 |

#### 单并发阶梯测试（经 `gateway`）

| 阶梯 | 实测 prompt tokens | completion tokens | 总时延 ms | 估算 completion tok/s | 结论 |
|------|--------------------|-------------------|-----------|------------------------|------|
| 4K   | 4096   | 64 | 3023.31   | 21.17 | 通过 |
| 32K  | 32768  | 64 | 15020.06  | 4.26  | 通过 |
| 64K  | 65536  | 64 | 31972.00  | 2.00  | 通过 |
| 128K | 131072 | 64 | 75674.43  | 0.85  | 通过 |
| 256K | 262000 | -  | 120067.00 | -     | 失败，`gateway` 上游读超时后返回 `500` |

#### 观察

- 相比历史 `models/Qwen/Qwen3.6-27B` 记录，这个 `FP8` 版本在当前 `0.65` 配置下已经能真正完成单条 `256K`。
- 但它的长上下文性能明显不理想：`4K -> 256K` 的单并发 `completion tok/s` 从约 `22.73` 下降到约 `0.32`，`256K` 完整请求时延接近 `199s`。
- 从纯性能结果看，这个 `27B-FP8` 虽然参数规模更小，但在这台机器上的长上下文体验明显慢于当前正式默认的 `Qwen3.6-35B-A3B-FP8`。
- 本轮日志里可见 `GPU KV cache usage` 高点约 `15.7%`，过程中没有出现 OOM 或容器重启。
- `gateway` 到 `128K` 为止只增加了约 `0.21s / 0.48s / 0.76s / 1.11s` 的额外时延，代理层本身不是短到中长上下文的主要瓶颈。
- `gateway 256K` 的失败不是模型本身失败，而是控制面当前 `llmnode/proxy/backend.py` 中 `post_json()` 的 `httpx.AsyncClient(timeout=120)` 先触发了 `ReadTimeout`，随后对外表现为 `500 Internal Server Error`。
- 结论上，这个配置更像是“模型本体能扛住 256K”的容量证明，不适合作为经网关对外提供 `256K` 长上下文服务的当前正式体验基线。

### `models/Qwen/Qwen3.6-35B-A3B-FP8`

#### 部署参数

- served model: `qwen36-35b-a3b-fp8`
- backend: `vLLM`
- 关键参数:
  - `max_model_len=262144`
  - `gpu_memory_utilization=0.65`
  - `max_tokens=64`
  - 单并发

#### 可用性结论

- 最大已验证上下文: `262000 prompt tokens`
- 是否单条通过 256K: 是
- 备注:
  - 当前在线配置可稳定返回 `256K` 单条请求
  - 本轮 5 个阶梯都返回 `200 OK`

#### 单并发阶梯测试

| 阶梯 | 实测 prompt tokens | completion tokens | 总时延 ms | 估算 completion tok/s | 结论 |
|------|--------------------|-------------------|-----------|------------------------|------|
| 4K   | 4096   | 64 | 681.51   | 93.91 | 通过 |
| 32K  | 32768  | 64 | 2839.24  | 22.54 | 通过 |
| 64K  | 65536  | 64 | 6489.18  | 9.86  | 通过 |
| 128K | 131072 | 64 | 17453.12 | 3.67  | 通过 |
| 256K | 262000 | 64 | 55036.84 | 1.16  | 通过 |

#### 单并发阶梯测试（经 `gateway`）

| 阶梯 | 实测 prompt tokens | completion tokens | 总时延 ms | 估算 completion tok/s | 结论 |
|------|--------------------|-------------------|-----------|------------------------|------|
| 4K   | 4096   | 64 | 762.53   | 83.93 | 通过 |
| 32K  | 32768  | 64 | 2909.74  | 22.00 | 通过 |
| 64K  | 65536  | 64 | 6562.00  | 9.75  | 通过 |
| 128K | 131072 | 64 | 17551.34 | 3.65  | 通过 |
| 256K | 262000 | 64 | 55068.25 | 1.16  | 通过 |

#### 观察

- 从 `4K -> 256K`，时延增长非常明显，单并发 `completion tok/s` 从约 `93.91` 下降到约 `1.16`。
- 当前配置的瓶颈不是“能不能过 256K”，而是“256K 虽然能过，但完整请求时延已经到约 `55s`”。
- 这组结果更适合作为“长上下文可用性验证”和“极限容量记录”，不适合作为日常交互体验基线。
- 长上下文测试期间 vLLM 日志中可见：
  - `GPU KV cache usage` 最高约 `13.4%`
  - prompt throughput 在不同阶段有波动，但未出现 OOM 或容器重启
- `gateway` 路径和直连 `vLLM` 的结果非常接近：
  - `4K` 约多 `81 ms`
  - `32K` 约多 `71 ms`
  - `64K` 约多 `73 ms`
  - `128K` 约多 `98 ms`
  - `256K` 基本可视为无额外差异
- 在当前单并发配置下，控制面代理层不是长上下文时延的主要瓶颈。

### `models/Qwen/Qwen3.6-35B-A3B-GGUF/qwen36-35b-a3b-q4km.gguf`

#### 部署参数

- served model: `qwen36-35b-a3b-q4km.gguf`
- backend: `llama.cpp`
- 关键参数:
  - `image_name=ghcr.io/ggml-org/llama.cpp:full-cuda`
  - `ctx_size=262144`
  - `n_parallel=1`
  - `n_gpu_layers=-1`
  - `max_tokens=64`

#### 可用性结论

- 最大已验证上下文: `262000 prompt tokens`
- 是否单条通过 256K: 是
- 备注:
  - 在 `ctx_size=262144, n_parallel=1` 下，单条 `256K` 可通过
  - `llama.cpp` 日志确认：
    - `n_ctx=262144`
    - `n_ctx_seq=262144`
  - 测试期间 GPU 显存占用约 `26.4 GiB`

#### 单并发阶梯测试

| 阶梯 | 实测 prompt tokens | completion tokens | 总时延 ms | 估算 completion tok/s | 结论 |
|------|--------------------|-------------------|-----------|------------------------|------|
| 4K   | 4096   | 64 | 5498.75  | 11.64 | 通过 |
| 32K  | 32768  | 64 | 7767.31  | 8.24  | 通过 |
| 64K  | 65536  | 64 | 10031.80 | 6.38  | 通过 |
| 128K | 131072 | 64 | 24153.03 | 2.65  | 通过 |
| 256K | 262000 | 64 | 68353.48 | 0.94  | 通过 |

#### 观察

- 这组结果是在“优先保证单条 256K 可用”的 `ctx_size=262144, n_parallel=1` 配置下测得，不适合直接拿去和面向日常短请求优化的配置比较。
- 相比当前 `vLLM + FP8` 配置，`llama.cpp + q4km` 在同样单并发、长上下文条件下整体更慢：
  - `4K`: 约 `5.50s` vs `0.68s`
  - `32K`: 约 `7.77s` vs `2.84s`
  - `64K`: 约 `10.03s` vs `6.49s`
  - `128K`: 约 `24.15s` vs `17.45s`
  - `256K`: 约 `68.35s` vs `55.04s`
- 本轮 `llama.cpp` 返回中 `has_reasoning=false`，没有像当前 `vLLM` 一样把推理过程单独放进 `reasoning` 字段。
- 结论上，`llama.cpp q4km` 也能扛住单条 `256K`，但在这台机器上的长上下文性能仍弱于当前正式 `vLLM + FP8` 配置。

### `models/Qwen/Qwen3.6-35B-A3B-FP8`（SGLang 启动观测）

#### 部署参数

- served model: `qwen36-35b-a3b-fp8`
- backend: `SGLang`
- 关键参数:
  - `image_name=lmsysorg/sglang:v0.5.11-cu129-runtime`
  - `reasoning_parser=qwen3`
  - 观测轮次 A:
    - `mem_fraction_static=0.85`
    - `max_running_requests=4`
  - 观测轮次 B:
    - `mem_fraction_static=0.65`
    - `max_running_requests=1`

#### 可用性结论

- 最大已验证上下文: 未进入正式请求阶段
- 是否单条通过 256K: 未验证
- 备注:
  - 两轮观测都完成了镜像启动、参数下发、权重加载与 KV cache 分配
  - 但在当前机器与当时运行环境下，`/v1/models` 在等待窗口内始终未进入稳定可服务状态
  - 因此本轮没有进入 `4K / 32K / 64K / 128K / 256K` 五档正式压测

#### 单并发阶梯测试

| 阶梯 | 实测 prompt tokens | completion tokens | 总时延 ms | 估算 completion tok/s | 结论 |
|------|--------------------|-------------------|-----------|------------------------|------|
| 4K   | 未测 | 未测 | 未测 | 未测 | 后端未稳定就绪 |
| 32K  | 未测 | 未测 | 未测 | 未测 | 后端未稳定就绪 |
| 64K  | 未测 | 未测 | 未测 | 未测 | 后端未稳定就绪 |
| 128K | 未测 | 未测 | 未测 | 未测 | 后端未稳定就绪 |
| 256K | 未测 | 未测 | 未测 | 未测 | 后端未稳定就绪 |

#### 观察

- 轮次 A（`0.85 / 4`）：
  - `Load weight end` 后日志显示：
    - `KV Cache is allocated. #tokens: 901428`
    - `Capture cuda graph bs [1, 2, 4]`
  - 观察窗口内未等到 `ready`，启动成本明显偏高
- 轮次 B（`0.65 / 1`）：
  - 参数已确认生效：
    - `mem_fraction_static=0.65`
    - `max_running_requests=1`
  - `Load weight end` 后日志显示：
    - `KV Cache is allocated. #tokens: 465585`
    - `Capture cuda graph bs [1]`
  - 相比 `0.85 / 4`，单并发配置明显减轻了 KV cache 与图捕获规模
- 但在轮次 B 中，`curl http://127.0.0.1:15673/v1/models` 仍返回：
  - `Recv failure: Connection reset by peer`
  - 容器进程仍存活，不是直接崩溃退出
- 观测期间 GPU 上还存在额外计算进程：
  - `/home/pengyao/.conda/envs/yolov8_chem/bin/python`
  - 显存占用约 `20.6 GiB`
- 这说明当前环境下，SGLang 的问题不是“参数没有生效”，而是“即使降到 `0.65 / 1`，在现有显存竞争和 warmup 行为下，服务仍未在本轮观察窗口内稳定开放”
- 如果后续还要继续推进 SGLang 正式压测，更合理的下一步应是：
  - 先清空外部 GPU 占用
  - 再单独复测 `0.65 / 1`
  - 必要时再评估是否关闭或进一步缩减 CUDA graph 相关启动负担

## 补充说明

### `models/Qwen/Qwen3-VL-8B-Instruct-FP8` 的 20G 显存预算判断

- `Qwen3.6-35B-A3B-FP8` 在本文能跑 `256K`，对应配置可参考 `models/Qwen/Qwen3.6-35B-A3B-FP8/config.json`
- 这个模型的 `text_config` 里有大量 `linear_attention`，而且 `num_key_value_heads=2`
- `Qwen3-VL-8B-Instruct-FP8` 对应 `models/Qwen/Qwen3-VL-8B-Instruct-FP8/config.json`
- 它是标准注意力路径，`num_key_value_heads=8`、`num_hidden_layers=36`、`head_dim=128`、`max_position_embeddings=262144`
- 这会直接导致两个模型的 KV cache 成本完全不是一个量级，因此会出现“35B A3B 更大却能过 256K，8B VL 更小却扛不住 256K”的反直觉结果
- 容器日志已经给出关键信息：
  - 当前 `262144` 需要约 `36.0 GiB` KV cache
  - 现在实际可用 KV cache 只有约 `6.95 GiB`
- 因此这不是文档和程序冲突，而是两个模型本身的长上下文成本曲线完全不同
- 如果预算仍要压在 `20G` 显存附近，更合理的做法是把 `max_model_len` / `ctx_size` 从 `262144` 收到 `49152`
