# 大模型推理性能调优学习过程记录

> 文档定位：这是 `docs/knowledge/llm-serving-optimization/` 下的学习过程记录，不是 `llmnode` 项目蓝图、契约或路线图。  
> 放置位置：`/proj02/liuheshan/llmnode/docs/knowledge/llm-serving-optimization/learning-log.md`。  
> 当前目标：从零基础开始，借助当前 `llmnode` 部署项目，逐步建立大模型推理部署、性能分析、量化调优、CUDA/Triton Kernel 优化和芯片/编译器协同分析能力。

## 1. 学习目标

目标岗位能力可以拆成六条主线：

1. 能在自研 GPU 或指定 GPU 环境上部署并调优大模型推理服务，重点框架包括 `vLLM` 和 `SGLang`。
2. 能分析 `GLM / Qwen / DeepSeek` 等模型结构，理解 Attention、MLP、MoE、Rope、KV cache 等关键模块的计算和访存特征。
3. 能定位推理瓶颈，判断问题主要来自算力、显存、KV cache、内存带宽、通信、调度还是框架开销。
4. 能理解并实践 `FP8 / INT8 / AWQ / GPTQ` 等量化加速方式，知道量化对显存、吞吐、延迟和精度的影响。
5. 能阅读、编写和优化 CUDA / Triton Kernel，先从 GEMM、Attention、Norm、Rope 等常见算子开始。
6. 能使用 Nsight、torch profiler、框架日志和硬件计数器，与芯片和编译器团队一起分析后端性能问题。

这份记录不追求一次性学完所有内容，而是把每个知识点落到当前项目可执行的实验和可复盘的结论上。

## 2. 当前项目训练场

当前 `llmnode` 项目适合作为入门训练场，因为它已经具备一条完整的本地推理服务链路：

- 正式控制入口：`python -m llmnode.control`
- 当前正式运行形态：单机本地 LLM 节点控制与网关系统
- 已纳入控制面边界的后端：`vLLM / llama.cpp / SGLang`
- 主要模型实验对象：`Qwen3.6-27B`、`Qwen3.6-35B-A3B`
- 已出现的量化形态：`FP8`、`AWQ-4bit`、`AWQ-INT4`、`NVFP4`、`GGUF Q4_K_M`
- 已有观测方向：长上下文、KV cache、显存占用、completion tok/s、端到端延迟、ready 状态、启动日志解析
- 已有自动化能力：性能实验室可创建、查询、取消 benchmark 任务，结果写入 `runtime/data/benchmarks/<run_id>/`

建议优先阅读：

1. `README.md`
2. `docs/process/run.md`
3. `docs/contracts/control-plane.md`
4. `docs/knowledge/runtime-and-backends/backend_integration_qa.md`
5. `docs/knowledge/models-and-formats/model_context_performance.md`
6. `docs/superpowers/specs/2026-06-02-performance-lab-design.md`

## 3. 总体学习路线

### 阶段 0：补齐工程基本功

目标：能看懂项目命令、日志、配置和基本 Python 代码。

需要掌握：

- Linux 常用命令：`ps`、`ss`、`curl`、`tail`、`rg`、`du`、`df`
- Docker 基础：镜像、容器、端口、挂载、日志、`docker inspect`
- Python 基础：模块入口、虚拟环境、dataclass、FastAPI 基础
- Git 基础：查看改动、分支、提交、避免误删用户改动
- GPU 基础命令：`nvidia-smi`、显存占用、进程查询

结合项目练习：

```bash
cd /proj02/liuheshan/llmnode
/home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control env
/home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control status
/home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control doctor
```

记录重点：

- 当前 Python 环境是什么
- 当前激活的 backend profile 是什么
- 当前后端类型是 `vllm`、`llama.cpp` 还是 `sglang`
- 模型目录、runtime 目录、日志目录在哪里
- doctor 给出的下一步建议是什么

阶段成果：

- 能独立解释 `llmnode` 从控制命令到后端容器再到 gateway 的启动链路。

### 阶段 1：跑通当前部署链路

目标：理解“服务能不能起来”和“服务能不能稳定推理”不是同一件事。

