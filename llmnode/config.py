from dataclasses import dataclass
from pathlib import Path
import os

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_FILE = PROJECT_ROOT / "config" / "defaults.yaml"
RUNTIME_DIR = PROJECT_ROOT / "runtime"
DATA_DIR = RUNTIME_DIR / "data"
RUN_DIR = RUNTIME_DIR / "run"
LOG_DIR = RUNTIME_DIR / "logs"
DEFAULT_MODEL_DIR = PROJECT_ROOT / "models" / "Qwen" / "Qwen3.6-35B-A3B"


@dataclass
class GatewaySettings:
    host: str = "0.0.0.0"
    port: int = 4000
    api_key: str = "dev-key"
    backend_url: str = "http://127.0.0.1:8000"
    backend_model: str = "qwen36-35b-a3b"
    agent_base_url: str = "http://127.0.0.1:4010"
    agent_status_url: str = "http://127.0.0.1:4010/state"
    require_agent_ready: bool = False
    queue_limit: int = 8
    execution_limit: int = 1


@dataclass
class AgentSettings:
    host: str = "127.0.0.1"
    port: int = 4010
    state: str = "stopped"
    poll_interval: int = 15
    auto_recover: bool = True
    recovery_threshold: int = 2
    startup_grace_period: int = 300


@dataclass
class ScheduleSettings:
    timezone: str = "Asia/Shanghai"
    work_days: list[str] | None = None
    start_time: str = "09:00"
    end_time: str = "18:00"
    auto_stop_enabled: bool = True
    auto_start_enabled: bool = True
    cooldown_minutes: int = 10


@dataclass
class BackendSettings:
    backend_type: str = "vllm"
    container_name: str = "qwen36-vllm"
    image_name: str = "vllm/vllm-openai:nightly"
    model_dir: str = str(DEFAULT_MODEL_DIR)
    model_file: str = ""
    model_name: str = "qwen36-35b-a3b"
    host_port: int = 8000
    gpu_memory_utilization: float = 0.6
    tensor_parallel_size: int = 1
    max_model_len: int = 262144
    max_num_seqs: int = 4
    shm_size: str = "16g"
    enable_auto_tool_choice: bool = True
    reasoning_parser: str = "qwen3"
    tool_call_parser: str = "qwen3_coder"
    n_gpu_layers: int = -1
    ctx_size: int = 4096
    n_parallel: int = 1
    mem_fraction_static: float = 0.9
    max_running_requests: int = 4



@dataclass
class AppSettings:
    gateway: GatewaySettings
    agent: AgentSettings
    schedule: ScheduleSettings
    vllm: BackendSettings


