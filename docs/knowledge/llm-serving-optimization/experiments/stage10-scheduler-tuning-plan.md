# 第十阶段实验方案：调度层实测与交互式延迟回归

> 文档定位：项目知识库中的 LLM serving 优化实验方案，不属于 `llmnode` 项目蓝图、契约或正式路线图。  
> 实验目标：把 Stage 9 已经明确的“调度层优先”结论，落成一轮可执行、可回归、可收口的实测方案；优先验证 `chunked prefill` 与 `max_num_seqs` 对 `64K + 512` 主代表点的影响。  
> 更新时间：2026-07-07。  
> 当前结论状态：这是下一轮执行方案，不是实测结论；所有结果字段都应在执行后按实测填写。

相关专题：

- 总方案见 [experiment-master-plan.md](./experiment-master-plan.md)。
- 当前工程边界见 [stage9-optimization-actions-and-deployment-boundaries.md](./stage9-optimization-actions-and-deployment-boundaries.md)。
- queue / launch gap 归因见 [stage8-launch-gap-and-queue-analysis.md](./stage8-launch-gap-and-queue-analysis.md)。
- benchmark 口径见 [../performance/benchmark-methodology.md](../performance/benchmark-methodology.md)。
- vLLM 参数背景见 [../serving/vllm-deep-dive.md](../serving/vllm-deep-dive.md)。

## 1. 为什么现在做这一轮

Stage 1-9 已完成第一轮闭环，当前稳定结论已经足够明确：

1. `AWQ-INT4` 是当前 A800 主线默认候选。
2. `64K + 512` 是主代表 workload。
3. `Marlin + FlashAttention` 是长期稳定主热点。
4. `64K c4` 已出现明确 `Running / Waiting` 队列。
5. 当前最可操作的优化方向在调度层，不在 kernel 层。

因此下一步不应继续：

- 扩更多量化矩阵
- 重跑旧的 `16K/64K + 512` 基线
- 优先攻 `server-side ncu attach`
- 直接进入 kernel patch

这一轮只回答一个问题：

> 通过更合适的调度参数，能否在不改 kernel 的前提下，改善 `64K` 长上下文场景的交互式延迟和排队表现？

## 2. 本轮只测什么

本轮只保留两个变量，分两条子实验串行执行：

### 2.1 子实验 A：chunked prefill

目标：

- 观察把长 prefill 切得更细后，`TTFT`、`E2E latency` 和 `c2/c4` 的等待表现是否改善。

只改：

- `max_num_batched_tokens`

固定不变：

- profile：`vllm_qwen36-27b-awq-int4`
- backend：`vLLM`
- `gpu_memory_utilization=0.55`
- `max_model_len=262144`
- `max_num_seqs=4`
- prompt：`64K`
- output：`512`

### 2.2 子实验 B：并发边界

目标：

- 判断交互式场景下，`max_num_seqs=2` 是否比 `4` 更合理。

只改：

- `max_num_seqs`

固定不变：

- profile：`vllm_qwen36-27b-awq-int4`
- backend：`vLLM`
- `gpu_memory_utilization=0.55`
- `max_model_len=262144`
- prompt：`64K`
- output：`512`
- chunked prefill 参数固定为子实验 A 中更合理的一档；如果 A 没有明显收益，则维持当前基线值

## 3. 实验矩阵

### 3.1 子实验 A：chunked prefill 矩阵

建议保留三档，不再扩更多点：

| 组别 | `max_num_batched_tokens` | 目的 |
|---|---:|---|
| A0 | 当前基线值 | 对照组 |
| A1 | `4096` | 更激进切块，观察 TTFT / 排队是否改善 |
| A2 | `16384` | 更宽切块，观察是否只是切块过细带来额外调度成本 |

并发档位：

| 档位 | 作用 |
|---|---|
| `c1` | 看单请求 TTFT / E2E 是否被额外调度开销拖慢 |
| `c2` | 看无明显 Waiting 队列时，TTFT 和 TPOT 是否改善 |
| `c4` | 看 Waiting 队列和 wall time 是否收敛 |

### 3.2 子实验 B：`max_num_seqs` 矩阵

只保留两档：

| 组别 | `max_num_seqs` | 目的 |
|---|---:|---|
| B0 | `4` | 当前基线 |
| B1 | `2` | 验证限制并发后，交互式延迟是否更稳 |

建议并发档位：

| 档位 | 作用 |
|---|---|
| `c1` | 确认单请求不被新配置拖慢 |
| `c2` | 当前主要交互档位，对比尾延迟与 TPOT |
| `c4` | 作为压力观察点，验证 Waiting 是否减轻 |

## 4. 指标与记录口径

本轮必须同时记录 streaming 与非 streaming 指标，避免只看一种口径。

