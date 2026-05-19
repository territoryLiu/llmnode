import asyncio
import sqlite3
import warnings
from datetime import datetime, timedelta, timezone

import httpx

from llmnode.agent.service import create_agent_app
from llmnode.agent.state import AgentState
from llmnode.storage.db import list_agent_events, write_request_metric


def test_state_machine_has_ready_state():
    state = AgentState()
    assert state.status == "stopped"


def test_agent_state_exposes_readiness_flags():
    state = AgentState()
    assert state.status == "stopped"
    assert state.http_ready is False
    assert state.inference_ready is False
    assert state.retry_after_seconds is None
    assert state.last_transition_at == ""
    assert state.last_probe_error == ""
    assert state.last_probe_latency_ms is None


def test_agent_exposes_state():
    async def run():
        app = create_agent_app(enable_monitor=False)

        async def fake_health(_):
            return True

        async def fake_probe(_, model_name):
            return {"ok": True, "latency_ms": 12.5}

        app.state.backend_driver.health = fake_health
        app.state.backend_driver.probe = fake_probe
        app.state.warming_up_retry_after = 5
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/state")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["status"] == "ready"
            assert payload["backend_ready"] is True
            assert payload["http_ready"] is True
            assert payload["inference_ready"] is True
            assert "checked_at" in payload
            assert "failure_count" in payload

    asyncio.run(run())


def test_agent_warming_up_when_http_ready_but_probe_fails():
    async def run():
        app = create_agent_app(enable_monitor=False)

        async def fake_health(_):
            return True

        async def fake_probe(*_args, **_kwargs):
            raise RuntimeError("stream not ready")

        app.state.backend_driver.health = fake_health
        app.state.backend_driver.probe = fake_probe
        app.state.warming_up_retry_after = 5
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/state")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["status"] == "warming_up"
            assert payload["http_ready"] is True
            assert payload["inference_ready"] is False
            assert payload["retry_after_seconds"] == 5

    asyncio.run(run())


def test_agent_warming_up_event_records_stream_not_ready_metadata():
    async def run():
        app = create_agent_app(enable_monitor=False)

        async def fake_health(_):
            return True

        async def fake_probe(*_args, **_kwargs):
            raise RuntimeError("stream not ready")

        app.state.backend_driver.health = fake_health
        app.state.backend_driver.probe = fake_probe
        app.state.warming_up_retry_after = 5
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/state")
            assert resp.status_code == 200
            events = list_agent_events(app.state.db, limit=5)
            assert events
            latest = events[0]
            assert latest["status"] == "warming_up"
            assert latest["event_type"] == "stream_not_ready"
            assert latest["readiness_state"] == "warming_up"
            assert latest["http_ready"] is True
            assert latest["inference_ready"] is False
            assert latest["metadata"]["last_probe_error"] == "stream not ready"
            assert latest["metadata"]["retry_after_seconds"] == 5

    asyncio.run(run())


def test_agent_ready_after_warming_up_records_backend_recovered_event():
    async def run():
        app = create_agent_app(enable_monitor=False)
        probe_attempts = {"count": 0}

        async def fake_health(_):
            return True

        async def fake_probe(*_args, **_kwargs):
            probe_attempts["count"] += 1
            if probe_attempts["count"] == 1:
                raise RuntimeError("stream not ready")
            return {"ok": True, "latency_ms": 12.5}

        app.state.backend_driver.health = fake_health
        app.state.backend_driver.probe = fake_probe
        app.state.warming_up_retry_after = 5
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            first = await client.get("/state")
            assert first.status_code == 200
            assert first.json()["status"] == "warming_up"

            second = await client.get("/state")
            assert second.status_code == 200
            payload = second.json()
            assert payload["status"] == "ready"
            assert payload["inference_ready"] is True

            events = list_agent_events(app.state.db, limit=5)
            assert len(events) >= 2
            assert events[0]["status"] == "ready"
            assert events[0]["event_type"] == "backend_recovered"
            assert events[0]["readiness_state"] == "ready"
            assert events[0]["http_ready"] is True
            assert events[0]["inference_ready"] is True
            assert "last_probe_latency_ms" in events[0]["metadata"]
            assert events[1]["event_type"] == "stream_not_ready"

    asyncio.run(run())


def test_agent_events_endpoint_returns_list():
    async def run():
        app = create_agent_app(enable_monitor=False)

        async def fake_health(_):
            return True

        app.state.backend_driver.health = fake_health
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            await client.get("/state")
            resp = await client.get("/events")
            assert resp.status_code == 200
            payload = resp.json()
            assert "events" in payload
            assert isinstance(payload["events"], list)

    asyncio.run(run())


