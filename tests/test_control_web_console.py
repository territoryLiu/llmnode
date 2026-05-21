from pathlib import Path

from llmnode.control import RuntimeConfig, _create_admin_key, _ensure_web_console_api_key, _ensure_web_console_static_dist, _web_console_has_expected_proxy_env
from llmnode.storage.db import init_db


def test_web_console_proxy_env_check_rejects_missing_env(monkeypatch, tmp_path: Path):
    environ_file = tmp_path / "environ"
    environ_file.write_bytes(b"PATH=/usr/bin\0VITE_API_PROXY_TARGET=http://127.0.0.1:4000\0")

    def fake_exists(self: Path) -> bool:
        if str(self).startswith("/proc/1234/environ"):
            return True
        return Path.exists(self)

    def fake_read_bytes(self: Path) -> bytes:
        if str(self).startswith("/proc/1234/environ"):
            return environ_file.read_bytes()
        return Path.read_bytes(self)

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "read_bytes", fake_read_bytes)

    assert _web_console_has_expected_proxy_env("1234", "http://127.0.0.1:4000") is False


def test_web_console_proxy_env_check_rejects_wrong_proxy_key(monkeypatch, tmp_path: Path):
    environ_file = tmp_path / "environ"
    environ_file.write_bytes(
        b"PATH=/usr/bin\0"
        b"VITE_API_PROXY_TARGET=http://127.0.0.1:4000\0"
        b"VITE_API_PROXY_KEY=sk-stale-console-key\0"
    )

    def fake_read_bytes(self: Path) -> bytes:
        if str(self).startswith("/proc/1234/environ"):
            return environ_file.read_bytes()
        return Path.read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", fake_read_bytes)

    assert _web_console_has_expected_proxy_env("1234", "http://127.0.0.1:4000", "sk-current-console-key") is False


