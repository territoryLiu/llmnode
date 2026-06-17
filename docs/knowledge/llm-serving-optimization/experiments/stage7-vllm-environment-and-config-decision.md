# 第七阶段实验报告：vLLM 主线环境核验与主配置决策收口

> 文档定位：项目知识库中的 LLM serving 优化实验报告，不属于 `llmnode` 项目蓝图、契约或正式路线图。
> 实验目标：完成 `experiment-master-plan.md` 中 `V0 / V1` 的第一轮现实核验，确认宿主真实实验环境、当前默认激活 profile、`AWQ-INT4` 主基线是否能稳定拉起，并把”默认上线候选 / 观察项 / 实验项”正式收口。
> 更新时间：2026-06-10。
> 当前结论状态：宿主机环境、Docker 镜像、GPU 状态和 `AWQ-INT4` baseline 启动证据已核验完成；仓库默认激活 profile 仍然指向 `NVFP4`，与当前主线决策不一致。

相关专题：

- 总方案见 [experiment-master-plan.md](./experiment-master-plan.md)。
- AWQ benchmark / profiler 证据见 [stage1-2-qwen27b.md](./stage1-2-qwen27b.md)、[stage3-awq-concurrency.md](./stage3-awq-concurrency.md)、[stage4-awq-profiler.md](./stage4-awq-profiler.md)。
- NVFP4 对照见 [stage1-2-qwen27b.md](./stage1-2-qwen27b.md)、[stage5-nvfp4-profiler.md](./stage5-nvfp4-profiler.md)。
- FP8 KV 质量见 [stage6a-fp8-kv-benchmark.md](./stage6a-fp8-kv-benchmark.md)。
- Nsight 进展见 [stage6b-nsight-toolchain.md](./stage6b-nsight-toolchain.md)。

## 1. 一页结论

本轮最重要结论：

1. 宿主真实实验环境可用，`NVIDIA A800 80GB PCIe` 空闲，`vllm/vllm-openai:nightly` 镜像已存在，不需要重新拉镜像。
2. 非提权环境下的 `llmnode.control doctor` 会出现误判：它会把 GPU 和 Docker 镜像都看成缺失，因此后续所有真实 vLLM / GPU 实验必须以宿主提权环境为准。
3. 仓库默认激活 profile 仍是 `vllm_qwen36-27b-nvfp4`，来源于 [config/defaults.yaml](/proj02/liuheshan/llmnode/config/defaults.yaml:35)，这与当前主线建议的默认基线 `AWQ-INT4` 不一致。
4. `AWQ-INT4` 在宿主真实环境下已重新拉起并完成 API ready，说明它不仅是历史 benchmark 里的主候选，也是当前机器上可直接复现的主候选。
5. 结合 Stage 1、3-7 已有证据，本轮正式收口如下：
   - 默认上线候选：`AWQ-INT4`
   - 观察项：`NVFP4`
   - 仅实验配置：`AWQ-INT4 + FP8 KV cache`

## 2. 核验目标

本轮不是重复跑 `16K/64K + 512` benchmark，而是验证三件事：

1. 当前主线环境是否真实可用。
2. 当前仓库默认激活 profile 是否与主线决策一致。
3. `AWQ-INT4` 是否能在当前宿主环境下完成一次新的真实启动闭环。

## 3. 环境核验

### 3.1 非提权 `env / status / doctor`

执行：

```bash
/home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control env
/home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control status
/home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control doctor
```

结论：

| 项目 | 结果 | 判断 |
|---|---|---|
| `env` 当前 model_dir | `models/Qwen/Qwen3.6-27B-NVFP4` | 当前默认激活 profile 是 `NVFP4` |
| `status` | managed stack 停止，旧 `qwen36-27b-nvfp4-vllm` 容器已退出 | 当前没有可用 backend |
| `doctor` GPU 结果 | `nvidia-smi available but no GPUs detected` | 非真实宿主结论 |
| `doctor` backend image | `missing vllm/vllm-openai:nightly` | 非真实宿主结论 |

关键判断：

> `doctor` 在非提权环境下对 GPU 和 Docker 的判断不可信，不能作为后续实验环境结论。

### 3.2 宿主真实 GPU 状态

执行：

```bash
nvidia-smi
```

结果：

| 项目 | 值 |
|---|---|
| GPU | `NVIDIA A800 80GB PCIe` |
| Driver | `580.126.09` |
| CUDA Version | `13.0` |
| 当前显存占用 | `14 MiB / 81920 MiB` |
| 当前 GPU 进程 | 仅 `Xorg 4 MiB` |

结论：

- 宿主 GPU 真实可见。
- 当前没有外部计算负载干扰，可用于继续 vLLM 实验。

### 3.3 宿主 Docker 状态

执行：

```bash
docker image inspect vllm/vllm-openai:nightly --format '{{.Id}} {{.Created}}'
docker ps -a --format '{{.Names}} {{.Status}} {{.Image}}' | rg 'qwen36-27b|vllm'
```

结果：

| 项目 | 结果 |
|---|---|
| 镜像 | `vllm/vllm-openai:nightly` 已存在 |
| AWQ / NVFP4 / profiler / FP8 KV 容器 | 历史容器均存在，状态为 `Exited` |

结论：

- 当前主线不缺镜像。
- 历史实验容器均可作为已有产物索引，但本轮启动应以新的 runtime log 为准。

## 4. 当前默认激活 profile 与主线决策的差异

仓库当前默认激活 profile 来源：

