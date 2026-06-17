# Profiling 完整指南

> 文档定位：项目知识库中的性能分析完整指南，覆盖方法论（什么时候用、看什么）和实操（怎么用、命令是什么）。
> 目标：从 benchmark 结果走向 kernel 级瓶颈分析，提供可直接复用的操作步骤。
> 更新时间：2026-06-16。

相关专题：

- Benchmark 方法论见 [benchmark-methodology.md](./benchmark-methodology.md)。
- KV cache 专题见 [kv-cache.md](./kv-cache.md)。
- vLLM 深入见 [../serving/vllm-deep-dive.md](../serving/vllm-deep-dive.md)。
- 实际 profiler 实验数据见 [stage4-awq-profiler.md](../experiments/stage4-awq-profiler.md)。
- Nsight 工具链 bring-up 见 [stage6b-nsight-toolchain.md](../experiments/stage6b-nsight-toolchain.md)。

---

## 第一部分：方法论

### 1. 什么时候需要 profiler

先做 benchmark，再做 profiler。

适合上 profiler 的情况：

- 两个 profile 速度差异明显，但原因不清楚。
- 16K 到 64K 掉速严重，需要证明是 attention / KV / HBM。
- output 拉长后 decode 仍慢，需要看 GEMM 或 sampling。
- 多并发 P99 抖动，需要看调度空洞或 CPU/GPU overlap。
- 某个 kernel 或量化路径怀疑没有生效。

不适合一开始就 profiler：

- 服务还没稳定 ready。
- benchmark 口径没固定。
- token 数和输出长度不准确。
- 只跑一次，没有可复现现象。

### 2. 三类工具对比

| 工具 | 全称 | 看什么 | 适合回答 |
|---|---|---|---|
| **torch profiler** | PyTorch Profiler | PyTorch operator + CUDA kernel 关联 | 框架层 operator 和 kernel 怎么对应 |
| **nsys** | Nsight Systems | CPU/GPU timeline、kernel 排布、空洞 | 慢在哪个阶段，GPU 是否空转 |
| **ncu** | Nsight Compute | 单 kernel 访存、occupancy、stall | 某个 kernel 为什么慢 |

**使用顺序**：先 torch profiler / nsys 找阶段和大热点 → 再 ncu 深挖单 kernel。

### 3. Prefill / Decode 怎么看

| 阶段 | 现象 | profiler 重点 |
|---|---|---|
| Prefill | 大 prompt 一次性处理，TTFT 高 | attention、GEMM、Rope、Norm、KV 写入 |
| Decode | 每步生成一个 token，循环多次 | 小 batch GEMM、attention KV 读取、sampling、调度 |

长上下文 prefill 常见热点：

- attention kernel
- GEMM / matmul
- rope
- norm
- KV cache 写入
- memory copy / layout transform

decode 常见热点：

- attention over KV
- small GEMM
- sampling
- CPU scheduler gap
- kernel launch overhead

### 4. 常见瓶颈类型

| 瓶颈 | 表现 | 用什么看 | 下一步 |
|---|---|---|---|
| 算力瓶颈 | Tensor Core 利用高，GEMM 占主导 | nsys + ncu | 看量化、batch、kernel |
| HBM 带宽瓶颈 | memory throughput 高，stall 多 | ncu | 看 KV cache、layout、quantization |
| 调度空洞 | GPU 时间线上有空白 | nsys | 看 batching、CPU scheduler、chunked prefill |
| KV cache 压力 | 长上下文掉速、显存贴边 | torch profiler + nsys | 看 KV dtype、prefix cache、上下文截断 |
| 反量化开销 | 低比特模型 kernel 多且碎 | torch profiler | 看 Marlin/Machete 路径 |
| 通信瓶颈 | 多 GPU 中 NCCL 时间高 | nsys | 看 TP/PP/EP、NVLink/PCIe |

### 5. 采样对象怎么选

不要对所有点都 profiler。第一轮只选 1 到 2 个代表点：