def test_ensure_web_console_api_key_reads_admin_key_from_db(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    data_dir = runtime_dir / "data"
    data_dir.mkdir(parents=True)
    db = init_db(data_dir / "gateway.db")
    row, secret = _create_admin_key(db)
    assert row["name"] == "admin"

    config = RuntimeConfig(
        project_dir=tmp_path,
        runtime_dir=runtime_dir,
        log_dir=tmp_path / "logs",
        run_dir=tmp_path / "run",
        gateway_url="http://127.0.0.1:4000",
        agent_url="http://127.0.0.1:4010",
        backend_url="http://127.0.0.1:15673/v1/models",
        web_console_dir=tmp_path / "web-console",
        web_console_port=5173,
        web_console_url="http://127.0.0.1:5173",
        web_console_static_url="http://127.0.0.1:4000/console/",
        web_console_dist_dir=tmp_path / "web-console" / "dist",
        web_console_log_file=tmp_path / "logs" / "web-console.log",
        web_console_system_key_name="Web Console",
        model_dir="model",
        python_bin="python",
        gateway_pid_file=tmp_path / "run" / "gateway.pid",
        agent_pid_file=tmp_path / "run" / "agent.pid",
        web_pid_file=tmp_path / "run" / "web.pid",
        backend_logger_pid_file=tmp_path / "run" / "backend-logger.pid",
        backend_latest_log_link=tmp_path / "logs" / "backend.latest.log",
        gateway_log_file=tmp_path / "logs" / "gateway.log",
        agent_log_file=tmp_path / "logs" / "agent.log",
        backend_type="vllm",
        backend_container_name="container",
        backend_image_name="image",
        backend_model_name="model",
        backend_host_port=15673,
        backend_shm_size="8g",
        vllm_gpu_memory_utilization=0.5,
        vllm_tensor_parallel_size=1,
        vllm_max_model_len=1024,
        vllm_max_num_seqs=4,
        vllm_enable_auto_tool_choice=False,
        vllm_reasoning_parser="qwen3",
        vllm_tool_call_parser="qwen3_coder",
        llamacpp_model_file="",
        llamacpp_n_gpu_layers=0,
        llamacpp_ctx_size=0,
        llamacpp_n_parallel=1,
        sglang_tp_size=1,
        sglang_mem_fraction_static=0.5,
        sglang_max_running_requests=4,
        sglang_reasoning_parser="qwen3",
    )

    import os
    previous = os.environ.get("VLLM_CLAUDE_DB_PATH")
    os.environ["VLLM_CLAUDE_DB_PATH"] = str(data_dir / "gateway.db")
    try:
        loaded = _ensure_web_console_api_key(config)
    finally:
        if previous is None:
            os.environ.pop("VLLM_CLAUDE_DB_PATH", None)
        else:
            os.environ["VLLM_CLAUDE_DB_PATH"] = previous
    assert loaded == secret


def test_ensure_web_console_static_dist_skips_existing_dist(tmp_path: Path, monkeypatch):
    config = RuntimeConfig(
        project_dir=tmp_path,
        runtime_dir=tmp_path / "runtime",
        log_dir=tmp_path / "logs",
        run_dir=tmp_path / "run",
        gateway_url="http://127.0.0.1:4000",
        agent_url="http://127.0.0.1:4010",
        backend_url="http://127.0.0.1:15673/v1/models",
        web_console_dir=tmp_path / "web-console",
        web_console_port=5173,
        web_console_url="http://127.0.0.1:5173",
        web_console_static_url="http://127.0.0.1:4000/console/",
        web_console_dist_dir=tmp_path / "web-console" / "dist",
        web_console_log_file=tmp_path / "logs" / "web-console.log",
        web_console_system_key_name="Web Console",
        model_dir="model",
        python_bin="python",
        gateway_pid_file=tmp_path / "run" / "gateway.pid",
        agent_pid_file=tmp_path / "run" / "agent.pid",
        web_pid_file=tmp_path / "run" / "web.pid",
        backend_logger_pid_file=tmp_path / "run" / "backend-logger.pid",
        backend_latest_log_link=tmp_path / "logs" / "backend.latest.log",
        gateway_log_file=tmp_path / "logs" / "gateway.log",
        agent_log_file=tmp_path / "logs" / "agent.log",
        backend_type="vllm",
        backend_container_name="container",
        backend_image_name="image",
        backend_model_name="model",
        backend_host_port=15673,
        backend_shm_size="8g",
        vllm_gpu_memory_utilization=0.5,
        vllm_tensor_parallel_size=1,
        vllm_max_model_len=1024,
        vllm_max_num_seqs=4,
        vllm_enable_auto_tool_choice=False,
        vllm_reasoning_parser="qwen3",
        vllm_tool_call_parser="qwen3_coder",
        llamacpp_model_file="",
        llamacpp_n_gpu_layers=0,
        llamacpp_ctx_size=0,
        llamacpp_n_parallel=1,
        sglang_tp_size=1,
        sglang_mem_fraction_static=0.5,
        sglang_max_running_requests=4,
        sglang_reasoning_parser="qwen3",
    )
    config.web_console_dist_dir.mkdir(parents=True)
    (config.web_console_dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    build_calls: list[list[str]] = []

    monkeypatch.setattr("llmnode.control._run_command_capture", lambda command, cwd=None, env=None: build_calls.append(command))

    _ensure_web_console_static_dist(config)

    assert build_calls == []


def test_ensure_web_console_static_dist_builds_missing_dist(tmp_path: Path, monkeypatch):
    config = RuntimeConfig(
        project_dir=tmp_path,
        runtime_dir=tmp_path / "runtime",
        log_dir=tmp_path / "logs",
        run_dir=tmp_path / "run",
        gateway_url="http://127.0.0.1:4000",
        agent_url="http://127.0.0.1:4010",
        backend_url="http://127.0.0.1:15673/v1/models",
        web_console_dir=tmp_path / "web-console",
        web_console_port=5173,
        web_console_url="http://127.0.0.1:5173",
        web_console_static_url="http://127.0.0.1:4000/console/",
        web_console_dist_dir=tmp_path / "web-console" / "dist",
        web_console_log_file=tmp_path / "logs" / "web-console.log",
        web_console_system_key_name="Web Console",
        model_dir="model",
        python_bin="python",
        gateway_pid_file=tmp_path / "run" / "gateway.pid",
        agent_pid_file=tmp_path / "run" / "agent.pid",
        web_pid_file=tmp_path / "run" / "web.pid",
        backend_logger_pid_file=tmp_path / "run" / "backend-logger.pid",
        backend_latest_log_link=tmp_path / "logs" / "backend.latest.log",
        gateway_log_file=tmp_path / "logs" / "gateway.log",
        agent_log_file=tmp_path / "logs" / "agent.log",
        backend_type="vllm",
        backend_container_name="container",
        backend_image_name="image",
        backend_model_name="model",
        backend_host_port=15673,
        backend_shm_size="8g",
        vllm_gpu_memory_utilization=0.5,
        vllm_tensor_parallel_size=1,
        vllm_max_model_len=1024,
        vllm_max_num_seqs=4,
        vllm_enable_auto_tool_choice=False,
        vllm_reasoning_parser="qwen3",
        vllm_tool_call_parser="qwen3_coder",
        llamacpp_model_file="",
        llamacpp_n_gpu_layers=0,
        llamacpp_ctx_size=0,
        llamacpp_n_parallel=1,
        sglang_tp_size=1,
        sglang_mem_fraction_static=0.5,
        sglang_max_running_requests=4,
        sglang_reasoning_parser="qwen3",
    )
    config.web_console_dir.mkdir(parents=True)
    (config.web_console_dir / "node_modules").mkdir()
    build_calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = "built"
        stderr = ""

    monkeypatch.setattr("llmnode.control.shutil.which", lambda name: "/usr/bin/npm" if name == "npm" else None)
    def fake_run_command_capture(command, cwd=None, env=None):
        build_calls.append(command)
        config.web_console_dist_dir.mkdir(parents=True)
        (config.web_console_dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")
        return Result()

    monkeypatch.setattr("llmnode.control._run_command_capture", fake_run_command_capture)

    _ensure_web_console_static_dist(config)

    assert build_calls == [["npm", "run", "build"]]


def test_static_dist_uses_console_asset_base(tmp_path: Path, monkeypatch):
    config = RuntimeConfig(
        project_dir=tmp_path,
        runtime_dir=tmp_path / "runtime",
        log_dir=tmp_path / "logs",
        run_dir=tmp_path / "run",
        gateway_url="http://127.0.0.1:4000",
        agent_url="http://127.0.0.1:4010",
        backend_url="http://127.0.0.1:15673/v1/models",
        web_console_dir=tmp_path / "web-console",
        web_console_port=5173,
        web_console_url="http://127.0.0.1:5173",
        web_console_static_url="http://127.0.0.1:4000/console/",
        web_console_dist_dir=tmp_path / "web-console" / "dist",
        web_console_log_file=tmp_path / "logs" / "web-console.log",
        web_console_system_key_name="Web Console",
        model_dir="model",
        python_bin="python",
        gateway_pid_file=tmp_path / "run" / "gateway.pid",
        agent_pid_file=tmp_path / "run" / "agent.pid",
        web_pid_file=tmp_path / "run" / "web.pid",
        backend_logger_pid_file=tmp_path / "run" / "backend-logger.pid",
        backend_latest_log_link=tmp_path / "logs" / "backend.latest.log",
        gateway_log_file=tmp_path / "logs" / "gateway.log",
        agent_log_file=tmp_path / "logs" / "agent.log",
        backend_type="vllm",
        backend_container_name="container",
        backend_image_name="image",
        backend_model_name="model",
        backend_host_port=15673,
        backend_shm_size="8g",
        vllm_gpu_memory_utilization=0.5,
        vllm_tensor_parallel_size=1,
        vllm_max_model_len=1024,
        vllm_max_num_seqs=4,
        vllm_enable_auto_tool_choice=False,
        vllm_reasoning_parser="qwen3",
        vllm_tool_call_parser="qwen3_coder",
        llamacpp_model_file="",
        llamacpp_n_gpu_layers=0,
        llamacpp_ctx_size=0,
        llamacpp_n_parallel=1,
        sglang_tp_size=1,
        sglang_mem_fraction_static=0.5,
        sglang_max_running_requests=4,
        sglang_reasoning_parser="qwen3",
    )
    config.web_console_dir.mkdir(parents=True)
    (config.web_console_dir / "node_modules").mkdir()

    class Result:
        returncode = 0
        stdout = "built"
        stderr = ""

    monkeypatch.setattr("llmnode.control.shutil.which", lambda name: "/usr/bin/npm" if name == "npm" else None)

    def fake_run_command_capture(command, cwd=None, env=None):
        config.web_console_dist_dir.mkdir(parents=True)
        (config.web_console_dist_dir / "assets").mkdir()
        (config.web_console_dist_dir / "index.html").write_text(
            '<script type="module" src="/console/assets/index.js"></script>',
            encoding="utf-8",
        )
        return Result()

    monkeypatch.setattr("llmnode.control._run_command_capture", fake_run_command_capture)

    _ensure_web_console_static_dist(config)

    built = (config.web_console_dist_dir / "index.html").read_text(encoding="utf-8")
    assert "/console/assets/" in built
