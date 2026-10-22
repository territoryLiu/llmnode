from __future__ import annotations

from dataclasses import field
from dataclasses import dataclass
from typing import Any


@dataclass
class BenchmarkAttemptResult:
    kind: str
    latency_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    completion_tokens_per_second: float | None = None
    http_status: int | None = None
    finish_reason: str | None = None
    error_message: str | None = None
    prompt_token_mismatch: bool | None = None
    concurrency_index: int | None = None
    batch_index: int | None = None
    batch_latency_ms: float | None = None
    batch_output_tokens_per_second: float | None = None
    result: str = "unknown"
    ttft_ms: float | None = None
    prefill_ms: float | None = None
    decode_ms: float | None = None
    tpot_ms: float | None = None
    decode_tokens_per_second: float | None = None


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
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: float | None = None
    completion_tokens_per_second: float | None = None
    http_status: int | None = None
    finish_reason: str | None = None
    error_message: str | None = None
    prompt_token_mismatch: bool | None = None
    result: str = "unknown"
    backend_metrics: dict[str, Any] = field(default_factory=dict)
    warmup_runs: int = 0
    measured_runs: int = 0
    success_count: int = 0
    error_count: int = 0
    success_rate: float | None = None
    latency_ms_avg: float | None = None
    latency_ms_p50: float | None = None
    latency_ms_min: float | None = None
    latency_ms_max: float | None = None
    completion_tokens_per_second_avg: float | None = None
    completion_tokens_per_second_p50: float | None = None
    completion_tokens_per_second_min: float | None = None
    completion_tokens_per_second_max: float | None = None
    ttft_ms_avg: float | None = None
    ttft_ms_p50: float | None = None
    ttft_ms_min: float | None = None
    ttft_ms_max: float | None = None
    prefill_ms_avg: float | None = None
    decode_ms_avg: float | None = None
    tpot_ms_avg: float | None = None
    tpot_ms_p50: float | None = None
    tpot_ms_min: float | None = None
    tpot_ms_max: float | None = None
    decode_tokens_per_second_avg: float | None = None
    decode_tokens_per_second_p50: float | None = None
    decode_tokens_per_second_min: float | None = None
    decode_tokens_per_second_max: float | None = None
    batch_latency_ms_avg: float | None = None
    batch_latency_ms_p50: float | None = None
    aggregate_output_tokens_per_second_avg: float | None = None
    aggregate_output_tokens_per_second_p50: float | None = None
    aggregate_output_tokens_per_second_min: float | None = None
    aggregate_output_tokens_per_second_max: float | None = None
    attempts: list[BenchmarkAttemptResult] = field(default_factory=list)


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
    force_output_tokens: bool = False
    concurrency: int = 1
    status: str = "running"
    errors: list[str] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
