import asyncio
import json

import httpx

from llmnode.api.app import create_app
from llmnode.models import ModelCapabilities, ModelRoute
from llmnode.security import hash_api_key
from llmnode.storage.db import create_api_key, upsert_model_route


def test_native_responses_route_posts_to_upstream_responses():
    async def run():
        app = create_app()
        calls: list[tuple[str, str, dict, dict | None]] = []

        async def fake_post_json_to(base_url, path, payload, headers=None):
            calls.append((base_url, path, payload, headers))
            return {
                "id": "resp_upstream_1",
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
                "usage": {"input_tokens": 3, "output_tokens": 5, "total_tokens": 8},
            }

        app.state.post_json_to = fake_post_json_to
        upsert_model_route(
            app.state.db,
            {
                "name": "gpt-4o",
                "display_name": "GPT-4o",
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
        app.state.ctx.models = {}
        app.state.ctx.models["gpt-4o"] = ModelRoute(
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
            capabilities=ModelCapabilities(
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
        create_api_key(app.state.db, name="resp-native", key_hash=hash_api_key("sk-native"), scopes=["inference"])
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/responses",
                headers={"Authorization": "Bearer sk-native"},
                json={"model": "gpt-4o", "input": "hello"},
            )
            assert resp.status_code == 200
            assert calls[0][1] == "/v1/responses"
            assert calls[0][2]["model"] == "gpt-4o"

    asyncio.run(run())


def test_native_responses_route_uses_upstream_previous_response_id():
    async def run():
        app = create_app()
        calls: list[tuple[str, str, dict, dict | None]] = []

        async def fake_post_json_to(base_url, path, payload, headers=None):
            calls.append((base_url, path, payload, headers))
            return {
                "id": "resp_upstream_2",
                "object": "response",
                "status": "completed",
                "model": payload["model"],
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "ok2"}],
                    }
                ],
                "usage": {"input_tokens": 3, "output_tokens": 5, "total_tokens": 8},
            }

        app.state.post_json_to = fake_post_json_to
        app.state.ctx.models = {
            "gpt-4o": ModelRoute(
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
                capabilities=ModelCapabilities(
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
        create_api_key(app.state.db, name="resp-native-2", key_hash=hash_api_key("sk-native-2"), scopes=["inference"])
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
                "resp_local_1",
                "req_1",
                "gpt-4o",
                '[{"role":"user","content":"hello"}]',
                '[]',
                '[{"role":"user","content":"hello"}]',
                None,
                "gpt-4o",
                "responses",
                "responses",
                "resp_upstream_1",
                '{"model":"gpt-4o","input":"hello"}',
                '{"id":"resp_local_1"}',
            ),
        )
        app.state.db.commit()

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/responses",
                headers={"Authorization": "Bearer sk-native-2"},
                json={
                    "model": "gpt-4o",
                    "previous_response_id": "resp_local_1",
                    "input": "follow up",
                },
            )
            assert resp.status_code == 200
            assert calls[-1][2]["previous_response_id"] == "resp_upstream_1"

    asyncio.run(run())


def test_native_responses_stream_posts_to_upstream_responses_stream():
    async def run():
        app = create_app()
        calls: list[tuple[str, str, dict, dict | None]] = []

        async def fake_stream_bytes_from(base_url, path, payload, headers=None):
            calls.append((base_url, path, payload, headers))
            chunks = [
                b'event: response.output_text.delta\ndata: {"delta":"Hi"}\n\n',
                (
                    "event: response.completed\ndata: "
                    + json.dumps(
                        {
                            "id": "resp_upstream_stream_1",
                            "status": "completed",
                            "output": [
                                {
                                    "type": "message",
                                    "role": "assistant",
                                    "content": [{"type": "output_text", "text": "Hi"}],
                                }
                            ],
                            "usage": {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
                        }
                    )
                    + "\n\n"
                ).encode(),
            ]
            for chunk in chunks:
                yield chunk

        app.state.stream_bytes_from = fake_stream_bytes_from
        app.state.ctx.models = {
            "gpt-4o": ModelRoute(
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
                capabilities=ModelCapabilities(
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
        create_api_key(app.state.db, name="resp-native-stream", key_hash=hash_api_key("sk-native-stream"), scopes=["inference"])
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with client.stream(
                "POST",
                "/v1/responses",
                headers={"Authorization": "Bearer sk-native-stream"},
                json={"model": "gpt-4o", "input": "hello", "stream": True},
            ) as resp:
                assert resp.status_code == 200
                body = ""
                async for chunk in resp.aiter_text():
                    body += chunk
                assert "event: response.output_text.delta" in body
                assert "event: response.completed" in body
            assert calls[0][1] == "/v1/responses"

    asyncio.run(run())
