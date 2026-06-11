# 第八阶段实验报告：`64K + 512` 同形状 Nsight Compute 推进

> 文档定位：项目知识库中的 LLM serving 优化实验报告，不属于 `llmnode` 项目蓝图、契约或正式路线图。  
> 实验目标：把 `Nsight Compute` 从 `16K + 512` 代表点推进到主代表点 `64K + 512`，优先补齐 `AWQ-INT4` 的同形状 `Marlin` / `FlashAttention` 低层 section。  
> 更新时间：2026-06-11。  
> 当前结论状态：`64K + 512` 同形状 workload 已可稳定跑通；旧的 “cold start + profiler overhead 挤掉 KV cache 导致初始化失败” 已被绕开；进一步确认之前部分 offline `ncu` 失败混入了 `--force-overwrite true` 参数误用。修正为无值 flag `--force-overwrite` 后，offline 单进程 + eager 路径已经能在 GPU 空闲窗口导出 `64K + 512` 的 `Marlin` 与 `FlashAttention` `LaunchStats` report。当前待补的是是否需要更深的 `Occupancy / MemoryWorkloadAnalysis`，不是 kernel section 能否打通。

相关专题：

- Stage 7 Nsight bring-up 与 `16K` `ncu` 成功样本见 [stage7-fp8-kv-quality-and-nsight.md](./stage7-fp8-kv-quality-and-nsight.md)
- AWQ profiler 见 [stage4-awq-profiler.md](./stage4-awq-profiler.md)
- NVFP4 profiler 见 [stage6-nvfp4-profiler.md](./stage6-nvfp4-profiler.md)
- 当前总路线见 [experiment-master-plan.md](../experiment-master-plan.md)

## 1. 本阶段要回答的问题

1. `64K + 512` 主代表点能否在不回退到 `16K` 的前提下完成真实 `ncu` 采样？
2. 旧阻塞点到底是不是 `ncu` 本身，还是 `vLLM` 初始化时的 KV 预算被 profiler overhead 挤压？
3. 如果把 `spawn`、`torch.compile`、`CUDA Graph` 这些变量依次拆开后，`ncu` 还能不能对 `64K` workload 给出 section？

## 2. 固定条件

- backend: vLLM
- profile role: `vllm_qwen36-27b-awq-int4`
- model: `Qwen3.6-27B-AWQ-INT4`
- GPU: `NVIDIA A800 80GB PCIe`
- prompt tokens: `65536`
- output tokens: `512`
- concurrency: `1`
- host `ncu`:
  `/opt/anaconda3/pkgs/nsight-compute-2026.1.1.2-h934865d_0/nsight-compute-2026.1.1/ncu`

## 3. 核心方法调整

Stage 7 已证明，直接让 `ncu` 冷启动包裹默认 `max_model_len=262144` 的真实 vLLM workload，会因为 profiler overhead 压缩可用 KV cache，导致初始化阶段就失败。

这一轮不再坚持默认 `262144` 配置，而是把目标收窄为：

```text
保持真实 64K prompt + 512 output 形状不变，
只把 max_model_len 收到 66048，
让 prompt + output 刚好能容纳，
避免为 256K 预留无意义的 KV 预算。
```

这轮还额外拆了两个变量：

1. 是否关闭 `V1 multiprocessing`
2. 是否关闭 `torch.compile + CUDA Graph`

## 4. 运行脚本与结果

### 4.1 64K prompt 生成

先在宿主生成精确 `65536` token prompt：

```bash
/home/heshan/.conda/envs/paper2any/bin/python - <<'PY'
from pathlib import Path
from transformers import AutoTokenizer
from llmnode.perf.prompt_builder import build_prompt_for_target

model_dir='/proj02/liuheshan/llmnode/models/Qwen/Qwen3.6-27B-AWQ-INT4'
tok=AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)
prompt, actual=build_prompt_for_target(
    tokenizer=tok,
    target_prompt_tokens=65536,
    base_fragment='hello',
)
Path('/tmp/llmnode_ncu_prompt_64k.txt').write_text(prompt, encoding='utf-8')
print(actual)
PY
```

结果：

- 实际 prompt tokens: `65536`
- 输出文件：`/tmp/llmnode_ncu_prompt_64k.txt`

### 4.2 runtime-only 脚本：默认 compile/graph 路径

脚本：

```text
/tmp/llmnode_ncu_same_shape_runtime.py
```

关键参数：

