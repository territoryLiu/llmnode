# 模型长上下文性能查询

本文档只保留可查询的结论，不再写实验过程。  
组织方式是“一个模型一节”，每个模型把下面这些信息放在一起：

- 当前部署参数
- 权重显存
- 可用 KV 显存
- KV token 容量
- `256K` 工程建议并发
- `4K / 32K / 64K / 128K / 172K / 256K` 的 `completion tok/s`
- 最大已验证上下文
- 是否单条 `256K` 可过
- 当前缺失哪些关键指标

## 1. 查询规则

- 并发只写工程建议值，不写理论极限值
- 没有实测的数据一律写 `未测`
- `tok/s` 统一指 `completion tok/s`
- 如果某个值只是容量推断，不是正式压测结果，会明确写成“容量上判断可过”

## 2. `models/Qwen/Qwen3.6-27B`

### 2.1 基本信息

- 后端：`vLLM`
- served model：未保留为当前正式在线配置
- 关键部署参数：
  - `max_model_len=262144`
  - `gpu_memory_utilization=0.75 / 0.85`

### 2.2 显存与 KV

- 权重显存：`未测`
- 可用 KV 显存：`14.13 GiB`
- KV token 容量：`未测`

### 2.3 并发与上下文

- `256K` 工程建议并发：`0`
- 最大已验证上下文：未成功达到 `256K`
- `256K` 单条可过：否

### 2.4 各档 token 速度

- `4K`：`未测`
- `32K`：`未测`
- `64K`：`未测`
- `128K`：`未测`
- `172K`：`未测`
- `256K`：`未测`

### 2.5 当前结论

- 当前只保留 `256K` 边界失败记录：
  - `gpu_memory_utilization=0.75` 时估算上限约 `98784`
  - `gpu_memory_utilization=0.85` 时仍未稳定通过 `256K`，估算上限约 `228928`
- 当前记录不支持把它作为稳定 `256K` 的正式默认部署

### 2.6 仍缺指标

- 权重显存
- KV token 容量
- `4K / 32K / 64K / 128K / 172K / 256K` 单并发速度
- `256K` 端到端总时延

## 3. `models/Qwen/Qwen3.6-27B-FP8`

### 3.1 基本信息

- 后端：`vLLM`
- served model：`qwen36-27b-fp8`
- 关键部署参数：
  - `max_model_len=262144`
  - `gpu_memory_utilization=0.65`
  - `max_num_seqs=4`
  - `max_tokens=64`
  - 单并发

### 3.2 显存与 KV

- 权重显存：`未测`
- 可用 KV 显存：`20.5 GiB`
- KV token 容量：`83,888 tokens`
- 长请求过程观测：
  - `GPU KV cache usage` 高点约 `15.7%`

### 3.3 并发与上下文

- `256K` 工程建议并发：`1`
- 最大已验证上下文：`262000 prompt tokens`
- `256K` 单条可过：
  - 直连 `vLLM`：是
  - 经 `gateway`：否

### 3.4 各档 token 速度

- `4K`：`22.73`
- `32K`：`4.40`
- `64K`：`2.05`
- `128K`：`0.86`
- `172K`：`未测`
- `256K`：`0.32`

### 3.5 补充说明

- 经 `gateway` 的 `256K` 在约 `120067 ms` 返回 `500`
- 关键结论不是“能不能扛住 `256K`”，而是“虽然模型本体能过，但长上下文体验明显偏慢”
- 这组更像容量证明，不适合作为经网关对外提供 `256K` 服务的正式体验基线

### 3.6 仍缺指标

- 权重显存
- `172K` 单并发速度
- `256K` 直连与 `gateway` 分路径首 token 时延
- 稳态多并发下的错误率 / 超时率

## 4. `models/Qwen/Qwen3.6-35B-A3B-FP8`

### 4.1 基本信息

- 后端：`vLLM`
- served model：`qwen36-35b-a3b-fp8`
- 关键部署参数：
  - `max_model_len=262144`
  - `gpu_memory_utilization=0.65`
  - `max_tokens=64`
  - 单并发

### 4.2 显存与 KV

- 权重显存：`未测`
- 可用 KV 显存：`未测`
- KV token 容量：`未测`
- 长请求过程观测：
  - `GPU KV cache usage` 最高约 `13.4%`

### 4.3 并发与上下文

- `256K` 工程建议并发：`未测`
- 最大已验证上下文：`262000 prompt tokens`
- `256K` 单条可过：是

### 4.4 各档 token 速度