| 点 | 为什么选 |
|---|---|
| `AWQ + 64K prompt + 512 output` | 显存效率候选，decode 占比更合理 |
| `NVFP4 + 64K prompt + 512 output` | 长上下文候选，和 AWQ 对比 |
| `BF16 + 64K prompt + 512 output` | 速度上限参考 |
| `AWQ + 256K prompt + 64/256 output` | 长上下文极限 |

优先级：

```text
先固定一个模型和请求形状，
再比较不同量化或参数。
```

### 6. 从 profiler 到优化动作

| 发现 | 可能动作 |
|---|---|
| prefill attention 占主导 | chunked prefill、FlashAttention 路径、上下文策略 |
| decode KV 读取占主导 | KV cache 量化、prefix cache、减少上下文 |
| 低比特 GEMM 慢 | 换量化 kernel、对比 BF16/AWQ/NVFP4 |
| GPU 空洞多 | 调度参数、并发、max_num_seqs、CPU 侧排查 |
| CUDA graph 占显存大 | 调整图捕获相关配置或显存参数 |
| sampling/CPU 明显 | 检查 tokenizer、stream、JSON/tool parsing |

### 7. 给芯片/编译器团队的问题描述

不要说：

```text
模型很慢。
```

要说：

```text
在 A800 上，Qwen3.6-27B-AWQ-INT4，vLLM，prompt=64K，output=512，concurrency=1。
prefill 阶段占 E2E 的 X%，Top kernel 是 Y，shape 是 Z。
Nsight 显示该 kernel memory stall 高 / Tensor Core 利用低 / launch gap 明显。
复现命令和 trace 路径如下。
```

### 8. 快速决策表

| 你想知道 | 用什么 | 命令 |
|---|---|---|
| 整体慢在哪阶段 | nsys | `nsys stats *.nsys-rep` |
| top 5 kernels 是什么 | torch profiler | `analyze_llm_torch_profile.py` |
| 某个 kernel 为什么慢 | ncu | `ncu --section LaunchStats --kernel-name "regex:.*Marlin.*"` |
| GPU 有没有空洞 | nsys GUI | 打开 `.nsys-rep` 看 timeline |
| prefill 占多少时间 | torch profiler | 分析脚本输出的 prefill table |
| kernel 的 occupancy | ncu | `ncu --section Occupancy` |
| kernel 的访存带宽 | ncu | `ncu --section MemoryWorkloadAnalysis` |
| CPU/GPU 是否重叠 | nsys GUI | Timeline View 看 CPU/GPU 并行 |

---

## 第二部分：实操指南

### 9. Torch Profiler

#### 9.1 启用方式（vLLM 内置）

vLLM 支持通过 profiler API 在运行时启停 torch profiler，无需修改代码。

**步骤一：创建专用 profile**

在 `config/backends/` 下创建 profiler 专用 yaml，关键字段：

```yaml
profiler_config: '{"profiler":"torch","torch_profiler_dir":"/tmp/vllm-profile"}'
profiler_host_dir: "runtime/data/profiles/<your-profile-name>"
```

`profiler_config` 传给 vLLM 的 `--profiler-config` 参数。
`profiler_host_dir` 是宿主机挂载目录，容器内 `/tmp/vllm-profile` 会映射到此路径。

**步骤二：启动 vLLM**

```bash
VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE=<your-profiler-profile> \
  /home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control start --service vllm --daemon
```

**步骤三：采集 trace**

```bash
# 开始采集
curl -sS -X POST http://127.0.0.1:<port>/start_profile

# 发送请求（用 benchmark 脚本或手动 curl）
/home/heshan/.conda/envs/paper2any/bin/python scripts/benchmark_backend.py \
  --profile <your-profile> \
  --targets 65536 --max-tokens 512 --concurrency 1 \
  --warmup-runs 0 --measure-runs 1 \
  --output-dir runtime/data/benchmarks/<output-dir>

# 停止采集
curl -sS -X POST http://127.0.0.1:<port>/stop_profile
```