def test_agent_manage_start_stop_use_docker_controls():
    async def run():
        app = create_agent_app(enable_monitor=False)

        async def fake_health(_):
            return True

        calls = []

        def fake_start():
            calls.append("start")

        def fake_stop():
            calls.append("stop")

        async def run_sync(func):
            return func()

        app.state.backend_driver.start = fake_start
        app.state.backend_driver.stop = fake_stop
        app.state.backend_driver.health = fake_health
        app.state.run_sync = run_sync

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            r1 = await client.post("/manage/start")
            await asyncio.sleep(0)
            r2 = await client.post("/manage/stop")
            assert r1.status_code == 200
            assert r2.status_code == 200
            assert calls[0] == "start"
            assert calls[1] == "stop"

    asyncio.run(run())


def test_agent_manual_stop_blocks_state_triggered_auto_recovery():
    async def run():
        app = create_agent_app(enable_monitor=False)
        app.state.agent.failure_count = app.state.recovery_threshold

        async def fake_health(_):
            return False

        restart_calls = []

        def fake_stop():
            restart_calls.append("stop")

        def fake_start():
            restart_calls.append("start")

        async def run_sync(func):
            return func()

        app.state.backend_driver.health = fake_health
        app.state.backend_driver.stop = fake_stop
        app.state.backend_driver.start = fake_start
        app.state.run_sync = run_sync

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            stop_resp = await client.post("/manage/stop")
            assert stop_resp.status_code == 200

            state_resp = await client.get("/state")
            assert state_resp.status_code == 200
            payload = state_resp.json()
            assert payload["status"] == "stopped"
            assert payload["desired_state"] == "stopped"
            assert restart_calls == ["stop"]

    asyncio.run(run())


def test_agent_manual_start_restores_auto_recovery_target():
    async def run():
        app = create_agent_app(enable_monitor=False)
        app.state.agent.status = "stopped"
        app.state.agent.desired_state = "stopped"

        async def fake_health(_):
            return False

        def fake_snapshot():
            return {"exists": False, "status": "missing"}

        restart_calls = []

        def fake_stop():
            restart_calls.append("stop")

        def fake_start():
            restart_calls.append("start")

        async def run_sync(func):
            return func()

        app.state.backend_driver.health = fake_health
        app.state.backend_driver.snapshot = fake_snapshot
        app.state.backend_driver.stop = fake_stop
        app.state.backend_driver.start = fake_start
        app.state.run_sync = run_sync

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            start_resp = await client.post("/manage/start")
            await asyncio.sleep(0)
            assert start_resp.status_code == 200

            app.state.agent.failure_count = app.state.recovery_threshold - 1
            state_resp = await client.get("/state")
            assert state_resp.status_code == 200
            payload = state_resp.json()
            assert payload["desired_state"] == "running"
            assert restart_calls == ["start", "stop", "start"]

    asyncio.run(run())


def test_agent_create_app_emits_no_deprecation_warnings():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        app = create_agent_app(enable_monitor=False)
        transport = httpx.ASGITransport(app=app)

        async def run():
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                await client.get("/health/liveliness")

        asyncio.run(run())

    assert not any(issubclass(item.category, DeprecationWarning) for item in caught)


def test_agent_state_exposes_started_at_after_manual_start():
    async def run():
        app = create_agent_app(enable_monitor=False)

        def fake_start():
            return {"action": "started_existing"}

        async def run_sync(func):
            return func()

        app.state.backend_driver.start = fake_start
        app.state.run_sync = run_sync
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            start_resp = await client.post("/manage/start")
            await asyncio.sleep(0)
            assert start_resp.status_code == 200
            state_resp = await client.get("/state")
            assert state_resp.status_code == 200
            payload = state_resp.json()
            assert payload["started_at"]

    asyncio.run(run())


def test_agent_defers_auto_recovery_during_startup_grace():
    async def run():
        app = create_agent_app(enable_monitor=False)
        app.state.agent.status = "starting"
        app.state.agent.desired_state = "running"
        app.state.agent.started_at = datetime.now(timezone.utc).isoformat()
        app.state.agent.failure_count = app.state.recovery_threshold

        async def fake_health(_):
            return False

        def fake_snapshot():
            return {"exists": True, "status": "running"}

        restart_calls = []

        def fake_stop():
            restart_calls.append("stop")

        def fake_start():
            restart_calls.append("start")

        async def run_sync(func):
            return func()

        app.state.backend_driver.health = fake_health
        app.state.backend_driver.snapshot = fake_snapshot
        app.state.backend_driver.stop = fake_stop
        app.state.backend_driver.start = fake_start
        app.state.run_sync = run_sync
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/state")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["status"] == "starting"
            assert payload["last_error"] == "container running, waiting for backend warmup"
            assert restart_calls == []

    asyncio.run(run())


