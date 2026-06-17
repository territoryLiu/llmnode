# 推理核心计算原语：GEMM 与 FlashAttention

> 文档定位：项目知识库中的 LLM serving 优化基础专题，不属于 `llmnode` 项目蓝图、契约或正式路线图。  
> 目标：解释 Transformer 推理中两个最大计算单元——GEMM 和 FlashAttention——是什么、怎么工作、为什么在 prefill 和 decode 阶段表现不同。  
> 更新时间：2026-06-12。  
> 关联：加速方法总览见 [accel-map.md](./accel-map.md)，量化细节见 [../optimization/quantization-deep-dive.md](../optimization/quantization-deep-dive.md)，profiler 实测见 [../performance/profiling-guide.md](../performance/profiling-guide.md)。

## 1. GEMM

### 1.1 是什么

GEMM = General Matrix Multiplication，通用矩阵乘法。Transformer 里每个线性层的核心计算都是 GEMM：

```text
输出 = 输入 × 权重矩阵 + 偏置
```

一层 Transformer 里的 GEMM 包括：

| 位置 | 作用 | 矩阵形状示例 |
|---|---|---|
| QKV projection | 把输入映射到 Q、K、V 三个空间 | `(seq, 4096) × (4096, 4096)` |
| Output projection | Attention 输出投影回 hidden_dim | `(seq, 4096) × (4096, 4096)` |
| FFN up/gate | 前馈网络扩展维度 | `(seq, 4096) × (4096, 11008)` |
| FFN down | 前馈网络压缩回 hidden_dim | `(seq, 11008) × (11008, 4096)` |

27B 模型大约 64 层，每层都有这些 GEMM，所以 GEMM 是推理中占比最大的计算。

### 1.2 Prefill 和 Decode 的区别

GEMM 的性能特征取决于矩阵形状，而 prefill 和 decode 的形状完全不同：

**Prefill**（处理整个 prompt）：

```text
输入形状：(batch_size × seq_len, hidden_dim)
例如：(16384, 4096) × (4096, 4096)
```

两边都大，GPU 几千个 CUDA core 能打满，是 **compute-bound**（算力瓶颈）。计算密度高，GPU 利用率好。

**Decode**（每步生成 1 个 token）：

```text
输入形状：(batch_size, hidden_dim)
例如：(1, 4096) × (4096, 4096)
```

一边很小（只有 1 个 token），矩阵很大（全部权重）。GPU 大部分 core 闲着，是 **memory-bound**（带宽瓶颈）。瓶颈在从显存读权重的速度，不在计算。

### 1.3 量化 GEMM

量化模型的 GEMM 多了一步反量化：

| 路径 | 流程 | 代表 |
|---|---|---|
| BF16 GEMM | 直接算 | `ampere_bf16_s16816gemm` |
| AWQ Marlin GEMM | 4-bit 权重 → 反量化 → 算 | `marlin::Marlin<..., 256, 4, 16, 4, false, ...>` |
| NVFP4 Marlin GEMM | FP4 权重 → 反量化 → 算 | `marlin::Marlin<..., 256, 4, 16, 4, false, ...>` |

反量化在 GPU 的寄存器或 SRAM（片上缓存）里实时完成，结果不存回显存。

### 1.4 量化为什么反而更快

这是最常见的疑问：多了一步反量化，为什么速度反而上升？

答案在于 decode 阶段是 memory-bound，不是 compute-bound。

| | BF16 | AWQ-INT4 |
|---|---|---|
| 权重大小 | 51.1 GiB | 19.05 GiB |
| 读取时间（A800 2 TB/s） | ~25 ms | ~9.5 ms |
| 反量化开销 | 无 | 很小（寄存器内完成） |
| 总时间 | 读 51 GiB | 读 19 GiB + 微量反量化 |

读 19 GiB + 反量化 < 读 51 GiB，所以量化更快。

打个比方：搬 38 块砖回来刷漆，比搬 100 块砖回来直接用更快。

但 prefill 阶段反过来——它是 compute-bound，瓶颈在算不在搬，反量化的额外计算开销就暴露了。Stage 1 实测：BF16 prefill TTFT=4,442ms vs AWQ 6,003ms（16K）。

一句话总结：**量化省的是搬运量，多的是计算量。Decode 搬运是瓶颈，所以量化赢；Prefill 计算是瓶颈，所以量化输。**

