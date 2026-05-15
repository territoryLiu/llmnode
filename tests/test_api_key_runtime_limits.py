import asyncio

import httpx

from llmnode.api.app import create_app
from llmnode.config import load_settings
from llmnode.proxy.vllm_client import VLLMClient
from llmnode.runtime import RequestGate
from llmnode.security import hash_api_key
from llmnode.storage.db import create_api_key


class FastClient(VLLMClient):
    def __init__(self):
        super().__init__(base_url="http://fake")

    async def health(self) -> bool:
        return True

    async def post_json(self, path, payload):
        return {"path": path, "model": payload["model"]}


class SlowClient(VLLMClient):
    def __init__(self):
        super().__init__(base_url="http://fake")
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def health(self) -> bool:
        return True

    async def post_json(self, path, payload):
        self.started.set()
        await self.release.wait()
        return {"path": path, "model": payload["model"]}


TEST_MODEL = load_settings().vllm.model_name


def seed_admin_key(app, secret: str = "sk-admin-test") -> str:
    create_api_key(
        app.state.db,
        name=f"admin-{secret}",
        key_hash=hash_api_key(secret),
        scopes=["admin"],
    )
    return secret


def test_db_key_rpm_limit_rejects_second_request():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FastClient()
        admin_secret = seed_admin_key(app)
        create_api_key(
            app.state.db,
            name="rpm-key",
            key_hash=hash_api_key("sk-test-rpm"),
            scopes=["inference"],
            rpm_limit=1,
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            first = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer sk-test-rpm"},
                json={
                    "model": TEST_MODEL,
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            assert first.status_code == 200

            second = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer sk-test-rpm"},
                json={
                    "model": TEST_MODEL,
                    "messages": [{"role": "user", "content": "hello again"}],
                    "max_tokens": 16,
                },
            )
            assert second.status_code == 429
            assert "rpm" in second.json()["detail"]

            logs = await client.get("/admin/request-logs", headers={"Authorization": f"Bearer {admin_secret}"})
            assert logs.status_code == 200
            rejected = logs.json()["logs"][0]
            assert rejected["status"] == "rejected"
            assert rejected["rejection_reason"] == "rpm_limit_exceeded"

    asyncio.run(run())


def test_queue_full_does_not_consume_api_key_rpm_budget():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FastClient()
        app.state.request_gate = RequestGate(execution_limit=1, queue_limit=0)
        admin_secret = seed_admin_key(app)
        create_api_key(
            app.state.db,
            name="queue-full-key",
            key_hash=hash_api_key("sk-test-queue-full"),
            scopes=["inference"],
            rpm_limit=1,
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            first = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer sk-test-queue-full"},
                json={
                    "model": TEST_MODEL,
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            assert first.status_code == 429
            assert "queue" in first.json()["detail"]

            second = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer sk-test-queue-full"},
                json={
                    "model": TEST_MODEL,
                    "messages": [{"role": "user", "content": "hello again"}],
                    "max_tokens": 16,
                },
            )
            assert second.status_code == 429
            assert "queue" in second.json()["detail"]

            logs = await client.get("/admin/request-logs", headers={"Authorization": f"Bearer {admin_secret}"})
            assert logs.status_code == 200
            assert all(item["rejection_reason"] == "queue_full" for item in logs.json()["logs"][:2])

    asyncio.run(run())


def test_db_key_concurrency_limit_rejects_parallel_request():
    async def run():
        app = create_app()
        slow_client = SlowClient()
        app.state.ctx.backend_client = slow_client
        app.state.request_gate = RequestGate(execution_limit=4, queue_limit=8)
        admin_secret = seed_admin_key(app)
        create_api_key(
            app.state.db,
            name="concurrency-key",
            key_hash=hash_api_key("sk-test-concurrency"),
            scopes=["inference"],
            concurrency_limit=1,
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            first_task = asyncio.create_task(
                client.post(
                    "/v1/chat/completions",
                    headers={"Authorization": "Bearer sk-test-concurrency"},
                    json={
                        "model": TEST_MODEL,
                        "messages": [{"role": "user", "content": "hello"}],
                        "max_tokens": 16,
                    },
                )
            )
            await asyncio.wait_for(slow_client.started.wait(), timeout=1)

            second_task = asyncio.create_task(
                client.post(
                    "/v1/chat/completions",
                    headers={"Authorization": "Bearer sk-test-concurrency"},
                    json={
                        "model": TEST_MODEL,
                        "messages": [{"role": "user", "content": "hello again"}],
                        "max_tokens": 16,
                    },
                )
            )
            await asyncio.sleep(0.05)
            assert second_task.done(), "parallel request should be rejected immediately by concurrency limit"

            second = await second_task
            assert second.status_code == 429
            assert "concurrency" in second.json()["detail"]

            slow_client.release.set()
            first = await asyncio.wait_for(first_task, timeout=1)
            assert first.status_code == 200

            logs = await client.get("/admin/request-logs", headers={"Authorization": f"Bearer {admin_secret}"})
            assert logs.status_code == 200
            rejected = next(item for item in logs.json()["logs"] if item["status"] == "rejected")
            assert rejected["rejection_reason"] == "concurrency_limit_exceeded"

    asyncio.run(run())
