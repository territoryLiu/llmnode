import asyncio

import httpx

from llmnode.api.app import create_app
from llmnode.security import hash_api_key
from llmnode.storage.db import create_api_key


def test_admin_can_create_and_list_inference_api_keys():
    async def run():
        app = create_app()
        admin_secret = "sk-admin-seed"
        create_api_key(
            app.state.db,
            name="seed-admin",
            key_hash=hash_api_key(admin_secret),
            scopes=["admin"],
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            created = await client.post(
                "/admin/keys",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={
                    "name": "worker",
                    "scopes": ["inference"],
                    "rpm_limit": None,
                    "concurrency_limit": None,
                },
            )
            assert created.status_code == 200
            body = created.json()
            assert body["secret"].startswith("sk-")
            assert body["key"]["name"] == "worker"
            # Created key returns masked_key
            assert "masked_key" in body["key"]
            assert body["key"]["masked_key"].startswith("sk-")
            assert body["key"]["masked_key"] != body["secret"]

            listed = await client.get("/admin/keys", headers={"Authorization": f"Bearer {admin_secret}"})
            assert listed.status_code == 200
            key_row = listed.json()["keys"][0]
            assert key_row["name"] == "worker"
            assert "secret" not in key_row
            assert "key_hash" not in key_row
            assert key_row["plain_secret"] == body["secret"]
            # Listed key returns masked_key
            assert "masked_key" in key_row
            assert key_row["masked_key"].startswith("sk-")
            # Listed key includes usage_summary
            assert "usage_summary" in key_row
            assert "total_requests" in key_row["usage_summary"]

    asyncio.run(run())


def test_admin_keys_endpoint_rejects_admin_or_mixed_scopes():
    async def run():
        app = create_app()
        admin_secret = "sk-admin-seed"
        create_api_key(
            app.state.db,
            name="admin",
            key_hash=hash_api_key(admin_secret),
            scopes=["admin"],
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            duplicate = await client.post(
                "/admin/keys",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={"name": "another-admin", "scopes": ["admin"]},
            )
            assert duplicate.status_code == 400

            mixed = await client.post(
                "/admin/keys",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={"name": "worker-admin", "scopes": ["admin", "inference"]},
            )
            assert mixed.status_code == 400

    asyncio.run(run())


def test_admin_list_hides_admin_key_from_regular_key_table():
    async def run():
        app = create_app()
        admin_secret = "sk-admin-seed"
        create_api_key(
            app.state.db,
            name="admin",
            key_hash=hash_api_key(admin_secret),
            scopes=["admin"],
        )
        create_api_key(
            app.state.db,
            name="worker",
            key_hash=hash_api_key("sk-worker"),
            scopes=["inference"],
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            listed = await client.get("/admin/keys", headers={"Authorization": f"Bearer {admin_secret}"})
            assert listed.status_code == 200
            names = [item["name"] for item in listed.json()["keys"]]
            assert "admin" not in names
            assert "worker" in names

    asyncio.run(run())


def test_admin_can_patch_status_but_cannot_change_scopes_away_from_inference():
    async def run():
        app = create_app()
        admin_secret = "sk-admin-seed"
        create_api_key(
            app.state.db,
            name="seed-admin",
            key_hash=hash_api_key(admin_secret),
            scopes=["admin"],
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            created = await client.post(
                "/admin/keys",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={"name": "worker", "scopes": ["inference"]},
            )
            key_id = created.json()["key"]["id"]
            patched = await client.patch(
                f"/admin/keys/{key_id}",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={"status": "disabled"},
            )
            assert patched.status_code == 200
            assert patched.json()["key"]["status"] == "disabled"
            assert patched.json()["key"]["scopes"] == ["inference"]

            invalid = await client.patch(
                f"/admin/keys/{key_id}",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={"scopes": ["admin", "inference"]},
            )
            assert invalid.status_code == 400

    asyncio.run(run())


def test_admin_keys_normalize_timestamp_fields_to_utc_iso():
    async def run():
        app = create_app()
        admin_secret = "sk-admin-seed"
        create_api_key(
            app.state.db,
            name="seed-admin",
            key_hash=hash_api_key(admin_secret),
            scopes=["admin"],
        )
        raw_key = create_api_key(
            app.state.db,
            name="worker",
            key_hash=hash_api_key("sk-worker"),
            scopes=["inference"],
        )
        app.state.db.execute(
            """
            UPDATE api_keys
            SET created_at = ?, disabled_at = ?, last_used_at = ?
            WHERE id = ?
            """,
            (
                "2026-05-19 09:42:00",
                "2026-05-19 10:00:00",
                "2026-05-19 10:15:00",
                raw_key["id"],
            ),
        )
        app.state.db.commit()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            listed = await client.get("/admin/keys", headers={"Authorization": f"Bearer {admin_secret}"})
            assert listed.status_code == 200
            key_row = next(item for item in listed.json()["keys"] if item["id"] == raw_key["id"])
            assert key_row["created_at"] == "2026-05-19T09:42:00Z"
            assert key_row["disabled_at"] == "2026-05-19T10:00:00Z"
            assert key_row["last_used_at"] == "2026-05-19T10:15:00Z"

    asyncio.run(run())


def test_admin_can_delete_api_key():
    async def run():
        app = create_app()
        admin_secret = "sk-admin-seed"
        create_api_key(
            app.state.db,
            name="seed-admin",
            key_hash=hash_api_key(admin_secret),
            scopes=["admin"],
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            created = await client.post(
                "/admin/keys",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={"name": "to-delete", "scopes": ["inference"]},
            )
            key_id = created.json()["key"]["id"]
            deleted = await client.delete(f"/admin/keys/{key_id}", headers={"Authorization": f"Bearer {admin_secret}"})
            assert deleted.status_code == 200
            assert deleted.json()["deleted"] is True

            listed = await client.get("/admin/keys", headers={"Authorization": f"Bearer {admin_secret}"})
            assert all(item["id"] != key_id for item in listed.json()["keys"])

    asyncio.run(run())


def test_non_admin_key_cannot_use_admin_keys_endpoint():
    async def run():
        app = create_app()
        create_api_key(
            app.state.db,
            name="inference-only",
            key_hash=hash_api_key("sk-test-456"),
            scopes=["inference"],
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/admin/keys", headers={"Authorization": "Bearer sk-test-456"})
            assert resp.status_code == 403

    asyncio.run(run())


def test_admin_readiness_overview_returns_base_urls():
    async def run():
        app = create_app()
        admin_secret = "sk-admin-seed"
        create_api_key(
            app.state.db,
            name="seed-admin",
            key_hash=hash_api_key(admin_secret),
            scopes=["admin"],
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/admin/overview/readiness", headers={"Authorization": f"Bearer {admin_secret}"})
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["base_urls"]["local"] == "http://127.0.0.1:4000"
            assert "lan" in payload["base_urls"]

    asyncio.run(run())
