import asyncio

import httpx

from llmnode.api.app import create_app
from llmnode.security import hash_api_key
from llmnode.storage.db import create_api_key


def test_admin_can_create_and_list_api_keys():
    async def run():
        app = create_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            created = await client.post(
                "/admin/keys",
                headers={"Authorization": "Bearer dev-key"},
                json={
                    "name": "console-admin",
                    "scopes": ["admin"],
                    "rpm_limit": None,
                    "concurrency_limit": None,
                },
            )
            assert created.status_code == 200
            body = created.json()
            assert body["secret"].startswith("ln_live_")
            assert body["key"]["name"] == "console-admin"

            listed = await client.get("/admin/keys", headers={"Authorization": "Bearer dev-key"})
            assert listed.status_code == 200
            key_row = listed.json()["keys"][0]
            assert key_row["name"] == "console-admin"
            assert "secret" not in key_row
            assert "key_hash" not in key_row

    asyncio.run(run())


def test_admin_can_patch_status_and_scopes():
    async def run():
        app = create_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            created = await client.post(
                "/admin/keys",
                headers={"Authorization": "Bearer dev-key"},
                json={"name": "worker", "scopes": ["inference"]},
            )
            key_id = created.json()["key"]["id"]
            patched = await client.patch(
                f"/admin/keys/{key_id}",
                headers={"Authorization": "Bearer dev-key"},
                json={"status": "disabled", "scopes": ["admin", "inference"]},
            )
            assert patched.status_code == 200
            assert patched.json()["key"]["status"] == "disabled"
            assert patched.json()["key"]["scopes"] == ["admin", "inference"]

    asyncio.run(run())


def test_admin_can_delete_api_key():
    async def run():
        app = create_app()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            created = await client.post(
                "/admin/keys",
                headers={"Authorization": "Bearer dev-key"},
                json={"name": "to-delete", "scopes": ["inference"]},
            )
            key_id = created.json()["key"]["id"]
            deleted = await client.delete(f"/admin/keys/{key_id}", headers={"Authorization": "Bearer dev-key"})
            assert deleted.status_code == 200
            assert deleted.json()["deleted"] is True

            listed = await client.get("/admin/keys", headers={"Authorization": "Bearer dev-key"})
            assert all(item["id"] != key_id for item in listed.json()["keys"])

    asyncio.run(run())


def test_non_admin_key_cannot_use_admin_keys_endpoint():
    async def run():
        app = create_app()
        create_api_key(
            app.state.db,
            name="inference-only",
            key_hash=hash_api_key("ln_test_456"),
            scopes=["inference"],
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/admin/keys", headers={"Authorization": "Bearer ln_test_456"})
            assert resp.status_code == 403

    asyncio.run(run())