注意：`stop_profile` 可能超时（30s），但只要日志显示 `Stopping profiler...` 且 trace 文件完整写出即可。

#### 9.2 产出文件

```text
runtime/data/profiles/<your-profile>/
├── rank0.*.pt.trace.json.gz           # 主 trace 文件（gzip 压缩）
├── <hash>.async_llm.*.pt.trace.json.gz  # async LLM trace
└── profiler_out_0.txt                 # 原始表格输出
```

#### 9.3 分析脚本

```bash
/home/heshan/.conda/envs/paper2any/bin/python \
  /home/heshan/.codex/skills/AI-Infra-Auto-Driven-SKILLS/skills/llm-torch-profiler-analysis/scripts/analyze_llm_torch_profile.py \
  --input runtime/data/profiles/<your-profile>
```

输出三张表：

| 表 | 内容 |
|---|---|
| Prefill Kernel Table | prefill 阶段 top kernels、GPU time、占比 |
| Decode Kernel Table | decode 阶段 top kernels、GPU time、占比 |
| Overlap / Fuse Table | GPU idle 机会、kernel 融合机会 |

#### 9.4 采集建议

如果希望更干净地区分 prefill 和 decode，优先采两段：

| trace | prompt | output | 目的 |
|---|---|---:|---|
| prefill | `65536` | `1` | 捕获长上下文 prefill / TTFT 主路径 |
| decode | `1` | `512` | 捕获稳定 decode / sampling 主路径 |

#### 9.5 项目中的实际数据

```text
runtime/data/profiles/stage4-awq-profiler/          # c1 trace
runtime/data/profiles/stage4-awq-profiler-c4/       # c4 trace
```

### 10. Nsight Systems (nsys)

#### 10.1 工具路径

```text
/opt/anaconda3/pkgs/nsight-compute-2026.1.1.2-h934865d_0/nsight-compute-2026.1.1/host/target-linux-x64/nsys
```

vLLM 镜像内未预装 `nsys`，需从宿主挂载进容器。

#### 10.2 容器内 smoke 测试

用最小 Torch CUDA matmul 验证工具链可用：

```bash
docker run --rm --gpus all \
  -e HOME=/tmp \
  -v /opt/anaconda3/pkgs/nsight-compute-2026.1.1.2-h934865d_0/nsight-compute-2026.1.1:/host-ncu:ro \
  -v /tmp:/host-tmp \
  --entrypoint /bin/bash \
  vllm/vllm-openai:nightly \
  -lc '/host-ncu/host/target-linux-x64/nsys profile \
    --force-overwrite=true \
    --sample=none \
    --trace=cuda,nvtx,osrt \
    --output=/host-tmp/llmnode-nsys-container-smoke \
    python3 /tmp/nsys_torch_smoke.py'
```

验证命令：

```bash
nsys stats /tmp/llmnode-nsys-container-smoke.nsys-rep
```

应能看到 CUDA API Summary、GPU Kernel Summary、GPU MemOps Summary。

#### 10.3 Offline 请求窗口 capture

用 `cudaProfilerStart/Stop` 缩小 capture window 到纯请求阶段，避免启动/compile/warmup 污染：

```bash
# 在请求脚本中调用：
# torch.cuda.cudart().cudaProfilerStart()
# ... 发送请求 ...
# torch.cuda.cudart().cudaProfilerStop()

# nsys 命令：
nsys profile \
  --force-overwrite=true \
  --sample=none \
  --trace=cuda,nvtx,osrt \
  --output=/tmp/llmnode-nsys-vllm-offline-awq-64k-512 \
  python3 your_request_script.py
```

#### 10.4 Server-side capture（推荐）

用 `nsys launch/start/stop` 做 server-side capture，覆盖真实 server 调度链路：

