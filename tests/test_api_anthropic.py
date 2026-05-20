import asyncio

from unittest.mock import patch

import httpx

from llmnode.api.app import create_app
from llmnode.config import load_settings
from llmnode.models import ModelCapabilities, ModelRoute
from llmnode.proxy.vllm_client import VLLMClient
from llmnode.security import hash_api_key
from llmnode.storage.db import create_api_key


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


TEST_MODEL = load_settings().vllm.model_name


def seed_admin_key(app, secret: str = "sk-admin-test") -> str:
    create_api_key(
        app.state.db,
        name=f"admin-{secret}",
        key_hash=hash_api_key(secret),
        scopes=["admin"],
    )
    return secret


def test_anthropic_messages_endpoint_exists():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/messages",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "model": TEST_MODEL,
                    "max_tokens": 16,
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
            assert resp.status_code == 200
            assert resp.json()["content"][0]["text"] == TEST_MODEL

    asyncio.run(run())


def test_anthropic_messages_managed_local_allows_claude_code_builtin_tool_metadata():
    async def run():
        app = create_app()
        captured: list[tuple[str, dict]] = []

        class CapturingClient(FakeClient):
            async def post_json(self, path, payload):
                captured.append((path, payload))
                return await super().post_json(path, payload)

        app.state.ctx.backend_client = CapturingClient()
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/messages",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "model": TEST_MODEL,
                    "max_tokens": 16,
                    "messages": [{"role": "user", "content": "hello"}],
                    "tools": [
                        {
                            "type": "bash_20241022",
                            "name": "web_search",
                            "max_uses": 5,
                        },
                        {
                            "name": "Read",
                            "description": "Read files from local filesystem",
                            "input_schema": {
                                "type": "object",
                                "properties": {"file_path": {"type": "string"}},
                                "required": ["file_path"],
                            },
                        }
                    ],
                },
            )
            assert resp.status_code == 200
            assert captured[0][0] == "/v1/messages"
            assert len(captured[0][1]["tools"]) == 1
            assert captured[0][1]["tools"][0]["name"] == "Read"

    asyncio.run(run())


def test_anthropic_messages_managed_local_forwards_anthropic_tool_definitions():
    async def run():
        app = create_app()
        captured: list[tuple[str, dict]] = []

        class CapturingClient(FakeClient):
            async def post_json(self, path, payload):
                captured.append((path, payload))
                return {
                    "id": "msg_tool_1",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "Read",
                            "input": {"file_path": "README.md"},
                        }
                    ],
                    "model": payload["model"],
                }

        app.state.ctx.backend_client = CapturingClient()
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/messages",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "model": TEST_MODEL,
                    "max_tokens": 16,
                    "messages": [{"role": "user", "content": "read readme"}],
                    "tools": [
                        {
                            "name": "Read",
                            "description": "Read files from local filesystem",
                            "input_schema": {
                                "type": "object",
                                "properties": {"file_path": {"type": "string"}},
                                "required": ["file_path"],
                            },
                        }
                    ],
                },
            )
            assert resp.status_code == 200
            assert captured[0][0] == "/v1/messages"
            assert captured[0][1]["tools"][0]["name"] == "Read"
            assert resp.json()["content"][0]["type"] == "tool_use"

    asyncio.run(run())


def test_anthropic_messages_managed_local_accepts_tool_result_followup():
    async def run():
        app = create_app()
        captured: list[tuple[str, dict]] = []

        class CapturingClient(FakeClient):
            async def post_json(self, path, payload):
                captured.append((path, payload))
                return {
                    "id": "msg_tool_2",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "done"}],
                    "model": payload["model"],
                }

        app.state.ctx.backend_client = CapturingClient()
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/messages",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "model": TEST_MODEL,
                    "max_tokens": 16,
                    "messages": [
                        {"role": "user", "content": "read readme"},
                        {
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "tool_use",
                                    "id": "toolu_1",
                                    "name": "Read",
                                    "input": {"file_path": "README.md"},
                                }
                            ],
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": "toolu_1",
                                    "content": "README contents",
                                }
                            ],
                        },
                    ],
                    "tools": [
                        {
                            "name": "Read",
                            "description": "Read files from local filesystem",
                            "input_schema": {
                                "type": "object",
                                "properties": {"file_path": {"type": "string"}},
                                "required": ["file_path"],
                            },
                        }
                    ],
                },
            )
            assert resp.status_code == 200
            assert captured[0][1]["messages"][2]["content"][0]["type"] == "tool_result"

    asyncio.run(run())


