from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_UNSET = object()


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
    return f"ln_saved_{key_id}"


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
            finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        ),
    )
    conn.commit()


def _percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * ratio) - 1))
    return ordered[index]


def aggregate_request_metrics(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT status, latency_ms, completion_tokens
        FROM request_metrics
        ORDER BY created_at ASC
        """
    ).fetchall()
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
    }


def list_request_logs(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    cursor = conn.execute(
        """
        SELECT id, request_id, model_name, status, protocol, error_message, created_at, api_key_id, auth_source, client_ip, user_agent, rejection_reason
        FROM request_logs
        ORDER BY id DESC
        LIMIT ?
        """,
        (max(1, min(limit, 500)),),
    )
    rows = cursor.fetchall()
    return [
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
    ]


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
        SELECT COUNT(*) AS total_requests,
               COALESCE(SUM(total_tokens), 0) AS total_tokens
        FROM request_metrics rm
        JOIN request_logs rl ON rm.request_id = rl.request_id
        WHERE rl.api_key_id = ?
        """,
        (api_key_id,),
    ).fetchone()
    return {
        "summary": {
            "total_requests": row[0] if row else 0,
            "total_tokens": row[1] if row else 0,
        },
    }