| 文件 | 当前值 |
|---|---|
| [config/defaults.yaml](/proj02/liuheshan/llmnode/config/defaults.yaml:35) | `active_backend_profile: vllm_qwen36-27b-nvfp4` |

这意味着：

- 直接运行 `python -m llmnode.control env/status/doctor` 时，默认看到的是 `NVFP4`。
- 但当前 `experiment-master-plan.md` 已经把 `AWQ-INT4` 收口为默认上线候选。

当前判断：

> 仓库默认激活 profile 仍停留在旧的 `NVFP4` 路线，而当前实验主线和决策文档已经转向 `AWQ-INT4`。

这不是“实验失败”，而是“默认配置尚未跟随实验决策更新”的状态。

## 5. `AWQ-INT4` 真实启动闭环

### 5.1 启动命令

```bash
VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE=vllm_qwen36-27b-awq-int4 \
  /home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control start --service vllm --daemon
```

runtime log：

```text
runtime/logs/qwen36-27b-awq-int4-vllm-20260610-171543.log
```

### 5.2 启动侧证据

| 字段 | 值 |
|---|---:|
| model | `qwen36-27b-awq-int4` |
| vLLM version | `0.19.2rc1.dev134+gfe9c3d6c5` |
| `gpu_memory_utilization` | `0.55` |
| `max_model_len` | `262144` |
| `max_num_seqs` | `4` |
| attention backend | `FLASH_ATTN` |
| AWQ kernel | `MarlinLinearKernel for CompressedTensorsWNA16` |
| model loading memory | `19.05 GiB` |
| model loading time | `10.01 s` |
| torch.compile total | `67.85 s` |
| initial profiling / warmup | `90.96 s` |
| estimated CUDA graph memory | `0.11 GiB` |
| available KV cache memory | `22.38 GiB` |
| GPU KV cache size | `90,944 tokens` |
| max concurrency for `262,144` tokens/request | `1.38x` |
| startup complete | yes |

### 5.3 API ready 证据

执行：

```bash
curl -sS http://127.0.0.1:15673/v1/models
```

结果：

- 返回 `qwen36-27b-awq-int4`
- `max_model_len=262144`
- HTTP 请求成功

结论：

> `AWQ-INT4` 已在当前宿主真实环境下重新完成一次完整启动闭环，既能拉起，也能对外提供模型接口。

## 6. 当前配置决策收口

基于 Stage 2-7 的已有 benchmark / profiler / Nsight 证据，再结合本轮现实核验，当前配置决策正式收口为：

| 配置 | 当前定位 | 当前处理 |
|---|---|---|
| `vllm_qwen36-27b-awq-int4` | 默认上线候选 / 主分析基线 | 保留为主线 |
| `vllm_qwen36-27b-nvfp4` | 同形状对照 / FP4 路线观察项 | 保留，但不替代 AWQ 默认基线 |
| `vllm_qwen36-27b-awq-int4-fp8-kv` | 容量实验配置 | 不作为默认上线候选 |

进一步展开：

1. `AWQ-INT4`
   - 已完成 benchmark、并发、profiler、Nsight 主线
   - 本轮重新证明当前宿主环境下可直接拉起
   - 应继续作为默认基线推进 `64K + 512` 同形状 `ncu`

2. `NVFP4`
   - 仍有价值，尤其是无干扰 `64K + 512` benchmark 和 profiler 对照
   - 但当前证据还不足以把它升成默认上线候选

3. `FP8 KV cache`
   - 容量收益已证实
   - 质量回归已有新增退化
   - 只能留在实验项，不能直接写成可上线配置

## 7. 当前发现的问题

### 7.1 非提权环境会误导环境判断

表现：

- `doctor` 报 GPU 缺失
- `doctor` 报镜像缺失

实际：

- 宿主 GPU 正常
- 宿主镜像正常

影响：

- 后续所有真正依赖 GPU / Docker / `/v1/models` 的验证，都必须以宿主提权环境为准。

### 7.2 默认激活 profile 与主线决策不一致

表现：

- 仓库默认 profile 仍指向 `NVFP4`
- 主线方案和证据已经把 `AWQ-INT4` 定为默认候选

影响：

- 新人直接跑 `env/status` 会先看到 `NVFP4`
- 这和当前文档里的默认主线不一致，容易造成认知漂移

## 8. 这轮完成了什么

本轮已经完成 `experiment-master-plan.md` 里的两项现实工作：

1. `V0`：环境与证据清点  
   已完成宿主 GPU、Docker、旧容器、当前 active profile 和 `AWQ-INT4` 启动闭环核验。
2. `V1`：主配置决策收口  
   已完成第一轮现实决策收口，并把默认/观察/实验三类配置正式写清楚。

## 9. 仍未完成什么

本轮没有完成：

1. `64K + 512` 同形状 `ncu`
2. launch gap 的进一步分类
3. 默认 profile 是否应从 `NVFP4` 改为 `AWQ-INT4` 的仓库配置更新

因此当前阶段还不能宣称整条 vLLM 主线已完成。

## 10. 下一步

优先级建议：

1. 继续做 `V2`：`64K + 512` 同形状 `Nsight Compute`
2. 如果 `V2` 仍被冷启动 profiler overhead 卡住，优先做 attach 路径
3. 在 `V2` 完成前，不再重复扩更多 benchmark 版本

如果只做一个实验，下一步建议明确为：

```text
在 AWQ-INT4 主基线上完成 `64K + 512` 同形状 ncu。
```