```bash
# 步骤一：nsys launch 启动 server
nsys launch --trace=cuda,nvtx,osrt \
  --output=/tmp/llmnode-nsys-vllm-server-awq-64k-c4-512 \
  -- python -m vllm.entrypoints.openai.api_server ...

# 步骤二：等 API ready 后
nsys start

# 步骤三：发送并发请求
curl ... & curl ... & curl ... & curl ...

# 步骤四：请求完成后
nsys stop
```

#### 10.5 产出文件

```text
/tmp/llmnode-nsys-*.nsys-rep      # 主报告文件（二进制，GUI 打开）
/tmp/llmnode-nsys-*.sqlite        # SQLite 数据库（可查询）
/tmp/llmnode-nsys-*-summary.json  # 汇总 JSON（命令行快速查看）
```

#### 10.6 命令行分析

```bash
# 统计汇总
nsys stats /tmp/llmnode-nsys-vllm-server-awq-64k-c4-512.nsys-rep

# 输出包含：
# - CUDA API Summary（cudaLaunchKernel、cudaEventSynchronize 等）
# - GPU Kernel Summary（Marlin、FlashAttention 等）
# - GPU MemOps Summary（cudaMemcpy 等）
# - OS Runtime Summary
```

#### 10.7 关键参数说明

| 参数 | 作用 |
|---|---|
| `--trace=cuda,nvtx,osrt` | 采集 CUDA API、NVTX 标记、OS runtime |
| `--sample=none` | 禁用 CPU sampling，减少 overhead |
| `--force-overwrite` | 覆盖已有输出文件 |
| `--output=<path>` | 输出文件路径（不含扩展名） |

#### 10.8 项目中的实际数据

```text
/tmp/llmnode-nsys-vllm-offline-awq-64k-512.nsys-rep      # offline c1
/tmp/llmnode-nsys-vllm-server-awq-64k-c2-512.nsys-rep    # server c2
/tmp/llmnode-nsys-vllm-server-awq-64k-c4-512.nsys-rep    # server c4
```

### 11. Nsight Compute (ncu)

#### 11.1 工具路径

```bash
# 推荐版本（2026.1.1）
/opt/anaconda3/pkgs/nsight-compute-2026.1.1.2-h934865d_0/nsight-compute-2026.1.1/ncu

# 旧版（2022.3.0）
/opt/anaconda3/nsight-compute/2022.3.0/ncu

# ⚠️ 不可用：/opt/anaconda3/bin/ncu（报 nsight-compute directory is not found）
```

#### 11.2 权限检查

`ncu` 采集 SM occupancy / memory bandwidth 需要内核权限：

```bash
cat /proc/driver/nvidia/params | grep RmProfilingAdminOnly
```

- `RmProfilingAdminOnly: 1` → 需要 root 或修改参数
- `RmProfilingAdminOnly: 0` → 可直接使用

#### 11.3 关键参数

```bash
ncu \
  --force-overwrite \                    # 无值 flag，不要写 true
  --kernel-name "regex:.*Marlin.*" \     # 过滤 kernel（正则）
  --section LaunchStats \                # 启动统计（grid/block/registers）
  --section Occupancy \                  # SM 占用率
  --section MemoryWorkloadAnalysis \     # 访存分析（bandwidth/L2 hit）
  --launch-count 6 \                     # 采集前 N 个匹配的 kernel
  --profile-from-start on \              # 从启动开始 profile
  python3 your_script.py
```

#### 11.4 64K 主代表点采集方法

直接用 `ncu` 包裹默认 `max_model_len=262144` 的 vLLM 会失败，需要三个调整：

| 调整 | 设置 | 作用 |
|---|---|---|
| `max_model_len` | `66048`（从 262144 收窄） | 避免 profiler overhead 压缩 KV cache，导致 64K 初始化失败 |
| `VLLM_ENABLE_V1_MULTIPROCESSING` | `0` | 消除 spawn 子进程，确保 ncu 追踪到真实 kernel |
| `enforce_eager` | `True` | 关闭 torch.compile + CUDA Graph，减少采样干扰 |

完整命令：

