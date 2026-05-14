# Long Context Benchmark And Gateway Timeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 `gateway` 对长非流式请求的上游 `ReadTimeout`，并交付一套支持 `vLLM / llama.cpp / sglang` 的直连 benchmark 采集工具，输出结构化原始数据与周期采样结果。

**Architecture:** 代理超时修复通过为 `BackendClient` 引入正式的非流式 upstream timeout 配置完成，保持 health 和 stream 路径的独立超时语义；benchmark 能力拆为 `llmnode/perf` 库层和 `scripts/benchmark_backend.py` 薄入口，分别负责 prompt 构造、GPU 采样、后端日志解析、运行编排和结果落盘。

**Tech Stack:** FastAPI, httpx, pytest, Python dataclasses, Docker, nvidia-smi

---

### Task 1: 给 gateway 非流式上游请求引入正式 timeout 配置

**Files:**
- Modify: `llmnode/config.py`
- Modify: `llmnode/proxy/backend.py`
- Test: `tests/test_api_openai.py`

- [ ] **Step 1: 先写失败测试，锁定 backend client 的 timeout 不再硬编码为 120**

```python
import asyncio
from unittest.mock import patch

import httpx

from llmnode.proxy.backend import VLLMBackendClient


def test_backend_client_uses_configured_request_timeout():
    captured = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs["timeout"]
            captured["base_url"] = kwargs["base_url"]

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, path, json):
            class Response:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"ok": True}

            return Response()

    async def run():
        client = VLLMBackendClient(base_url="http://fake", request_timeout_seconds=300)
        with patch("llmnode.proxy.backend.httpx.AsyncClient", FakeAsyncClient):
            await client.post_json("/v1/chat/completions", {"model": "demo"})

    asyncio.run(run())
    assert captured["timeout"] == 300
```

- [ ] **Step 2: 运行测试确认当前失败**

Run: `pytest tests/test_api_openai.py -k configured_request_timeout -v`
Expected: FAIL，提示 `VLLMBackendClient` 不接受 `request_timeout_seconds` 或仍固定使用 `120`

- [ ] **Step 3: 在配置层新增 gateway upstream timeout 设置**

```python
@dataclass
class GatewaySettings:
    host: str = "0.0.0.0"
    port: int = 4000
    api_key: str = "dev-key"
    backend_url: str = f"http://127.0.0.1:{DEFAULT_BACKEND_PORT}"
    backend_model: str = "qwen36-35b-a3b-fp8"
    backend_request_timeout_seconds: int = 300
```

```python
backend_request_timeout_seconds=int(
    os.getenv(
        "VLLM_CLAUDE_BACKEND_REQUEST_TIMEOUT_SECONDS",
        gateway.get("backend_request_timeout_seconds", 300),
    )
),
```

- [ ] **Step 4: 给 `VLLMBackendClient` 注入 request timeout，并保留 health/stream 的独立语义**

```python
@dataclass
class VLLMBackendClient:
    base_url: str
    backend_type: str = "vllm"
    request_timeout_seconds: int = 300
    health_timeout_seconds: int = 10

    async def post_json(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.request_timeout_seconds,
        ) as client:
            response = await client.post(path, json=payload)
            response.raise_for_status()
            return response.json()
```

- [ ] **Step 5: 在 app 初始化时把 timeout 配置传入 backend client**

```python
backend_client = VLLMBackendClient(
    base_url=settings.gateway.backend_url,
    backend_type=settings.vllm.backend_type,
    request_timeout_seconds=settings.gateway.backend_request_timeout_seconds,
)
```

- [ ] **Step 6: 运行相关测试**

Run: `pytest tests/test_api_openai.py -v`
Expected: PASS，且现有 API openai 测试不回归

- [ ] **Step 7: Commit**

```bash
git add llmnode/config.py llmnode/proxy/backend.py llmnode/api/app.py tests/test_api_openai.py
git commit -m "feat: make gateway upstream timeout configurable"
```

### Task 2: 为 benchmark 建立结果对象与输出目录约定

