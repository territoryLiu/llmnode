# 控制面诊断能力增强

## 1. 设计目标

当前 `doctor / status / logs` 已经具备基础诊断能力，但在三后端线上联调验证完成后，诊断能力成为新的瓶颈：

- `doctor` 能检查环境，但不能针对三后端的特定依赖给出精准建议
- `status` 能展示进程状态，但看不到容器详细信息、推理参数、GPU 使用情况
- `logs` 能查看日志，但不支持实时跟踪、错误高亮、按后端类型过滤

本设计的目标是：

1. **提升定位效率**：从"能看到状态"到"能快速定位问题根因"
2. **三后端感知**：诊断逻辑能识别当前后端类型，给出针对性建议
3. **保持轻量**：不引入重型监控系统，保持命令行工具的简洁性

## 2. 设计原则

- **渐进增强**：在现有命令基础上扩展，不破坏现有行为
- **后端感知**：根据 `backend_type` 动态调整检查项和建议
- **可操作性**：诊断结果必须包含可执行的修复建议
- **性能优先**：诊断命令本身不能成为性能瓶颈（< 3s 完成）

## 3. `doctor` 命令增强

### 3.1 当前能力

```bash
python -m llmnode.control doctor
```

当前检查项：
- 环境工具（python/docker/npm/ss）
- 目录存在性（model_dir/web_console_dir/node_modules）
- 端口占用（gateway/agent/backend/web-console）
- HTTP 健康检查（gateway/agent/backend/web-console）
- Docker 状态（容器存在性、镜像存在性）
- 基础建议（安装依赖、拉取镜像、启动服务）

### 3.2 增强方向

#### 3.2.1 三后端特定检查

根据 `backend_type` 动态增加检查项：

**vLLM 特定检查：**
- GPU 可用性（`nvidia-smi` 可用性、CUDA 版本）
- 显存容量（是否满足 `gpu_memory_utilization * 模型大小`）
- 镜像版本（是否支持 `reasoning_parser` / `tool_call_parser`）
- 模型格式（是否为 HuggingFace 格式）

**llama.cpp 特定检查：**
- 镜像类型（是否为 `full-cuda` 镜像）
- 模型文件存在性（`model_file` 是否存在于 `model_dir`）
- 模型格式（是否为 GGUF 格式）
- `n_gpu_layers` 合理性（是否超过模型层数）

**SGLang 特定检查：**
- `reasoning_parser` 参数（是否设置为 `qwen3`）
- `tp_size` 与 GPU 数量匹配
- 镜像版本（是否包含 `distro` 模块补丁）

#### 3.2.2 容器详细诊断

当容器存在但不健康时，增加：
- 容器状态（`docker inspect` 获取 `State.Status` / `State.ExitCode`）
- 容器重启次数（`RestartCount`）
- 容器资源限制（`HostConfig.Memory` / `HostConfig.ShmSize`）
- 容器最近日志（最后 20 行，高亮错误关键词）

#### 3.2.3 GPU 状态检查

新增 `gpu` 检查段：
- GPU 数量（`nvidia-smi --list-gpus`）
- GPU 型号、显存容量
- GPU 使用率、显存使用率
- CUDA 版本、驱动版本
- 是否有其他进程占用 GPU

#### 3.2.4 模型文件检查

新增 `model` 检查段：
- 模型目录大小（`du -sh`）
- 模型文件列表（关键文件：`config.json` / `*.safetensors` / `*.gguf`）
- 模型格式识别（HuggingFace / GGUF / 其他）
- 模型配置解析（从 `config.json` 读取 `model_type` / `hidden_size` / `num_hidden_layers`）

#### 3.2.5 智能建议增强

当前建议比较通用，增强为：

**场景 1：后端容器启动失败**
- 检查容器日志最后 20 行
- 识别常见错误模式：
  - `CUDA out of memory` → 建议降低 `gpu_memory_utilization` 或 `max_model_len`
  - `Model not found` → 建议检查 `model_dir` 和 `model_name`
  - `Permission denied` → 建议检查 Docker 权限和目录权限
  - `Port already in use` → 建议检查端口占用并提供 `lsof` 命令

