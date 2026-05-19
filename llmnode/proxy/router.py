from __future__ import annotations

import os
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Dict

from fastapi import HTTPException

from ..models import ModelRoute
from ..security import hash_api_key
from ..storage.db import get_api_key_by_hash
from .backend import BackendClient
from .executor import NormalizedRequest


@dataclass
class AuthContext:
    source: str
    api_key_id: int | None
    name: str
    scopes: list[str]
    rpm_limit: int | None
    concurrency_limit: int | None


@dataclass
class GatewayContext:
    backend_client: BackendClient
    models: Dict[str, ModelRoute]
    post_json_to: Callable[[str, str, Dict[str, Any], dict[str, str] | None], Awaitable[Dict[str, Any]]] | None = None
    stream_bytes_from: Callable[[str, str, Dict[str, Any], dict[str, str] | None], Any] | None = None


@dataclass(frozen=True)
class RouteExecutionPlan:
    route: ModelRoute
    runtime_caps: dict[str, Any]
    client_protocol: str
    execution_mode: str
    selected_adapter: str | None


_CLAUDE_CODE_BUILTIN_TOOL_PREFIXES = (
    "web_search_",
    "bash_",
    "text_editor_",
)


def is_anthropic_function_tool(tool: dict[str, Any]) -> bool:
    return (
        isinstance(tool.get("name"), str)
        and isinstance(tool.get("description"), str)
        and isinstance(tool.get("input_schema"), dict)
    )


def extract_api_token(auth_header: str | None, x_api_key: str | None) -> str:
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
    elif x_api_key:
        token = x_api_key.strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing api key")
    return token


def resolve_auth_context(
    auth_header: str | None,
    x_api_key: str | None,
    *,
    db: sqlite3.Connection,
) -> AuthContext:
    token = extract_api_token(auth_header, x_api_key)
    record = get_api_key_by_hash(db, hash_api_key(token))
    if record is None or record["status"] != "active":
        raise HTTPException(status_code=401, detail="invalid api key")

    return AuthContext(
        source="db",
        api_key_id=record["id"],
        name=record["name"],
        scopes=list(record["scopes"]),
        rpm_limit=record["rpm_limit"],
        concurrency_limit=record["concurrency_limit"],
    )


def require_scope(auth: AuthContext, scope: str) -> None:
    if "admin" in auth.scopes:
        return
    if scope not in auth.scopes:
        raise HTTPException(status_code=403, detail=f"missing required scope: {scope}")


def resolve_route(model_name: str, models: Dict[str, ModelRoute]) -> ModelRoute:
    route = models.get(model_name)
    if route and route.enabled:
        return route
    raise HTTPException(status_code=404, detail=f"unknown model: {model_name}")


def ensure_route_supports_request(
    route: ModelRoute,
    req: NormalizedRequest,
    *,
    runtime_caps: dict[str, Any] | None = None,
    adapter: str | None = None,
) -> None:
    caps = runtime_caps or route.runtime_capabilities()
    native_protocols = caps["native_protocols"]
    protocol_features = caps["protocol_features"]
    tool_policies = caps["tool_policies"]

    if req.client_protocol not in native_protocols and adapter is None:
        raise HTTPException(status_code=400, detail="native_protocol_not_supported")
    if req.stream and not protocol_features.get("stream", False):
        raise HTTPException(status_code=400, detail="stream_not_supported_for_model")
    for tool in req.tools or []:
        tool_type = tool.get("type")
        if tool_type == "function":
            if not tool_policies.get("openai_function_tools", False):
                raise HTTPException(status_code=400, detail="openai_function_tools_not_supported")
            continue
        if tool_type is None and is_anthropic_function_tool(tool):
            if not tool_policies.get("anthropic_function_tools", False):
                raise HTTPException(status_code=400, detail="anthropic_function_tools_not_supported")
            continue
        if not tool_policies.get("builtin_tools", False):
            raise HTTPException(status_code=400, detail="builtin_tools_not_supported")