- `4K`：`93.91`
- `32K`：`22.54`
- `64K`：`9.86`
- `128K`：`3.67`
- `172K`：`未测`
- `256K`：`1.16`

### 4.5 补充说明

- 当前正式默认长上下文性能基线
- `gateway` 与直连结果非常接近，代理层不是主要瓶颈 
- 当前瓶颈不是“能不能过 `256K`”，而是“`256K` 虽然能过，但完整请求时延已经到约 `55s`”

### 4.6 仍缺指标

- 权重显存
- 可用 KV 显存
- KV token 容量
- `256K` 工程建议并发
- `172K` 单并发速度
- `gateway` 路径下各档首 token 时延

## 5. `models/Qwen/Qwen3.6-35B-A3B-AWQ-4bit`

### 5.1 基本信息

- 后端：`vLLM`
- served model：`qwen36-35b-a3b-awq-4bit`
- 关键部署参数：
  - `max_model_len=262144`
  - `gpu_memory_utilization=0.4`
  - `max_num_seqs=4`
  - `shm_size=16g`

### 5.2 显存与 KV

- 权重显存：`22.4 GiB`
- 可用 KV 显存：`15.03 GiB`
- KV token 容量：`196,416 tokens`
- 单条 `256K` 的近似 KV 成本：约 `5.08 GiB`
- 本轮 benchmark 过程观测：
  - 容器进程显存约 `32686 MiB`
  - 整机 GPU 已用显存约 `32709 MiB`

### 5.3 并发与上下文

- `256K` 工程建议并发：`2`
- 最大已验证上下文：`262000 prompt tokens`
- `256K` 单条可过：是

### 5.4 各档 token 速度

- `4K`
  - 实际 prompt tokens：`4096`
  - `completion tok/s`：`avg 89.41` / `median 89.58` / `min 88.95` / `max 89.72`
  - 端到端时延：`avg 715.78 ms` / `median 714.47 ms` / `min 713.37 ms` / `max 719.50 ms`
- `32K`
  - 实际 prompt tokens：`32768`
  - `completion tok/s`：`avg 23.91` / `median 24.02` / `min 23.34` / `max 24.35`
  - 端到端时延：`avg 2678.00 ms` / `median 2664.18 ms` / `min 2627.90 ms` / `max 2741.91 ms`
- `64K`
  - 实际 prompt tokens：`65536`
  - `completion tok/s`：`avg 10.47` / `median 10.47` / `min 10.44` / `max 10.50`
  - 端到端时延：`avg 6112.86 ms` / `median 6114.27 ms` / `min 6096.82 ms` / `max 6127.49 ms`
- `128K`
  - 实际 prompt tokens：`131072`
  - `completion tok/s`：`avg 3.76` / `median 3.76` / `min 3.75` / `max 3.78`
  - 端到端时延：`avg 17003.87 ms` / `median 17025.99 ms` / `min 16918.79 ms` / `max 17066.82 ms`
- `172K`
  - 实际 prompt tokens：`176128`
  - `completion tok/s`：`avg 2.31` / `median 2.31` / `min 2.31` / `max 2.32`
  - 端到端时延：`avg 27659.83 ms` / `median 27667.46 ms` / `min 27613.58 ms` / `max 27698.43 ms`
- `256K`
  - 实际 prompt tokens：`262000`
  - `completion tok/s`：`avg 1.18` / `median 1.18` / `min 1.18` / `max 1.18`
  - 端到端时延：`avg 54236.95 ms` / `median 54210.02 ms` / `min 54130.59 ms` / `max 54370.25 ms`

### 5.5 补充说明

- 当前已补齐单并发阶梯速度，现阶段既是容量表，也是单并发交互性能表
- 本轮统计口径：
  - `warmup_runs=1`
  - `measured_runs=3`
  - 文档中的 `avg / median / min / max` 仅统计 `measure` 轮次，不包含 warmup
- 理论值接近 `3x`，但工程上不建议按 `3` 个 `256K` 常态规划
- 如果只按“权重显存 + 单条 `256K` KV”静态相加，单条 `256K` 约需 `27.48 GiB`
- 因此更准确的说法是：
  - `30 GiB` 接近可行边界
  - 但不属于有明显安全余量的预算
- 本轮单并发 benchmark 结果：
  - `4K -> 256K` 的 `completion tok/s` 均值从 `89.41` 下降到 `1.18`
  - `172K` 的 `completion tok/s` 均值约 `2.31`
  - `256K` 端到端时延均值约 `54.24s`
