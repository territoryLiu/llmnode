import asyncio
import json
from unittest.mock import patch

import httpx

from llmnode.api.app import create_app
from llmnode.config import load_settings
from llmnode.models import ModelCapabilities, ModelRoute
from llmnode.proxy.vllm_client import VLLMClient
from llmnode.security import hash_api_key
from llmnode.storage.db import create_api_key


TEST_MODEL = load_settings().vllm.model_name


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
        assert path == "/v1/responses"
        return {
            "id": "resp_sync_1",
            "object": "response",
            "status": "completed",
            "model": payload["model"],
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "hello from responses"}],
                }
            ],
            "usage": {"input_tokens": 5, "output_tokens": 7, "total_tokens": 12},
        }


class ResponsesToolFakeClient(VLLMClient):
    def __init__(self):
        super().__init__(base_url="http://fake")

    async def health(self) -> bool:
        return True

    async def post_json(self, path, payload):
        assert path == "/v1/responses"
        return {
            "id": "resp_tool_1",
            "object": "response",
            "status": "completed",
            "model": payload["model"],
            "output": [
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "run_code",
                    "arguments": "{\"code\":\"print(1)\"}",
                }
            ],
            "usage": {"input_tokens": 9, "output_tokens": 4, "total_tokens": 13},
        }


class ResponsesStreamingFakeClient(VLLMClient):
    def __init__(self):
        super().__init__(base_url="http://fake")

    async def health(self) -> bool:
        return True

    async def stream_bytes(self, path, payload):
        assert path == "/v1/responses"
        chunks = [
            b'event: response.created\ndata: {"id":"resp_stream_1","object":"response","status":"in_progress"}\n\n',
            b'event: response.output_text.delta\ndata: {"response_id":"resp_stream_1","delta":"Hel"}\n\n',
            b'event: response.output_text.delta\ndata: {"response_id":"resp_stream_1","delta":"lo"}\n\n',
            (
                "event: response.completed\ndata: "
                + json.dumps(
                    {
                        "id": "resp_stream_1",
                        "object": "response",
                        "status": "completed",
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "Hello"}],
                            }
                        ],
                        "usage": {"input_tokens": 3, "output_tokens": 5, "total_tokens": 8},
                    }
                )
                + "\n\n"
            ).encode(),
        ]
        for chunk in chunks:
            yield chunk


def _responses_messages_route(auth_ref: str = "ANTHROPIC_RESPONSES_KEY") -> ModelRoute:
    class ResponsesMessagesRoute(ModelRoute):
        def runtime_capabilities(self) -> dict[str, object]:
            return {
                "native_protocols": ["messages"],
                "adapter_policies": ["responses->messages"],
                "tool_policies": {
                    "openai_function_tools": True,
                    "anthropic_function_tools": True,
                    "builtin_tools": False,
                },
                "protocol_features": {
                    "stream": True,
                    "count_tokens": True,
                    "json_schema": False,
                    "previous_response_id": False,
                },
            }

    return ResponsesMessagesRoute(
        name=TEST_MODEL,
        display_name="Claude Messages Route",
        backend_model=None,
        backend_type=None,
        enabled=True,
        lifecycle_mode="external",
        upstream_protocol="messages",
        upstream_base_url="https://messages.example.com",
        upstream_model="claude-sonnet-4",
        upstream_auth_kind="x_api_key",
        upstream_auth_ref=auth_ref,
        capabilities=ModelCapabilities(
            supports_responses=False,
            supports_chat=False,
            supports_messages=True,
            supports_stream=True,
            supports_function_tools=True,
            supports_builtin_tools=False,
        ),
        source_kind="manual",
    )


def _external_chat_only_route(auth_ref: str = "OPENAI_CHAT_ONLY_KEY") -> ModelRoute:
    return ModelRoute(
        name=TEST_MODEL,
        display_name="External Chat Only Route",
        backend_model=None,
        backend_type=None,
        enabled=True,
        lifecycle_mode="external",
        upstream_protocol="chat",
        upstream_base_url="https://chat.example.com",
        upstream_model="gpt-4.1-mini",
        upstream_auth_kind="bearer",
        upstream_auth_ref=auth_ref,
        capabilities=ModelCapabilities(
            supports_responses=False,
            supports_chat=True,
            supports_messages=False,
            supports_stream=True,
            supports_function_tools=True,
            supports_builtin_tools=False,
            supports_previous_response_id_native=False,
            supports_json_schema=True,
        ),
        source_kind="manual",
    )


