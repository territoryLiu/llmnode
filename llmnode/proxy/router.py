from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Dict

from fastapi import HTTPException

from ..models import ModelRoute
from ..security import hash_api_key
from ..storage.db import get_api_key_by_hash
from .backend import BackendClient


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
    api_key: str
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
    bootstrap_key: str,
    db: sqlite3.Connection,
) -> AuthContext:
    token = extract_api_token(auth_header, x_api_key)
    if token == bootstrap_key:
        return AuthContext(
            source="bootstrap",
            api_key_id=None,
            name="bootstrap",
            scopes=["admin", "inference"],
            rpm_limit=None,
            concurrency_limit=None,
        )

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


async def proxy_openai_chat(payload: Dict[str, Any], ctx: GatewayContext) -> Dict[str, Any]:
    route = resolve_route(payload["model"], ctx.models)
    payload = dict(payload)
    payload["model"] = route.backend_model
    if not await ctx.backend_client.health():
        raise HTTPException(status_code=503, detail="backend vllm is not ready")
    return await ctx.backend_client.post_json("/v1/chat/completions", payload)


async def proxy_anthropic_messages(payload: Dict[str, Any], ctx: GatewayContext) -> Dict[str, Any]:
    route = resolve_route(payload["model"], ctx.models)
    payload = dict(payload)
    payload["model"] = route.backend_model
    if not await ctx.backend_client.health():
        raise HTTPException(status_code=503, detail="backend vllm is not ready")
    return await ctx.backend_client.post_json("/v1/messages", payload)


async def stream_openai_chat(payload: Dict[str, Any], ctx: GatewayContext):
    route = resolve_route(payload["model"], ctx.models)
    payload = dict(payload)
    payload["model"] = route.backend_model
    if not await ctx.backend_client.health():
        raise HTTPException(status_code=503, detail="backend vllm is not ready")
    return ctx.backend_client.stream_bytes("/v1/chat/completions", payload)


async def stream_anthropic_messages(payload: Dict[str, Any], ctx: GatewayContext):
    route = resolve_route(payload["model"], ctx.models)
    payload = dict(payload)
    payload["model"] = route.backend_model
    if not await ctx.backend_client.health():
        raise HTTPException(status_code=503, detail="backend vllm is not ready")
    return ctx.backend_client.stream_bytes("/v1/messages", payload)