def load_settings(path: Path | None = None) -> AppSettings:
    file_path = path or DEFAULTS_FILE
    data = yaml.safe_load(file_path.read_text()) if file_path.exists() else {}
    data = data or {}
    gateway = data.get("gateway", {})
    agent = data.get("agent", {})
    schedule = data.get("schedule", {})
    vllm = data.get("vllm", {})

    def _resolve_path(value: str | Path | None, default: Path) -> str:
        raw = Path(str(value or default))
        if raw.is_absolute():
            return str(raw)
        return str((PROJECT_ROOT / raw).resolve())

    return AppSettings(
        gateway=GatewaySettings(
            host=os.getenv("VLLM_CLAUDE_GATEWAY_HOST", gateway.get("host", "0.0.0.0")),
            port=int(os.getenv("VLLM_CLAUDE_GATEWAY_PORT", gateway.get("port", 4000))),
            api_key=os.getenv("VLLM_CLAUDE_GATEWAY_KEY", gateway.get("api_key", "dev-key")),
            backend_url=os.getenv("VLLM_CLAUDE_BACKEND_URL", gateway.get("backend_url", "http://127.0.0.1:8000")),
            backend_model=os.getenv("VLLM_CLAUDE_BACKEND_MODEL", gateway.get("backend_model", "qwen36-35b-a3b")),
            agent_base_url=os.getenv(
                "VLLM_CLAUDE_AGENT_BASE_URL",
                gateway.get("agent_base_url", "http://127.0.0.1:4010"),
            ),
            agent_status_url=os.getenv(
                "VLLM_CLAUDE_AGENT_STATUS_URL",
                gateway.get("agent_status_url", "http://127.0.0.1:4010/state"),
            ),
            require_agent_ready=os.getenv(
                "VLLM_CLAUDE_REQUIRE_AGENT_READY",
                str(gateway.get("require_agent_ready", False)),
            ).lower()
            in {"1", "true", "yes", "on"},
            queue_limit=int(os.getenv("VLLM_CLAUDE_QUEUE_LIMIT", gateway.get("queue_limit", 8))),
            execution_limit=int(os.getenv("VLLM_CLAUDE_EXECUTION_LIMIT", gateway.get("execution_limit", 1))),
        ),
        agent=AgentSettings(
            host=os.getenv("VLLM_CLAUDE_AGENT_HOST", agent.get("host", "127.0.0.1")),
            port=int(os.getenv("VLLM_CLAUDE_AGENT_PORT", agent.get("port", 4010))),
            state=os.getenv("VLLM_CLAUDE_AGENT_STATE", agent.get("state", "stopped")),
            poll_interval=int(os.getenv("VLLM_CLAUDE_AGENT_POLL_INTERVAL", agent.get("poll_interval", 15))),
            auto_recover=os.getenv("VLLM_CLAUDE_AGENT_AUTO_RECOVER", str(agent.get("auto_recover", True))).lower()
            in {"1", "true", "yes", "on"},
            recovery_threshold=int(
                os.getenv("VLLM_CLAUDE_AGENT_RECOVERY_THRESHOLD", agent.get("recovery_threshold", 2))
            ),
            startup_grace_period=int(
                os.getenv("VLLM_CLAUDE_AGENT_STARTUP_GRACE_PERIOD", agent.get("startup_grace_period", 300))
            ),
        ),
        schedule=ScheduleSettings(
            timezone=os.getenv("VLLM_CLAUDE_SCHEDULE_TIMEZONE", schedule.get("timezone", "Asia/Shanghai")),
            work_days=list(schedule.get("work_days", ["mon", "tue", "wed", "thu", "fri"])),
            start_time=os.getenv("VLLM_CLAUDE_SCHEDULE_START_TIME", schedule.get("start_time", "09:00")),
            end_time=os.getenv("VLLM_CLAUDE_SCHEDULE_END_TIME", schedule.get("end_time", "18:00")),
            auto_stop_enabled=os.getenv(
                "VLLM_CLAUDE_SCHEDULE_AUTO_STOP",
                str(schedule.get("auto_stop_enabled", True)),
            ).lower()
            in {"1", "true", "yes", "on"},
            auto_start_enabled=os.getenv(
                "VLLM_CLAUDE_SCHEDULE_AUTO_START",
                str(schedule.get("auto_start_enabled", True)),
            ).lower()
            in {"1", "true", "yes", "on"},
            cooldown_minutes=int(
                os.getenv("VLLM_CLAUDE_SCHEDULE_COOLDOWN_MINUTES", schedule.get("cooldown_minutes", 10))
            ),
        ),
        vllm=BackendSettings(
            backend_type=os.getenv("VLLM_CLAUDE_VLLM_BACKEND_TYPE", vllm.get("backend_type", "vllm")),
            container_name=os.getenv("VLLM_CLAUDE_VLLM_CONTAINER", vllm.get("container_name", "qwen36-vllm")),
            image_name=os.getenv("VLLM_CLAUDE_VLLM_IMAGE", vllm.get("image_name", "vllm/vllm-openai:nightly")),
            model_dir=_resolve_path(
                os.getenv(
                "VLLM_CLAUDE_VLLM_MODEL_DIR",
                vllm.get("model_dir", str(Path("models") / "Qwen" / "Qwen3.6-35B-A3B")),
            ),
                DEFAULT_MODEL_DIR,
            ),
            model_file=os.getenv("LLMNODE_LLAMACPP_MODEL_FILE", vllm.get("model_file", "")),
            model_name=os.getenv("VLLM_CLAUDE_VLLM_MODEL_NAME", vllm.get("model_name", "qwen36-35b-a3b")),
            host_port=int(os.getenv("VLLM_CLAUDE_VLLM_PORT", vllm.get("host_port", 8000))),
            gpu_memory_utilization=float(os.getenv("VLLM_CLAUDE_VLLM_GPU_MEMORY_UTILIZATION", vllm.get("gpu_memory_utilization", 0.6))),
            tensor_parallel_size=int(os.getenv("VLLM_CLAUDE_VLLM_TENSOR_PARALLEL_SIZE", vllm.get("tensor_parallel_size", 1))),
            max_model_len=int(os.getenv("VLLM_CLAUDE_VLLM_MAX_MODEL_LEN", vllm.get("max_model_len", 262144))),
            max_num_seqs=int(os.getenv("VLLM_CLAUDE_VLLM_MAX_NUM_SEQS", vllm.get("max_num_seqs", 4))),
            shm_size=os.getenv("VLLM_CLAUDE_VLLM_SHM_SIZE", vllm.get("shm_size", "16g")),
            enable_auto_tool_choice=os.getenv(
                "VLLM_CLAUDE_VLLM_ENABLE_AUTO_TOOL_CHOICE",
                str(vllm.get("enable_auto_tool_choice", True)),
            ).lower() in {"1", "true", "yes", "on"},
            reasoning_parser=os.getenv("VLLM_CLAUDE_VLLM_REASONING_PARSER", vllm.get("reasoning_parser", "qwen3")),
            tool_call_parser=os.getenv("VLLM_CLAUDE_VLLM_TOOL_CALL_PARSER", vllm.get("tool_call_parser", "qwen3_coder")),
            n_gpu_layers=int(os.getenv("LLMNODE_LLAMACPP_N_GPU_LAYERS", vllm.get("n_gpu_layers", -1))),
            ctx_size=int(os.getenv("LLMNODE_LLAMACPP_CTX_SIZE", vllm.get("ctx_size", 4096))),
            n_parallel=int(os.getenv("LLMNODE_LLAMACPP_N_PARALLEL", vllm.get("n_parallel", 1))),
            mem_fraction_static=float(os.getenv("LLMNODE_SGLANG_MEM_FRACTION_STATIC", vllm.get("mem_fraction_static", 0.9))),
            max_running_requests=int(os.getenv("LLMNODE_SGLANG_MAX_RUNNING_REQUESTS", vllm.get("max_running_requests", 4))),
        ),
    )
