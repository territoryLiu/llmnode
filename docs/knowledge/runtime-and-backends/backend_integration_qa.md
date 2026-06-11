# 三后端联调验证 Q&A

记录三后端（vLLM / llama.cpp / SGLang）首次线上联调验证（2026-05-12）中发现的问题及解决方案。

---

## 问题清单

| # | 后端 | 现象 | 状态 |
|---|------|------|------|
| Q1 | llama.cpp | GPU 未被使用，`--n-gpu-layers` 被忽略 | ✅ 已验证修复 |
| Q2 | SGLang | 镜像缺少 `distro` 模块，启动报 `ModuleNotFoundError` | ✅ 已临时修复 |
| Q3 | SGLang | `<think>` 块混入 `content` 字段，未剥离到 `reasoning_content` | ✅ 已正式修复 |
| Q4 | vLLM | 首次启动时 GPU 显存被残留进程占用导致启动失败 | ✅ 有操作规范 |
| Q5 | 通用 | 改了容器启动参数后，旧容器被复用导致新参数未生效 | ✅ 有操作规范 |

---

## Q1：llama.cpp 无 GPU 加速（`:full` 镜像为纯 CPU 版）✅ 已验证修复

**现象**

启动日志出现：
```
warning: no usable GPU found, --gpu-layers option will be ignored
warning: one possible reason is that llama.cpp was compiled without GPU support
```
`--n-gpu-layers -1` 配置被静默忽略，模型完全跑在 CPU 上，推理速度极慢。

**根因**

`ghcr.io/ggml-org/llama.cpp:full` 是纯 CPU 编译版本，不含 CUDA 支持。

**解决方案**

改用带 CUDA 的镜像（离线 tar 包加载）：

```bash
docker load -i llama.cpp-full-cuda.tar
```

| 镜像 tag | 说明 |
|----------|------|
| `ghcr.io/ggml-org/llama.cpp:full-cuda` | 带所有工具 + CUDA，当前使用 |
| `ghcr.io/ggml-org/llama.cpp:server-cuda` | 仅 llama-server + CUDA，体积小 |
| `ghcr.io/ggml-org/llama.cpp:b<build>-cuda` | 固定构建号，生产推荐锁定 |

`config/defaults.yaml` llama.cpp 段对应字段：
```yaml
image_name: ghcr.io/ggml-org/llama.cpp:full-cuda
```

**验证结果（2026-05-12）**

- GPU 显存占用：约 26GB（`/app/llama-server` 进程）
- 推理速度：~68 token/s
- `reasoning_content` 字段有内容，`content` 字段干净

**关于 n_ctx_seq < n_ctx_train 的说明**

llama.cpp 的 `n_ctx_seq`（每个并发 slot 的序列长度）= `ctx_size / n_parallel`。  
当前配置 `ctx_size=262144, n_parallel=4`，每个 slot 实际可用 65536 token，属于正常行为，不是 bug。  
若需要单 session 支持 256K，可将 `n_parallel` 改为 1。

---

## Q2：SGLang 镜像缺少 `distro` 模块

**现象**

启动时报错：
```
ModuleNotFoundError: No module named 'distro'
```
调用链：`sglang.launch_server` → `server_args.py` → `function_call_parser.py` → `protocol.py` → `openai/__init__.py` → `_base_client.py` → `import distro`

**根因**

`lmsysorg/sglang:v0.5.11-cu129-runtime` 镜像中的 `openai` 包版本依赖 `distro`，但镜像未预装该包。

**临时修复（已合入代码）**

`llmnode/agent/docker_control.py` 的 `SGLangContainerSpec` 改为通过 shell 前置安装：

```python
@property
def entrypoint(self) -> list[str] | None:
    return ["/bin/sh", "-c"]

@property
def command(self) -> list[str]:
    inner = " ".join([
        "pip install -q distro &&",
        "python", "-m", "sglang.launch_server",
        ...
    ])
    return [inner]
```

**根本解决方案**

等待上游镜像修复，或在本地自建镜像：
```dockerfile
FROM lmsysorg/sglang:v0.5.11-cu129-runtime
RUN pip install -q distro
```

升级镜像版本后验证是否已修复，确认后移除临时补丁并恢复标准 entrypoint。

---

## Q3：SGLang 的 thinking 内容混入 `content` 字段（已正式修复）

**现象**

通过 gateway 请求 SGLang 时，`choices[0].message.content` 包含完整的 thinking 文字（无 `<think>` 标签），`reasoning_content` 字段为空。

**根因**

SGLang v0.5.11 处理 Qwen3 chat template 时，会把 `<think>...</think>` 标签剥掉，将 thinking 文字和最终回答一起放入 `content`，`reasoning_content` 字段始终为 `null`。

这一行为是因为启动时没有指定 `--reasoning-parser`。SGLang v0.5.11 **已支持** `--reasoning-parser qwen3`（与 vLLM 同名参数），启用后 thinking 会被正确剥离到 `reasoning_content`，`content` 保持干净。

**正式修复方案（已合入）**

`SGLangContainerSpec` 启动命令加入 `--reasoning-parser <reasoning_parser>` 参数，由配置字段 `reasoning_parser` 控制。

修改位置：`llmnode/agent/docker_control.py`

