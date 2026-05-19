import asyncio

import httpx

from llmnode.api.app import create_app
from llmnode.config import load_settings
from llmnode.security import hash_api_key
from llmnode.storage.db import create_api_key


EXPECTED_MODEL_NAME = load_settings().vllm.model_name


def seed_admin_key(app, secret: str = "sk-admin-routes") -> str:
    create_api_key(
        app.state.db,
        name=f"admin-{secret}",
        key_hash=hash_api_key(secret),
        scopes=["admin"],
    )
    return secret


def test_admin_can_create_external_route():
    async def run():
        app = create_app()
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
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
                    "upstream_auth_ref": "OPENAI_KEY",
                    "enabled": True,
                    "capabilities_json": {"supports_responses": True},
                },
            )
            assert response.status_code == 200
            payload = response.json()["model"]
            assert payload["source_kind"] == "manual"
            assert payload["name"] == "openai-gpt-4.1"
            assert payload["lifecycle_mode"] == "external"

    asyncio.run(run())


def test_admin_cannot_delete_profile_seed_route():
    async def run():
        app = create_app()
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.delete(
                f"/admin/models/{EXPECTED_MODEL_NAME}",
                headers={"Authorization": f"Bearer {admin_secret}"},
            )
            assert response.status_code == 409

    asyncio.run(run())


def test_admin_can_delete_manual_route():
    async def run():
        app = create_app()
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            created = await client.post(
                "/admin/models",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "name": "anthropic-claude",
                    "display_name": "Anthropic Claude",
                    "lifecycle_mode": "external",
                    "upstream_protocol": "messages",
                    "upstream_base_url": "https://api.anthropic.com",
                    "upstream_model": "claude-sonnet",
                    "upstream_auth_kind": "x_api_key",
                    "upstream_auth_ref": "ANTHROPIC_KEY",
                },
            )
            assert created.status_code == 200

            deleted = await client.delete(
                "/admin/models/anthropic-claude",
                headers={"Authorization": f"Bearer {admin_secret}"},
            )
            assert deleted.status_code == 200
            assert deleted.json() == {"deleted": True, "name": "anthropic-claude"}

    asyncio.run(run())


def test_admin_cannot_reenable_stale_profile_seed_route():
    async def run():
        app = create_app()
        admin_secret = seed_admin_key(app)
        route = app.state.ctx.models[EXPECTED_MODEL_NAME]
        stale_route = route.__class__(
            **{
                **route.__dict__,
                "enabled": False,
                "stale": True,
            }
        )
        app.state.ctx.models[EXPECTED_MODEL_NAME] = stale_route
        app.state.db.execute(
            "UPDATE model_routes SET enabled = 0, stale = 1 WHERE name = ?",
            (EXPECTED_MODEL_NAME,),
        )
        app.state.db.commit()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            patch = await client.patch(
                f"/admin/models/{EXPECTED_MODEL_NAME}",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={"enabled": True},
            )
            assert patch.status_code == 409
            assert patch.json()["detail"] == "stale profile_seed routes cannot be re-enabled; create a manual route or switch back to the source profile"

    asyncio.run(run())


def test_admin_can_create_and_update_runtime_semantics_for_manual_route():
    async def run():
        app = create_app()
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
                    "upstream_auth_ref": "OPENAI_KEY",
                    "enabled": True,
                    "capabilities_json": {
                        "supports_responses": True,
                        "supports_chat": True,
                        "supports_messages": False,
                        "supports_stream": True,
                        "supports_function_tools": True,
                        "supports_builtin_tools": False,
                        "supports_previous_response_id_native": True,
                        "supports_json_schema": True,
                    },
                    "native_protocols_json": ["responses"],
                    "adapter_policies_json": [],
                    "tool_policies_json": {
                        "openai_function_tools": True,
                        "anthropic_function_tools": False,
                        "builtin_tools": False,
                    },
                    "protocol_features_json": {
                        "stream": True,
                        "count_tokens": False,
                        "json_schema": True,
                        "previous_response_id": True,
                    },
                },
            )
            assert created.status_code == 200
            created_model = created.json()["model"]
            assert created_model["native_protocols_json"] == ["responses"]
            assert created_model["tool_policies_json"]["anthropic_function_tools"] is False
            assert created_model["protocol_features_json"]["previous_response_id"] is True

            patched = await client.patch(
                "/admin/models/openai-gpt-4.1",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "native_protocols_json": ["chat"],
                    "adapter_policies_json": ["responses->chat"],
                    "tool_policies_json": {
                        "openai_function_tools": True,
                        "anthropic_function_tools": True,
                        "builtin_tools": False,
                    },
                    "protocol_features_json": {
                        "stream": True,
                        "count_tokens": False,
                        "json_schema": False,
                        "previous_response_id": False,
                    },
                },
            )
            assert patched.status_code == 200
            patched_model = patched.json()["model"]
            assert patched_model["native_protocols_json"] == ["chat"]
            assert patched_model["adapter_policies_json"] == ["responses->chat"]
            assert patched_model["tool_policies_json"]["anthropic_function_tools"] is True
            assert patched_model["protocol_features_json"]["previous_response_id"] is False

    asyncio.run(run())
