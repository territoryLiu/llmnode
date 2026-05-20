from __future__ import annotations

import json
import statistics
import os
from dataclasses import asdict
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

import httpx

from ..config import BENCHMARK_DIR, load_settings
from ..diagnostics import get_container_logs
from .models import BenchmarkRun
from .models import BenchmarkAttemptResult
from .models import BenchmarkStepResult
from .models import SamplePoint
from .probe_backend import parse_backend_runtime_sample
from .probe_backend import parse_vllm_startup_metrics
from .probe_gpu import classify_gpu_processes
from .probe_gpu import query_gpu_process_rows
from .probe_gpu import query_gpu_total_used_mb
from .prompt_builder import build_prompt_for_target


def write_benchmark_outputs(
    root_dir: Path,
    run: BenchmarkRun,
    steps: list[BenchmarkStepResult],
    samples: list[SamplePoint],
) -> Path:
    output_dir = root_dir / run.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_payload = asdict(run) | {"steps": [asdict(step) for step in steps]}
    (output_dir / "summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (output_dir / "samples.jsonl").open("w", encoding="utf-8") as fh:
        for sample in samples:
            fh.write(json.dumps(asdict(sample), ensure_ascii=False) + "\n")
    return output_dir


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat()


def _default_run_id(profile: str) -> str:
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{profile}"


def _resolve_benchmark_root(output_dir: str) -> Path:
    if output_dir:
        return Path(output_dir).expanduser().resolve()
    return BENCHMARK_DIR


def _load_tokenizer(model_dir: str):
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("transformers is required to run benchmark_backend.py") from exc
    return AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)


def _extract_backend_pids(container_name: str) -> set[int]:
    pid_file = Path("/sys/fs/cgroup/system.slice/docker.service")
    _ = pid_file
    if not container_name:
        return set()
    rows = query_gpu_process_rows()
    return {row["pid"] for row in rows}


def _collect_backend_metrics(backend_type: str, container_name: str) -> dict[str, Any]:
    logs = "\n".join(get_container_logs(container_name, 400))
    startup = parse_vllm_startup_metrics(logs) if backend_type == "vllm" else {}
    runtime = parse_backend_runtime_sample(backend_type, logs)
    return startup | runtime


def _sample_once(active_step: str, backend_type: str, container_name: str) -> SamplePoint:
    rows = query_gpu_process_rows()
    breakdown = classify_gpu_processes(rows, backend_pids=_extract_backend_pids(container_name))
    backend_metrics = _collect_backend_metrics(backend_type, container_name)
    return SamplePoint(
        ts=_iso_now(),
        active_step=active_step,
        gpu_total_used_mb=query_gpu_total_used_mb(),
        backend_process_used_mb=breakdown["backend_process_used_mb"],
        other_processes_total_mb=breakdown["other_processes_total_mb"],
        other_processes=breakdown["other_processes"],
        kv_cache_usage_percent=backend_metrics.get("kv_cache_usage_percent"),
        prompt_throughput_tokens_per_s=backend_metrics.get("prompt_throughput_tokens_per_s"),
        generation_throughput_tokens_per_s=backend_metrics.get("generation_throughput_tokens_per_s"),
        backend_metrics=backend_metrics,
    )


