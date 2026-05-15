import asyncio
import json

import httpx

from llmnode.api.app import create_app
from llmnode.proxy.vllm_client import VLLMClient
from llmnode.security import hash_api_key
from llmnode.storage.db import create_api_key


TEST_MODEL = "qwen36-27b-fp8"


def seed_inference_key(app, secret: str = "sk-responses-test") -> str:
    create_api_key(
        app.state.db,
        name=f"inference-{secret}",
        key_hash=hash_api_key(secret),
        scopes=["inference"],
    )
    return secret


class ResponsesSyncFakeClient(VLLMClient):
    def __init__(self):
        super().__init__(base_url="http://fake")
        self.calls: list[tuple[str, dict]] = []

    async def health(self) -> bool:
        return True

    async def post_json(self, path, payload):
        self.calls.append((path, payload))
        assert path == "/v1/chat/completions"
        return {
            "id": "chatcmpl_resp_sync",
            "object": "chat.completion",
            "model": payload["model"],
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "hello from responses",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 7,
                "total_tokens": 12,
            },
        }


class ResponsesToolFakeClient(VLLMClient):
    def __init__(self):
        super().__init__(base_url="http://fake")

    async def health(self) -> bool:
        return True

    async def post_json(self, path, payload):
        return {
            "id": "chatcmpl_resp_tool",
            "object": "chat.completion",
            "model": payload["model"],
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "run_code",
                                    "arguments": "{\"code\":\"print(1)\"}",
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {
                "prompt_tokens": 9,
                "completion_tokens": 4,
                "total_tokens": 13,
            },
        }


class ResponsesStreamingFakeClient(VLLMClient):
    def __init__(self):
        super().__init__(base_url="http://fake")

    async def health(self) -> bool:
        return True

    async def stream_bytes(self, path, payload):
        assert path == "/v1/chat/completions"
        chunks = [
            b'data: {"id":"chatcmpl_resp_stream","choices":[{"delta":{"content":"Hel"}}]}\n\n',
            b'data: {"id":"chatcmpl_resp_stream","choices":[{"delta":{"content":"lo"}}]}\n\n',
            (
                "data: "
                + json.dumps(
                    {
                        "id": "chatcmpl_resp_stream",
                        "choices": [{"delta": {}, "finish_reason": "stop"}],
                        "usage": {
                            "prompt_tokens": 3,
                            "completion_tokens": 5,
                            "total_tokens": 8,
                        },
                    }
                )
                + "\n\n"
            ).encode(),
            b"data: [DONE]\n\n",
        ]
        for chunk in chunks:
            yield chunk


def test_responses_sync_request_is_adapted_from_input():
    async def run():
        app = create_app()
        backend = ResponsesSyncFakeClient()
        app.state.ctx.backend_client = backend
        secret = seed_inference_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/responses",
                headers={"Authorization": f"Bearer {secret}"},
                json={
                    "model": TEST_MODEL,
                    "input": "hello gateway",
                    "max_output_tokens": 32,
                },
            )
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["object"] == "response"
            assert payload["status"] == "completed"
            assert payload["output"][0]["type"] == "message"
            assert payload["output"][0]["content"][0]["text"] == "hello from responses"
            assert payload["usage"]["input_tokens"] == 5
            assert payload["usage"]["output_tokens"] == 7
            path, forwarded = backend.calls[0]
            assert path == "/v1/chat/completions"
            assert forwarded["messages"] == [{"role": "user", "content": "hello gateway"}]
            assert forwarded["max_tokens"] == 32

    asyncio.run(run())


def test_responses_previous_response_id_replays_prior_context():
    async def run():
        app = create_app()
        backend = ResponsesSyncFakeClient()
        app.state.ctx.backend_client = backend
        secret = seed_inference_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            first = await client.post(
                "/v1/responses",
                headers={"Authorization": f"Bearer {secret}"},
                json={"model": TEST_MODEL, "input": "first turn"},
            )
            assert first.status_code == 200
            previous_response_id = first.json()["id"]

            second = await client.post(
                "/v1/responses",
                headers={"Authorization": f"Bearer {secret}"},
                json={
                    "model": TEST_MODEL,
                    "previous_response_id": previous_response_id,
                    "input": "second turn",
                },
            )
            assert second.status_code == 200
            _, forwarded = backend.calls[-1]
            assert forwarded["messages"] == [
                {"role": "user", "content": "first turn"},
                {"role": "assistant", "content": "hello from responses"},
                {"role": "user", "content": "second turn"},
            ]

    asyncio.run(run())