- 和当前 `35B-A3B-FP8` 基线相比：
  - `4K` 略慢（`89.41` vs `93.91`）
  - `32K` 基本同量级（`23.91` vs `22.54`）
  - `64K / 128K / 172K / 256K` 仍需要结合更多轮次判断是否稳定占优

### 5.6 仍缺指标

- `gateway` 路径结果
- 长请求稳定性观测
- 多并发压测结果

## 6. `models/Qwen/Qwen3.6-35B-A3B-GGUF/qwen36-35b-a3b-q4km.gguf`

### 6.1 基本信息

- 后端：`llama.cpp`
- served model：`qwen36-35b-a3b-q4km.gguf`
- 关键部署参数：
  - `ctx_size=262144`
  - `n_parallel=1`
  - `n_gpu_layers=-1`
  - `max_tokens=64`

### 6.2 显存与 KV

- 权重显存：`未测`
- 可用 KV 显存：`未测`
- KV token 容量：`未测`
- 观测总显存：约 `26.4 GiB`

### 6.3 并发与上下文

- `256K` 工程建议并发：`1`
- 最大已验证上下文：`262000 prompt tokens`
- `256K` 单条可过：是

### 6.4 各档 token 速度

- `4K`：`11.64`
- `32K`：`8.24`
- `64K`：`6.38`
- `128K`：`2.65`
- `172K`：`未测`
- `256K`：`0.94`

### 6.5 补充说明

- 这组结果是在 `ctx_size=262144, n_parallel=1` 下测得
- 它回答的是“能不能优先保证单条 `256K`”，不是“日常短请求是否最佳”
- 相比当前 `vLLM + FP8` 配置，在同样长上下文单并发条件下整体更慢

### 6.6 仍缺指标

- 权重显存
- 可用 KV 显存
- KV token 容量
- `172K` 单并发速度
- `256K` 端到端总时延拆解

## 7. `models/Qwen/Qwen3.6-35B-A3B-FP8`（SGLang）

### 7.1 基本信息

- 后端：`SGLang`
- served model：`qwen36-35b-a3b-fp8`
- 关键部署参数：
  - 轮次 A:
    - `mem_fraction_static=0.85`
    - `max_running_requests=4`
  - 轮次 B:
    - `mem_fraction_static=0.65`
    - `max_running_requests=1`

### 7.2 显存与 KV

- 权重显存：`未测`
- 可用 KV 显存：`未测`
- KV token 容量：
  - 轮次 A：`901,428 tokens`
  - 轮次 B：`465,585 tokens`

### 7.3 并发与上下文

- `256K` 工程建议并发：`未测`
- 最大已验证上下文：未进入正式请求阶段
- `256K` 单条可过：未验证

### 7.4 各档 token 速度

- `4K`：`未测`
- `32K`：`未测`
- `64K`：`未测`
- `128K`：`未测`
- `172K`：`未测`
- `256K`：`未测`

### 7.5 补充说明

- 当前已确认参数可以下发，KV cache 也能分配
- 但当前观测窗口内服务未稳定开放，因此不能把这组条目当作正式可服务性能结果
- 当前它更像“启动容量观测”，不是“正式性能结果”

### 7.6 仍缺指标

- 权重显存
- 可用 KV 显存
- `256K` 工程建议并发
- 全部正式请求阶梯结果
- 服务 ready 前后的稳定性观测

## 8. `models/Qwen/Qwen3.6-27B-AWQ-INT4`

### 8.1 基本信息

- 后端：`vLLM`
- served model：`qwen36-27b-awq-int4`
- 关键部署参数：
  - `max_model_len=262144`
  - `gpu_memory_utilization=0.5`
  - `max_num_seqs=4`
  - `shm_size=16g`

### 8.2 显存与 KV

- 权重显存：`19.05 GiB`
- 可用 KV 显存：`18.42 GiB`
- KV token 容量：`75,264 tokens`
- 单条 `256K` 的近似 KV 成本：约 `16.16 GiB`
- 本轮 benchmark 过程观测：
  - 容器进程显存约 `40,408 MiB -> 41,770 MiB`
  - 整机 GPU 已用显存约 `40,431 MiB -> 41,793 MiB`

### 8.3 并发与上下文

- `256K` 工程建议并发：`1`
- 最大已验证上下文：`262000 prompt tokens`
- `256K` 单条可过：是

### 8.4 各档 token 速度

