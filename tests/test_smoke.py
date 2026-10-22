from pathlib import Path

import yaml

import llmnode.config as config_module
from llmnode.config import load_settings
from llmnode.models import load_model_catalog


def _repo_active_profile_payload() -> tuple[str, dict]:
    defaults = yaml.safe_load(Path("config/defaults.yaml").read_text(encoding="utf-8"))
    active_profile = defaults["active_backend_profile"]
    profile = yaml.safe_load(Path(f"config/backends/{active_profile}.yaml").read_text(encoding="utf-8"))
    return active_profile, profile["backend"]


def test_model_catalog_loads():
    active_profile, backend = _repo_active_profile_payload()
    catalog = load_model_catalog()
    assert list(catalog) == [backend["model_name"]]
    assert catalog[backend["model_name"]].backend_type == backend["backend_type"]


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


def test_settings_loads_repo_active_profile_defaults():
    active_profile, backend = _repo_active_profile_payload()
    settings = load_settings()
    assert settings.active_backend_profile == active_profile
    assert settings.vllm.backend_type == backend["backend_type"]
    assert settings.vllm.model_dir.endswith(backend["model_dir"])
    assert settings.vllm.model_name == backend["model_name"]
    assert settings.sqlite_retention.as_dict() == {
        "request_logs": 30,
        "request_metrics": 90,
        "agent_events": 30,
        "response_states": 7,
    }


def test_settings_missing_defaults_file_falls_back_to_repo_active_profile(tmp_path: Path):
    active_profile, backend = _repo_active_profile_payload()
    settings = load_settings(tmp_path / "missing-defaults.yaml")
    assert settings.active_backend_profile == active_profile
    assert settings.gateway.backend_model == backend["model_name"]
    assert settings.vllm.backend_type == backend["backend_type"]
    assert settings.vllm.model_dir.endswith(backend["model_dir"])
    assert settings.vllm.model_name == backend["model_name"]
    assert settings.vllm.host_port == backend["host_port"]


def test_settings_default_resource_setting_matches_active_profile():
    _, backend = _repo_active_profile_payload()
    settings = load_settings()
    if backend["backend_type"] == "llama.cpp":
        assert settings.vllm.n_gpu_layers == backend["n_gpu_layers"]
    else:
        assert settings.vllm.gpu_memory_utilization == backend["gpu_memory_utilization"]


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