def test_agent_skips_recovery_when_container_running():
    """容器 running 时即使过了 startup_grace_period 也不触发恢复（模型在 warmup）"""
    async def run():
        app = create_agent_app(enable_monitor=False)
        app.state.agent.status = "starting"
        app.state.agent.desired_state = "running"
        app.state.agent.started_at = (datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat()
        app.state.agent.failure_count = app.state.recovery_threshold

        async def fake_health(_):
            return False

        def fake_snapshot():
            return {"exists": True, "status": "running"}

        restart_calls = []

        def fake_stop():
            restart_calls.append("stop")

        def fake_start():
            restart_calls.append("start")

        async def run_sync(func):
            return func()

        app.state.backend_driver.health = fake_health
        app.state.backend_driver.snapshot = fake_snapshot
        app.state.backend_driver.stop = fake_stop
        app.state.backend_driver.start = fake_start
        app.state.run_sync = run_sync
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/state")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["status"] == "starting"
            assert payload["last_error"] == "container running, waiting for backend warmup"
            assert restart_calls == []

    asyncio.run(run())


def test_agent_recovers_when_container_missing_and_grace_expired():
    """容器不存在且超过 grace period 才触发恢复重启"""
    async def run():
        app = create_agent_app(enable_monitor=False)
        app.state.agent.status = "starting"
        app.state.agent.desired_state = "running"
        app.state.agent.started_at = (datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat()
        app.state.agent.failure_count = app.state.recovery_threshold

        async def fake_health(_):
            return False

        def fake_snapshot():
            return {"exists": False, "status": "missing"}

        restart_calls = []

        def fake_stop():
            restart_calls.append("stop")

        def fake_start():
            restart_calls.append("start")

        async def run_sync(func):
            return func()

        app.state.backend_driver.health = fake_health
        app.state.backend_driver.snapshot = fake_snapshot
        app.state.backend_driver.stop = fake_stop
        app.state.backend_driver.start = fake_start
        app.state.run_sync = run_sync
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/state")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["status"] == "starting"
            assert payload["last_error"] == "recovery restart issued"
            assert restart_calls == ["stop", "start"]

    asyncio.run(run())


def test_agent_diagnostics_status_includes_readiness_fields():
    async def run():
        app = create_agent_app(enable_monitor=False)

        async def fake_health(_):
            return True

        async def fake_probe(_, model_name):
            return {"ok": True, "latency_ms": 12.5}

        app.state.backend_driver.health = fake_health
        app.state.backend_driver.probe = fake_probe
        app.state.warming_up_retry_after = 5
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            # Trigger a state refresh first
            await client.get("/state")
            resp = await client.get("/admin/diagnostics/status")
            assert resp.status_code == 200
            payload = resp.json()
            assert "http_ready" in payload
            assert "inference_ready" in payload
            assert "retry_after_seconds" in payload
            assert "readiness_state" in payload
            assert "last_probe_error" in payload
            assert "last_probe_latency_ms" in payload

    asyncio.run(run())


def test_agent_metrics_endpoint_returns_aggregated_metrics():
    async def run():
        app = create_agent_app(enable_monitor=False)
        app.state.db.execute("DELETE FROM request_metrics")
        app.state.db.commit()
        write_request_metric(
            app.state.db,
            request_id="req-1",
            model_name="qwen36-27b",
            protocol="openai",
            status="ok",
            latency_ms=1500.0,
            prompt_tokens=32,
            completion_tokens=64,
            total_tokens=96,
            tokens_per_second=42.6,
            started_at="2026-05-13T10:00:00+00:00",
            finished_at="2026-05-13T10:00:01.500000+00:00",
        )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/admin/diagnostics/metrics")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["queue_length"] == 0
            assert "generated_at" in payload
            assert payload["request_count"] == 1
            assert payload["success_count"] == 1
            assert payload["avg_latency_ms"] == 1500.0

        app.state.db.execute("DELETE FROM request_metrics")
        app.state.db.commit()

    try:
        asyncio.run(run())
    finally:
        with sqlite3.connect("/proj02/liuheshan/llmnode/runtime/data/gateway.db") as conn:
            conn.execute("DELETE FROM request_metrics")
            conn.commit()