- `4K`
  - 实际 prompt tokens：`4096`
  - `completion tok/s`：`avg 26.51` / `median 26.85` / `min 25.79` / `max 26.88`
  - 端到端时延：`avg 2415.35 ms` / `median 2383.18 ms` / `min 2380.84 ms` / `max 2482.04 ms`
- `32K`
  - 实际 prompt tokens：`32768`
  - `completion tok/s`：`avg 4.68` / `median 4.68` / `min 4.65` / `max 4.72`
  - 端到端时延：`avg 13668.27 ms` / `median 13662.48 ms` / `min 13573.24 ms` / `max 13769.08 ms`
- `64K`
  - 实际 prompt tokens：`65536`
  - `completion tok/s`：`avg 2.12` / `median 2.12` / `min 2.12` / `max 2.13`
  - 端到端时延：`avg 30165.00 ms` / `median 30189.31 ms` / `min 30062.79 ms` / `max 30242.89 ms`
- `128K`
  - 实际 prompt tokens：`131072`
  - `completion tok/s`：`avg 0.88` / `median 0.88` / `min 0.88` / `max 0.88`
  - 端到端时延：`avg 72608.32 ms` / `median 72578.28 ms` / `min 72527.54 ms` / `max 72719.16 ms`
- `172K`
  - 实际 prompt tokens：`176128`
  - `completion tok/s`：`avg 0.59` / `median 0.59` / `min 0.59` / `max 0.59`
  - 端到端时延：`avg 108860.73 ms` / `median 108896.09 ms` / `min 108758.30 ms` / `max 108927.81 ms`
- `256K`
  - 实际 prompt tokens：`262000`
  - `completion tok/s`：`avg 0.33` / `median 0.33` / `min 0.33` / `max 0.33`
  - 端到端时延：`avg 194244.74 ms` / `median 194212.95 ms` / `min 194156.00 ms` / `max 194365.26 ms`

### 8.5 补充说明

- 本轮统计口径：
  - `warmup_runs=1`
  - `measured_runs=3`
  - 文档中的 `avg / median / min / max` 仅统计 `measure` 轮次，不包含 warmup
- benchmark 摘要给出的 `max_concurrency_for_256k = 1.14`，工程建议按 `1` 规划
- 本轮启动日志记录：
  - `Model loading took 19.05 GiB memory`
  - `torch.compile took 76.84 s`
- 本轮单并发 benchmark 结果：
  - `4K -> 256K` 的 `completion tok/s` 均值从 `26.51` 下降到 `0.33`
  - `172K` 的 `completion tok/s` 均值约 `0.59`
  - `256K` 端到端时延均值约 `194.24s`
- 过程采样中，`256K` 阶段观测到 `GPU KV cache usage` 峰值约 `60.6%`
- `172K` 和 `256K` 阶段的部分过程采样里，vLLM 指标接口会返回 `available_kv_cache_memory / gpu_kv_cache_size_tokens / max_concurrency_for_256k = null`
  - 文档中的这 3 个值取自同轮 benchmark 前半段非空样本，可作为本配置的已观测容量基线

### 8.6 仍缺指标

- `gateway` 路径结果
- 多并发压测
- 长请求错误率 / 超时率
- 首 token 时延拆解

## 9. `models/Qwen/Qwen3.6-27B-NVFP4`

### 9.1 基本信息

- 后端：`vLLM`
- served model：`qwen36-27b-nvfp4`
- 关键部署参数：
  - `max_model_len=262144`
  - `gpu_memory_utilization=0.55`
  - 历史对照：`gpu_memory_utilization=0.34 / 0.5 / 0.6`
  - `max_num_seqs=4`
  - `max_tokens=64`
  - 单并发

### 9.2 显存与 KV

- 权重显存：`24.05 GiB`
- `gpu_memory_utilization=0.34` 时：
  - 可用 KV 显存：`0.74 GiB`
  - KV token 容量：`2,352 tokens`
- `gpu_memory_utilization=0.5` 时：
  - 可用 KV 显存：`13.42 GiB`
  - `max_model_len=262144` 启动失败
  - vLLM 报错：`262144` 至少需要 `16.17 GiB` KV cache
  - vLLM 估算当前可用显存下最大模型长度约 `217168`
- `gpu_memory_utilization=0.55` 时：
  - 可用 KV 显存：`17.38 GiB`
  - KV token 容量：`70,560 tokens`
  - `Maximum concurrency for 262,144 tokens per request: 1.07x`
  - 当前在线进程显存占用约 `45,918 MiB`