def test_anthropic_messages_managed_local_rejects_generic_builtin_tools():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        app.state.ctx.models[TEST_MODEL] = ModelRoute(
            name=TEST_MODEL,
            display_name="Managed Local Messages Without Builtins",
            backend_model=TEST_MODEL,
            backend_type="vllm",
            enabled=True,
            lifecycle_mode="managed_local",
            upstream_protocol="messages",
            capabilities=ModelCapabilities(
                supports_responses=False,
                supports_chat=False,
                supports_messages=True,
                supports_stream=True,
                supports_function_tools=True,
                supports_builtin_tools=False,
            ),
            native_protocols_json=["messages"],
            tool_policies_json={
                "anthropic_function_tools": True,
                "builtin_tools": False,
            },
        )
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/messages",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "model": TEST_MODEL,
                    "max_tokens": 16,
                    "messages": [{"role": "user", "content": "hello"}],
                    "tools": [{"type": "web_search"}],
                },
            )
            assert resp.status_code == 400
            assert resp.json()["detail"] == "builtin_tools_not_supported"

    asyncio.run(run())


def test_anthropic_messages_request_logs_message_block_types():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/messages",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "model": TEST_MODEL,
                    "max_tokens": 16,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "describe this image"},
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": "abc123",
                                    },
                                },
                            ],
                        }
                    ],
                },
            )
            assert resp.status_code == 200
            request_id = resp.headers["x-request-id"]

        detail = app.state.db.execute(
            "SELECT metadata_json FROM request_logs WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        assert detail is not None
        metadata = detail[0]
        payload = {} if metadata is None else __import__("json").loads(metadata)
        assert payload["client_protocol"] == "messages"
        assert payload["message_block_types"] == [
            {"role": "user", "types": ["text", "image"]}
        ]

    asyncio.run(run())


def test_anthropic_count_tokens_endpoint_exists():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/messages/count_tokens",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "model": TEST_MODEL,
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
            assert resp.status_code == 200
            payload = resp.json()
            assert "input_tokens" in payload
            assert isinstance(payload["input_tokens"], int)

    asyncio.run(run())


def test_anthropic_messages_external_messages_route_posts_to_upstream_messages():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        calls: list[tuple[str, str, dict, dict | None]] = []

        async def fake_post_json_to(base_url, path, payload, headers=None):
            calls.append((base_url, path, payload, headers))
            return {
                "id": "msg_ext_1",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "ok"}],
                "model": payload["model"],
                "usage": {"input_tokens": 3, "output_tokens": 5},
            }

        app.state.post_json_to = fake_post_json_to
        app.state.ctx.post_json_to = fake_post_json_to
        app.state.ctx.models[TEST_MODEL] = ModelRoute(
            name=TEST_MODEL,
            display_name="Claude External",
            backend_model=None,
            backend_type=None,
            enabled=True,
            lifecycle_mode="external",
            upstream_protocol="messages",
            upstream_base_url="https://messages.example.com",
            upstream_model="claude-sonnet-4",
            upstream_auth_kind="x_api_key",
            upstream_auth_ref="ANTHROPIC_PROXY_KEY",
            capabilities=ModelCapabilities(
                supports_responses=False,
                supports_chat=False,
                supports_messages=True,
                supports_stream=True,
                supports_function_tools=True,
                supports_builtin_tools=False,
            ),
        )
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        with patch.dict("os.environ", {"ANTHROPIC_PROXY_KEY": "sk-upstream-anthropic"}, clear=False):
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.post(
                    "/v1/messages",
                    headers={"Authorization": f"Bearer {admin_secret}"},
                    json={
                        "model": TEST_MODEL,
                        "max_tokens": 16,
                        "messages": [{"role": "user", "content": "hello"}],
                    },
                )
                assert resp.status_code == 200
                assert resp.json()["model"] == "claude-sonnet-4"
                assert calls[0][0] == "https://messages.example.com"
                assert calls[0][1] == "/v1/messages"
                assert calls[0][2]["model"] == "claude-sonnet-4"
                assert calls[0][3] == {"x-api-key": "sk-upstream-anthropic"}

    asyncio.run(run())


