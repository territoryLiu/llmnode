from __future__ import annotations

import json
import statistics
import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
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
    try:
        return AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)
    except ValueError as exc:
        if "Tokenizer class" not in str(exc):
            raise
        tokenizer_config_path = Path(model_dir) / "tokenizer_config.json"
        if not tokenizer_config_path.exists():
            raise
        config = json.loads(tokenizer_config_path.read_text(encoding="utf-8"))
        if config.get("tokenizer_class") != "TokenizersBackend":
            raise
        fallback_config = dict(config)
        fallback_config.pop("tokenizer_class", None)
        with tempfile.TemporaryDirectory(prefix="llmnode-tokenizer-") as temp_dir:
            temp_path = Path(temp_dir)
            for item in Path(model_dir).iterdir():
                target = temp_path / item.name
                if item.name == "tokenizer_config.json":
                    target.write_text(json.dumps(fallback_config, ensure_ascii=False, indent=2), encoding="utf-8")
                else:
                    os.symlink(item, target)
            return AutoTokenizer.from_pretrained(str(temp_path), trust_remote_code=True)


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


def _sample_once_safe(active_step: str, backend_type: str, container_name: str) -> SamplePoint:
    try:
        return _sample_once(active_step, backend_type, container_name)
    except Exception as exc:
        return SamplePoint(
            ts=_iso_now(),
            active_step=active_step,
            backend_metrics={"sample_error": str(exc)},
        )


def _run_with_sampling(
    samples: list[SamplePoint],
    active_label: str,
    backend_type: str,
    container_name: str,
    sample_interval: float,
    fn,
):
    interval = max(float(sample_interval), 0.1)
    stop_event = threading.Event()

    def collect() -> None:
        while not stop_event.is_set():
            samples.append(_sample_once_safe(active_label, backend_type, container_name))
            stop_event.wait(interval)

    thread = threading.Thread(target=collect, daemon=True)
    thread.start()
    try:
        return fn()
    finally:
        stop_event.set()
        thread.join(timeout=interval + 1.0)
        samples.append(_sample_once_safe(active_label, backend_type, container_name))


