from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.request import Request, urlopen

from .config import LOG_DIR, PROJECT_ROOT, RUN_DIR, load_settings
from .agent.backend import LlamaCppBackendDriver, SGLangBackendDriver, VLLMBackendDriver
from .agent.docker_control import LlamaCppContainerSpec, SGLangContainerSpec, VLLMContainerSpec
from .diagnostics import (
    analyze_logs_for_errors,
    collect_cuda_version,
    collect_gpu_info,
    detect_model_format,
    format_uptime,
    get_container_logs,
    inspect_container,
    parse_model_config,
)
from .security import generate_api_key, hash_api_key
from .storage.db import create_api_key, get_api_key_by_hash, get_api_key_by_name, init_db, update_api_key


def _load_dotenv() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


_load_dotenv()


@dataclass
class RuntimeConfig:
    project_dir: Path
    runtime_dir: Path
    log_dir: Path
    run_dir: Path
    gateway_url: str
    agent_url: str
    backend_url: str
    web_console_dir: Path
    web_console_port: int
    web_console_url: str
    web_console_log_file: Path
    web_console_system_key_name: str
    model_dir: str
    python_bin: str
    gateway_pid_file: Path
    agent_pid_file: Path
    web_pid_file: Path
    backend_logger_pid_file: Path
    backend_latest_log_link: Path
    gateway_log_file: Path
    agent_log_file: Path
    backend_type: str
    backend_container_name: str
    backend_image_name: str
    backend_model_name: str
    backend_host_port: int
    backend_shm_size: str
    vllm_gpu_memory_utilization: float
    vllm_tensor_parallel_size: int
    vllm_max_model_len: int
    vllm_max_num_seqs: int
    vllm_enable_auto_tool_choice: bool
    vllm_reasoning_parser: str
    vllm_tool_call_parser: str
    llamacpp_model_file: str
    llamacpp_n_gpu_layers: int
    llamacpp_ctx_size: int
    llamacpp_n_parallel: int
    sglang_tp_size: int
    sglang_mem_fraction_static: float
    sglang_max_running_requests: int
    sglang_reasoning_parser: str


def _default_python_bin() -> str:
    configured = os.getenv("VLLM_CLAUDE_PYTHON_BIN")
    if configured:
        return configured
    preferred = Path("/home/heshan/.conda/envs/paper2any/bin/python")
    if preferred.exists():
        return str(preferred)
    return sys.executable


def _runtime_config() -> RuntimeConfig:
    settings = load_settings()
    runtime_dir = Path(os.getenv("VLLM_CLAUDE_RUNTIME_DIR", str(PROJECT_ROOT / "runtime"))).resolve()
    log_dir = Path(os.getenv("VLLM_CLAUDE_LOG_DIR", str(LOG_DIR))).resolve()
    run_dir = Path(os.getenv("VLLM_CLAUDE_RUN_DIR", str(RUN_DIR))).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)

    gateway_url = os.getenv(
        "VLLM_CLAUDE_GATEWAY_BASE_URL",
        f"http://127.0.0.1:{settings.gateway.port}",
    )
    agent_url = os.getenv(
        "VLLM_CLAUDE_AGENT_BASE_URL",
        f"http://127.0.0.1:{settings.agent.port}",
    )
    web_console_port = int(os.getenv("VLLM_CLAUDE_WEB_CONSOLE_PORT", "5173"))
    web_console_url = os.getenv(
        "VLLM_CLAUDE_WEB_CONSOLE_URL",
        f"http://127.0.0.1:{web_console_port}",
    )
    web_console_dir = Path(
        os.getenv("VLLM_CLAUDE_WEB_CONSOLE_DIR", str(PROJECT_ROOT / "web-console"))
    ).resolve()
    web_console_system_key_name = os.getenv("VLLM_CLAUDE_WEB_CONSOLE_KEY_NAME", "Web Console")
    python_bin = _default_python_bin()

    return RuntimeConfig(
        project_dir=PROJECT_ROOT,
        runtime_dir=runtime_dir,
        log_dir=log_dir,
        run_dir=run_dir,
        gateway_url=gateway_url,
        agent_url=agent_url,
        backend_url=f"http://127.0.0.1:{settings.vllm.host_port}/v1/models",
        web_console_dir=web_console_dir,
        web_console_port=web_console_port,
        web_console_url=web_console_url,
        web_console_log_file=log_dir / "web-console.log",
        web_console_system_key_name=web_console_system_key_name,
        model_dir=settings.vllm.model_dir,
        python_bin=python_bin,
        gateway_pid_file=run_dir / "gateway.pid",
        agent_pid_file=run_dir / "agent.pid",
        web_pid_file=run_dir / "web-console.pid",
        backend_logger_pid_file=run_dir / f"{settings.vllm.container_name}.logger.pid",
        backend_latest_log_link=log_dir / f"{settings.vllm.container_name}.latest.log",
        gateway_log_file=log_dir / "gateway.log",
        agent_log_file=log_dir / "agent.log",
        backend_type=settings.vllm.backend_type,
        backend_container_name=settings.vllm.container_name,
        backend_image_name=settings.vllm.image_name,
        backend_model_name=settings.vllm.model_name,
        backend_host_port=settings.vllm.host_port,
        backend_shm_size=settings.vllm.shm_size,
        vllm_gpu_memory_utilization=settings.vllm.gpu_memory_utilization,
        vllm_tensor_parallel_size=settings.vllm.tensor_parallel_size,
        vllm_max_model_len=settings.vllm.max_model_len,
        vllm_max_num_seqs=settings.vllm.max_num_seqs,
        vllm_enable_auto_tool_choice=settings.vllm.enable_auto_tool_choice,
        vllm_reasoning_parser=settings.vllm.reasoning_parser,
        vllm_tool_call_parser=settings.vllm.tool_call_parser,
        llamacpp_model_file=settings.vllm.model_file,
        llamacpp_n_gpu_layers=settings.vllm.n_gpu_layers,
        llamacpp_ctx_size=settings.vllm.ctx_size,
        llamacpp_n_parallel=settings.vllm.n_parallel,
        sglang_tp_size=settings.vllm.tensor_parallel_size,
        sglang_mem_fraction_static=settings.vllm.mem_fraction_static,
        sglang_max_running_requests=settings.vllm.max_running_requests,
        sglang_reasoning_parser=settings.vllm.reasoning_parser,
    )


def _ensure_web_console_api_key(config: RuntimeConfig) -> str:
    db_path = PROJECT_ROOT / "runtime" / "data" / "gateway.db"
    secret_path = config.runtime_dir / "data" / "web-console-admin.key"
    conn = init_db(db_path)
    secret_path.parent.mkdir(parents=True, exist_ok=True)

    secret = secret_path.read_text(encoding="utf-8").strip() if secret_path.exists() else ""
    row = get_api_key_by_hash(conn, hash_api_key(secret)) if secret else None
    if row is None:
        existing_named = get_api_key_by_name(conn, config.web_console_system_key_name)
        secret = generate_api_key()
        if existing_named is None:
            create_api_key(
                conn,
                name=config.web_console_system_key_name,
                key_hash=hash_api_key(secret),
                plain_secret=secret,
                scopes=["admin", "inference"],
                note="system-managed local web console key",
            )
        else:
            update_api_key(
                conn,
                existing_named["id"],
                key_hash=hash_api_key(secret),
                plain_secret=secret,
                status="active",
                scopes=["admin", "inference"],
                note="system-managed local web console key",
            )
        secret_path.write_text(f"{secret}\n", encoding="utf-8")
    elif row["status"] != "active" or set(row["scopes"]) != {"admin", "inference"}:
        update_api_key(
            conn,
            row["id"],
            plain_secret=secret,
            status="active",
            scopes=["admin", "inference"],
            note="system-managed local web console key",
        )
    return secret


