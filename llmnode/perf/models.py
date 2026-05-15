from __future__ import annotations

from dataclasses import field
from dataclasses import dataclass
from typing import Any


@dataclass
class GpuProcessBreakdown:
    backend_processes: list[dict[str, Any]] = field(default_factory=list)
    backend_process_used_mb: int = 0
    other_processes_total_mb: int = 0
    other_processes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class BenchmarkStepResult:
    label: str
    target_prompt_tokens: int
    actual_prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: float | None = None
    completion_tokens_per_second: float | None = None
    http_status: int | None = None
    result: str = "unknown"
    backend_metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class SamplePoint:
    ts: str
    active_step: str
    gpu_total_used_mb: int | None = None
    backend_process_used_mb: int | None = None
    other_processes_total_mb: int | None = None
    other_processes: list[dict[str, Any]] = field(default_factory=list)
    kv_cache_usage_percent: float | None = None
    prompt_throughput_tokens_per_s: float | None = None
    generation_throughput_tokens_per_s: float | None = None
    backend_metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkRun:
    run_id: str
    backend_type: str
    model_name: str
    endpoint: str
    targets: list[int]
    active_backend_profile: str = ""
    model_dir: str = ""
    container_name: str = ""
    max_tokens: int = 64
    status: str = "running"
    errors: list[str] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