需要掌握：

- `start / stop / restart / status / doctor / logs` 的作用
- `http_ready` 和 `inference_ready` 的区别
- `warming_up / ready / degraded` 等状态含义
- gateway、node-agent、backend 容器的分工

结合项目练习：

```bash
cd /proj02/liuheshan/llmnode
/home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control start
/home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control status
/home/heshan/.conda/envs/paper2any/bin/python -m llmnode.control logs --target backend
curl -sS -m 5 http://127.0.0.1:15673/v1/models
```

记录重点：

- 模型加载耗时
- 模型权重占用显存
- 可用 KV cache 显存
- 是否出现 warming_up 或 503
- 服务端返回的模型名

阶段成果：

- 能从日志判断服务是“没启动”、“HTTP 可达但推理未就绪”，还是“推理 ready”。

### 阶段 2：理解 vLLM / SGLang 推理框架机制

目标：知道框架为什么能提升吞吐，以及哪些参数会影响性能。

需要掌握：

- vLLM 的 PagedAttention、KV cache 管理、continuous batching
- SGLang 的前端协议、调度、KV cache、reasoning parser
- `max_model_len`、`gpu_memory_utilization`、`max_num_seqs`、`max_tokens`
- SGLang 中 `mem_fraction_static`、`max_running_requests`、`tp_size`
- llama.cpp 与 vLLM/SGLang 的定位差异

结合项目练习：

- 对比 `docs/knowledge/runtime-and-backends/backend_integration_qa.md` 里的三后端问题。
- 观察 SGLang 为什么需要 `--reasoning-parser qwen3`。
- 观察 vLLM 显存不足时的启动失败日志。
- 理解“旧容器被复用导致新参数未生效”的排查方法。

记录重点：

- 每个后端最关键的启动参数
- 每个参数影响显存、吞吐还是可服务上下文
- 参数是否真的生效，如何用日志或 `docker inspect` 验证

阶段成果：

- 能解释一次 vLLM 或 SGLang 后端配置修改后，应该如何验证新参数已经进入真实容器。

### 阶段 3：理解模型结构与瓶颈来源

目标：能把模型结构和性能现象联系起来。

需要掌握：

- Transformer 基本结构：Embedding、Attention、MLP、Norm、Rope、LM Head
- Attention 的计算复杂度和 KV cache 显存成本
- Prefill 和 Decode 的差异
- 长上下文下为什么 prefill 变慢
- MoE 模型中的专家路由、top-k experts、专家 GEMM、负载不均衡
- Qwen、DeepSeek、GLM 这类模型常见结构差异

结合项目练习：

- 以 `Qwen3.6-35B-A3B-FP8` 为当前主案例。
- 观察 `4K / 32K / 64K / 128K / 172K / 256K` 的 tok/s 下降。
- 对比 `35B-A3B-FP8`、`35B-A3B-AWQ-4bit`、`27B-NVFP4`、`27B-AWQ-INT4` 的长上下文表现。

记录重点：

- prompt token 数增长后，completion tok/s 如何变化
- 端到端时延如何变化
- 权重显存和 KV cache 显存是否成为瓶颈
- 哪些结论来自实测，哪些只是推断

阶段成果：

- 能写出一页分析：为什么 `256K` 上下文能跑通，但交互体验仍然很慢。

### 阶段 4：建立 benchmark 与瓶颈分析习惯

目标：能做可复现的性能实验，而不是只看一次日志。

需要掌握：

- benchmark 的基本口径：warmup、measure、平均值、中位数、min/max
- 指标含义：TTFT、TPOT、completion tok/s、端到端延迟、成功率、错误率
- 过程采样：显存、KV cache usage、容器状态、队列长度
- 对照实验：一次只改一个变量

结合项目练习：

- 使用性能实验室跑同一模型不同上下文长度。
- 使用同一上下文长度对比不同量化 profile。
- 使用启动日志解析判断显存和 KV cache 边界。

推荐实验表：

