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
    assert "qwen36-35b-a3b" not in routes
    assert "stale-alias" not in routes
    assert routes["qwen36-35b-a3b-fp8"]["backend_model"] == "qwen36-35b-a3b-fp8"
