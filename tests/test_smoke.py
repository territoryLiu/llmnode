from llmnode.config import load_settings
from llmnode.models import load_model_catalog


def test_model_catalog_loads():
    catalog = load_model_catalog()
    assert "claude-sonnet-4-5-20250929" in catalog


def test_settings_loads_default_ports():
    settings = load_settings()
    assert settings.gateway.port == 4000
    assert settings.agent.port == 4010


def test_settings_loads_agent_control_defaults():
    settings = load_settings()
    assert settings.gateway.agent_base_url == "http://127.0.0.1:4010"
    assert settings.gateway.agent_status_url == "http://127.0.0.1:4010/state"


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
    assert settings.vllm.backend_type == "vllm"
    assert settings.vllm.model_dir.endswith("models/Qwen/Qwen3.6-35B-A3B-FP8")
    assert settings.vllm.model_name == "qwen36-35b-a3b"