| 实验 | 固定项 | 变量 | 观察指标 |
|---|---|---|---|
| 长上下文阶梯 | 模型、后端、量化 | prompt tokens | tok/s、端到端延迟、KV usage |
| 量化对比 | 后端、prompt tokens | FP8 / AWQ / NVFP4 | 权重显存、tok/s、错误率 |
| 显存参数对比 | 模型、prompt tokens | gpu_memory_utilization | 可用 KV、是否启动、是否 OOM |
| 后端对比 | 模型或近似模型 | vLLM / SGLang / llama.cpp | ready 时间、tok/s、稳定性 |

阶段成果：

- 能产出一份小型实验报告，说明实验条件、结果、结论和不确定性。

### 阶段 5：学习量化加速

目标：理解量化不是“位数越低越快”，而是要结合硬件、Kernel、反量化和框架支持。

需要掌握：

- FP16 / BF16 / FP8 / INT8 / INT4 的基本区别
- AWQ、GPTQ 的基本思想
- 权重量化和激活量化的区别
- W4A16、W8A8、FP8 的常见部署含义
- 量化对显存、带宽、Tensor Core、反量化开销的影响
- 精度回归与性能回归都要测

结合项目练习：

- 对比 `Qwen3.6-35B-A3B-FP8` 和 `Qwen3.6-35B-A3B-AWQ-4bit`。
- 对比 `Qwen3.6-27B-AWQ-INT4` 和 `Qwen3.6-27B-NVFP4`。
- 记录不同 profile 的权重显存、KV cache、tok/s 和端到端延迟。

阶段成果：

- 能解释为什么某个 INT4/AWQ 配置显存更低，但长上下文速度不一定更好。

### 阶段 6：学习 CUDA / Triton Kernel

目标：从会用框架，逐步走向能看懂并优化关键算子。

入门顺序：

1. GPU 执行模型：SM、warp、thread block、register、shared memory、global memory
2. 内存层次：HBM、L2、shared memory、寄存器
3. 常见性能指标：occupancy、memory bandwidth、arithmetic intensity、warp stall
4. CUDA 基础 Kernel：vector add、reduction、matmul
5. Triton 基础 Kernel：block matmul、layer norm、Rope
6. Attention Kernel：FlashAttention 思路、tiling、online softmax
7. MoE Kernel：专家分发、grouped GEMM、负载均衡

结合项目练习：

- 先不要急着改框架源码。
- 先用独立小实验复现 GEMM、Norm、Rope 的性能差异。
- 再观察 vLLM/SGLang 对 Attention 和量化 GEMM 的调用路径。
- 最后把 profiler 结果和项目 benchmark 结果关联起来。

阶段成果：

- 能写出一个 Triton LayerNorm 或 Rope 小 Kernel，并说明它的访存瓶颈在哪里。

### 阶段 7：学习 Nsight 与 profiler

目标：能用工具证明瓶颈，而不是只凭感觉判断。

需要掌握：

- Nsight Systems：看时间线、CPU/GPU overlap、kernel 排布、空洞
- Nsight Compute：看单个 kernel 的占用率、访存、指令、stall 原因
- torch profiler：看框架层 operator 和 kernel 时间
- vLLM/SGLang 日志：看模型加载、KV cache、并发、错误

结合项目练习：

- 对一次 `4K` 请求和一次 `256K` 请求分别采 trace。
- 对比 prefill 阶段和 decode 阶段的 kernel 分布。
- 找到耗时最大的 Attention/GEMM/Norm/Rope 相关 kernel。
- 判断瓶颈更像算力不足、访存不足、调度空洞还是同步开销。

阶段成果：

- 能产出一份 profiler 截图或表格，指出最值得优化的 1 到 3 个 kernel 或阶段。

### 阶段 8：芯片 / 编译器协同视角

目标：能把框架现象翻译成芯片和编译器团队能处理的问题。

需要掌握：

- 如何描述 workload：模型、batch、seq_len、dtype、算子、shape
- 如何描述瓶颈：算力、带宽、cache miss、kernel launch、同步、通信
- 如何提供最小复现：独立脚本、固定输入 shape、固定 dtype
- 如何给编译器团队反馈：哪个 pattern 没 fuse、哪个 kernel 生成差、哪个 layout 不友好