```python
@dataclass(frozen=True)
class SGLangContainerSpec:
    ...
    reasoning_parser: str   # 新增字段，Qwen3 填 "qwen3"

    @property
    def command(self) -> list[str]:
        parts = [
            "pip install -q distro &&",
            "python", "-m", "sglang.launch_server",
            ...
        ]
        if self.reasoning_parser:
            parts += ["--reasoning-parser", self.reasoning_parser]
        return [" ".join(parts)]
```

`config/defaults.yaml` SGLang 示例配置对应字段：
```yaml
reasoning_parser: qwen3
```

**教训：先查官方文档，不要从现象直接下结论**

初次联调时看到 `reasoning_content` 为 null，直接推断"SGLang 不支持 reasoning parser"，走了一条弯路：在 gateway 层注入 `chat_template_kwargs: {"enable_thinking": false}` 来禁掉 thinking，以此绕开污染问题。

这个结论是错的。SGLang v0.5.11 一直都有 `--reasoning-parser` 参数，只是启动命令里漏掉了这个参数。现象是"没有正确分离"，不等于"不支持"。查官方文档后才发现，一行参数解决问题。

**正确排查顺序**：先看官方文档确认功能是否存在 → 检查启动命令是否传了对应参数 → 再考虑代码层面的绕行方案。

**修复后预期效果**

```
reasoning_content: <thinking 内容>
content: 你好！...（干净的最终回答）
```

**SGLang reasoning parser 支持的模型**（来自官方文档）：

| 模型 | Parser |
|------|--------|
| DeepSeek-R1 系列 | `deepseek-r1` |
| DeepSeek-V3 系列 | `deepseek-v3` |
| Qwen3 标准模型 | `qwen3` |
| Qwen3-Thinking 模型 | `qwen3` 或 `qwen3-thinking` |

---

## Q4：vLLM 启动时显存不足（残留进程占用）

**现象**

vLLM 容器启动失败，日志报：
```
ValueError: Free memory on device cuda:0 (28.21/79.25 GiB) on startup is less than
desired GPU memory utilization (0.9, 71.32 GiB).
```
实际 GPU 总显存 80GB，`gpu_memory_utilization=0.9` 要求 71GB，但启动时只有 28GB 可用。

**根因**

上一次 vLLM 容器非正常退出后，GPU 显存未及时释放，新容器启动时遭遇残留占用。

**操作规范**

1. 启动前先确认显存状态：
   ```bash
   nvidia-smi
   nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
   ```
2. 若有残留进程，等待其释放或手动清理后再启动。
3. 使用 `python -m llmnode.control stop` 正常停机，避免残留。
4. 若因首次启动失败导致容器重启后显存已清空，agent 的自动重启机制会自动拉起，无需手动干预。

---

## Q5：改了容器启动参数后新参数未生效（旧容器被复用）

**现象**

修改了 `SGLangContainerSpec.command`（加入 `--reasoning-parser qwen3`），重新启动后 `docker inspect` 显示容器里的命令仍是旧的，新参数没有生效。

**根因**

`ensure_container_running` 的逻辑是：容器已存在就直接 `start`，不会销毁重建。因此改了代码后只要旧容器还在（哪怕是 Exited 状态），新的启动参数就不会生效。

```python
# docker_control.py 中的行为
try:
    container = client.containers.get(spec.container_name)
    container.start()   # 直接用旧容器，不重建
    ...
except NotFound:
    client.containers.run(...)   # 只有容器不存在时才用新参数创建
```

**操作规范**

改了任何容器启动参数（镜像、命令、环境变量、挂载等）后，必须手动删除旧容器再启动：

```bash
docker rm <container_name>
python -m llmnode.control start --service vllm
```

或者直接：

```bash
docker rm qwen36-sglang   # 以 SGLang 为例
python -m llmnode.control start --service vllm
```

**验证方法**

启动后用 `docker inspect` 确认实际启动命令：

```bash
docker inspect <container_name> --format '{{json .Args}}' | python3 -c "import sys,json; print(' '.join(json.load(sys.stdin)))"
```

**长期改进方向**

`ensure_container_running` 可以加入命令哈希比对，发现命令不一致时自动重建容器。目前作为运维规范处理，不自动重建。

---

## 附：三后端联调验证结果汇总（2026-05-12）

| 后端 | 模型 | 启动 | 推理 | finish_reason | thinking 处理 |
|------|------|------|------|---------------|--------------|
| vLLM | Qwen3.6-35B-A3B (safetensors) | ✓ | ✓ | stop | reasoning 字段有内容，content 干净 |
| llama.cpp | Qwen3.6-35B-A3B-GGUF (q4km) | ✓（full-cuda 镜像） | ✓ | length/stop | reasoning_content 有内容，content 干净；~68 token/s |
| SGLang | Qwen3.6-35B-A3B (safetensors) | ✓（需 distro 补丁） | ✓ | stop | `--reasoning-parser qwen3` 已启用，reasoning_content 正常分离 |

上下文长度配置（已更新到 `config/defaults.yaml`）：

| 后端 | 参数 | 值 |
|------|------|-----|
| vLLM | `max_model_len` | 262144（256K） |
| llama.cpp | `ctx_size` | 262144（256K） |
| SGLang | `context_length`（未显式设置，由模型 config 决定） | — |
