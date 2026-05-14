from pathlib import Path

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
    secret = "ln_live_abc123def456ghi789jkl012mno345"
    masked = mask_api_key(secret)
    assert masked.startswith("ln_liv")
    assert "***" in masked
    assert masked.endswith("o345")
    assert masked != secret


def test_mask_api_key_returns_short_secrets_unchanged():
    short = "ln_1234"
    assert mask_api_key(short) == short


def test_stable_masked_key_is_deterministic():
    assert stable_masked_key(1) == "ln_saved_1"
    assert stable_masked_key(42) == "ln_saved_42"
    assert stable_masked_key(1) == stable_masked_key(1)
