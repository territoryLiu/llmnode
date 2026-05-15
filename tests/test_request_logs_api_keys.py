import asyncio

import httpx

from llmnode.api.app import create_app
from llmnode.config import load_settings
from llmnode.security import hash_api_key
from llmnode.storage.db import create_api_key
from llmnode.proxy.vllm_client import VLLMClient


class FakeClient(VLLMClient):
    def __init__(self):
        super().__init__(base_url="http://fake")

    async def health(self) -> bool:
        return True

    async def post_json(self, path, payload):
        return {"path": path, "model": payload["model"]}


TEST_MODEL = load_settings().vllm.model_name


def seed_admin_key(app, secret: str = "sk-admin-test") -> str:
    create_api_key(
        app.state.db,
        name=f"admin-{secret}",
        key_hash=hash_api_key(secret),
        scopes=["admin"],
    )
    return secret


def test_request_logs_include_db_api_key_identity():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        admin_secret = seed_admin_key(app)
        created = create_api_key(
            app.state.db,
            name="inference-key",
            key_hash=hash_api_key("sk-test-567"),
            scopes=["inference"],
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer sk-test-567"},
                json={
                    "model": TEST_MODEL,
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            logs = await client.get("/admin/request-logs", headers={"Authorization": f"Bearer {admin_secret}"})
            assert logs.status_code == 200
            first = logs.json()["logs"][0]
            assert first["api_key_id"] == created["id"]
            assert first["auth_source"] == "db"

    asyncio.run(run())


def test_request_logs_include_admin_db_key_identity():
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
                    "model": TEST_MODEL,
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            logs = await client.get("/admin/request-logs", headers={"Authorization": f"Bearer {admin_secret}"})
            assert logs.status_code == 200
            first = logs.json()["logs"][0]
            assert first["api_key_id"] is not None
            assert first["auth_source"] == "db"

    asyncio.run(run())


def test_request_logs_include_queue_rejection_reason():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        app.state.request_gate._queue_limit = 0
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            await client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "model": TEST_MODEL,
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            logs = await client.get("/admin/request-logs", headers={"Authorization": f"Bearer {admin_secret}"})
            assert logs.status_code == 200
            first = logs.json()["logs"][0]
            assert first["rejection_reason"] == "queue_full"

    asyncio.run(run())
