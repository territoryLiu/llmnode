import asyncio
import warnings

import httpx

from llmnode.agent.service import create_agent_app
from llmnode.agent.state import AgentState


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
            calls.append(("start", app.state.vllm_spec.container_name))

        def fake_stop():
            calls.append(("stop", app.state.vllm_spec.container_name))

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
            assert calls[0][0] == "start"
            assert calls[1][0] == "stop"

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
