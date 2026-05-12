from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone

from fastapi import FastAPI

from ..config import PROJECT_ROOT, load_settings
from ..storage.db import init_db, list_agent_events, write_agent_event
from .backend import LlamaCppBackendDriver, SGLangBackendDriver, VLLMBackendDriver
from .docker_control import LlamaCppContainerSpec, SGLangContainerSpec, VLLMContainerSpec
from .state import AgentState


def create_agent_app(enable_monitor: bool = True) -> FastAPI:
    settings = load_settings()

    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _seconds_since(timestamp: str) -> float | None:
        if not timestamp:
            return None
        try:
            return (datetime.now(timezone.utc) - datetime.fromisoformat(timestamp)).total_seconds()
        except ValueError:
            return None

    def _within_startup_grace(snapshot: dict[str, object] | None) -> bool:
        started_seconds_ago = _seconds_since(app.state.agent.started_at)
        if started_seconds_ago is None or started_seconds_ago > app.state.startup_grace_period:
            return False
        if not snapshot:
            return False
        return bool(snapshot.get("exists")) and str(snapshot.get("status")) == "running"

    async def _refresh_state() -> bool:
        ready = await app.state.backend_driver.health(app.state.backend_url)
        app.state.agent.backend_ready = ready
        app.state.agent.checked_at = _utc_now()
        if ready:
            app.state.agent.failure_count = 0
            if app.state.agent.status in {"starting", "recovering", "stopped", "degraded"}:
                app.state.agent.mark("ready")
                write_agent_event(app.state.db, "ready", "backend healthy")
            return True

        app.state.agent.failure_count += 1
        if app.state.agent.status == "ready":
            app.state.agent.mark("degraded", "backend became unavailable")
            write_agent_event(app.state.db, "degraded", "backend became unavailable")
        elif app.state.agent.status == "starting":
            app.state.agent.mark("starting", "waiting for backend")
        elif not app.state.agent.last_error:
            app.state.agent.last_error = "backend unavailable"
        return False

    async def _recover_if_needed() -> None:
        if not app.state.auto_recover:
            return
        if app.state.agent.failure_count < app.state.recovery_threshold:
            return
        if app.state.recovery_lock.locked():
            return
        snapshot = await app.state.run_sync(app.state.backend_driver.snapshot)
        if _within_startup_grace(snapshot):
            app.state.agent.mark("starting", "waiting for backend warmup")
            return
        async with app.state.recovery_lock:
            if app.state.agent.status == "recovering":
                return
            app.state.agent.mark("recovering", "auto recovery triggered")
            write_agent_event(app.state.db, "recovering", "auto recovery triggered")
            with suppress(Exception):
                await app.state.run_sync(app.state.backend_driver.stop)
            with suppress(Exception):
                await app.state.run_sync(app.state.backend_driver.start)
            app.state.agent.last_recovery_at = _utc_now()
            app.state.agent.failure_count = 0
            app.state.agent.mark("starting", "recovery restart issued")
            write_agent_event(app.state.db, "starting", "recovery restart issued")

    async def _monitor_loop() -> None:
        while True:
            try:
                ready = await _refresh_state()
                if not ready:
                    await _recover_if_needed()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                app.state.agent.mark("alerting", f"monitor error: {exc}")
                write_agent_event(app.state.db, "alerting", f"monitor error: {exc}")
            await asyncio.sleep(app.state.poll_interval)

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI):
        if enable_monitor and fastapi_app.state.monitor_task is None:
            fastapi_app.state.monitor_task = asyncio.create_task(_monitor_loop())
        try:
            yield
        finally:
            if fastapi_app.state.monitor_task is not None:
                fastapi_app.state.monitor_task.cancel()
                with suppress(asyncio.CancelledError):
                    await fastapi_app.state.monitor_task
                fastapi_app.state.monitor_task = None

    app = FastAPI(title="llmnode_agent", version="0.1.0", lifespan=lifespan)
    app.state.agent = AgentState(status=settings.agent.state)
    app.state.backend_url = settings.gateway.backend_url
    bt = settings.vllm.backend_type
    if bt == "llama.cpp":
        spec = LlamaCppContainerSpec(
            container_name=settings.vllm.container_name,
            image_name=settings.vllm.image_name,
            model_dir=settings.vllm.model_dir,
            model_file=settings.vllm.model_file,
            model_name=settings.vllm.model_name,
            host_port=settings.vllm.host_port,
            n_gpu_layers=settings.vllm.n_gpu_layers,
            ctx_size=settings.vllm.ctx_size,
            n_parallel=settings.vllm.n_parallel,
            shm_size=settings.vllm.shm_size,
        )
        app.state.backend_driver = LlamaCppBackendDriver(spec=spec)
    elif bt == "sglang":
        spec = SGLangContainerSpec(
            container_name=settings.vllm.container_name,
            image_name=settings.vllm.image_name,
            model_dir=settings.vllm.model_dir,
            model_name=settings.vllm.model_name,
            host_port=settings.vllm.host_port,
            tp_size=settings.vllm.tensor_parallel_size,
            mem_fraction_static=settings.vllm.mem_fraction_static,
            max_running_requests=settings.vllm.max_running_requests,
            shm_size=settings.vllm.shm_size,
            reasoning_parser=settings.vllm.reasoning_parser,
        )
        app.state.backend_driver = SGLangBackendDriver(spec=spec)
    else:
        spec = VLLMContainerSpec(
            container_name=settings.vllm.container_name,
            image_name=settings.vllm.image_name,
            model_dir=settings.vllm.model_dir,
            model_name=settings.vllm.model_name,
            host_port=settings.vllm.host_port,
            gpu_memory_utilization=settings.vllm.gpu_memory_utilization,
            tensor_parallel_size=settings.vllm.tensor_parallel_size,
            max_model_len=settings.vllm.max_model_len,
            max_num_seqs=settings.vllm.max_num_seqs,
            shm_size=settings.vllm.shm_size,
            enable_auto_tool_choice=settings.vllm.enable_auto_tool_choice,
            reasoning_parser=settings.vllm.reasoning_parser,
            tool_call_parser=settings.vllm.tool_call_parser,
        )
        app.state.backend_driver = VLLMBackendDriver(spec=spec)
    app.state.backend_type = bt
    app.state.poll_interval = int(getattr(settings.agent, "poll_interval", 15))
    app.state.auto_recover = bool(getattr(settings.agent, "auto_recover", True))
    app.state.recovery_threshold = int(getattr(settings.agent, "recovery_threshold", 2))
    app.state.startup_grace_period = int(getattr(settings.agent, "startup_grace_period", 180))
    app.state.recovery_lock = asyncio.Lock()
    app.state.monitor_task = None
    app.state.run_sync = asyncio.to_thread
    app.state.db = init_db(PROJECT_ROOT / "runtime" / "data" / "gateway.db")

    @app.get("/health/liveliness")
    async def liveliness():
        return {"status": app.state.agent.status}

    @app.get("/state")
    async def state():
        ready = await _refresh_state()
        if not ready:
            await _recover_if_needed()
        return {
            "status": app.state.agent.status,
            "backend_ready": ready,
            "failure_count": app.state.agent.failure_count,
            "checked_at": app.state.agent.checked_at,
            "last_error": app.state.agent.last_error,
            "last_recovery_at": app.state.agent.last_recovery_at,
            "started_at": app.state.agent.started_at,
        }

    @app.get("/container")
    async def container():
        snapshot = await app.state.run_sync(app.state.backend_driver.snapshot)
        return {"backend_type": app.state.backend_type, "container": snapshot}

    @app.get("/events")
    async def events(limit: int = 50):
        return {"events": list_agent_events(app.state.db, limit=limit)}

    @app.post("/manage/start")
    async def start_backend():
        await app.state.run_sync(app.state.backend_driver.start)
        app.state.agent.mark("starting", "manual start requested")
        write_agent_event(app.state.db, "starting", "manual start requested")
        return {"status": app.state.agent.status}

    @app.post("/manage/stop")
    async def stop_backend():
        await app.state.run_sync(app.state.backend_driver.stop)
        app.state.agent.mark("stopped", "manual stop requested")
        write_agent_event(app.state.db, "stopped", "manual stop requested")
        return {"status": app.state.agent.status}

    @app.post("/manage/restart")
    async def restart_backend():
        await app.state.run_sync(app.state.backend_driver.restart)
        app.state.agent.mark("recovering", "manual restart requested")
        write_agent_event(app.state.db, "recovering", "manual restart requested")
        return {"status": app.state.agent.status}

    return app