- `max_model_len=66048`
- `gpu_memory_utilization=0.55`
- `max_num_seqs=1`

干跑命令：

```bash
docker run --rm --gpus all --ipc=host \
  -e HOME=/tmp \
  -v /proj02/liuheshan/llmnode/models/Qwen/Qwen3.6-27B-AWQ-INT4:/model:ro \
  -v /tmp:/host-tmp \
  --entrypoint python3 \
  vllm/vllm-openai:nightly \
  /host-tmp/llmnode_ncu_same_shape_runtime.py
```

结果：

| metric | value |
|---|---|
| prompt tokens | `65536` |
| completion tokens | `512` |
| finish_reason | `length` |
| elapsed | `41.15 s` |
| completion tok/s | `12.44` |

关键观察：

- 同形状 `64K + 512` workload 已能稳定跑通。
- 旧的 KV 预算初始化失败已经被 `max_model_len=66048` 这条路线绕开。
- 但默认路径中仍会出现：

```text
Overriding VLLM_WORKER_MULTIPROC_METHOD to 'spawn'. Reasons: CUDA is initialized
```

这说明如果继续直接对该路径做 `ncu`，仍可能把真实 CUDA kernel 放到子进程里。

### 4.3 单进程路径：关闭 `V1 multiprocessing`

宿主容器内源码检查确认：

- `VLLM_ENABLE_V1_MULTIPROCESSING` 默认是 `True`
- `VLLM_WORKER_MULTIPROC_METHOD` 默认是 `fork`
- 但若 `cuda_is_initialized()` 为真，`vllm/utils/system_utils.py` 会强制覆盖成 `spawn`
- `vllm/v1/engine/llm_engine.py` 与 `vllm/v1/executor/uniproc_executor.py` 说明：
  只要设置 `VLLM_ENABLE_V1_MULTIPROCESSING=0`，就会走 `InprocClient + UniProcExecutor` 单进程路径

干跑命令：

```bash
docker run --rm --gpus all --ipc=host \
  -e HOME=/tmp \
  -e VLLM_ENABLE_V1_MULTIPROCESSING=0 \
  -v /proj02/liuheshan/llmnode/models/Qwen/Qwen3.6-27B-AWQ-INT4:/model:ro \
  -v /tmp:/host-tmp \
  --entrypoint python3 \
  vllm/vllm-openai:nightly \
  /host-tmp/llmnode_ncu_same_shape_runtime.py
```

结果：

- 日志中不再出现 `spawn` 覆盖 warning
- 直接进入单进程 `EngineCore`
- 但如果 GPU 上同时还有别的本任务容器在释放显存，会把可用 KV cache 压到极低，出现：

```text
Available KV cache memory: 0.59 GiB
ValueError: ... estimated maximum model length is 7056
```

因此这一路径必须在“GPU 干净、没有并行同卡本任务进程”的前提下使用。

### 4.4 单进程 + eager 路径

为了进一步排除 `torch.compile + CUDA Graph` 对 `ncu` 采样的干扰，又补了一份 eager 版本脚本：

```text
/tmp/llmnode_ncu_same_shape_runtime_eager.py
```

唯一额外变量：

- `enforce_eager=True`

干跑命令：

```bash
docker run --rm --gpus all --ipc=host \
  -e HOME=/tmp \
  -e VLLM_ENABLE_V1_MULTIPROCESSING=0 \
  -v /proj02/liuheshan/llmnode/models/Qwen/Qwen3.6-27B-AWQ-INT4:/model:ro \
  -v /tmp:/host-tmp \
  --entrypoint python3 \
  vllm/vllm-openai:nightly \
  /host-tmp/llmnode_ncu_same_shape_runtime_eager.py
```

结果：

| metric | value |
|---|---|
| prompt tokens | `65536` |
| completion tokens | `512` |
| finish_reason | `length` |
| elapsed | `63.05 s` |
| completion tok/s | `8.12` |

关键观察：

- 日志明确显示：

```text
Enforce eager set, disabling torch.compile and CUDAGraphs
```

- 同形状 `64K + 512` 在 eager 路径下仍能跑通。
- eager 会把速度从约 `12.44 tok/s` 拉低到约 `8.12 tok/s`，但它是更干净的 profiling 候选路径。

## 5. `ncu` 尝试矩阵

### 5.1 已尝试命令族

