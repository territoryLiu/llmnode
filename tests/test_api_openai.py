import asyncio
from unittest.mock import patch

import httpx

from llmnode.api.app import create_app
from llmnode.config import load_settings
from llmnode.models import ModelCapabilities, ModelRoute
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


def test_chat_completions_external_chat_route_posts_to_upstream_chat():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        calls: list[tuple[str, str, dict, dict | None]] = []

        async def fake_post_json_to(base_url, path, payload, headers=None):
            calls.append((base_url, path, payload, headers))
            return {
                "id": "chatcmpl-ext-1",
                "object": "chat.completion",
                "model": payload["model"],
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8},
            }

        app.state.post_json_to = fake_post_json_to
        app.state.ctx.post_json_to = fake_post_json_to
        app.state.ctx.models[EXPECTED_MODEL_NAME] = ModelRoute(
            name=EXPECTED_MODEL_NAME,
            display_name="External Chat",
            backend_model=None,
            backend_type=None,
            enabled=True,
            lifecycle_mode="external",
            upstream_protocol="chat",
            upstream_base_url="https://chat.example.com/v1",
            upstream_model="gpt-4o-mini",
            upstream_auth_kind="bearer",
            upstream_auth_ref="OPENAI_CHAT_TOKEN",
            capabilities=ModelCapabilities(
                supports_responses=False,
                supports_chat=True,
                supports_messages=False,
                supports_stream=True,
                supports_function_tools=True,
                supports_builtin_tools=True,
            ),
        )
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        with patch.dict("os.environ", {"OPENAI_CHAT_TOKEN": "sk-upstream-openai-chat"}, clear=False):
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
                assert resp.json()["model"] == "gpt-4o-mini"
                assert calls[0][0] == "https://chat.example.com/v1"
                assert calls[0][1] == "/v1/chat/completions"
                assert calls[0][2]["model"] == "gpt-4o-mini"
                assert calls[0][3] == {"authorization": "Bearer sk-upstream-openai-chat"}

    asyncio.run(run())


def test_chat_completions_external_chat_route_streams_from_upstream_chat():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        calls: list[tuple[str, str, dict, dict | None]] = []

        async def fake_stream_bytes_from(base_url, path, payload, headers=None):
            calls.append((base_url, path, payload, headers))
            chunks = [
                b'data: {"id":"chatcmpl-ext-2","choices":[{"delta":{"content":"Hi"}}]}\n\n',
                b'data: {"id":"chatcmpl-ext-2","choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":2,"completion_tokens":1,"total_tokens":3}}\n\n',
                b"data: [DONE]\n\n",
            ]
            for chunk in chunks:
                yield chunk

        app.state.stream_bytes_from = fake_stream_bytes_from
        app.state.ctx.stream_bytes_from = fake_stream_bytes_from
        app.state.ctx.models[EXPECTED_MODEL_NAME] = ModelRoute(
            name=EXPECTED_MODEL_NAME,
            display_name="External Chat",
            backend_model=None,
            backend_type=None,
            enabled=True,
            lifecycle_mode="external",
            upstream_protocol="chat",
            upstream_base_url="https://chat.example.com/v1",
            upstream_model="gpt-4o-mini",
            upstream_auth_kind="bearer",
            upstream_auth_ref="OPENAI_CHAT_STREAM_TOKEN",
            capabilities=ModelCapabilities(
                supports_responses=False,
                supports_chat=True,
                supports_messages=False,
                supports_stream=True,
                supports_function_tools=True,
                supports_builtin_tools=True,
            ),
        )
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        with patch.dict("os.environ", {"OPENAI_CHAT_STREAM_TOKEN": "sk-upstream-openai-stream"}, clear=False):
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                async with client.stream(
                    "POST",
                    "/v1/chat/completions",
                    headers={"Authorization": f"Bearer {admin_secret}"},
                    json={
                        "model": EXPECTED_MODEL_NAME,
                        "messages": [{"role": "user", "content": "hello"}],
                        "max_tokens": 16,
                        "stream": True,
                    },
                ) as resp:
                    assert resp.status_code == 200
                    body = await resp.aread()
                    text = body.decode()
                    assert 'data: {"id":"chatcmpl-ext-2"' in text
                assert calls[0][0] == "https://chat.example.com/v1"
                assert calls[0][1] == "/v1/chat/completions"
                assert calls[0][2]["model"] == "gpt-4o-mini"
                assert calls[0][3] == {"authorization": "Bearer sk-upstream-openai-stream"}

    asyncio.run(run())


def test_chat_completions_external_chat_route_rejects_missing_upstream_secret():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        app.state.ctx.models[EXPECTED_MODEL_NAME] = ModelRoute(
            name=EXPECTED_MODEL_NAME,
            display_name="External Chat",
            backend_model=None,
            backend_type=None,
            enabled=True,
            lifecycle_mode="external",
            upstream_protocol="chat",
            upstream_base_url="https://chat.example.com/v1",
            upstream_model="gpt-4o-mini",
            upstream_auth_kind="bearer",
            upstream_auth_ref="MISSING_OPENAI_CHAT_TOKEN",
            capabilities=ModelCapabilities(
                supports_responses=False,
                supports_chat=True,
                supports_messages=False,
                supports_stream=True,
                supports_function_tools=True,
                supports_builtin_tools=True,
            ),
        )
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        with patch.dict("os.environ", {}, clear=False):
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
                assert resp.status_code == 500
                assert resp.json()["detail"] == "missing_upstream_auth_secret"

    asyncio.run(run())