def test_anthropic_messages_external_messages_route_streams_from_upstream_messages():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        calls: list[tuple[str, str, dict, dict | None]] = []

        async def fake_stream_bytes_from(base_url, path, payload, headers=None):
            calls.append((base_url, path, payload, headers))
            chunks = [
                b'event: message_start\ndata: {"type":"message_start","message":{"id":"msg_ext_2"}}\n\n',
                b'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hi"}}\n\n',
                b'event: message_delta\ndata: {"type":"message_delta","usage":{"input_tokens":2,"output_tokens":1}}\n\n',
            ]
            for chunk in chunks:
                yield chunk

        app.state.stream_bytes_from = fake_stream_bytes_from
        app.state.ctx.stream_bytes_from = fake_stream_bytes_from
        app.state.ctx.models[TEST_MODEL] = ModelRoute(
            name=TEST_MODEL,
            display_name="Claude External",
            backend_model=None,
            backend_type=None,
            enabled=True,
            lifecycle_mode="external",
            upstream_protocol="messages",
            upstream_base_url="https://messages.example.com",
            upstream_model="claude-sonnet-4",
            upstream_auth_kind="x_api_key",
            upstream_auth_ref="ANTHROPIC_STREAM_KEY",
            capabilities=ModelCapabilities(
                supports_responses=False,
                supports_chat=False,
                supports_messages=True,
                supports_stream=True,
                supports_function_tools=True,
                supports_builtin_tools=False,
            ),
        )
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        with patch.dict("os.environ", {"ANTHROPIC_STREAM_KEY": "sk-upstream-anthropic-stream"}, clear=False):
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                async with client.stream(
                    "POST",
                    "/v1/messages",
                    headers={"Authorization": f"Bearer {admin_secret}"},
                    json={
                        "model": TEST_MODEL,
                        "max_tokens": 16,
                        "stream": True,
                        "messages": [{"role": "user", "content": "hello"}],
                    },
                ) as resp:
                    assert resp.status_code == 200
                    body = await resp.aread()
                    text = body.decode()
                    assert "content_block_delta" in text
                assert calls[0][0] == "https://messages.example.com"
                assert calls[0][1] == "/v1/messages"
                assert calls[0][2]["model"] == "claude-sonnet-4"
                assert calls[0][3] == {"x-api-key": "sk-upstream-anthropic-stream"}

    asyncio.run(run())


def test_anthropic_messages_external_messages_route_rejects_missing_upstream_secret():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        app.state.ctx.models[TEST_MODEL] = ModelRoute(
            name=TEST_MODEL,
            display_name="Claude External",
            backend_model=None,
            backend_type=None,
            enabled=True,
            lifecycle_mode="external",
            upstream_protocol="messages",
            upstream_base_url="https://messages.example.com",
            upstream_model="claude-sonnet-4",
            upstream_auth_kind="x_api_key",
            upstream_auth_ref="MISSING_ANTHROPIC_PROXY_KEY",
            capabilities=ModelCapabilities(
                supports_responses=False,
                supports_chat=False,
                supports_messages=True,
                supports_stream=True,
                supports_function_tools=True,
                supports_builtin_tools=False,
            ),
        )
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        with patch.dict("os.environ", {}, clear=False):
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.post(
                    "/v1/messages",
                    headers={"Authorization": f"Bearer {admin_secret}"},
                    json={
                        "model": TEST_MODEL,
                        "max_tokens": 16,
                        "messages": [{"role": "user", "content": "hello"}],
                    },
                )
                assert resp.status_code == 500
                assert resp.json()["detail"] == "missing_upstream_auth_secret"

    asyncio.run(run())


def test_anthropic_messages_rejects_external_non_messages_route():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        app.state.ctx.models[TEST_MODEL] = ModelRoute(
            name=TEST_MODEL,
            display_name="External Chat Only",
            backend_model=None,
            backend_type=None,
            enabled=True,
            lifecycle_mode="external",
            upstream_protocol="chat",
            upstream_base_url="https://chat.example.com/v1",
            upstream_model="gpt-4o-mini",
            upstream_auth_kind="bearer",
            upstream_auth_ref="openai-chat",
            capabilities=ModelCapabilities(
                supports_responses=False,
                supports_chat=True,
                supports_messages=True,
                supports_stream=True,
                supports_function_tools=True,
                supports_builtin_tools=True,
            ),
        )
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/messages",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "model": TEST_MODEL,
                    "max_tokens": 16,
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
            assert resp.status_code == 400
            assert resp.json()["detail"] == "native_protocol_not_supported"

    asyncio.run(run())


def test_anthropic_messages_returns_503_when_warming_up():
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
                "/v1/messages",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "model": TEST_MODEL,
                    "max_tokens": 16,
                    "stream": True,
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
            assert resp.status_code == 503
            assert resp.json()["detail"] == "backend_warming_up"

    asyncio.run(run())
