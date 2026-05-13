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
        return {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": payload["model"]}],
        }


def test_anthropic_messages_endpoint_exists():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/messages",
                headers={"Authorization": "Bearer dev-key"},
                json={
                    "model": "qwen36-35b-a3b-fp8",
                    "max_tokens": 16,
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
            assert resp.status_code == 200
            assert resp.json()["content"][0]["text"] == "qwen36-35b-a3b-fp8"

    asyncio.run(run())