1. 默认 runtime-only 路径 + `Marlin` filter
2. 默认 runtime-only 路径 + 无 filter 诊断
3. 单进程路径 `VLLM_ENABLE_V1_MULTIPROCESSING=0`
4. 单进程 + eager 路径

代表性命令族：

```bash
docker run --rm --gpus all --ipc=host \
  -e HOME=/tmp \
  -e VLLM_ENABLE_V1_MULTIPROCESSING=0 \
  -v /proj02/liuheshan/llmnode/models/Qwen/Qwen3.6-27B-AWQ-INT4:/model:ro \
  -v /tmp:/host-tmp \
  -v /opt/anaconda3/pkgs/nsight-compute-2026.1.1.2-h934865d_0/nsight-compute-2026.1.1:/host-ncu:ro \
  --entrypoint /host-ncu/ncu \
  vllm/vllm-openai:nightly \
  --target-processes all \
  --kernel-name 'regex:.*Marlin.*' \
  --section LaunchStats \
  --section Occupancy \
  --section MemoryWorkloadAnalysis \
  --launch-count 6 \
  --profile-from-start on \
  --export /host-tmp/llmnode-awq-64k512-marlin-mp0-eager-lc6 \
  --force-overwrite true \
  python3 /host-tmp/llmnode_ncu_same_shape_runtime_eager.py
```

### 5.2 当前结果

| case | 运行状态 | 结果 |
|---|---|---|
| 默认 compile/graph 路径 + `Marlin` filter | 进程可起 | `No kernels were profiled` |
| 默认 compile/graph 路径 + 无 filter 诊断 | 进程可起 | `No kernels were profiled` |
| 单进程路径 `VLLM_ENABLE_V1_MULTIPROCESSING=0` | 进程可起 | `No kernels were profiled` |
| 单进程 + eager 路径 | 进程可起 | `No kernels were profiled` |

补充观察：

- 这几轮失败后，`/tmp` 下没有留下可用 `.ncu-rep` 导出文件。
- 宿主 `ncu --help` 已确认这里的 `attach` 语义是：
  `attach to launched application`，即先 `ncu --mode=launch`，再 `ncu --mode=attach`，不是直接附着任意一个已经在运行中的 vLLM 服务进程。
- 当前失败形态已经不再是：
  - 权限阻塞
  - `target process terminated before first instrumented API call`
  - `64K` 初始化期 KV 预算不足
- 它已经收敛成更窄的一个问题：

```text
offline 64K same-shape vLLM generate 路径在当前参数组合下仍无法让 ncu 产出 kernel section
```

上面这个结论后来被修正：这些 offline 尝试中的一部分命令使用了 `--force-overwrite true`。在 Nsight Compute 2026.1.1 中，`--force-overwrite` 是无值 flag；多出来的 `true` 会被当成目标程序，导致真正的 Python runtime 脚本没有执行。因此，这组 “No kernels were profiled” 不能再作为 offline 路径不可行的最终证据，只能保留为历史排查记录。

### 5.3 server-under-ncu 路径的额外摸排

为了确认 `offline LLM.generate()` 之外的路径是否可行，本轮又补了一条更接近最终目标的 server-side 诊断。

先写了显式 API server 入口脚本：

```text
/tmp/llmnode_ncu_api_server.py
```

然后做了两类对照：

1. 不包 `ncu`
   - 用 `python3 /host-tmp/llmnode_ncu_api_server.py ...` 直接起服务；
   - 容器可以正常驻留，说明显式脚本入口和这组服务参数本身是有效的。
2. 包 `ncu`
   - 改成：

```text
/host-ncu/ncu ... python3 /host-tmp/llmnode_ncu_api_server.py ...
```

   - 无论是 `vllm serve` CLI、`python -m vllm.entrypoints.openai.api_server`，还是显式脚本入口，都会在约 `1` 秒内退出。

当前最有信息量的一次保留容器诊断，结果是：

- 容器状态：`Exited (0)`
- 启动到退出总时长：约 `1.28 s`
- `docker logs` 只有：

```text
==LOG== Target process 18 terminated before first instrumented API call.
==WARNING== No kernels were profiled.
```

这说明当前新的 server-side 结论是：

```text
同一条显式 Python API server 入口，在不包 ncu 时可以正常驻留；
一旦改成 server-under-ncu，进程会在真正进入服务启动日志前就退出。
```

因此，当前 `V2` 的阻塞点又进一步收窄为：