```bash
docker run --rm --gpus all \
  -e HOME=/tmp \
  -e VLLM_ENABLE_V1_MULTIPROCESSING=0 \
  -v /opt/anaconda3/pkgs/nsight-compute-2026.1.1.2-h934865d_0/nsight-compute-2026.1.1:/host-ncu:ro \
  -v /path/to/model:/model \
  -v /tmp:/host-tmp \
  --entrypoint /bin/bash \
  vllm/vllm-openai:nightly \
  -lc '/host-ncu/ncu \
    --force-overwrite \
    --kernel-name "regex:.*Marlin.*" \
    --section LaunchStats \
    --launch-count 6 \
    --profile-from-start on \
    --output /host-tmp/ncu-marlin-64k \
    python3 -c "
from vllm import LLM
llm = LLM(model=\"/model\", max_model_len=66048, enforce_eager=True)
llm.generate([\"prompt with 64K tokens...\"], max_tokens=512)
"'
```

#### 11.5 踩坑记录

**`--force-overwrite` 误用**

```bash
# ❌ 错误：true 被当成目标程序，脚本不执行，返回 No kernels were profiled
ncu --force-overwrite true python3 script.py

# ✅ 正确：无值 flag
ncu --force-overwrite python3 script.py
```

**`HOME` 目录权限**

ncu 尝试写入 `~/Documents/NVIDIA Nsight Compute/` 时有权限 warning：

```bash
# 显式设置 HOME
docker run ... -e HOME=/tmp ...
```

**进程过滤**

| 策略 | 效果 |
|---|---|
| `--target-processes all` | 可能优先命中短命子进程 |
| `--target-processes application-only` | 能绑到 APIServer，但不覆盖 EngineCore |
| `--target-processes-filter regex:.*EngineCore.*` | attach 通道直接消失 |

当前推荐：直接用 offline 单进程路径，不依赖 attach。

#### 11.6 产出文件

```text
/tmp/ncu-marlin-64k.ncu-rep    # 主报告文件（GUI 打开）
```

#### 11.7 项目中的实际数据

Stage 6b 已采集的 LaunchStats：

| 指标 | Marlin | FlashAttention |
|---|---|---|
| Block Size | 256 | 128 |
| Grid Size | 108 | 8,192 |
| Registers Per Thread | 255 | 255 |
| Dynamic Shared Memory | 166.91 KiB/block | 49.15 KiB/block |
| Waves Per SM | 1 | 37.93 |
| theoretical occupancy | 12.5% | 12.5% |
| achieved occupancy | 12.5% | 12.43% |
| memory throughput | 447-491 GB/s | 19.09-19.29 GB/s |
| L2 hit rate | 62.5% | 98.6% |

关键发现：两个主热点 kernel 的共同瓶颈是 **register 压力（255/thread）**，不是 shared memory。

---

## 第三部分：图形界面与远程查看

### 12. 图形界面分析工具

#### 12.1 Torch Profiler → TensorBoard

```bash
# 安装 TensorBoard
pip install tensorboard

# 启动 TensorBoard 指向 trace 目录
tensorboard --logdir=runtime/data/profiles/<your-profile> --port=6006

# 浏览器访问：http://<server-ip>:6006
```

TensorBoard 中可查看：

| Tab | 内容 |
|---|---|
| **Trace View** | 时间线瀑布图，查看 operator/kernel 排布 |
| **Operator View** | 按 operator 统计 GPU time |
| **Kernel View** | 按 kernel 统计 GPU time |
| **Memory View** | 显存使用曲线 |

#### 12.2 Torch Profiler → Chrome Trace Viewer（轻量级）

```bash
# Chrome 地址栏输入：
chrome://tracing

# 点击 Load 按钮，选择 .pt.trace.json 或 .pt.trace.json.gz 文件
```

优点：无需安装，Chrome 自带。
缺点：功能比 TensorBoard 少，适合快速查看。

#### 12.3 Nsight Systems → Nsight Systems GUI

