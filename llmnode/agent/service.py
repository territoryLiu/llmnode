from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI

from ..config import PROJECT_ROOT, load_settings
from ..diagnostics import (
    analyze_logs_for_errors,
    collect_cuda_version,
    collect_gpu_info,
    detect_model_format,
    format_uptime,
    get_container_logs,
    inspect_container,
    parse_model_config,
)
from ..storage.db import aggregate_request_metrics, init_db, list_agent_events, write_agent_event
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
        # Stage 1: HTTP health check
        http_ready = await app.state.backend_driver.health(app.state.backend_url)
        app.state.agent.http_ready = http_ready
        app.state.agent.backend_ready = http_ready
        app.state.agent.checked_at = _utc_now()

        if not http_ready:
            # HTTP not reachable — reset inference readiness
            app.state.agent.inference_ready = False
            app.state.agent.retry_after_seconds = None
            app.state.agent.last_probe_error = "backend http unreachable"
            app.state.agent.last_probe_latency_ms = None
            app.state.agent.failure_count += 1
            if app.state.agent.desired_state == "stopped":
                app.state.agent.mark("stopped", "manual stop requested")
                write_agent_event(
                    app.state.db, "stopped", "manual stop requested",
                    readiness_state="stopped", http_ready=False, inference_ready=False,
                )
                return False
            if app.state.agent.status == "ready":
                app.state.agent.mark("degraded", "backend became unavailable")
                write_agent_event(
                    app.state.db, "degraded", "backend became unavailable",
                    readiness_state="degraded", http_ready=False, inference_ready=False,
                )
            elif app.state.agent.status == "starting":
                app.state.agent.mark("starting", "waiting for backend")
            elif not app.state.agent.last_error:
                app.state.agent.last_error = "backend unavailable"
            return False

        # HTTP is reachable — reset failure counter
        app.state.agent.failure_count = 0

        # Stage 2: Inference probe
        probe_start = datetime.now(timezone.utc)
        try:
            model_name = settings.vllm.model_name or "unknown"
            await app.state.backend_driver.probe(app.state.backend_url, model_name)
            latency_ms = (datetime.now(timezone.utc) - probe_start).total_seconds() * 1000
            app.state.agent.inference_ready = True
            app.state.agent.retry_after_seconds = None
            app.state.agent.last_probe_error = ""
            app.state.agent.last_probe_latency_ms = latency_ms
        except Exception as exc:
            latency_ms = (datetime.now(timezone.utc) - probe_start).total_seconds() * 1000
            app.state.agent.inference_ready = False
            app.state.agent.retry_after_seconds = app.state.warming_up_retry_after
            app.state.agent.last_probe_error = str(exc)
            app.state.agent.last_probe_latency_ms = latency_ms

        # Determine status from readiness flags
        if app.state.agent.desired_state == "stopped":
            app.state.agent.mark("stopped", "manual stop requested")
            write_agent_event(
                app.state.db, "stopped", "manual stop requested",
                readiness_state="stopped", http_ready=True, inference_ready=app.state.agent.inference_ready,
            )
            return False

        if app.state.agent.inference_ready:
            # Both stages passed
            if app.state.agent.status in {"starting", "recovering", "degraded", "warming_up"} or (
                app.state.agent.status == "stopped" and app.state.agent.desired_state == "running"
            ):
                app.state.agent.mark("ready")
                write_agent_event(
                    app.state.db, "ready", "backend healthy",
                    readiness_state="ready", http_ready=True, inference_ready=True,
                )
            return True
        else:
            # HTTP ready but inference not ready — warming up
            if app.state.agent.status != "warming_up":
                app.state.agent.mark("warming_up", "backend http ready, inference probe pending")
                write_agent_event(
                    app.state.db, "warming_up", "backend http ready, inference probe pending",
                    readiness_state="warming_up", http_ready=True, inference_ready=False,
                )
            return False

    async def _recover_if_needed() -> None:
        if not app.state.auto_recover:
            return
        if app.state.agent.desired_state != "running":
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
    app.state.warming_up_retry_after = int(getattr(settings.agent, "warming_up_retry_after", 5))
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
            "desired_state": app.state.agent.desired_state,
            "backend_ready": ready,
            "http_ready": app.state.agent.http_ready,
            "inference_ready": app.state.agent.inference_ready,
            "retry_after_seconds": app.state.agent.retry_after_seconds,
            "failure_count": app.state.agent.failure_count,
            "checked_at": app.state.agent.checked_at,
            "last_error": app.state.agent.last_error,
            "last_recovery_at": app.state.agent.last_recovery_at,
            "started_at": app.state.agent.started_at,
            "last_transition_at": app.state.agent.last_transition_at,
            "last_probe_error": app.state.agent.last_probe_error,
            "last_probe_latency_ms": app.state.agent.last_probe_latency_ms,
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
        app.state.agent.desired_state = "running"
        await app.state.run_sync(app.state.backend_driver.start)
        app.state.agent.mark("starting", "manual start requested")
        write_agent_event(app.state.db, "starting", "manual start requested")
        return {"status": app.state.agent.status}

    @app.post("/manage/stop")
    async def stop_backend():
        app.state.agent.desired_state = "stopped"
        await app.state.run_sync(app.state.backend_driver.stop)
        app.state.agent.mark("stopped", "manual stop requested")
        write_agent_event(app.state.db, "stopped", "manual stop requested")
        return {"status": app.state.agent.status}

    @app.post("/manage/restart")
    async def restart_backend():
        app.state.agent.desired_state = "running"
        await app.state.run_sync(app.state.backend_driver.restart)
        app.state.agent.mark("recovering", "manual restart requested")
        write_agent_event(app.state.db, "recovering", "manual restart requested")
        return {"status": app.state.agent.status}

    @app.get("/admin/diagnostics/gpu")
    async def diagnostics_gpu():
        """获取 GPU 信息"""
        gpus = await app.state.run_sync(collect_gpu_info)
        cuda_version = await app.state.run_sync(collect_cuda_version)
        return {
            "gpus": gpus,
            "cuda_version": cuda_version,
        }

    @app.get("/admin/diagnostics/container")
    async def diagnostics_container():
        """获取容器详细信息"""
        snapshot = await app.state.run_sync(app.state.backend_driver.snapshot)
        container_name = snapshot.get("name", "")

        if not container_name:
            return {"error": "Container not found"}

        container_info = await app.state.run_sync(inspect_container, container_name)
        if container_info:
            container_info["uptime"] = format_uptime(container_info.get("started_at", ""))

        return {
            "backend_type": app.state.backend_type,
            "container": container_info,
            "snapshot": snapshot,
        }

    @app.get("/admin/diagnostics/model")
    async def diagnostics_model():
        """获取模型信息"""
        settings = load_settings()
        model_dir = Path(settings.vllm.model_dir)

        model_format = await app.state.run_sync(detect_model_format, model_dir)
        model_config = {}
        if model_format == "huggingface":
            model_config = await app.state.run_sync(parse_model_config, model_dir)

        return {
            "model_dir": str(model_dir),
            "model_name": settings.vllm.model_name,
            "model_format": model_format,
            "model_config": model_config,
        }

    @app.get("/admin/diagnostics/metrics")
    async def diagnostics_metrics():
        """获取请求指标聚合结果"""
        metrics = aggregate_request_metrics(app.state.db)
        metrics["queue_length"] = 0
        metrics["generated_at"] = _utc_now()
        return metrics

    @app.get("/admin/diagnostics/suggestions")
    async def diagnostics_suggestions():
        """获取智能建议"""
        settings = load_settings()
        suggestions = []

        # 检查容器日志
        snapshot = await app.state.run_sync(app.state.backend_driver.snapshot)
        container_name = snapshot.get("name", "")

        if container_name and snapshot.get("exists"):
            container_logs = await app.state.run_sync(get_container_logs, container_name, 20)
            log_suggestions = await app.state.run_sync(analyze_logs_for_errors, container_logs)
            suggestions.extend(log_suggestions)

        # 检查模型格式匹配
        model_dir = Path(settings.vllm.model_dir)
        model_format = await app.state.run_sync(detect_model_format, model_dir)
        backend_type = app.state.backend_type

        if backend_type == "vllm" and model_format == "gguf":
            suggestions.append("切换到 llama.cpp 后端或转换模型为 HuggingFace 格式")
        elif backend_type == "llama.cpp" and model_format == "huggingface":
            suggestions.append("切换到 vLLM 后端或转换模型为 GGUF 格式")

        # 检查 GPU
        gpus = await app.state.run_sync(collect_gpu_info)
        if not gpus and backend_type in ("vllm", "sglang"):
            suggestions.append("检查 GPU 驱动和 CUDA 安装，确认 nvidia-smi 可用")
            suggestions.append("检查 Docker 是否配置 nvidia-runtime")

        return {"suggestions": suggestions}

    @app.get("/admin/diagnostics/status")
    async def diagnostics_status():
        """获取完整诊断状态"""
        settings = load_settings()

        # GPU 信息
        gpus = await app.state.run_sync(collect_gpu_info)
        cuda_version = await app.state.run_sync(collect_cuda_version)

        # 容器信息
        snapshot = await app.state.run_sync(app.state.backend_driver.snapshot)
        container_name = snapshot.get("name", "")
        container_info = {}
        if container_name:
            container_info = await app.state.run_sync(inspect_container, container_name)
            if container_info:
                container_info["uptime"] = format_uptime(container_info.get("started_at", ""))

        # 模型信息
        model_dir = Path(settings.vllm.model_dir)
        model_format = await app.state.run_sync(detect_model_format, model_dir)
        model_config = {}
        if model_format == "huggingface":
            model_config = await app.state.run_sync(parse_model_config, model_dir)

        # 推理参数
        inference_params = {}
        if app.state.backend_type == "vllm":
            inference_params = {
                "gpu_memory_utilization": settings.vllm.gpu_memory_utilization,
                "tensor_parallel_size": settings.vllm.tensor_parallel_size,
                "max_model_len": settings.vllm.max_model_len,
                "max_num_seqs": settings.vllm.max_num_seqs,
                "reasoning_parser": settings.vllm.reasoning_parser,
                "tool_call_parser": settings.vllm.tool_call_parser,
            }
        elif app.state.backend_type == "llama.cpp":
            inference_params = {
                "model_file": settings.vllm.model_file,
                "n_gpu_layers": settings.vllm.n_gpu_layers,
                "ctx_size": settings.vllm.ctx_size,
                "n_parallel": settings.vllm.n_parallel,
            }
        elif app.state.backend_type == "sglang":
            inference_params = {
                "tp_size": settings.vllm.tensor_parallel_size,
                "mem_fraction_static": settings.vllm.mem_fraction_static,
                "max_running_requests": settings.vllm.max_running_requests,
                "reasoning_parser": settings.vllm.reasoning_parser,
            }

        return {
            "backend_type": app.state.backend_type,
            "readiness_state": app.state.agent.status,
            "http_ready": app.state.agent.http_ready,
            "inference_ready": app.state.agent.inference_ready,
            "retry_after_seconds": app.state.agent.retry_after_seconds,
            "last_transition_at": app.state.agent.last_transition_at,
            "last_probe_error": app.state.agent.last_probe_error,
            "last_probe_latency_ms": app.state.agent.last_probe_latency_ms,
            "gpu": {
                "gpus": gpus,
                "cuda_version": cuda_version,
            },
            "container": {
                "info": container_info,
                "snapshot": snapshot,
            },
            "model": {
                "model_dir": str(model_dir),
                "model_name": settings.vllm.model_name,
                "model_format": model_format,
                "model_config": model_config,
            },
            "inference_params": inference_params,
        }

    return app
