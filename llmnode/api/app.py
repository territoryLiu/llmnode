from __future__ import annotations

import asyncio
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
from fastapi.responses import JSONResponse, StreamingResponse

from ..config import PROJECT_ROOT, load_settings
from ..logging import setup_logging
from ..models import ModelRoute, load_model_catalog, logical_models_for_api, model_routes_for_admin
from ..protocols import AnthropicMessagesRequest, OpenAIChatCompletionsRequest
from ..proxy.backend import VLLMBackendClient
from ..proxy.router import (
    AuthContext,
    GatewayContext,
    proxy_anthropic_messages,
    proxy_openai_chat,
    require_scope,
    resolve_auth_context,
    stream_anthropic_messages,
    stream_openai_chat,
)

_VALID_BACKEND_TYPES = {"vllm", "llama.cpp", "sglang"}
from ..runtime import QueueFullError, QueueTimeoutError, RequestGate
from ..runtime import ApiKeyConcurrencyError, ApiKeyGate, ApiKeyRateLimitError
from ..security import generate_api_key, hash_api_key
from ..storage.db import (
    aggregate_usage_for_api_key,
    create_api_key,
    delete_api_key,
    get_api_key_by_id,
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
    upsert_model_route,
    upsert_schedule_config,
    write_request_metric,
    write_request_log,
)

_MISSING = object()
_ALLOWED_SCOPES = {"admin", "inference"}
_ALLOWED_STATUSES = {"active", "disabled"}


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
        bootstrap_key=request.app.state.ctx.api_key,
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
    }


def _elapsed_ms(started_at: datetime, finished_at: datetime) -> float:
    return (finished_at - started_at).total_seconds() * 1000.0


def _extract_usage(payload: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None, None, None
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")
    return prompt_tokens, completion_tokens, total_tokens


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
) -> None:
    prompt_tokens, completion_tokens, total_tokens = _extract_usage(response_payload or {})
    latency_ms = _elapsed_ms(started_at, finished_at)
    tokens_per_second = None
    if completion_tokens is not None and latency_ms > 0:
        tokens_per_second = completion_tokens / (latency_ms / 1000.0)
    with suppress(Exception):
        write_request_metric(
            app.state.db,
            request_id=request_id,
            model_name=model_name,
            protocol=protocol,
            status=status,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            tokens_per_second=tokens_per_second,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
        )


