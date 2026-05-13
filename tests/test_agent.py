import asyncio
import warnings
from datetime import datetime, timedelta, timezone

import httpx

from llmnode.agent.service import create_agent_app
from llmnode.agent.state import AgentState
from llmnode.storage.db import write_request_metric


def test_state_machine_has_ready_state():
    state = AgentState()
    assert state.status == "stopped"


def test_agent_exposes_state():
    async def run():
        app = create_agent_app(enable_monitor=False)

        async def fake_health(_):
            return True

        app.state.backend_driver.health = fake_health
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/state")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["status"] == "ready"
            assert payload["backend_ready"] is True
            assert "checked_at" in payload
            assert "failure_count" in payload

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
            r2 = await client.post("/manage/stop")
            assert r1.status_code == 200
            assert r2.status_code == 200
            assert calls[0] == "start"
            assert calls[1] == "stop"

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
            assert payload["last_error"] == "waiting for backend warmup"
            assert restart_calls == []

    asyncio.run(run())


def test_agent_recovers_after_startup_grace_expires():
    async def run():
        app = create_agent_app(enable_monitor=False)
        app.state.agent.status = "starting"
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
            assert payload["last_error"] == "recovery restart issued"
            assert restart_calls == ["stop", "start"]

    asyncio.run(run())


def test_agent_metrics_endpoint_returns_aggregated_metrics():
    async def run():
        app = create_agent_app(enable_monitor=False)
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

    asyncio.run(run())