**场景 2：后端健康检查失败**
- 区分"容器未启动"和"容器启动但不健康"
- 如果容器启动但不健康，建议查看实时日志：
  ```bash
  python -m llmnode.control logs --target vllm --follow
  ```

**场景 3：GPU 不可用**
- 检查 `nvidia-smi` 是否可用
- 检查 Docker 是否配置 `nvidia-runtime`
- 提供配置 Docker GPU 支持的命令

**场景 4：模型格式不匹配**
- vLLM 需要 HuggingFace 格式，但检测到 GGUF → 建议转换或切换到 llama.cpp
- llama.cpp 需要 GGUF 格式，但检测到 HuggingFace → 建议转换或切换到 vLLM

### 3.3 输出格式优化

增加颜色和符号：
- ✓ 绿色：检查通过
- ✗ 红色：检查失败
- ⚠ 黄色：警告（非致命）
- ℹ 蓝色：信息

示例输出：
```
llmnode doctor
  project: /proj02/liuheshan/llmnode
  python: /home/heshan/.conda/envs/paper2any/bin/python
  backend_type: vllm
  model_dir: models/Qwen/Qwen3.6-35B-A3B

environment
  ✓ python_bin: ok (/home/heshan/.conda/envs/paper2any/bin/python)
  ℹ python_version: Python 3.11.9
  ✓ docker: ok (Docker version 24.0.7)
  ✓ nvidia-smi: ok (CUDA Version: 12.2)
  ✓ model_dir: ok (models/Qwen/Qwen3.6-35B-A3B)

gpu
  ✓ gpu_count: 2 GPUs detected
  ℹ gpu_0: NVIDIA A100-SXM4-80GB (80GB, 15% used, 12GB occupied)
  ℹ gpu_1: NVIDIA A100-SXM4-80GB (80GB, 0% used, 0GB occupied)
  ✓ cuda_version: 12.2
  ✓ driver_version: 535.129.03

model
  ✓ model_format: HuggingFace (detected config.json)
  ℹ model_type: qwen2
  ℹ model_size: 35B parameters
  ℹ model_layers: 64 layers
  ✓ model_files: 15 safetensors files found

backend (vllm)
  ✓ backend_image: ok (vllm/vllm-openai:v0.6.4.post1)
  ✓ backend_container: running (llmnode-vllm)
  ✓ backend_health: ok (http://127.0.0.1:8000/v1/models)
  ℹ container_uptime: 2h 15m
  ℹ container_restarts: 0

suggestions
  No issues detected. Stack is healthy.
```

## 4. `status` 命令增强

### 4.1 当前能力

```bash
python -m llmnode.control status
```

当前输出：
- 项目基本信息（project/backend/python/model_dir/web_console）
- 进程状态（gateway/agent/web_console 的 PID 和端口）
- HTTP 健康检查（gateway/agent/backend/web-console）
- 栈状态摘要（stopped/warming/partial/ready）

### 4.2 增强方向

#### 4.2.1 容器详细信息

新增 `container` 段：
- 容器名称、镜像、状态
- 容器启动时间、运行时长
- 容器重启次数
- 容器资源使用（CPU/内存/GPU）

#### 4.2.2 推理参数展示

根据 `backend_type` 展示关键推理参数：

**vLLM：**
```
backend (vllm)
  container: llmnode-vllm (running, uptime: 2h 15m)
  image: vllm/vllm-openai:v0.6.4.post1
  model: Qwen/Qwen3.6-35B-A3B
  gpu_memory_utilization: 0.95
  tensor_parallel_size: 2
  max_model_len: 32768
  max_num_seqs: 256
  reasoning_parser: qwen3
  tool_call_parser: hermes
```

