from pathlib import Path

from llmnode.config import load_settings
from llmnode.models import load_model_catalog


def test_model_catalog_loads():
    catalog = load_model_catalog()
    assert list(catalog) == ["qwen36-35b-a3b-fp8"]
    assert catalog["qwen36-35b-a3b-fp8"].backend_type == "vllm"


def test_settings_loads_default_ports():
    settings = load_settings()
    assert settings.gateway.port == 4000
    assert settings.agent.port == 4010
    assert settings.vllm.host_port == 15673


def test_settings_loads_agent_control_defaults():
    settings = load_settings()
    assert settings.gateway.agent_base_url == "http://127.0.0.1:4010"
    assert settings.gateway.agent_status_url == "http://127.0.0.1:4010/state"
    assert settings.agent.startup_grace_period == 300


def test_settings_loads_schedule_defaults():
    settings = load_settings()
    assert settings.schedule.timezone == "Asia/Shanghai"
    assert settings.schedule.start_time == "09:00"
    assert settings.schedule.end_time == "18:00"


def test_settings_uses_models_directory_for_vllm():
    settings = load_settings()
    assert "/models/" in settings.vllm.model_dir


def test_settings_default_vllm_model_dir_and_name():
    settings = load_settings()
    assert settings.active_backend_profile == "vllm_qwen36-35b-a3b-fp8"
    assert settings.vllm.backend_type == "vllm"
    assert settings.vllm.model_dir.endswith("models/Qwen/Qwen3.6-35B-A3B-FP8")
    assert settings.vllm.model_name == "qwen36-35b-a3b-fp8"


def test_settings_code_defaults_fall_back_to_fp8_when_config_file_is_missing(tmp_path: Path):
    settings = load_settings(tmp_path / "missing-defaults.yaml")
    assert settings.gateway.backend_model == "qwen36-35b-a3b-fp8"
    assert settings.vllm.model_dir.endswith("models/Qwen/Qwen3.6-35B-A3B-FP8")
    assert settings.vllm.model_name == "qwen36-35b-a3b-fp8"
    assert settings.vllm.host_port == 15673


def test_settings_default_gpu_memory_utilization_is_065():
    settings = load_settings()
    assert settings.vllm.gpu_memory_utilization == 0.65


def test_settings_load_active_profile_from_local_backends_directory(tmp_path: Path):
    defaults = tmp_path / "defaults.yaml"
    backends = tmp_path / "backends"
    backends.mkdir()
    defaults.write_text(
        "active_backend_profile: llama.cpp_demo\n"
        "gateway:\n"
        "  port: 4999\n",
        encoding="utf-8",
    )
    (backends / "llama.cpp_demo.yaml").write_text(
        "backend:\n"
        "  backend_type: llama.cpp\n"
        "  container_name: demo-llamacpp\n"
        "  image_name: ghcr.io/ggml-org/llama.cpp:full-cuda\n"
        "  model_dir: models/Qwen/Qwen3.6-35B-A3B-GGUF\n"
        "  model_file: qwen36-35b-a3b-q4km.gguf\n"
        "  model_name: demo-model\n"
        "  display_name: Demo Model\n"
        "  host_port: 16666\n"
        "  ctx_size: 32768\n"
        "  n_parallel: 2\n",
        encoding="utf-8",
    )

    settings = load_settings(defaults)

    assert settings.active_backend_profile == "llama.cpp_demo"
    assert settings.gateway.port == 4999
    assert settings.gateway.backend_url == "http://127.0.0.1:16666"
    assert settings.gateway.backend_model == "demo-model"
    assert settings.vllm.backend_type == "llama.cpp"
    assert settings.vllm.model_file == "qwen36-35b-a3b-q4km.gguf"
    assert settings.vllm.host_port == 16666
