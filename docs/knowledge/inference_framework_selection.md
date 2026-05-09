# 推理框架选型（Docker 部署版：vLLM / llama.cpp / SGLang）

本文面向当前项目的实际约束：

- 宿主机 NVIDIA 驱动较新
- 本机 CUDA Toolkit 较老，且因为项目依赖暂时不能升级
- 希望避免本地编译 `llama.cpp` 时踩 CUDA/编译链版本坑

结论先行：三套后端都建议优先走 Docker，尽量把 CUDA 用户态库、推理框架依赖、Python 运行时都封装在容器内。

---

## 1. 适用前提与核心判断

### 1.1 为什么“驱动新 + toolkit 旧”仍然可以用 Docker

关键点是 CUDA 的职责分层：

- 宿主机主要提供内核态驱动（`nvidia-smi` 可见）
- 容器镜像提供用户态 CUDA 库与运行时（如 CUDA 12.x）

因此：

- 你本机 Toolkit 老，不一定阻碍容器内运行较新的 CUDA 用户态栈
- 只要宿主机驱动版本满足容器内 CUDA 运行时最低要求，容器就可以工作

### 1.2 你当前场景的部署策略

- 不在宿主机本地编译 `llama.cpp` CUDA 版本
- 使用官方镜像直接运行 `llama-server`
- 三个后端统一用容器化部署，减少环境漂移

### 1.3 开始前检查项

```bash
nvidia-smi
docker --version
docker info | grep -i runtime
```

期望：

- `nvidia-smi` 正常显示 GPU 与驱动
- Docker 可用
- 已安装并启用 NVIDIA Container Toolkit（至少能使用 `--gpus all`）

---

## 2. 官方镜像与固定版本清单

说明：当前会话网络受限，无法在线拉取 tag 列表验证。以下为建议锁定版本（基线版本），请在你的机器执行 `docker pull` 验证；验证通过后建议进一步锁定 digest。

### 2.1 vLLM

- 官方镜像：`vllm/vllm-openai`
- 锁定版本：`v0.8.5`
- 拉取命令：

```bash
docker pull vllm/vllm-openai:v0.8.5
```

### 2.2 llama.cpp

- 官方镜像：`ghcr.io/ggml-org/llama.cpp`
- 锁定版本：`b5471-cuda`
- 拉取命令：

```bash
docker pull ghcr.io/ggml-org/llama.cpp:b5471-cuda
```

### 2.3 SGLang

- 官方镜像：`lmsysorg/sglang`
- 锁定版本：`v0.4.6.post1-cu124`
- 拉取命令：

```bash
docker pull lmsysorg/sglang:v0.4.6.post1-cu124
```

---

## 3. 三框架详细说明（Docker 视角）

## 3.1 vLLM

### 3.1.1 介绍

`vLLM` 是高吞吐在线推理框架，优势在于连续批处理与高效 KV Cache 管理，适合作为 OpenAI 兼容 API 服务后端。

### 3.1.2 特点

- 高并发吞吐表现强
- OpenAI 兼容 API 成熟
- Hugging Face 模型生态兼容度高
- 生产可用性较好

### 3.1.3 使用范围

适合：

- 在线 API 服务
- 并发较高、响应时延可控的场景
- 需要快速接入 HF 模型目录

### 3.1.4 Docker 运行示例

```bash
docker run --rm --gpus all \
  --ipc=host \
  -p 8000:8000 \
  -v /proj02/liuheshan/llmnode/models:/models \
  -e HUGGING_FACE_HUB_TOKEN=${HUGGING_FACE_HUB_TOKEN} \
  vllm/vllm-openai:v0.8.5 \
  --model /models/Qwen/Qwen3.6-35B-A3B \
  --host 0.0.0.0 \
  --port 8000
```

### 3.1.5 编译与安装方式（Docker 优先）

- 你的场景不建议本机 `pip install vllm` 作为主路径
- 推荐以官方镜像为主，业务只对接 HTTP API
- 若后续必须源码调试，再额外开开发容器进行可控编译

---

## 3.2 llama.cpp

### 3.2.1 介绍

`llama.cpp` 更偏本地与混合部署，支持 CPU offload，在“显存不足但内存较大”的机器上实用价值很高。

### 3.2.2 特点