def test_settings_local_profile_missing_fields_fall_back_to_same_repo_profile(tmp_path: Path, monkeypatch):
    repo_defaults = tmp_path / "repo-defaults.yaml"
    repo_backends = tmp_path / "repo-backends"
    repo_backends.mkdir()
    repo_defaults.write_text("active_backend_profile: vllm_repo_default\n", encoding="utf-8")
    (repo_backends / "vllm_repo_default.yaml").write_text(
        "backend:\n"
        "  backend_type: vllm\n"
        "  container_name: repo-default-vllm\n"
        "  image_name: vllm/vllm-openai:nightly\n"
        "  model_dir: models/Qwen/RepoDefault\n"
        "  model_file: \"\"\n"
        "  model_name: repo-default-model\n"
        "  display_name: Repo Default Model\n"
        "  host_port: 18888\n",
        encoding="utf-8",
    )
    (repo_backends / "llama.cpp_demo.yaml").write_text(
        "backend:\n"
        "  backend_type: llama.cpp\n"
        "  container_name: repo-demo-llamacpp\n"
        "  image_name: ghcr.io/ggml-org/llama.cpp:full-cuda\n"
        "  model_dir: models/Qwen/RepoDemo\n"
        "  model_file: repo-demo.gguf\n"
        "  model_name: repo-demo-model\n"
        "  display_name: Repo Demo Model\n"
        "  host_port: 17777\n"
        "  ctx_size: 65536\n"
        "  n_parallel: 2\n",
        encoding="utf-8",
    )

    local_defaults = tmp_path / "local-defaults.yaml"
    local_backends = tmp_path / "backends"
    local_backends.mkdir()
    local_defaults.write_text("active_backend_profile: llama.cpp_demo\n", encoding="utf-8")
    (local_backends / "llama.cpp_demo.yaml").write_text(
        "backend:\n"
        "  backend_type: llama.cpp\n"
        "  host_port: 16666\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(config_module, "DEFAULTS_FILE", repo_defaults)
    monkeypatch.setattr(config_module, "BACKENDS_DIR", repo_backends)

    settings = load_settings(local_defaults)

    assert settings.active_backend_profile == "llama.cpp_demo"
    assert settings.gateway.backend_model == "repo-demo-model"
    assert settings.vllm.backend_type == "llama.cpp"
    assert settings.vllm.container_name == "repo-demo-llamacpp"
    assert settings.vllm.model_file == "repo-demo.gguf"
    assert settings.vllm.model_name == "repo-demo-model"
    assert settings.vllm.host_port == 16666


def test_settings_load_repo_awq_int4_profile(tmp_path: Path):
    defaults = tmp_path / "defaults.yaml"
    defaults.write_text("active_backend_profile: vllm_qwen36-27b-awq-int4\n", encoding="utf-8")

    profile_settings = load_settings(defaults)
    assert profile_settings.active_backend_profile == "vllm_qwen36-27b-awq-int4"
    assert profile_settings.vllm.backend_type == "vllm"
    assert profile_settings.vllm.model_dir.endswith("models/Qwen/Qwen3.6-27B-AWQ-INT4")
    assert profile_settings.vllm.model_name == "qwen36-27b-awq-int4"
    assert profile_settings.vllm.gpu_memory_utilization == 0.55
    assert profile_settings.gateway.backend_model == "qwen36-27b-awq-int4"


def test_settings_loads_current_repo_active_profile():
    settings = load_settings()

    active_profile, backend = _repo_active_profile_payload()
    assert settings.active_backend_profile == active_profile
    assert settings.vllm.backend_type == backend["backend_type"]
    assert settings.vllm.model_name == backend["model_name"]


def test_settings_load_qwen38_dflash_profile_with_draft_mount(tmp_path: Path):
    defaults = tmp_path / "defaults.yaml"
    defaults.write_text(
        "active_backend_profile: vllm_qwen38-27b-awq-int4-dflash2\n",
        encoding="utf-8",
    )

    settings = load_settings(defaults)

    assert settings.vllm.speculative_model_dir.endswith("models/Qwen/Qwen3.8-27B-DFlash2")
    assert settings.vllm.speculative_config == (
        '{"method":"dflash","model":"/draft-model","num_speculative_tokens":7}'
    )


def test_settings_load_qwen38_nvfp4_mtp_profiles(tmp_path: Path):
    for tokens in (3, 7):
        defaults = tmp_path / f"defaults-{tokens}.yaml"
        defaults.write_text(
            f"active_backend_profile: vllm_qwen38-27b-nvfp4-mtp{tokens}\n",
            encoding="utf-8",
        )

        settings = load_settings(defaults)

        assert settings.vllm.model_dir.endswith("models/Qwen/Qwen3.8-27B-NVFP4")
        assert settings.vllm.speculative_config == (
            f'{{"method":"mtp","num_speculative_tokens":{tokens}}}'
        )
        assert settings.vllm.disabled_kernels == "HummingFP8ScaledMMLinearKernel"


def test_settings_load_repo_deepseek_v4_q8_llamacpp_profile(tmp_path: Path):
    defaults = tmp_path / "defaults.yaml"
    defaults.write_text(
        "active_backend_profile: llama.cpp_deepseek-v4-flash-0731-ud-q8-k-xl\n",
        encoding="utf-8",
    )

    profile_settings = load_settings(defaults)

    assert profile_settings.vllm.backend_type == "llama.cpp"
    assert profile_settings.vllm.image_name == "ghcr.io/ggml-org/llama.cpp:server-cuda"
    assert profile_settings.vllm.model_dir.endswith(
        "models/deepseek/unsloth/DeepSeek-V4-Flash-0731-GGUF/UD-Q8_K_XL"
    )
    assert profile_settings.vllm.model_file == (
        "DeepSeek-V4-Flash-0731-UD-Q8_K_XL-00001-of-00005.gguf"
    )
    assert profile_settings.vllm.model_name == "deepseek-v4-flash-0731-ud-q8-k-xl"
    assert profile_settings.vllm.n_gpu_layers == 16
    assert profile_settings.vllm.ctx_size == 16384
    assert profile_settings.vllm.n_parallel == 1
    assert profile_settings.gateway.backend_model == "deepseek-v4-flash-0731-ud-q8-k-xl"


def test_settings_load_repo_awq_int4_profiler_profile(tmp_path: Path):
    defaults = tmp_path / "defaults.yaml"
    defaults.write_text("active_backend_profile: vllm_qwen36-27b-awq-int4-profiler\n", encoding="utf-8")

    profile_settings = load_settings(defaults)
    assert profile_settings.active_backend_profile == "vllm_qwen36-27b-awq-int4-profiler"
    assert profile_settings.vllm.container_name == "qwen36-27b-awq-int4-profiler-vllm"
    assert profile_settings.vllm.profiler_config == '{"profiler":"torch","torch_profiler_dir":"/tmp/vllm-profile"}'
    assert profile_settings.vllm.profiler_host_dir.endswith("runtime/data/profiles/stage4-awq-profiler")


def test_settings_load_repo_awq_int4_fp8_kv_profile(tmp_path: Path):
    defaults = tmp_path / "defaults.yaml"
    defaults.write_text("active_backend_profile: vllm_qwen36-27b-awq-int4-fp8-kv\n", encoding="utf-8")

    profile_settings = load_settings(defaults)
    assert profile_settings.active_backend_profile == "vllm_qwen36-27b-awq-int4-fp8-kv"
    assert profile_settings.vllm.container_name == "qwen36-27b-awq-int4-fp8-kv-vllm"
    assert profile_settings.vllm.model_dir.endswith("models/Qwen/Qwen3.6-27B-AWQ-INT4")
    assert profile_settings.vllm.model_name == "qwen36-27b-awq-int4"
    assert profile_settings.vllm.kv_cache_dtype == "fp8"


def test_settings_load_repo_nvfp4_profiler_profile(tmp_path: Path):
    defaults = tmp_path / "defaults.yaml"
    defaults.write_text("active_backend_profile: vllm_qwen36-27b-nvfp4-profiler\n", encoding="utf-8")

    profile_settings = load_settings(defaults)
    assert profile_settings.active_backend_profile == "vllm_qwen36-27b-nvfp4-profiler"
    assert profile_settings.vllm.container_name == "qwen36-27b-nvfp4-profiler-vllm"
    assert profile_settings.vllm.model_dir.endswith("models/Qwen/Qwen3.6-27B-NVFP4")
    assert profile_settings.vllm.model_name == "qwen36-27b-nvfp4"
    assert profile_settings.vllm.profiler_config == '{"profiler":"torch","torch_profiler_dir":"/tmp/vllm-profile"}'
    assert profile_settings.vllm.profiler_host_dir.endswith("runtime/data/profiles/stage6-nvfp4-profiler")


def test_settings_load_repo_nvfp4_profile(tmp_path: Path, monkeypatch):
    defaults = tmp_path / "defaults.yaml"
    defaults.write_text("active_backend_profile: vllm_qwen36-27b-nvfp4\n", encoding="utf-8")
    monkeypatch.delenv("VLLM_CLAUDE_VLLM_GPU_MEMORY_UTILIZATION", raising=False)

    profile_settings = load_settings(defaults)
    assert profile_settings.active_backend_profile == "vllm_qwen36-27b-nvfp4"
    assert profile_settings.vllm.backend_type == "vllm"
    assert profile_settings.vllm.model_dir.endswith("models/Qwen/Qwen3.6-27B-NVFP4")
    assert profile_settings.vllm.model_name == "qwen36-27b-nvfp4"
    assert profile_settings.vllm.display_name == "Qwen3.6 27B NVFP4"
    assert profile_settings.vllm.max_model_len == 262144
    assert profile_settings.vllm.gpu_memory_utilization == 0.6
    assert profile_settings.vllm.kv_cache_dtype == ""
    assert profile_settings.gateway.backend_model == "qwen36-27b-nvfp4"