def _external_chat_adapter_route(auth_ref: str = "OPENAI_CHAT_ADAPTER_KEY") -> ModelRoute:
    class ExternalChatAdapterRoute(ModelRoute):
        def runtime_capabilities(self) -> dict[str, object]:
            return {
                "native_protocols": ["chat"],
                "adapter_policies": ["responses->chat"],
                "tool_policies": {
                    "openai_function_tools": True,
                    "anthropic_function_tools": True,
                    "builtin_tools": False,
                },
                "protocol_features": {
                    "stream": True,
                    "count_tokens": False,
                    "json_schema": True,
                    "previous_response_id": False,
                },
            }

    return ExternalChatAdapterRoute(
        name=TEST_MODEL,
        display_name="External Chat Adapter Route",
        backend_model=None,
        backend_type=None,
        enabled=True,
        lifecycle_mode="external",
        upstream_protocol="chat",
        upstream_base_url="https://chat.example.com",
        upstream_model="gpt-4.1-mini",
        upstream_auth_kind="bearer",
        upstream_auth_ref=auth_ref,
        capabilities=ModelCapabilities(
            supports_responses=False,
            supports_chat=True,
            supports_messages=False,
            supports_stream=True,
            supports_function_tools=True,
            supports_builtin_tools=False,
            supports_previous_response_id_native=False,
            supports_json_schema=True,
        ),
        source_kind="manual",
    )


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
            assert path == "/v1/responses"
            assert forwarded["input"] == "hello gateway"
            assert forwarded["max_output_tokens"] == 32

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
            assert forwarded["previous_response_id"] == "resp_sync_1"
            assert forwarded["input"] == "second turn"

    asyncio.run(run())