### 1.5 实测数据参考

Stage 1 的 GEMM 相关 profiler 数据：

| 指标 | AWQ Marlin (prefill) | AWQ Marlin (decode) |
|---|---|---|
| GPU time 占比 | 61.6%（NVFP4）/ 68%+（Nsight） | 41-68% |
| achieved occupancy | 12.5% | — |
| registers/thread | 255 | — |
| dynamic shared memory/block | 166.91 KiB | — |
| memory throughput | 447-491 GB/s | — |
| L2 hit rate | 62.5% | — |

## 2. FlashAttention

### 2.1 是什么

Self-Attention 的计算：

```text
Attention(Q, K, V) = softmax(Q × K^T / √d) × V
```

其中 Q、K、V 是 Query、Key、Value 三个矩阵，来自输入经 QKV projection 后的结果。

传统实现需要把完整的 `Q × K^T` 注意力矩阵（seq_len × seq_len）写到 GPU 显存（HBM），再读回来算 softmax，再乘 V。长序列下这个中间矩阵巨大：64K 序列的注意力矩阵是 64K × 64K × 2 bytes ≈ 8 GiB。

### 2.2 为什么叫 Flash

FlashAttention 的核心思想是 **tiling**（分块）：把 Q、K、V 切成小块，在 GPU 的 SRAM（片上高速缓存，几十 MB 级别，带宽远高于 HBM）里完成全部计算，不把完整的注意力矩阵写到 HBM。

```text
传统 Attention：
  Q×K^T → 写到 HBM → 读回来 softmax → 写到 HBM → 读回来 ×V → 写到 HBM
  （多次 HBM 往返，带宽浪费）

FlashAttention：
  Q块 × K块 → SRAM 内算 softmax → SRAM 内 × V块 → 累加结果
  （全程 SRAM，只把最终结果写回 HBM）
```

收益：
- 显存：不需要存 seq_len × seq_len 的中间矩阵
- 速度：减少了 HBM 读写次数，Attention 从 memory-bound 变得更高效

### 2.3 Prefill 和 Decode 的区别

**Prefill**：

```text
Q: (seq_len, head_dim)
K: (seq_len, head_dim)
V: (seq_len, head_dim)
注意力矩阵：(seq_len, seq_len)
```

Q、K、V 都是长序列，注意力矩阵很大，计算量大。但 FlashAttention 的 tiling 让 memory 访问模式很高效。

**Decode**：

```text
Q: (1, head_dim)           ← 只有 1 个新生成的 token
K: (kv_len, head_dim)      ← 整个历史序列的 KV cache
V: (kv_len, head_dim)
注意力矩阵：(1, kv_len)
```

Q 只有 1 行，但 K、V 是整个历史（可能几万个 token）。这是 1 × seq_len 的注意力计算，memory-bound——瓶颈在读 KV cache。

### 2.4 Split-KV

FlashAttention 在 decode 阶段使用 split-KV 策略：把 KV cache 分成多块，多个 CUDA block 并行计算各自那块的注意力，最后 combine。这就是 profiler 里看到两个 kernel 的原因：

| Kernel | 作用 |
|---|---|
| `flash_fwd_splitkv_kernel` | 各块并行计算部分注意力 |
| `flash_fwd_splitkv_combine_kernel` | 合并各块结果 |

### 2.5 实测数据参考

Stage 1 的 FlashAttention profiler 数据：

| 指标 | Prefill | Decode |
|---|---|---|
| GPU time 占比 | 23-24% | 12-13% |
| achieved occupancy | 12.43% | — |
| dynamic shared memory/block | 49.15 KiB | — |
| memory throughput | 19.09-19.29 GB/s | — |
| L2 hit rate | 98.6% | — |

L2 hit rate 98.6% 说明 FlashAttention 的 tiling 策略非常有效——数据几乎都在 L2 cache 里命中，不需要反复访问 HBM。

## 3. GPU 存储层次与推理执行模型

### 3.1 GPU 的存储层次

GPU 的存储不是一个扁平的大空间，而是多层速度-容量梯度：

```text
寄存器 (Register)       ← 每个 CUDA core 自己的，最快，极小
    ↕
SRAM (Shared Memory)    ← 每个 SM 共享的片上缓存，快，容量小
    ↕
L2 Cache                ← 全 GPU 共享，中等速度和容量
    ↕
HBM (显存 VRAM)         ← 最大但最慢
```

