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


def ensure_route_supports_request(route: ModelRoute, req: NormalizedRequest) -> None:
    if req.client_protocol == "chat" and not route.capabilities.supports_chat:
        raise HTTPException(status_code=400, detail="chat_not_supported_for_model")
    if (
        req.client_protocol == "messages"
        and not route.capabilities.supports_messages
        and not (route.lifecycle_mode == "managed_local" and route.upstream_protocol == "chat")
    ):
        raise HTTPException(status_code=400, detail="messages_not_supported_for_model")
    if req.client_protocol == "responses" and route.upstream_protocol == "responses" and not route.capabilities.supports_responses:
        raise HTTPException(status_code=400, detail="responses_not_supported_for_model")
    if req.stream and not route.capabilities.supports_stream:
        raise HTTPException(status_code=400, detail="stream_not_supported_for_model")
    for tool in req.tools or []:
        tool_type = tool.get("type")
        if tool_type != "function" and not route.capabilities.supports_builtin_tools:
            raise HTTPException(status_code=400, detail="unsupported_builtin_tools")
        if tool_type == "function" and not route.capabilities.supports_function_tools:
            raise HTTPException(status_code=400, detail="unsupported_function_tools")


def select_upstream_adapter(route: ModelRoute, req: NormalizedRequest) -> str:
    if route.upstream_protocol == "responses":
        return "native_responses"
    if route.upstream_protocol == "chat" and req.client_protocol == "responses":
        return "responses_to_chat"
    if route.upstream_protocol == "messages" and req.client_protocol == "responses":
        return "responses_to_messages"
    raise HTTPException(status_code=400, detail="unsupported_route_protocol_combination")


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