**Files:**
- Create: `llmnode/perf/__init__.py`
- Create: `llmnode/perf/models.py`
- Modify: `llmnode/config.py`
- Test: `tests/test_perf_benchmark.py`

- [ ] **Step 1: 先写失败测试，锁定 benchmark 输出对象结构**

```python
from llmnode.perf.models import BenchmarkRun, BenchmarkStepResult, SamplePoint


def test_benchmark_models_expose_expected_fields():
    run = BenchmarkRun(
        run_id="demo",
        backend_type="vllm",
        model_name="qwen",
        endpoint="http://127.0.0.1:15673",
        targets=[4096],
    )
    assert run.run_id == "demo"
    assert run.backend_type == "vllm"
    assert run.targets == [4096]
```

- [ ] **Step 2: 运行测试确认当前失败**

Run: `pytest tests/test_perf_benchmark.py -k benchmark_models_expose_expected_fields -v`
Expected: FAIL，提示 `llmnode.perf.models` 不存在

- [ ] **Step 3: 新建 perf 结果 dataclass**

```python
@dataclass
class BenchmarkStepResult:
    label: str
    target_prompt_tokens: int
    actual_prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: float | None = None
    completion_tokens_per_second: float | None = None
    http_status: int | None = None
    result: str = "unknown"
    backend_metrics: dict[str, Any] = field(default_factory=dict)
```

```python
@dataclass
class BenchmarkRun:
    run_id: str
    backend_type: str
    model_name: str
    endpoint: str
    targets: list[int]
    active_backend_profile: str = ""
    model_dir: str = ""
    container_name: str = ""
    max_tokens: int = 64
    status: str = "running"
    errors: list[str] = field(default_factory=list)
```

- [ ] **Step 4: 在配置层提供 benchmark 输出根目录**

```python
BENCHMARK_DIR = DATA_DIR / "benchmarks"
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_perf_benchmark.py -v`
Expected: PASS，模型对象结构固定下来

- [ ] **Step 6: Commit**

```bash
git add llmnode/perf/__init__.py llmnode/perf/models.py llmnode/config.py tests/test_perf_benchmark.py
git commit -m "feat: add benchmark result models"
```

### Task 3: 实现 prompt builder，精确逼近目标 token 阶梯

**Files:**
- Create: `llmnode/perf/prompt_builder.py`
- Test: `tests/test_perf_benchmark.py`

- [ ] **Step 1: 先写失败测试，锁定 prompt builder 的行为**

```python
class FakeTokenizer:
    def apply_chat_template(self, messages, tokenize=True, add_generation_prompt=True):
        content = messages[0]["content"]
        return [1] * len(content.split())


def test_prompt_builder_returns_prompt_not_exceeding_target():
    from llmnode.perf.prompt_builder import build_prompt_for_target

    prompt, actual = build_prompt_for_target(
        tokenizer=FakeTokenizer(),
        target_prompt_tokens=8,
        base_fragment="hello",
    )
    assert actual <= 8
    assert isinstance(prompt, str)
```

- [ ] **Step 2: 运行测试确认当前失败**

Run: `pytest tests/test_perf_benchmark.py -k prompt_builder_returns_prompt_not_exceeding_target -v`
Expected: FAIL，提示 `build_prompt_for_target` 不存在

- [ ] **Step 3: 实现独立 prompt builder**

```python
def build_prompt_for_target(tokenizer, target_prompt_tokens: int, base_fragment: str = "hello ") -> tuple[str, int]:
    lo, hi = 1, target_prompt_tokens
    best_prompt = ""
    best_count = 0

    while lo <= hi:
        mid = (lo + hi) // 2
        prompt = base_fragment * mid
        token_count = count_prompt_tokens(tokenizer, prompt)
        if token_count <= target_prompt_tokens:
            best_prompt = prompt
            best_count = token_count
            lo = mid + 1
        else:
            hi = mid - 1

    return best_prompt, best_count
```