1. 不是 CLI 参数写错；
2. 不是显式 Python API server 入口本身不可用；
3. 而是 `ncu launch-and-attach` 与当前 long-running API server 启动形态之间仍存在不兼容。

### 5.4 `ncu --mode=launch / --mode=attach` 两步式摸排

为了验证真正的 attach 路径，本轮又补了一次更贴近官方语义的两步式摸排：

1. 用 `--mode=launch` 启动一个 `16K` 轻量代表点的 API server；
2. 再对它做 `--mode=attach`；
3. 最后用 `/tmp/llmnode_server_request.py` 等待 `/v1/models` 并发起单请求。

这一轮拿到三个关键事实：

1. `launch` 本身能挂起来  
   日志会进入 `APIServer` 启动流程，说明两步式方法不是“命令一启动就死”。
2. attach 通道对命名空间敏感  
   从另一个独立容器里直接做 `ncu --mode=attach --hostname 127.0.0.1`，会得到：

```text
No processes found on 127.0.0.1 (ports 49152-49215)
```

   但改成在同一个 `launch` 容器里执行：

```text
docker exec <launch-container> /host-ncu/ncu --mode=attach ...
```

   就能成功连上：

```text
Connected to process 149 (/usr/bin/python3.12)
```

3. 同容器 attach 仍未产出 section  
   当前最有信息量的一次同容器 attach 最后输出：

```text
==PROF== Disconnected from process 149
==WARNING== No kernels were profiled.
==WARNING== Profiling kernels launched by child processes requires the --target-processes all option.
```

进一步摸排后，还确认了两个补充事实：

- `launch` 侧如果漏掉 `--model /model`，服务会错误回退去找 `Qwen/Qwen3-0.6B`，并因为当前容器网络不可达而失败；
  因此显式脚本入口必须同时传位置参数 `/model` 和 `--model /model`。
- 在补上 `--target-processes all` 的 `launch` 侧参数后，两步式链路仍只推进到了 `APIServer` 的早期配置阶段；
  当前窗口下没有走到稳定的模型加载 / ready / 请求执行阶段，也没有产出 `.ncu-rep`。

随后又补了一轮更细的 `16K` 方法对照，新增了四个关键事实：

1. 之前 attach 到的 `PID 149` 不是主服务进程，而是短生命周期子进程：

```text
/usr/bin/python3 -m vllm.model_executor.models.registry
```

   这解释了为什么旧的同容器 attach 会很快断开，并提示 child process。
2. 把 `launch` 侧改成 `--target-processes application-only` 后，同容器 attach 可以稳定连到：

```text
Connected to process 18 (/usr/bin/python3.12)
```

   说明 attach 绑定错进程并不是宿主端口问题，而是 `target-processes all` 下优先命中了短命子进程。
3. 但即使 attach 成功绑定到稳定的 `APIServer pid=18`，真正的执行链仍会继续下沉到后面出现的：

```text
(EngineCore pid=380)
```

   同一次请求里还能观察到：
   - `POST /v1/chat/completions` 返回 `200 OK`
   - 请求耗时约 `73.96 s`
   - `16384 + 512` workload 真实执行完成
4. 在这个 `application-only` 试验里，attach 进程在请求完成后仍未自然产出 report，需要人工中断；`/tmp` 下也没有生成 `.ncu-rep`。
5. 又补了一轮 `target-processes all + delayed attach` 对照：
   - 先让 `launch` 容器继续推进到更晚的启动阶段；
   - 再做同容器 `attach`；
   - attach 仍然优先连到：

```text
Connected to process 149 (/usr/bin/python3.12)
```

   随后依旧是：

```text
==PROF== Disconnected from process 149
==WARNING== No kernels were profiled.
==WARNING== Profiling kernels launched by child processes requires the --target-processes all option.
```

   这说明只靠“延后 attach 时机”还不足以绕开 `model_executor.models.registry` 这一类短生命周期子进程。
6. 又补了一轮 `target-processes-filter` 对照，想直接把 launch 侧目标收窄到 `EngineCore`：
   - `regex:VLLM::EngineCore` 会直接报语法错误：

```text
==ERROR== Invalid expression for --target-processes-filter option. Invalid number of prefixes.
```

   - 改成可接受的 `regex:.*EngineCore.*` 后，launch 容器本身可以正常进入：

```text
==PROF== Waiting for profiler to attach on ports 49152-49215
```

   - 而且进程树里确实能看到：