- `gpu_memory_utilization=0.6` 时：
  - 可用 KV 显存：`21.34 GiB`
  - KV token 容量：`87,024 tokens`
  - `Maximum concurrency for 262,144 tokens per request: 1.32x`
- 本轮 `256K` 服务端实测过程观测：
  - `gpu_memory_utilization=0.55` 时容器进程显存约 `45,918 MiB`
  - `gpu_memory_utilization=0.6` 时容器进程显存约 `49,982 MiB`
  - `gpu_memory_utilization=0.6` 的日志中曾观测到 `GPU KV cache usage` 高点约 `76.0%`

### 9.3 并发与上下文

- `256K` 工程建议并发：`1`
- 最大已验证上下文：`262000 prompt tokens + 64 output tokens`
- `256K` 单条可过：是
- `4K` 单条可过：
  - 直接请求 `4096 prompt + 64 output`：否
  - 预留输出余量后的 `4032 prompt + 64 output`：是

### 9.4 各档 token 速度

- `4K`
  - 服务端实测 prompt tokens：`4032`
  - output tokens：`64`
  - `completion tok/s`：`avg 25.10` / `median 25.19` / `min 24.88` / `max 25.23`
  - 端到端时延：`avg 2549.70 ms` / `median 2540.22 ms` / `min 2536.77 ms` / `max 2572.12 ms`
- `32K`：`未测`
- `64K`：`未测`
- `128K`：`未测`
- `172K`：`未测`
- `256K`
  - 服务端实测 prompt tokens：`262000`
  - output tokens：`64`
  - `gpu_memory_utilization=0.55`：`completion tok/s 0.3415` / 端到端时延 `187415.80 ms`
  - `gpu_memory_utilization=0.6`：`completion tok/s 0.3413` / 端到端时延 `187512.74 ms`

### 9.5 补充说明

- 本轮统计口径：
  - `4K` 为服务端直测 `3` 轮
  - `256K` 为服务端直测 `1` 轮
  - 统计口径均以服务端返回的 `usage.prompt_tokens / usage.completion_tokens` 为准
- 当前在线实例的启动日志已明确给出：
  - `gpu_memory_utilization=0.34`：
    - `Model loading took 24.05 GiB memory`
    - `Available KV cache memory: 0.74 GiB`
    - `GPU KV cache size: 2,352 tokens`
  - `gpu_memory_utilization=0.6`：
    - `Model loading took 24.05 GiB memory`
    - `Available KV cache memory: 21.34 GiB`
    - `GPU KV cache size: 87,024 tokens`
  - `gpu_memory_utilization=0.55`：
    - `Model loading took 24.05 GiB memory`
    - `Available KV cache memory: 17.38 GiB`
    - `GPU KV cache size: 70,560 tokens`
    - `Maximum concurrency for 262,144 tokens per request: 1.07x`
- `gpu_memory_utilization=0.5` 时无法以 `max_model_len=262144` 启动：
  - 启动日志显示可用 KV 只有 `13.42 GiB`
  - vLLM 判定至少需要 `16.17 GiB` 才能服务单条 `262144` 请求
  - 如果坚持使用 `0.5`，应把 `max_model_len` 降到不高于日志估算的 `217168`，并重新实测
- `gpu_memory_utilization=0.55` 是当前已验证的较低可用点：
  - 它能跑通单条 `262000 prompt tokens + 64 output tokens`
  - 但启动日志只给出 `1.07x` 并发余量，工程上比 `0.6` 更贴边
- `gpu_memory_utilization=0.6` 且 `max_model_len=262144` 时，vLLM 启动日志给出 `Maximum concurrency for 262,144 tokens per request: 1.32x`
- `4096 prompt + 64 output` 的直推请求会被 vLLM 拒绝：
  - 原因是当时短上下文 profile 的总 token 数达到 `4097`，超出 `max_model_len=4096`
  - 因此本节正式性能结果使用“预留输出余量”的 `4032 prompt + 64 output`
- 当前仓库内置 benchmark 在 `TokenizersBackend` 目录格式下，本地 tokenizer 计数和服务端 `usage.prompt_tokens` 不完全一致：
  - 因此本节最终以服务端实测口径为准
  - 之前基于本地 tokenizer 推导出的 `3968` 只可视为近似值，不再作为正式最大上下文结论
