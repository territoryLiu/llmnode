from datetime import datetime, timezone
from pathlib import Path

from llmnode.storage.db import cleanup_retention, init_db


def test_cleanup_retention_dry_run_then_execute_uses_table_specific_ttls(tmp_path: Path):
    conn = init_db(tmp_path / "retention.db")
    conn.executemany(
        "INSERT INTO request_logs(request_id, model_name, status, protocol, created_at) VALUES (?, ?, ?, ?, ?)",
        [
            ("old-log", "demo", "ok", "openai", "2026-01-01 00:00:00"),
            ("new-log", "demo", "ok", "openai", "2026-08-18 00:00:00"),
        ],
    )
    conn.commit()
    now = datetime(2026, 8, 19, tzinfo=timezone.utc)
    policies = {"request_logs": 30}

    preview = cleanup_retention(conn, policies, tables=["request_logs"], now=now)
    assert preview["dry_run"] is True
    assert preview["tables"]["request_logs"]["eligible"] == 1
    assert conn.execute("SELECT COUNT(*) FROM request_logs").fetchone()[0] == 2

    result = cleanup_retention(conn, policies, tables=["request_logs"], dry_run=False, now=now)
    assert result["total_deleted"] == 1
    assert conn.execute("SELECT request_id FROM request_logs").fetchone()[0] == "new-log"


def test_response_state_retention_uses_updated_at(tmp_path: Path):
    conn = init_db(tmp_path / "retention.db")
    conn.execute(
        """INSERT INTO response_states(
            response_id, request_id, model_name, input_items_json, output_items_json,
            messages_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("r1", "q1", "demo", "[]", "[]", "[]", "2026-01-01 00:00:00", "2026-08-18 00:00:00"),
    )
    conn.commit()
    result = cleanup_retention(
        conn,
        {"response_states": 7},
        tables=["response_states"],
        dry_run=False,
        now=datetime(2026, 8, 19, tzinfo=timezone.utc),
    )
    assert result["total_deleted"] == 0
    assert conn.execute("SELECT COUNT(*) FROM response_states").fetchone()[0] == 1