```text
VLLM::EngineCore
```

   - 但无论是“立刻 attach”，还是“等 `EngineCore` 已经出现后再 attach”，结果都会变成：

```text
==WARNING== No processes found on 127.0.0.1 (ports 49152-49215).
==ERROR== No attachable process found.
```

   这说明 `target-processes-filter` 虽然能被 `launch` 接受，但把目标正向过滤到 `EngineCore` 后，attach 通道本身就不可用了。
7. 又补了一轮 `exclude:python3` 对照，想绕开 `149` 而不直接正向过滤到 `EngineCore`：
   - launch 仍能正常进入 `Waiting for profiler to attach`
   - 进程树里不再出现 `149`
   - 后续确实能看到稳定的：

```text
VLLM::EngineCore
```

   - 但在 `EngineCore` 已经稳定存在后再做同容器 attach，结果依旧是：

```text
==WARNING== No processes found on 127.0.0.1 (ports 49152-49215).
==ERROR== No attachable process found.
```

   这说明不仅“正向过滤到 `EngineCore`”会让 attach 失效，连“只排除 `python3`”这种更保守的过滤也会让 attach 通道消失。

这说明 attach 路径的真实新边界已经进一步收窄为：

```text
两步式 launch/attach 不是完全不能用，
但 vLLM server-side 真正发 kernel 的进程链会从 APIServer 继续下沉到 EngineCore；
只覆盖 APIServer 仍然不足以产出可复查的 kernel section。
```

这说明当前新的 attach 结论是：

```text
两步式 launch/attach 已经不是“完全不会 attach”；
但它在当前环境下仍没有推进到可复现的 server-side kernel section。
```

### 5.5 修正 `--force-overwrite` 后的 offline `ncu` 结果

根因修正：

```text
错误写法：--force-overwrite true
正确写法：--force-overwrite
```

最小脚本验证表明，错误写法下 `true` 被当成目标程序，目标脚本不会执行；正确写法下目标脚本可以正常执行。因此，后续 offline `ncu` 命令统一使用无值 flag。

修正后先跑了 `16K + 512` `Marlin` `LaunchStats` 捕获，用于确认方法有效：

- report: `/tmp/llmnode-awq-16k512-param-marlin-lc1-fixed.ncu-rep`
- 导入验证：`ncu --import ... --page details` 可读到 `void Marlin<...>` kernel
- 关键 LaunchStats：`Block Size=256`、`Grid Size=108`、`Registers Per Thread=255`、`Dynamic Shared Memory Per Block=166.91 Kbyte/block`、`Waves Per SM=1`

随后跑了 `64K + 512` 同形状捕获：

- report: `/tmp/llmnode-awq-64k512-param-marlin-lc1-fixed.ncu-rep`
- runtime JSON: `/tmp/llmnode-ncu-param-64k-ncu-marlin-fixed.json`
- prompt file: `/host-tmp/llmnode_ncu_prompt_64k.txt`
- `max_model_len`: `66048`
- `max_tokens`: `512`
- `enforce_eager`: `true`
- completion tokens: `512`
- finish reason: `length`
- elapsed: `181.66 s`
- completion speed: `2.82 tok/s`

`64K` report 导入验证同样可读到 `void Marlin<...>` kernel，LaunchStats 与 `16K` 样本保持同一类形态：

- `Block Size=256`
- `Grid Size=108`
- `Registers Per Thread=255`
- `Dynamic Shared Memory Per Block=166.91 Kbyte/block`
- `Waves Per SM=1`

这说明 `64K + 512` same-shape 的 `Marlin` `LaunchStats` 已经拿到。需要注意的是，本轮运行期间机器上存在其他用户进程占用 GPU，因此这里的 `181.66 s / 2.82 tok/s` 只能记录为受污染窗口下的 runtime 事实，不能写成主性能结论。

### 5.6 GPU 空闲窗口 clean 复测

在 `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader` 返回空之后，重跑同一条 offline 单进程 + eager 路径。

通用条件：

- `VLLM_ENABLE_V1_MULTIPROCESSING=0`
- `max_model_len=66048`
- `max_tokens=512`
- `enforce_eager=true`
- `gpu_memory_utilization=0.55`
- `max_num_seqs=1`
- `--target-processes all`
- `--section LaunchStats`
- `--launch-count 1`
- `--force-overwrite`

#### 5.6.1 clean `Marlin`

artifact：