- [ ] **Step 4: 为真实 tokenizer 接口补辅助函数**

```python
def count_prompt_tokens(tokenizer, prompt: str) -> int:
    token_ids = tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}],
        tokenize=True,
        add_generation_prompt=True,
    )
    return len(token_ids)
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_perf_benchmark.py -v`
Expected: PASS，prompt builder 能稳定返回不超过 target 的 prompt

- [ ] **Step 6: Commit**

```bash
git add llmnode/perf/prompt_builder.py tests/test_perf_benchmark.py
git commit -m "feat: add benchmark prompt builder"
```

### Task 4: 实现 GPU 进程采样与“其他进程显存”聚合

**Files:**
- Create: `llmnode/perf/probe_gpu.py`
- Test: `tests/test_perf_gpu_probe.py`

- [ ] **Step 1: 先写失败测试，锁定 GPU 进程归类**

```python
from llmnode.perf.probe_gpu import classify_gpu_processes


def test_classify_gpu_processes_separates_backend_and_other():
    rows = [
        {"pid": 101, "process_name": "python", "used_memory_mb": 12000},
        {"pid": 202, "process_name": "python", "used_memory_mb": 2048},
    ]
    result = classify_gpu_processes(rows, backend_pids={101})
    assert result["backend_process_used_mb"] == 12000
    assert result["other_processes_total_mb"] == 2048
    assert result["other_processes"][0]["pid"] == 202
```

- [ ] **Step 2: 运行测试确认当前失败**

Run: `pytest tests/test_perf_gpu_probe.py -k classify_gpu_processes_separates_backend_and_other -v`
Expected: FAIL，提示 `probe_gpu.py` 不存在

- [ ] **Step 3: 实现 GPU 进程归类函数**

```python
def classify_gpu_processes(rows: list[dict[str, Any]], backend_pids: set[int]) -> dict[str, Any]:
    backend_rows = [row for row in rows if row["pid"] in backend_pids]
    other_rows = [row for row in rows if row["pid"] not in backend_pids]
    return {
        "backend_processes": backend_rows,
        "backend_process_used_mb": sum(row["used_memory_mb"] for row in backend_rows),
        "other_processes_total_mb": sum(row["used_memory_mb"] for row in other_rows),
        "other_processes": other_rows,
    }
```

- [ ] **Step 4: 实现 `nvidia-smi` 采样包装**

```python
def read_gpu_process_rows(raw_text: str) -> list[dict[str, Any]]:
    rows = []
    for line in raw_text.splitlines():
        pid, process_name, used_memory = [part.strip() for part in line.split(",", 2)]
        rows.append(
            {
                "pid": int(pid),
                "process_name": process_name,
                "used_memory_mb": int(used_memory.removesuffix(" MiB")),
            }
        )
    return rows
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_perf_gpu_probe.py -v`
Expected: PASS，且分类逻辑能稳定输出 backend/other 两级结果

- [ ] **Step 6: Commit**

```bash
git add llmnode/perf/probe_gpu.py tests/test_perf_gpu_probe.py
git commit -m "feat: add gpu process probe"
```

### Task 5: 实现三后端日志解析器

**Files:**
- Create: `llmnode/perf/probe_backend.py`
- Test: `tests/test_perf_backend_probe.py`

- [ ] **Step 1: 先写失败测试，覆盖 vLLM 启动期 KV cache 解析**

```python
from llmnode.perf.probe_backend import parse_vllm_startup_metrics


def test_parse_vllm_startup_metrics_extracts_kv_capacity():
    text = """
    Available KV cache memory: 20.5 GiB
    GPU KV cache size: 83,888 tokens
    Maximum concurrency for 262,144 tokens per request: 1.27x
    """
    result = parse_vllm_startup_metrics(text)
    assert result["available_kv_cache_memory"] == "20.5 GiB"
    assert result["gpu_kv_cache_size_tokens"] == 83888
    assert result["max_concurrency_for_256k"] == 1.27
```