A800 的具体数值：

| 层级 | 容量 | 带宽 | 延迟 |
|---|---|---|---|
| 寄存器 | ~256 KB / SM | ~TB/s 级 | ~1 cycle |
| SRAM (Shared Memory) | ~164 KiB / SM | ~TB/s 级 | ~几 cycles |
| L2 Cache | ~40 MiB | ~几 TB/s | ~几十 cycles |
| HBM（显存） | 80 GiB | 2 TB/s | ~几百 cycles |

注意带宽的量级差距：SRAM 带宽是 HBM 的几百到上千倍。这就是为什么 FlashAttention 把计算放在 SRAM 里做能大幅提速。

### 3.2 GPU 硬件组织：从 GPU 到 ALU

GPU 的硬件是一个层级结构，理解这个层级才能看懂 profiler 里的 occupancy、warp、block 这些指标。

```text
GPU
 └── GPC (Graphics Processing Cluster)        ← 几个（A800 有 7 个）
      └── SM (Streaming Multiprocessor)        ← 几十个（A800 有 108 个）
           ├── CUDA Core (INT32 / FP32)        ← 每 SM 64 个（A800）
           ├── FP64 Core                       ← 每 SM 32 个（A800）
           ├── Tensor Core                     ← 每 SM 4 个（A800 第三代）
           ├── Special Function Unit (SFU)     ← 超越函数（sin, cos, exp...）
           ├── Load/Store Unit (LD/ST)         ← 内存读写
           ├── Warp Scheduler                  ← 调度 warp 执行
           ├── Register File                   ← 每 SM 256 KB（A800）
           └── Shared Memory / L1 Cache        ← 每 SM 164 KiB（A800）
```

#### SM（Streaming Multiprocessor）

SM 是 GPU 的基本执行单元。一个 GPU 有几十到一百多个 SM，每个 SM 独立运行，可以并行处理不同的 thread block。

A800 有 **108 个 SM**。每个 SM 有：
- 64 个 FP32 CUDA Core
- 32 个 FP64 CUDA Core
- 4 个第三代 Tensor Core
- 256 KB 寄存器文件
- 164 KiB 可配置的 Shared Memory / L1 Cache

SM 的核心职责：接收一个 thread block，把里面的线程分成 warp，调度 warp 在 CUDA Core 和 Tensor Core 上执行。

#### CUDA Core

CUDA Core 是 SM 内部最基础的算术单元，本质上就是一个 **ALU（Arithmetic Logic Unit）**。每个 CUDA Core 在一个时钟周期内能完成一次浮点运算（如 FMA：乘加融合）。

```
一个 CUDA Core = 一个 ALU = 一次浮点/整数运算单元
```

A800 每个 SM 有 64 个 FP32 CUDA Core，108 个 SM 总共 64 × 108 = **6,912 个 FP32 CUDA Core**。

但 CUDA Core 不是独立工作的。它们被组织成 warp，由 Warp Scheduler 统一调度。

#### Warp 和 Thread

**Thread**（线程）是最小执行单位。每个 thread 有自己的寄存器和程序计数器。

**Warp**（线程束）是 GPU 调度的基本单位。一个 warp = **32 个 thread**，它们执行相同的指令（SIMT：Single Instruction, Multiple Thread），但操作不同的数据。

```text
Thread Block（线程块）
 └── Warp 0: thread 0-31   ← 同时执行同一条指令
 └── Warp 1: thread 32-63
 └── Warp 2: thread 64-95
 └── ...
```

一个 SM 可以同时管理多个 warp（通过 warp scheduler 切换）。当一个 warp 在等数据（比如从 HBM 读权重），scheduler 立刻切换到另一个就绪的 warp，让 CUDA Core 不闲着。这叫 **latency hiding**（延迟隐藏）。

#### Register（寄存器）

每个 CUDA Core（更准确地说是每个 thread）有自己的寄存器。寄存器是 GPU 上最快的存储，一个 cycle 就能读写。

A800 每个 SM 有 **256 KB** 寄存器文件。如果一个 SM 同时管理 2048 个 thread（常见上限），每个 thread 可用 256KB / 2048 = **128 个 32-bit 寄存器**。

