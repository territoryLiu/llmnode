from pathlib import Path

import pytest
from fastapi import HTTPException

from llmnode.models import ModelCapabilities, ModelRoute, model_route_from_row, model_routes_for_admin
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


def test_managed_local_vllm_route_derives_native_protocols():
    route = ModelRoute(
        name="qwen36-27b-awq-int4",
        display_name="Qwen",
        backend_model="qwen36-27b-awq-int4",
        backend_type="vllm",
        lifecycle_mode="managed_local",
    )

    runtime = route.runtime_capabilities()

    assert runtime["native_protocols"] == ["chat", "responses", "messages"]
    assert runtime["adapter_policies"] == []
    assert runtime["tool_policies"]["anthropic_function_tools"] is True
    assert runtime["tool_policies"]["builtin_tools"] is False


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
    runtime_caps = {
        "native_protocols": ["chat"],
        "adapter_policies": ["responses->chat"],
        "tool_policies": {
            "openai_function_tools": True,
            "anthropic_function_tools": True,
            "builtin_tools": False,
        },
        "protocol_features": {"stream": True},
    }
    assert select_upstream_adapter(route, req, runtime_caps=runtime_caps) == "responses_to_chat"


def test_route_rejects_messages_when_not_in_native_protocols():
    route = ModelRoute(
        name="chat-only",
        display_name="Chat Only",
        lifecycle_mode="external",
        upstream_protocol="chat",
    )
    route_runtime = {
        "native_protocols": ["chat"],
        "adapter_policies": [],
        "tool_policies": {
            "openai_function_tools": True,
            "anthropic_function_tools": False,
            "builtin_tools": False,
        },
        "protocol_features": {"stream": True},
    }

    req = NormalizedRequest(client_protocol="messages", model="chat-only", messages=[])

    with pytest.raises(HTTPException) as exc_info:
        ensure_route_supports_request(route, req, runtime_caps=route_runtime)

    assert exc_info.value.detail == "native_protocol_not_supported"


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
    assert exc_info.value.detail == "builtin_tools_not_supported"


def test_model_route_persists_native_protocols_and_tool_policies(tmp_path: Path):
    conn = init_db(tmp_path / "gateway.db")
    upsert_model_route(
        conn,
        {
            "name": "qwen36-27b-awq-int4",
            "display_name": "Qwen",
            "backend_model": "qwen36-27b-awq-int4",
            "backend_type": "vllm",
            "enabled": True,
            "lifecycle_mode": "managed_local",
            "upstream_protocol": "chat",
            "native_protocols_json": ["chat", "responses", "messages"],
            "adapter_policies_json": [],
            "tool_policies_json": {
                "openai_function_tools": True,
                "anthropic_function_tools": True,
                "builtin_tools": False,
            },
            "protocol_features_json": {
                "stream": True,
                "count_tokens": True,
                "json_schema": False,
                "previous_response_id": True,
            },
            "capabilities_json": {
                "supports_responses": True,
                "supports_chat": True,
                "supports_messages": True,
                "supports_stream": True,
                "supports_function_tools": True,
                "supports_builtin_tools": False,
                "supports_previous_response_id_native": True,
                "supports_json_schema": False,
            },
        },
    )

    row = list_model_routes(conn)[0]

    assert row["native_protocols_json"] == ["chat", "responses", "messages"]
    assert row["adapter_policies_json"] == []
    assert row["tool_policies_json"]["anthropic_function_tools"] is True
    assert row["protocol_features_json"]["count_tokens"] is True


def test_model_route_runtime_capabilities_prefer_persisted_runtime_fields():
    route = model_route_from_row(
        {
            "name": "anthropic-claude",
            "display_name": "Anthropic Claude",
            "backend_model": None,
            "backend_type": None,
            "enabled": True,
            "lifecycle_mode": "external",
            "upstream_protocol": "messages",
            "upstream_base_url": "https://api.anthropic.com",
            "upstream_model": "claude-sonnet",
            "upstream_auth_kind": "x_api_key",
            "upstream_auth_ref": "ANTHROPIC_KEY",
            "capabilities_json": {
                "supports_responses": False,
                "supports_chat": False,
                "supports_messages": True,
                "supports_stream": True,
                "supports_function_tools": True,
                "supports_builtin_tools": False,
                "supports_previous_response_id_native": False,
                "supports_json_schema": False,
            },
            "native_protocols_json": ["messages", "responses"],
            "adapter_policies_json": ["responses->messages"],
            "tool_policies_json": {
                "openai_function_tools": False,
                "anthropic_function_tools": True,
                "builtin_tools": False,
            },
            "protocol_features_json": {
                "stream": True,
                "count_tokens": True,
                "json_schema": True,
                "previous_response_id": True,
            },
        }
    )

    runtime = route.runtime_capabilities()

    assert runtime["native_protocols"] == ["messages", "responses"]
    assert runtime["adapter_policies"] == ["responses->messages"]
    assert runtime["tool_policies"]["openai_function_tools"] is False
    assert runtime["tool_policies"]["anthropic_function_tools"] is True
    assert runtime["protocol_features"]["json_schema"] is True
    assert runtime["protocol_features"]["previous_response_id"] is True


def test_model_route_admin_payload_includes_recommended_runtime_semantics():
    route = ModelRoute(
        name="anthropic-claude",
        display_name="Anthropic Claude",
        backend_model=None,
        backend_type=None,
        enabled=True,
        lifecycle_mode="external",
        upstream_protocol="messages",
        upstream_base_url="https://api.anthropic.com",
        upstream_model="claude-sonnet",
        upstream_auth_kind="x_api_key",
        upstream_auth_ref="ANTHROPIC_KEY",
        capabilities=ModelCapabilities(
            supports_responses=False,
            supports_chat=False,
            supports_messages=True,
            supports_stream=True,
            supports_function_tools=True,
            supports_builtin_tools=False,
            supports_previous_response_id_native=False,
            supports_json_schema=False,
        ),
    )

    payload = model_routes_for_admin({"anthropic-claude": route})[0]

    assert payload["recommended_runtime_semantics"] == {
        "native_protocols_json": ["messages"],
        "adapter_policies_json": [],
        "protocol_features_json": {
            "stream": True,
            "count_tokens": True,
            "json_schema": False,
            "previous_response_id": False,
        },
    }