- 当前不再使用“KV token 容量 -> 256K 所需显存”的线性外推：
  - 这类外推和同仓库 `Qwen3.6-27B-AWQ-INT4` 的已验证 `256K` 结果相冲突
  - 更合理的解释是：`vLLM` 日志里的 `GPU KV cache size tokens` 不是这类模型“最大可服务 prompt tokens”的直接等价物
  - 当前 `NVFP4` 已经通过 `262000 prompt tokens + 64 output tokens` 服务端实测
- 这组结果更适合回答：
  - NVFP4 在当前 `262144 / 0.55` profile 下是否可服务
  - 当前 `4K` 和 `256K` 两个端点的单并发完成速度大概是多少

### 9.6 仍缺指标

- `gateway` 路径结果
- 多并发压测
- 更细的首 token 时延
- `32K / 64K / 128K / 172K` 中间档位速度

## 10. 通用缺口指标

如果后续继续补数据，优先补这些字段：

- `172K` 单并发 `completion tok/s`
- `256K` 端到端总时延
- 权重显存与 KV 显存拆账更完整的启动日志
- `gateway` 路径下的单并发阶梯速度
- 长请求期间的峰值 `GPU KV cache usage`
- 多并发下的：
  - 首 token 时延
  - 稳态 `completion tok/s`
  - 错误率 / 超时率
- 不同 `gpu_memory_utilization / max_num_seqs / n_parallel` 的配置对照

## 11. 性能测试自动化改造清单

当前性能测试可以自动化，但应先保证后端采集口径可信，再做前端测试界面。否则界面会放大错误结论。

### 11.1 已补齐的基础问题

- 控制面启动前会校验运行中容器是否匹配当前 profile：
  - 如果镜像、启动参数、端口或模型挂载漂移，会停止并重建容器
  - 避免 `status` 显示 `max_model_len=262144`，但实际 Docker `Cmd` 仍是旧 `4096` 的情况
- benchmark 输出已记录服务端口径：
  - `usage.prompt_tokens`
  - `usage.completion_tokens`
  - `usage.total_tokens`
  - `finish_reason`
  - `error_message`
  - `prompt_token_mismatch`
- `TokenizersBackend` tokenizer 加载失败时，benchmark 会使用兼容 fallback：
  - 这个 fallback 只解决本地构造 prompt 的问题
  - 正式结论仍以服务端 `usage.prompt_tokens` 为准
- `sample_interval` 已从“请求前后采样”改为“请求运行期间连续采样”：
  - 长上下文请求可更可靠捕获峰值 GPU 显存与 `GPU KV cache usage`

### 11.2 仍需要补的自动化能力

- 自动启动矩阵：
  - 输入 `profile / gpu_memory_utilization / max_model_len / max_num_seqs`
  - 自动 `stop -> start -> healthcheck -> logs parse -> benchmark`
  - 每组配置独立产出 `summary.json / samples.jsonl`
- 启动失败结构化解析：
  - 解析 vLLM 的 KV 不足错误
  - 记录 `required_kv_memory / available_kv_memory / suggested_max_model_len`
  - 失败也生成结果文件，而不是只靠人工看日志
- 多并发压测：
  - 至少支持 `concurrency=1/2/4`
  - 分别记录成功率、超时率、首 token 时延、端到端时延、吞吐与峰值显存
- prompt 预算策略：
  - 默认按 `target_prompt_tokens + max_tokens <= max_model_len` 生成请求
  - 文档中同时记录目标 prompt、本地 tokenizer 估算、服务端 prompt 三个值
- 结果对比视图：
  - 同一模型不同 `gpu_memory_utilization`
  - 同一模型不同 `max_model_len`
  - AWQ / NVFP4 / FP8 的同长度速度和显存对比

### 11.3 前端测试界面建议

- 可以在管理台增加“性能实验室”页面，但页面只负责编排和展示，不直接推导 KV 结论。
- 前端表单建议包含：
  - 模型 profile
  - 上下文长度列表，例如 `4K / 32K / 64K / 128K / 172K / 256K`
  - `max_tokens`
  - warmup / measure 轮数
  - 并发数
  - 是否自动重启后端
- 前端展示建议包含：
  - 权重显存、可用 KV 显存、vLLM maximum concurrency
  - 服务端 prompt tokens、completion tok/s、端到端时延
  - 峰值进程显存、整机 GPU 显存、峰值 KV usage
  - 错误原因与启动失败建议
- 后端 API 建议先做最小闭环：
  - `POST /admin/perf/runs` 创建测试任务
  - `GET /admin/perf/runs/{id}` 查询 summary
  - `GET /admin/perf/runs/{id}/samples` 查询采样曲线
  - `GET /admin/perf/runs` 查询历史列表