结合项目练习：

- 从性能实验室结果中挑一个稳定慢点，例如 `256K` 长上下文。
- 提取模型、后端、dtype、prompt tokens、output tokens、显存参数。
- 用 profiler 找出关键 kernel。
- 写成一个“后端优化 issue 模板”。

阶段成果：

- 能把“模型慢”改写成“在某 shape 下某类 kernel 或阶段慢，并提供复现和证据”。




## 4. 每次学习记录模板

建议每次学习都用同一个模板，方便后续复盘。

```markdown
## YYYY-MM-DD：主题

### 今日目标

- 本次想弄懂什么问题：

### 项目上下文

- 后端：
- 模型：
- profile：
- 关键参数：
- 命令：

### 观察结果

- 启动日志：
- 显存：
- KV cache：
- tok/s：
- 端到端延迟：
- 错误或异常：

### 初步分析

- 我认为瓶颈可能是：
- 证据：
- 还不能确认的是：

### 下一步实验

- 下一次只改变的变量：
- 预期现象：
- 如何判断结论成立：

### 岗位能力映射

- 对应能力：
- 今天补齐了什么：
- 还缺什么：
```

## 5. 当前项目可做的实战题

### 实战题 1：解释长上下文性能下降

问题：

- 为什么 `4K -> 256K` 后，completion tok/s 会明显下降？

项目材料：

- `docs/knowledge/models-and-formats/model_context_performance.md`
- `Qwen3.6-35B-A3B-FP8`
- `Qwen3.6-35B-A3B-AWQ-4bit`
- `Qwen3.6-27B-NVFP4`

要求产出：

- 一张对比表
- 一段对 prefill、KV cache、Attention 访存的解释
- 明确哪些是实测结论，哪些是推断

### 实战题 2：分析 vLLM KV cache 边界

问题：

- 为什么 `gpu_memory_utilization=0.5` 时可能无法支撑 `max_model_len=262144`？

项目材料：

- vLLM 启动日志
- `Available KV cache memory`
- `GPU KV cache size`
- `Maximum concurrency for 262,144 tokens per request`

要求产出：

- 记录启动参数和日志关键行
- 解释权重显存、KV 显存和最大上下文之间的关系
- 说明为什么不能简单用 `GPU KV cache size tokens` 线性外推所有模型的最大 prompt token

### 实战题 3：比较 FP8 / AWQ / NVFP4

问题：

- 为什么不同量化格式的显存和速度表现不完全一致？

项目材料：

- `Qwen3.6-35B-A3B-FP8`
- `Qwen3.6-35B-A3B-AWQ-4bit`
- `Qwen3.6-27B-AWQ-INT4`
- `Qwen3.6-27B-NVFP4`

要求产出：

- 同 token 长度下的 tok/s 对比
- 权重显存对比
- 端到端延迟对比
- 解释可能的反量化、Kernel 支持和硬件路径影响

### 实战题 4：SGLang ready 慢或不稳定排查

问题：

- SGLang 已经分配 KV cache，但服务没有稳定开放时，应该如何排查？

项目材料：

- `docs/knowledge/runtime-and-backends/backend_integration_qa.md`
- `docs/contracts/control-plane.md`
- SGLang 启动日志

要求产出：

- 区分容器启动、HTTP ready、inference ready
- 检查 `reasoning_parser`、`tp_size`、镜像依赖
- 给出下一步最小验证命令

### 实战题 5：从框架调参走向 Kernel 分析

问题：

- 当前最慢的请求阶段到底是 Attention、GEMM、Norm、Rope，还是调度/同步？

项目材料：

- 性能实验室结果
- torch profiler / Nsight trace
- vLLM 或 SGLang 请求日志

要求产出：

- 一张 kernel 耗时表
- 一个最小复现 shape
- 一个给芯片/编译器团队看的问题描述

## 6. 面试可讲项目案例积累

每完成一个阶段，沉淀一个可讲案例。建议最终形成下面 5 个案例：

1. **本地大模型推理网关部署案例**
   - 讲清楚 `gateway-api / node-agent / backend / web-console` 的分工。

