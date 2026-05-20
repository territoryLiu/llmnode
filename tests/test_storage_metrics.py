import sqlite3
from pathlib import Path

from llmnode.storage.db import (
    create_api_key,
    aggregate_request_metrics,
    aggregate_usage_breakdown,
    aggregate_usage_chart,
    aggregate_usage_for_api_key,
    aggregate_usage_trend,
    init_db,
    write_request_metric,
    write_request_log,
)
from llmnode.security import hash_api_key


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


def test_request_metrics_persist_usage_ledger_fields(tmp_path: Path):
    conn = init_db(tmp_path / "metrics.db")

    write_request_metric(
        conn,
        request_id="req-ledger",
        model_name="demo",
        protocol="openai",
        status="ok",
        latency_ms=10.0,
        prompt_tokens=1,
        completion_tokens=2,
        total_tokens=3,
        tokens_per_second=0.2,
        backend_type="vllm",
        api_key_id=7,
        cache_creation_tokens=5,
        cache_read_tokens=6,
        cache_miss_tokens=None,
        error_code=None,
        status_detail=None,
        started_at="2026-05-14T10:00:00+00:00",
        finished_at="2026-05-14T10:00:01+00:00",
    )

    row = conn.execute(
        """
        SELECT backend_type, api_key_id, cache_creation_tokens, cache_read_tokens, cache_miss_tokens
        FROM request_metrics
        WHERE request_id = ?
        """,
        ("req-ledger",),
    ).fetchone()

    assert row == ("vllm", 7, 5, 6, None)


def test_usage_aggregation_exposes_summary_trend_breakdown_and_key_views(tmp_path: Path):
    conn = init_db(tmp_path / "metrics.db")
    alpha_key = create_api_key(
        conn,
        name="alpha-key",
        key_hash=hash_api_key("sk-alpha"),
        scopes=["inference"],
    )
    beta_key = create_api_key(
        conn,
        name="beta-key",
        key_hash=hash_api_key("sk-beta"),
        scopes=["inference"],
    )

    write_request_log(
        conn,
        request_id="req-1",
        model_name="demo-a",
        status="ok",
        protocol="openai",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    )
    write_request_metric(
        conn,
        request_id="req-1",
        model_name="demo-a",
        protocol="openai",
        status="ok",
        latency_ms=100.0,
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        tokens_per_second=200.0,
        backend_type="vllm",
        api_key_id=alpha_key["id"],
        cache_creation_tokens=1,
        cache_read_tokens=2,
        cache_miss_tokens=3,
        started_at="2026-05-14T10:00:00+00:00",
        finished_at="2026-05-14T10:00:00.100000+00:00",
    )
    write_request_log(
        conn,
        request_id="req-2",
        model_name="demo-b",
        status="timeout",
        protocol="anthropic",
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
    )
    write_request_metric(
        conn,
        request_id="req-2",
        model_name="demo-b",
        protocol="anthropic",
        status="timeout",
        latency_ms=250.0,
        prompt_tokens=8,
        completion_tokens=None,
        total_tokens=8,
        tokens_per_second=None,
        backend_type="sglang",
        api_key_id=beta_key["id"],
        cache_creation_tokens=None,
        cache_read_tokens=None,
        cache_miss_tokens=None,
        started_at="2026-05-14T11:00:00+00:00",
        finished_at="2026-05-14T11:00:00.250000+00:00",
    )

    summary = aggregate_request_metrics(conn)
    assert summary["request_count"] == 2
    assert summary["success_count"] == 1
    assert summary["total_tokens"] == 38
    assert summary["cache_read_tokens"] == 2
    assert summary["cache_read_observed_requests"] == 1

    trend = aggregate_usage_trend(conn, granularity="day")
    assert trend == [
        {
            "bucket": "2026-05-14",
            "request_count": 2,
            "total_tokens": 38,
            "cache_read_tokens": 2,
            "cache_read_observed": 1,
        }
    ]

    backend_breakdown = aggregate_usage_breakdown(conn, group_by="backend_type")
    assert backend_breakdown[0]["group"] == "vllm"
    assert backend_breakdown[0]["total_tokens"] == 30
    assert backend_breakdown[1]["group"] == "sglang"
    assert backend_breakdown[1]["cache_read_tokens"] is None

    key_summary = aggregate_usage_for_api_key(conn, api_key_id=alpha_key["id"])
    assert key_summary["summary"]["api_key_id"] == alpha_key["id"]
    assert key_summary["summary"]["request_count"] == 1
    assert key_summary["summary"]["total_requests"] == 1
    assert key_summary["summary"]["total_tokens"] == 30
    assert key_summary["summary"]["cache_read_tokens"] == 2
    assert key_summary["summary"]["cache_read_observed_requests"] == 1

    chart = aggregate_usage_chart(
        conn,
        window="day",
        group_by="backend_type",
        now="2026-05-14T12:00:00+00:00",
    )
    assert chart["window"] == "day"
    assert chart["group_by"] == "backend_type"
    assert chart["groups"][0]["group"] == "vllm"
    assert chart["groups"][0]["totals"]["prompt_tokens"] == 10
    assert chart["groups"][0]["totals"]["completion_tokens"] == 20
    assert chart["groups"][0]["totals"]["cache_tokens"] == 6
    assert next(
        point["total_tokens"]
        for point in chart["groups"][0]["points"]
        if point["bucket"] == "2026-05-14 10:00"
    ) == 30

    key_name_chart = aggregate_usage_chart(
        conn,
        window="day",
        group_by="api_key_name",
        now="2026-05-14T12:00:00+00:00",
    )
    assert [group["group"] for group in key_name_chart["groups"]] == ["alpha-key", "beta-key"]
    assert key_name_chart["groups"][0]["label"] == "alpha-key"
    assert next(
        point["prompt_tokens"]
        for point in key_name_chart["groups"][1]["points"]
        if point["bucket"] == "2026-05-14 11:00"
    ) == 8


