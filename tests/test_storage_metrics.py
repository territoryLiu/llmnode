from pathlib import Path

from llmnode.storage.db import (
    aggregate_request_metrics,
    init_db,
    write_request_metric,
)


def test_request_metrics_aggregation_counts_latency_and_throughput(tmp_path: Path):
    conn = init_db(tmp_path / "metrics.db")

    write_request_metric(
        conn,
        request_id="req-1",
        model_name="qwen36-27b",
        protocol="openai",
        status="ok",
        latency_ms=1000.0,
        prompt_tokens=10,
        completion_tokens=50,
        total_tokens=60,
        tokens_per_second=50.0,
        started_at="2026-05-13T10:00:00+00:00",
        finished_at="2026-05-13T10:00:01+00:00",
    )
    write_request_metric(
        conn,
        request_id="req-2",
        model_name="qwen36-27b",
        protocol="openai",
        status="ok",
        latency_ms=2000.0,
        prompt_tokens=12,
        completion_tokens=30,
        total_tokens=42,
        tokens_per_second=15.0,
        started_at="2026-05-13T10:00:02+00:00",
        finished_at="2026-05-13T10:00:04+00:00",
    )
    write_request_metric(
        conn,
        request_id="req-3",
        model_name="qwen36-27b",
        protocol="anthropic",
        status="timeout",
        latency_ms=3000.0,
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
        tokens_per_second=None,
        started_at="2026-05-13T10:00:05+00:00",
        finished_at="2026-05-13T10:00:08+00:00",
    )

    metrics = aggregate_request_metrics(conn)

    assert metrics["request_count"] == 3
    assert metrics["success_count"] == 2
    assert round(metrics["success_rate"], 4) == 0.6667
    assert metrics["avg_latency_ms"] == 2000.0
    assert metrics["p95_latency_ms"] == 3000.0
    assert metrics["p99_latency_ms"] == 3000.0
    assert metrics["tokens_observed_requests"] == 2
    assert round(metrics["throughput_tokens_per_s"], 4) == round(80 / 3, 4)