def _print_header(title: str) -> None:
    print(f"\n== {title} ==")


def _print_kv(key: str, value: str) -> None:
    print(f"  {key:<16} {value}")


def _print_step(label: str) -> None:
    print(f"[step] {label}")


def _print_info(label: str, value: str) -> None:
    print(f"[info] {label}: {value}")


def _print_success(message: str) -> None:
    print(f"[ok] {message}")


def _print_warn(message: str) -> None:
    print(f"[warn] {message}")


def _print_error(message: str) -> None:
    print(f"[error] {message}", file=sys.stderr)


def _print_check(name: str, status: str, detail: str) -> None:
    """打印检查结果，带状态符号"""
    # 状态符号映射
    symbol_map = {
        "ok": "✓",
        "missing": "✗",
        "warn": "⚠",
        "info": "ℹ",
        "down": "✗",
        "present": "✓",
        "running": "✓",
        "free": "○",
        "in_use": "●",
        "exited": "○",
    }

    symbol = symbol_map.get(status, "·")
    print(f"  {symbol} {name:<18} {status:<12} {detail}")


def _http_ok(url: str, method: str = "GET") -> bool:
    request = Request(url, method=method)
    try:
        with urlopen(request, timeout=2):
            return True
    except Exception:
        return False


def _http_post(url: str, timeout: int = 60) -> None:
    request = Request(url, data=b"", method="POST")
    with urlopen(request, timeout=timeout):
        return


def _pid_from_file(pid_file: Path) -> str:
    try:
        return pid_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def _is_pid_running(pid: str) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def _is_pid_file_running(pid_file: Path) -> bool:
    return _is_pid_running(_pid_from_file(pid_file))


