from pathlib import Path
import sqlite3

from llmnode.storage.db import (
    create_api_key,
    delete_api_key,
    get_api_key_by_hash,
    get_api_key_by_id,
    init_db,
    list_api_keys,
    mask_api_key,
    stable_masked_key,
    update_api_key,
)
from llmnode.security import hash_api_key


def test_create_and_list_api_keys(tmp_path: Path):
    conn = init_db(tmp_path / "gateway.db")
    row = create_api_key(
        conn,
        name="console-admin",
        key_hash="hash-1",
        scopes=["admin"],
        rpm_limit=None,
        concurrency_limit=None,
        note="main key",
    )
    assert row["name"] == "console-admin"
    rows = list_api_keys(conn)
    assert len(rows) == 1
    assert rows[0]["key_hash"] == "hash-1"
    assert "plain_secret" not in rows[0]
    assert rows[0]["note"] == "main key"


def test_lookup_api_key_by_hash(tmp_path: Path):
    conn = init_db(tmp_path / "gateway.db")
    create_api_key(
        conn,
        name="worker",
        key_hash="hash-2",
        scopes=["inference"],
        rpm_limit=60,
        concurrency_limit=2,
    )
    row = get_api_key_by_hash(conn, "hash-2")
    assert row is not None
    assert row["name"] == "worker"
    assert row["status"] == "active"
    assert row["rpm_limit"] == 60


def test_update_status_round_trip(tmp_path: Path):
    conn = init_db(tmp_path / "gateway.db")
    row = create_api_key(
        conn,
        name="worker",
        key_hash="hash-3",
        scopes=["inference"],
    )
    disabled = update_api_key(conn, row["id"], status="disabled")
    assert disabled is not None
    assert disabled["status"] == "disabled"
    assert disabled["disabled_at"] is not None

    enabled = update_api_key(conn, row["id"], status="active")
    assert enabled is not None
    assert enabled["status"] == "active"
    assert enabled["disabled_at"] is None


def test_delete_api_key(tmp_path: Path):
    conn = init_db(tmp_path / "gateway.db")
    row = create_api_key(
        conn,
        name="temp",
        key_hash="hash-4",
        scopes=["inference"],
    )
    assert delete_api_key(conn, row["id"]) is True
    assert get_api_key_by_id(conn, row["id"]) is None
    assert delete_api_key(conn, row["id"]) is False


def test_scopes_json_round_trip(tmp_path: Path):
    conn = init_db(tmp_path / "gateway.db")
    row = create_api_key(
        conn,
        name="hybrid",
        key_hash="hash-5",
        scopes=["admin", "inference"],
        note="dual scope",
    )
    assert row["scopes"] == ["admin", "inference"]
    updated = update_api_key(conn, row["id"], scopes=["inference"], note=None)
    assert updated is not None
    assert updated["scopes"] == ["inference"]
    assert updated["note"] is None


def test_mask_api_key_masks_long_secrets():
    secret = "sk-eac3308ba6ef32875698a0a75d06bb71e7ded2a843ff03e16b98136cb0dd996c"
    masked = mask_api_key(secret)
    assert masked.startswith("sk-")
    assert "***" in masked
    assert masked.endswith("996c")
    assert masked != secret


def test_mask_api_key_returns_short_secrets_unchanged():
    short = "sk-1234"
    assert mask_api_key(short) == short


def test_stable_masked_key_uses_sk_prefix_and_id_suffix():
    assert stable_masked_key(1).startswith("sk-")
    assert stable_masked_key(42).startswith("sk-")
    assert stable_masked_key(1).endswith("0001")
    assert stable_masked_key(42).endswith("0042")
    assert stable_masked_key(1) == stable_masked_key(1)


def test_legacy_plain_secret_column_is_migrated_to_admin_file(tmp_path: Path):
    db_path = tmp_path / "gateway.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE api_keys (id INTEGER PRIMARY KEY, key_hash TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL, scopes TEXT NOT NULL, rpm_limit INTEGER, concurrency_limit INTEGER, created_at TEXT, disabled_at TEXT, last_used_at TEXT, note TEXT, plain_secret TEXT)")
    secret = "sk-legacy-admin"
    conn.execute("INSERT INTO api_keys(key_hash,name,status,scopes,plain_secret) VALUES (?,?,?,?,?)", (hash_api_key(secret), "admin", "active", '["admin"]', secret))
    conn.commit()
    conn.close()

    migrated = init_db(db_path)
    columns = {row[1] for row in migrated.execute("PRAGMA table_info(api_keys)")}
    assert "plain_secret" not in columns
    assert migrated.execute("SELECT count(*) FROM api_keys").fetchone()[0] == 1
    assert (tmp_path / "admin.key").read_text(encoding="utf-8").strip() == secret
    assert (tmp_path / "admin.key").stat().st_mode & 0o777 == 0o600
    assert db_path.stat().st_mode & 0o777 == 0o600
    assert db_path.parent.stat().st_mode & 0o777 == 0o700