### 4.1 streaming 指标

至少记录：

- `ttft_ms_avg`
- `prefill_ms_avg`
- `decode_ms_avg`
- `tpot_ms_avg`
- `decode_tokens_per_second_avg`
- `p50 / min / max`

用途：

- 判断是 prefill 改善，还是 decode / sampling 被拖慢

### 4.2 非 streaming / 服务侧指标

至少记录：

- `E2E latency avg`
- `latency p50 / p90 / p99`
- `completion tok/s`
- success rate
- wall time

用途：

- 判断真实交互体验和尾延迟是否改善

### 4.3 启动与运行侧证据

每组都至少补三类侧证据：

1. 启动日志
   - `max_model_len`
   - `gpu_memory_utilization`
   - `max_num_seqs`
   - `Available KV cache memory`
   - `GPU KV cache size`
2. 运行期日志
   - `Running / Waiting`
   - `GPU KV cache usage`
3. 外部环境
   - `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader`

## 5. 成功标准

这轮不是追求“任何指标都更好”，而是要得到可执行决策。

### 5.1 子实验 A 成功标准

满足以下任一条即可视为成立：

1. `64K c2/c4` 的 `TTFT` 明显下降，且 `TPOT` 没有明显退化。
2. `64K c4` 的 `Running / Waiting` 更快进入稳定态，wall time 收敛。
3. `64K c4` 的 `P90/P99 latency` 明显下降。

判定失败条件：

1. `TTFT` 无改善，且 `E2E` 或 `TPOT` 更差。
2. `c4` Waiting 队列形态没有改善，反而 wall time 更长。
3. 单请求 `c1` 明显退化，说明切块成本高于收益。

### 5.2 子实验 B 成功标准

满足以下任一条即可视为成立：

1. `max_num_seqs=2` 下 `c2` / `c4` 的 `P90/P99 latency` 更稳。
2. `c4` Waiting 队列明显减轻，交互式延迟更可接受。
3. `c2` 的 `TTFT + TPOT` 组合优于 `4`，且成功率不下降。

判定失败条件：

1. `max_num_seqs=2` 只是把系统总吞吐显著压低，但交互延迟没有改善。
2. `c2` / `c4` 的尾延迟与 wall time 都没有收益。

## 6. 执行顺序

严格按下面顺序走，避免变量串扰：

1. 先做环境检查  
   确认 GPU 空闲、镜像存在、当前无外部负载污染
2. 跑子实验 A  
   先 `c1`，再 `c2`，最后 `c4`
3. 在 A 中选出一档更合理的 chunked prefill 配置  
   如果没有收益，保留基线
4. 再跑子实验 B  
   只比较 `max_num_seqs=4` 与 `2`
5. 最后补一页决策总结  
   写明下一轮默认建议值

## 7. 建议命令框架

下面只给口径，不把未验证命令写成既定事实。执行时应以当前 `llmnode.control` 和 benchmark 脚本实参为准。

### 7.1 启动前检查

```bash
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
/home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control env
/home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control status
```

### 7.2 streaming benchmark

```bash
/home/heshan/.conda/envs/paper2any/bin/python scripts/benchmark_streaming.py \
  --profile vllm_qwen36-27b-awq-int4 \
  --targets 65536 \
  --max-tokens 512 \
  --warmup-runs 1 \
  --measure-runs 3
```

### 7.3 非 streaming / 并发 benchmark

```bash
/home/heshan/.conda/envs/paper2any/bin/python scripts/benchmark_backend.py \
  --profile vllm_qwen36-27b-awq-int4 \
  --target 65536 \
  --max-tokens 512 \
  --concurrency 2
```

如果要固定某一轮参数，建议为本轮临时 profile 单独命名，避免覆盖当前主线配置。

## 8. 产物要求

本轮完成后，至少应产出：

1. 一份新的实验报告  
   建议文件名：`stage10-scheduler-tuning-results.md`
2. 每组 benchmark 的 JSON 结果
3. 关键启动日志路径
4. 如有必要，再补一份最小对比表回流到 `learning-log.md`

## 9. 本轮明确不做什么

1. 不改默认仓库 profile
2. 不新增新的量化格式
3. 不补更多 `ncu` section
4. 不以单次 noisy 结果直接更新主线结论
5. 不把 `256K` 重新拉回默认服务承诺讨论

## 10. 完成后要回答的问题

本轮结束后，至少要能明确回答：

1. `chunked prefill` 是否改善了 `64K` 交互式 TTFT？
2. 改善主要体现在 `c2`，还是 `c4`？
3. `max_num_seqs=2` 是否比 `4` 更适合作为交互式默认档位？
4. 下一轮默认建议值是什么？
5. 这些变化是否足以更新 Stage 9 的“上线边界”表？
