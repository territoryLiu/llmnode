from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import sqlite3
import uuid
from contextlib import suppress
from dataclasses import asdict, replace
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, PlainTextResponse

from ..config import PROJECT_ROOT, load_settings
from ..logging import setup_logging
from ..models import ModelCapabilities, ModelRoute, load_model_catalog, logical_models_for_api, model_route_from_row, model_routes_for_admin
from ..protocols import AnthropicMessagesRequest, OpenAIChatCompletionsRequest, OpenAIResponsesRequest
from ..proxy.backend import VLLMBackendClient, post_json_to, stream_bytes_from
from ..proxy.adapters import build_responses_chat_payload, build_responses_messages_payload
from ..proxy.router import (
    AuthContext,
    GatewayContext,
    build_upstream_headers,
    is_anthropic_function_tool,
    proxy_anthropic_messages,
    proxy_openai_chat,
    proxy_openai_chat_via_route,
    plan_route_execution,
    ensure_route_supports_request,
    resolve_route,
    require_scope,
    resolve_auth_context,
    select_upstream_adapter,
    strip_claude_code_builtin_tools_for_managed_messages,
    stream_anthropic_messages,
    stream_openai_chat,
    stream_openai_chat_via_route,
)

_VALID_BACKEND_TYPES = {"vllm", "llama.cpp", "sglang"}
from ..runtime import QueueFullError, QueueTimeoutError, RequestGate
from ..runtime import ApiKeyConcurrencyError, ApiKeyGate, ApiKeyRateLimitError
from ..security import generate_api_key, hash_api_key
from ..storage.db import (
    aggregate_request_metrics,
    aggregate_usage_breakdown,
    aggregate_usage_chart,
    aggregate_usage_for_api_key,
    aggregate_usage_trend,
    create_api_key,
    delete_api_key,
    delete_model_route,
    get_api_key_by_id,
    get_request_log_detail,
    get_response_state,
    init_db,
    list_agent_events,
    list_api_keys,
    list_model_routes,
    list_request_logs,
    load_schedule_config,
    mask_api_key,
    seed_model_routes,
    stable_masked_key,
    update_api_key,
    upsert_response_state,
    upsert_model_route,
    upsert_schedule_config,
    write_agent_event,
    write_request_metric,
    write_request_log,
)

_MISSING = object()
_ALLOWED_SCOPES = {"admin", "inference"}
_ALLOWED_STATUSES = {"active", "disabled"}
_VALID_LIFECYCLE_MODES = {"managed_local", "external"}
_VALID_UPSTREAM_PROTOCOLS = {"responses", "chat", "messages"}
_VALID_UPSTREAM_AUTH_KINDS = {"none", "bearer", "x_api_key"}
_CAPABILITY_FIELDS = {
    "supports_responses",
    "supports_chat",
    "supports_messages",
    "supports_stream",
    "supports_function_tools",
    "supports_builtin_tools",
    "supports_previous_response_id_native",
    "supports_json_schema",
}
_VALID_NATIVE_PROTOCOLS = {"responses", "chat", "messages"}
_VALID_ADAPTER_POLICIES = {"responses->chat", "responses->messages"}
_TOOL_POLICY_FIELDS = {
    "openai_function_tools",
    "anthropic_function_tools",
    "builtin_tools",
}
_PROTOCOL_FEATURE_FIELDS = {
    "stream",
    "count_tokens",
    "json_schema",
    "previous_response_id",
}


def _request_id(request: Request) -> str:
    return request.headers.get("x-request-id", str(uuid.uuid4()))


async def _read_json_body(request: Request) -> dict[str, Any]:
    raw = (await request.body()) or b"{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid json body") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="json body must be an object")
    return payload


def _resolve_auth(request: Request, scope: str) -> AuthContext:
    auth = resolve_auth_context(
        request.headers.get("authorization"),
        request.headers.get("x-api-key"),
        db=request.app.state.db,
    )
    require_scope(auth, scope)
    return auth


def _request_log_context(request: Request, auth: AuthContext) -> dict[str, Any]:
    return {
        "api_key_id": auth.api_key_id,
        "auth_source": auth.source,
        "client_ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "rejection_reason": None,
        "metadata": {},
    }


def _elapsed_ms(started_at: datetime, finished_at: datetime) -> float:
    return (finished_at - started_at).total_seconds() * 1000.0


def _extract_usage(payload: dict[str, Any]) -> dict[str, int | None]:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "cache_creation_tokens": None,
            "cache_read_tokens": None,
            "cache_miss_tokens": None,
        }
    cache = usage.get("cache")
    if not isinstance(cache, dict):
        cache = {}
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cache_creation_tokens": cache.get("creation_tokens"),
        "cache_read_tokens": cache.get("read_tokens"),
        "cache_miss_tokens": cache.get("miss_tokens"),
    }


def _record_request_metric(
    app: FastAPI,
    *,
    request_id: str,
    model_name: str,
    protocol: str,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    response_payload: dict[str, Any] | None = None,
    backend_type: str | None = None,
    api_key_id: int | None = None,
) -> None:
    usage = _extract_usage(response_payload or {})
    latency_ms = _elapsed_ms(started_at, finished_at)
    tokens_per_second = None
    if usage["completion_tokens"] is not None and latency_ms > 0:
        tokens_per_second = usage["completion_tokens"] / (latency_ms / 1000.0)
    with suppress(Exception):
        write_request_metric(
            app.state.db,
            request_id=request_id,
            model_name=model_name,
            protocol=protocol,
            status=status,
            latency_ms=latency_ms,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
            tokens_per_second=tokens_per_second,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            backend_type=backend_type,
            api_key_id=api_key_id,
            cache_creation_tokens=usage["cache_creation_tokens"],
            cache_read_tokens=usage["cache_read_tokens"],
            cache_miss_tokens=usage["cache_miss_tokens"],
        )


def _extract_openai_stream_usage(chunk: bytes) -> dict[str, Any] | None:
    if not chunk.startswith(b"data: "):
        return None
    data = chunk[6:].strip()
    if not data or data == b"[DONE]":
        return None
    try:
        payload = json.loads(data)
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(payload, dict) and isinstance(payload.get("usage"), dict):
        return payload
    return None


