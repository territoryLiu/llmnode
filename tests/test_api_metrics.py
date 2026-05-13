import asyncio

import httpx

from llmnode.api.app import create_app
from llmnode.proxy.vllm_client import VLLMClient
from llmnode.storage.db import aggregate_request_metrics


class UsageFakeClient(VLLMClient):
    def __init__(self):
        super().__init__(base_url="http://fake")

    async def health(self) -> bool:
        return True

    async def post_json(self, path, payload):
        return {
            "id": "resp_1",
            "object": "chat.completion",
            "model": payload["model"],
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 22,
                "total_tokens": 33,
            },
        }


def test_chat_completions_write_metrics_for_success():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = UsageFakeClient()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer dev-key"},
                json={
                    "model": "claude-sonnet-4-5-20250929",
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            assert resp.status_code == 200
            metrics = aggregate_request_metrics(app.state.db)
            assert metrics["request_count"] == 1
            assert metrics["success_count"] == 1
            assert metrics["tokens_observed_requests"] == 1
            assert metrics["throughput_tokens_per_s"] > 0

    asyncio.run(run())


class NoUsageFakeClient(VLLMClient):
    def __init__(self):
        super().__init__(base_url="http://fake")

    async def health(self) -> bool:
        return True

    async def post_json(self, path, payload):
        return {
            "id": "resp_2",
            "object": "chat.completion",
            "model": payload["model"],
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        }


def test_queue_rejection_writes_metrics_record():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = UsageFakeClient()
        app.state.request_gate._queue_limit = 0
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer dev-key"},
                json={
                    "model": "claude-sonnet-4-5-20250929",
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            assert resp.status_code == 429
            metrics = aggregate_request_metrics(app.state.db)
            assert metrics["request_count"] == 1
            assert metrics["success_count"] == 0
            assert metrics["tokens_observed_requests"] == 0

    asyncio.run(run())


def test_success_without_usage_still_writes_latency_metrics():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = NoUsageFakeClient()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer dev-key"},
                json={
                    "model": "claude-sonnet-4-5-20250929",
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            assert resp.status_code == 200
            metrics = aggregate_request_metrics(app.state.db)
            assert metrics["request_count"] == 1
            assert metrics["success_count"] == 1
            assert metrics["tokens_observed_requests"] == 0
            assert metrics["avg_latency_ms"] > 0

    asyncio.run(run())