def _summarize_attempts(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    measured = [item for item in attempts if item.get("kind") == "measure"]
    latencies = [float(item["latency_ms"]) for item in measured if item.get("latency_ms") is not None]
    speeds = [float(item["completion_tokens_per_second"]) for item in measured if item.get("completion_tokens_per_second") is not None]
    success_count = sum(1 for item in measured if item.get("result") == "success")
    error_count = len(measured) - success_count
    summary: dict[str, Any] = {
        "warmup_runs": sum(1 for item in attempts if item.get("kind") == "warmup"),
        "measured_runs": len(measured),
        "success_count": success_count,
        "error_count": error_count,
        "success_rate": success_count / len(measured) if measured else None,
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
    prompt_values = [item.get("prompt_tokens") for item in measured if item.get("prompt_tokens") is not None]
    total_values = [item.get("total_tokens") for item in measured if item.get("total_tokens") is not None]
    finish_reasons = [item.get("finish_reason") for item in measured if item.get("finish_reason")]
    error_messages = [item.get("error_message") for item in measured if item.get("error_message")]
    mismatches = [item.get("prompt_token_mismatch") for item in measured if item.get("prompt_token_mismatch") is not None]
    summary["prompt_tokens"] = prompt_values[-1] if prompt_values else None
    summary["completion_tokens"] = completion_values[-1] if completion_values else None
    summary["total_tokens"] = total_values[-1] if total_values else None
    summary["finish_reason"] = finish_reasons[-1] if finish_reasons else None
    summary["error_message"] = error_messages[-1] if error_messages else None
    summary["prompt_token_mismatch"] = any(mismatches) if mismatches else None
    return summary


def _extract_error_message(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        return str(message) if message else json.dumps(error, ensure_ascii=False)
    if isinstance(error, str):
        return error
    return None


def _extract_finish_reason(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    finish_reason = first.get("finish_reason")
    return str(finish_reason) if finish_reason is not None else None


def run_benchmark(
    *,
    targets: list[int],
    max_tokens: int = 64,
    sample_interval: float = 1.0,
    output_dir: str = "",
    profile: str = "",
    warmup_runs: int = 1,
    measure_runs: int = 3,
    concurrency: int = 1,
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
        concurrency=concurrency,
        started_at=_iso_now(),
    )

    steps: list[BenchmarkStepResult] = []
    samples: list[SamplePoint] = []
    backend_metrics = _collect_backend_metrics(settings.vllm.backend_type, settings.vllm.container_name)

    for target in targets:
        label = f"{target // 1024}K" if target >= 1024 else str(target)
        prompt, actual_prompt_tokens = build_prompt_for_target(
            tokenizer=tokenizer,
            target_prompt_tokens=target,
            base_fragment="hello",
        )
        step = BenchmarkStepResult(
            label=label,
            target_prompt_tokens=target,
            actual_prompt_tokens=actual_prompt_tokens,
            backend_metrics=backend_metrics,
        )
        attempts: list[dict[str, Any]] = []
        total_runs = [("warmup", warmup_runs), ("measure", measure_runs)]

        def execute_attempt(active_label: str, kind: str, concurrency_index: int) -> dict[str, Any]:
            attempt_started_at = _utc_now()
            attempt: dict[str, Any] = {
                "kind": kind,
                "concurrency_index": concurrency_index,
                "result": "unknown",
            }
            try:
                def post_request():
                    with httpx.Client(
                        base_url=settings.gateway.backend_url,
                        timeout=settings.gateway.backend_request_timeout_seconds,
                    ) as client:
                        return client.post(
                            "/v1/chat/completions",
                            json={
                                "model": settings.vllm.model_name,
                                "messages": [{"role": "user", "content": prompt}],
                                "max_tokens": max_tokens,
                            },
                        )

                response = _run_with_sampling(
                    samples,
                    active_label,
                    settings.vllm.backend_type,
                    settings.vllm.container_name,
                    sample_interval,
                    post_request,
                )
                finished_at = _utc_now()
                attempt["http_status"] = response.status_code
                try:
                    payload = response.json()
                except ValueError:
                    payload = {}
                    attempt["error_message"] = response.text[:500]
                usage = payload.get("usage") if isinstance(payload, dict) else {}
                latency_ms = (finished_at - attempt_started_at).total_seconds() * 1000.0
                prompt_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
                completion_tokens = usage.get("completion_tokens") if isinstance(usage, dict) else None
                total_tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
                attempt["prompt_tokens"] = prompt_tokens
                attempt["completion_tokens"] = completion_tokens
                attempt["total_tokens"] = total_tokens
                attempt["finish_reason"] = _extract_finish_reason(payload)
                attempt["error_message"] = attempt.get("error_message") or _extract_error_message(payload)
                attempt["prompt_token_mismatch"] = (
                    prompt_tokens != actual_prompt_tokens
                    if prompt_tokens is not None and actual_prompt_tokens is not None
                    else None
                )
                attempt["latency_ms"] = latency_ms
                attempt["completion_tokens_per_second"] = (
                    completion_tokens / (latency_ms / 1000.0)
                    if completion_tokens is not None and latency_ms > 0
                    else None
                )
                attempt["result"] = "success" if response.is_success else "error"
            except httpx.ReadTimeout:
                attempt["result"] = "timeout"
                attempt["error_message"] = "read timeout"
            except Exception as exc:
                run.errors.append(str(exc))
                attempt["result"] = "error"
                attempt["error_message"] = str(exc)
            return attempt

        for kind, count in total_runs:
            for index in range(count):
                active_label = f"{label}-{kind}-{index + 1}"
                if concurrency == 1:
                    attempts.append(execute_attempt(active_label, kind, 1))
                else:
                    with ThreadPoolExecutor(max_workers=concurrency) as pool:
                        futures = [
                            pool.submit(execute_attempt, f"{active_label}-c{idx}", kind, idx)
                            for idx in range(1, concurrency + 1)
                        ]
                        for future in as_completed(futures):
                            attempts.append(future.result())
        summary = _summarize_attempts(attempts)
        step.attempts = [BenchmarkAttemptResult(**attempt) for attempt in attempts]
        step.warmup_runs = summary["warmup_runs"]
        step.measured_runs = summary["measured_runs"]
        step.success_count = summary["success_count"]
        step.error_count = summary["error_count"]
        step.success_rate = summary["success_rate"]
        step.http_status = summary["http_status"]
        step.result = summary["result"]
        step.prompt_tokens = summary["prompt_tokens"]
        step.completion_tokens = summary["completion_tokens"]
        step.total_tokens = summary["total_tokens"]
        step.finish_reason = summary["finish_reason"]
        step.error_message = summary["error_message"]
        step.prompt_token_mismatch = summary["prompt_token_mismatch"]
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

    run.status = "completed" if not run.errors else "completed_with_errors"
    run.finished_at = _iso_now()
    return write_benchmark_outputs(benchmark_root, run, steps, samples)
