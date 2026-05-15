from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any
from pathlib import Path

_UNSET = object()
_ALLOWED_CHART_WINDOWS = {"12h", "day", "month", "year"}
_ALLOWED_CHART_GROUP_BY = {"backend_type", "model_name", "device_type"}


def _now_sql() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def _ensure_columns(conn: sqlite3.Connection, table_name: str, columns: dict[str, str]) -> None:
    existing = _table_columns(conn, table_name)
    for name, ddl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {name} {ddl}")


def _decode_api_key_row(row: Any) -> dict[str, Any]:
    return {
        "id": row[0],
        "key_hash": row[1],
        "name": row[2],
        "status": row[3],
        "scopes": json.loads(row[4]),
        "rpm_limit": row[5],
        "concurrency_limit": row[6],
        "created_at": row[7],
        "disabled_at": row[8],
        "last_used_at": row[9],
        "note": row[10],
    }


def mask_api_key(secret: str) -> str:
    if len(secret) <= 10:
        return secret
    return f"{secret[:6]}***{secret[-4:]}"


def stable_masked_key(key_id: int) -> str:
    return f"sk-{'*' * 36}{key_id:04d}"[-43:]


def init_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS request_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            model_name TEXT NOT NULL,
            status TEXT NOT NULL,
            protocol TEXT NOT NULL,
            error_message TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    _ensure_columns(
        conn,
        "request_logs",
        {
            "api_key_id": "INTEGER",
            "auth_source": "TEXT",
            "client_ip": "TEXT",
            "user_agent": "TEXT",
            "rejection_reason": "TEXT",
        },
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL,
            reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    _ensure_columns(
        conn,
        "agent_events",
        {
            "event_type": "TEXT",
            "readiness_state": "TEXT",
            "http_ready": "INTEGER",
            "inference_ready": "INTEGER",
            "metadata_json": "TEXT",
        },
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS model_routes (
            name TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            backend_model TEXT NOT NULL,
            backend_type TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            timezone TEXT NOT NULL,
            work_days TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            auto_stop_enabled INTEGER NOT NULL,
            auto_start_enabled INTEGER NOT NULL,
            cooldown_minutes INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            scopes TEXT NOT NULL,
            rpm_limit INTEGER,
            concurrency_limit INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            disabled_at TEXT,
            last_used_at TEXT,
            note TEXT
        )
        """
    )
    _ensure_columns(
        conn,
        "api_keys",
        {
            "last_used_at": "TEXT",
            "note": "TEXT",
        },
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS request_metrics (
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
    _ensure_columns(
        conn,
        "request_metrics",
        {
            "backend_type": "TEXT",
            "api_key_id": "INTEGER",
            "cache_creation_tokens": "INTEGER",
            "cache_read_tokens": "INTEGER",
            "cache_miss_tokens": "INTEGER",
            "error_code": "TEXT",
            "status_detail": "TEXT",
        },
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_request_metrics_created_at "
        "ON request_metrics(created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_request_metrics_backend_type "
        "ON request_metrics(backend_type)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_request_metrics_api_key_id "
        "ON request_metrics(api_key_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_request_metrics_model_name "
        "ON request_metrics(model_name)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS response_states (
            response_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            model_name TEXT NOT NULL,
            input_items_json TEXT NOT NULL,
            output_items_json TEXT NOT NULL,
            messages_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_response_states_created_at "
        "ON response_states(created_at)"
    )
    conn.commit()
    return conn


def write_request_log(
    conn: sqlite3.Connection,
    request_id: str,
    model_name: str,
    status: str,
    protocol: str,
    error_message: str | None = None,
    *,
    api_key_id: int | None = None,
    auth_source: str | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
    rejection_reason: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO request_logs(
            request_id, model_name, status, protocol, error_message, api_key_id, auth_source, client_ip, user_agent, rejection_reason
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            request_id,
            model_name,
            status,
            protocol,
            error_message,
            api_key_id,
            auth_source,
            client_ip,
            user_agent,
            rejection_reason,
        ),
    )
    conn.commit()


def write_agent_event(
    conn: sqlite3.Connection,
    status: str,
    reason: str | None = None,
    *,
    event_type: str | None = None,
    readiness_state: str | None = None,
    http_ready: bool | None = None,
    inference_ready: bool | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO agent_events(
            status, reason, event_type, readiness_state, http_ready, inference_ready, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            status,
            reason,
            event_type or status,
            readiness_state or status,
            None if http_ready is None else int(http_ready),
            None if inference_ready is None else int(inference_ready),
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )
    conn.commit()


def write_request_metric(
    conn: sqlite3.Connection,
    *,
    request_id: str,
    model_name: str,
    protocol: str,
    status: str,
    latency_ms: float | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
    tokens_per_second: float | None,
    started_at: str,
    finished_at: str | None,
    backend_type: str | None = None,
    api_key_id: int | None = None,
    cache_creation_tokens: int | None = None,
    cache_read_tokens: int | None = None,
    cache_miss_tokens: int | None = None,
    error_code: str | None = None,
    status_detail: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO request_metrics(
            request_id,
            model_name,
            protocol,
            status,
            latency_ms,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            tokens_per_second,
            started_at,
            finished_at,
            backend_type,
            api_key_id,
            cache_creation_tokens,
            cache_read_tokens,
            cache_miss_tokens,
            error_code,
            status_detail
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            request_id,
            model_name,
            protocol,
            status,
            latency_ms,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            tokens_per_second,
            started_at,
            finished_at,
            backend_type,
            api_key_id,
            cache_creation_tokens,
            cache_read_tokens,
            cache_miss_tokens,
            error_code,
            status_detail,
        ),
    )
    conn.commit()


def upsert_response_state(
    conn: sqlite3.Connection,
    *,
    response_id: str,
    request_id: str,
    model_name: str,
    input_items: list[dict[str, Any]],
    output_items: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> None:
    conn.execute(
        """
        INSERT INTO response_states(
            response_id,
            request_id,
            model_name,
            input_items_json,
            output_items_json,
            messages_json,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(response_id) DO UPDATE SET
            request_id = excluded.request_id,
            model_name = excluded.model_name,
            input_items_json = excluded.input_items_json,
            output_items_json = excluded.output_items_json,
            messages_json = excluded.messages_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            response_id,
            request_id,
            model_name,
            json.dumps(input_items, ensure_ascii=False),
            json.dumps(output_items, ensure_ascii=False),
            json.dumps(messages, ensure_ascii=False),
        ),
    )
    conn.commit()


def get_response_state(conn: sqlite3.Connection, response_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT response_id, request_id, model_name, input_items_json, output_items_json, messages_json, created_at, updated_at
        FROM response_states
        WHERE response_id = ?
        """,
        (response_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "response_id": row[0],
        "request_id": row[1],
        "model_name": row[2],
        "input_items": json.loads(row[3]),
        "output_items": json.loads(row[4]),
        "messages": json.loads(row[5]),
        "created_at": row[6],
        "updated_at": row[7],
    }


def _percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * ratio) - 1))
    return ordered[index]


def _select_request_metric_rows(
    conn: sqlite3.Connection,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[tuple[Any, ...]]:
    where_parts = []
    params: list[Any] = []
    if date_from:
        where_parts.append("started_at >= ?")
        params.append(date_from)
    if date_to:
        where_parts.append("started_at <= ?")
        params.append(date_to)
    clause = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
    rows = conn.execute(
        f"""
        SELECT status, latency_ms, completion_tokens, total_tokens,
               cache_creation_tokens, cache_read_tokens, cache_miss_tokens
        FROM request_metrics
        {clause}
        ORDER BY started_at ASC
        """,
        params,
    ).fetchall()
    return rows


def aggregate_request_metrics(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = _select_request_metric_rows(conn)
    request_count = len(rows)
    success_count = sum(1 for row in rows if row[0] == "ok")
    latencies = [float(row[1]) for row in rows if row[1] is not None]
    token_rows = [
        (float(row[1]), int(row[2]))
        for row in rows
        if row[1] is not None and row[2] is not None
    ]
    total_completion_tokens = sum(item[1] for item in token_rows)
    total_latency_seconds = sum(item[0] / 1000.0 for item in token_rows)

    total_tokens_values = [row[3] for row in rows if row[3] is not None]
    cache_creation_values = [row[4] for row in rows if row[4] is not None]
    cache_read_values = [row[5] for row in rows if row[5] is not None]
    cache_miss_values = [row[6] for row in rows if row[6] is not None]

    return {
        "request_count": request_count,
        "success_count": success_count,
        "success_rate": (success_count / request_count) if request_count else 0.0,
        "avg_latency_ms": (sum(latencies) / len(latencies)) if latencies else 0.0,
        "p95_latency_ms": _percentile(latencies, 0.95) or 0.0,
        "p99_latency_ms": _percentile(latencies, 0.99) or 0.0,
        "throughput_tokens_per_s": (
            total_completion_tokens / total_latency_seconds
            if total_latency_seconds > 0
            else 0.0
        ),
        "tokens_observed_requests": len(token_rows),
        "total_tokens": sum(total_tokens_values) if total_tokens_values else None,
        "cache_creation_tokens": sum(cache_creation_values) if cache_creation_values else None,
        "cache_read_tokens": sum(cache_read_values) if cache_read_values else None,
        "cache_miss_tokens": sum(cache_miss_values) if cache_miss_values else None,
        "cache_read_observed_requests": len(cache_read_values),
    }


def list_request_logs(
    conn: sqlite3.Connection,
    limit: int = 50,
    *,
    offset: int = 0,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
    query: str | None = None,
    export_all: bool = False,
) -> dict[str, Any]:
    where_parts: list[str] = []
    params: list[Any] = []
    if date_from:
        where_parts.append("created_at >= ?")
        params.append(date_from.replace("T", " "))
    if date_to:
        where_parts.append("created_at <= ?")
        params.append(date_to.replace("T", " "))
    if status and status != "all":
        where_parts.append("status = ?")
        params.append(status)
    if query and query.strip():
        keyword = f"%{query.strip().lower()}%"
        where_parts.append(
            """
            (
                LOWER(request_id) LIKE ?
                OR LOWER(model_name) LIKE ?
                OR LOWER(protocol) LIKE ?
                OR LOWER(COALESCE(auth_source, '')) LIKE ?
                OR LOWER(COALESCE(client_ip, '')) LIKE ?
                OR LOWER(COALESCE(user_agent, '')) LIKE ?
                OR LOWER(COALESCE(rejection_reason, '')) LIKE ?
                OR LOWER(COALESCE(error_message, '')) LIKE ?
            )
            """
        )
        params.extend([keyword] * 8)
    clause = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
    normalized_limit = max(1, min(limit, 500))
    normalized_offset = max(0, offset)
    total = conn.execute(
        f"SELECT COUNT(*) FROM request_logs{clause}",
        params,
    ).fetchone()[0]
    sql = f"""
        SELECT id, request_id, model_name, status, protocol, error_message, created_at, api_key_id, auth_source, client_ip, user_agent, rejection_reason
        FROM request_logs
        {clause}
        ORDER BY id DESC
    """
    query_params: tuple[Any, ...]
    if export_all:
        query_params = tuple(params)
    else:
        sql += "\nLIMIT ? OFFSET ?"
        query_params = (*params, normalized_limit, normalized_offset)
    cursor = conn.execute(sql, query_params)
    rows = cursor.fetchall()
    return {
        "logs": [
            {
                "id": row[0],
                "request_id": row[1],
                "model_name": row[2],
                "status": row[3],
                "protocol": row[4],
                "error_message": row[5],
                "created_at": row[6],
                "api_key_id": row[7],
                "auth_source": row[8],
                "client_ip": row[9],
                "user_agent": row[10],
                "rejection_reason": row[11],
            }
            for row in rows
        ],
        "total": total,
        "limit": normalized_limit,
        "offset": normalized_offset,
    }


def list_agent_events(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    cursor = conn.execute(
        """
        SELECT id, status, reason, event_type, readiness_state, http_ready, inference_ready, metadata_json, created_at
        FROM agent_events
        ORDER BY id DESC
        LIMIT ?
        """,
        (max(1, min(limit, 500)),),
    )
    rows = cursor.fetchall()
    return [
        {
            "id": row[0],
            "status": row[1],
            "reason": row[2],
            "event_type": row[3],
            "readiness_state": row[4],
            "http_ready": bool(row[5]) if row[5] is not None else None,
            "inference_ready": bool(row[6]) if row[6] is not None else None,
            "metadata": json.loads(row[7]) if row[7] else {},
            "created_at": row[8],
        }
        for row in rows
    ]


def get_request_log_detail(conn: sqlite3.Connection, request_id: str) -> dict[str, Any] | None:
    log_row = conn.execute(
        """
        SELECT id, request_id, model_name, status, protocol, error_message, created_at, api_key_id, auth_source, client_ip, user_agent, rejection_reason
        FROM request_logs
        WHERE request_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (request_id,),
    ).fetchone()
    if log_row is None:
        return None
    metrics_row = conn.execute(
        """
        SELECT request_id, model_name, protocol, status, latency_ms, prompt_tokens, completion_tokens,
               total_tokens, tokens_per_second, started_at, finished_at, backend_type, api_key_id,
               cache_creation_tokens, cache_read_tokens, cache_miss_tokens, error_code, status_detail
        FROM request_metrics
        WHERE request_id = ?
        """,
        (request_id,),
    ).fetchone()
    return {
        "request_id": request_id,
        "log": {
            "id": log_row[0],
            "request_id": log_row[1],
            "model_name": log_row[2],
            "status": log_row[3],
            "protocol": log_row[4],
            "error_message": log_row[5],
            "created_at": log_row[6],
            "api_key_id": log_row[7],
            "auth_source": log_row[8],
            "client_ip": log_row[9],
            "user_agent": log_row[10],
            "rejection_reason": log_row[11],
        },
        "metrics": None if metrics_row is None else {
            "request_id": metrics_row[0],
            "model_name": metrics_row[1],
            "protocol": metrics_row[2],
            "status": metrics_row[3],
            "latency_ms": metrics_row[4],
            "prompt_tokens": metrics_row[5],
            "completion_tokens": metrics_row[6],
            "total_tokens": metrics_row[7],
            "tokens_per_second": metrics_row[8],
            "started_at": metrics_row[9],
            "finished_at": metrics_row[10],
            "backend_type": metrics_row[11],
            "api_key_id": metrics_row[12],
            "cache_creation_tokens": metrics_row[13],
            "cache_read_tokens": metrics_row[14],
            "cache_miss_tokens": metrics_row[15],
            "error_code": metrics_row[16],
            "status_detail": metrics_row[17],
        },
    }


def create_api_key(
    conn: sqlite3.Connection,
    *,
    name: str,
    key_hash: str,
    scopes: list[str],
    rpm_limit: int | None = None,
    concurrency_limit: int | None = None,
    status: str = "active",
    note: str | None = None,
) -> dict[str, Any]:
    disabled_at = _now_sql() if status == "disabled" else None
    cursor = conn.execute(
        """
        INSERT INTO api_keys(key_hash, name, status, scopes, rpm_limit, concurrency_limit, disabled_at, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            key_hash,
            name,
            status,
            json.dumps(scopes, ensure_ascii=False),
            rpm_limit,
            concurrency_limit,
            disabled_at,
            note,
        ),
    )
    conn.commit()
    row = conn.execute(
        """
        SELECT id, key_hash, name, status, scopes, rpm_limit, concurrency_limit, created_at, disabled_at, last_used_at, note
        FROM api_keys
        WHERE id = ?
        """,
        (cursor.lastrowid,),
    ).fetchone()
    assert row is not None
    return _decode_api_key_row(row)


def list_api_keys(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cursor = conn.execute(
        """
        SELECT id, key_hash, name, status, scopes, rpm_limit, concurrency_limit, created_at, disabled_at, last_used_at, note
        FROM api_keys
        ORDER BY id DESC
        """
    )
    return [_decode_api_key_row(row) for row in cursor.fetchall()]


def get_api_key_by_hash(conn: sqlite3.Connection, key_hash: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, key_hash, name, status, scopes, rpm_limit, concurrency_limit, created_at, disabled_at, last_used_at, note
        FROM api_keys
        WHERE key_hash = ?
        """,
        (key_hash,),
    ).fetchone()
    return _decode_api_key_row(row) if row else None


def get_api_key_by_id(conn: sqlite3.Connection, key_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, key_hash, name, status, scopes, rpm_limit, concurrency_limit, created_at, disabled_at, last_used_at, note
        FROM api_keys
        WHERE id = ?
        """,
        (key_id,),
    ).fetchone()
    return _decode_api_key_row(row) if row else None


def update_api_key(
    conn: sqlite3.Connection,
    key_id: int,
    *,
    name: str | None | object = _UNSET,
    status: str | None | object = _UNSET,
    scopes: list[str] | None | object = _UNSET,
    rpm_limit: int | None | object = _UNSET,
    concurrency_limit: int | None | object = _UNSET,
    note: str | None | object = _UNSET,
) -> dict[str, Any] | None:
    assignments: list[str] = []
    params: list[Any] = []

    if name is not _UNSET:
        assignments.append("name = ?")
        params.append(name)
    if status is not _UNSET:
        assignments.append("status = ?")
        params.append(status)
        if status == "disabled":
            assignments.append("disabled_at = ?")
            params.append(_now_sql())
        elif status == "active":
            assignments.append("disabled_at = ?")
            params.append(None)
    if scopes is not _UNSET:
        assignments.append("scopes = ?")
        params.append(json.dumps(scopes, ensure_ascii=False))
    if rpm_limit is not _UNSET:
        assignments.append("rpm_limit = ?")
        params.append(rpm_limit)
    if concurrency_limit is not _UNSET:
        assignments.append("concurrency_limit = ?")
        params.append(concurrency_limit)
    if note is not _UNSET:
        assignments.append("note = ?")
        params.append(note)

    if not assignments:
        return get_api_key_by_id(conn, key_id)

    params.append(key_id)
    cursor = conn.execute(
        f"""
        UPDATE api_keys
        SET {", ".join(assignments)}
        WHERE id = ?
        """,
        params,
    )
    conn.commit()
    if cursor.rowcount == 0:
        return None
    return get_api_key_by_id(conn, key_id)


def delete_api_key(conn: sqlite3.Connection, key_id: int) -> bool:
    cursor = conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
    conn.commit()
    return cursor.rowcount > 0


def list_model_routes(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cursor = conn.execute(
        """
        SELECT name, display_name, backend_model, backend_type, enabled
        FROM model_routes
        ORDER BY name
        """
    )
    rows = cursor.fetchall()
    return [
        {
            "name": row[0],
            "display_name": row[1],
            "backend_model": row[2],
            "backend_type": row[3],
            "enabled": bool(row[4]),
        }
        for row in rows
    ]


def seed_model_routes(conn: sqlite3.Connection, routes: list[dict[str, Any]]) -> None:
    desired_names = {route["name"] for route in routes}
    if desired_names:
        placeholders = ",".join("?" for _ in desired_names)
        conn.execute(
            f"DELETE FROM model_routes WHERE name NOT IN ({placeholders})",
            tuple(desired_names),
        )
    else:
        conn.execute("DELETE FROM model_routes")
    for route in routes:
        conn.execute(
            """
            INSERT INTO model_routes(name, display_name, backend_model, backend_type, enabled)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                display_name=excluded.display_name,
                backend_model=excluded.backend_model,
                backend_type=excluded.backend_type,
                enabled=excluded.enabled
            """,
            (
                route["name"],
                route["display_name"],
                route["backend_model"],
                route["backend_type"],
                int(bool(route.get("enabled", True))),
            ),
        )
    conn.commit()


def upsert_model_route(conn: sqlite3.Connection, route: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO model_routes(name, display_name, backend_model, backend_type, enabled)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            display_name=excluded.display_name,
            backend_model=excluded.backend_model,
            backend_type=excluded.backend_type,
            enabled=excluded.enabled
        """,
        (
            route["name"],
            route["display_name"],
            route["backend_model"],
            route["backend_type"],
            int(bool(route.get("enabled", True))),
        ),
    )
    conn.commit()


def load_schedule_config(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT timezone, work_days, start_time, end_time, auto_stop_enabled, auto_start_enabled, cooldown_minutes
        FROM schedule_config
        WHERE id = 1
        """
    ).fetchone()
    if not row:
        return None
    return {
        "timezone": row[0],
        "work_days": json.loads(row[1]),
        "start_time": row[2],
        "end_time": row[3],
        "auto_stop_enabled": bool(row[4]),
        "auto_start_enabled": bool(row[5]),
        "cooldown_minutes": row[6],
    }


def upsert_schedule_config(conn: sqlite3.Connection, schedule: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO schedule_config(
            id, timezone, work_days, start_time, end_time, auto_stop_enabled, auto_start_enabled, cooldown_minutes
        )
        VALUES (1, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            timezone=excluded.timezone,
            work_days=excluded.work_days,
            start_time=excluded.start_time,
            end_time=excluded.end_time,
            auto_stop_enabled=excluded.auto_stop_enabled,
            auto_start_enabled=excluded.auto_start_enabled,
            cooldown_minutes=excluded.cooldown_minutes
        """,
        (
            schedule["timezone"],
            json.dumps(schedule.get("work_days", []), ensure_ascii=False),
            schedule["start_time"],
            schedule["end_time"],
            int(bool(schedule.get("auto_stop_enabled", True))),
            int(bool(schedule.get("auto_start_enabled", True))),
            int(schedule.get("cooldown_minutes", 10)),
        ),
    )
    conn.commit()


def aggregate_usage_for_api_key(conn: sqlite3.Connection, api_key_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS request_count,
               COALESCE(SUM(total_tokens), 0) AS total_tokens,
               SUM(cache_read_tokens) AS cache_read_tokens,
               COUNT(cache_read_tokens) AS cache_read_observed_requests
        FROM request_metrics
        WHERE api_key_id = ?
        """,
        (api_key_id,),
    ).fetchone()
    return {
        "summary": {
            "api_key_id": api_key_id,
            "request_count": row[0] if row else 0,
            "total_requests": row[0] if row else 0,
            "total_tokens": row[1] if row else 0,
            "cache_read_tokens": row[2] if row else None,
            "cache_read_observed_requests": row[3] if row else 0,
        },
    }


_ALLOWED_GROUP_BY = {"model_name", "backend_type", "api_key_id", "protocol", "status"}


def _parse_iso_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _truncate_bucket_start(value: datetime, *, window: str) -> datetime:
    value = value.astimezone(timezone.utc)
    if window in {"12h", "day"}:
        return value.replace(minute=0, second=0, microsecond=0)
    if window == "month":
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    if window == "year":
        return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"unsupported window: {window}")


def _advance_bucket(value: datetime, *, window: str, steps: int = 1) -> datetime:
    if window in {"12h", "day"}:
        return value + timedelta(hours=steps)
    if window == "month":
        return value + timedelta(days=steps)
    if window == "year":
        year = value.year
        month = value.month
        total = (year * 12 + (month - 1)) + steps
        next_year, month_index = divmod(total, 12)
        return value.replace(year=next_year, month=month_index + 1, day=1)
    raise ValueError(f"unsupported window: {window}")


def _window_bucket_count(window: str) -> int:
    return {
        "12h": 12,
        "day": 24,
        "month": 30,
        "year": 12,
    }[window]


def _format_bucket_key(value: datetime, *, window: str) -> str:
    if window in {"12h", "day"}:
        return value.strftime("%Y-%m-%d %H:00")
    if window == "month":
        return value.strftime("%Y-%m-%d")
    if window == "year":
        return value.strftime("%Y-%m")
    raise ValueError(f"unsupported window: {window}")


def _format_bucket_label(value: datetime, *, window: str) -> str:
    if window == "12h":
        return value.strftime("%H:%M")
    if window == "day":
        return value.strftime("%m-%d %H:%M")
    if window == "month":
        return value.strftime("%m-%d")
    if window == "year":
        return value.strftime("%Y-%m")
    raise ValueError(f"unsupported window: {window}")


def _device_type_from_user_agent(user_agent: str | None) -> str:
    if not user_agent:
        return "unknown"
    lowered = user_agent.lower()
    if any(token in lowered for token in ("iphone", "android", "mobile", "ipad", "tablet")):
        return "mobile"
    if any(token in lowered for token in ("curl", "postman", "insomnia", "python", "httpie", "wget")):
        return "tool"
    if any(token in lowered for token in ("mozilla", "chrome", "safari", "firefox", "edge", "macintosh", "windows", "linux")):
        return "desktop"
    return "unknown"


def _group_label(group_by: str, value: str | None) -> str:
    if group_by == "backend_type":
        mapping = {
            "vllm": "vLLM",
            "llama.cpp": "llama.cpp",
            "sglang": "SGLang",
            None: "Unknown",
            "": "Unknown",
        }
        return mapping.get(value, str(value))
    if group_by == "device_type":
        mapping = {
            "desktop": "Desktop",
            "mobile": "Mobile",
            "tool": "Tool",
            "unknown": "Unknown",
            None: "Unknown",
            "": "Unknown",
        }
        return mapping.get(value, str(value))
    return str(value or "Unknown")


def _empty_usage_totals() -> dict[str, int]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "cache_miss_tokens": 0,
        "cache_tokens": 0,
        "total_tokens": 0,
    }


def _accumulate_usage_totals(target: dict[str, int], row: dict[str, Any]) -> None:
    prompt_tokens = int(row.get("prompt_tokens") or 0)
    completion_tokens = int(row.get("completion_tokens") or 0)
    cache_creation_tokens = int(row.get("cache_creation_tokens") or 0)
    cache_read_tokens = int(row.get("cache_read_tokens") or 0)
    cache_miss_tokens = int(row.get("cache_miss_tokens") or 0)
    total_tokens = int(row.get("total_tokens") or 0)
    target["prompt_tokens"] += prompt_tokens
    target["completion_tokens"] += completion_tokens
    target["cache_creation_tokens"] += cache_creation_tokens
    target["cache_read_tokens"] += cache_read_tokens
    target["cache_miss_tokens"] += cache_miss_tokens
    target["cache_tokens"] += cache_creation_tokens + cache_read_tokens + cache_miss_tokens
    target["total_tokens"] += total_tokens


def aggregate_usage_chart(
    conn: sqlite3.Connection,
    *,
    window: str = "12h",
    group_by: str = "backend_type",
    now: str | None = None,
) -> dict[str, Any]:
    if window not in _ALLOWED_CHART_WINDOWS:
        raise ValueError(f"unsupported window: {window}")
    if group_by not in _ALLOWED_CHART_GROUP_BY:
        raise ValueError(f"unsupported group_by: {group_by}")

    current = _parse_iso_datetime(now) if now else datetime.now(timezone.utc)
    bucket_end = _advance_bucket(_truncate_bucket_start(current, window=window), window=window)
    bucket_count = _window_bucket_count(window)
    bucket_starts = [
        _advance_bucket(bucket_end, window=window, steps=offset - bucket_count)
        for offset in range(bucket_count)
    ]
    bucket_keys = [_format_bucket_key(item, window=window) for item in bucket_starts]
    bucket_labels = {
        _format_bucket_key(item, window=window): _format_bucket_label(item, window=window)
        for item in bucket_starts
    }
    bucket_index = {key: idx for idx, key in enumerate(bucket_keys)}
    range_start = bucket_starts[0].isoformat()
    range_end = bucket_end.isoformat()

    rows = conn.execute(
        """
        SELECT m.request_id,
               m.started_at,
               m.model_name,
               m.backend_type,
               m.prompt_tokens,
               m.completion_tokens,
               m.total_tokens,
               m.cache_creation_tokens,
               m.cache_read_tokens,
               m.cache_miss_tokens,
               l.user_agent
        FROM request_metrics AS m
        LEFT JOIN request_logs AS l ON l.request_id = m.request_id
        WHERE m.started_at >= ? AND m.started_at < ?
        ORDER BY m.started_at ASC
        """,
        (range_start, range_end),
    ).fetchall()

    overall_points = [
        {
            "bucket": bucket_key,
            "label": bucket_labels[bucket_key],
            "request_count": 0,
            **_empty_usage_totals(),
        }
        for bucket_key in bucket_keys
    ]
    overall_totals = _empty_usage_totals()
    grouped: dict[str, dict[str, Any]] = {}

    for row in rows:
        started_at = _parse_iso_datetime(row[1])
        bucket_key = _format_bucket_key(_truncate_bucket_start(started_at, window=window), window=window)
        if bucket_key not in bucket_index:
            continue
        metric_row = {
            "prompt_tokens": row[4],
            "completion_tokens": row[5],
            "total_tokens": row[6],
            "cache_creation_tokens": row[7],
            "cache_read_tokens": row[8],
            "cache_miss_tokens": row[9],
        }
        if group_by == "backend_type":
            group_value = row[3] or "unknown"
        elif group_by == "model_name":
            group_value = row[2] or "unknown"
        else:
            group_value = _device_type_from_user_agent(row[10])

        if group_value not in grouped:
            grouped[group_value] = {
                "group": group_value,
                "label": _group_label(group_by, group_value),
                "totals": _empty_usage_totals(),
                "points": [
                    {
                        "bucket": key,
                        "label": bucket_labels[key],
                        "request_count": 0,
                        **_empty_usage_totals(),
                    }
                    for key in bucket_keys
                ],
            }

        point = grouped[group_value]["points"][bucket_index[bucket_key]]
        point["request_count"] += 1
        overall_points[bucket_index[bucket_key]]["request_count"] += 1
        _accumulate_usage_totals(point, metric_row)
        _accumulate_usage_totals(overall_points[bucket_index[bucket_key]], metric_row)
        _accumulate_usage_totals(grouped[group_value]["totals"], metric_row)
        _accumulate_usage_totals(overall_totals, metric_row)

    groups = sorted(
        grouped.values(),
        key=lambda item: (item["totals"]["total_tokens"], item["totals"]["prompt_tokens"]),
        reverse=True,
    )

    return {
        "window": window,
        "group_by": group_by,
        "totals": overall_totals,
        "points": overall_points,
        "groups": groups,
    }


def aggregate_usage_trend(conn: sqlite3.Connection, *, granularity: str = "day") -> list[dict[str, Any]]:
    bucket_expr = {
        "day": "substr(started_at, 1, 10)",
        "month": "substr(started_at, 1, 7)",
        "year": "substr(started_at, 1, 4)",
    }[granularity]
    rows = conn.execute(
        f"""
        SELECT {bucket_expr} AS bucket,
               COUNT(*) AS request_count,
               COALESCE(SUM(total_tokens), 0) AS total_tokens,
               SUM(cache_read_tokens) AS cache_read_tokens,
               COUNT(cache_read_tokens) AS cache_read_observed
        FROM request_metrics
        GROUP BY 1
        ORDER BY 1
        """
    ).fetchall()
    return [
        {
            "bucket": row[0],
            "request_count": row[1],
            "total_tokens": row[2],
            "cache_read_tokens": row[3],
            "cache_read_observed": row[4],
        }
        for row in rows
    ]


def aggregate_usage_breakdown(conn: sqlite3.Connection, *, group_by: str) -> list[dict[str, Any]]:
    if group_by not in _ALLOWED_GROUP_BY:
        raise ValueError(f"unsupported group_by: {group_by}")
    rows = conn.execute(
        f"""
        SELECT {group_by} AS grouping_value,
               COUNT(*) AS request_count,
               COALESCE(SUM(total_tokens), 0) AS total_tokens,
               SUM(cache_read_tokens) AS cache_read_tokens,
               COUNT(cache_read_tokens) AS cache_read_observed
        FROM request_metrics
        GROUP BY 1
        ORDER BY total_tokens DESC
        """
    ).fetchall()
    return [
        {
            "group": row[0],
            "request_count": row[1],
            "total_tokens": row[2],
            "cache_read_tokens": row[3],
            "cache_read_observed": row[4],
        }
        for row in rows
    ]