2. **vLLM 长上下文容量与性能分析案例**
   - 讲清楚 `max_model_len`、`gpu_memory_utilization`、KV cache 和 `256K` 请求的关系。

3. **三后端联调排障案例**
   - 讲清楚 llama.cpp CUDA 镜像、SGLang reasoning parser、旧容器复用这类问题。

4. **量化格式对比案例**
   - 讲清楚 FP8、AWQ、NVFP4 在显存和速度上的取舍。

5. **Kernel / profiler 优化预研案例**
   - 讲清楚如何从 benchmark 定位到具体 kernel，再把问题转给芯片或编译器团队。

## 7. 每周学习节奏

适合零基础的节奏如下：

| 周期 | 主题 | 产出 |
|---|---|---|
| 第 1 周 | 跑通项目、理解控制面 | 一篇部署链路记录 |
| 第 2 周 | vLLM/SGLang 参数和日志 | 一篇后端参数说明 |
| 第 3 周 | 长上下文和 KV cache | 一篇 256K 性能分析 |
| 第 4 周 | 量化格式对比 | 一篇 FP8/AWQ/NVFP4 对比 |
| 第 5 周 | Transformer 结构和 Attention | 一篇模型结构笔记 |
| 第 6 周 | CUDA/Triton 入门 | 一个小 Kernel 实验 |
| 第 7 周 | Nsight / profiler | 一份 trace 分析报告 |
| 第 8 周 | 综合优化案例 | 一份面试项目复盘 |

## 8. 当前第一步

建议从最小闭环开始，不要直接跳到 CUDA Kernel。

第一步任务：

1. 运行 `llmnode.control env/status/doctor`。
2. 找到当前激活 profile。
3. 找到后端日志。
4. 记录模型加载显存、KV cache 显存、ready 状态。
5. 用模板写第一篇学习记录。

第一篇记录标题建议：

```markdown
## 2026-06-05：第一次理解 llmnode 的大模型部署链路
```

第一篇记录只需要回答三个问题：

1. 当前服务由哪些组件组成？
2. 当前后端和模型是什么？
3. 我如何判断它已经 ready？

把这三个问题回答清楚，就已经完成了从”看岗位要求很虚”到”能在真实项目里开始定位问题”的第一步。

## 9. 实验进展记录

> 详细实验方案见 [experiments/experiment-master-plan.md](./experiments/experiment-master-plan.md)，各阶段报告见 [experiments/](./experiments/)。

### Qwen3.6-27B 各阶段进展

`Qwen3.6-27B` 第一阶段 streaming 最小闭环已经补完：`AWQ-INT4 / NVFP4 / FP8 / BF16 + 16K/64K + output=512` 重复测量、`NVFP4 gpu_memory_utilization=0.6` 确认为默认配置、`AWQ-INT4 64K + output=512` TTFT / TPOT 代表点。

第三阶段 `AWQ-INT4` 并发阶梯已经完成：`concurrency=1/2/4` 均在无外部 GPU 负载环境下跑通，`16K/64K + output=512` 没有 OOM、timeout 或 HTTP error。

Stage 3 已补系统总 output tok/s 近似口径：`16K c1 -> c4` 约 `32.85 -> 53.33 tok/s`，`64K c1 -> c4` 约 `10.85 -> 13.79 tok/s`。这说明 `64K` 并发扩展很弱。

Stage 4 已完成 `AWQ-INT4 64K + output=512` 的 `concurrency=1` 与 `concurrency=4` torch profiler 代表点。证据显示：

1. `prefill`：AWQ Marlin GEMM 是最大热点，FlashAttention 是第二热点。
2. `decode`：AWQ Marlin GEMM 仍是最大热点，attention / FP16 GEMM / sampling 也有可见占比。
3. `concurrency=4` 日志有明确 `Running/Waiting` 排队过程，KV cache usage 峰值约 `74.7%`。
4. c1/c4 trace 都没有超过 `1.0%` 阈值的明确 GPU idle / overlap 机会。