def test_chat_route_previous_response_id_replays_local_messages_not_upstream_id():
    async def run():
        app = create_app()
        backend = ResponsesSyncFakeClient()
        app.state.ctx.backend_client = backend
        secret = seed_inference_key(app, "sk-responses-local-replay")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            first = await client.post(
                "/v1/responses",
                headers={"Authorization": f"Bearer {secret}"},
                json={"model": TEST_MODEL, "input": "first turn"},
            )
            assert first.status_code == 200
            previous_response_id = first.json()["id"]

            second = await client.post(
                "/v1/responses",
                headers={"Authorization": f"Bearer {secret}"},
                json={
                    "model": TEST_MODEL,
                    "previous_response_id": previous_response_id,
                    "input": "second turn",
                },
            )
            assert second.status_code == 200
            _, forwarded = backend.calls[-1]
            assert "previous_response_id" not in forwarded
            assert forwarded["messages"] == [
                {"role": "user", "content": "first turn"},
                {"role": "assistant", "content": "hello from responses"},
                {"role": "user", "content": "second turn"},
            ]

    asyncio.run(run())


def test_responses_maps_tool_calls_into_output_items():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = ResponsesToolFakeClient()
        secret = seed_inference_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/responses",
                headers={"Authorization": f"Bearer {secret}"},
                json={
                    "model": TEST_MODEL,
                    "input": "call a function",
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "run_code",
                                "parameters": {"type": "object"},
                            },
                        }
                    ],
                },
            )
            assert resp.status_code == 200
            payload = resp.json()
            function_call = next(item for item in payload["output"] if item["type"] == "function_call")
            assert function_call["call_id"] == "call_1"
            assert function_call["name"] == "run_code"
            assert function_call["arguments"] == "{\"code\":\"print(1)\"}"

    asyncio.run(run())


def test_responses_stream_emits_event_style_sse():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = ResponsesStreamingFakeClient()
        secret = seed_inference_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with client.stream(
                "POST",
                "/v1/responses",
                headers={"Authorization": f"Bearer {secret}"},
                json={
                    "model": TEST_MODEL,
                    "input": "stream please",
                    "stream": True,
                },
            ) as resp:
                assert resp.status_code == 200
                body = ""
                async for chunk in resp.aiter_text():
                    body += chunk
                assert "event: response.created" in body
                assert "event: response.output_text.delta" in body
                assert "event: response.completed" in body
                assert '"delta":"Hel"' in body
                assert '"delta":"lo"' in body

    asyncio.run(run())


def test_responses_request_logs_and_metrics_use_protocol_responses():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = ResponsesSyncFakeClient()
        secret = seed_inference_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/responses",
                headers={"Authorization": f"Bearer {secret}"},
                json={"model": TEST_MODEL, "input": "metrics"},
            )
            assert resp.status_code == 200

        log_row = app.state.db.execute(
            "SELECT protocol, status FROM request_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        metric_row = app.state.db.execute(
            "SELECT protocol, status FROM request_metrics ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        assert log_row == ("responses", "ok")
        assert metric_row == ("responses", "ok")

    asyncio.run(run())


def test_responses_rejects_when_agent_not_ready():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = ResponsesSyncFakeClient()
        app.state.require_agent_ready = True
        secret = seed_inference_key(app)

        async def fake_agent_state():
            return {"status": "recovering", "backend_ready": False}

        app.state.fetch_agent_state = fake_agent_state
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/responses",
                headers={"Authorization": f"Bearer {secret}"},
                json={"model": TEST_MODEL, "input": "hello"},
            )
            assert resp.status_code == 503
            assert resp.json()["detail"] == "agent_not_ready"

    asyncio.run(run())
