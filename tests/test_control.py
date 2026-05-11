from __future__ import annotations

from pathlib import Path

from llmnode.control import RuntimeConfig, _build_vllm_spec, _default_python_bin, _probe_process_state, _resolve_log_targets, _tail_lines, build_parser


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
        vllm_url="http://127.0.0.1:8000/v1/models",
        web_console_dir=tmp_path / "web-console",
        web_console_port=5173,
        web_console_url="http://127.0.0.1:5173",
        web_console_log_file=log_dir / "web-console.log",
        model_dir=str(tmp_path / "models"),
        python_bin="/tmp/fake-python",
        gateway_pid_file=run_dir / "gateway.pid",
        agent_pid_file=run_dir / "agent.pid",
        web_pid_file=run_dir / "web-console.pid",
        vllm_logger_pid_file=run_dir / "qwen36-vllm.logger.pid",
        vllm_latest_log_link=log_dir / "qwen36-vllm.latest.log",
        gateway_log_file=log_dir / "gateway.log",
        agent_log_file=log_dir / "agent.log",
        vllm_container_name="qwen36-vllm",
        vllm_image_name="vllm/vllm-openai:nightly",
        vllm_model_name="qwen36-35b-a3b",
        vllm_host_port=8000,
        vllm_gpu_memory_utilization=0.6,
        vllm_tensor_parallel_size=1,
        vllm_max_model_len=262144,
        vllm_max_num_seqs=4,
        vllm_shm_size="16g",
        vllm_enable_auto_tool_choice=True,
        vllm_reasoning_parser="qwen3",
        vllm_tool_call_parser="qwen3_coder",
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


def test_build_vllm_spec_uses_runtime_config(tmp_path: Path):
    config = make_runtime_config(tmp_path)
    spec = _build_vllm_spec(config)
    assert spec.container_name == "qwen36-vllm"
    assert spec.model_dir == config.model_dir
    assert spec.host_port == 8000


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