profiler 里看到的 `registers/thread=255` 意味着 kernel 用满了每个 thread 允许的最大寄存器数（255 是上限），这会限制每个 SM 能同时管理的 thread 数，从而影响 occupancy。

#### Tensor Core

Tensor Core 是 NVIDIA 从 Volta 架构开始加入的专用矩阵运算单元。它不是通用 ALU，而是能在一次操作中完成一个小矩阵乘法（如 4×4 × 4×4）。

| 架构 | Tensor Core 代际 | 支持精度 |
|---|---|---|
| Volta | 第一代 | FP16 |
| Turing | 第二代 | FP16、INT8 |
| Ampere | 第三代 | BF16、FP16、TF32、INT8、INT4 |
| Hopper | 第四代 | FP8、BF16、FP16、INT8 |
| Blackwell | 第五代 | FP4、FP8、FP6、BF16、INT8 |

A800 的第三代 Tensor Core 支持 BF16/FP16/TF32/INT8/INT4，但**不支持原生 FP8**。这就是为什么 A800 上 FP8 走 fallback（weight-only FP8 + Marlin），性能不如 BF16。

Tensor Core 和 CUDA Core 的关系：
- CUDA Core：通用 ALU，一次做一次标量运算
- Tensor Core：专用矩阵单元，一次做一次小矩阵乘法（如 4×4），吞吐远高于 CUDA Core

GEMM kernel 里大部分计算走 Tensor Core，而不是通用 CUDA Core。

#### SM 内部的并行度

一个 SM 内部的资源分配（A800 为例）：

| 资源 | 数量 | 说明 |
|---|---|---|
| FP32 CUDA Core | 64 | 通用浮点运算 |
| Tensor Core | 4 | 矩阵乘法加速 |
| Warp Scheduler | 4 | 每 cycle 可以发射 4 条指令 |
| 最大活跃 warp | 64 | 每 SM 最多管理 64 个 warp = 2048 个 thread |
| 最大活跃 thread | 2048 | 受寄存器和 Shared Memory 限制 |
| 寄存器文件 | 256 KB | 所有活跃 thread 共享 |
| Shared Memory | 最大 164 KiB | 可配置，和 L1 Cache 共享空间 |

#### Cycle（时钟周期）

GPU 有一个时钟在滴答滴答走，每"滴答"一次就是一个 cycle。A800 的时钟频率约 1.41 GHz，意味着每秒走 14.1 亿次 cycle。

```text
时间 ──┬──┬──┬──┬──┬──┬──┬──┬──┬──→
       ↑  ↑  ↑  ↑  ↑  ↑  ↑  ↑  ↑
     cycle cycle cycle ...
     1     2     3
```

每条 GPU 指令需要若干个 cycle 执行完：

| 操作 | 大约需要 |
|---|---|
| 寄存器读写 | 1 cycle |
| CUDA Core 做一次 FMA（乘加） | 几个 cycle |
| 从 L2 Cache 读数据 | 几十个 cycle |
| 从 HBM（显存）读数据 | 几百个 cycle |

一次 HBM 读取的时间里，CUDA Core 本可以做几百次运算。这就是为什么需要 latency hiding——让 Core 在等数据的时候干别的活。

#### Thread、CUDA Core、ALU、Register 的关系

这四个概念不在同一个层次上，容易混淆：

```text
层次          概念              本质
─────────────────────────────────────────────────
物理硬件      CUDA Core / ALU   焊在芯片上的电路，做加减乘除
物理硬件      Register          焊在芯片上的存储单元，极快
逻辑概念      Thread            一个"要执行的任务"，不是一个物理东西
调度单位      Warp              32 个 thread 打包，统一调度
```

**Thread 不是硬件**。Thread 是 CUDA 编程模型里的概念——它代表"一个要执行的计算任务"，有自己的程序计数器、寄存器和逻辑身份（thread ID）。但 thread **没有自己专属的 CUDA Core**，它只有在被调度执行时才临时占用一个 CUDA Core。

**CUDA Core / ALU 是硬件**。它焊在芯片上，只能做一件事：把两个数加起来或乘起来。它没有记忆，不知道"我在帮哪个 thread 干活"。

**Register 是 per-thread 的**。寄存器是物理硬件（SM 里的一块 SRAM），但逻辑上按 thread 分配。当一个 thread 被调度到 CUDA Core 上执行时，Warp Scheduler 从寄存器文件里取出这个 thread 的数据送到 ALU，算完写回。