**llama.cpp：**
```
backend (llama.cpp)
  container: llmnode-llamacpp (running, uptime: 1h 30m)
  image: ghcr.io/ggerganov/llama.cpp:full-cuda
  model: Qwen/Qwen3.6-35B-A3B
  model_file: qwen3.6-35b-a3b-q4_k_m.gguf
  n_gpu_layers: 64
  ctx_size: 32768
  n_parallel: 8
```

**SGLang：**
```
backend (sglang)
  container: llmnode-sglang (running, uptime: 45m)
  image: lmsysorg/sglang:latest
  model: Qwen/Qwen3.6-35B-A3B
  tp_size: 2
  mem_fraction_static: 0.9
  max_running_requests: 256
  reasoning_parser: qwen3
```

#### 4.2.3 性能指标

新增 `metrics` 段（如果后端支持）：
- 请求总数、成功率
- 平均延迟、P95/P99 延迟
- 吞吐量（tokens/s）
- 队列长度

#### 4.2.4 栈状态细化

当前栈状态只有 4 种（stopped/warming/partial/ready），细化为：

- `stopped`：所有服务都不可达
- `starting`：agent 可达，但 backend 容器不存在
- `warming`：agent 可达，backend 容器运行中，但 HTTP 不可达（模型加载中）
- `partial`：部分服务可达，但不是全部
- `ready`：所有服务可达
- `degraded`：所有服务可达，但有警告（如容器重启次数 > 0）

### 4.3 输出格式优化

增加表格展示：

```
llmnode status
  project: /proj02/liuheshan/llmnode
  backend: vllm
  python: /home/heshan/.conda/envs/paper2any/bin/python
  model_dir: models/Qwen/Qwen3.6-35B-A3B
  web_console: http://127.0.0.1:5173

processes
  ┌──────────────┬──────┬──────┬────────────────────────────────────────────┐
  │ Service      │ PID  │ Port │ Health                                     │
  ├──────────────┼──────┼──────┼────────────────────────────────────────────┤
  │ gateway      │ 1234 │ 4000 │ ✓ ok                                       │
  │ agent        │ 1235 │ 4010 │ ✓ ok                                       │
  │ web_console  │ 1236 │ 5173 │ ✓ ok                                       │
  └──────────────┴──────┴──────┴────────────────────────────────────────────┘

backend (vllm)
  container: llmnode-vllm (running, uptime: 2h 15m, restarts: 0)
  image: vllm/vllm-openai:v0.6.4.post1
  model: Qwen/Qwen3.6-35B-A3B
  health: ✓ ok (http://127.0.0.1:8000/v1/models)
  gpu_memory_utilization: 0.95
  tensor_parallel_size: 2
  max_model_len: 32768
  max_num_seqs: 256

summary
  stack_state: ready
  detail: Gateway, agent, vllm, and web-console are all reachable.
```

## 5. `logs` 命令增强

### 5.1 当前能力

```bash
python -m llmnode.control logs --target all --lines 50
```

当前功能：
- 支持 `--target` 选择日志源（all/agent/gateway/web-console/vllm）
- 支持 `--lines` 限制行数
- 按日志源分段展示

### 5.2 增强方向

#### 5.2.1 实时跟踪

新增 `--follow` / `-f` 参数：
```bash
python -m llmnode.control logs --target vllm --follow
```

实现：
- 使用 `docker logs -f` 实时跟踪容器日志
- 使用 `tail -f` 实时跟踪 Python 服务日志
- 支持 `Ctrl+C` 优雅退出

#### 5.2.2 错误高亮

自动识别并高亮错误关键词：
- 红色：`ERROR` / `FATAL` / `CRITICAL` / `Exception` / `Traceback`
- 黄色：`WARN` / `WARNING`
- 绿色：`INFO` / `DEBUG`

#### 5.2.3 时间范围过滤

新增 `--since` 参数：
```bash
python -m llmnode.control logs --target vllm --since 5m
python -m llmnode.control logs --target vllm --since "2026-05-12 14:00:00"
```

#### 5.2.4 关键词搜索