- report: `/tmp/llmnode-awq-64k512-clean-marlin-lc1.ncu-rep`
- runtime JSON: `/tmp/llmnode-ncu-param-64k-clean-marlin.json`

runtime 结果：

| metric | value |
|---|---|
| completion tokens | `512` |
| finish reason | `length` |
| elapsed | `176.78 s` |
| completion tok/s | `2.90` |

KV cache 观测：

| metric | value |
|---|---|
| Available KV cache memory | `21.12 GiB` |
| GPU KV cache size | `86,240 tokens` |
| Maximum concurrency for `66,048` tokens/request | `5.01x` |

导入验证：

```text
void Marlin<...>
```

关键 LaunchStats：

| metric | value |
|---|---|
| Block Size | `256` |
| Grid Size | `108` |
| Registers Per Thread | `255` |
| Dynamic Shared Memory Per Block | `166.91 Kbyte/block` |
| Threads | `27,648` |
| Waves Per SM | `1` |

#### 5.6.2 clean `FlashAttention`

artifact：

- report: `/tmp/llmnode-awq-64k512-clean-flashattn-lc1.ncu-rep`
- runtime JSON: `/tmp/llmnode-ncu-param-64k-clean-flashattn.json`

runtime 结果：

| metric | value |
|---|---|
| completion tokens | `512` |
| finish reason | `length` |
| elapsed | `184.96 s` |
| completion tok/s | `2.77` |

KV cache 观测：

| metric | value |
|---|---|
| Available KV cache memory | `21.12 GiB` |
| GPU KV cache size | `86,240 tokens` |
| Maximum concurrency for `66,048` tokens/request | `5.01x` |

导入验证：

```text
void flash_fwd_kernel<...>(Flash_fwd_params)
```

关键 LaunchStats：

| metric | value |
|---|---|
| Block Size | `128` |
| Grid Size | `8,192` |
| Registers Per Thread | `255` |
| Dynamic Shared Memory Per Block | `49.15 Kbyte/block` |
| Threads | `1,048,576` |
| Waves Per SM | `37.93` |

至此，`64K + 512` 主代表点已经具备 clean `Marlin` 与 `FlashAttention` 的同一 workload、同一 `ncu` section 证据。这里的 tok/s 仍是 `ncu` 包裹下的 profiler runtime，不等同于正常 serving 性能。

## 6. 已确认

1. 旧阻塞点“`ncu` 冷启动包裹默认 `262144` 配置会挤掉 KV cache，导致 `64K` 初始化失败”已经被绕开。
2. `max_model_len=66048` 是当前最有效的 same-shape 保护手段：
   - 保住了 `65536 + 512` 的真实 workload
   - 又避免为 `256K` 预留多余 KV 预算
3. `VLLM_ENABLE_V1_MULTIPROCESSING=0` 确实能消掉 `spawn` 路径，进入单进程执行器。
4. `enforce_eager=True` 确实能关掉 `torch.compile + CUDA Graph`，并保持 `64K + 512` workload 可运行。
5. 当前新的真实阻塞点已经不是 workload 能不能跑，也不是 `ncu` 能不能产出主热点 section；clean `Marlin` 与 `FlashAttention` `LaunchStats` 均已可导入。
6. `target-processes all` 下 attach 可能会优先命中短生命周期子进程，而不是稳定的 `APIServer`。
7. 即使 attach 成功绑定到稳定的 `APIServer`，server-side 真正执行 kernel 的关键进程仍会继续下沉到 `EngineCore`。
8. 即使刻意延后到更晚阶段再做 `target-processes all` attach，`ncu` 仍可能优先选中 `model_executor.models.registry` 子进程。
9. `target-processes-filter regex:.*EngineCore.*` 虽能让 `launch` 接受并保留 `EngineCore` 进程，但 attach 阶段会直接失去可连接目标。
10. `target-processes-filter exclude:python3` 虽能绕开 `149`，并保留后续 `EngineCore` 进程，但 attach 阶段同样会直接失去可连接目标。
11. clean 窗口下，`64K + 512` 的 KV cache 观测稳定为 `21.12 GiB` 可用、`86,240 tokens`、`66,048 tokens/request` 最大并发 `5.01x`。

## 7. 仍不确定

