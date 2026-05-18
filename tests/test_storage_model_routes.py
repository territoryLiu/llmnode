from pathlib import Path

from llmnode.storage.db import init_db, list_model_routes, seed_model_routes, upsert_model_route


def test_seed_model_routes_reconciles_existing_rows(tmp_path: Path):
    conn = init_db(tmp_path / "gateway.db")
    upsert_model_route(
        conn,
        {
            "name": "qwen36-35b-a3b",
            "display_name": "Stale Model",
            "backend_model": "qwen36-35b-a3b",
            "backend_type": "vllm",
            "enabled": True,
        },
    )
    upsert_model_route(
        conn,
        {
            "name": "stale-alias",
            "display_name": "Stale Alias",
            "backend_model": "qwen36-35b-a3b",
            "backend_type": "vllm",
            "enabled": True,
        },
    )

    seed_model_routes(
        conn,
        [
            {
                "name": "qwen36-35b-a3b-fp8",
                "display_name": "Qwen3.6 35B A3B FP8",
                "backend_model": "qwen36-35b-a3b-fp8",
                "backend_type": "vllm",
                "enabled": True,
            },
        ],
    )

    routes = {item["name"]: item for item in list_model_routes(conn)}
    assert routes["qwen36-35b-a3b"]["stale"] is True
    assert routes["qwen36-35b-a3b"]["enabled"] is False
    assert routes["stale-alias"]["stale"] is True
    assert routes["stale-alias"]["enabled"] is False
    assert routes["qwen36-35b-a3b-fp8"]["backend_model"] == "qwen36-35b-a3b-fp8"
    assert routes["qwen36-35b-a3b-fp8"]["stale"] is False


def test_seed_model_routes_keeps_manual_routes_and_marks_old_profile_routes_stale(tmp_path: Path):
    conn = init_db(tmp_path / "gateway.db")
    upsert_model_route(
        conn,
        {
            "name": "manual-openai",
            "display_name": "Manual OpenAI",
            "backend_model": None,
            "backend_type": None,
            "enabled": True,
            "lifecycle_mode": "external",
            "upstream_protocol": "responses",
            "upstream_base_url": "https://api.openai.com/v1",
            "upstream_model": "gpt-4.1",
            "upstream_auth_kind": "bearer",
            "upstream_auth_ref": "OPENAI_KEY",
            "capabilities_json": {"supports_responses": True},
            "source_kind": "manual",
            "source_ref": None,
            "stale": 0,
        },
    )
    upsert_model_route(
        conn,
        {
            "name": "old-seeded",
            "display_name": "Old Seeded",
            "backend_model": "old-model",
            "backend_type": "vllm",
            "enabled": True,
            "lifecycle_mode": "managed_local",
            "upstream_protocol": "chat",
            "upstream_base_url": "http://127.0.0.1:8000/v1",
            "upstream_model": "old-model",
            "upstream_auth_kind": "none",
            "upstream_auth_ref": None,
            "capabilities_json": {},
            "source_kind": "profile_seed",
            "source_ref": "old_profile",
            "stale": 0,
        },
    )

    events = seed_model_routes(
        conn,
        [
            {
                "name": "new-seeded",
                "display_name": "New Seeded",
                "backend_model": "new-model",
                "backend_type": "vllm",
                "enabled": True,
                "lifecycle_mode": "managed_local",
                "upstream_protocol": "chat",
                "upstream_base_url": "http://127.0.0.1:9000/v1",
                "upstream_model": "new-model",
                "upstream_auth_kind": "none",
                "upstream_auth_ref": None,
                "capabilities_json": {},
                "source_kind": "profile_seed",
                "source_ref": "new_profile",
                "stale": 0,
            },
        ],
    )

    routes = {item["name"]: item for item in list_model_routes(conn)}
    event_by_type = {item["event_type"]: item for item in events}
    assert routes["manual-openai"]["source_kind"] == "manual"
    assert routes["manual-openai"]["enabled"] is True
    assert routes["old-seeded"]["stale"] is True
    assert routes["old-seeded"]["enabled"] is False
    assert routes["new-seeded"]["source_ref"] == "new_profile"
    assert event_by_type["route_manual_preserved"]["metadata"] == {
        "route_name": "manual-openai",
        "source_kind": "manual",
        "source_ref": None,
        "action": "preserved",
    }
    assert event_by_type["route_marked_stale"]["metadata"] == {
        "route_name": "old-seeded",
        "source_kind": "profile_seed",
        "source_ref": "old_profile",
        "action": "marked_stale",
    }