def _sanitize_api_key_row(row: dict[str, Any], *, masked_key: str | None = None) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "masked_key": masked_key or stable_masked_key(row["id"]),
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
        db_path = PROJECT_ROOT / "runtime" / "data" / "gateway-test.db"
        with suppress(FileNotFoundError):
            db_path.unlink()
    catalog = load_model_catalog()
    db = init_db(db_path)
    seed_model_routes(db, model_routes_for_admin(catalog))
    schedule_state = load_schedule_config(db)
    if schedule_state is None:
        schedule_state = asdict(settings.schedule)
        upsert_schedule_config(db, schedule_state)
    backend_client = VLLMBackendClient(base_url=settings.gateway.backend_url, backend_type=settings.vllm.backend_type)
    ctx = GatewayContext(
        api_key=settings.gateway.api_key,
        backend_client=backend_client,
        models={item["name"]: ModelRoute(**item) for item in list_model_routes(db)},
    )
    request_gate = RequestGate(
        execution_limit=settings.gateway.execution_limit,
        queue_limit=settings.gateway.queue_limit,
    )
    api_key_gate = ApiKeyGate()

    app = FastAPI(title="llmnode", version="0.1.0")
    app.state.ctx = ctx
    app.state.request_gate = request_gate
    app.state.api_key_gate = api_key_gate
    app.state.db = db
    app.state.agent_base_url = settings.gateway.agent_base_url
    app.state.agent_status_url = settings.gateway.agent_status_url
    app.state.require_agent_ready = settings.gateway.require_agent_ready
    app.state.schedule = schedule_state

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
            "backend_type": app.state.ctx.backend_client.backend_type,
            "backend_ready": backend_ready,
            "backend_error": backend_error,
            "backend_container": backend_container,
            "agent_state": agent_state,
            "require_agent_ready": app.state.require_agent_ready,
            "queue_length": app.state.request_gate.waiting,
            "models": logical_models_for_api(app.state.ctx.models),
            "logs": list_request_logs(app.state.db, limit=20),
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
                    "api_key_configured": bool(settings.gateway.api_key),
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
    async def admin_request_logs(request: Request, limit: int = 50):
        _resolve_auth(request, "admin")
        request_id = _request_id(request)
        response = JSONResponse({"logs": list_request_logs(request.app.state.db, limit=limit)})
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/admin/logs")
    async def admin_logs(request: Request, limit: int = 50):
        _resolve_auth(request, "admin")
        request_id = _request_id(request)
        response = JSONResponse({"logs": list_request_logs(request.app.state.db, limit=limit)})
        response.headers["x-request-id"] = request_id
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

    @app.patch("/admin/models/{name}")
    async def admin_update_model(request: Request, name: str):
        _resolve_auth(request, "admin")
        payload = await _read_json_body(request)
        route = request.app.state.ctx.models.get(name)
        if route is None:
            raise HTTPException(status_code=404, detail=f"unknown model: {name}")
        backend_type = payload.get("backend_type", route.backend_type)
        if backend_type not in _VALID_BACKEND_TYPES:
            raise HTTPException(status_code=400, detail=f"unsupported backend_type: {backend_type}")
        updated = replace(
            route,
            display_name=payload.get("display_name", route.display_name),
            backend_model=payload.get("backend_model", route.backend_model),
            backend_type=backend_type,
            enabled=bool(payload.get("enabled", route.enabled)),
        )
        request.app.state.ctx.models[name] = updated
        upsert_model_route(request.app.state.db, asdict(updated))
        request_id = _request_id(request)
        response = JSONResponse({"model": model_routes_for_admin({name: updated})[0]})
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
        request_id = _request_id(request)
        started_at = datetime.now(timezone.utc)
        log_context = _request_log_context(request, auth)
        try:
            key_lease = await request.app.state.api_key_gate.begin(
                auth.api_key_id,
                rpm_limit=auth.rpm_limit,
                concurrency_limit=auth.concurrency_limit,
            )
        except ApiKeyRateLimitError as exc:
            log_context["rejection_reason"] = "rpm_limit_exceeded"
            write_request_log(
                request.app.state.db,
                request_id,
                payload.model,
                "rejected",
                "openai",
                str(exc),
                **log_context,
            )
            raise HTTPException(status_code=429, detail=str(exc), headers={"x-request-id": request_id}) from exc
        except ApiKeyConcurrencyError as exc:
            log_context["rejection_reason"] = "concurrency_limit_exceeded"
            write_request_log(
                request.app.state.db,
                request_id,
                payload.model,
                "rejected",
                "openai",
                str(exc),
                **log_context,
            )
            raise HTTPException(status_code=429, detail=str(exc), headers={"x-request-id": request_id}) from exc
        if payload.stream:
            gate = request.app.state.request_gate.slot()
            try:
                await gate.__aenter__()
                stream = await stream_openai_chat(payload.to_backend_payload(payload.model), request.app.state.ctx)
            except QueueFullError as exc:
                await key_lease.reject()
                finished_at = datetime.now(timezone.utc)
                log_context["rejection_reason"] = "queue_full"
                _record_request_metric(
                    request.app,
                    request_id=request_id,
                    model_name=payload.model,
                    protocol="openai",
                    status="rejected",
                    started_at=started_at,
                    finished_at=finished_at,
                )
                write_request_log(
                    request.app.state.db,
                    request_id,
                    payload.model,
                    "rejected",
                    "openai",
                    str(exc),
                    **log_context,
                )
                raise HTTPException(status_code=429, detail=str(exc), headers={"x-request-id": request_id}) from exc
            except QueueTimeoutError as exc:
                await key_lease.reject()
                finished_at = datetime.now(timezone.utc)
                log_context["rejection_reason"] = "queue_timeout"
                _record_request_metric(
                    request.app,
                    request_id=request_id,
                    model_name=payload.model,
                    protocol="openai",
                    status="timeout",
                    started_at=started_at,
                    finished_at=finished_at,
                )
                write_request_log(
                    request.app.state.db,
                    request_id,
                    payload.model,
                    "timeout",
                    "openai",
                    str(exc),
                    **log_context,
                )
                raise HTTPException(status_code=504, detail=str(exc), headers={"x-request-id": request_id}) from exc
            except Exception:
                await key_lease.reject()
                await gate.__aexit__(None, None, None)
                raise

            async def body():
                try:
                    async for chunk in stream:
                        yield chunk
                finally:
                    await key_lease.finish()
                    await gate.__aexit__(None, None, None)

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
            await key_lease.reject()
            finished_at = datetime.now(timezone.utc)
            log_context["rejection_reason"] = "queue_full"
            _record_request_metric(
                request.app,
                request_id=request_id,
                model_name=payload.model,
                protocol="openai",
                status="rejected",
                started_at=started_at,
                finished_at=finished_at,
            )
            write_request_log(
                request.app.state.db,
                request_id,
                payload.model,
                "rejected",
                "openai",
                str(exc),
                **log_context,
            )
            raise HTTPException(status_code=429, detail=str(exc), headers={"x-request-id": request_id}) from exc
        except QueueTimeoutError as exc:
            await key_lease.reject()
            finished_at = datetime.now(timezone.utc)
            log_context["rejection_reason"] = "queue_timeout"
            _record_request_metric(
                request.app,
                request_id=request_id,
                model_name=payload.model,
                protocol="openai",
                status="timeout",
                started_at=started_at,
                finished_at=finished_at,
            )
            write_request_log(
                request.app.state.db,
                request_id,
                payload.model,
                "timeout",
                "openai",
                str(exc),
                **log_context,
            )
            raise HTTPException(status_code=504, detail=str(exc), headers={"x-request-id": request_id}) from exc
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

    @app.post("/v1/messages")
    async def anthropic_messages(request: Request):
        auth = _resolve_auth(request, "inference")
        await ensure_agent_ready()
        raw = await _read_json_body(request)
        payload = AnthropicMessagesRequest.model_validate(raw)
        request_id = _request_id(request)
        started_at = datetime.now(timezone.utc)
        log_context = _request_log_context(request, auth)
        try:
            key_lease = await request.app.state.api_key_gate.begin(
                auth.api_key_id,
                rpm_limit=auth.rpm_limit,
                concurrency_limit=auth.concurrency_limit,
            )
        except ApiKeyRateLimitError as exc:
            log_context["rejection_reason"] = "rpm_limit_exceeded"
            write_request_log(
                request.app.state.db,
                request_id,
                payload.model,
                "rejected",
                "anthropic",
                str(exc),
                **log_context,
            )
            raise HTTPException(status_code=429, detail=str(exc), headers={"x-request-id": request_id}) from exc
        except ApiKeyConcurrencyError as exc:
            log_context["rejection_reason"] = "concurrency_limit_exceeded"
            write_request_log(
                request.app.state.db,
                request_id,
                payload.model,
                "rejected",
                "anthropic",
                str(exc),
                **log_context,
            )
            raise HTTPException(status_code=429, detail=str(exc), headers={"x-request-id": request_id}) from exc
        if payload.stream:
            gate = request.app.state.request_gate.slot()
            try:
                await gate.__aenter__()
                stream = await stream_anthropic_messages(payload.to_backend_payload(payload.model), request.app.state.ctx)
            except QueueFullError as exc:
                await key_lease.reject()
                finished_at = datetime.now(timezone.utc)
                log_context["rejection_reason"] = "queue_full"
                _record_request_metric(
                    request.app,
                    request_id=request_id,
                    model_name=payload.model,
                    protocol="anthropic",
                    status="rejected",
                    started_at=started_at,
                    finished_at=finished_at,
                )
                write_request_log(
                    request.app.state.db,
                    request_id,
                    payload.model,
                    "rejected",
                    "anthropic",
                    str(exc),
                    **log_context,
                )
                raise HTTPException(status_code=429, detail=str(exc), headers={"x-request-id": request_id}) from exc
            except QueueTimeoutError as exc:
                await key_lease.reject()
                finished_at = datetime.now(timezone.utc)
                log_context["rejection_reason"] = "queue_timeout"
                _record_request_metric(
                    request.app,
                    request_id=request_id,
                    model_name=payload.model,
                    protocol="anthropic",
                    status="timeout",
                    started_at=started_at,
                    finished_at=finished_at,
                )
                write_request_log(
                    request.app.state.db,
                    request_id,
                    payload.model,
                    "timeout",
                    "anthropic",
                    str(exc),
                    **log_context,
                )
                raise HTTPException(status_code=504, detail=str(exc), headers={"x-request-id": request_id}) from exc
            except Exception:
                await key_lease.reject()
                await gate.__aexit__(None, None, None)
                raise

            async def body():
                try:
                    async for chunk in stream:
                        yield chunk
                finally:
                    await key_lease.finish()
                    await gate.__aexit__(None, None, None)

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
            await key_lease.reject()
            finished_at = datetime.now(timezone.utc)
            log_context["rejection_reason"] = "queue_full"
            _record_request_metric(
                request.app,
                request_id=request_id,
                model_name=payload.model,
                protocol="anthropic",
                status="rejected",
                started_at=started_at,
                finished_at=finished_at,
            )
            write_request_log(
                request.app.state.db,
                request_id,
                payload.model,
                "rejected",
                "anthropic",
                str(exc),
                **log_context,
            )
            raise HTTPException(status_code=429, detail=str(exc), headers={"x-request-id": request_id}) from exc
        except QueueTimeoutError as exc:
            await key_lease.reject()
            finished_at = datetime.now(timezone.utc)
            log_context["rejection_reason"] = "queue_timeout"
            _record_request_metric(
                request.app,
                request_id=request_id,
                model_name=payload.model,
                protocol="anthropic",
                status="timeout",
                started_at=started_at,
                finished_at=finished_at,
            )
            write_request_log(
                request.app.state.db,
                request_id,
                payload.model,
                "timeout",
                "anthropic",
                str(exc),
                **log_context,
            )
            raise HTTPException(status_code=504, detail=str(exc), headers={"x-request-id": request_id}) from exc
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

    return app
