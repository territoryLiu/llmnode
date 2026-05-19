from pathlib import Path

from llmnode.control import RuntimeConfig, _ensure_web_console_api_key, _web_console_has_expected_proxy_env
from llmnode.security import hash_api_key
from llmnode.storage.db import create_api_key, init_db


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


def test_ensure_web_console_api_key_recovers_existing_named_key_without_secret_file(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    data_dir = runtime_dir / "data"
    data_dir.mkdir(parents=True)
    db = init_db(data_dir / "gateway.db")
    create_api_key(
        db,
        name="Web Console",
        key_hash=hash_api_key("sk-old-console"),
        scopes=["admin", "inference"],
        note="legacy",
    )

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

    secret = _ensure_web_console_api_key(config)
    assert secret.startswith("sk-")
    assert (runtime_dir / "data" / "web-console-admin.key").exists()
