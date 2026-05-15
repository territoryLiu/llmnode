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


def seed_admin_key(app, secret: str = "sk-admin-test") -> str:
    create_api_key(
        app.state.db,
        name=f"admin-{secret}",
        key_hash=hash_api_key(secret),
        scopes=["admin"],
    )
    return secret


def test_admin_stream_emits_snapshot_event():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        admin_secret = seed_admin_key(app)

        async def fake_agent_state():
            return {"status": "ready", "backend_ready": True}

        app.state.fetch_agent_state = fake_agent_state
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with client.stream(
                "GET",
                "/admin/stream?once=1",
                headers={"Authorization": f"Bearer {admin_secret}"},
            ) as resp:
                assert resp.status_code == 200
                assert "text/event-stream" in resp.headers["content-type"]
                body = await resp.aread()
                text = body.decode("utf-8")
                assert "event: snapshot" in text
                assert '"backend_type": "vllm"' in text

    asyncio.run(run())