def test_migration_preserves_existing_data(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    conn = init_db(db_path)
    conn.close()

    legacy = sqlite3.connect(db_path, check_same_thread=False)
    legacy.execute("DROP TABLE request_metrics")
    legacy.execute(
        """
        CREATE TABLE request_metrics (
            request_id TEXT PRIMARY KEY,
            model_name TEXT NOT NULL,
            protocol TEXT NOT NULL,
            status TEXT NOT NULL,
            latency_ms REAL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            tokens_per_second REAL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    legacy.execute(
        """
        INSERT INTO request_metrics(
            request_id, model_name, protocol, status, latency_ms,
            prompt_tokens, completion_tokens, total_tokens, tokens_per_second,
            started_at, finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "req-legacy",
            "demo",
            "openai",
            "ok",
            42.0,
            1,
            2,
            3,
            4.0,
            "2026-05-13T00:00:00+00:00",
            "2026-05-13T00:00:01+00:00",
        ),
    )
    legacy.commit()
    legacy.close()

    migrated = init_db(db_path)
    row = migrated.execute(
        """
        SELECT request_id, total_tokens, backend_type, api_key_id, cache_read_tokens
        FROM request_metrics
        WHERE request_id = ?
        """,
        ("req-legacy",),
    ).fetchone()

    assert row == ("req-legacy", 3, None, None, None)


def test_aggregation_handles_null_cache_tokens_without_faking_zero(tmp_path: Path):
    conn = init_db(tmp_path / "metrics.db")

    write_request_metric(
        conn,
        request_id="req-cache",
        model_name="demo",
        protocol="openai",
        status="ok",
        latency_ms=100.0,
        prompt_tokens=5,
        completion_tokens=5,
        total_tokens=10,
        tokens_per_second=50.0,
        backend_type="vllm",
        api_key_id=1,
        cache_creation_tokens=2,
        cache_read_tokens=7,
        cache_miss_tokens=0,
        started_at="2026-05-14T00:00:00+00:00",
        finished_at="2026-05-14T00:00:00.100000+00:00",
    )
    write_request_metric(
        conn,
        request_id="req-no-cache",
        model_name="demo",
        protocol="openai",
        status="ok",
        latency_ms=100.0,
        prompt_tokens=5,
        completion_tokens=5,
        total_tokens=10,
        tokens_per_second=50.0,
        backend_type="vllm",
        api_key_id=1,
        cache_creation_tokens=None,
        cache_read_tokens=None,
        cache_miss_tokens=None,
        started_at="2026-05-15T00:00:00+00:00",
        finished_at="2026-05-15T00:00:00.100000+00:00",
    )

    summary = aggregate_request_metrics(conn)
    trend = aggregate_usage_trend(conn, granularity="day")

    assert summary["cache_read_tokens"] == 7
    assert summary["cache_read_observed_requests"] == 1
    assert trend[0]["cache_read_tokens"] == 7
    assert trend[0]["cache_read_observed"] == 1
    assert trend[1]["cache_read_tokens"] is None
    assert trend[1]["cache_read_observed"] == 0
