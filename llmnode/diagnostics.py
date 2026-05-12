"""
诊断工具模块

提供可复用的诊断函数，供 CLI 和 API 使用。
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def collect_gpu_info() -> list[dict]:
    """采集 GPU 信息，返回 GPU 列表"""
    if not _command_exists("nvidia-smi"):
        return []

    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits"
        ],
        capture_output=True,
        text=True,
        check=False,
    )

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


def collect_cuda_version() -> str:
    """采集 CUDA 版本"""
    if not _command_exists("nvidia-smi"):
        return "unavailable"

    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return "unavailable"

    driver_version = result.stdout.strip().splitlines()[0] if result.stdout.strip() else "unknown"

    # 尝试获取 CUDA 版本
    result = subprocess.run(["nvidia-smi"], capture_output=True, text=True, check=False)
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            if "CUDA Version:" in line:
                parts = line.split("CUDA Version:")
                if len(parts) > 1:
                    cuda_version = parts[1].strip().split()[0]
                    return f"{cuda_version} (driver: {driver_version})"

    return f"driver: {driver_version}"


def inspect_container(container_name: str) -> dict:
    """获取容器详细信息"""
    result = subprocess.run(
        ["docker", "inspect", container_name],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {}

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


def get_container_logs(container_name: str, lines: int = 20) -> list[str]:
    """获取容器最近日志"""
    result = subprocess.run(
        ["docker", "logs", "--tail", str(lines), container_name],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return (result.stdout + result.stderr).splitlines()


def detect_model_format(model_dir: Path) -> str:
    """检测模型格式"""
    if not model_dir.is_dir():
        return "unknown"

    if (model_dir / "config.json").exists():
        return "huggingface"

    if any(model_dir.glob("*.gguf")):
        return "gguf"

    return "unknown"


def parse_model_config(model_dir: Path) -> dict:
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


def analyze_logs_for_errors(logs: list[str]) -> list[str]:
    """分析日志，识别错误模式并返回建议"""
    error_patterns = {
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

    suggestions = []
    log_text = "\n".join(logs)

    for error_type, config in error_patterns.items():
        if re.search(config["pattern"], log_text, re.IGNORECASE):
            suggestions.append(config["suggestion"])

    return suggestions


def format_uptime(started_at: str) -> str:
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


def _command_exists(command: str) -> bool:
    """检查命令是否存在"""
    import shutil
    return shutil.which(command) is not None