- [ ] **Step 2: 补一个 llama.cpp 缺失 KV 百分比时回退为 null 的失败测试**

```python
from llmnode.perf.probe_backend import parse_backend_runtime_sample


def test_llamacpp_runtime_sample_allows_missing_kv_cache_percent():
    result = parse_backend_runtime_sample("llama.cpp", "n_ctx=262144\nn_ctx_seq=262144\n")
    assert result["kv_cache_usage_percent"] is None
    assert result["n_ctx"] == 262144
```

- [ ] **Step 3: 运行测试确认当前失败**

Run: `pytest tests/test_perf_backend_probe.py -v`
Expected: FAIL，提示 `probe_backend.py` 不存在

- [ ] **Step 4: 实现三后端解析函数**

```python
def parse_vllm_startup_metrics(text: str) -> dict[str, Any]:
    return {
        "available_kv_cache_memory": _search_group(text, r"Available KV cache memory:\s*([0-9.]+\s*GiB)"),
        "gpu_kv_cache_size_tokens": _search_int(text, r"GPU KV cache size:\s*([0-9,]+)\s*tokens"),
        "max_concurrency_for_256k": _search_float(
            text,
            r"Maximum concurrency for 262,144 tokens per request:\s*([0-9.]+)x",
        ),
    }
```

```python
def parse_backend_runtime_sample(backend_type: str, text: str) -> dict[str, Any]:
    if backend_type == "vllm":
        return {
            "kv_cache_usage_percent": _search_float(text, r"GPU KV cache usage:\s*([0-9.]+)%"),
            "prompt_throughput_tokens_per_s": _search_float(text, r"Avg prompt throughput:\s*([0-9.]+)\s*tokens/s"),
            "generation_throughput_tokens_per_s": _search_float(text, r"Avg generation throughput:\s*([0-9.]+)\s*tokens/s"),
        }
    if backend_type == "llama.cpp":
        return {
            "kv_cache_usage_percent": None,
            "n_ctx": _search_int(text, r"n_ctx=([0-9]+)"),
            "n_ctx_seq": _search_int(text, r"n_ctx_seq=([0-9]+)"),
        }
    return {
        "kv_cache_usage_percent": None,
        "kv_cache_allocated_tokens": _search_int(text, r"KV Cache is allocated\. #tokens:\s*([0-9,]+)"),
    }
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_perf_backend_probe.py -v`
Expected: PASS，且缺失字段明确返回 `None`

- [ ] **Step 6: Commit**

```bash
git add llmnode/perf/probe_backend.py tests/test_perf_backend_probe.py
git commit -m "feat: add backend benchmark probes"
```

### Task 6: 实现 benchmark 主流程与结果落盘

**Files:**
- Create: `llmnode/perf/benchmark.py`
- Test: `tests/test_perf_benchmark.py`

- [ ] **Step 1: 先写失败测试，锁定 run 输出文件**

```python
from pathlib import Path

from llmnode.perf.benchmark import write_benchmark_outputs
from llmnode.perf.models import BenchmarkRun


def test_write_benchmark_outputs_creates_summary_and_samples(tmp_path: Path):
    run = BenchmarkRun(
        run_id="demo",
        backend_type="vllm",
        model_name="qwen",
        endpoint="http://127.0.0.1:15673",
        targets=[4096],
    )
    output_dir = write_benchmark_outputs(tmp_path, run, [], [])
    assert (output_dir / "summary.json").exists()
    assert (output_dir / "samples.jsonl").exists()
```

- [ ] **Step 2: 运行测试确认当前失败**

Run: `pytest tests/test_perf_benchmark.py -k write_benchmark_outputs_creates_summary_and_samples -v`
Expected: FAIL，提示 `write_benchmark_outputs` 不存在

- [ ] **Step 3: 实现输出目录与文件写入**

