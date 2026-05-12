from __future__ import annotations

import argparse
import os
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
    print(f"  {name:<18} {status:<12} {detail}")


def _http_ok(url: str, method: str = "GET") -> bool:
    request = Request(url, method=method)
    try:
        with urlopen(request, timeout=2):
            return True
    except Exception:
        return False


def _http_post(url: str) -> None:
    request = Request(url, data=b"", method="POST")
    with urlopen(request, timeout=10):
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
    if _web_console_matches_project(config):
        adopted_pid = _adopt_web_console_pid_if_needed(config)
        if adopted_pid:
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
            env=os.environ.copy(),
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

    gateway_http_state = "ok" if _http_ok(f"{config.gateway_url}/health/liveliness") else "unreachable"
    agent_http_state = "ok" if _http_ok(f"{config.agent_url}/state") else "unreachable"
    backend_http_state = "ok" if _http_ok(config.backend_url) else "unreachable"
    web_console_http_state = "ok" if _http_ok(config.web_console_url) else "unreachable"

    stack_state = "partial"
    stack_detail = "Some services are available, but the stack is not fully ready yet."
    if all(state == "unreachable" for state in (gateway_http_state, agent_http_state, backend_http_state, web_console_http_state)):
        stack_state = "stopped"
        stack_detail = "No managed services are currently reachable."
    elif all(state == "ok" for state in (gateway_http_state, agent_http_state, backend_http_state, web_console_http_state)):
        stack_state = "ready"
        stack_detail = f"Gateway, agent, {config.backend_type}, and web-console are all reachable."
    elif gateway_http_state == "ok" and agent_http_state == "ok" and web_console_http_state == "ok" and backend_http_state == "unreachable":
        stack_state = "warming"
        stack_detail = f"Control plane is up, and {config.backend_type} is still warming up or loading the model."

    _print_header("summary")
    _print_kv("stack_state", stack_state)
    _print_kv("detail", stack_detail)

    _print_header("http health")
    _print_kv("gateway_http", f"{gateway_http_state} ({config.gateway_url}/health/liveliness)")
    _print_kv("agent_http", f"{agent_http_state} ({config.agent_url}/state)")
    _print_kv("backend_http", f"{backend_http_state} ({config.backend_url})")
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

    _print_header("docker state")
    if _command_exists("docker"):
        backend_container_state = "running" if _docker_container_running(config.backend_container_name) else (
            "present" if _docker_container_exists(config.backend_container_name) else "missing"
        )
        _print_check(
            "backend_container",
            backend_container_state,
            config.backend_container_name,
        )
        backend_image_state = "ok" if _run_command_capture(["docker", "image", "inspect", config.backend_image_name]).returncode == 0 else "missing"
        _print_check("backend_image", backend_image_state, config.backend_image_name)
    else:
        backend_container_state = "unknown"
        backend_image_state = "unknown"
        _print_check("backend_container", "unknown", "docker unavailable")
        _print_check("backend_image", "unknown", "docker unavailable")

    suggestions: list[str] = []
    if not (config.web_console_dir / "node_modules").is_dir():
        suggestions.append("安装前端依赖：cd web-console && npm install")
    if not _command_exists("docker"):
        suggestions.append("安装并启动 Docker，确认 `docker --version` 可用")
    elif backend_image_state == "missing":
        suggestions.append(f"准备后端镜像：docker pull {config.backend_image_name}")
    if not Path(config.model_dir).is_dir():
        suggestions.append(f"检查模型目录是否存在：{config.model_dir}")
    if not _http_ok(f"{config.agent_url}/state") and not _http_ok(f"{config.gateway_url}/health/liveliness"):
        suggestions.append("尝试启动整栈：python -m llmnode.control start")
    elif not _http_ok(config.backend_url):
        suggestions.append(f"查看后端暖机日志：python -m llmnode.control logs --target vllm --lines 50")
    if not _http_ok(config.web_console_url) and (config.web_console_dir / "node_modules").is_dir():
        suggestions.append("单独查看前端日志：python -m llmnode.control logs --target web-console --lines 50")

    _print_header("suggestions")
    if suggestions:
        for index, item in enumerate(suggestions, start=1):
            print(f"  {index}. {item}")
    else:
        _print_info("next", "No obvious setup gaps detected. Use status/logs for deeper inspection.")
    return 0


def _resolve_log_targets(config: RuntimeConfig, target: str) -> list[tuple[str, Path]]:
    targets: list[tuple[str, Path]] = [
        ("agent", config.agent_log_file),
        ("gateway", config.gateway_log_file),
        ("web-console", config.web_console_log_file),
    ]
    targets.append(("vllm", config.backend_latest_log_link))

    if target == "all":
        return targets
    normalized = {name: path for name, path in targets}
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


def _logs(config: RuntimeConfig, target: str, lines: int) -> int:
    _print_header("llmnode logs")
    _print_kv("target", target)
    _print_kv("lines", str(lines))
    for name, path in _resolve_log_targets(config, target):
        _print_header(f"log:{name}")
        resolved = path.resolve(strict=False) if path.is_symlink() else path
        _print_kv("path", str(resolved))
        if not path.exists() and not path.is_symlink():
            _print_warn("log file is missing")
            continue
        content = _tail_lines(path, lines)
        if not content:
            _print_info("content", "log file is empty")
            continue
        for line in content:
            print(f"  {line}")
    return 0


def _stop_stack(config: RuntimeConfig) -> int:
    _print_header("llmnode stop")
    if _http_ok(f"{config.agent_url}/health/liveliness"):
        _print_step(f"requesting {config.backend_type} stop through agent")
        try:
            _http_post(f"{config.agent_url}/manage/stop")
        except Exception:
            pass
        _print_success(f"{config.backend_type} stop requested through agent")
    else:
        _print_step(f"stopping {config.backend_type} directly")
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
    started = False
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
        started = True
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

        _print_header("stack ready")
        _print_kv("gateway", config.gateway_url)
        _print_kv("agent", config.agent_url)
        _print_kv("web_console", config.web_console_url)
        _print_kv("next", "Run 'python -m llmnode.control status' for a full health summary")
        return 0
    except Exception as exc:
        if started:
            _print_error("Startup failed; cleaning up started services")
            _stop_stack(config)
        _print_error(str(exc))
        return 1


def _restart_stack(config: RuntimeConfig) -> int:
    _print_header("llmnode restart")
    _print_info("action", "stop current stack, then start again")
    _stop_stack(config)
    return _start_stack(config)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m llmnode.control")
    parser.add_argument("action", choices=["start", "stop", "restart", "status", "doctor", "env", "logs"], nargs="?", default="status")
    parser.add_argument("--service", choices=["agent", "gateway", "vllm"])
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--foreground", action="store_true")
    parser.add_argument("--target", choices=["agent", "gateway", "web-console", "vllm", "all"], default="all")
    parser.add_argument("--lines", type=int, default=20)
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
        return _restart_stack(config)
    if args.action == "doctor":
        return _doctor(config)
    if args.action == "env":
        return _env_report(config)
    if args.action == "logs":
        return _logs(config, args.target, max(args.lines, 0))
    return _status_stack(config)


if __name__ == "__main__":
    raise SystemExit(main())
