from __future__ import annotations

from pathlib import Path

from llmnode.control import RuntimeConfig, _build_backend_spec, _default_python_bin, _probe_process_state, _resolve_log_targets, _restart_without_backend, _tail_lines, build_parser


def make_runtime_config(tmp_path: Path) -> RuntimeConfig:
    runtime_dir = tmp_path / "runtime"
    log_dir = runtime_dir / "logs"
    run_dir = runtime_dir / "run"
    log_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    return RuntimeConfig(
        project_dir=tmp_path,
        runtime_dir=runtime_dir,
        log_dir=log_dir,
        run_dir=run_dir,
        gateway_url="http://127.0.0.1:4000",
        agent_url="http://127.0.0.1:4010",
        backend_url="http://127.0.0.1:15673/v1/models",
        web_console_dir=tmp_path / "web-console",
        web_console_port=5173,
        web_console_url="http://127.0.0.1:5173",
        web_console_log_file=log_dir / "web-console.log",
        web_console_system_key_name="Web Console",
        model_dir=str(tmp_path / "models"),
        python_bin="/tmp/fake-python",
        gateway_pid_file=run_dir / "gateway.pid",
        agent_pid_file=run_dir / "agent.pid",
        web_pid_file=run_dir / "web-console.pid",
        backend_logger_pid_file=run_dir / "qwen36-vllm.logger.pid",
        backend_latest_log_link=log_dir / "qwen36-vllm.latest.log",
        gateway_log_file=log_dir / "gateway.log",
        agent_log_file=log_dir / "agent.log",
        backend_type="vllm",
        backend_container_name="qwen36-vllm",
        backend_image_name="vllm/vllm-openai:nightly",
        backend_model_name="qwen36-35b-a3b-fp8",
        backend_host_port=15673,
        backend_shm_size="16g",
        vllm_gpu_memory_utilization=0.65,
        vllm_tensor_parallel_size=1,
        vllm_max_model_len=262144,
        vllm_max_num_seqs=4,
        vllm_enable_auto_tool_choice=True,
        vllm_reasoning_parser="qwen3",
        vllm_tool_call_parser="qwen3_coder",
        llamacpp_model_file="",
        llamacpp_n_gpu_layers=-1,
        llamacpp_ctx_size=262144,
        llamacpp_n_parallel=4,
        sglang_tp_size=1,
        sglang_mem_fraction_static=0.65,
        sglang_max_running_requests=1,
        sglang_reasoning_parser="qwen3",
    )


def test_control_parser_defaults_to_status():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.action == "status"


def test_control_parser_supports_service_options():
    parser = build_parser()
    args = parser.parse_args(["start", "--service", "agent", "--daemon"])
    assert args.action == "start"
    assert args.service == "agent"
    assert args.daemon is True


def test_control_parser_supports_restart_exclude_backend():
    parser = build_parser()
    args = parser.parse_args(["restart", "--exclude-backend"])
    assert args.action == "restart"
    assert args.exclude_backend is True


def test_control_parser_supports_doctor_action():
    parser = build_parser()
    args = parser.parse_args(["doctor"])
    assert args.action == "doctor"


def test_control_parser_supports_logs_options():
    parser = build_parser()
    args = parser.parse_args(["logs", "--target", "agent", "--lines", "5"])
    assert args.action == "logs"
    assert args.target == "agent"
    assert args.lines == 5


def test_probe_process_state_reports_stopped_for_missing_pid(tmp_path: Path):
    pid_file = tmp_path / "missing.pid"
    probe = _probe_process_state(pid_file, port=None, url=None)
    assert probe["state"] == "stopped"
    assert probe["pid"] == ""


def test_runtime_config_dataclass_accepts_expected_paths(tmp_path: Path):
    config = make_runtime_config(tmp_path)
    assert config.gateway_pid_file.name == "gateway.pid"
    assert config.agent_pid_file.name == "agent.pid"
    assert config.web_pid_file.name == "web-console.pid"


