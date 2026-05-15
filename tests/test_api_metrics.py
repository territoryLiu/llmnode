import asyncio
import json

import httpx

from llmnode.api.app import create_app
from llmnode.proxy.vllm_client import VLLMClient
from llmnode.security import hash_api_key
from llmnode.storage.db import aggregate_request_metrics, create_api_key


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


TEST_MODEL = "qwen36-27b-fp8"


def seed_admin_key(app, secret: str = "sk-admin-test") -> str:
    create_api_key(
        app.state.db,
        name=f"admin-{secret}",
        key_hash=hash_api_key(secret),
        scopes=["admin"],
    )
    return secret


def test_chat_completions_write_metrics_for_success():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = UsageFakeClient()
        admin_secret = seed_admin_key(app)
        admin_row = create_api_key(
            app.state.db,
            name="inference-success-key",
            key_hash=hash_api_key("sk-success-metrics"),
            scopes=["inference"],
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer sk-success-metrics"},
                json={
                    "model": TEST_MODEL,
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
            row = app.state.db.execute(
                """
                SELECT backend_type, api_key_id, cache_creation_tokens, cache_read_tokens, cache_miss_tokens
                FROM request_metrics
                """
            ).fetchone()
            assert row == ("vllm", admin_row["id"], None, None, None)

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
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "model": TEST_MODEL,
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
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "model": TEST_MODEL,
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


def test_admin_usage_overview_and_key_usage_endpoints():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = UsageFakeClient()
        admin_secret = seed_admin_key(app)
        created = create_api_key(
            app.state.db,
            name="custom-inference-key",
            key_hash=hash_api_key("sk-test-usage-key"),
            scopes=["inference"],
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer sk-test-usage-key"},
                json={
                    "model": TEST_MODEL,
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            assert resp.status_code == 200

            overview = await client.get("/admin/overview/usage", headers={"Authorization": f"Bearer {admin_secret}"})
            assert overview.status_code == 200
            payload = overview.json()
            assert "summary" in payload
            assert "trend" in payload
            assert "breakdown" in payload
            assert "chart" in payload
            assert payload["summary"]["request_count"] == 1
            assert payload["breakdown"]["api_keys"][0]["group"] == created["id"]
            assert payload["chart"]["window"] == "12h"
            assert payload["chart"]["group_by"] == "backend_type"

            key_usage = await client.get(
                f"/admin/keys/{created['id']}/usage",
                headers={"Authorization": f"Bearer {admin_secret}"},
            )
            assert key_usage.status_code == 200
            assert key_usage.json()["summary"]["api_key_id"] == created["id"]
            assert key_usage.json()["summary"]["request_count"] == 1

            by_device = await client.get(
                "/admin/overview/usage?window=day&group_by=device_type",
                headers={"Authorization": f"Bearer {admin_secret}"},
            )
            assert by_device.status_code == 200
            assert by_device.json()["chart"]["group_by"] == "device_type"

    asyncio.run(run())


class StreamingUsageFakeClient(VLLMClient):
    def __init__(self):
        super().__init__(base_url="http://fake")

    async def health(self) -> bool:
        return True

    async def stream_bytes(self, path, payload):
        assert path == "/v1/chat/completions"
        chunks = [
            b'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":"he"}}]}\n\n',
            (
                'data: '
                + json.dumps(
                    {
                        "id": "chatcmpl-1",
                        "choices": [{"delta": {}, "finish_reason": "stop"}],
                        "usage": {
                            "prompt_tokens": 4,
                            "completion_tokens": 6,
                            "total_tokens": 10,
                            "cache": {
                                "creation_tokens": 2,
                                "read_tokens": 3,
                                "miss_tokens": 1,
                            },
                        },
                    }
                )
                + "\n\n"
            ).encode(),
            b"data: [DONE]\n\n",
        ]
        for chunk in chunks:
            yield chunk


class NativeResponsesUsageClient:
    backend_type = "external"

    async def health(self) -> bool:
        return True

    async def post_json(self, path, payload):
        raise AssertionError("native responses path should not use backend_client.post_json")

    async def stream_bytes(self, path, payload):
        raise AssertionError("native responses sync path should not use backend_client.stream_bytes")


def test_streaming_chat_records_metrics_on_completion():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = StreamingUsageFakeClient()
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with client.stream(
                "POST",
                    "/v1/chat/completions",
                    headers={"Authorization": f"Bearer {admin_secret}"},
                    json={
                    "model": TEST_MODEL,
                        "messages": [{"role": "user", "content": "hello"}],
                        "max_tokens": 16,
                        "stream": True,
                },
            ) as resp:
                assert resp.status_code == 200
                body = b""
                async for chunk in resp.aiter_bytes():
                    body += chunk
                assert b"data: [DONE]" in body

            metrics = aggregate_request_metrics(app.state.db)
            assert metrics["request_count"] == 1
            assert metrics["success_count"] == 1
            assert metrics["total_tokens"] == 10
            assert metrics["cache_read_tokens"] == 3

    asyncio.run(run())


def test_native_responses_sync_records_metrics_on_completion():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = NativeResponsesUsageClient()

        async def fake_post_json_to(base_url, path, payload, headers=None):
            assert path == "/v1/responses"
            return {
                "id": "resp_native_metrics_1",
                "object": "response",
                "status": "completed",
                "model": payload["model"],
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "ok"}],
                    }
                ],
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 7,
                    "total_tokens": 19,
                },
            }

        app.state.post_json_to = fake_post_json_to
        app.state.ctx.models = {
            "gpt-4o": __import__("llmnode.models", fromlist=["ModelRoute", "ModelCapabilities"]).ModelRoute(
                name="gpt-4o",
                display_name="GPT-4o",
                backend_model=None,
                backend_type=None,
                enabled=True,
                lifecycle_mode="external",
                upstream_protocol="responses",
                upstream_base_url="https://api.openai.com/v1",
                upstream_model="gpt-4o",
                upstream_auth_kind="bearer",
                upstream_auth_ref="openai-prod",
                capabilities=__import__("llmnode.models", fromlist=["ModelCapabilities"]).ModelCapabilities(
                    supports_responses=True,
                    supports_chat=True,
                    supports_messages=False,
                    supports_stream=True,
                    supports_function_tools=True,
                    supports_builtin_tools=True,
                    supports_previous_response_id_native=True,
                    supports_json_schema=True,
                ),
            )
        }
        create_api_key(
            app.state.db,
            name="native-responses-metrics",
            key_hash=hash_api_key("sk-native-resp-metrics"),
            scopes=["inference"],
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/responses",
                headers={"Authorization": "Bearer sk-native-resp-metrics"},
                json={"model": "gpt-4o", "input": "hello"},
            )
            assert resp.status_code == 200

        metrics = aggregate_request_metrics(app.state.db)
        assert metrics["request_count"] == 1
        assert metrics["success_count"] == 1
        assert metrics["total_tokens"] == 19
        row = app.state.db.execute(
            "SELECT protocol, status, backend_type FROM request_metrics"
        ).fetchone()
        assert row == ("responses", "ok", "external")

    asyncio.run(run())
