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

## 9. 通用缺口指标

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