```python
def write_benchmark_outputs(
    root_dir: Path,
    run: BenchmarkRun,
    steps: list[BenchmarkStepResult],
    samples: list[SamplePoint],
) -> Path:
    output_dir = root_dir / run.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(asdict(run) | {"steps": [asdict(step) for step in steps]}, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output_dir / "samples.jsonl").open("w", encoding="utf-8") as fh:
        for sample in samples:
            fh.write(json.dumps(asdict(sample), ensure_ascii=False) + "\n")
    return output_dir
```

- [ ] **Step 4: 实现 benchmark orchestration 骨架**

```python
def run_benchmark(...):
    # 1. resolve settings/profile
    # 2. preflight checks
    # 3. iterate steps serially
    # 4. collect samples
    # 5. write outputs
    ...
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_perf_benchmark.py -v`
Expected: PASS，落盘结构稳定

- [ ] **Step 6: Commit**

```bash
git add llmnode/perf/benchmark.py tests/test_perf_benchmark.py
git commit -m "feat: add benchmark runner"
```

### Task 7: 增加 CLI 薄入口脚本

**Files:**
- Create: `scripts/benchmark_backend.py`
- Test: `tests/test_perf_benchmark.py`

- [ ] **Step 1: 先写失败测试，锁定 CLI 参数解析默认值**

```python
from scripts.benchmark_backend import build_parser


def test_benchmark_cli_defaults():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.max_tokens == 64
    assert args.sample_interval == 1.0
```

- [ ] **Step 2: 运行测试确认当前失败**

Run: `pytest tests/test_perf_benchmark.py -k benchmark_cli_defaults -v`
Expected: FAIL，提示 `scripts.benchmark_backend` 不存在

- [ ] **Step 3: 实现薄入口**

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", nargs="*", type=int, default=[4096, 32768, 65536, 131072, 262000])
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--sample-interval", type=float, default=1.0)
    parser.add_argument("--output-dir", type=str, default="")
    parser.add_argument("--profile", type=str, default="")
    return parser
```

```python
def main() -> int:
    args = build_parser().parse_args()
    run_benchmark(...)
    return 0
```

- [ ] **Step 4: 运行测试**

Run: `pytest tests/test_perf_benchmark.py -v`
Expected: PASS，CLI 默认值固定

- [ ] **Step 5: Commit**

```bash
git add scripts/benchmark_backend.py tests/test_perf_benchmark.py
git commit -m "feat: add benchmark cli entrypoint"
```

### Task 8: 做命令级验证并回流文档

**Files:**
- Modify: `docs/knowledge/model_context_performance.md`

- [ ] **Step 1: 先跑 timeout 修复相关测试**

Run: `pytest tests/test_api_openai.py -v`
Expected: PASS

- [ ] **Step 2: 再跑 benchmark 相关测试**

Run: `pytest tests/test_perf_benchmark.py tests/test_perf_gpu_probe.py tests/test_perf_backend_probe.py -v`
Expected: PASS

- [ ] **Step 3: 用当前在线后端跑一轮真实 benchmark**

Run: `/home/heshan/.conda/envs/paper2any/bin/python scripts/benchmark_backend.py --targets 4096 32768 --max-tokens 64`
Expected: 在 `runtime/data/benchmarks/...` 下生成 `summary.json` 和 `samples.jsonl`

- [ ] **Step 4: 验证 gateway 256K 不再在约 120 秒报 500**

Run: 使用当前 `qwen36-27b-fp8` 配置经 `gateway` 发送 `262000 prompt tokens` 非流式请求
Expected: 不再在约 `120s` 左右因 `ReadTimeout` 提前返回 `500`

- [ ] **Step 5: 如有必要，把新脚本和 timeout 语义补充回知识文档**

```markdown
- 当前 benchmark 原始数据由 `scripts/benchmark_backend.py` 输出到 `runtime/data/benchmarks/...`
- `gateway` 非流式上游 timeout 已改为正式可配置，不再固定为 `120s`
```

- [ ] **Step 6: Commit**

```bash
git add llmnode/perf scripts/benchmark_backend.py tests docs/knowledge/model_context_performance.md
git commit -m "feat: add benchmark tooling and fix gateway timeout"
```