def _summarize_attempts(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    measured = [item for item in attempts if item.get("kind") == "measure"]
    latencies = [float(item["latency_ms"]) for item in measured if item.get("latency_ms") is not None]
    speeds = [float(item["completion_tokens_per_second"]) for item in measured if item.get("completion_tokens_per_second") is not None]
    summary: dict[str, Any] = {
        "warmup_runs": sum(1 for item in attempts if item.get("kind") == "warmup"),
        "measured_runs": len(measured),
        "http_status": measured[-1].get("http_status") if measured else None,
        "result": "success" if measured and all(item.get("result") == "success" for item in measured) else (measured[-1].get("result") if measured else "unknown"),
    }
    if latencies:
        summary["latency_ms_avg"] = statistics.mean(latencies)
        summary["latency_ms_p50"] = statistics.median(latencies)
        summary["latency_ms_min"] = min(latencies)
        summary["latency_ms_max"] = max(latencies)
        summary["latency_ms"] = summary["latency_ms_avg"]
    else:
        summary["latency_ms_avg"] = None
        summary["latency_ms_p50"] = None
        summary["latency_ms_min"] = None
        summary["latency_ms_max"] = None
        summary["latency_ms"] = None
    if speeds:
        summary["completion_tokens_per_second_avg"] = statistics.mean(speeds)
        summary["completion_tokens_per_second_p50"] = statistics.median(speeds)
        summary["completion_tokens_per_second_min"] = min(speeds)
        summary["completion_tokens_per_second_max"] = max(speeds)
        summary["completion_tokens_per_second"] = summary["completion_tokens_per_second_avg"]
    else:
        summary["completion_tokens_per_second_avg"] = None
        summary["completion_tokens_per_second_p50"] = None
        summary["completion_tokens_per_second_min"] = None
        summary["completion_tokens_per_second_max"] = None
        summary["completion_tokens_per_second"] = None
    completion_values = [item.get("completion_tokens") for item in measured if item.get("completion_tokens") is not None]
    summary["completion_tokens"] = completion_values[-1] if completion_values else None
    return summary


def run_benchmark(
    *,
    targets: list[int],
    max_tokens: int = 64,
    sample_interval: float = 1.0,
    output_dir: str = "",
    profile: str = "",
    warmup_runs: int = 1,
    measure_runs: int = 3,
) -> Path:
    if profile:
        os.environ["VLLM_CLAUDE_ACTIVE_BACKEND_PROFILE"] = profile
    settings = load_settings()
    benchmark_root = _resolve_benchmark_root(output_dir)
    benchmark_root.mkdir(parents=True, exist_ok=True)
    tokenizer = _load_tokenizer(settings.vllm.model_dir)
    run = BenchmarkRun(
        run_id=_default_run_id(settings.active_backend_profile),
        backend_type=settings.vllm.backend_type,
        model_name=settings.vllm.model_name,
        endpoint=settings.gateway.backend_url,
        targets=targets,
        active_backend_profile=settings.active_backend_profile,
        model_dir=settings.vllm.model_dir,
        container_name=settings.vllm.container_name,
        max_tokens=max_tokens,
        started_at=_iso_now(),
    )

    steps: list[BenchmarkStepResult] = []
    samples: list[SamplePoint] = []
    backend_metrics = _collect_backend_metrics(settings.vllm.backend_type, settings.vllm.container_name)

    with httpx.Client(base_url=settings.gateway.backend_url, timeout=settings.gateway.backend_request_timeout_seconds) as client:
        for target in targets:
            label = f"{target // 1024}K" if target >= 1024 else str(target)
            prompt, actual_prompt_tokens = build_prompt_for_target(
                tokenizer=tokenizer,
                target_prompt_tokens=target,
                base_fragment="hello",
            )
            started_at = _utc_now()
            step = BenchmarkStepResult(
                label=label,
                target_prompt_tokens=target,
                actual_prompt_tokens=actual_prompt_tokens,
                backend_metrics=backend_metrics,
            )
            attempts: list[dict[str, Any]] = []
            total_runs = [("warmup", warmup_runs), ("measure", measure_runs)]
            for kind, count in total_runs:
                for index in range(count):
                    active_label = f"{label}-{kind}-{index + 1}"
                    samples.append(_sample_once(active_label, settings.vllm.backend_type, settings.vllm.container_name))
                    attempt_started_at = _utc_now()
                    attempt: dict[str, Any] = {"kind": kind, "result": "unknown"}
                    try:
                        response = client.post(
                            "/v1/chat/completions",
                            json={
                                "model": settings.vllm.model_name,
                                "messages": [{"role": "user", "content": prompt}],
                                "max_tokens": max_tokens,
                            },
                        )
                        finished_at = _utc_now()
                        payload = response.json()
                        usage = payload.get("usage") if isinstance(payload, dict) else {}
                        latency_ms = (finished_at - attempt_started_at).total_seconds() * 1000.0
                        completion_tokens = usage.get("completion_tokens") if isinstance(usage, dict) else None
                        attempt["http_status"] = response.status_code
                        attempt["completion_tokens"] = completion_tokens
                        attempt["latency_ms"] = latency_ms
                        attempt["completion_tokens_per_second"] = (
                            completion_tokens / (latency_ms / 1000.0)
                            if completion_tokens is not None and latency_ms > 0
                            else None
                        )
                        attempt["result"] = "success" if response.is_success else "error"
                    except httpx.ReadTimeout:
                        attempt["result"] = "timeout"
                    except Exception as exc:
                        run.errors.append(str(exc))
                        attempt["result"] = "error"
                    samples.append(_sample_once(active_label, settings.vllm.backend_type, settings.vllm.container_name))
                    attempts.append(attempt)
            summary = _summarize_attempts(attempts)
            step.attempts = [BenchmarkAttemptResult(**attempt) for attempt in attempts]
            step.warmup_runs = summary["warmup_runs"]
            step.measured_runs = summary["measured_runs"]
            step.http_status = summary["http_status"]
            step.result = summary["result"]
            step.completion_tokens = summary["completion_tokens"]
            step.latency_ms = summary["latency_ms"]
            step.completion_tokens_per_second = summary["completion_tokens_per_second"]
            step.latency_ms_avg = summary["latency_ms_avg"]
            step.latency_ms_p50 = summary["latency_ms_p50"]
            step.latency_ms_min = summary["latency_ms_min"]
            step.latency_ms_max = summary["latency_ms_max"]
            step.completion_tokens_per_second_avg = summary["completion_tokens_per_second_avg"]
            step.completion_tokens_per_second_p50 = summary["completion_tokens_per_second_p50"]
            step.completion_tokens_per_second_min = summary["completion_tokens_per_second_min"]
            step.completion_tokens_per_second_max = summary["completion_tokens_per_second_max"]
            steps.append(step)

    _ = sample_interval
    run.status = "completed" if not run.errors else "completed_with_errors"
    run.finished_at = _iso_now()
    return write_benchmark_outputs(benchmark_root, run, steps, samples)