```text
Thread 0 的寄存器 ──读取──→ CUDA Core 0 (ALU) ──写回──→ Thread 0 的寄存器
Thread 1 的寄存器 ──读取──→ CUDA Core 1 (ALU) ──写回──→ Thread 1 的寄存器
```

为什么不 1:1 绑定？因为 A800 只有 6,912 个 CUDA Core，但可以同时管理 221,184 个 thread（108 SM × 2048 thread/SM）。大部分 thread 大部分时间在等数据（从 HBM 读），Warp Scheduler 通过在 warp 之间快速切换让 Core 尽量不空闲。

#### Warp 详解

Warp = **32 个 thread 打包成一组**，是 GPU 调度的最小单位。为什么是 32？这是硬件设计的选择——Warp Scheduler 一次发射一条指令，分给 32 个 CUDA Core 并行执行（SIMT），只需要译码一次。

**Warp 的生命周期**：

```text
创建：thread block 被分配到 SM 上，按 32 个一组切分成多个 warp
  ↓
就绪：warp 的所有操作数都准备好了，可以执行
  ↓
执行：Warp Scheduler 发射指令，32 个 CUDA Core 同时算
  ↓
阻塞：遇到长延迟操作（如读 HBM），warp 挂起等待
  ↓
就绪：数据到了，warp 重新可以执行
  ↓
完成：warp 里所有 thread 都执行完
```

一个 SM 可以同时管理 64 个 warp，但每个 cycle 只有几个能真正执行。Warp Scheduler 在这些 warp 之间快速切换，Core 尽量不空闲。

**Warp Diverge（分支分歧）**：

因为 32 个 thread 执行同一条指令，如果代码里有 if-else：

```cuda
if (thread_id < 16) {
    A();  // Thread 0-15 要走这里
} else {
    B();  // Thread 16-31 要走这里
}
```

GPU 不能同时走两个分支。它会：
1. 先让 Thread 0-15 执行 A()，Thread 16-31 暂停等待
2. 再让 Thread 16-31 执行 B()，Thread 0-15 暂停等待
3. 两轮都完成后才继续

这叫 warp diverge，会浪费一半的 Core 算力。LLM 推理的 GEMM kernel 里通常没有分支（纯矩阵运算），所以不太受这个影响。

#### Occupancy 详解

Occupancy = **SM 上实际活跃的 warp 数 / SM 能容纳的最大 warp 数**。

A800 每个 SM 最多 64 个 warp（2048 个 thread）。如果某个 kernel 只能让 8 个 warp 同时驻留在 SM 上，occupancy = 8/64 = 12.5%。

**什么限制了 occupancy**：

SM 的资源是有限的，多种资源共同限制能驻留多少 warp：

| 资源 | A800 每 SM | 影响 |
|---|---|---|
| 寄存器文件 | 256 KB | 每个 thread 用的寄存器越多，能放的 thread 越少 |
| Shared Memory | 最多 164 KiB | kernel 用的 Shared Memory 越多，能放的 block 越少 |
| 最大 warp 数 | 64 | 硬上限 |
| 最大 thread 数 | 2048 | 硬上限 |

举个例子：

```text
情况 A：kernel 每 thread 用 32 个寄存器
  256 KB / (32 × 4 bytes) / 32 threads = 64 个 warp 可以驻留
  → occupancy = 64/64 = 100%

情况 B：kernel 每 thread 用 255 个寄存器（Marlin 的情况）
  256 KB / (255 × 4 bytes) / 32 threads ≈ 8 个 warp 可以驻留
  → occupancy = 8/64 = 12.5%
```

**低 occupancy 好不好**：

| 场景 | 低 occupancy 的影响 |
|---|---|
| memory-bound（等 HBM 数据） | 影响小。warp 在等数据，多几个 warp 也只是多几个等的，Core 还是闲着 |
| compute-bound（算力打满） | 影响大。warp 太少 → 等数据的 warp 不够 → Core 没有别的活干 → 空转 |

Marlin kernel 的 `achieved occupancy=12.5%` 但 GPU time 占 68%——说明它虽然是低 occupancy，但每个 warp 的 ALU 利用率很高（Tensor Core 在密集做矩阵乘），不需要靠大量 warp 来隐藏延迟。

#### 一次完整的执行流程

以一个 warp（32 个 thread）执行一次 FMA 为例：