def test_default_python_bin_prefers_configured_env(monkeypatch):
    monkeypatch.setenv("VLLM_CLAUDE_PYTHON_BIN", "/tmp/custom-python")
    assert _default_python_bin() == "/tmp/custom-python"


def test_build_backend_spec_vllm_uses_runtime_config(tmp_path: Path):
    config = make_runtime_config(tmp_path)
    spec = _build_backend_spec(config)
    assert spec.container_name == "qwen36-vllm"
    assert spec.model_dir == config.model_dir
    assert spec.host_port == 15673


def test_build_backend_spec_llamacpp(tmp_path: Path):
    config = make_runtime_config(tmp_path)
    object.__setattr__(config, "backend_type", "llama.cpp") if hasattr(config, "__dataclass_fields__") else None
    from dataclasses import replace
    config = replace(config, backend_type="llama.cpp", llamacpp_model_file="model.gguf")
    spec = _build_backend_spec(config)
    assert spec.container_name == "qwen36-vllm"
    assert spec.model_file == "model.gguf"


def test_build_backend_spec_sglang(tmp_path: Path):
    from dataclasses import replace
    config = make_runtime_config(tmp_path)
    config = replace(config, backend_type="sglang")
    spec = _build_backend_spec(config)
    assert spec.container_name == "qwen36-vllm"
    assert spec.tp_size == 1


def test_tail_lines_returns_last_n_lines(tmp_path: Path):
    log_file = tmp_path / "test.log"
    log_file.write_text("a\nb\nc\nd\n", encoding="utf-8")
    assert _tail_lines(log_file, 2) == ["c", "d"]


def test_resolve_log_targets_supports_all(tmp_path: Path):
    config = make_runtime_config(tmp_path)
    targets = _resolve_log_targets(config, "all")
    names = [name for name, _ in targets]
    assert names == ["agent", "gateway", "web-console", "vllm"]


def test_control_parser_supports_env_action():
    parser = build_parser()
    args = parser.parse_args(["env"])
    assert args.action == "env"


def test_control_parser_supports_create_api_key_action():
    parser = build_parser()
    args = parser.parse_args(["create-api-key", "--name", "console-admin", "--scope", "admin", "--scope", "inference"])
    assert args.action == "create-api-key"
    assert args.name == "console-admin"
    assert args.scope == ["admin", "inference"]


def test_restart_without_backend_restarts_control_plane_only(tmp_path: Path, monkeypatch):
    config = make_runtime_config(tmp_path)
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr("llmnode.control._print_header", lambda *args, **kwargs: None)
    monkeypatch.setattr("llmnode.control._print_info", lambda *args, **kwargs: None)
    monkeypatch.setattr("llmnode.control._print_step", lambda *args, **kwargs: None)
    monkeypatch.setattr("llmnode.control._print_kv", lambda *args, **kwargs: None)
    monkeypatch.setattr("llmnode.control._wait_for_http", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "llmnode.control._adopt_web_console_pid_if_needed",
        lambda *_args, **_kwargs: "",
    )
    monkeypatch.setattr(
        "llmnode.control._stop_pid_file",
        lambda pid_file, label: calls.append(("stop_pid", label)),
    )
    monkeypatch.setattr(
        "llmnode.control._stop_python_service",
        lambda pid_file, label, legacy_pattern: calls.append(("stop_service", label)),
    )
    monkeypatch.setattr(
        "llmnode.control._spawn_python_module",
        lambda _config, module, pid_file, log_file, label: calls.append(("start_service", label)),
    )
    monkeypatch.setattr(
        "llmnode.control._start_web_console",
        lambda _config: calls.append(("start_service", "Web console")),
    )

    result = _restart_without_backend(config)

    assert result == 0
    assert calls == [
        ("stop_pid", "Web console"),
        ("stop_service", "Gateway"),
        ("stop_service", "Node agent"),
        ("start_service", "Node agent"),
        ("start_service", "Gateway"),
        ("start_service", "Web console"),
    ]
