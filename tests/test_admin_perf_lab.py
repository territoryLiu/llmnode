import asyncio

import httpx

from llmnode.api.app import create_app
from llmnode.perf.lab_runner import PerfLabRunner
from llmnode.perf.lab_store import PerfRunStore
from llmnode.security import hash_api_key
from llmnode.storage.db import create_api_key


class ApiFakeExecutor:
    def execute_point(self, *, run_id, point, request, store, cancel_requested):
        store.update_point(run_id, point.point_id, status="completed", summary={"result": "success"})


def seed_admin_key(app, secret: str = "sk-admin-test") -> str:
    create_api_key(app.state.db, name="admin-perf", key_hash=hash_api_key(secret), scopes=["admin"])
    return secret


async def wait_done(client, run_id, headers):
    for _ in range(50):
        response = await client.get(f"/admin/perf/runs/{run_id}", headers=headers)
        payload = response.json()
        if payload["run"]["status"] in {"completed", "completed_with_errors", "failed", "cancelled"}:
            return payload
        await asyncio.sleep(0.02)
    raise AssertionError("run did not finish")


def test_admin_perf_run_lifecycle(tmp_path):
    async def run():
        app = create_app()
        app.state.perf_lab_runner = PerfLabRunner(
            store=PerfRunStore(tmp_path),
            executor=ApiFakeExecutor(),
        )
        admin_secret = seed_admin_key(app)
        headers = {"Authorization": f"Bearer {admin_secret}"}
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            create = await client.post(
                "/admin/perf/runs",
                headers=headers,
                json={"profile": "vllm_qwen36-27b-nvfp4", "targets": [4096]},
            )
            assert create.status_code == 200
            run_id = create.json()["run"]["run_id"]
            final = await wait_done(client, run_id, headers)
            assert final["run"]["status"] == "completed"

            listing = await client.get("/admin/perf/runs", headers=headers)
            assert listing.status_code == 200
            assert listing.json()["runs"][0]["run_id"] == run_id

            samples = await client.get(f"/admin/perf/runs/{run_id}/samples", headers=headers)
            assert samples.status_code == 200
            assert "samples" in samples.json()

    asyncio.run(run())


def test_admin_perf_rejects_invalid_payload(tmp_path):
    async def run():
        app = create_app()
        app.state.perf_lab_runner = PerfLabRunner(store=PerfRunStore(tmp_path), executor=ApiFakeExecutor())
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/admin/perf/runs",
                headers={"Authorization": f"Bearer {admin_secret}"},
                json={"profile": "", "targets": []},
            )
            assert response.status_code == 400

    asyncio.run(run())
