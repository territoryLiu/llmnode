from pathlib import Path

import pytest
from fastapi import HTTPException

from llmnode.models import ModelCapabilities, ModelRoute
from llmnode.proxy.executor import NormalizedRequest
from llmnode.proxy.router import ensure_route_supports_request, select_upstream_adapter
from llmnode.storage.db import init_db, list_model_routes, upsert_model_route


def test_model_route_supports_upstream_protocol_fields(tmp_path: Path):
    conn = init_db(tmp_path / "gateway.db")
    upsert_model_route(
        conn,
        {
            "name": "gpt-4o",
            "display_name": "GPT-4o",
            "enabled": True,
            "lifecycle_mode": "external",
            "backend_type": None,
            "backend_model": None,
            "upstream_protocol": "responses",
            "upstream_base_url": "https://api.openai.com/v1",
            "upstream_model": "gpt-4o",
            "upstream_auth_kind": "bearer",
            "upstream_auth_ref": "openai-prod",
            "capabilities_json": {
                "supports_responses": True,
                "supports_chat": True,
                "supports_messages": False,
                "supports_stream": True,
                "supports_function_tools": True,
                "supports_builtin_tools": True,
                "supports_previous_response_id_native": True,
                "supports_json_schema": True,
            },
        },
    )
    row = list_model_routes(conn)[0]
    assert row["lifecycle_mode"] == "external"
    assert row["upstream_protocol"] == "responses"
    assert row["upstream_auth_kind"] == "bearer"
    assert row["upstream_auth_ref"] == "openai-prod"
    assert row["capabilities_json"]["supports_previous_response_id_native"] is True


def test_model_route_defaults_keep_managed_local_chat_shape():
    route = ModelRoute(
        name="qwen36-27b-fp8",
        display_name="Qwen 27B FP8",
        backend_model="qwen36-27b-fp8",
    )
    assert route.lifecycle_mode == "managed_local"
    assert route.upstream_protocol == "chat"
    assert route.resolved_upstream_model() == "qwen36-27b-fp8"


def test_chat_native_route_selects_responses_to_chat_adapter():
    route = ModelRoute(
        name="qwen36-27b-fp8",
        display_name="Qwen",
        backend_model="qwen36-27b-fp8",
        upstream_protocol="chat",
        capabilities=ModelCapabilities(
            supports_responses=False,
            supports_chat=True,
            supports_stream=True,
            supports_function_tools=True,
        ),
    )
    req = NormalizedRequest(client_protocol="responses", model="qwen36-27b-fp8", messages=[])
    assert select_upstream_adapter(route, req) == "responses_to_chat"


def test_chat_native_route_rejects_builtin_tools():
    route = ModelRoute(
        name="qwen36-27b-fp8",
        display_name="Qwen",
        backend_model="qwen36-27b-fp8",
        upstream_protocol="chat",
        capabilities=ModelCapabilities(
            supports_builtin_tools=False,
            supports_function_tools=True,
        ),
    )
    req = NormalizedRequest(
        client_protocol="responses",
        model="qwen36-27b-fp8",
        messages=[],
        tools=[{"type": "web_search"}],
    )
    with pytest.raises(HTTPException) as exc_info:
        ensure_route_supports_request(route, req)
    assert exc_info.value.detail == "unsupported_builtin_tools"