```text
1. Warp Scheduler 选中一个就绪的 warp（32 个 thread）

2. 从寄存器文件读取这 32 个 thread 各自的操作数
   Thread 0: reg[0]=a0, reg[1]=b0, reg[2]=c0
   Thread 1: reg[0]=a1, reg[1]=b1, reg[2]=c1
   ...
   Thread 31: reg[0]=a31, reg[1]=b31, reg[2]=c31

3. 32 个 CUDA Core 同时执行（SIMT）
   Core 0:  result0 = a0 * b0 + c0
   Core 1:  result1 = a1 * b1 + c1
   ...
   Core 31: result31 = a31 * b31 + c31

4. 32 个结果写回各自 thread 的寄存器
   Thread 0: reg[3] = result0
   Thread 1: reg[3] = result1
   ...
```

一个 cycle 完成。Warp Scheduler 立刻准备下一条指令。

#### Profiler 指标对应关系

| Profiler 指标 | 含义 |
|---|---|
| `registers/thread=255` | 每个 thread 用了 255 个寄存器（上限），SM 能同时驻留的 thread 数减少 |
| `achieved occupancy=12.5%` | 实际活跃 warp 数只有最大值的 12.5% |
| `CUDA Core` / `Tensor Core` | kernel 执行时间，本质是 ALU 的忙碌时间 |
| `warp stall` | warp 在等什么（数据、指令、同步...） |

#### 和 CPU 的对比

| | CPU | GPU |
|---|---|---|
| 核心数 | 几个到几十个 | 几千个 CUDA Core |
| 单核能力 | 强（复杂控制流、分支预测、乱序执行） | 弱（简单 ALU，依赖大量并行） |
| 擅长 | 串行任务、复杂逻辑、低延迟 | 大规模并行计算、高吞吐 |
| 线程模型 | 每线程有完整上下文（OS 线程） | 轻量 thread，由硬件 warp scheduler 管理 |
| 内存模型 | 大缓存 + 主存 | 大带宽 HBM + 小片上缓存 |

GPU 不是在"单个快速核心"上赢 CPU，而是在"几千个简单核心并行"上赢。LLM 推理里的矩阵乘法天然是大规模并行任务（矩阵的每个元素可以独立计算），所以 GPU 比 CPU 快几个数量级。

### 3.3 模型权重住在哪里

27B 模型的权重（BF16 约 51 GiB，AWQ-INT4 约 19 GiB）全部住在 HBM（显存）里。SRAM 只有几十 KiB 级别，连一层的权重都装不下（一层线性层可能几百 MiB）。

所以推理时不可能把整个模型搬到 SRAM 里算，只能**流式处理**。

### 3.4 实际执行过程：搬一层算一层

以一个线性层 `(1, 4096) × (4096, 4096)` 为例（decode 阶段）：

```text
Step 1: 从 HBM 把权重矩阵的一块（tile）搬到 SRAM
        比如搬 128×128 的一块，约 128×128×2 bytes = 32 KiB

Step 2: 输入向量已经在寄存器里了，和 SRAM 里的权重块做矩阵乘
        ALU 算完，结果写到寄存器

Step 3: 搬下一块权重，重复，直到这层的整个矩阵算完

Step 4: 这层的输出写回 HBM（或留在 SRAM 给下一层用）

Step 5: 搬下一层的权重，重复以上过程
```

64 层 Transformer 就是重复 64 次这个流程。每一层的权重在轮到它的时候才从 HBM 搬进来，算完就可以丢掉（除非下一层还要用）。

### 3.5 为什么瓶颈在搬运不在计算

A800 的算力和带宽：

| 指标 | 值 |
|---|---|
| BF16 算力 | 312 TFLOPS |
| HBM 带宽 | 2 TB/s |

算力 / 带宽 = 312 / 2 = **156 FLOPS/Byte**。意思是 GPU 每从 HBM 搬 1 个字节的数据，理论上能算 156 次浮点运算。

但 decode 阶段的 GEMM `(1, 4096) × (4096, 4096)` 只需要做 `1 × 4096 × 4096 × 2 = 33.5M` 次浮点运算，却要读 `4096 × 4096 × 2 = 32 MiB` 的权重。计算密度 = 33.5M / 32M ≈ **1 FLOPS/Byte**，远低于硬件的 156 FLOPS/Byte 能力。