新增 `--grep` 参数：
```bash
python -m llmnode.control logs --target vllm --grep "CUDA"
python -m llmnode.control logs --target all --grep "error" --ignore-case
```

#### 5.2.5 后端类型感知

当 `--target vllm` 时，根据实际 `backend_type` 自动映射：
- `backend_type: vllm` → 读取 vLLM 容器日志
- `backend_type: llama.cpp` → 读取 llama.cpp 容器日志
- `backend_type: sglang` → 读取 SGLang 容器日志

或者新增 `--target backend` 作为通用别名。

#### 5.2.6 日志导出

新增 `--output` 参数：
```bash
python -m llmnode.control logs --target all --output /tmp/llmnode-logs.txt
```

### 5.3 输出格式优化

增加时间戳和日志级别：

```
llmnode logs
  target: vllm
  lines: 50

log:vllm
  path: /proj02/liuheshan/llmnode/runtime/logs/llmnode-vllm.latest.log
  [2026-05-12 14:23:15] INFO: vLLM version 0.6.4.post1
  [2026-05-12 14:23:16] INFO: Initializing an LLM engine (v0.6.4.post1) with config: ...
  [2026-05-12 14:23:45] INFO: Loading model weights from /model/Qwen/Qwen3.6-35B-A3B
  [2026-05-12 14:25:12] INFO: Model loaded successfully
  [2026-05-12 14:25:13] INFO: Starting HTTP server on 0.0.0.0:8000
  [2026-05-12 14:25:14] INFO: Application startup complete
```

## 6. 实施计划

### 6.1 阶段 1：`doctor` 增强（P0）

**目标：** 提升环境诊断能力，减少"启动失败不知道为什么"的情况

**任务：**
1. 实现三后端特定检查（GPU/模型格式/镜像版本）
2. 实现容器详细诊断（状态/重启次数/资源限制/最近日志）
3. 实现智能建议（识别常见错误模式，给出可执行命令）
4. 优化输出格式（颜色/符号/分段）

**验收标准：**
- 能识别 vLLM/llama.cpp/SGLang 的特定问题
- 能给出至少 5 种常见错误的精准建议
- 诊断时间 < 3s

### 6.2 阶段 2：`status` 增强（P0）

**目标：** 让用户一眼看到系统运行状态和关键参数

**任务：**
1. 实现容器详细信息展示（名称/镜像/状态/运行时长/重启次数）
2. 实现推理参数展示（根据 backend_type 动态展示）
3. 细化栈状态（6 种状态）
4. 优化输出格式（表格/分段）

**验收标准：**
- 能展示三后端的关键推理参数
- 栈状态能准确反映系统健康度
- 输出清晰易读

### 6.3 阶段 3：`logs` 增强（P1）

**目标：** 提升日志查看效率，支持实时跟踪和错误定位

**任务：**
1. 实现 `--follow` 实时跟踪
2. 实现错误高亮
3. 实现 `--since` 时间范围过滤
4. 实现 `--grep` 关键词搜索
5. 实现后端类型感知（`--target backend`）

**验收标准：**
- `--follow` 能实时跟踪日志
- 错误关键词能自动高亮
- `--grep` 能快速定位问题

## 7. 技术实现要点

### 7.1 GPU 信息采集

使用 `nvidia-smi` 命令：
```python
def _collect_gpu_info() -> list[dict]:
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    gpus = []
    for line in result.stdout.strip().splitlines():
        index, name, mem_total, mem_used, util = line.split(", ")
        gpus.append({
            "index": int(index),
            "name": name,
            "memory_total_mb": int(mem_total),
            "memory_used_mb": int(mem_used),
            "utilization_percent": int(util),
        })
    return gpus
```

### 7.2 容器详细信息采集

