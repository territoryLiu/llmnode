# 大模型推理 Benchmark 方法论

> 文档定位：项目知识库中的 LLM serving 优化专题，服务 `llmnode` 的性能实验和报告复盘。  
> 目标：建立统一 benchmark 口径，避免把 `completion tok/s`、端到端延迟、TTFT、TPOT、prefill、decode 混在一起。  
> 当前重点：解释为什么第一阶段 `output tokens=64` 不足以判断量化是否加速，并指导第二阶段实验。

## 1. Benchmark 先问四个问题

每次跑性能实验前，先写清楚：

| 问题 | 为什么重要 |
|---|---|
| 输入多长 | 决定 prefill 压力、attention 访存和 KV cache 写入 |
| 输出多长 | 决定 decode 占比，影响量化和 speculative decoding 的收益 |
| 并发多少 | 决定调度、batching、排队和 KV cache 竞争 |
| 统计什么指标 | 不同指标回答不同问题，不能混用 |

典型例子：

```text
16K prompt + 64 output
```

回答的是：

> 长输入、短输出场景下的端到端体验。

它不能很好回答：

> 某种量化是否能提升纯 decode 吞吐。

## 2. 核心指标

| 指标 | 英文 | 含义 | 主要回答什么 |
|---|---|---|---|
| 首 token 时延 | TTFT | 从请求发出到收到第一个 token 的时间 | prefill、排队、调度是否慢 |
| 每 token 间隔 | ITL / TPOT | decode 阶段相邻 token 的间隔 | decode 稳态速度 |
| 端到端时延 | E2E latency | 请求开始到全部输出完成 | 用户整体等待时间 |
| 输入吞吐 | prefill tok/s | prompt token 处理速度 | 长上下文 prefill 能力 |
| 输出吞吐 | decode tok/s / completion tok/s | 生成 token 速度 | decode 能力 |
| 总吞吐 | total tok/s | prompt + output 总 token 速度 | 系统整体处理 token 能力 |
| 请求吞吐 | QPS / RPS | 每秒完成请求数 | 服务能力 |
| 成功率 | success rate | 成功请求占比 | 稳定性 |
| 分位时延 | P50/P90/P99 | 多请求时延分布 | 尾延迟和服务体验 |

注意：

- `completion tok/s` 只看输出 token，但它可能被长 prefill 影响。
- `端到端 latency` 对用户重要，但不适合直接归因瓶颈。
- `TTFT` 更接近 prefill 和排队问题。
- `TPOT / ITL` 更接近 decode 问题。

## 3. Prefill 与 Decode

LLM 推理通常分两段：

| 阶段 | 做什么 | 常见瓶颈 |
|---|---|---|
| Prefill | 一次性处理 prompt，写入 KV cache | attention、GEMM、HBM 带宽、KV 写入 |
| Decode | 每次生成一个或多个 token，读取历史 KV | 小 batch GEMM、attention KV 读取、scheduler、sampling |

长上下文下：

```text
prompt 越长 -> prefill 越重 -> TTFT 越高
```

长输出下：

```text
output 越长 -> decode 占比越高 -> TPOT 更有意义
```

第一阶段 `16K/64K prompt + 64 output` 更偏 prefill 压力测试。第二阶段要加入 `output=256/512/1024`，让 decode 占比变大。

## 4. 输出长度怎么选

| output tokens | 适合回答的问题 | 建议 |
|---:|---|---|
| `64` | 短回答体验、与第一阶段对齐 | 保留 |
| `256` | 中等输出，开始观察 decode | 推荐 |
| `512` | 几百字回答、代码生成、decode 更明显 | 推荐 |
| `1024` | 长生成稳定性和 decode 吞吐 | 只对少数候选做 |

如果只测 `64`，可能低估：

- AWQ/GPTQ 的 decode 收益或损失。
- speculative decoding / MTP 的价值。
- sampling 和流式输出的稳定性问题。

## 5. 并发怎么测

并发不要一上来拉很大。建议阶梯：

```text
1 -> 2 -> 4 -> 8 -> 16
```

每一级记录：

- 成功率
- 平均 / P50 / P90 / P99 latency
- TTFT
- TPOT
- GPU 显存峰值
- KV cache usage
- 是否排队
- 是否 503 / timeout / OOM

并发实验回答的是：

> 这个部署能服务多少请求。

不是：

> 这个模型单请求最快能多快。

## 6. 固定变量

每次实验只改一个核心变量。

| 实验 | 固定项 | 变量 |
|---|---|---|
| 量化对比 | 模型族、后端、prompt/output、并发 | BF16 / FP8 / AWQ / NVFP4 |
| 输出长度对比 | 模型、后端、prompt、并发 | output tokens |
| 上下文阶梯 | 模型、后端、output、并发 | prompt tokens |
| 显存参数对比 | 模型、prompt/output、并发 | `gpu_memory_utilization` |
| 调度参数对比 | 模型、prompt/output、并发 | `max_num_seqs`、chunked prefill |

如果一次改多个变量，结论会变成猜测。

## 7. 报告模板

```markdown
## 实验目标

- 本次想回答的问题：

## 固定条件

- 后端：
- 模型：
- profile：
- GPU：
- prompt tokens：
- output tokens：
- concurrency：
- warmup / measure：

## 结果表

| profile | prompt | output | concurrency | TTFT | TPOT | completion tok/s | E2E latency | success |
|---|---:|---:|---:|---:|---:|---:|---:|---|

## 解释

- 明确实测结论：
- 合理推断：
- 不能确认：

## 下一步

- 只改变哪个变量：
- 预期看到什么：
- 如何判断结论成立：
```

## 8. 当前第二阶段建议

基于第一阶段，第二阶段建议：

| 实验 | 固定项 | 变量 | 目的 |
|---|---|---|---|
| 输出长度阶梯 | `AWQ/NVFP4`、16K/64K prompt、并发 1 | `64/256/512` | 判断短输出结论是否误导 |
| AWQ 并发阶梯 | AWQ、固定 prompt/output | `1/2/4/8` | 看显存效率是否转化为服务吞吐 |
| 上下文阶梯 | AWQ、并发 1、output 256 | `16K/32K/64K/128K/192K/256K` | 找真实长上下文曲线 |
| NVFP4 显存参数 | NVFP4、固定 workload | `gpu_memory_utilization=0.55/0.6` | 看容量和稳定性余量 |
| 代表点 profiler | NVFP4 或 AWQ | `64K prompt + 512 output` | 拆 prefill / decode |

## 9. 常见误区

| 误区 | 修正 |
|---|---|
| `tok/s` 高就一定好 | 还要看 TTFT、P99、成功率和显存 |
| 单并发快就能服务多人 | 多并发会引入调度、batching、KV 竞争 |
| output 64 能代表生成速度 | 太短，decode 占比不够 |
| 平均值够了 | 多并发必须看 P90/P99 |
| 一次实验能定论 | 需要 warmup、重复测量和噪声判断 |

## 10. 相关文档

- [KV cache 专题](./kv-cache.md)
- [vLLM 深入](../serving/vllm-deep-dive.md)
- [第一阶段实验报告](../experiments/stage1-qwen27b.md)