Stage 7 已完成 `AWQ-INT4 + FP8 KV cache` 的容量和速度对照：KV tokens 从普通 AWQ 的 `90,944` 提到 `178,752`，256K max concurrency 从 `1.38x` 提到 `2.68x`；但 `64K + output=512` 单并发平均吞吐为 `9.52 tok/s`，低于普通 AWQ。因此它当前更像容量方案，不是单请求加速方案。

Stage 6 已完成 `NVFP4 64K + output=512` 的 torch profiler 代表点。证据显示：`prefill` 仍由 Marlin GEMM `61.6%` 和 FlashAttention `23.6%` 主导；`decode` 中 Marlin GEMM `41.3%`、普通 BF16 GEMM `23.9%`、FlashAttention `12.6%`。这说明 NVFP4 和 AWQ 共享 Marlin + attention 主热点，但 NVFP4 decode 的普通 BF16 GEMM 占比更明显。

Stage 7 已完成 `FP8 KV cache` 最小质量回归，并开始 Nsight bring-up。普通 AWQ baseline 在 5 个质量用例中通过长上下文、代码、数学 3 项，但严格 JSON 和工具 JSON 因 reasoning 混入失败；FP8 KV 对照只通过长上下文 1 项，相比 baseline 新增 `code_generation` 和 `math_reasoning` 两项退化。因此 `AWQ-INT4 + FP8 KV cache` 当前仍只能视为容量实验配置，不能作为可上线配置。`nsys` 已在 Nsight Compute 2026.1.1 包内找到，并已完成真实 vLLM server 短请求 timeline capture，能生成 `.nsys-rep/.sqlite`，`nsys stats` 可读 CUDA API、GPU kernel、memops 和 CUDA graph 信息；短请求报告中 FlashAttention 与 Marlin 仍是主要 kernel 家族。随后又完成一次 `AWQ-INT4 64K + output=512` offline 请求窗口 capture，使用 `cudaProfilerStart/Stop` 收窄采集范围；请求窗口内 Marlin 占 GPU kernel time `68.1%`，FlashAttention splitkv 占 `23.4%`，CUDA graph trace `368` 行，`cudaGraphLaunch` `369` 次。之后补了一次 server-side `64K + output=512, concurrency=2` capture：两个请求均 `200 OK`，wall time `79.22 s`，vLLM 日志显示 `Running=2 / Waiting=0`，KV usage 峰值约 `37.3%`；Nsight 中 Marlin 占 `68.3%`，FlashAttention splitkv 占 `23.5%`。进一步又补了 server-side `concurrency=4` capture：4 个请求全部 `200 OK`，wall time `136.84 s`，vLLM 日志明确出现 `Running=2 / Waiting=2 -> Running=3 / Waiting=1 -> Running=4 / Waiting=0`，KV usage 峰值约 `74.7%`；Nsight 中 Marlin 占 `68.5%`，FlashAttention splitkv 占 `24.0%`。基于 c4 `.sqlite` 继续拆时间线后，可以再定量补充：kernel span 已覆盖请求 wall time 的 `98.2%`，但 kernel 内部累计 gap 仍约 `20.43 s`，占 kernel span `15.2%`；主要 kernel 全落在同一个 CUDA stream 上，没有看到多流 kernel overlap 证据。这说明当前瓶颈更像大量细碎 launch/sync gap 叠加在单流主热点之上。`/opt/anaconda3/bin/ncu` wrapper 不可用，但 Nsight Compute 2026.1.1 真实二进制可挂载进 vLLM 容器启动。2026-06-10 已确认 `RmProfilingAdminOnly: 0`，旧的 GPU counter 权限阻塞已消失；新的真实难点变成 `ncu` 对 vLLM 冷启动 / warmup 的额外显存与 replay 开销。当前 `64K + output=512` 同形状 workload 在 `ncu` 包裹下会因为 KV cache 预算被挤压而初始化失败；不过更小的 `16K + output=512` 真实 workload 已能在 `ncu` 下完整跑通，而且已经成功拿到真实 `Marlin` kernel 与 `flash_fwd_kernel` 的 `LaunchStats / Occupancy / MemoryWorkloadAnalysis`。其中 Marlin 代表点显示：`achieved occupancy=12.5%`、`registers/thread=255`、`dynamic shared memory/block=166.91 KiB`、`memory throughput≈447.53-490.95 GB/s`、`L2 hit rate≈62.5%`；FlashAttention 代表点显示：`achieved occupancy≈12.43%`、`dynamic shared memory/block=49.15 KiB`、`memory throughput≈19.09-19.29 GB/s`、`L2 hit rate≈98.6%`。