def _port_in_use(port: int) -> bool:
    try:
        proc = subprocess.run(
            ["ss", "-ltn"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False
    suffix = f":{port}"
    return any(suffix in line for line in proc.stdout.splitlines())


def _run_command(command: list[str], stdout=None, stderr=None, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        check=True,
        stdout=stdout,
        stderr=stderr,
        text=True,
    )


def _run_command_capture(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True)


def _command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def _collect_version(command: list[str]) -> str:
    result = _run_command_capture(command)
    if result.returncode != 0:
        return "unavailable"
    output = (result.stdout or result.stderr).strip()
    if not output:
        return "available"
    return output.splitlines()[0]


def _docker_container_exists(container_name: str) -> bool:
    result = _run_command_capture(["docker", "ps", "-aq", "-f", f"name=^{container_name}$"])
    return result.returncode == 0 and bool(result.stdout.strip())


def _docker_container_running(container_name: str) -> bool:
    result = _run_command_capture(["docker", "ps", "-q", "-f", f"name=^{container_name}$"])
    return result.returncode == 0 and bool(result.stdout.strip())


def _collect_gpu_info() -> list[dict]:
    """采集 GPU 信息，返回 GPU 列表"""
    if not _command_exists("nvidia-smi"):
        return []

    result = _run_command_capture([
        "nvidia-smi",
        "--query-gpu=index,name,memory.total,memory.used,utilization.gpu",
        "--format=csv,noheader,nounits"
    ])

    if result.returncode != 0:
        return []

    gpus = []
    for line in result.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        try:
            gpus.append({
                "index": int(parts[0]),
                "name": parts[1],
                "memory_total_mb": int(parts[2]),
                "memory_used_mb": int(parts[3]),
                "utilization_percent": int(parts[4]),
            })
        except (ValueError, IndexError):
            continue

    return gpus


def _collect_cuda_version() -> str:
    """采集 CUDA 版本"""
    if not _command_exists("nvidia-smi"):
        return "unavailable"

    result = _run_command_capture(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"])
    if result.returncode != 0:
        return "unavailable"

    driver_version = result.stdout.strip().splitlines()[0] if result.stdout.strip() else "unknown"

    # 尝试获取 CUDA 版本
    result = _run_command_capture(["nvidia-smi"])
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            if "CUDA Version:" in line:
                parts = line.split("CUDA Version:")
                if len(parts) > 1:
                    cuda_version = parts[1].strip().split()[0]
                    return f"{cuda_version} (driver: {driver_version})"

    return f"driver: {driver_version}"


def _inspect_container(container_name: str) -> dict:
    """获取容器详细信息"""
    result = _run_command_capture(["docker", "inspect", container_name])
    if result.returncode != 0:
        return {}

    import json
    try:
        data = json.loads(result.stdout)[0]
        state = data.get("State", {})
        config = data.get("Config", {})
        host_config = data.get("HostConfig", {})

        return {
            "status": state.get("Status", "unknown"),
            "running": state.get("Running", False),
            "exit_code": state.get("ExitCode", 0),
            "started_at": state.get("StartedAt", ""),
            "restart_count": data.get("RestartCount", 0),
            "image": config.get("Image", ""),
            "memory_limit": host_config.get("Memory", 0),
            "shm_size": host_config.get("ShmSize", 0),
        }
    except (json.JSONDecodeError, KeyError, IndexError):
        return {}


def _get_container_logs(container_name: str, lines: int = 20) -> list[str]:
    """获取容器最近日志"""
    result = _run_command_capture(["docker", "logs", "--tail", str(lines), container_name])
    if result.returncode != 0:
        return []
    return (result.stdout + result.stderr).splitlines()


def _detect_model_format(model_dir: Path) -> str:
    """检测模型格式"""
    if not model_dir.is_dir():
        return "unknown"

    if (model_dir / "config.json").exists():
        return "huggingface"

    if any(model_dir.glob("*.gguf")):
        return "gguf"

    return "unknown"


def _parse_model_config(model_dir: Path) -> dict:
    """解析模型配置"""
    config_file = model_dir / "config.json"
    if not config_file.exists():
        return {}

    try:
        with config_file.open("r", encoding="utf-8") as f:
            config = json.load(f)
        return {
            "model_type": config.get("model_type", "unknown"),
            "hidden_size": config.get("hidden_size", 0),
            "num_hidden_layers": config.get("num_hidden_layers", 0),
            "vocab_size": config.get("vocab_size", 0),
        }
    except (json.JSONDecodeError, OSError):
        return {}


# 错误模式配置
ERROR_PATTERNS = {
    "cuda_oom": {
        "pattern": r"CUDA out of memory|OutOfMemoryError|out of memory",
        "suggestion": "降低 gpu_memory_utilization 或 max_model_len 参数",
    },
    "model_not_found": {
        "pattern": r"Model .* not found|No such file or directory.*model|FileNotFoundError.*model",
        "suggestion": "检查 model_dir 和 model_name 配置是否正确",
    },
    "port_in_use": {
        "pattern": r"Address already in use|port .* is already allocated|bind.*failed",
        "suggestion": "检查端口占用，使用 lsof -i :<port> 或 ss -ltn 查看",
    },
    "permission_denied": {
        "pattern": r"Permission denied|PermissionError",
        "suggestion": "检查 Docker 权限和目录权限，可能需要 sudo 或加入 docker 组",
    },
    "gpu_not_found": {
        "pattern": r"No CUDA-capable device|CUDA driver version is insufficient|nvidia-smi not found",
        "suggestion": "检查 GPU 驱动和 CUDA 是否正确安装，Docker 是否配置 nvidia-runtime",
    },
}


def _analyze_logs_for_errors(logs: list[str]) -> list[str]:
    """分析日志，识别错误模式并返回建议"""
    suggestions = []
    log_text = "\n".join(logs)

    for error_type, config in ERROR_PATTERNS.items():
        if re.search(config["pattern"], log_text, re.IGNORECASE):
            suggestions.append(config["suggestion"])

    return suggestions


def _spawn_python_module(config: RuntimeConfig, module_name: str, pid_file: Path, log_file: Path, label: str) -> None:
    if _is_pid_file_running(pid_file):
        _print_info(label, f"already running (pid={_pid_from_file(pid_file)})")
        return
    if pid_file.exists():
        pid_file.unlink()
    with log_file.open("a", encoding="utf-8") as handle:
        process = subprocess.Popen(  # noqa: S603
            [config.python_bin, "-m", module_name],
            cwd=str(config.project_dir),
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env={**os.environ, "PYTHONPATH": str(config.project_dir)},
        )
    pid_file.write_text(f"{process.pid}\n", encoding="utf-8")
    _print_success(f"{label} started (pid={process.pid})")
    _print_info("log", str(log_file))


def _run_python_module_foreground(config: RuntimeConfig, module_name: str) -> int:
    process = subprocess.run(  # noqa: S603
        [config.python_bin, "-m", module_name],
        cwd=str(config.project_dir),
        env={**os.environ, "PYTHONPATH": str(config.project_dir)},
        check=False,
    )
    return int(process.returncode)


def _wait_for_http(url: str, label: str, timeout_seconds: int = 30) -> None:
    for _ in range(timeout_seconds):
        if _http_ok(url):
            _print_success(f"{label} ready at {url}")
            return
        time.sleep(1)
    raise RuntimeError(f"{label} did not become ready: {url}")


def _wait_for_backend_ready(config: RuntimeConfig, timeout_seconds: int = 900) -> None:
    state_url = f"{config.agent_url}/state"
    deadline = time.time() + timeout_seconds
    last_status = ""
    while time.time() < deadline:
        try:
            with urlopen(Request(state_url), timeout=5) as resp:
                data = json.loads(resp.read().decode())
            if data.get("inference_ready"):
                _print_success(f"{config.backend_type} inference ready")
                return
            status = data.get("status", "unknown")
            detail = f"status={status}"
            probe_error = data.get("last_probe_error", "")
            if probe_error:
                detail += f", error={probe_error}"
            if detail != last_status:
                _print_info(f"waiting for {config.backend_type}", detail)
                last_status = detail
        except Exception:
            if last_status != "agent unreachable":
                _print_info(f"waiting for {config.backend_type}", "agent not reachable")
                last_status = "agent unreachable"
        time.sleep(5)
    raise RuntimeError(f"{config.backend_type} did not become ready within {timeout_seconds}s")


def _find_process_by_pattern(pattern: str) -> str:
    try:
        proc = subprocess.run(
            ["pgrep", "-f", pattern],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return ""
    for line in proc.stdout.splitlines():
        candidate = line.strip()
        if candidate:
            return candidate
    return ""


def _build_backend_spec(config: RuntimeConfig):
    bt = config.backend_type
    if bt == "llama.cpp":
        return LlamaCppContainerSpec(
            container_name=config.backend_container_name,
            image_name=config.backend_image_name,
            model_dir=config.model_dir,
            model_file=config.llamacpp_model_file,
            model_name=config.backend_model_name,
            host_port=config.backend_host_port,
            n_gpu_layers=config.llamacpp_n_gpu_layers,
            ctx_size=config.llamacpp_ctx_size,
            n_parallel=config.llamacpp_n_parallel,
            shm_size=config.backend_shm_size,
        )
    if bt == "sglang":
        return SGLangContainerSpec(
            container_name=config.backend_container_name,
            image_name=config.backend_image_name,
            model_dir=config.model_dir,
            model_name=config.backend_model_name,
            host_port=config.backend_host_port,
            tp_size=config.sglang_tp_size,
            mem_fraction_static=config.sglang_mem_fraction_static,
            max_running_requests=config.sglang_max_running_requests,
            shm_size=config.backend_shm_size,
            reasoning_parser=config.sglang_reasoning_parser,
        )
    return VLLMContainerSpec(
        container_name=config.backend_container_name,
        image_name=config.backend_image_name,
        model_dir=config.model_dir,
        model_name=config.backend_model_name,
        host_port=config.backend_host_port,
        gpu_memory_utilization=config.vllm_gpu_memory_utilization,
        tensor_parallel_size=config.vllm_tensor_parallel_size,
        max_model_len=config.vllm_max_model_len,
        max_num_seqs=config.vllm_max_num_seqs,
        shm_size=config.backend_shm_size,
        enable_auto_tool_choice=config.vllm_enable_auto_tool_choice,
        reasoning_parser=config.vllm_reasoning_parser,
        tool_call_parser=config.vllm_tool_call_parser,
    )


def _backend_log_file(config: RuntimeConfig) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return config.log_dir / f"{config.backend_container_name}-{timestamp}.log"


def _ensure_backend_prerequisites(config: RuntimeConfig) -> None:
    if not Path(config.model_dir).is_dir():
        raise RuntimeError(f"Model directory not found: {config.model_dir}")
    result = _run_command_capture(["docker", "image", "inspect", config.backend_image_name])
    if result.returncode != 0:
        raise RuntimeError(f"Docker image not found: {config.backend_image_name}")


def _start_backend_log_tailer(config: RuntimeConfig, log_file: Path) -> None:
    if _is_pid_file_running(config.backend_logger_pid_file):
        _stop_pid_file(config.backend_logger_pid_file, "backend log tailer")
    process = subprocess.Popen(  # noqa: S603
        ["stdbuf", "-oL", "-eL", "docker", "logs", "-f", config.backend_container_name],
        stdout=log_file.open("a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=os.environ.copy(),
    )
    config.backend_logger_pid_file.write_text(f"{process.pid}\n", encoding="utf-8")


def _start_backend_direct(config: RuntimeConfig) -> int:
    _ensure_backend_prerequisites(config)
    spec = _build_backend_spec(config)
    bt = config.backend_type
    if bt == "llama.cpp":
        driver = LlamaCppBackendDriver(spec=spec)
    elif bt == "sglang":
        driver = SGLangBackendDriver(spec=spec)
    else:
        driver = VLLMBackendDriver(spec=spec)
    result = driver.start()
    log_file = _backend_log_file(config)
    log_file.write_text(
        "\n".join(
            [
                "=== llmnode startup ===",
                f"timestamp={datetime.now().strftime('%Y%m%d-%H%M%S')}",
                f"backend_type={bt}",
                f"container_name={config.backend_container_name}",
                f"image_name={config.backend_image_name}",
                f"model_dir={config.model_dir}",
                f"model_name={config.backend_model_name}",
                f"host_port={config.backend_host_port}",
                f"shm_size={config.backend_shm_size}",
                "==========================",
                "",
            ]
        ),
        encoding="utf-8",
    )
    if config.backend_latest_log_link.exists() or config.backend_latest_log_link.is_symlink():
        config.backend_latest_log_link.unlink()
    config.backend_latest_log_link.symlink_to(log_file.name)
    _start_backend_log_tailer(config, log_file)
    snapshot = result.get("snapshot", {})
    _print_success(f"{bt} container ready for warmup: {snapshot.get('name', config.backend_container_name)}")
    _print_info("log", str(log_file))
    _print_info("health", f"curl http://127.0.0.1:{config.backend_host_port}/v1/models")
    return 0


def _stop_backend_direct(config: RuntimeConfig) -> int:
    _stop_pid_file(config.backend_logger_pid_file, "backend log tailer")
    spec = _build_backend_spec(config)
    bt = config.backend_type
    if bt == "llama.cpp":
        driver = LlamaCppBackendDriver(spec=spec)
    elif bt == "sglang":
        driver = SGLangBackendDriver(spec=spec)
    else:
        driver = VLLMBackendDriver(spec=spec)
    result = driver.stop()
    action = result.get("action", "stopped")
    if action == "missing":
        _print_info(bt, f"container {config.backend_container_name} is not running")
    else:
        _print_success(f"{bt} container stop sequence completed ({config.backend_container_name})")
    return 0


def _stop_pid(pid: str) -> bool:
    if not _is_pid_running(pid):
        return False
    os.kill(int(pid), signal.SIGTERM)
    for _ in range(30):
        if not _is_pid_running(pid):
            return True
        time.sleep(1)
    try:
        os.kill(int(pid), signal.SIGKILL)
    except OSError:
        pass
    return True


def _stop_pid_file(pid_file: Path, label: str) -> None:
    pid = _pid_from_file(pid_file)
    if not pid:
        _print_info(label, "not running")
        return
    if _stop_pid(pid):
        pid_file.unlink(missing_ok=True)
        _print_success(f"{label} stopped (pid={pid})")
        return
    pid_file.unlink(missing_ok=True)
    _print_warn(f"{label} stale pid file removed")


def _stop_python_service(pid_file: Path, label: str, legacy_pattern: str) -> None:
    pid = _pid_from_file(pid_file)
    if pid:
        if _stop_pid(pid):
            pid_file.unlink(missing_ok=True)
            _print_success(f"{label} stopped (pid={pid})")
            return
        pid_file.unlink(missing_ok=True)
    legacy_pid = _find_process_by_pattern(legacy_pattern)
    if legacy_pid:
        _stop_pid(legacy_pid)
        _print_success(f"{label} stopped via legacy process match (pid={legacy_pid})")
        return
    _print_info(label, "not running")


def _web_console_matches_project(config: RuntimeConfig) -> bool:
    try:
        with urlopen(config.web_console_url, timeout=2) as response:
            homepage = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return False
    return "/src/main.tsx" in homepage


def _find_web_console_pid(config: RuntimeConfig) -> str:
    vite_bin = config.web_console_dir / "node_modules" / ".bin" / "vite"
    pattern = rf"node .*{vite_bin}( .*)?--port {config.web_console_port}"
    return _find_process_by_pattern(pattern)


def _web_console_has_expected_proxy_env(pid: str, expected_target: str, expected_key: str | None = None) -> bool:
    if not pid:
        return False
    environ_path = Path(f"/proc/{pid}/environ")
    try:
        raw = environ_path.read_bytes()
    except Exception:
        return False
    entries = {}
    for item in raw.split(b"\0"):
        if not item or b"=" not in item:
            continue
        key, value = item.split(b"=", 1)
        entries[key.decode("utf-8", errors="ignore")] = value.decode("utf-8", errors="ignore")
    proxy_key = entries.get("VITE_API_PROXY_KEY")
    if entries.get("VITE_API_PROXY_TARGET") != expected_target or not proxy_key:
        return False
    if expected_key is not None and proxy_key != expected_key:
        return False
    return True


def _adopt_web_console_pid_if_needed(config: RuntimeConfig) -> str:
    existing_pid = _pid_from_file(config.web_pid_file)
    if existing_pid and _is_pid_running(existing_pid):
        return ""
    config.web_pid_file.unlink(missing_ok=True)
    detected_pid = _find_web_console_pid(config)
    if detected_pid:
        config.web_pid_file.write_text(f"{detected_pid}\n", encoding="utf-8")
        return detected_pid
    return ""


def _start_web_console(config: RuntimeConfig) -> None:
    if not config.web_console_dir.exists():
        raise RuntimeError(f"Web console directory not found: {config.web_console_dir}")
    console_secret = _ensure_web_console_api_key(config)
    adopted_pid = _adopt_web_console_pid_if_needed(config)
    if adopted_pid and not _web_console_has_expected_proxy_env(adopted_pid, config.gateway_url, console_secret):
        _print_warn(f"web-console pid={adopted_pid} is missing managed proxy env; restarting it")
        _stop_pid(adopted_pid)
        config.web_pid_file.unlink(missing_ok=True)
        time.sleep(1)
    if _web_console_matches_project(config):
        adopted_pid = _adopt_web_console_pid_if_needed(config)
        if adopted_pid and _web_console_has_expected_proxy_env(adopted_pid, config.gateway_url, console_secret):
            _print_info("web-console", f"adopted existing Vite process (pid={adopted_pid})")
            _print_success(f"Web console already reachable at {config.web_console_url}")
            return
    if _is_pid_file_running(config.web_pid_file):
        _print_info("web-console", f"already running (pid={_pid_from_file(config.web_pid_file)})")
        return
    if not shutil.which("npm"):
        raise RuntimeError("npm is not installed; cannot start web console")
    if not (config.web_console_dir / "node_modules").exists():
        raise RuntimeError("web-console/node_modules is missing. Run 'cd web-console && npm install' first")
    if _port_in_use(config.web_console_port):
        raise RuntimeError(
            f"Port {config.web_console_port} is already in use, and {config.web_console_url} is not responding"
        )
    with config.web_console_log_file.open("a", encoding="utf-8") as handle:
        env = os.environ.copy()
        env["VITE_API_PROXY_TARGET"] = config.gateway_url
        env["VITE_API_PROXY_KEY"] = console_secret
        process = subprocess.Popen(  # noqa: S603
            [
                "npm",
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                str(config.web_console_port),
                "--strictPort",
            ],
            cwd=str(config.web_console_dir),
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )
    config.web_pid_file.write_text(f"{process.pid}\n", encoding="utf-8")
    _print_success(f"Web console started (pid={process.pid})")
    _print_info("log", str(config.web_console_log_file))


def _start_single_service(config: RuntimeConfig, service: str, daemon: bool) -> int:
    if service == "vllm":
        if not daemon:
            raise RuntimeError("backend only supports daemon-style service control")
        return _start_backend_direct(config)
    if service == "agent":
        if daemon:
            _spawn_python_module(config, "llmnode.agent", config.agent_pid_file, config.agent_log_file, "Agent")
            return 0
        return _run_python_module_foreground(config, "llmnode.agent")
    if daemon:
        _spawn_python_module(config, "llmnode", config.gateway_pid_file, config.gateway_log_file, "Gateway")
        return 0
    return _run_python_module_foreground(config, "llmnode")


def _stop_single_service(config: RuntimeConfig, service: str) -> int:
    if service == "vllm":
        return _stop_backend_direct(config)
    if service == "agent":
        _stop_python_service(config.agent_pid_file, "Agent", r"python(3)? -m llmnode\.agent$")
        return 0
    _stop_python_service(config.gateway_pid_file, "Gateway", r"python(3)? -m llmnode$")
    return 0


def _probe_process_state(pid_file: Path, port: int | None, url: str | None) -> dict[str, str]:
    pid = _pid_from_file(pid_file)
    pid_running = _is_pid_running(pid)
    port_listening = _port_in_use(port) if port else False
    http_ready = _http_ok(url) if url else False
    state = "stopped"
    if http_ready:
        state = "ready"
    elif pid_running or port_listening:
        state = "partial"
    return {
        "pid": pid,
        "pid_running": str(pid_running).lower(),
        "port_listening": str(port_listening).lower(),
        "http_ready": str(http_ready).lower(),
        "state": state,
    }


def _print_process_status(name: str, pid_file: Path, port: int | None, url: str | None) -> None:
    probe = _probe_process_state(pid_file, port, url)
    state = probe["state"]
    if state == "ready":
        print(f"  {name:<12} ready   pid={probe['pid'] or 'unknown'}  port={port or 'n/a'}  http=ok")
        return
    if state == "partial":
        print(
            f"  {name:<12} partial pid={probe['pid'] or 'none'}  port={port or 'n/a'}"
            f"  pid_running={probe['pid_running']}  port_listening={probe['port_listening']}"
            f"  http_ready={probe['http_ready']}"
        )
        return
    print(f"  {name:<12} stopped")


def _format_uptime(started_at: str) -> str:
    """计算容器运行时长"""
    if not started_at or started_at == "0001-01-01T00:00:00Z":
        return "not started"

    try:
        from datetime import datetime, timezone
        start_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - start_time

        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60

        if days > 0:
            return f"{days}d {hours}h"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    except (ValueError, AttributeError):
        return "unknown"


def _status_stack(config: RuntimeConfig) -> int:
    _print_header("llmnode status")
    _print_kv("project", str(config.project_dir))
    _print_kv("backend", config.backend_type)
    _print_kv("python", config.python_bin)
    _print_kv("model_dir", config.model_dir)
    _print_kv("web_console", config.web_console_url)

    if _web_console_matches_project(config):
        adopted_pid = _adopt_web_console_pid_if_needed(config)
        if adopted_pid:
            _print_info("web-console", f"adopted existing Vite process (pid={adopted_pid})")

    settings = load_settings()

    _print_header("processes")
    _print_process_status("gateway", config.gateway_pid_file, settings.gateway.port, f"{config.gateway_url}/health/liveliness")
    _print_process_status("agent", config.agent_pid_file, settings.agent.port, f"{config.agent_url}/state")
    _print_process_status("web_console", config.web_pid_file, config.web_console_port, config.web_console_url)

    # 容器详细信息和推理参数展示
    _print_header(f"backend ({config.backend_type})")

    backend_container_running = _docker_container_running(config.backend_container_name)
    backend_container_exists = _docker_container_exists(config.backend_container_name)

    if backend_container_exists:
        container_info = _inspect_container(config.backend_container_name)
        if container_info:
            status = container_info.get("status", "unknown")
            uptime = _format_uptime(container_info.get("started_at", ""))
            restart_count = container_info.get("restart_count", 0)

            _print_kv("container", f"{config.backend_container_name} ({status}, uptime: {uptime}, restarts: {restart_count})")
            _print_kv("image", config.backend_image_name)
            _print_kv("model", config.backend_model_name)

            # 根据后端类型展示推理参数
            if config.backend_type == "vllm":
                _print_kv("gpu_memory_util", str(config.vllm_gpu_memory_utilization))
                _print_kv("tensor_parallel", str(config.vllm_tensor_parallel_size))
                _print_kv("max_model_len", str(config.vllm_max_model_len))
                _print_kv("max_num_seqs", str(config.vllm_max_num_seqs))
                if config.vllm_reasoning_parser:
                    _print_kv("reasoning_parser", config.vllm_reasoning_parser)
                if config.vllm_tool_call_parser:
                    _print_kv("tool_call_parser", config.vllm_tool_call_parser)
            elif config.backend_type == "llama.cpp":
                _print_kv("model_file", config.llamacpp_model_file)
                _print_kv("n_gpu_layers", str(config.llamacpp_n_gpu_layers))
                _print_kv("ctx_size", str(config.llamacpp_ctx_size))
                _print_kv("n_parallel", str(config.llamacpp_n_parallel))
            elif config.backend_type == "sglang":
                _print_kv("tp_size", str(config.sglang_tp_size))
                _print_kv("mem_fraction", str(config.sglang_mem_fraction_static))
                _print_kv("max_requests", str(config.sglang_max_running_requests))
                if config.sglang_reasoning_parser:
                    _print_kv("reasoning_parser", config.sglang_reasoning_parser)

            # 健康检查
            backend_http_state = "ok" if _http_ok(config.backend_url) else "unreachable"
            _print_kv("health", f"{backend_http_state} ({config.backend_url})")
        else:
            _print_kv("container", f"{config.backend_container_name} (exists but cannot inspect)")
    else:
        _print_kv("container", f"{config.backend_container_name} (not found)")

    # HTTP 健康检查
    gateway_http_state = "ok" if _http_ok(f"{config.gateway_url}/health/liveliness") else "unreachable"
    agent_http_state = "ok" if _http_ok(f"{config.agent_url}/state") else "unreachable"
    backend_http_state = "ok" if _http_ok(config.backend_url) else "unreachable"
    web_console_http_state = "ok" if _http_ok(config.web_console_url) else "unreachable"

    # 从 agent /state 获取推理探针结果
    agent_inference_ready = False
    agent_probe_error = ""
    if agent_http_state == "ok":
        try:
            with urlopen(Request(f"{config.agent_url}/state"), timeout=5) as resp:
                agent_state_data = json.loads(resp.read().decode())
            agent_inference_ready = bool(agent_state_data.get("inference_ready", False))
            agent_probe_error = str(agent_state_data.get("last_probe_error", ""))
        except Exception:
            pass

    # 栈状态细化（6 种状态）
    stack_state = "partial"
    stack_detail = "Some services are available, but the stack is not fully ready yet."

    if all(state == "unreachable" for state in (gateway_http_state, agent_http_state, backend_http_state, web_console_http_state)):
        stack_state = "stopped"
        stack_detail = "No managed services are currently reachable."
    elif agent_http_state == "ok" and not backend_container_exists:
        stack_state = "starting"
        stack_detail = f"Agent is up, but {config.backend_type} container does not exist yet."
    elif agent_http_state == "ok" and backend_container_running and backend_http_state == "unreachable":
        stack_state = "warming"
        stack_detail = f"Control plane is up, and {config.backend_type} is warming up or loading the model."
    elif agent_http_state == "ok" and backend_http_state == "ok" and not agent_inference_ready:
        stack_state = "warming"
        stack_detail = f"Backend HTTP reachable but inference not ready"
        if agent_probe_error:
            stack_detail += f": {agent_probe_error}"
    elif all(state == "ok" for state in (gateway_http_state, agent_http_state, backend_http_state, web_console_http_state)):
        # 检查是否有警告（容器重启次数 > 0）
        if backend_container_exists:
            container_info = _inspect_container(config.backend_container_name)
            if container_info and container_info.get("restart_count", 0) > 0:
                stack_state = "degraded"
                stack_detail = f"All services are reachable, but {config.backend_type} container has restarted {container_info['restart_count']} time(s)."
            else:
                stack_state = "ready"
                stack_detail = f"Gateway, agent, {config.backend_type}, and web-console are all reachable."
        else:
            stack_state = "ready"
            stack_detail = f"Gateway, agent, {config.backend_type}, and web-console are all reachable."

    _print_header("summary")
    _print_kv("stack_state", stack_state)
    _print_kv("detail", stack_detail)

    _print_header("http health")
    _print_kv("gateway_http", f"{gateway_http_state} ({config.gateway_url}/health/liveliness)")
    _print_kv("agent_http", f"{agent_http_state} ({config.agent_url}/state)")
    _print_kv("backend_http", f"{backend_http_state} ({config.backend_url})")
    _print_kv("backend_inference", f"{'ready' if agent_inference_ready else 'not ready'}" + (f" ({agent_probe_error})" if agent_probe_error else ""))
    _print_kv("web_console_http", f"{web_console_http_state} ({config.web_console_url})")
    return 0


def _env_report(config: RuntimeConfig) -> int:
    _print_header("llmnode env")
    _print_kv("project", str(config.project_dir))
    _print_kv("python", config.python_bin)
    _print_kv("runtime_dir", str(config.runtime_dir))
    _print_kv("log_dir", str(config.log_dir))
    _print_kv("run_dir", str(config.run_dir))
    _print_kv("model_dir", config.model_dir)
    _print_kv("backend_type", config.backend_type)
    _print_kv("gateway_url", config.gateway_url)
    _print_kv("agent_url", config.agent_url)
    _print_kv("backend_url", config.backend_url)
    _print_kv("web_console_url", config.web_console_url)
    _print_kv("web_console_dir", str(config.web_console_dir))
    return 0


def _doctor(config: RuntimeConfig) -> int:
    _print_header("llmnode doctor")
    _print_kv("project", str(config.project_dir))
    _print_kv("python", config.python_bin)
    _print_kv("backend_type", config.backend_type)
    _print_kv("model_dir", config.model_dir)
    _print_kv("web_console", config.web_console_url)

    _print_header("environment")
    python_status = "ok" if Path(config.python_bin).exists() else "missing"
    _print_check("python_bin", python_status, config.python_bin)
    _print_check("python_version", "info", _collect_version([config.python_bin, "--version"]))
    _print_check("docker", "ok" if _command_exists("docker") else "missing", _collect_version(["docker", "--version"]))
    _print_check("npm", "ok" if _command_exists("npm") else "missing", _collect_version(["npm", "--version"]))
    _print_check("ss", "ok" if _command_exists("ss") else "missing", _collect_version(["ss", "--version"]))
    _print_check("model_dir", "ok" if Path(config.model_dir).is_dir() else "missing", config.model_dir)
    _print_check(
        "web_console_dir",
        "ok" if config.web_console_dir.is_dir() else "missing",
        str(config.web_console_dir),
    )
    _print_check(
        "node_modules",
        "ok" if (config.web_console_dir / "node_modules").is_dir() else "missing",
        str(config.web_console_dir / "node_modules"),
    )

    # GPU 信息检查
    gpus = _collect_gpu_info()
    if gpus:
        _print_header("gpu")
        _print_check("gpu_count", "ok", f"{len(gpus)} GPU(s) detected")
        for gpu in gpus:
            mem_used_gb = gpu["memory_used_mb"] / 1024
            mem_total_gb = gpu["memory_total_mb"] / 1024
            mem_percent = (gpu["memory_used_mb"] / gpu["memory_total_mb"] * 100) if gpu["memory_total_mb"] > 0 else 0
            _print_check(
                f"gpu_{gpu['index']}",
                "info",
                f"{gpu['name']} ({mem_total_gb:.0f}GB, {mem_percent:.0f}% used, {mem_used_gb:.1f}GB occupied, util: {gpu['utilization_percent']}%)"
            )
        cuda_version = _collect_cuda_version()
        _print_check("cuda", "ok" if cuda_version != "unavailable" else "missing", cuda_version)
    elif _command_exists("nvidia-smi"):
        _print_header("gpu")
        _print_check("gpu_count", "warn", "nvidia-smi available but no GPUs detected")
    else:
        _print_header("gpu")
        _print_check("nvidia-smi", "missing", "GPU support unavailable")

    # 模型文件检查
    model_dir_path = Path(config.model_dir)
    if model_dir_path.is_dir():
        _print_header("model")
        model_format = _detect_model_format(model_dir_path)
        _print_check("model_format", "ok" if model_format != "unknown" else "warn", model_format)

        if model_format == "huggingface":
            model_config = _parse_model_config(model_dir_path)
            if model_config:
                _print_check("model_type", "info", model_config.get("model_type", "unknown"))
                _print_check("num_layers", "info", str(model_config.get("num_hidden_layers", "unknown")))
                _print_check("hidden_size", "info", str(model_config.get("hidden_size", "unknown")))
        elif model_format == "gguf":
            gguf_files = list(model_dir_path.glob("*.gguf"))
            if gguf_files:
                _print_check("gguf_files", "info", f"{len(gguf_files)} GGUF file(s) found")

    _print_header("ports")
    _print_check("gateway_port", "in_use" if _port_in_use(4000) else "free", "4000")
    _print_check("agent_port", "in_use" if _port_in_use(4010) else "free", "4010")
    _print_check("backend_port", "in_use" if _port_in_use(config.backend_host_port) else "free", str(config.backend_host_port))
    _print_check(
        "web_console_port",
        "in_use" if _port_in_use(config.web_console_port) else "free",
        str(config.web_console_port),
    )

    _print_header("http")
    _print_check("gateway_http", "ok" if _http_ok(f"{config.gateway_url}/health/liveliness") else "down", f"{config.gateway_url}/health/liveliness")
    _print_check("agent_http", "ok" if _http_ok(f"{config.agent_url}/state") else "down", f"{config.agent_url}/state")
    _print_check("backend_http", "ok" if _http_ok(config.backend_url) else "down", config.backend_url)
    _print_check("web_console_http", "ok" if _http_ok(config.web_console_url) else "down", config.web_console_url)

    _print_header("artifacts")
    _print_check("gateway_pid", "present" if config.gateway_pid_file.exists() else "missing", str(config.gateway_pid_file))
    _print_check("agent_pid", "present" if config.agent_pid_file.exists() else "missing", str(config.agent_pid_file))
    _print_check("web_pid", "present" if config.web_pid_file.exists() else "missing", str(config.web_pid_file))
    _print_check(
        "backend_logger_pid",
        "present" if config.backend_logger_pid_file.exists() else "missing",
        str(config.backend_logger_pid_file),
    )
    _print_check(
        "backend_latest_log",
        "present" if config.backend_latest_log_link.exists() or config.backend_latest_log_link.is_symlink() else "missing",
        str(config.backend_latest_log_link),
    )

    # Docker 状态和容器详细诊断
    _print_header(f"backend ({config.backend_type})")
    if _command_exists("docker"):
        backend_container_state = "running" if _docker_container_running(config.backend_container_name) else (
            "present" if _docker_container_exists(config.backend_container_name) else "missing"
        )
        _print_check(
            "container_state",
            backend_container_state,
            config.backend_container_name,
        )
        backend_image_state = "ok" if _run_command_capture(["docker", "image", "inspect", config.backend_image_name]).returncode == 0 else "missing"
        _print_check("image", backend_image_state, config.backend_image_name)

        # 容器详细信息
        if backend_container_state in ("running", "present"):
            container_info = _inspect_container(config.backend_container_name)
            if container_info:
                _print_check("container_status", "info", container_info.get("status", "unknown"))
                _print_check("restart_count", "info", str(container_info.get("restart_count", 0)))
                if container_info.get("shm_size", 0) > 0:
                    shm_gb = container_info["shm_size"] / (1024 ** 3)
                    _print_check("shm_size", "info", f"{shm_gb:.1f}GB")
    else:
        backend_container_state = "unknown"
        backend_image_state = "unknown"
        _print_check("docker", "missing", "docker unavailable")

    # 三后端特定检查
    if config.backend_type == "vllm" and model_format == "gguf":
        _print_check("format_mismatch", "warn", "vLLM requires HuggingFace format, but GGUF detected")
    elif config.backend_type == "llama.cpp" and model_format == "huggingface":
        _print_check("format_mismatch", "warn", "llama.cpp requires GGUF format, but HuggingFace detected")

    # 智能建议系统
    suggestions: list[str] = []

    # 基础环境建议
    if not (config.web_console_dir / "node_modules").is_dir():
        suggestions.append("安装前端依赖：cd web-console && npm install")
    if not _command_exists("docker"):
        suggestions.append("安装并启动 Docker，确认 `docker --version` 可用")
    elif backend_image_state == "missing":
        suggestions.append(f"准备后端镜像：docker pull {config.backend_image_name}")
    if not Path(config.model_dir).is_dir():
        suggestions.append(f"检查模型目录是否存在：{config.model_dir}")

    # 容器日志分析建议
    if backend_container_state == "present" and not _http_ok(config.backend_url):
        container_logs = _get_container_logs(config.backend_container_name, 20)
        log_suggestions = _analyze_logs_for_errors(container_logs)
        suggestions.extend(log_suggestions)

    # 服务状态建议
    if not _http_ok(f"{config.agent_url}/state") and not _http_ok(f"{config.gateway_url}/health/liveliness"):
        suggestions.append("尝试启动整栈：python -m llmnode.control start")
    elif not _http_ok(config.backend_url):
        suggestions.append(f"查看后端日志：python -m llmnode.control logs --target vllm --lines 50")
    if not _http_ok(config.web_console_url) and (config.web_console_dir / "node_modules").is_dir():
        suggestions.append("单独查看前端日志：python -m llmnode.control logs --target web-console --lines 50")

    # 模型格式不匹配建议
    if config.backend_type == "vllm" and model_format == "gguf":
        suggestions.append("切换到 llama.cpp 后端或转换模型为 HuggingFace 格式")
    elif config.backend_type == "llama.cpp" and model_format == "huggingface":
        suggestions.append("切换到 vLLM 后端或转换模型为 GGUF 格式")

    # GPU 建议
    if not gpus and config.backend_type in ("vllm", "sglang"):
        suggestions.append("检查 GPU 驱动和 CUDA 安装，确认 nvidia-smi 可用")
        suggestions.append("检查 Docker 是否配置 nvidia-runtime：docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi")

    _print_header("suggestions")
    if suggestions:
        for index, item in enumerate(suggestions, start=1):
            print(f"  {index}. {item}")
    else:
        _print_info("next", "No obvious issues detected. Use status/logs for deeper inspection.")
    return 0


def _resolve_log_targets(config: RuntimeConfig, target: str) -> list[tuple[str, Path]]:
    """解析日志目标，支持后端类型感知"""
    targets: list[tuple[str, Path]] = [
        ("agent", config.agent_log_file),
        ("gateway", config.gateway_log_file),
        ("web-console", config.web_console_log_file),
    ]

    # 后端类型感知：根据实际 backend_type 映射
    backend_name = config.backend_type
    targets.append((backend_name, config.backend_latest_log_link))

    # 兼容旧的 vllm 别名和新的 backend 通用别名
    if target in ("vllm", "backend"):
        target = backend_name

    if target == "all":
        return targets

    normalized = {name: path for name, path in targets}
    if target not in normalized:
        raise ValueError(f"Unknown log target: {target}. Available: {', '.join(normalized.keys())}, all")

    return [(target, normalized[target])]


def _tail_lines(path: Path, max_lines: int) -> list[str]:
    if not path.exists() and not path.is_symlink():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    if max_lines <= 0:
        return lines
    return lines[-max_lines:]


def _highlight_log_line(line: str) -> str:
    """高亮日志行中的错误关键词"""
    # ANSI 颜色代码
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    RESET = "\033[0m"

    # 错误关键词（红色）
    error_keywords = ["ERROR", "FATAL", "CRITICAL", "Exception", "Traceback", "Failed", "failed"]
    for keyword in error_keywords:
        if keyword in line:
            return f"{RED}{line}{RESET}"

    # 警告关键词（黄色）
    warn_keywords = ["WARN", "WARNING", "Warning"]
    for keyword in warn_keywords:
        if keyword in line:
            return f"{YELLOW}{line}{RESET}"

    # 信息关键词（绿色）
    info_keywords = ["INFO", "DEBUG"]
    for keyword in info_keywords:
        if keyword in line:
            return f"{GREEN}{line}{RESET}"

    return line


def _grep_lines(lines: list[str], pattern: str, ignore_case: bool = False) -> list[str]:
    """过滤日志行，支持正则表达式"""
    flags = re.IGNORECASE if ignore_case else 0
    try:
        regex = re.compile(pattern, flags)
    except re.error:
        # 如果不是有效的正则表达式，当作普通字符串处理
        if ignore_case:
            pattern_lower = pattern.lower()
            return [line for line in lines if pattern_lower in line.lower()]
        return [line for line in lines if pattern in line]

    return [line for line in lines if regex.search(line)]


def _follow_log_file(path: Path, highlight: bool = True) -> None:
    """实时跟踪日志文件"""
    if path.is_symlink():
        path = path.resolve()

    if not path.exists():
        print(f"  Log file does not exist: {path}")
        return

    # 使用 tail -f 实时跟踪
    try:
        process = subprocess.Popen(
            ["tail", "-f", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        print(f"  Following {path} (Ctrl+C to stop)...")
        for line in process.stdout:
            if highlight:
                highlighted = _highlight_log_line(line.rstrip())
                print(f"  {highlighted}")
            else:
                print(f"  {line.rstrip()}")
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
        print("\n  Stopped following log.")
    except Exception as e:
        print(f"  Error following log: {e}")


def _logs(config: RuntimeConfig, target: str, lines: int, follow: bool = False, grep: str = "", ignore_case: bool = False, highlight: bool = True) -> int:
    _print_header("llmnode logs")
    _print_kv("target", target)
    if follow:
        _print_kv("mode", "follow (real-time)")
    else:
        _print_kv("lines", str(lines))
    if grep:
        _print_kv("grep", grep)

    try:
        log_targets = _resolve_log_targets(config, target)
    except ValueError as e:
        _print_error(str(e))
        return 1

    for name, path in log_targets:
        _print_header(f"log:{name}")
        resolved = path.resolve(strict=False) if path.is_symlink() else path
        _print_kv("path", str(resolved))

        if not path.exists() and not path.is_symlink():
            _print_warn("log file is missing")
            continue

        # 实时跟踪模式
        if follow:
            _follow_log_file(path, highlight=highlight)
            continue

        # 普通模式：读取最后 N 行
        content = _tail_lines(path, lines)
        if not content:
            _print_info("content", "log file is empty")
            continue

        # 关键词搜索
        if grep:
            content = _grep_lines(content, grep, ignore_case)
            if not content:
                _print_info("grep", f"no lines matching '{grep}'")
                continue

        # 输出日志内容
        for line in content:
            if highlight:
                highlighted = _highlight_log_line(line)
                print(f"  {highlighted}")
            else:
                print(f"  {line}")

    return 0


def _stop_stack(config: RuntimeConfig) -> int:
    _print_header("llmnode stop")
    if _http_ok(f"{config.agent_url}/health/liveliness"):
        _print_step(f"requesting {config.backend_type} stop through agent")
        try:
            _http_post(f"{config.agent_url}/manage/stop")
        except Exception as exc:
            _print_warn(f"stop request failed: {exc}")
            _print_step(f"falling back to direct {config.backend_type} stop")
            _stop_backend_direct(config)
        else:
            # Verify the backend actually stopped
            _print_step("verifying backend stop")
            for _ in range(30):
                time.sleep(1)
                if not _docker_container_running(config.backend_container_name):
                    _print_success(f"{config.backend_type} container stopped")
                    break
            else:
                _print_warn(f"{config.backend_type} container may still be running")
    else:
        _print_step(f"agent not reachable, stopping {config.backend_type} directly")
        _stop_backend_direct(config)

    _print_step("stopping web-console")
    _adopt_web_console_pid_if_needed(config)
    _stop_pid_file(config.web_pid_file, "Web console")

    _print_step("stopping gateway-api")
    _stop_python_service(config.gateway_pid_file, "Gateway", r"python(3)? -m llmnode$")

    _print_step("stopping node-agent")
    _stop_python_service(config.agent_pid_file, "Node agent", r"python(3)? -m llmnode\.agent$")

    _print_header("stack stopped")
    _print_kv("result", f"agent, gateway, {config.backend_type}, and web-console stop sequence completed")
    return 0


def _start_stack(config: RuntimeConfig) -> int:
    started_agent = False
    try:
        _print_header("llmnode start")
        _print_kv("backend", config.backend_type)
        _print_kv("python", config.python_bin)
        _print_kv("model_dir", config.model_dir)
        _print_kv("gateway", config.gateway_url)
        _print_kv("agent", config.agent_url)
        _print_kv("web_console", config.web_console_url)

        _print_step("starting node-agent")
        _spawn_python_module(config, "llmnode.agent", config.agent_pid_file, config.agent_log_file, "Node agent")
        started_agent = True
        _wait_for_http(f"{config.agent_url}/health/liveliness", "Agent")

        _print_step(f"requesting {config.backend_type} start through agent")
        _http_post(f"{config.agent_url}/manage/start")
        _print_success(f"{config.backend_type} start requested through agent")

        _print_step("starting gateway-api")
        _spawn_python_module(config, "llmnode", config.gateway_pid_file, config.gateway_log_file, "Gateway")
        _wait_for_http(f"{config.gateway_url}/health/liveliness", "Gateway")

        _print_step("starting web-console")
        _start_web_console(config)
        _wait_for_http(config.web_console_url, "Web console")

        _print_step(f"waiting for {config.backend_type} inference readiness")
        _wait_for_backend_ready(config)

        _print_header("stack ready")
        _print_kv("gateway", config.gateway_url)
        _print_kv("agent", config.agent_url)
        _print_kv("web_console", config.web_console_url)
        _print_kv("next", "Run 'python -m llmnode.control status' for a full health summary")
        return 0
    except Exception as exc:
        if started_agent:
            _print_error("Startup failed; stopping agent")
            _stop_python_service(config.agent_pid_file, "Node agent", r"python(3)? -m llmnode\.agent$")
        _print_error(str(exc))
        return 1


def _restart_stack(config: RuntimeConfig) -> int:
    _print_header("llmnode restart")
    _print_info("action", "stop current stack, then start again")
    _stop_stack(config)
    return _start_stack(config)


def _restart_without_backend(config: RuntimeConfig) -> int:
    _print_header("llmnode restart")
    _print_info("action", "restart control-plane services without touching backend container")

    _print_step("stopping web-console")
    _adopt_web_console_pid_if_needed(config)
    _stop_pid_file(config.web_pid_file, "Web console")

    _print_step("stopping gateway-api")
    _stop_python_service(config.gateway_pid_file, "Gateway", r"python(3)? -m llmnode$")

    _print_step("stopping node-agent")
    _stop_python_service(config.agent_pid_file, "Node agent", r"python(3)? -m llmnode\.agent$")

    _print_step("starting node-agent")
    _spawn_python_module(config, "llmnode.agent", config.agent_pid_file, config.agent_log_file, "Node agent")
    _wait_for_http(f"{config.agent_url}/health/liveliness", "Agent")

    _print_step("starting gateway-api")
    _spawn_python_module(config, "llmnode", config.gateway_pid_file, config.gateway_log_file, "Gateway")
    _wait_for_http(f"{config.gateway_url}/health/liveliness", "Gateway")

    _print_step("starting web-console")
    _start_web_console(config)
    _wait_for_http(config.web_console_url, "Web console")

    _print_header("control-plane ready")
    _print_kv("agent", config.agent_url)
    _print_kv("gateway", config.gateway_url)
    _print_kv("web_console", config.web_console_url)
    _print_kv("backend", f"left untouched ({config.backend_type})")
    return 0


def _create_api_key_action(args: argparse.Namespace) -> int:
    db_path = PROJECT_ROOT / "runtime" / "data" / "gateway.db"
    conn = init_db(db_path)
    secret = generate_api_key()
    try:
        row = create_api_key(
            conn,
            name=args.name,
            key_hash=hash_api_key(secret),
            scopes=list(args.scope),
            rpm_limit=args.rpm_limit,
            concurrency_limit=args.concurrency_limit,
            note=args.note,
            status="disabled" if args.disabled else "active",
        )
    except Exception as exc:
        _print_error(str(exc))
        return 1

    _print_header("api key created")
    _print_kv("id", str(row["id"]))
    _print_kv("name", row["name"])
    _print_kv("status", row["status"])
    _print_kv("scopes", ",".join(row["scopes"]))
    _print_kv("db", str(db_path))
    _print_info("secret", secret)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m llmnode.control")
    parser.add_argument("action", choices=["start", "stop", "restart", "status", "doctor", "env", "logs", "create-api-key"], nargs="?", default="status")
    parser.add_argument("--service", choices=["agent", "gateway", "vllm"])
    parser.add_argument("--exclude-backend", action="store_true")
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--foreground", action="store_true")
    parser.add_argument("--target", choices=["agent", "gateway", "web-console", "vllm", "backend", "all"], default="all")
    parser.add_argument("--lines", type=int, default=20)
    parser.add_argument("--follow", "-f", action="store_true", help="Follow log output in real-time")
    parser.add_argument("--grep", type=str, default="", help="Filter log lines by pattern (supports regex)")
    parser.add_argument("--ignore-case", "-i", action="store_true", help="Ignore case when using --grep")
    parser.add_argument("--no-highlight", action="store_true", help="Disable error highlighting")
    parser.add_argument("--name", type=str, default="")
    parser.add_argument("--scope", action="append", choices=["admin", "inference"], default=[])
    parser.add_argument("--rpm-limit", type=int, default=None)
    parser.add_argument("--concurrency-limit", type=int, default=None)
    parser.add_argument("--note", type=str, default=None)
    parser.add_argument("--disabled", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    config = _runtime_config()
    if args.service:
        if args.action == "start":
            daemon = True
            if args.foreground:
                daemon = False
            elif args.daemon:
                daemon = True
            return _start_single_service(config, args.service, daemon=daemon)
        if args.action == "stop":
            return _stop_single_service(config, args.service)
        parser.error("--service only supports 'start' and 'stop'")
    if args.action == "start":
        return _start_stack(config)
    if args.action == "stop":
        return _stop_stack(config)
    if args.action == "restart":
        if args.exclude_backend:
            return _restart_without_backend(config)
        return _restart_stack(config)
    if args.action == "doctor":
        return _doctor(config)
    if args.action == "env":
        return _env_report(config)
    if args.action == "logs":
        return _logs(
            config,
            args.target,
            max(args.lines, 0),
            follow=args.follow,
            grep=args.grep,
            ignore_case=args.ignore_case,
            highlight=not args.no_highlight,
        )
    if args.action == "create-api-key":
        if not args.name.strip():
            parser.error("--name is required for 'create-api-key'")
        if not args.scope:
            parser.error("at least one --scope is required for 'create-api-key'")
        return _create_api_key_action(args)
    return _status_stack(config)


if __name__ == "__main__":
    raise SystemExit(main())