ALU 大部分时间在等数据，不是在计算。这就是 **memory-bound**。

打个比方：

```
ALU 是一个算得飞快的厨师（每秒能做 1000 道菜）
HBM 是一个很远的仓库（每秒只能送来 10 个食材）

厨师大部分时间在等食材，不是在做菜
```

### 3.6 Prefill 为什么不同

Prefill 的 GEMM 形状是 `(16384, 4096) × (4096, 4096)`：

- 计算量：`16384 × 4096 × 4096 × 2 = 550 GFLOPS`
- 权重读取：`4096 × 4096 × 2 = 32 MiB`（同一块权重被 16384 个 token 复用）
- 计算密度：`550G / 32M ≈ 17,000 FLOPS/Byte`

17,000 远大于硬件的 156 FLOPS/Byte 能力，说明 ALU 打满了，变成 **compute-bound**。这时候瓶颈在算不在搬，所以 BF16（无反量化开销）反而最快。

### 3.7 优化方向对应关系

| 瓶颈 | 优化方向 | 例子 |
|---|---|---|
| HBM 带宽（memory-bound） | 搬更少的数据 | 量化（4-bit 比 16-bit 小 4 倍） |
| HBM 带宽（memory-bound） | 减少 HBM 访问 | FlashAttention（SRAM 内完成） |
| HBM 带宽（memory-bound） | 提高 L2 命中 | 更好的 tiling 策略 |
| 算力（compute-bound） | 减少计算量 | 量化反量化融合、更高效的 kernel |
| 算力（compute-bound） | 用更多 core | Tensor Parallel（多 GPU 分担） |
| launch 开销 | 减少 CPU-GPU 交互 | CUDA Graph（固定 shape 批量 launch） |

## 4. 两个原语在 Transformer 里怎么串起来

一层 Transformer 的计算流程：

```text
输入 token
  → GEMM：QKV projection（算 Q、K、V）
  → FlashAttention：Q×K^T 算注意力分数，再 ×V
  → GEMM：output projection（投影回 hidden_dim）
  → GEMM：FFN up/gate（前馈网络扩展）
  → GEMM：FFN down（前馈网络压缩）
  → 输出
```

64 层重复以上流程。

## 5. 占比为什么这么高

Stage 1 profiler 中 GEMM + FlashAttention 合计占 GPU time 的 85-92%：

| 阶段 | GEMM | FlashAttention | 合计 | 剩余 |
|---|---|---|---|---|
| Prefill | 62-68% | 23-24% | ~90% | sampling、layernorm、数据搬运 |
| Decode | 41-68% | 12-13% | ~80% | sampling、SoftMax、layernorm |

剩余部分被 sampling（softmax + top-p/top-k 采样）、LayerNorm/RMSNorm、RoPE 位置编码、数据搬运等分掉。这些单个占比很小，但在高并发或短序列下可能变得更显著。

## 6. Memory-bound vs Compute-bound 判断

一个简化判断方法：

| 条件 | 倾向 | 原因 |
|---|---|---|
| 矩阵两边都大 | compute-bound | GPU core 能打满 |
| 矩阵一边很小 | memory-bound | GPU core 闲着，等数据 |
| batch 大 | compute-bound | 多个请求合在一起算 |
| batch=1 | memory-bound | 只有 1 个请求 |

Decode 阶段 batch=1（或很小）、输入只有 1 个 token，所以几乎所有操作都是 memory-bound。这是理解量化为什么能加速 decode 的关键。

## 7. 与当前项目的关联

当前项目的 profiler 实测已经验证了上述理论：

- Stage 4（AWQ profiler）：prefill Marlin 61.6% + FlashAttention 23.6%；decode Marlin 41.3% + FlashAttention 12.6%
- Stage 6（NVFP4 profiler）：与 AWQ 方向一致，但 decode 中普通 BF16 GEMM 占比更突出（23.9%）
- Stage 8（Nsight Compute）：Marlin 占 68%+，FlashAttention 占 23%+，两者合计 > 90%

优化方向：
- GEMM 优化：更高效的量化 kernel（Marlin、CUTLASS）、更好的 batch 策略
- Attention 优化：FlashAttention 版本升级、PagedAttention 调度、KV cache 压缩
- 系统优化：continuous batching 把 decode 的 batch 做大，从 memory-bound 转向 compute-bound