- `GGUF` 路线成熟
- CPU/GPU 混合部署能力强
- 对低显存单机更友好
- `llama-server` 可直接提供 OpenAI 兼容接口（常见部署方式）

### 3.2.3 使用范围

适合：

- 本地开发、低显存部署
- 单机混合推理
- 需要较强 offload 能力的场景

### 3.2.4 Docker 运行示例（避免本机 toolkit 约束）

```bash
docker run --rm --gpus all \
  -p 8080:8080 \
  -v /proj02/liuheshan/llmnode/models:/models \
  ghcr.io/ggml-org/llama.cpp:b5471-cuda \
  /app/llama-server \
  -m /models/gemma/gemma-4-31b-it-Q4_K_M.gguf \
  --host 0.0.0.0 \
  --port 8080 \
  -ngl 999
```

### 3.2.5 编译与安装方式

在你当前环境，建议明确两条策略：

- 主策略：只用官方 Docker 镜像，不在宿主机本地编译 CUDA 版本
- 备用策略：必须本地编译时，放到单独开发容器内完成，避免污染宿主机工具链

这正是你“驱动够新、toolkit 老且不能升”场景下的稳妥做法。

---

## 3.3 SGLang

### 3.3.1 介绍

`SGLang` 强调“推理 + 编排”结合，适合 Agent、复杂多轮流程、结构化输出与工具调用场景。

### 3.3.2 特点

- 推理服务能力强
- 编排与程序化控制能力突出
- 对 Agent/Workflow 场景友好
- 可作为 vLLM 之外的高性能替代方案

### 3.3.3 使用范围

适合：

- 复杂调用链和 Agent 应用
- 结构化输出要求较高的服务
- 需要更细粒度推理流程控制的场景

### 3.3.4 Docker 运行示例

```bash
docker run --rm --gpus all \
  --ipc=host \
  -p 30000:30000 \
  -v /proj02/liuheshan/llmnode/models:/models \
  -e HUGGING_FACE_HUB_TOKEN=${HUGGING_FACE_HUB_TOKEN} \
  lmsysorg/sglang:v0.4.6.post1-cu124 \
  python -m sglang.launch_server \
  --model-path /models/Qwen/Qwen3.6-35B-A3B \
  --host 0.0.0.0 \
  --port 30000
```

### 3.3.5 编译与安装方式（Docker 优先）

- 生产优先使用官方镜像
- 本机 Python 依赖与 CUDA 依赖尽量不与业务环境耦合
- 若需源码调试，建议同样走开发容器

---

## 4. 镜像锁定与可复现建议

### 4.1 从 tag 升级到 digest 锁定

建议在可联网环境完成首次拉取后，记录 digest：

```bash
docker image inspect vllm/vllm-openai:v0.8.5 --format '{{index .RepoDigests 0}}'
docker image inspect ghcr.io/ggml-org/llama.cpp:b5471-cuda --format '{{index .RepoDigests 0}}'
docker image inspect lmsysorg/sglang:v0.4.6.post1-cu124 --format '{{index .RepoDigests 0}}'
```

后续生产可改为：

```bash
docker pull <repo>@sha256:<digest>
```

这样可避免 tag 漂移。

### 4.2 模型目录约定

建议统一挂载：

- 宿主机：`/proj02/liuheshan/llmnode/models`
- 容器内：`/models`

并在配置里只管理模型相对路径，减少后端切换成本。

---

## 5. 兼容性与排障（针对你的环境）

### 5.1 常见风险

- 本机 toolkit 老导致本地编译失败（`nvcc` / `cmake` / CUDA headers）
- 容器启动时找不到 GPU（NVIDIA Container Toolkit 未配置）
- 驱动版本过低导致容器内 CUDA runtime 不兼容

### 5.2 快速排障命令

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

若这条命令成功，说明：

- Docker GPU 透传基本正常
- 容器内高版本 CUDA 用户态与宿主机驱动可协同

之后再分别启动 vLLM / llama.cpp / SGLang 容器排查框架级参数问题。

---

## 6. 最终选型建议（结合当前项目）

- 默认主后端：`vLLM`（稳定高吞吐）
- 第二后端：`llama.cpp`（低显存与混合部署能力）
- 第三候选：`SGLang`（Agent/编排能力强化）

在你当前“本机 toolkit 旧、不能升级”的条件下，`llama.cpp` 明确建议走 Docker 主路径，不走宿主机本地 CUDA 编译。
