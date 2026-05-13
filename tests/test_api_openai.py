import asyncio

import httpx

from llmnode.api.app import create_app
from llmnode.proxy.vllm_client import VLLMClient


class FakeClient(VLLMClient):
    def __init__(self):
        super().__init__(base_url="http://fake")

    async def health(self) -> bool:
        return True

    async def post_json(self, path, payload):
        return {"path": path, "model": payload["model"]}


def test_models_endpoint_returns_catalog():
    async def run():
        app = create_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/v1/models", headers={"Authorization": "Bearer dev-key"})
            assert resp.status_code == 200
            ids = [item["id"] for item in resp.json()["data"]]
            assert ids == ["qwen36-35b-a3b-fp8"]

    asyncio.run(run())


def test_admin_status_includes_agent_state():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()

        async def fake_agent_state():
            return {"status": "ready", "backend_ready": True}

        app.state.fetch_agent_state = fake_agent_state
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/admin/status", headers={"Authorization": "Bearer dev-key"})
            assert resp.status_code == 200
            assert resp.json()["agent_state"]["status"] == "ready"
            assert resp.json()["backend_type"] == "vllm"

    asyncio.run(run())


def test_admin_status_includes_runtime_config():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()

        async def fake_agent_state():
            return {"status": "ready", "backend_ready": True}

        app.state.fetch_agent_state = fake_agent_state
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/admin/status", headers={"Authorization": "Bearer dev-key"})
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["runtime"]["schedule"]["timezone"] == "Asia/Shanghai"
            assert payload["runtime"]["backend"]["backend_type"] == "vllm"

    asyncio.run(run())


def test_chat_completions_passes_through_real_model_name():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer dev-key"},
                json={
                    "model": "qwen36-35b-a3b-fp8",
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            assert resp.status_code == 200
            assert resp.json()["model"] == "qwen36-35b-a3b-fp8"

    asyncio.run(run())


def test_chat_completions_rejects_when_agent_not_ready():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        app.state.require_agent_ready = True

        async def fake_agent_state():
            return {"status": "recovering", "backend_ready": False}

        app.state.fetch_agent_state = fake_agent_state
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer dev-key"},
                json={
                    "model": "qwen36-35b-a3b-fp8",
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            assert resp.status_code == 503
            assert "agent not ready" in resp.json()["detail"]

    asyncio.run(run())


def test_admin_request_logs_endpoint_exists():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer dev-key"},
                json={
                    "model": "qwen36-35b-a3b-fp8",
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            resp = await client.get("/admin/request-logs", headers={"Authorization": "Bearer dev-key"})
            assert resp.status_code == 200
            payload = resp.json()
            assert "logs" in payload
            assert isinstance(payload["logs"], list)
            assert len(payload["logs"]) >= 1

    asyncio.run(run())


def test_admin_models_can_be_updated():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/admin/models", headers={"Authorization": "Bearer dev-key"})
            assert resp.status_code == 200
            original = resp.json()["models"][0]

            patch = await client.patch(
                f"/admin/models/{original['name']}",
                headers={"Authorization": "Bearer dev-key"},
                json={"display_name": "Updated Name", "enabled": False},
            )
            assert patch.status_code == 200
            assert patch.json()["model"]["display_name"] == "Updated Name"
            assert patch.json()["model"]["enabled"] is False

            resp2 = await client.get("/admin/models", headers={"Authorization": "Bearer dev-key"})
            models = resp2.json()["models"]
            updated = next(item for item in models if item["name"] == original["name"])
            assert updated["display_name"] == "Updated Name"
            assert updated["enabled"] is False

    asyncio.run(run())


def test_admin_schedule_can_be_updated():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/admin/schedule", headers={"Authorization": "Bearer dev-key"})
            assert resp.status_code == 200
            assert resp.json()["schedule"]["timezone"] == "Asia/Shanghai"

            patch = await client.patch(
                "/admin/schedule",
                headers={"Authorization": "Bearer dev-key"},
                json={"timezone": "UTC", "start_time": "10:00"},
            )
            assert patch.status_code == 200
            assert patch.json()["schedule"]["timezone"] == "UTC"
            assert patch.json()["schedule"]["start_time"] == "10:00"

            resp2 = await client.get("/admin/schedule", headers={"Authorization": "Bearer dev-key"})
            assert resp2.json()["schedule"]["timezone"] == "UTC"

    asyncio.run(run())
