# Performance

性能分析目录，只回答“怎么测、怎么解释指标、怎么定位瓶颈”。

| 文件 | 职责 |
|---|---|
| [benchmark-methodology.md](./benchmark-methodology.md) | benchmark 指标、口径、实验矩阵和报告模板 |
| [kv-cache.md](./kv-cache.md) | KV cache、长上下文容量、vLLM KV 日志解释 |
| [profiling-guide.md](./profiling-guide.md) | Profiling 完整指南：方法论 + torch profiler / nsys / ncu 实操 + 图形界面 + SSH 远程查看 |

具体某次模型测试数据放到 `../experiments/`，量化机制细节放到 `../optimization/`。