def _extract_anthropic_stream_usage(chunk: bytes) -> dict[str, Any] | None:
    event_type: str | None = None
    data_lines: list[str] = []
    for raw_line in chunk.decode("utf-8", errors="ignore").splitlines():
        if raw_line.startswith("event: "):
            event_type = raw_line[7:].strip()
        elif raw_line.startswith("data: "):
            data_lines.append(raw_line[6:])
    if event_type != "message_delta" or not data_lines:
        return None
    try:
        payload = json.loads("\n".join(data_lines))
    except (json.JSONDecodeError, ValueError):
        return None
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        return None
    return {
        "usage": {
            "prompt_tokens": usage.get("input_tokens"),
            "completion_tokens": usage.get("output_tokens"),
            "total_tokens": (
                (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0)
                if usage.get("input_tokens") is not None or usage.get("output_tokens") is not None
                else None
            ),
        }
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _response_usage_from_chat(payload: dict[str, Any]) -> dict[str, Any]:
    usage = _extract_usage(payload)
    return {
        "input_tokens": usage["prompt_tokens"],
        "output_tokens": usage["completion_tokens"],
        "total_tokens": usage["total_tokens"],
        "input_token_details": {
            "cache_creation_tokens": usage["cache_creation_tokens"],
            "cache_read_tokens": usage["cache_read_tokens"],
            "cache_miss_tokens": usage["cache_miss_tokens"],
        },
    }


def _responses_metric_payload_from_responses(payload: dict[str, Any]) -> dict[str, Any]:
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        usage = {}
    return {
        "usage": {
            "prompt_tokens": usage.get("input_tokens"),
            "completion_tokens": usage.get("output_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }
    }


def _responses_metric_payload_from_messages(payload: dict[str, Any]) -> dict[str, Any]:
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        usage = {}
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    total_tokens = None
    if input_tokens is not None or output_tokens is not None:
        total_tokens = (input_tokens or 0) + (output_tokens or 0)
    return {
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": total_tokens,
        }
    }


def _responses_output_and_messages_from_text_parts(
    text_parts: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not text_parts:
        return [], []
    text = "".join(text_parts)
    return (
        [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
        [{"role": "assistant", "content": text}],
    )


def _assistant_message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)
    return ""


def _tool_call_output_item(tool_call: dict[str, Any]) -> dict[str, Any]:
    function = tool_call.get("function") if isinstance(tool_call, dict) else None
    return {
        "type": "function_call",
        "call_id": tool_call.get("id"),
        "name": function.get("name") if isinstance(function, dict) else None,
        "arguments": function.get("arguments") if isinstance(function, dict) else None,
    }


def _responses_output_from_chat(chat_payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    choices = chat_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return [], []
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return [], []

    output: list[dict[str, Any]] = []
    conversation_messages: list[dict[str, Any]] = []
    text = _assistant_message_text(message)
    if text:
        output.append(
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        )
        conversation_messages.append({"role": "assistant", "content": text})

    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        for tool_call in tool_calls:
            if isinstance(tool_call, dict):
                output.append(_tool_call_output_item(tool_call))
                conversation_messages.append(
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [tool_call],
                    }
                )
    return output, conversation_messages


def _responses_payload_from_chat(
    *,
    chat_payload: dict[str, Any],
    request_payload: OpenAIResponsesRequest,
    response_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    output, assistant_messages = _responses_output_from_chat(chat_payload)
    payload = {
        "id": response_id,
        "object": "response",
        "created_at": _now_iso(),
        "status": "completed",
        "model": request_payload.model,
        "output": output,
        "usage": _response_usage_from_chat(chat_payload),
    }
    return payload, assistant_messages


def _response_output_to_messages(output_items: Any) -> list[dict[str, Any]]:
    if not isinstance(output_items, list):
        return []
    messages: list[dict[str, Any]] = []
    for item in output_items:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message" or item.get("role") != "assistant":
            continue
        content = item.get("content")
        text_parts: list[str] = []
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "output_text" and isinstance(block.get("text"), str):
                    text_parts.append(block["text"])
        if text_parts:
            messages.append({"role": "assistant", "content": "".join(text_parts)})
    return messages


def _resolved_metric_backend_type(app: FastAPI, route: ModelRoute) -> str:
    if route.lifecycle_mode == "external":
        return "external"
    return route.backend_type or app.state.ctx.backend_client.backend_type


async def _begin_api_key_lease_or_raise(
    app: FastAPI,
    *,
    auth: AuthContext,
    request_id: str,
    model_name: str,
    protocol: str,
    log_context: dict[str, Any],
) -> Any:
    try:
        return await app.state.api_key_gate.begin(
            auth.api_key_id,
            rpm_limit=auth.rpm_limit,
            concurrency_limit=auth.concurrency_limit,
        )
    except ApiKeyRateLimitError as exc:
        log_context["rejection_reason"] = "rpm_limit_exceeded"
        write_request_log(
            app.state.db,
            request_id,
            model_name,
            "rejected",
            protocol,
            str(exc),
            **log_context,
        )
        raise HTTPException(status_code=429, detail=str(exc), headers={"x-request-id": request_id}) from exc
    except ApiKeyConcurrencyError as exc:
        log_context["rejection_reason"] = "concurrency_limit_exceeded"
        write_request_log(
            app.state.db,
            request_id,
            model_name,
            "rejected",
            protocol,
            str(exc),
            **log_context,
        )
        raise HTTPException(status_code=429, detail=str(exc), headers={"x-request-id": request_id}) from exc


async def _reject_request_with_metric(
    app: FastAPI,
    *,
    key_lease: Any,
    exc: Exception,
    request_id: str,
    model_name: str,
    protocol: str,
    status: str,
    rejection_reason: str,
    http_status: int,
    started_at: datetime,
    log_context: dict[str, Any],
) -> None:
    await key_lease.reject()
    finished_at = datetime.now(timezone.utc)
    log_context["rejection_reason"] = rejection_reason
    _record_request_metric(
        app,
        request_id=request_id,
        model_name=model_name,
        protocol=protocol,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
    )
    write_request_log(
        app.state.db,
        request_id,
        model_name,
        status,
        protocol,
        str(exc),
        **log_context,
    )
    raise HTTPException(status_code=http_status, detail=str(exc), headers={"x-request-id": request_id}) from exc


def _assistant_message_text_from_anthropic(message_payload: dict[str, Any]) -> str:
    content = message_payload.get("content")
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "".join(parts)


def _count_anthropic_message_content_tokens(content: Any) -> int:
    if isinstance(content, str):
        return max(1, len(content) // 4) if content else 0
    if isinstance(content, list):
        total = 0
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text" and isinstance(block.get("text"), str):
                total += max(1, len(block["text"]) // 4) if block["text"] else 0
            elif block_type == "tool_result":
                tool_content = block.get("content")
                if isinstance(tool_content, str):
                    total += max(1, len(tool_content) // 4) if tool_content else 0
                elif isinstance(tool_content, list):
                    total += _count_anthropic_message_content_tokens(tool_content)
                total += 8
            elif block_type == "tool_use":
                total += max(1, len(json.dumps(block.get("input", {}), ensure_ascii=False)) // 4)
                total += 8
        return total
    return 0


def _estimate_anthropic_input_tokens(raw: dict[str, Any]) -> int:
    total = 0
    system = raw.get("system")
    if isinstance(system, str):
        total += max(1, len(system) // 4) if system else 0
    elif isinstance(system, list):
        total += _count_anthropic_message_content_tokens(system)
    messages = raw.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            total += 4
            total += _count_anthropic_message_content_tokens(message.get("content"))
    tools = raw.get("tools")
    if isinstance(tools, list):
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            if is_anthropic_function_tool(tool):
                total += max(1, len(json.dumps(tool, ensure_ascii=False)) // 4)
            else:
                total += 8
    return total


def _responses_payload_from_anthropic(
    *,
    message_payload: dict[str, Any],
    request_payload: OpenAIResponsesRequest,
    response_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    text = _assistant_message_text_from_anthropic(message_payload)
    output: list[dict[str, Any]] = []
    assistant_messages: list[dict[str, Any]] = []
    if text:
        output.append(
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        )
        assistant_messages.append({"role": "assistant", "content": text})
    usage = message_payload.get("usage") if isinstance(message_payload.get("usage"), dict) else {}
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    total_tokens = None
    if input_tokens is not None or output_tokens is not None:
        total_tokens = (input_tokens or 0) + (output_tokens or 0)
    payload = {
        "id": response_id,
        "object": "response",
        "created_at": _now_iso(),
        "status": "completed",
        "model": request_payload.model,
        "output": output,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        },
    }
    return payload, assistant_messages


def _format_sse_event(event: str, payload: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n".encode()


def _parse_openai_stream_event(chunk: bytes) -> dict[str, Any] | None:
    if not chunk.startswith(b"data: "):
        return None
    data = chunk[6:].strip()
    if not data or data == b"[DONE]":
        return None
    try:
        payload = json.loads(data)
    except (json.JSONDecodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _parse_anthropic_stream_event(chunk: bytes) -> tuple[str | None, dict[str, Any] | None]:
    event_type: str | None = None
    data_lines: list[str] = []
    for raw_line in chunk.decode("utf-8", errors="ignore").splitlines():
        if raw_line.startswith("event: "):
            event_type = raw_line[7:].strip()
        elif raw_line.startswith("data: "):
            data_lines.append(raw_line[6:])
    if not data_lines:
        return event_type, None
    try:
        payload = json.loads("\n".join(data_lines))
    except (json.JSONDecodeError, ValueError):
        return event_type, None
    return event_type, payload if isinstance(payload, dict) else None


def _sanitize_api_key_row(row: dict[str, Any], *, masked_key: str | None = None) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "masked_key": masked_key or stable_masked_key(row["id"]),
        "plain_secret": row.get("plain_secret"),
        "status": row["status"],
        "scopes": row["scopes"],
        "rpm_limit": row["rpm_limit"],
        "concurrency_limit": row["concurrency_limit"],
        "created_at": row["created_at"],
        "disabled_at": row["disabled_at"],
        "last_used_at": row["last_used_at"],
        "note": row["note"],
    }


def _normalize_name(value: Any, field_name: str = "name") -> str:
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a string")
    name = value.strip()
    if not name:
        raise HTTPException(status_code=400, detail=f"{field_name} must not be empty")
    return name


def _normalize_scopes(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise HTTPException(status_code=400, detail="scopes must be a non-empty list")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise HTTPException(status_code=400, detail="scope values must be strings")
        scope = item.strip()
        if scope not in _ALLOWED_SCOPES:
            raise HTTPException(status_code=400, detail=f"unsupported scope: {scope}")
        if scope not in seen:
            normalized.append(scope)
            seen.add(scope)
    return normalized


def _normalize_status(value: Any) -> str:
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail="status must be a string")
    status = value.strip()
    if status not in _ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail=f"unsupported status: {status}")
    return status


def _normalize_optional_limit(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HTTPException(status_code=400, detail=f"{field_name} must be a positive integer or null")
    return value


def _normalize_optional_note(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail="note must be a string or null")
    return value.strip() or None


def _normalize_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a boolean")
    return value


def _normalize_optional_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a string or null")
    return value.strip() or None


def _normalize_optional_backend_type(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail="backend_type must be a string or null")
    backend_type = value.strip()
    if backend_type not in _VALID_BACKEND_TYPES:
        raise HTTPException(status_code=400, detail=f"unsupported backend_type: {backend_type}")
    return backend_type


def _normalize_capabilities_payload(payload: Any, current: ModelRoute) -> dict[str, bool]:
    capabilities = {
        "supports_responses": current.capabilities.supports_responses,
        "supports_chat": current.capabilities.supports_chat,
        "supports_messages": current.capabilities.supports_messages,
        "supports_stream": current.capabilities.supports_stream,
        "supports_function_tools": current.capabilities.supports_function_tools,
        "supports_builtin_tools": current.capabilities.supports_builtin_tools,
        "supports_previous_response_id_native": current.capabilities.supports_previous_response_id_native,
        "supports_json_schema": current.capabilities.supports_json_schema,
    }
    if payload is _MISSING:
        return capabilities
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="capabilities_json must be an object")
    for key, value in payload.items():
        if key not in _CAPABILITY_FIELDS:
            raise HTTPException(status_code=400, detail=f"unsupported capability: {key}")
        capabilities[key] = _normalize_bool(value, f"capabilities_json.{key}")
    return capabilities


def _normalize_native_protocols_payload(payload: Any, current: ModelRoute) -> list[str]:
    current_runtime = current.runtime_capabilities()
    protocols = list(current_runtime["native_protocols"])
    if payload is _MISSING:
        return protocols
    if not isinstance(payload, list) or not payload:
        raise HTTPException(status_code=400, detail="native_protocols_json must be a non-empty list")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, str):
            raise HTTPException(status_code=400, detail="native_protocols_json values must be strings")
        protocol = item.strip()
        if protocol not in _VALID_NATIVE_PROTOCOLS:
            raise HTTPException(status_code=400, detail=f"unsupported native protocol: {protocol}")
        if protocol not in seen:
            normalized.append(protocol)
            seen.add(protocol)
    return normalized


def _normalize_adapter_policies_payload(payload: Any, current: ModelRoute) -> list[str]:
    current_runtime = current.runtime_capabilities()
    policies = list(current_runtime["adapter_policies"])
    if payload is _MISSING:
        return policies
    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="adapter_policies_json must be a list")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, str):
            raise HTTPException(status_code=400, detail="adapter_policies_json values must be strings")
        policy = item.strip()
        if policy not in _VALID_ADAPTER_POLICIES:
            raise HTTPException(status_code=400, detail=f"unsupported adapter policy: {policy}")
        if policy not in seen:
            normalized.append(policy)
            seen.add(policy)
    return normalized


def _normalize_tool_policies_payload(payload: Any, current: ModelRoute) -> dict[str, bool]:
    current_runtime = current.runtime_capabilities()
    policies = dict(current_runtime["tool_policies"])
    if payload is _MISSING:
        return policies
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="tool_policies_json must be an object")
    for key, value in payload.items():
        if key not in _TOOL_POLICY_FIELDS:
            raise HTTPException(status_code=400, detail=f"unsupported tool policy: {key}")
        policies[key] = _normalize_bool(value, f"tool_policies_json.{key}")
    return policies


def _normalize_protocol_features_payload(payload: Any, current: ModelRoute) -> dict[str, bool]:
    current_runtime = current.runtime_capabilities()
    features = dict(current_runtime["protocol_features"])
    if payload is _MISSING:
        return features
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="protocol_features_json must be an object")
    for key, value in payload.items():
        if key not in _PROTOCOL_FEATURE_FIELDS:
            raise HTTPException(status_code=400, detail=f"unsupported protocol feature: {key}")
        features[key] = _normalize_bool(value, f"protocol_features_json.{key}")
    return features


def _build_model_route_storage_payload(route: ModelRoute) -> dict[str, Any]:
    runtime_caps = route.runtime_capabilities()
    return {
        "name": route.name,
        "display_name": route.display_name,
        "backend_model": route.backend_model,
        "backend_type": route.backend_type,
        "enabled": route.enabled,
        "lifecycle_mode": route.lifecycle_mode,
        "upstream_protocol": route.upstream_protocol,
        "upstream_base_url": route.upstream_base_url,
        "upstream_model": route.upstream_model,
        "upstream_auth_kind": route.upstream_auth_kind,
        "upstream_auth_ref": route.upstream_auth_ref,
        "source_kind": route.source_kind,
        "source_ref": route.source_ref,
        "stale": route.stale,
        "capabilities_json": _normalize_capabilities_payload(_MISSING, route),
        "native_protocols_json": runtime_caps["native_protocols"],
        "adapter_policies_json": runtime_caps["adapter_policies"],
        "tool_policies_json": runtime_caps["tool_policies"],
        "protocol_features_json": runtime_caps["protocol_features"],
    }


def _validate_create_model_route_payload(payload: dict[str, Any]) -> ModelRoute:
    if "name" not in payload:
        raise HTTPException(status_code=400, detail="name is required")
    if "lifecycle_mode" not in payload:
        raise HTTPException(status_code=400, detail="lifecycle_mode is required")
    if "upstream_protocol" not in payload:
        raise HTTPException(status_code=400, detail="upstream_protocol is required")

    name = _normalize_name(payload["name"])
    display_name = _normalize_name(payload.get("display_name", name), "display_name")
    lifecycle_mode = str(payload["lifecycle_mode"]).strip()
    if lifecycle_mode != "external":
        raise HTTPException(status_code=400, detail="phase1 only supports external route creation")
    upstream_protocol = str(payload["upstream_protocol"]).strip()
    if upstream_protocol not in _VALID_UPSTREAM_PROTOCOLS:
        raise HTTPException(status_code=400, detail=f"unsupported upstream_protocol: {upstream_protocol}")
    upstream_base_url = _normalize_optional_string(payload.get("upstream_base_url"), "upstream_base_url")
    upstream_model = _normalize_optional_string(payload.get("upstream_model"), "upstream_model")
    if not upstream_base_url:
        raise HTTPException(status_code=400, detail="upstream_base_url is required for external routes")
    if not upstream_model:
        raise HTTPException(status_code=400, detail="upstream_model is required for external routes")
    upstream_auth_kind = str(payload.get("upstream_auth_kind", "none")).strip()
    if upstream_auth_kind not in _VALID_UPSTREAM_AUTH_KINDS:
        raise HTTPException(status_code=400, detail=f"unsupported upstream_auth_kind: {upstream_auth_kind}")
    upstream_auth_ref = _normalize_optional_string(payload.get("upstream_auth_ref"), "upstream_auth_ref")
    if upstream_auth_kind != "none" and not upstream_auth_ref:
        raise HTTPException(status_code=400, detail="upstream_auth_ref is required when upstream_auth_kind is not none")

    base_route = ModelRoute(name=name, display_name=display_name)
    capabilities_json = _normalize_capabilities_payload(payload.get("capabilities_json", _MISSING), base_route)
    seed_route = ModelRoute(
        name=name,
        display_name=display_name,
        backend_model=None,
        backend_type=None,
        enabled=_normalize_bool(payload.get("enabled", True), "enabled"),
        lifecycle_mode="external",
        upstream_protocol=upstream_protocol,
        upstream_base_url=upstream_base_url,
        upstream_model=upstream_model,
        upstream_auth_kind=upstream_auth_kind,
        upstream_auth_ref=None if upstream_auth_kind == "none" else upstream_auth_ref,
        capabilities=ModelCapabilities(**capabilities_json),
        source_kind="manual",
        source_ref=None,
        stale=False,
    )
    native_protocols_json = _normalize_native_protocols_payload(payload.get("native_protocols_json", _MISSING), seed_route)
    adapter_policies_json = _normalize_adapter_policies_payload(payload.get("adapter_policies_json", _MISSING), seed_route)
    tool_policies_json = _normalize_tool_policies_payload(payload.get("tool_policies_json", _MISSING), seed_route)
    protocol_features_json = _normalize_protocol_features_payload(payload.get("protocol_features_json", _MISSING), seed_route)

    return ModelRoute(
        name=name,
        display_name=display_name,
        backend_model=None,
        backend_type=None,
        enabled=seed_route.enabled,
        lifecycle_mode="external",
        upstream_protocol=upstream_protocol,
        upstream_base_url=upstream_base_url,
        upstream_model=upstream_model,
        upstream_auth_kind=upstream_auth_kind,
        upstream_auth_ref=None if upstream_auth_kind == "none" else upstream_auth_ref,
        capabilities=ModelCapabilities(**capabilities_json),
        native_protocols_json=native_protocols_json,
        adapter_policies_json=adapter_policies_json,
        tool_policies_json=tool_policies_json,
        protocol_features_json=protocol_features_json,
        source_kind="manual",
        source_ref=None,
        stale=False,
    )


def _validate_update_model_route_payload(payload: dict[str, Any], route: ModelRoute) -> ModelRoute:
    display_name = route.display_name
    if "display_name" in payload:
        display_name = _normalize_name(payload["display_name"], "display_name")

    enabled = route.enabled
    if "enabled" in payload:
        enabled = _normalize_bool(payload["enabled"], "enabled")
    if route.source_kind == "profile_seed" and route.stale and not route.enabled and enabled:
        raise HTTPException(
            status_code=409,
            detail="stale profile_seed routes cannot be re-enabled; create a manual route or switch back to the source profile",
        )

    lifecycle_mode = route.lifecycle_mode
    if "lifecycle_mode" in payload:
        if not isinstance(payload["lifecycle_mode"], str):
            raise HTTPException(status_code=400, detail="lifecycle_mode must be a string")
        lifecycle_mode = payload["lifecycle_mode"].strip()
    if lifecycle_mode not in _VALID_LIFECYCLE_MODES:
        raise HTTPException(status_code=400, detail=f"unsupported lifecycle_mode: {lifecycle_mode}")
    if route.source_kind == "profile_seed" and lifecycle_mode == "external":
        raise HTTPException(
            status_code=409,
            detail="profile_seed routes cannot be converted to manual external routes",
        )

    upstream_protocol = route.upstream_protocol
    if "upstream_protocol" in payload:
        if not isinstance(payload["upstream_protocol"], str):
            raise HTTPException(status_code=400, detail="upstream_protocol must be a string")
        upstream_protocol = payload["upstream_protocol"].strip()
    if upstream_protocol not in _VALID_UPSTREAM_PROTOCOLS:
        raise HTTPException(status_code=400, detail=f"unsupported upstream_protocol: {upstream_protocol}")

    upstream_auth_kind = route.upstream_auth_kind
    if "upstream_auth_kind" in payload:
        if not isinstance(payload["upstream_auth_kind"], str):
            raise HTTPException(status_code=400, detail="upstream_auth_kind must be a string")
        upstream_auth_kind = payload["upstream_auth_kind"].strip()
    if upstream_auth_kind not in _VALID_UPSTREAM_AUTH_KINDS:
        raise HTTPException(status_code=400, detail=f"unsupported upstream_auth_kind: {upstream_auth_kind}")

    backend_type = route.backend_type
    if "backend_type" in payload:
        backend_type = _normalize_optional_backend_type(payload["backend_type"])

    backend_model = route.backend_model
    if "backend_model" in payload:
        backend_model = _normalize_optional_string(payload["backend_model"], "backend_model")

    upstream_base_url = route.upstream_base_url
    if "upstream_base_url" in payload:
        upstream_base_url = _normalize_optional_string(payload["upstream_base_url"], "upstream_base_url")

    upstream_model = route.upstream_model
    if "upstream_model" in payload:
        upstream_model = _normalize_optional_string(payload["upstream_model"], "upstream_model")

    upstream_auth_ref = route.upstream_auth_ref
    if "upstream_auth_ref" in payload:
        upstream_auth_ref = _normalize_optional_string(payload["upstream_auth_ref"], "upstream_auth_ref")

    capabilities_json = _normalize_capabilities_payload(payload.get("capabilities_json", _MISSING), route)
    route_for_runtime = replace(
        route,
        display_name=display_name,
        backend_model=backend_model,
        backend_type=backend_type,
        enabled=enabled,
        lifecycle_mode=lifecycle_mode,
        upstream_protocol=upstream_protocol,
        upstream_base_url=upstream_base_url,
        upstream_model=upstream_model,
        upstream_auth_kind=upstream_auth_kind,
        upstream_auth_ref=upstream_auth_ref,
        capabilities=ModelCapabilities(**capabilities_json),
    )
    native_protocols_json = _normalize_native_protocols_payload(payload.get("native_protocols_json", _MISSING), route_for_runtime)
    adapter_policies_json = _normalize_adapter_policies_payload(payload.get("adapter_policies_json", _MISSING), route_for_runtime)
    tool_policies_json = _normalize_tool_policies_payload(payload.get("tool_policies_json", _MISSING), route_for_runtime)
    protocol_features_json = _normalize_protocol_features_payload(payload.get("protocol_features_json", _MISSING), route_for_runtime)

    if lifecycle_mode == "managed_local":
        if backend_type not in _VALID_BACKEND_TYPES:
            raise HTTPException(status_code=400, detail=f"unsupported backend_type: {backend_type}")
        if not backend_model:
            raise HTTPException(status_code=400, detail="backend_model is required for managed_local routes")
        if not upstream_model:
            upstream_model = backend_model
    else:
        backend_type = None
        backend_model = None
        if not upstream_base_url:
            raise HTTPException(status_code=400, detail="upstream_base_url is required for external routes")
        if not upstream_model:
            raise HTTPException(status_code=400, detail="upstream_model is required for external routes")

    if upstream_auth_kind == "none":
        upstream_auth_ref = None
    elif not upstream_auth_ref:
        raise HTTPException(status_code=400, detail="upstream_auth_ref is required when upstream_auth_kind is not none")

    return replace(
        route_for_runtime,
        display_name=display_name,
        backend_model=backend_model,
        backend_type=backend_type,
        enabled=enabled,
        lifecycle_mode=lifecycle_mode,
        upstream_protocol=upstream_protocol,
        upstream_base_url=upstream_base_url,
        upstream_model=upstream_model,
        upstream_auth_kind=upstream_auth_kind,
        upstream_auth_ref=upstream_auth_ref,
        capabilities=ModelCapabilities(**capabilities_json),
        native_protocols_json=native_protocols_json,
        adapter_policies_json=adapter_policies_json,
        tool_policies_json=tool_policies_json,
        protocol_features_json=protocol_features_json,
        source_kind=route.source_kind,
        source_ref=route.source_ref,
        stale=route.stale,
    )


def _validate_create_api_key_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "name" not in payload:
        raise HTTPException(status_code=400, detail="name is required")
    if "scopes" not in payload:
        raise HTTPException(status_code=400, detail="scopes are required")
    return {
        "name": _normalize_name(payload["name"]),
        "scopes": _normalize_scopes(payload["scopes"]),
        "rpm_limit": _normalize_optional_limit(payload.get("rpm_limit"), "rpm_limit"),
        "concurrency_limit": _normalize_optional_limit(payload.get("concurrency_limit"), "concurrency_limit"),
        "note": _normalize_optional_note(payload.get("note")),
    }


def _validate_update_api_key_payload(payload: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if "name" in payload:
        updates["name"] = _normalize_name(payload["name"])
    if "status" in payload:
        updates["status"] = _normalize_status(payload["status"])
    if "scopes" in payload:
        updates["scopes"] = _normalize_scopes(payload["scopes"])
    if "rpm_limit" in payload:
        updates["rpm_limit"] = _normalize_optional_limit(payload["rpm_limit"], "rpm_limit")
    if "concurrency_limit" in payload:
        updates["concurrency_limit"] = _normalize_optional_limit(payload["concurrency_limit"], "concurrency_limit")
    if "note" in payload:
        updates["note"] = _normalize_optional_note(payload["note"])
    return updates


def create_app() -> FastAPI:
    setup_logging()
    settings = load_settings()
    db_path = PROJECT_ROOT / "runtime" / "data" / "gateway.db"
    if os.getenv("PYTEST_CURRENT_TEST"):
        db_path = PROJECT_ROOT / "runtime" / "data" / f"gateway-test-{uuid.uuid4().hex}.db"
    catalog = load_model_catalog()
    db = init_db(db_path)
    route_seed_events = seed_model_routes(db, model_routes_for_admin(catalog))
    for event in route_seed_events:
        write_agent_event(
            db,
            "info",
            event["reason"],
            event_type=event["event_type"],
            readiness_state="route_seed",
            metadata=event["metadata"],
        )
    schedule_state = load_schedule_config(db)
    if schedule_state is None:
        schedule_state = asdict(settings.schedule)
        upsert_schedule_config(db, schedule_state)
    backend_client = VLLMBackendClient(
        base_url=settings.gateway.backend_url,
        backend_type=settings.vllm.backend_type,
        request_timeout_seconds=settings.gateway.backend_request_timeout_seconds,
    )
    ctx = GatewayContext(
        backend_client=backend_client,
        models={item["name"]: model_route_from_row(item) for item in list_model_routes(db)},
        post_json_to=post_json_to,
        stream_bytes_from=stream_bytes_from,
    )
    request_gate = RequestGate(
        execution_limit=settings.gateway.execution_limit,
        queue_limit=settings.gateway.queue_limit,
    )
    api_key_gate = ApiKeyGate()

    app = FastAPI(title="llmnode", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["authorization", "content-type", "x-api-key"],
    )
    app.state.ctx = ctx
    app.state.request_gate = request_gate
    app.state.api_key_gate = api_key_gate
    app.state.db = db
    app.state.agent_base_url = settings.gateway.agent_base_url
    app.state.agent_status_url = settings.gateway.agent_status_url
    app.state.require_agent_ready = settings.gateway.require_agent_ready
    app.state.schedule = schedule_state
    app.state.post_json_to = post_json_to
    app.state.stream_bytes_from = stream_bytes_from

    async def fetch_agent_state() -> dict | None:
        if not app.state.agent_status_url:
            return None
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(app.state.agent_status_url)
                resp.raise_for_status()
                payload = resp.json()
                if isinstance(payload, dict):
                    return payload
                return None
        except httpx.HTTPError:
            return None

    app.state.fetch_agent_state = fetch_agent_state

    async def restart_agent_backend() -> dict[str, Any]:
        base_url = str(app.state.agent_base_url or "").rstrip("/")
        if not base_url:
            raise HTTPException(status_code=503, detail="agent control unavailable")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(f"{base_url}/manage/restart")
                resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise HTTPException(status_code=503, detail="agent control unavailable") from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=502, detail="agent restart failed") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail="agent control unavailable") from exc

        payload: dict[str, Any] = {}
        if resp.content:
            with suppress(ValueError):
                json_payload = resp.json()
                if isinstance(json_payload, dict):
                    payload = json_payload
        return {
            "accepted": True,
            "service": "backend",
            "action": "restart",
            "agent_status": payload.get("status", "recovering"),
        }

    app.state.restart_agent_backend = restart_agent_backend

    async def ensure_agent_ready() -> dict[str, Any]:
        if not app.state.require_agent_ready:
            return {}
        state = await app.state.fetch_agent_state()
        if not state:
            raise HTTPException(status_code=503, detail="agent_state_unavailable")
        # Check inference readiness
        if state.get("inference_ready") is False:
            retry_after = str(state.get("retry_after_seconds") or 5)
            if state.get("http_ready"):
                detail = "backend_warming_up"
            else:
                detail = "backend_not_ready"
            raise HTTPException(
                status_code=503,
                detail=detail,
                headers={"Retry-After": retry_after},
            )
        if state.get("status") != "ready":
            raise HTTPException(
                status_code=503,
                detail="agent_not_ready",
                headers={"Retry-After": "5"},
            )
        return state

    def _build_backend_runtime_info(s) -> dict[str, Any]:
        bt = s.vllm.backend_type
        info: dict[str, Any] = {
            "backend_type": bt,
            "container_name": s.vllm.container_name,
            "image_name": s.vllm.image_name,
            "model_dir": s.vllm.model_dir,
            "model_name": s.vllm.model_name,
            "host_port": s.vllm.host_port,
            "shm_size": s.vllm.shm_size,
        }
        if bt == "llama.cpp":
            info.update({
                "model_file": s.vllm.model_file,
                "n_gpu_layers": s.vllm.n_gpu_layers,
                "ctx_size": s.vllm.ctx_size,
                "n_parallel": s.vllm.n_parallel,
            })
        elif bt == "sglang":
            info.update({
                "tensor_parallel_size": s.vllm.tensor_parallel_size,
                "mem_fraction_static": s.vllm.mem_fraction_static,
                "max_running_requests": s.vllm.max_running_requests,
                "reasoning_parser": s.vllm.reasoning_parser,
            })
        else:
            info.update({
                "gpu_memory_utilization": s.vllm.gpu_memory_utilization,
                "tensor_parallel_size": s.vllm.tensor_parallel_size,
                "max_model_len": s.vllm.max_model_len,
                "max_num_seqs": s.vllm.max_num_seqs,
                "enable_auto_tool_choice": s.vllm.enable_auto_tool_choice,
                "reasoning_parser": s.vllm.reasoning_parser,
                "tool_call_parser": s.vllm.tool_call_parser,
            })
        return info

    async def build_admin_snapshot() -> dict:
        backend_ready = False
        backend_error: str | None = None
        backend_container: dict[str, Any] | None = None
        try:
            backend_ready = await app.state.ctx.backend_client.health()
        except Exception as exc:
            backend_error = f"{type(exc).__name__}: {exc}"
        agent_state = await app.state.fetch_agent_state()
        if hasattr(app.state, "backend_driver") and hasattr(app.state, "run_sync"):
            try:
                backend_container = await app.state.run_sync(app.state.backend_driver.snapshot)
            except Exception:
                backend_container = None
        return {
            "api_key_configured": app.state.db.execute(
                "SELECT 1 FROM api_keys WHERE status = 'active' LIMIT 1"
            ).fetchone() is not None,
            "backend_type": app.state.ctx.backend_client.backend_type,
            "backend_ready": backend_ready,
            "backend_error": backend_error,
            "backend_container": backend_container,
            "agent_state": agent_state,
            "require_agent_ready": app.state.require_agent_ready,
            "queue_length": app.state.request_gate.waiting,
            "models": logical_models_for_api(app.state.ctx.models),
            "logs": list_request_logs(app.state.db, limit=20)["logs"],
            "events": list_agent_events(app.state.db, limit=20),
            "runtime": {
                "gateway": {
                    "host": settings.gateway.host,
                    "port": settings.gateway.port,
                    "backend_url": settings.gateway.backend_url,
                    "backend_model": settings.gateway.backend_model,
                    "agent_base_url": settings.gateway.agent_base_url,
                    "agent_status_url": settings.gateway.agent_status_url,
                    "require_agent_ready": settings.gateway.require_agent_ready,
                    "queue_limit": settings.gateway.queue_limit,
                    "execution_limit": settings.gateway.execution_limit,
                    "api_key_configured": app.state.db.execute(
                        "SELECT 1 FROM api_keys WHERE status = 'active' LIMIT 1"
                    ).fetchone() is not None,
                },
                "agent": {
                    "host": settings.agent.host,
                    "port": settings.agent.port,
                    "state": settings.agent.state,
                    "poll_interval": settings.agent.poll_interval,
                    "auto_recover": settings.agent.auto_recover,
                    "recovery_threshold": settings.agent.recovery_threshold,
                    "startup_grace_period": settings.agent.startup_grace_period,
                },
                "schedule": {
                    "timezone": app.state.schedule["timezone"],
                    "work_days": app.state.schedule["work_days"],
                    "start_time": app.state.schedule["start_time"],
                    "end_time": app.state.schedule["end_time"],
                    "auto_stop_enabled": app.state.schedule["auto_stop_enabled"],
                    "auto_start_enabled": app.state.schedule["auto_start_enabled"],
                    "cooldown_minutes": app.state.schedule["cooldown_minutes"],
                },
                "backend": _build_backend_runtime_info(settings),
                "model_routes": model_routes_for_admin(app.state.ctx.models),
            },
        }

    @app.get("/health/liveliness")
    async def liveliness():
        return {"status": "alive", "queue_length": app.state.request_gate.waiting}

    @app.get("/v1/models")
    async def list_models(request: Request):
        _resolve_auth(request, "inference")
        request_id = _request_id(request)
        response = JSONResponse({"object": "list", "data": logical_models_for_api(request.app.state.ctx.models)})
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/admin/status")
    async def admin_status(request: Request):
        _resolve_auth(request, "admin")
        request_id = _request_id(request)
        response = JSONResponse(await build_admin_snapshot())
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/admin/stream")
    async def admin_stream(request: Request, once: bool = False, interval: int = 3):
        _resolve_auth(request, "admin")
        request_id = _request_id(request)

        async def event_source():
            while True:
                payload = await build_admin_snapshot()
                yield f"event: snapshot\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                if once:
                    break
                await asyncio.sleep(max(1, interval))

        response = StreamingResponse(event_source(), media_type="text/event-stream")
        response.headers["x-request-id"] = request_id
        response.headers["cache-control"] = "no-cache"
        response.headers["connection"] = "keep-alive"
        return response

    @app.get("/admin/request-logs")
    async def admin_request_logs(
        request: Request,
        limit: int = 50,
        offset: int = 0,
        date_from: str | None = None,
        date_to: str | None = None,
        status: str | None = None,
        query: str | None = None,
    ):
        _resolve_auth(request, "admin")
        request_id = _request_id(request)
        response = JSONResponse(
            list_request_logs(
                request.app.state.db,
                limit=limit,
                offset=offset,
                date_from=date_from,
                date_to=date_to,
                status=status,
                query=query,
            )
        )
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/admin/logs")
    async def admin_logs(
        request: Request,
        limit: int = 50,
        offset: int = 0,
        date_from: str | None = None,
        date_to: str | None = None,
        status: str | None = None,
        query: str | None = None,
    ):
        _resolve_auth(request, "admin")
        request_id = _request_id(request)
        response = JSONResponse(
            list_request_logs(
                request.app.state.db,
                limit=limit,
                offset=offset,
                date_from=date_from,
                date_to=date_to,
                status=status,
                query=query,
            )
        )
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/admin/request-logs/export")
    async def admin_request_logs_export(
        request: Request,
        date_from: str | None = None,
        date_to: str | None = None,
        status: str | None = None,
        query: str | None = None,
    ):
        _resolve_auth(request, "admin")
        rows = list_request_logs(
            request.app.state.db,
            limit=500,
            offset=0,
            date_from=date_from,
            date_to=date_to,
            status=status,
            query=query,
            export_all=True,
        )["logs"]
        request_id = _request_id(request)
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "id",
                "request_id",
                "model_name",
                "status",
                "protocol",
                "created_at",
                "api_key_id",
                "auth_source",
                "client_ip",
                "user_agent",
                "rejection_reason",
                "error_message",
            ],
        )
        writer.writeheader()
        csv_fields = set(writer.fieldnames)
        writer.writerows({key: row.get(key) for key in csv_fields} for row in rows)
        response = PlainTextResponse(output.getvalue(), media_type="text/csv; charset=utf-8")
        response.headers["x-request-id"] = request_id
        response.headers["content-disposition"] = 'attachment; filename="request-logs.csv"'
        return response

    @app.get("/admin/request-logs/{request_id}")
    async def admin_request_log_detail(request: Request, request_id: str):
        _resolve_auth(request, "admin")
        detail = get_request_log_detail(request.app.state.db, request_id)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"unknown request: {request_id}")
        response_request_id = _request_id(request)
        response = JSONResponse(detail)
        response.headers["x-request-id"] = response_request_id
        return response

    @app.get("/admin/events")
    async def admin_events(request: Request, limit: int = 50):
        _resolve_auth(request, "admin")
        request_id = _request_id(request)
        response = JSONResponse({"events": list_agent_events(request.app.state.db, limit=limit)})
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/admin/keys")
    async def admin_keys(request: Request):
        _resolve_auth(request, "admin")
        request_id = _request_id(request)
        raw_keys = list_api_keys(request.app.state.db)
        keys = [
            {
                **_sanitize_api_key_row(row, masked_key=stable_masked_key(row["id"])),
                "usage_summary": aggregate_usage_for_api_key(request.app.state.db, api_key_id=row["id"])["summary"],
            }
            for row in raw_keys
        ]
        response = JSONResponse({"keys": keys})
        response.headers["x-request-id"] = request_id
        return response

    @app.post("/admin/keys")
    async def admin_create_key(request: Request):
        _resolve_auth(request, "admin")
        payload = _validate_create_api_key_payload(await _read_json_body(request))
        secret = generate_api_key()
        try:
            row = create_api_key(
                request.app.state.db,
                name=payload["name"],
                key_hash=hash_api_key(secret),
                plain_secret=secret,
                scopes=payload["scopes"],
                rpm_limit=payload["rpm_limit"],
                concurrency_limit=payload["concurrency_limit"],
                note=payload["note"],
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="api key already exists") from exc
        request_id = _request_id(request)
        response = JSONResponse({"key": _sanitize_api_key_row(row, masked_key=mask_api_key(secret)), "secret": secret})
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/admin/overview/readiness")
    async def admin_readiness_overview(request: Request):
        _resolve_auth(request, "admin")
        request_id = _request_id(request)
        state = await request.app.state.fetch_agent_state()
        response = JSONResponse({
            "readiness": state,
            "base_urls": {
                "local": "http://127.0.0.1:4000",
                "lan": "http://10.18.90.100:4000",
            },
        })
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/admin/overview/usage")
    async def admin_usage_overview(
        request: Request,
        granularity: str = "day",
        window: str = "12h",
        group_by: str = "backend_type",
    ):
        _resolve_auth(request, "admin")
        request_id = _request_id(request)
        response = JSONResponse({
            "summary": aggregate_request_metrics(request.app.state.db),
            "trend": aggregate_usage_trend(request.app.state.db, granularity=granularity),
            "breakdown": {
                "models": aggregate_usage_breakdown(request.app.state.db, group_by="model_name"),
                "backends": aggregate_usage_breakdown(request.app.state.db, group_by="backend_type"),
                "api_keys": aggregate_usage_breakdown(request.app.state.db, group_by="api_key_id"),
            },
            "chart": aggregate_usage_chart(
                request.app.state.db,
                window=window,
                group_by=group_by,
            ),
        })
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/admin/keys/{key_id}/usage")
    async def admin_key_usage(request: Request, key_id: int):
        _resolve_auth(request, "admin")
        request_id = _request_id(request)
        response = JSONResponse(
            aggregate_usage_for_api_key(request.app.state.db, api_key_id=key_id)
        )
        response.headers["x-request-id"] = request_id
        return response

    @app.patch("/admin/keys/{key_id}")
    async def admin_update_key(request: Request, key_id: int):
        _resolve_auth(request, "admin")
        payload = _validate_update_api_key_payload(await _read_json_body(request))
        try:
            row = update_api_key(request.app.state.db, key_id, **payload)
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="api key already exists") from exc
        if row is None:
            raise HTTPException(status_code=404, detail=f"unknown api key: {key_id}")
        request_id = _request_id(request)
        response = JSONResponse({"key": _sanitize_api_key_row(row)})
        response.headers["x-request-id"] = request_id
        return response

    @app.delete("/admin/keys/{key_id}")
    async def admin_delete_key(request: Request, key_id: int):
        _resolve_auth(request, "admin")
        existing = get_api_key_by_id(request.app.state.db, key_id)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"unknown api key: {key_id}")
        delete_api_key(request.app.state.db, key_id)
        request_id = _request_id(request)
        response = JSONResponse({"deleted": True, "id": key_id})
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/admin/models")
    async def admin_models(request: Request):
        _resolve_auth(request, "admin")
        request_id = _request_id(request)
        response = JSONResponse({"models": model_routes_for_admin(request.app.state.ctx.models)})
        response.headers["x-request-id"] = request_id
        return response

    @app.post("/admin/models")
    async def admin_create_model(request: Request):
        _resolve_auth(request, "admin")
        route = _validate_create_model_route_payload(await _read_json_body(request))
        if route.name in request.app.state.ctx.models:
            raise HTTPException(status_code=409, detail=f"model already exists: {route.name}")
        request.app.state.ctx.models[route.name] = route
        upsert_model_route(request.app.state.db, _build_model_route_storage_payload(route))
        request_id = _request_id(request)
        response = JSONResponse({"model": model_routes_for_admin({route.name: route})[0]})
        response.headers["x-request-id"] = request_id
        return response

    @app.patch("/admin/models/{name}")
    async def admin_update_model(request: Request, name: str):
        _resolve_auth(request, "admin")
        payload = await _read_json_body(request)
        route = request.app.state.ctx.models.get(name)
        if route is None:
            raise HTTPException(status_code=404, detail=f"unknown model: {name}")
        updated = _validate_update_model_route_payload(payload, route)
        request.app.state.ctx.models[name] = updated
        upsert_model_route(request.app.state.db, _build_model_route_storage_payload(updated))
        request_id = _request_id(request)
        response = JSONResponse({"model": model_routes_for_admin({name: updated})[0]})
        response.headers["x-request-id"] = request_id
        return response

    @app.delete("/admin/models/{name}")
    async def admin_delete_model(request: Request, name: str):
        _resolve_auth(request, "admin")
        route = request.app.state.ctx.models.get(name)
        if route is None:
            raise HTTPException(status_code=404, detail=f"unknown model: {name}")
        if route.source_kind != "manual":
            raise HTTPException(
                status_code=409,
                detail="profile_seed routes cannot be deleted; disable them instead",
            )
        delete_model_route(request.app.state.db, name)
        request.app.state.ctx.models.pop(name, None)
        request_id = _request_id(request)
        response = JSONResponse({"deleted": True, "name": name})
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/admin/schedule")
    async def admin_schedule(request: Request):
        _resolve_auth(request, "admin")
        request_id = _request_id(request)
        response = JSONResponse({"schedule": request.app.state.schedule})
        response.headers["x-request-id"] = request_id
        return response

    @app.patch("/admin/schedule")
    async def admin_update_schedule(request: Request):
        _resolve_auth(request, "admin")
        payload = await _read_json_body(request)
        schedule = dict(request.app.state.schedule)
        if "timezone" in payload:
            schedule["timezone"] = str(payload["timezone"])
        if "work_days" in payload:
            schedule["work_days"] = list(payload["work_days"])
        if "start_time" in payload:
            schedule["start_time"] = str(payload["start_time"])
        if "end_time" in payload:
            schedule["end_time"] = str(payload["end_time"])
        if "auto_stop_enabled" in payload:
            schedule["auto_stop_enabled"] = bool(payload["auto_stop_enabled"])
        if "auto_start_enabled" in payload:
            schedule["auto_start_enabled"] = bool(payload["auto_start_enabled"])
        if "cooldown_minutes" in payload:
            schedule["cooldown_minutes"] = int(payload["cooldown_minutes"])
        request.app.state.schedule = schedule
        upsert_schedule_config(request.app.state.db, schedule)
        request_id = _request_id(request)
        response = JSONResponse({"schedule": schedule})
        response.headers["x-request-id"] = request_id
        return response

    @app.post("/admin/services/restart")
    async def admin_restart_service(request: Request):
        _resolve_auth(request, "admin")
        request_id = _request_id(request)
        response = JSONResponse(await request.app.state.restart_agent_backend())
        response.headers["x-request-id"] = request_id
        return response

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        auth = _resolve_auth(request, "inference")
        await ensure_agent_ready()
        raw = await _read_json_body(request)
        payload = OpenAIChatCompletionsRequest.model_validate(raw)
        route = resolve_route(payload.model, request.app.state.ctx.models)
        plan = plan_route_execution(
            route,
            type("Req", (), {
                "client_protocol": "chat",
                "stream": bool(payload.stream),
                "tools": payload.tools,
            })(),
        )
        request_id = _request_id(request)
        started_at = datetime.now(timezone.utc)
        log_context = _request_log_context(request, auth)
        log_context["metadata"] = {
            "client_protocol": "chat",
            "execution_mode": plan.execution_mode,
            "adapter_selected": plan.selected_adapter,
            "tool_classes_detected": ["openai_function_tools"] if payload.tools else [],
            "request_mutation": plan.execution_mode == "adapter",
            "mutation_reason": None if plan.execution_mode == "native" else (plan.selected_adapter or "adapter_path"),
        }
        key_lease = await _begin_api_key_lease_or_raise(
            request.app,
            auth=auth,
            request_id=request_id,
            model_name=payload.model,
            protocol="openai",
            log_context=log_context,
        )

        async def reject_openai_request(exc: Exception, *, status: str, rejection_reason: str, http_status: int) -> None:
            await _reject_request_with_metric(
                request.app,
                key_lease=key_lease,
                exc=exc,
                request_id=request_id,
                model_name=payload.model,
                protocol="openai",
                status=status,
                rejection_reason=rejection_reason,
                http_status=http_status,
                started_at=started_at,
                log_context=log_context,
            )

        if payload.stream:
            gate = request.app.state.request_gate.slot()
            try:
                await gate.__aenter__()
                stream = await stream_openai_chat(payload.to_backend_payload(payload.model), request.app.state.ctx)
            except QueueFullError as exc:
                await reject_openai_request(exc, status="rejected", rejection_reason="queue_full", http_status=429)
            except QueueTimeoutError as exc:
                await reject_openai_request(exc, status="timeout", rejection_reason="queue_timeout", http_status=504)
            except Exception:
                await key_lease.reject()
                await gate.__aexit__(None, None, None)
                raise

            async def body():
                last_usage_payload: dict[str, Any] | None = None
                try:
                    async for chunk in stream:
                        usage_payload = _extract_openai_stream_usage(chunk)
                        if usage_payload is not None:
                            last_usage_payload = usage_payload
                        yield chunk
                finally:
                    await key_lease.finish()
                    await gate.__aexit__(None, None, None)
                    if last_usage_payload is not None:
                        finished_at = datetime.now(timezone.utc)
                        _record_request_metric(
                            request.app,
                            request_id=request_id,
                            model_name=payload.model,
                            protocol="openai",
                            status="ok",
                            started_at=started_at,
                            finished_at=finished_at,
                            response_payload=last_usage_payload,
                            backend_type=_resolved_metric_backend_type(request.app, route),
                            api_key_id=auth.api_key_id,
                        )

            write_request_log(
                request.app.state.db,
                request_id,
                payload.model,
                "streaming",
                "openai",
                **log_context,
            )
            response = StreamingResponse(body(), media_type="text/event-stream")
            response.headers["x-request-id"] = request_id
            return response

        try:
            async with request.app.state.request_gate.slot():
                result = await proxy_openai_chat(payload.to_backend_payload(payload.model), request.app.state.ctx)
        except QueueFullError as exc:
            await reject_openai_request(exc, status="rejected", rejection_reason="queue_full", http_status=429)
        except QueueTimeoutError as exc:
            await reject_openai_request(exc, status="timeout", rejection_reason="queue_timeout", http_status=504)
        except Exception:
            await key_lease.finish()
            raise
        await key_lease.finish()
        finished_at = datetime.now(timezone.utc)
        _record_request_metric(
            request.app,
            request_id=request_id,
            model_name=payload.model,
            protocol="openai",
            status="ok",
            started_at=started_at,
            finished_at=finished_at,
            response_payload=result,
            backend_type=_resolved_metric_backend_type(request.app, route),
            api_key_id=auth.api_key_id,
        )
        write_request_log(
            request.app.state.db,
            request_id,
            payload.model,
            "ok",
            "openai",
            **log_context,
        )
        response = JSONResponse(result)
        response.headers["x-request-id"] = request_id
        return response

    @app.post("/v1/responses")
    async def responses(request: Request):
        auth = _resolve_auth(request, "inference")
        await ensure_agent_ready()
        raw = await _read_json_body(request)
        try:
            payload = OpenAIResponsesRequest.model_validate(raw)
            input_items = payload.input_items()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        route = resolve_route(payload.model, request.app.state.ctx.models)
        plan = plan_route_execution(
            route,
            type("Req", (), {
                "client_protocol": "responses",
                "stream": payload.stream,
                "tools": payload.tools,
            })(),
        )
        runtime_caps = plan.runtime_caps
        execution_mode = plan.execution_mode
        selected_adapter = plan.selected_adapter
        request_id = _request_id(request)
        response_id = f"resp_{uuid.uuid4().hex}"
        started_at = datetime.now(timezone.utc)
        log_context = _request_log_context(request, auth)

        previous_messages: list[dict[str, Any]] = []
        previous_state: dict[str, Any] | None = None
        if payload.previous_response_id:
            previous_state = get_response_state(request.app.state.db, payload.previous_response_id)
            if previous_state is None:
                raise HTTPException(status_code=404, detail=f"unknown response: {payload.previous_response_id}")
            if execution_mode == "native" and runtime_caps["protocol_features"].get("previous_response_id", False):
                previous_messages = []
            else:
                previous_messages = list(previous_state["messages"])

        chat_payload = build_responses_chat_payload(route, payload, previous_messages)
        messages_payload = build_responses_messages_payload(route, payload, previous_messages)
        messages_for_state = payload.to_chat_messages(previous_messages)
        tool_classes_detected: list[str] = []
        for tool in payload.tools or []:
            if isinstance(tool, dict) and tool.get("type") == "function":
                tool_classes_detected.append("openai_function_tools")
            elif isinstance(tool, dict) and is_anthropic_function_tool(tool):
                tool_classes_detected.append("anthropic_function_tools")
            elif isinstance(tool, dict):
                tool_classes_detected.append("builtin_tools")
        log_context["metadata"] = {
            "client_protocol": "responses",
            "execution_mode": execution_mode,
            "adapter_selected": selected_adapter,
            "tool_classes_detected": tool_classes_detected,
            "request_mutation": execution_mode == "adapter",
            "mutation_reason": None if execution_mode == "native" else (selected_adapter or "adapter_path"),
        }

        key_lease = await _begin_api_key_lease_or_raise(
            request.app,
            auth=auth,
            request_id=request_id,
            model_name=payload.model,
            protocol="responses",
            log_context=log_context,
        )

        def build_native_upstream_payload() -> dict[str, Any]:
            upstream_payload = dict(raw)
            upstream_payload["model"] = route.resolved_upstream_model() or payload.model
            if previous_state is not None and runtime_caps["protocol_features"].get("previous_response_id", False):
                upstream_previous_id = previous_state.get("upstream_response_id")
                if upstream_previous_id:
                    upstream_payload["previous_response_id"] = upstream_previous_id
            elif previous_state is not None:
                upstream_payload["input"] = messages_for_state
                upstream_payload.pop("previous_response_id", None)
            return upstream_payload

        async def reject_responses_request(exc: Exception, *, status: str, rejection_reason: str, http_status: int) -> None:
            await _reject_request_with_metric(
                request.app,
                key_lease=key_lease,
                exc=exc,
                request_id=request_id,
                model_name=payload.model,
                protocol="responses",
                status=status,
                rejection_reason=rejection_reason,
                http_status=http_status,
                started_at=started_at,
                log_context=log_context,
            )

        def persist_response_state(
            *,
            persisted_response_id: str,
            output_items: list[dict[str, Any]],
            messages: list[dict[str, Any]],
            upstream_protocol: str,
            request_payload: dict[str, Any],
            output_payload: dict[str, Any],
            upstream_response_id: str | None = None,
        ) -> None:
            upsert_response_state(
                request.app.state.db,
                response_id=persisted_response_id,
                request_id=request_id,
                model_name=payload.model,
                input_items=input_items,
                output_items=output_items,
                messages=messages,
                parent_response_id=payload.previous_response_id,
                route_name=route.name,
                client_protocol="responses",
                upstream_protocol=upstream_protocol,
                upstream_response_id=upstream_response_id,
                request_payload=request_payload,
                output_payload=output_payload,
            )

        async def execute_native_sync() -> JSONResponse:
            upstream_payload = build_native_upstream_payload()
            if route.lifecycle_mode == "external":
                result = await request.app.state.post_json_to(
                    route.upstream_base_url or "",
                    "/v1/responses",
                    upstream_payload,
                    headers=build_upstream_headers(route),
                )
            else:
                result = await request.app.state.ctx.backend_client.post_json("/v1/responses", upstream_payload)
            await key_lease.finish()
            finished_at = datetime.now(timezone.utc)
            persisted_response_id = result.get("id") or response_id
            _record_request_metric(
                request.app,
                request_id=request_id,
                model_name=payload.model,
                protocol="responses",
                status="ok",
                started_at=started_at,
                finished_at=finished_at,
                response_payload=_responses_metric_payload_from_responses(result),
                backend_type=route.backend_type or ("external" if route.lifecycle_mode == "external" else request.app.state.ctx.backend_client.backend_type),
                api_key_id=auth.api_key_id,
            )
            persist_response_state(
                persisted_response_id=persisted_response_id,
                output_items=result.get("output", []),
                messages=[*messages_for_state, *_response_output_to_messages(result.get("output"))],
                upstream_protocol="responses",
                upstream_response_id=result.get("id"),
                request_payload=upstream_payload,
                output_payload=result,
            )
            write_request_log(
                request.app.state.db,
                request_id,
                payload.model,
                "ok",
                "responses",
                **log_context,
            )
            response = JSONResponse(result)
            response.headers["x-request-id"] = request_id
            return response

        async def execute_messages_sync() -> JSONResponse:
            try:
                async with request.app.state.request_gate.slot():
                    if route.lifecycle_mode == "external":
                        result = await request.app.state.post_json_to(
                            route.upstream_base_url or "",
                            "/v1/messages",
                            messages_payload,
                            headers=build_upstream_headers(route),
                        )
                    else:
                        result = await request.app.state.ctx.backend_client.post_json("/v1/messages", messages_payload)
            except QueueFullError as exc:
                await reject_responses_request(exc, status="rejected", rejection_reason="queue_full", http_status=429)
            except QueueTimeoutError as exc:
                await reject_responses_request(exc, status="timeout", rejection_reason="queue_timeout", http_status=504)
            except Exception:
                await key_lease.finish()
                raise

            await key_lease.finish()
            finished_at = datetime.now(timezone.utc)
            _record_request_metric(
                request.app,
                request_id=request_id,
                model_name=payload.model,
                protocol="responses",
                status="ok",
                started_at=started_at,
                finished_at=finished_at,
                response_payload=_responses_metric_payload_from_messages(result),
                backend_type=route.backend_type or "external",
                api_key_id=auth.api_key_id,
            )
            response_payload, assistant_messages = _responses_payload_from_anthropic(
                message_payload=result,
                request_payload=payload,
                response_id=response_id,
            )
            persist_response_state(
                persisted_response_id=response_id,
                output_items=response_payload["output"],
                messages=[*messages_for_state, *assistant_messages],
                upstream_protocol=route.upstream_protocol or "messages",
                request_payload=messages_payload,
                output_payload=result,
            )
            write_request_log(
                request.app.state.db,
                request_id,
                payload.model,
                "ok",
                "responses",
                **log_context,
            )
            response = JSONResponse(response_payload)
            response.headers["x-request-id"] = request_id
            return response

        async def execute_chat_sync() -> JSONResponse:
            try:
                async with request.app.state.request_gate.slot():
                    result = await proxy_openai_chat_via_route(route, chat_payload, request.app.state.ctx)
            except QueueFullError as exc:
                await reject_responses_request(exc, status="rejected", rejection_reason="queue_full", http_status=429)
            except QueueTimeoutError as exc:
                await reject_responses_request(exc, status="timeout", rejection_reason="queue_timeout", http_status=504)
            except Exception:
                await key_lease.finish()
                raise

            await key_lease.finish()
            finished_at = datetime.now(timezone.utc)
            _record_request_metric(
                request.app,
                request_id=request_id,
                model_name=payload.model,
                protocol="responses",
                status="ok",
                started_at=started_at,
                finished_at=finished_at,
                response_payload=result,
                backend_type=route.backend_type or ("external" if route.lifecycle_mode == "external" else request.app.state.ctx.backend_client.backend_type),
                api_key_id=auth.api_key_id,
            )
            response_payload, assistant_messages = _responses_payload_from_chat(
                chat_payload=result,
                request_payload=payload,
                response_id=response_id,
            )
            persist_response_state(
                persisted_response_id=response_id,
                output_items=response_payload["output"],
                messages=[*messages_for_state, *assistant_messages],
                upstream_protocol=route.upstream_protocol or "chat",
                request_payload={
                    **chat_payload,
                    "model": route.resolved_upstream_model() or chat_payload.get("model"),
                },
                output_payload=result,
            )
            write_request_log(
                request.app.state.db,
                request_id,
                payload.model,
                "ok",
                "responses",
                **log_context,
            )
            response = JSONResponse(response_payload)
            response.headers["x-request-id"] = request_id
            return response

        async def execute_chat_stream() -> StreamingResponse:
            gate = request.app.state.request_gate.slot()
            try:
                await gate.__aenter__()
                stream = await stream_openai_chat_via_route(route, chat_payload, request.app.state.ctx)
            except QueueFullError as exc:
                await reject_responses_request(exc, status="rejected", rejection_reason="queue_full", http_status=429)
            except QueueTimeoutError as exc:
                await reject_responses_request(exc, status="timeout", rejection_reason="queue_timeout", http_status=504)
            except Exception:
                await key_lease.reject()
                await gate.__aexit__(None, None, None)
                raise

            async def body():
                last_usage_payload: dict[str, Any] | None = None
                output_text_parts: list[str] = []
                yield _format_sse_event(
                    "response.created",
                    {
                        "id": response_id,
                        "object": "response",
                        "status": "in_progress",
                        "model": payload.model,
                    },
                )
                try:
                    async for chunk in stream:
                        usage_payload = _extract_openai_stream_usage(chunk)
                        if usage_payload is not None:
                            last_usage_payload = usage_payload

                        event_payload = _parse_openai_stream_event(chunk)
                        if event_payload is None:
                            continue
                        choices = event_payload.get("choices")
                        if not isinstance(choices, list) or not choices:
                            continue
                        delta = choices[0].get("delta")
                        if not isinstance(delta, dict):
                            continue
                        content = delta.get("content")
                        if isinstance(content, str) and content:
                            output_text_parts.append(content)
                            yield _format_sse_event(
                                "response.output_text.delta",
                                {
                                    "response_id": response_id,
                                    "delta": content,
                                },
                            )
                finally:
                    await key_lease.finish()
                    await gate.__aexit__(None, None, None)
                    finished_at = datetime.now(timezone.utc)
                    if last_usage_payload is not None:
                        _record_request_metric(
                            request.app,
                            request_id=request_id,
                            model_name=payload.model,
                            protocol="responses",
                            status="ok",
                            started_at=started_at,
                            finished_at=finished_at,
                            response_payload=last_usage_payload,
                            backend_type=route.backend_type or ("external" if route.lifecycle_mode == "external" else request.app.state.ctx.backend_client.backend_type),
                            api_key_id=auth.api_key_id,
                        )
                    final_output, assistant_messages = _responses_output_and_messages_from_text_parts(output_text_parts)
                    persist_response_state(
                        persisted_response_id=response_id,
                        output_items=final_output,
                        messages=[*messages_for_state, *assistant_messages],
                        upstream_protocol=route.upstream_protocol or "chat",
                        request_payload={
                            **chat_payload,
                            "model": route.resolved_upstream_model() or chat_payload.get("model"),
                        },
                        output_payload={
                            "id": response_id,
                            "object": "response",
                            "status": "completed",
                            "output": final_output,
                        },
                    )
                    yield _format_sse_event(
                        "response.completed",
                        {
                            "id": response_id,
                            "object": "response",
                            "status": "completed",
                            "model": payload.model,
                            "output": final_output,
                            "usage": _response_usage_from_chat(last_usage_payload or {}),
                        },
                    )

            write_request_log(
                request.app.state.db,
                request_id,
                payload.model,
                "streaming",
                "responses",
                **log_context,
            )
            response = StreamingResponse(body(), media_type="text/event-stream")
            response.headers["x-request-id"] = request_id
            return response

        async def execute_native_stream() -> StreamingResponse:
            upstream_payload = build_native_upstream_payload()

            async def native_body():
                completed_payload: dict[str, Any] | None = None
                try:
                    if route.lifecycle_mode == "external":
                        stream = request.app.state.stream_bytes_from(
                            route.upstream_base_url or "",
                            "/v1/responses",
                            upstream_payload,
                            headers=build_upstream_headers(route),
                        )
                    else:
                        stream = request.app.state.ctx.backend_client.stream_bytes("/v1/responses", upstream_payload)
                    async for chunk in stream:
                        text = chunk.decode("utf-8", errors="ignore")
                        if "event: response.completed" in text:
                            parts = text.split("data: ", 1)
                            if len(parts) == 2:
                                with suppress(json.JSONDecodeError, ValueError):
                                    completed_payload = json.loads(parts[1].strip())
                        yield chunk
                finally:
                    await key_lease.finish()
                    finished_at = datetime.now(timezone.utc)
                    if completed_payload is not None:
                        persisted_response_id = completed_payload.get("id") or response_id
                        _record_request_metric(
                            request.app,
                            request_id=request_id,
                            model_name=payload.model,
                            protocol="responses",
                            status="ok",
                            started_at=started_at,
                            finished_at=finished_at,
                            response_payload=_responses_metric_payload_from_responses(completed_payload),
                            backend_type=route.backend_type or "external",
                            api_key_id=auth.api_key_id,
                        )
                        persist_response_state(
                            persisted_response_id=persisted_response_id,
                            output_items=completed_payload.get("output", []),
                            messages=[*messages_for_state, *_response_output_to_messages(completed_payload.get("output"))],
                            upstream_protocol="responses",
                            upstream_response_id=completed_payload.get("id"),
                            request_payload=upstream_payload,
                            output_payload=completed_payload,
                        )

            write_request_log(
                request.app.state.db,
                request_id,
                payload.model,
                "streaming",
                "responses",
                **log_context,
            )
            response = StreamingResponse(native_body(), media_type="text/event-stream")
            response.headers["x-request-id"] = request_id
            return response

        async def execute_messages_stream() -> StreamingResponse:
            gate = request.app.state.request_gate.slot()
            try:
                await gate.__aenter__()
                if route.lifecycle_mode == "external":
                    stream = request.app.state.stream_bytes_from(
                        route.upstream_base_url or "",
                        "/v1/messages",
                        messages_payload,
                        headers=build_upstream_headers(route),
                    )
                else:
                    stream = request.app.state.ctx.backend_client.stream_bytes("/v1/messages", messages_payload)
            except QueueFullError as exc:
                await reject_responses_request(exc, status="rejected", rejection_reason="queue_full", http_status=429)
            except QueueTimeoutError as exc:
                await reject_responses_request(exc, status="timeout", rejection_reason="queue_timeout", http_status=504)
            except Exception:
                await key_lease.reject()
                await gate.__aexit__(None, None, None)
                raise

            async def anthropic_body():
                last_usage_payload: dict[str, Any] | None = None
                output_text_parts: list[str] = []
                yield _format_sse_event(
                    "response.created",
                    {
                        "id": response_id,
                        "object": "response",
                        "status": "in_progress",
                        "model": payload.model,
                    },
                )
                try:
                    async for chunk in stream:
                        usage_payload = _extract_anthropic_stream_usage(chunk)
                        if usage_payload is not None:
                            last_usage_payload = usage_payload
                        event_type, event_payload = _parse_anthropic_stream_event(chunk)
                        if event_type != "content_block_delta" or not isinstance(event_payload, dict):
                            continue
                        delta = event_payload.get("delta")
                        if not isinstance(delta, dict):
                            continue
                        if delta.get("type") != "text_delta":
                            continue
                        text = delta.get("text")
                        if isinstance(text, str) and text:
                            output_text_parts.append(text)
                            yield _format_sse_event(
                                "response.output_text.delta",
                                {
                                    "response_id": response_id,
                                    "delta": text,
                                },
                            )
                finally:
                    await key_lease.finish()
                    await gate.__aexit__(None, None, None)
                    finished_at = datetime.now(timezone.utc)
                    if last_usage_payload is not None:
                        _record_request_metric(
                            request.app,
                            request_id=request_id,
                            model_name=payload.model,
                            protocol="responses",
                            status="ok",
                            started_at=started_at,
                            finished_at=finished_at,
                            response_payload=last_usage_payload,
                            backend_type=route.backend_type or "external",
                            api_key_id=auth.api_key_id,
                        )
                    final_output, assistant_messages = _responses_output_and_messages_from_text_parts(output_text_parts)
                    persist_response_state(
                        persisted_response_id=response_id,
                        output_items=final_output,
                        messages=[*messages_for_state, *assistant_messages],
                        upstream_protocol=route.upstream_protocol or "messages",
                        request_payload=messages_payload,
                        output_payload={
                            "id": response_id,
                            "object": "response",
                            "status": "completed",
                            "output": final_output,
                        },
                    )
                    yield _format_sse_event(
                        "response.completed",
                        {
                            "id": response_id,
                            "object": "response",
                            "status": "completed",
                            "model": payload.model,
                            "output": final_output,
                            "usage": {
                                "input_tokens": (last_usage_payload or {}).get("usage", {}).get("prompt_tokens"),
                                "output_tokens": (last_usage_payload or {}).get("usage", {}).get("completion_tokens"),
                                "total_tokens": (last_usage_payload or {}).get("usage", {}).get("total_tokens"),
                            },
                        },
                    )

            write_request_log(
                request.app.state.db,
                request_id,
                payload.model,
                "streaming",
                "responses",
                **log_context,
            )
            response = StreamingResponse(anthropic_body(), media_type="text/event-stream")
            response.headers["x-request-id"] = request_id
            return response

        if payload.stream:
            if execution_mode == "native":
                return await execute_native_stream()

            if selected_adapter == "responses_to_messages":
                return await execute_messages_stream()

            if selected_adapter != "responses_to_chat":
                raise HTTPException(status_code=400, detail="adapter_not_enabled_for_route")
            return await execute_chat_stream()

        if execution_mode == "native":
            return await execute_native_sync()

        if selected_adapter == "responses_to_messages":
            return await execute_messages_sync()

        if selected_adapter != "responses_to_chat":
            raise HTTPException(status_code=400, detail="adapter_not_enabled_for_route")

        return await execute_chat_sync()

    @app.post("/v1/messages")
    async def anthropic_messages(request: Request):
        auth = _resolve_auth(request, "inference")
        await ensure_agent_ready()
        raw = await _read_json_body(request)
        initial_payload = AnthropicMessagesRequest.model_validate(raw)
        route = resolve_route(initial_payload.model, request.app.state.ctx.models)
        sanitized_raw = strip_claude_code_builtin_tools_for_managed_messages(route, raw)
        payload = AnthropicMessagesRequest.model_validate(sanitized_raw)
        plan = plan_route_execution(
            route,
            type("Req", (), {
                "client_protocol": "messages",
                "stream": bool(payload.stream),
                "tools": payload.tools,
            })(),
        )
        request_id = _request_id(request)
        started_at = datetime.now(timezone.utc)
        log_context = _request_log_context(request, auth)
        tool_classes_detected: list[str] = []
        for tool in payload.tools or []:
            if isinstance(tool, dict) and is_anthropic_function_tool(tool):
                tool_classes_detected.append("anthropic_function_tools")
            elif isinstance(tool, dict):
                tool_classes_detected.append("builtin_tools")
        log_context["metadata"] = {
            "client_protocol": "messages",
            "execution_mode": plan.execution_mode,
            "adapter_selected": plan.selected_adapter,
            "tool_classes_detected": tool_classes_detected,
            "request_mutation": bool(sanitized_raw != raw) or plan.execution_mode == "adapter",
            "mutation_reason": "builtin_tool_metadata_filtered" if sanitized_raw != raw else (None if plan.execution_mode == "native" else (plan.selected_adapter or "adapter_path")),
        }
        key_lease = await _begin_api_key_lease_or_raise(
            request.app,
            auth=auth,
            request_id=request_id,
            model_name=payload.model,
            protocol="anthropic",
            log_context=log_context,
        )

        async def reject_anthropic_request(exc: Exception, *, status: str, rejection_reason: str, http_status: int) -> None:
            await _reject_request_with_metric(
                request.app,
                key_lease=key_lease,
                exc=exc,
                request_id=request_id,
                model_name=payload.model,
                protocol="anthropic",
                status=status,
                rejection_reason=rejection_reason,
                http_status=http_status,
                started_at=started_at,
                log_context=log_context,
            )

        if payload.stream:
            gate = request.app.state.request_gate.slot()
            try:
                await gate.__aenter__()
                stream = await stream_anthropic_messages(payload.to_backend_payload(payload.model), request.app.state.ctx)
            except QueueFullError as exc:
                await reject_anthropic_request(exc, status="rejected", rejection_reason="queue_full", http_status=429)
            except QueueTimeoutError as exc:
                await reject_anthropic_request(exc, status="timeout", rejection_reason="queue_timeout", http_status=504)
            except Exception:
                await key_lease.reject()
                await gate.__aexit__(None, None, None)
                raise

            async def body():
                last_usage_payload: dict[str, Any] | None = None
                try:
                    async for chunk in stream:
                        usage_payload = _extract_anthropic_stream_usage(chunk)
                        if usage_payload is not None:
                            last_usage_payload = usage_payload
                        yield chunk
                finally:
                    await key_lease.finish()
                    await gate.__aexit__(None, None, None)
                    if last_usage_payload is not None:
                        finished_at = datetime.now(timezone.utc)
                        _record_request_metric(
                            request.app,
                            request_id=request_id,
                            model_name=payload.model,
                            protocol="anthropic",
                            status="ok",
                            started_at=started_at,
                            finished_at=finished_at,
                            response_payload=last_usage_payload,
                            backend_type=_resolved_metric_backend_type(request.app, route),
                            api_key_id=auth.api_key_id,
                        )

            write_request_log(
                request.app.state.db,
                request_id,
                payload.model,
                "streaming",
                "anthropic",
                **log_context,
            )
            response = StreamingResponse(body(), media_type="text/event-stream")
            response.headers["x-request-id"] = request_id
            return response

        try:
            async with request.app.state.request_gate.slot():
                result = await proxy_anthropic_messages(payload.to_backend_payload(payload.model), request.app.state.ctx)
        except QueueFullError as exc:
            await reject_anthropic_request(exc, status="rejected", rejection_reason="queue_full", http_status=429)
        except QueueTimeoutError as exc:
            await reject_anthropic_request(exc, status="timeout", rejection_reason="queue_timeout", http_status=504)
        except Exception:
            await key_lease.finish()
            raise
        await key_lease.finish()
        finished_at = datetime.now(timezone.utc)
        _record_request_metric(
            request.app,
            request_id=request_id,
            model_name=payload.model,
            protocol="anthropic",
            status="ok",
            started_at=started_at,
            finished_at=finished_at,
            response_payload=result,
            backend_type=_resolved_metric_backend_type(request.app, route),
            api_key_id=auth.api_key_id,
        )
        write_request_log(
            request.app.state.db,
            request_id,
            payload.model,
            "ok",
            "anthropic",
            **log_context,
        )
        response = JSONResponse(result)
        response.headers["x-request-id"] = request_id
        return response

    @app.post("/v1/messages/count_tokens")
    async def anthropic_messages_count_tokens(request: Request):
        _resolve_auth(request, "inference")
        raw = await _read_json_body(request)
        model = raw.get("model")
        if not isinstance(model, str) or not model.strip():
            raise HTTPException(status_code=400, detail="model is required")
        messages = raw.get("messages")
        if not isinstance(messages, list):
            raise HTTPException(status_code=400, detail="messages must be a list")
        resolve_route(model, request.app.state.ctx.models)
        return JSONResponse({"input_tokens": _estimate_anthropic_input_tokens(raw)})

    return app