def strip_claude_code_builtin_tools_for_managed_messages(
    route: ModelRoute,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    if route.lifecycle_mode != "managed_local" or route.upstream_protocol != "chat":
        return payload
    tools = payload.get("tools")
    if not isinstance(tools, list) or route.capabilities.supports_builtin_tools:
        return payload
    filtered_tools: list[dict[str, Any]] = []
    stripped = False
    for tool in tools:
        if not isinstance(tool, dict):
            filtered_tools.append(tool)
            continue
        tool_type = tool.get("type")
        if isinstance(tool_type, str) and tool_type.startswith(_CLAUDE_CODE_BUILTIN_TOOL_PREFIXES):
            stripped = True
            continue
        filtered_tools.append(tool)
    if not stripped:
        return payload
    sanitized = dict(payload)
    if filtered_tools:
        sanitized["tools"] = filtered_tools
    else:
        sanitized.pop("tools", None)
        sanitized.pop("tool_choice", None)
    return sanitized


def select_upstream_adapter(
    route: ModelRoute,
    req: NormalizedRequest,
    *,
    runtime_caps: dict[str, Any] | None = None,
) -> str:
    caps = runtime_caps or route.runtime_capabilities()
    allowed = set(caps["adapter_policies"])
    if route.upstream_protocol == "responses":
        return "native_responses"
    if route.upstream_protocol == "chat" and req.client_protocol == "responses" and "responses->chat" in allowed:
        return "responses_to_chat"
    if route.upstream_protocol == "messages" and req.client_protocol == "responses" and "responses->messages" in allowed:
        return "responses_to_messages"
    raise HTTPException(status_code=400, detail="adapter_not_enabled_for_route")


def plan_route_execution(
    route: ModelRoute,
    req: NormalizedRequest,
) -> RouteExecutionPlan:
    runtime_caps = route.runtime_capabilities()
    selected_adapter: str | None = None
    execution_mode = "native"
    if req.client_protocol not in runtime_caps["native_protocols"]:
        if req.client_protocol == "responses":
            selected_adapter = select_upstream_adapter(route, req, runtime_caps=runtime_caps)
            execution_mode = "adapter"
    ensure_route_supports_request(
        route,
        req,
        runtime_caps=runtime_caps,
        adapter=selected_adapter,
    )
    return RouteExecutionPlan(
        route=route,
        runtime_caps=runtime_caps,
        client_protocol=req.client_protocol,
        execution_mode=execution_mode,
        selected_adapter=selected_adapter,
    )


def build_upstream_headers(route: ModelRoute) -> dict[str, str] | None:
    if route.upstream_auth_kind == "none":
        return None
    if not route.upstream_auth_ref:
        raise HTTPException(status_code=500, detail="missing_upstream_auth_ref")
    secret = os.getenv(route.upstream_auth_ref)
    if not secret:
        raise HTTPException(status_code=500, detail="missing_upstream_auth_secret")
    headers: dict[str, str] = {}
    if route.upstream_auth_kind == "bearer":
        headers["authorization"] = f"Bearer {secret}"
    elif route.upstream_auth_kind == "x_api_key":
        headers["x-api-key"] = secret
    return headers or None


async def proxy_openai_chat(payload: Dict[str, Any], ctx: GatewayContext) -> Dict[str, Any]:
    route = resolve_route(payload["model"], ctx.models)
    if route.upstream_protocol != "chat":
        raise HTTPException(status_code=400, detail="unsupported_route_protocol_combination")
    if route.lifecycle_mode == "external":
        if ctx.post_json_to is None:
            raise HTTPException(status_code=500, detail="external_post_json_unavailable")
        upstream_payload = dict(payload)
        upstream_payload["model"] = route.resolved_upstream_model() or payload["model"]
        return await ctx.post_json_to(
            route.upstream_base_url or "",
            "/v1/chat/completions",
            upstream_payload,
            build_upstream_headers(route),
        )
    return await ctx.backend_client.post_json("/v1/chat/completions", payload)


async def proxy_openai_chat_via_route(
    route: ModelRoute,
    payload: Dict[str, Any],
    ctx: GatewayContext,
) -> Dict[str, Any]:
    if route.upstream_protocol != "chat":
        raise HTTPException(status_code=400, detail="unsupported_route_protocol_combination")
    if route.lifecycle_mode == "external":
        if ctx.post_json_to is None:
            raise HTTPException(status_code=500, detail="external_post_json_unavailable")
        upstream_payload = dict(payload)
        upstream_payload["model"] = route.resolved_upstream_model() or payload["model"]
        return await ctx.post_json_to(
            route.upstream_base_url or "",
            "/v1/chat/completions",
            upstream_payload,
            build_upstream_headers(route),
        )
    return await ctx.backend_client.post_json("/v1/chat/completions", payload)


async def proxy_anthropic_messages(payload: Dict[str, Any], ctx: GatewayContext) -> Dict[str, Any]:
    route = resolve_route(payload["model"], ctx.models)
    if route.lifecycle_mode == "external":
        if route.upstream_protocol != "messages":
            raise HTTPException(status_code=400, detail="unsupported_route_protocol_combination")
        if ctx.post_json_to is None:
            raise HTTPException(status_code=500, detail="external_post_json_unavailable")
        upstream_payload = dict(payload)
        upstream_payload["model"] = route.resolved_upstream_model() or payload["model"]
        return await ctx.post_json_to(
            route.upstream_base_url or "",
            "/v1/messages",
            upstream_payload,
            build_upstream_headers(route),
        )
    return await ctx.backend_client.post_json("/v1/messages", payload)


async def stream_openai_chat(payload: Dict[str, Any], ctx: GatewayContext):
    route = resolve_route(payload["model"], ctx.models)
    if route.upstream_protocol != "chat":
        raise HTTPException(status_code=400, detail="unsupported_route_protocol_combination")
    if route.lifecycle_mode == "external":
        if ctx.stream_bytes_from is None:
            raise HTTPException(status_code=500, detail="external_stream_unavailable")
        upstream_payload = dict(payload)
        upstream_payload["model"] = route.resolved_upstream_model() or payload["model"]
        return ctx.stream_bytes_from(
            route.upstream_base_url or "",
            "/v1/chat/completions",
            upstream_payload,
            build_upstream_headers(route),
        )
    return ctx.backend_client.stream_bytes("/v1/chat/completions", payload)


async def stream_openai_chat_via_route(
    route: ModelRoute,
    payload: Dict[str, Any],
    ctx: GatewayContext,
):
    if route.upstream_protocol != "chat":
        raise HTTPException(status_code=400, detail="unsupported_route_protocol_combination")
    if route.lifecycle_mode == "external":
        if ctx.stream_bytes_from is None:
            raise HTTPException(status_code=500, detail="external_stream_unavailable")
        upstream_payload = dict(payload)
        upstream_payload["model"] = route.resolved_upstream_model() or payload["model"]
        return ctx.stream_bytes_from(
            route.upstream_base_url or "",
            "/v1/chat/completions",
            upstream_payload,
            build_upstream_headers(route),
        )
    return ctx.backend_client.stream_bytes("/v1/chat/completions", payload)


async def stream_anthropic_messages(payload: Dict[str, Any], ctx: GatewayContext):
    route = resolve_route(payload["model"], ctx.models)
    if route.lifecycle_mode == "external":
        if route.upstream_protocol != "messages":
            raise HTTPException(status_code=400, detail="unsupported_route_protocol_combination")
        if ctx.stream_bytes_from is None:
            raise HTTPException(status_code=500, detail="external_stream_unavailable")
        upstream_payload = dict(payload)
        upstream_payload["model"] = route.resolved_upstream_model() or payload["model"]
        return ctx.stream_bytes_from(
            route.upstream_base_url or "",
            "/v1/messages",
            upstream_payload,
            build_upstream_headers(route),
        )
    return ctx.backend_client.stream_bytes("/v1/messages", payload)