def test_chat_completions_rejects_external_non_chat_route():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        app.state.ctx.models[EXPECTED_MODEL_NAME] = ModelRoute(
            name=EXPECTED_MODEL_NAME,
            display_name="External Responses Only",
            backend_model=None,
            backend_type=None,
            enabled=True,
            lifecycle_mode="external",
            upstream_protocol="responses",
            upstream_base_url="https://api.openai.com/v1",
            upstream_model="gpt-4o",
            upstream_auth_kind="bearer",
            upstream_auth_ref="openai-prod",
            capabilities=ModelCapabilities(
                supports_responses=True,
                supports_chat=True,
                supports_messages=False,
                supports_stream=True,
                supports_function_tools=True,
                supports_builtin_tools=True,
            ),
        )
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
            assert resp.status_code == 400
            assert resp.json()["detail"] == "unsupported_route_protocol_combination"

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


def test_admin_models_can_update_external_route_fields_for_manual_route():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            created = await client.post(
                "/admin/models",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "name": "openai-gpt-4.1",
                    "display_name": "OpenAI GPT-4.1",
                    "lifecycle_mode": "external",
                    "upstream_protocol": "responses",
                    "upstream_base_url": "https://api.openai.com/v1",
                    "upstream_model": "gpt-4.1",
                    "upstream_auth_kind": "bearer",
                    "upstream_auth_ref": "openai-prod",
                    "enabled": True,
                    "capabilities_json": {
                        "supports_responses": True,
                        "supports_chat": True,
                        "supports_messages": False,
                        "supports_stream": True,
                        "supports_function_tools": True,
                        "supports_builtin_tools": True,
                        "supports_previous_response_id_native": True,
                        "supports_json_schema": True,
                    },
                },
            )
            assert created.status_code == 200

            patch = await client.patch(
                "/admin/models/openai-gpt-4.1",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "display_name": "Qwen3 Coder External",
                    "enabled": True,
                    "lifecycle_mode": "external",
                    "backend_type": None,
                    "backend_model": None,
                    "upstream_protocol": "responses",
                    "upstream_base_url": "https://api.openai.com/v1",
                    "upstream_model": "gpt-4o",
                    "upstream_auth_kind": "bearer",
                    "upstream_auth_ref": "openai-prod",
                    "capabilities_json": {
                        "supports_responses": True,
                        "supports_chat": True,
                        "supports_messages": False,
                        "supports_stream": True,
                        "supports_function_tools": True,
                        "supports_builtin_tools": True,
                        "supports_previous_response_id_native": True,
                        "supports_json_schema": True,
                    },
                },
            )
            assert patch.status_code == 200
            model = patch.json()["model"]
            assert model["display_name"] == "Qwen3 Coder External"
            assert model["lifecycle_mode"] == "external"
            assert model["backend_type"] is None
            assert model["backend_model"] is None
            assert model["upstream_protocol"] == "responses"
            assert model["upstream_base_url"] == "https://api.openai.com/v1"
            assert model["upstream_model"] == "gpt-4o"
            assert model["upstream_auth_kind"] == "bearer"
            assert model["upstream_auth_ref"] == "openai-prod"
            assert model["capabilities_json"]["supports_previous_response_id_native"] is True

    asyncio.run(run())


def test_admin_models_reject_invalid_external_route_payload_for_manual_route():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            created = await client.post(
                "/admin/models",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "name": "openai-gpt-4.1",
                    "display_name": "OpenAI GPT-4.1",
                    "lifecycle_mode": "external",
                    "upstream_protocol": "responses",
                    "upstream_base_url": "https://api.openai.com/v1",
                    "upstream_model": "gpt-4.1",
                    "upstream_auth_kind": "bearer",
                    "upstream_auth_ref": "openai-prod",
                },
            )
            assert created.status_code == 200

            patch = await client.patch(
                "/admin/models/openai-gpt-4.1",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "lifecycle_mode": "external",
                    "upstream_protocol": "responses",
                    "upstream_base_url": "",
                },
            )
            assert patch.status_code == 400
            assert patch.json()["detail"] == "upstream_base_url is required for external routes"

            patch2 = await client.patch(
                f"/admin/models/{EXPECTED_MODEL_NAME}",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "lifecycle_mode": "managed_local",
                    "upstream_protocol": "bogus",
                },
            )
            assert patch2.status_code == 400
            assert patch2.json()["detail"] == "unsupported upstream_protocol: bogus"

    asyncio.run(run())


def test_admin_models_reject_profile_seed_conversion_to_external():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            patch = await client.patch(
                f"/admin/models/{EXPECTED_MODEL_NAME}",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "lifecycle_mode": "external",
                    "upstream_protocol": "responses",
                    "upstream_base_url": "https://api.openai.com/v1",
                    "upstream_model": "gpt-4o",
                    "upstream_auth_kind": "bearer",
                    "upstream_auth_ref": "openai-prod",
                },
            )
            assert patch.status_code == 409
            assert patch.json()["detail"] == "profile_seed routes cannot be converted to manual external routes"

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
