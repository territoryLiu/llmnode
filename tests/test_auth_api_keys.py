import asyncio

import httpx

from llmnode.api.app import create_app
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


def test_bootstrap_key_can_access_admin_status():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/admin/status", headers={"Authorization": "Bearer dev-key"})
            assert resp.status_code == 200

    asyncio.run(run())


def test_bootstrap_key_can_access_models():
    async def run():
        app = create_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/v1/models", headers={"Authorization": "Bearer dev-key"})
            assert resp.status_code == 200

    asyncio.run(run())


def test_db_backed_inference_key_can_access_models():
    async def run():
        app = create_app()
        create_api_key(
            app.state.db,
            name="inference-key",
            key_hash=hash_api_key("ln_test_123"),
            scopes=["inference"],
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/v1/models", headers={"Authorization": "Bearer ln_test_123"})
            assert resp.status_code == 200

    asyncio.run(run())


def test_db_inference_key_gets_forbidden_on_admin_status():
    async def run():
        app = create_app()
        create_api_key(
            app.state.db,
            name="inference-key",
            key_hash=hash_api_key("ln_test_234"),
            scopes=["inference"],
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/admin/status", headers={"Authorization": "Bearer ln_test_234"})
            assert resp.status_code == 403

    asyncio.run(run())


def test_disabled_db_key_gets_rejected():
    async def run():
        app = create_app()
        create_api_key(
            app.state.db,
            name="disabled-key",
            key_hash=hash_api_key("ln_test_345"),
            scopes=["inference"],
            status="disabled",
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/v1/models", headers={"Authorization": "Bearer ln_test_345"})
            assert resp.status_code == 401

    asyncio.run(run())