```bash
# 下载安装：https://developer.nvidia.com/nsight-systems
# 安装后打开 .nsys-rep 文件
nsight-sys /tmp/llmnode-nsys-vllm-server-awq-64k-c4-512.nsys-rep
```

GUI 中可查看：

| View | 内容 |
|---|---|
| **Timeline View** | CPU/GPU 时间线，kernel 排布，空洞高亮 |
| **Statistics View** | kernel 统计、CUDA API 统计 |
| **NVLink/PCIe View** | 通信分析（多 GPU） |
| **MPI View** | 分布式通信分析 |

#### 12.4 Nsight Compute → Nsight Compute GUI

```bash
# 打开 .ncu-rep 文件
ncu-ui /path/to/report.ncu-rep
```

GUI 中可查看：

| View | 内容 |
|---|---|
| **Source View** | 源码 + PTX + SASS 对照 |
| **Memory Chart** | 访存模式分析 |
| **Roofline Chart** | 算力/带宽 roofline 模型 |
| **Occupancy View** | SM 占用率分析 |

### 13. SSH 远程服务器查看方法

#### 13.1 方法一：SSH 隧道 + 本地浏览器（推荐）

```bash
# 本地终端建立隧道
ssh -L 6006:localhost:6006 user@server      # TensorBoard
ssh -L 8080:localhost:8080 user@server      # 其他 web 工具

# 服务器上启动
tensorboard --logdir=runtime/data/profiles/<your-profile> --port=6006

# 本地浏览器访问 http://localhost:6006
```

#### 13.2 方法二：下载文件到本地分析

```bash
# 从服务器下载 trace 文件
scp user@server:/proj02/liuheshan/llmnode/runtime/data/profiles/<profile>/*.pt.trace.json.gz ./
scp user@server:/tmp/llmnode-nsys-*.nsys-rep ./
scp user@server:/tmp/ncu-*.ncu-rep ./

# 本地用对应 GUI 工具打开
# - .pt.trace.json.gz → TensorBoard 或 chrome://tracing
# - .nsys-rep → Nsight Systems GUI
# - .ncu-rep → Nsight Compute GUI
```

#### 13.3 方法三：命令行分析（无需 GUI）

```bash
# nsys 命令行统计
nsys stats /tmp/llmnode-nsys-vllm-server-awq-64k-c4-512.nsys-rep

# torch profiler 分析脚本
/home/heshan/.conda/envs/paper2any/bin/python \
  /home/heshan/.codex/skills/AI-Infra-Auto-Driven-SKILLS/skills/llm-torch-profiler-analysis/scripts/analyze_llm_torch_profile.py \
  --input runtime/data/profiles/<your-profile>
```

#### 13.4 方法四：VS Code Remote + 端口转发

```bash
# VS Code 连接远程服务器时，会自动转发端口
# 在服务器启动 TensorBoard 后，VS Code 会提示在本地打开
```

---

## 附录

### A. Profiler 报告模板

```markdown
## Profile 对象

- 后端：
- 模型：
- profile：
- prompt tokens：
- output tokens：
- concurrency：
- GPU：
- 命令：

## 总览

- TTFT：
- TPOT：
- E2E latency：
- GPU 利用率：
- 显存峰值：

## 时间线观察

- prefill 时间：
- decode 时间：
- 是否有 GPU 空洞：
- CPU 是否阻塞：

## Top kernels

| kernel | 阶段 | 时间占比 | 初步判断 |
|---|---|---:|---|

## 结论

- 已确认瓶颈：
- 仍是推断：
- 下一步验证：
```

### B. 当前第二阶段建议

先不用追求完整 profiler 体系。最小闭环：

1. 跑 `AWQ + 64K prompt + 512 output`。
2. 记录 TTFT / TPOT / E2E。
3. 采一次 Nsight Systems 或 torch profiler。
4. 标出 prefill 和 decode 大致时间。
5. 列 top 5 kernels。
6. 判断下一步该看 KV cache、量化 kernel，还是调度。