def test_chat_route_previous_response_id_replays_local_messages_not_upstream_id():
    async def run():
        app = create_app()
        app.state.ctx.models[TEST_MODEL] = _external_chat_adapter_route()
        secret = seed_inference_key(app, "sk-responses-local-replay")
        transport = httpx.ASGITransport(app=app)
        with patch.dict("os.environ", {"OPENAI_CHAT_ADAPTER_KEY": "sk-upstream-chat-adapter"}, clear=False):
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                app.state.db.execute(
                    """
                    INSERT INTO response_states(
                        response_id, request_id, model_name, input_items_json, output_items_json, messages_json,
                        parent_response_id, route_name, client_protocol, upstream_protocol, upstream_response_id,
                        request_json, output_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "resp_local_chat_1",
                        "req_local_chat_1",
                        TEST_MODEL,
                        '[{"role":"user","content":"first turn"}]',
                        '[{"type":"message","role":"assistant","content":[{"type":"output_text","text":"hello from responses"}]}]',
                        '[{"role":"user","content":"first turn"},{"role":"assistant","content":"hello from responses"}]',
                        None,
                        TEST_MODEL,
                        "responses",
                        "chat",
                        None,
                        '{"model":"%s","input":"first turn"}' % TEST_MODEL,
                        '{"id":"resp_local_chat_1"}',
                    ),
                )
                app.state.db.commit()

                calls: list[tuple[str, str, dict, dict | None]] = []

                async def fake_post_json_to(base_url, path, payload, headers=None):
                    calls.append((base_url, path, payload, headers))
                    return {
                        "id": "chat_sync_external_1",
                        "object": "chat.completion",
                        "model": payload["model"],
                        "choices": [
                            {
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": "external chat reply",
                                },
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {"prompt_tokens": 5, "completion_tokens": 4, "total_tokens": 9},
                    }

                app.state.post_json_to = fake_post_json_to
                app.state.ctx.post_json_to = fake_post_json_to

                second = await client.post(
                    "/v1/responses",
                    headers={"Authorization": f"Bearer {secret}"},
                    json={
                        "model": TEST_MODEL,
                        "previous_response_id": "resp_local_chat_1",
                        "input": "second turn",
                    },
                )
                assert second.status_code == 200
                _, path, forwarded, _ = calls[-1]
                assert path == "/v1/chat/completions"
                assert "previous_response_id" not in forwarded
                assert forwarded["messages"] == [
                    {"role": "user", "content": "first turn"},
                    {"role": "assistant", "content": "hello from responses"},
                    {"role": "user", "content": "second turn"},
                ]

    asyncio.run(run())


def test_responses_sync_chat_adapter_persists_response_state_metadata():
    async def run():
        app = create_app()
        app.state.ctx.models[TEST_MODEL] = _external_chat_adapter_route()
        secret = seed_inference_key(app, "sk-responses-chat-state")
        transport = httpx.ASGITransport(app=app)

        async def fake_post_json_to(base_url, path, payload, headers=None):
            return {
                "id": "chat_sync_external_state_1",
                "object": "chat.completion",
                "model": payload["model"],
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "external chat reply",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 4, "total_tokens": 9},
            }

        app.state.post_json_to = fake_post_json_to
        app.state.ctx.post_json_to = fake_post_json_to

        with patch.dict("os.environ", {"OPENAI_CHAT_ADAPTER_KEY": "sk-upstream-chat-adapter"}, clear=False):
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.post(
                    "/v1/responses",
                    headers={"Authorization": f"Bearer {secret}"},
                    json={"model": TEST_MODEL, "input": "hello gateway"},
                )
                assert resp.status_code == 200
                response_id = resp.json()["id"]

        state = app.state.db.execute(
            """
            SELECT route_name, client_protocol, upstream_protocol, parent_response_id, request_json, output_json
            FROM response_states
            WHERE response_id = ?
            """,
            (response_id,),
        ).fetchone()
        assert state is not None
        assert state[0] == TEST_MODEL
        assert state[1] == "responses"
        assert state[2] == "chat"
        assert state[3] is None
        assert json.loads(state[4])["model"] == "gpt-4.1-mini"
        assert json.loads(state[5])["id"] == "chat_sync_external_state_1"

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


def test_chat_route_rejects_builtin_tools():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = ResponsesSyncFakeClient()
        secret = seed_inference_key(app, "sk-responses-builtin-tools")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/responses",
                headers={"Authorization": f"Bearer {secret}"},
                json={
                    "model": TEST_MODEL,
                    "input": "search this",
                    "tools": [{"type": "web_search"}],
                },
            )
            assert resp.status_code == 400
            assert resp.json()["detail"] == "builtin_tools_not_supported"

    asyncio.run(run())


def test_responses_rejects_external_chat_only_route_without_adapter():
    async def run():
        app = create_app()
        app.state.ctx.models[TEST_MODEL] = _external_chat_only_route()
        secret = seed_inference_key(app, "sk-responses-chat-only")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/responses",
                headers={"Authorization": f"Bearer {secret}"},
                json={"model": TEST_MODEL, "input": "hello gateway"},
            )
            assert resp.status_code == 400
            assert resp.json()["detail"] == "adapter_not_enabled_for_route"

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


def test_responses_stream_chat_adapter_persists_response_state_metadata():
    async def run():
        app = create_app()
        app.state.ctx.models[TEST_MODEL] = _external_chat_adapter_route()
        secret = seed_inference_key(app, "sk-responses-chat-stream-state")
        transport = httpx.ASGITransport(app=app)

        async def fake_stream_bytes_from(base_url, path, payload, headers=None):
            yield b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n'
            yield (
                'data: {"choices":[{"delta":{"content":" there"}}],"usage":{"prompt_tokens":2,"completion_tokens":3,"total_tokens":5}}\n\n'
            ).encode()

        app.state.stream_bytes_from = fake_stream_bytes_from
        app.state.ctx.stream_bytes_from = fake_stream_bytes_from

        with patch.dict("os.environ", {"OPENAI_CHAT_ADAPTER_KEY": "sk-upstream-chat-adapter"}, clear=False):
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                async with client.stream(
                    "POST",
                    "/v1/responses",
                    headers={"Authorization": f"Bearer {secret}"},
                    json={"model": TEST_MODEL, "input": "hello stream", "stream": True},
                ) as resp:
                    assert resp.status_code == 200
                    body = ""
                    async for chunk in resp.aiter_text():
                        body += chunk
                    assert "event: response.completed" in body
                    completed_json = body.split("event: response.completed\ndata: ", 1)[1].strip()
                    response_id = json.loads(completed_json)["id"]

        state = app.state.db.execute(
            """
            SELECT route_name, client_protocol, upstream_protocol, parent_response_id, request_json, output_json
            FROM response_states
            WHERE response_id = ?
            """,
            (response_id,),
        ).fetchone()
        assert state is not None
        assert state[0] == TEST_MODEL
        assert state[1] == "responses"
        assert state[2] == "chat"
        assert state[3] is None
        assert json.loads(state[4])["model"] == "gpt-4.1-mini"
        assert json.loads(state[5])["status"] == "completed"

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


def test_responses_sync_can_adapt_to_external_messages_route():
    async def run():
        app = create_app()
        calls: list[tuple[str, str, dict, dict | None]] = []

        async def fake_post_json_to(base_url, path, payload, headers=None):
            calls.append((base_url, path, payload, headers))
            return {
                "id": "msg_resp_sync_1",
                "type": "message",
                "role": "assistant",
                "model": payload["model"],
                "content": [{"type": "text", "text": "hello from messages"}],
                "usage": {"input_tokens": 6, "output_tokens": 4},
            }

        app.state.post_json_to = fake_post_json_to
        app.state.ctx.post_json_to = fake_post_json_to
        app.state.ctx.models[TEST_MODEL] = _responses_messages_route()
        secret = seed_inference_key(app, "sk-responses-messages-sync")
        transport = httpx.ASGITransport(app=app)
        with patch.dict("os.environ", {"ANTHROPIC_RESPONSES_KEY": "sk-upstream-anthropic-responses"}, clear=False):
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.post(
                    "/v1/responses",
                    headers={"Authorization": f"Bearer {secret}"},
                    json={"model": TEST_MODEL, "input": "hello gateway", "max_output_tokens": 32},
                )
                assert resp.status_code == 200
                payload = resp.json()
                assert payload["object"] == "response"
                assert payload["output"][0]["content"][0]["text"] == "hello from messages"
                assert payload["usage"]["input_tokens"] == 6
                assert payload["usage"]["output_tokens"] == 4
                assert calls[0][0] == "https://messages.example.com"
                assert calls[0][1] == "/v1/messages"
                assert calls[0][2]["model"] == "claude-sonnet-4"
                assert calls[0][2]["messages"] == [{"role": "user", "content": "hello gateway"}]
                assert calls[0][2]["max_tokens"] == 32
                assert calls[0][3] == {"x-api-key": "sk-upstream-anthropic-responses"}

    asyncio.run(run())


def test_responses_stream_can_adapt_to_external_messages_route():
    async def run():
        app = create_app()
        calls: list[tuple[str, str, dict, dict | None]] = []

        async def fake_stream_bytes_from(base_url, path, payload, headers=None):
            calls.append((base_url, path, payload, headers))
            chunks = [
                b'event: message_start\ndata: {"type":"message_start","message":{"id":"msg_resp_stream_1"}}\n\n',
                b'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hi"}}\n\n',
                b'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":" there"}}\n\n',
                b'event: message_delta\ndata: {"type":"message_delta","usage":{"input_tokens":2,"output_tokens":3}}\n\n',
            ]
            for chunk in chunks:
                yield chunk

        app.state.stream_bytes_from = fake_stream_bytes_from
        app.state.ctx.stream_bytes_from = fake_stream_bytes_from
        app.state.ctx.models[TEST_MODEL] = _responses_messages_route("ANTHROPIC_RESPONSES_STREAM_KEY")
        secret = seed_inference_key(app, "sk-responses-messages-stream")
        transport = httpx.ASGITransport(app=app)
        with patch.dict("os.environ", {"ANTHROPIC_RESPONSES_STREAM_KEY": "sk-upstream-anthropic-responses-stream"}, clear=False):
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                async with client.stream(
                    "POST",
                    "/v1/responses",
                    headers={"Authorization": f"Bearer {secret}"},
                    json={"model": TEST_MODEL, "input": "stream please", "stream": True},
                ) as resp:
                    assert resp.status_code == 200
                    body = ""
                    async for chunk in resp.aiter_text():
                        body += chunk
                    assert "event: response.created" in body
                    assert "event: response.output_text.delta" in body
                    assert '"delta":"Hi"' in body
                    assert '"delta":" there"' in body
                    assert "event: response.completed" in body
                    completed_json = body.split("event: response.completed\ndata: ", 1)[1].strip()
                    response_id = json.loads(completed_json)["id"]
                assert calls[0][1] == "/v1/messages"
                assert calls[0][3] == {"x-api-key": "sk-upstream-anthropic-responses-stream"}
        state = app.state.db.execute(
            """
            SELECT route_name, client_protocol, upstream_protocol, request_json, output_json
            FROM response_states
            WHERE response_id = ?
            """,
            (response_id,),
        ).fetchone()
        assert state is not None
        assert state[0] == TEST_MODEL
        assert state[1] == "responses"
        assert state[2] == "messages"
        assert json.loads(state[3])["model"] == "claude-sonnet-4"
        assert json.loads(state[4])["status"] == "completed"

    asyncio.run(run())


def test_responses_messages_route_rejects_builtin_tools():
    async def run():
        app = create_app()
        app.state.ctx.models[TEST_MODEL] = _responses_messages_route()
        secret = seed_inference_key(app, "sk-responses-messages-tools")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/responses",
                headers={"Authorization": f"Bearer {secret}"},
                json={
                    "model": TEST_MODEL,
                    "input": "search this",
                    "tools": [{"type": "web_search"}],
                },
            )
            assert resp.status_code == 400
            assert resp.json()["detail"] == "builtin_tools_not_supported"

    asyncio.run(run())