1. `Marlin / FlashAttention` 的 `LaunchStats` 已经足够证明主热点 section 可采，但还不足以单独判断 memory behavior 或 cache 层面的瓶颈。
2. 是否需要继续补 `Occupancy / MemoryWorkloadAnalysis`，取决于后续 Stage 12 是否要把优化动作推进到 kernel 层。
3. 单进程 + eager 已经排除了最常见的干扰变量，并成功产出 clean report；但 server-side attach 方法是否能直接成功仍未说明。
4. `server-under-ncu` 当前又暴露出一个新的明确失败形态：
   `ncu` 包裹下的 API server 会在首个 instrumented API 前退出；
   但同一脚本在不包 `ncu` 时可以正常驻留。
5. 两步式 `launch/attach` 的 attach 通道已经部分验证成功：
   - 跨容器 attach 找不到进程；
   - 同容器 attach 可以连到真实 Python 进程；
   - 但 `target-processes all` 可能先连到短命 `model_executor.models.registry` 子进程；
   - `application-only` 虽能稳定连到 `APIServer pid=18`，仍没有覆盖后续 `EngineCore` 的真实 kernel 执行。
6. 当前还不确定 `ncu` 是否存在可用的本地选择策略，能让 `launch/attach` 在 `target-processes all` 下直接绕开 `149`，改为覆盖后续 `EngineCore` 链路。
7. 当前还不确定是否存在一种同时满足下面两点的 `ncu` 进程过滤策略：
   - 不被 `149` 这类短生命周期子进程抢占；
   - 又不会像 `regex:.*EngineCore.*` 一样直接丢失 attach 通道。
8. 当前还不确定 `exclude:python3` 这类保守过滤为什么也会把 attach 通道一起带没；从现象上看，它和正向 `EngineCore` 过滤落到了同一种失败形态。

## 8. 当前阶段结论

本阶段最重要的进展是下面这条边界已经清楚：

```text
64K + 512 same-shape workload 本身已经能稳定构造并运行；
修正 --force-overwrite 后，offline 单进程 + eager 路径可以稳定产出 clean ncu report；
Marlin 与 FlashAttention 的 LaunchStats 均已拿到。
```

因此，`V2` 现在不该再回退去重跑 `16K`，也不该再重复验证“默认 262144 会 OOM”这种旧结论。下一步应收敛到：

1. 用 clean `LaunchStats` 解释 Stage 11 的 launch gap / queue 现象
2. 判断是否需要补 `Occupancy / MemoryWorkloadAnalysis`
3. 如必须贴近真实 OpenAI server 请求路径，再继续攻克 server-side `launch + attach`

这里的 `attach` 现在应理解为两条候选实现，而不是直接附着任意现成进程：

1. `ncu --mode=launch` 启动 server，再 `ncu --mode=attach`
2. 继续调查 `server-under-ncu` 为什么会在首个 instrumented API 前退出，再配合 NVTX / launch filter 缩小到真实请求窗口

如果未来必须证明 OpenAI server 请求路径与 offline `LLM.generate()` 存在差异，第一条候选实现还应继续细分：

1. attach 需要在同一个 launch 容器内部执行，而不是另起独立容器直接扫 `127.0.0.1`
2. `launch` 侧必须显式带上 `--model /model`
3. 只把 attach 绑到 `APIServer` 还不够，必须继续解决 `EngineCore` 子进程覆盖问题
4. 单纯把 `target-processes-filter` 正向收窄到 `EngineCore` 也不够，因为当前会直接丢掉 attach 通道
5. 只靠 `exclude:python3` 这类保守过滤也不够，因为当前同样会直接丢掉 attach 通道
6. 这条路线现在不是 V2 主线阻塞项，只作为 server-side 差异验证的备用路线

## 9. 下一步

- 下一次只改什么变量：
  不再先改 `target-process coverage`，而是先把 clean `Marlin / FlashAttention` `LaunchStats` 回流到 Stage 11 / Stage 12 的瓶颈解释。
- 预期要验证什么：
  当前 `64K + 512` 的主热点更适合通过参数、调度、batching / chunked prefill 边界调整，还是需要继续进入 kernel-level 深采。
- 可选补采：
  如果 Stage 12 需要 kernel-level 结论，再补 `Occupancy / MemoryWorkloadAnalysis`，优先仍走已经验证可用的 offline 单进程 + eager 路径。
- 当前不再优先做什么：
  不再重复默认 `262144` 冷启动包裹式 `ncu`，不再优先攻克 server-side attach，除非必须证明 OpenAI server 请求路径与 offline `LLM.generate()` 存在差异。
