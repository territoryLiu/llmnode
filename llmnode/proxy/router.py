from __future__ import annotations

import sqlite3
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
    raise HTTPException(status_code=400, detail="unsupported_route_protocol_combination")


async def proxy_openai_chat(payload: Dict[str, Any], ctx: GatewayContext) -> Dict[str, Any]:
    resolve_route(payload["model"], ctx.models)
    return await ctx.backend_client.post_json("/v1/chat/completions", payload)


async def proxy_anthropic_messages(payload: Dict[str, Any], ctx: GatewayContext) -> Dict[str, Any]:
    resolve_route(payload["model"], ctx.models)
    return await ctx.backend_client.post_json("/v1/messages", payload)


async def stream_openai_chat(payload: Dict[str, Any], ctx: GatewayContext):
    resolve_route(payload["model"], ctx.models)
    return ctx.backend_client.stream_bytes("/v1/chat/completions", payload)


async def stream_anthropic_messages(payload: Dict[str, Any], ctx: GatewayContext):
    resolve_route(payload["model"], ctx.models)
    return ctx.backend_client.stream_bytes("/v1/messages", payload)
