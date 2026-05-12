# 三后端 Docker 部署方案

适用场景：宿主机 NVIDIA 驱动较新、本机 CUDA Toolkit 较老且暂时不能升级，需要避免本机编译踩坑。

**结论**：三套后端（vLLM / llama.cpp / SGLang）都建议优先走 Docker，把 CUDA 用户态库、推理框架依赖、Python 运行时全部封装在容器内。

---

## 1. 为什么"驱动新 + toolkit 旧"仍然可以用 Docker

CUDA 职责是分层的：

- 宿主机提供内核态驱动（`nvidia-smi` 可见）
- 容器镜像提供用户态 CUDA 库与运行时（如 CUDA 12.x）

因此本机 toolkit 老不会阻碍容器内运行较新的 CUDA 用户态栈，只要宿主机驱动版本满足容器内 CUDA 运行时的最低要求即可。

---

## 2. 开始前检查

```bash
nvidia-smi
docker --version
docker info | grep -i runtime
```

期望：`nvidia-smi` 正常显示 GPU 与驱动，Docker 可用，已启用 NVIDIA Container Toolkit（支持 `--gpus all`）。

快速验证 GPU 透传：

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

若此命令成功，则容器内高版本 CUDA 用户态与宿主机驱动可协同工作。

---

## 3. 官方镜像与固定版本

> 以下版本号是记录时的基线，不是已在线核验的固定版本。实际使用前请执行 `docker pull` 验证，验证通过后建议锁定 digest。

| 后端 | 镜像 | 版本示例 |
|------|------|----------|
| vLLM | `vllm/vllm-openai` | `v0.8.5` |
| llama.cpp | `ghcr.io/ggml-org/llama.cpp` | `b5471-cuda` |
| SGLang | `lmsysorg/sglang` | `v0.4.6.post1-cu124` |

锁定 digest 的方式：

```bash
docker image inspect vllm/vllm-openai:v0.8.5 --format '{{index .RepoDigests 0}}'
```

后续可改为 `docker pull <repo>@sha256:<digest>` 避免 tag 漂移。

---

## 4. 各后端运行示例

模型目录约定：宿主机 `/proj02/liuheshan/llmnode/models` 挂载为容器内 `/models`。

### 4.1 vLLM

特点：高吞吐、连续批处理、KV Cache 高效管理、OpenAI 兼容 API 成熟，适合在线 API 服务。

```bash
docker run --rm --gpus all \
  --ipc=host \
  -p 8000:8000 \
  -v /proj02/liuheshan/llmnode/models:/models \
  vllm/vllm-openai:v0.8.5 \
  --model /models/Qwen/Qwen3.6-35B-A3B \
  --host 0.0.0.0 \
  --port 8000
```

不建议在宿主机 `pip install vllm` 作为主路径；推荐以官方镜像为主，业务只对接 HTTP API。

### 4.2 llama.cpp

特点：支持 CPU offload、GGUF 路线成熟，低显存单机更友好，适合本地开发和混合部署。

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

在"驱动新、toolkit 老"的环境下，不要在宿主机本地编译 CUDA 版本，使用官方镜像即可。

#### llama.cpp 镜像标签说明

| 标签 | 内容 | 适用场景 |
|------|------|----------|
| `:full` | 所有二进制工具（llama-cli、llama-server、llama-quantize 等） | 开发/调试 |
| `:server` | 仅 llama-server + 最小依赖 | 生产，只需 HTTP 服务 |
| `:full-cuda` / `:b<build>-cuda` | full + CUDA 支持 | GPU 加速推理 |

验证镜像内是否包含 `llama-server`：

```bash
docker run --rm ghcr.io/ggml-org/llama.cpp:full which llama-server
```

### 4.3 SGLang

特点：推理 + 编排结合，对 Agent、复杂多轮流程、结构化输出与工具调用友好。

```bash
docker run --rm --gpus all \
  --ipc=host \
  -p 30000:30000 \
  -v /proj02/liuheshan/llmnode/models:/models \
  lmsysorg/sglang:v0.4.6.post1-cu124 \
  python -m sglang.launch_server \
  --model-path /models/Qwen/Qwen3.6-35B-A3B \
  --host 0.0.0.0 \
  --port 30000
```

---

## 5. 后端选型简表

| 后端 | 适合场景 | 当前项目定位 |
|------|----------|-------------|
| vLLM | 高并发在线 API 服务 | 正式默认主后端 |
| llama.cpp | 低显存、混合部署、本地开发 | 第二后端 |
| SGLang | Agent/编排、结构化输出 | 第三候选 |
