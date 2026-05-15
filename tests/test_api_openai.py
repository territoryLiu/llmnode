import asyncio
from unittest.mock import patch

import httpx

from llmnode.api.app import create_app
from llmnode.config import load_settings
from llmnode.proxy.backend import VLLMBackendClient
from llmnode.proxy.vllm_client import VLLMClient
from llmnode.security import hash_api_key
from llmnode.storage.db import create_api_key


class FakeClient(VLLMClient):
    def __init__(self):
        super().__init__(base_url="http://fake")

    async def health(self) -> bool:
        return True

    async def post_json(self, path, payload):
        return {"path": path, "model": payload["model"]}


EXPECTED_MODEL_NAME = load_settings().vllm.model_name


def seed_admin_key(app, secret: str = "sk-admin-test") -> str:
    create_api_key(
        app.state.db,
        name=f"admin-{secret}",
        key_hash=hash_api_key(secret),
        scopes=["admin"],
    )
    return secret


def test_models_endpoint_returns_catalog():
    async def run():
        app = create_app()
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/v1/models", headers={"Authorization": f"Bearer {admin_secret}"})
            assert resp.status_code == 200
            ids = [item["id"] for item in resp.json()["data"]]
            assert ids == [EXPECTED_MODEL_NAME]

    asyncio.run(run())


def test_admin_status_includes_agent_state():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        admin_secret = seed_admin_key(app)

        async def fake_agent_state():
            return {
                "status": "ready",
                "backend_ready": True,
                "http_ready": True,
                "inference_ready": True,
                "retry_after_seconds": None,
            }

        app.state.fetch_agent_state = fake_agent_state
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/admin/status", headers={"Authorization": f"Bearer {admin_secret}"})
            assert resp.status_code == 200
            assert resp.json()["agent_state"]["status"] == "ready"
            assert resp.json()["agent_state"]["http_ready"] is True
            assert resp.json()["backend_type"] == "vllm"

    asyncio.run(run())


def test_admin_status_includes_runtime_config():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        admin_secret = seed_admin_key(app)

        async def fake_agent_state():
            return {
                "status": "ready",
                "backend_ready": True,
                "http_ready": True,
                "inference_ready": True,
                "retry_after_seconds": None,
            }

        app.state.fetch_agent_state = fake_agent_state
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/admin/status", headers={"Authorization": f"Bearer {admin_secret}"})
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["runtime"]["schedule"]["timezone"] == "Asia/Shanghai"
            assert payload["runtime"]["backend"]["backend_type"] == "vllm"

    asyncio.run(run())


def test_chat_completions_passes_through_real_model_name():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "model": EXPECTED_MODEL_NAME,
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            assert resp.status_code == 200
            assert resp.json()["model"] == EXPECTED_MODEL_NAME

    asyncio.run(run())


def test_chat_completions_rejects_when_agent_not_ready():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        app.state.require_agent_ready = True
        admin_secret = seed_admin_key(app)

        async def fake_agent_state():
            return {"status": "recovering", "backend_ready": False}

        app.state.fetch_agent_state = fake_agent_state
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "model": EXPECTED_MODEL_NAME,
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            assert resp.status_code == 503
            assert resp.json()["detail"] == "agent_not_ready"

    asyncio.run(run())


def test_chat_completions_returns_503_with_retry_after_when_warming_up():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        app.state.require_agent_ready = True
        admin_secret = seed_admin_key(app)

        async def fake_agent_state():
            return {
                "status": "warming_up",
                "http_ready": True,
                "inference_ready": False,
                "retry_after_seconds": 5,
            }

        app.state.fetch_agent_state = fake_agent_state
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "model": EXPECTED_MODEL_NAME,
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            assert resp.status_code == 503
            assert resp.headers["retry-after"] == "5"
            assert resp.json()["detail"] == "backend_warming_up"

    asyncio.run(run())


def test_admin_request_logs_endpoint_exists():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            await client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "model": EXPECTED_MODEL_NAME,
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            resp = await client.get("/admin/request-logs", headers={"Authorization": f"Bearer {admin_secret}"})
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
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/admin/models", headers={"Authorization": f"Bearer {admin_secret}"})
            assert resp.status_code == 200
            original = resp.json()["models"][0]

            patch = await client.patch(
                f"/admin/models/{original['name']}",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={"display_name": "Updated Name", "enabled": False},
            )
            assert patch.status_code == 200
            assert patch.json()["model"]["display_name"] == "Updated Name"
            assert patch.json()["model"]["enabled"] is False

            resp2 = await client.get("/admin/models", headers={"Authorization": f"Bearer {admin_secret}"})
            models = resp2.json()["models"]
            updated = next(item for item in models if item["name"] == original["name"])
            assert updated["display_name"] == "Updated Name"
            assert updated["enabled"] is False

    asyncio.run(run())


def test_admin_schedule_can_be_updated():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/admin/schedule", headers={"Authorization": f"Bearer {admin_secret}"})
            assert resp.status_code == 200
            assert resp.json()["schedule"]["timezone"] == "Asia/Shanghai"

            patch = await client.patch(
                "/admin/schedule",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={"timezone": "UTC", "start_time": "10:00"},
            )
            assert patch.status_code == 200
            assert patch.json()["schedule"]["timezone"] == "UTC"
            assert patch.json()["schedule"]["start_time"] == "10:00"

            resp2 = await client.get("/admin/schedule", headers={"Authorization": f"Bearer {admin_secret}"})
            assert resp2.json()["schedule"]["timezone"] == "UTC"

    asyncio.run(run())


def test_backend_client_uses_configured_request_timeout():
    captured = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs["timeout"]
            captured["base_url"] = kwargs["base_url"]

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, path, json):
            class Response:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"ok": True}

            return Response()

    async def run():
        client = VLLMBackendClient(base_url="http://fake", request_timeout_seconds=300)
        with patch("llmnode.proxy.backend.httpx.AsyncClient", FakeAsyncClient):
            await client.post_json("/v1/chat/completions", {"model": "demo"})

    asyncio.run(run())
    assert captured["timeout"] == 300