使用 `docker inspect`：
```python
def _inspect_container(container_name: str) -> dict:
    result = subprocess.run(
        ["docker", "inspect", container_name],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {}
    import json
    data = json.loads(result.stdout)[0]
    return {
        "status": data["State"]["Status"],
        "running": data["State"]["Running"],
        "exit_code": data["State"]["ExitCode"],
        "started_at": data["State"]["StartedAt"],
        "restart_count": data["RestartCount"],
        "image": data["Config"]["Image"],
        "memory_limit": data["HostConfig"]["Memory"],
        "shm_size": data["HostConfig"]["ShmSize"],
    }
```

### 7.3 模型格式识别

```python
def _detect_model_format(model_dir: Path) -> str:
    if (model_dir / "config.json").exists():
        return "huggingface"
    if any(model_dir.glob("*.gguf")):
        return "gguf"
    return "unknown"
```

### 7.4 日志实时跟踪

```python
def _follow_logs(log_path: Path) -> None:
    if log_path.is_symlink():
        log_path = log_path.resolve()
    
    # 使用 subprocess 调用 tail -f
    process = subprocess.Popen(
        ["tail", "-f", str(log_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    
    try:
        for line in process.stdout:
            # 高亮错误关键词
            highlighted = _highlight_log_line(line)
            print(highlighted, end="")
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
```

### 7.5 错误模式识别

```python
ERROR_PATTERNS = {
    "cuda_oom": {
        "pattern": r"CUDA out of memory|OutOfMemoryError",
        "suggestion": "降低 gpu_memory_utilization 或 max_model_len",
    },
    "model_not_found": {
        "pattern": r"Model .* not found|No such file or directory.*model",
        "suggestion": "检查 model_dir 和 model_name 配置",
    },
    "port_in_use": {
        "pattern": r"Address already in use|port .* is already allocated",
        "suggestion": "检查端口占用：lsof -i :<port>",
    },
}

def _analyze_container_logs(container_name: str) -> list[str]:
    result = subprocess.run(
        ["docker", "logs", "--tail", "20", container_name],
        capture_output=True,
        text=True,
        check=False,
    )
    logs = result.stdout + result.stderr
    suggestions = []
    for error_type, config in ERROR_PATTERNS.items():
        if re.search(config["pattern"], logs, re.IGNORECASE):
            suggestions.append(config["suggestion"])
    return suggestions
```

## 8. 与管理台的关系

控制面诊断能力增强后，管理台可以复用这些能力：

- 管理台的"系统状态"页面可以调用 `status` 的数据采集逻辑
- 管理台的"日志查看"页面可以调用 `logs` 的日志读取逻辑
- 管理台的"健康检查"页面可以调用 `doctor` 的检查逻辑

建议在 `llmnode/agent/service.py` 中暴露这些能力为 HTTP API：
- `GET /admin/diagnostics/doctor` → 返回 doctor 检查结果（JSON）
- `GET /admin/diagnostics/status` → 返回 status 详细信息（JSON）
- `GET /admin/diagnostics/logs?target=vllm&lines=50` → 返回日志内容（JSON）

这样管理台和命令行工具可以共享同一套诊断逻辑。

## 9. 文档回流

完成后需要同步的文档：
- `docs/contracts/control-plane.md`：更新 `doctor / status / logs` 的契约
- `docs/process/run.md`：更新诊断流程
- `docs/blueprint/current.md`：更新"当前控制面能力"段落
- `README.md`：如果诊断能力成为核心卖点，可以在 README 中提及

## 10. 风险与限制

### 10.1 性能风险

- GPU 信息采集（`nvidia-smi`）可能较慢（~500ms）
- 容器详细信息采集（`docker inspect`）可能较慢（~200ms）
- 建议：增加缓存机制，避免短时间内重复采集

### 10.2 兼容性风险

- `nvidia-smi` 在无 GPU 环境下不可用 → 需要优雅降级
- `docker inspect` 输出格式可能因 Docker 版本而异 → 需要容错处理

### 10.3 维护成本

- 错误模式识别需要持续维护（新增错误类型）
- 三后端特定检查需要跟随后端版本更新

建议：
- 错误模式配置化（从配置文件读取，而不是硬编码）
- 后端特定检查模块化（每个后端一个独立检查函数）