### 当前状态与下一步

所有 V0-V5 工作包均已完成第一轮闭环。V2 最终闭环结论：两个主热点 kernel（Marlin / FlashAttention）的共同瓶颈是 **register 压力（255/thread）**，不是 shared memory。当前最可操作的优化方向在调度层（chunked prefill、`max_num_seqs`），不在 kernel 层。

下一步可选深化方向：

1. **调度层实测**：chunked prefill 对 `64K` TTFT 的影响（只改 `max_num_batched_tokens`）
2. **并发边界确认**：`max_num_seqs=2` vs `4` 的交互式延迟回归
3. **上游追踪**：关注 Marlin / vLLM 是否提供低 register 版本 kernel
4. **新硬件评估**：如有 Hopper / Blackwell 环境，重新评估 NVFP4 / FP8 路线

## 10. 能力分级参考（技能图谱）

> 原 `llm-engineer.md` 内容，合并到此作为学习路线的能力参照。

### 能力分级总览

```text
Level 1: Profiler 级 — 能发现瓶颈在哪
Level 2: Kernel 级 — 能自己写/改代码解决瓶颈
Level 3: 架构级 — 能设计整个 serving 方案并做技术选型
```

### Level 1：Profiler 级（已基本掌握）

| 能力项 | 要点 | 对应学习阶段 |
|---|---|---|
| Benchmark 方法论 | 控变量实验、TTFT/TPOT/E2E/tok/s/QPS/P50/P90/P99、并发阶梯 | 阶段 4 |
| 量化选型与权衡 | BF16/FP8/INT8/INT4/FP4、AWQ/GPTQ、硬件匹配、质量回归 | 阶段 5 |
| KV Cache 内存模型 | 计算公式、GQA/MQA、PagedAttention、vLLM 日志解读 | 阶段 3 |
| 推理框架机制（vLLM） | 请求生命周期、PagedAttention/continuous batching/prefix caching、关键参数 | 阶段 2 |
| Profiler 工具链 | torch profiler → nsys → ncu（从粗到细） | 阶段 7 |
| 瓶颈归因能力 | compute-bound / HBM-bound / scheduling gap / KV pressure / dequant overhead | 阶段 7 |

### Level 2：Kernel 级（待补）

- **CUDA 编程基础**：grid/block/warp/thread、内存层次、shared memory、occupancy 计算
- **Triton 编程**：block-level 模型、核心原语、自动 tiling
- **常见 LLM Kernel**：GEMM（cuBLAS/Marlin/CUTLASS）、FlashAttention、RMSNorm、RoPE、Sampling

### Level 3：架构级（待补）

- **多 GPU 并行**：TP/PP/SP、NCCL 集合通信
- **多框架对比**：vLLM / SGLang / TensorRT-LLM / llama.cpp
- **Speculative Decoding**：draft → verify、Medusa/EAGLE 变体
- **Attention 演进**：MQA → GQA → MLA、FlashAttention v1/v2/v3
- **MoE Serving**：expert routing、EP vs TP、All-to-All 通信
- **生产系统**：负载均衡、autoscaling、A/B 测试、成本优化、可观测性
- **编译优化**：torch.compile、CUDA Graph、XLA/TensorRT

### 学习路径

```text
当前位置（Level 1 完成）
    │
    ▼
CUDA 基础 ──→ Triton 基础 ──→ 能写/改 kernel
    │
    ▼
多 GPU 并行（TP/PP/NCCL）──→ 能部署 70B+ 模型
    │
    ▼
SGLang / TensorRT-LLM 对比 ──→ 能做框架选型
    │
    ▼
Speculative Decoding + MoE ──→ 能优化主流架构
    │
    ▼
生产系统能力 ──→ 能独立设计 serving 架构
```
