import asyncio
from unittest.mock import patch

import httpx
from fastapi import HTTPException

from llmnode.api.app import create_app
from llmnode.config import load_settings
from llmnode.proxy.vllm_client import VLLMClient
from llmnode.security import hash_api_key
from llmnode.storage.db import create_api_key
from llmnode.storage.db import write_agent_event


class FakeClient(VLLMClient):
    def __init__(self):
        super().__init__(base_url="http://fake")

    async def health(self) -> bool:
        return True

    async def post_json(self, path, payload):
        return {"path": path, "model": payload["model"]}


class FakeRestartClient:
    def __init__(self, response: httpx.Response | None = None, error: Exception | None = None):
        self._response = response
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url: str):
        if self._error is not None:
            raise self._error
        assert url.endswith("/manage/restart")
        return self._response


class FailingHealthClient(VLLMClient):
    def __init__(self, error: Exception):
        super().__init__(base_url="http://fake")
        self._error = error

    async def health(self) -> bool:
        raise self._error


TEST_MODEL = load_settings().vllm.model_name


def seed_admin_key(app, secret: str = "sk-admin-test") -> str:
    create_api_key(
        app.state.db,
        name=f"admin-{secret}",
        key_hash=hash_api_key(secret),
        scopes=["admin"],
    )
    return secret


def test_admin_events_endpoint_returns_rows():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        admin_secret = seed_admin_key(app)
        write_agent_event(app.state.db, "ready", "backend healthy")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/admin/events", headers={"Authorization": f"Bearer {admin_secret}"})
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["events"][0]["status"] == "ready"

    asyncio.run(run())


def test_admin_logs_alias_matches_request_logs():
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
                    "model": TEST_MODEL,
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            logs_resp = await client.get("/admin/logs", headers={"Authorization": f"Bearer {admin_secret}"})
            request_logs_resp = await client.get("/admin/request-logs", headers={"Authorization": f"Bearer {admin_secret}"})
            assert logs_resp.status_code == 200
            assert logs_resp.json()["logs"] == request_logs_resp.json()["logs"]

    asyncio.run(run())


def test_admin_request_logs_support_pagination_and_time_filters():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        admin_secret = seed_admin_key(app)
        app.state.db.execute(
            """
            INSERT INTO request_logs(
                request_id, model_name, status, protocol, error_message, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?)
            """,
            (
                "req-old",
                "demo",
                "ok",
                "openai",
                None,
                "2026-05-14 09:00:00",
                "req-new",
                "demo",
                "ok",
                "openai",
                None,
                "2026-05-15 09:00:00",
            ),
        )
        app.state.db.commit()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            filtered = await client.get(
                "/admin/request-logs?limit=1&offset=0&date_from=2026-05-15T00:00:00&date_to=2026-05-15T23:59:59",
                headers={"Authorization": f"Bearer {admin_secret}"},
            )
            assert filtered.status_code == 200
            payload = filtered.json()
            assert payload["total"] == 1
            assert len(payload["logs"]) == 1
            assert payload["logs"][0]["request_id"] == "req-new"

            paged = await client.get(
                "/admin/request-logs?limit=1&offset=1",
                headers={"Authorization": f"Bearer {admin_secret}"},
            )
            assert paged.status_code == 200
            assert paged.json()["logs"][0]["request_id"] == "req-old"

    asyncio.run(run())


def test_admin_request_logs_support_status_query_and_csv_export():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        admin_secret = seed_admin_key(app)
        app.state.db.execute(
            """
            INSERT INTO request_logs(
                request_id, model_name, status, protocol, error_message, created_at, auth_source, client_ip, user_agent, rejection_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "req-ok",
                "demo",
                "ok",
                "openai",
                None,
                "2026-05-15 09:00:00",
                "db",
                "127.0.0.1",
                "Mozilla/5.0",
                None,
                "req-error",
                "demo",
                "error",
                "openai",
                "backend down",
                "2026-05-15 10:00:00",
                "db",
                "127.0.0.2",
                "curl/8.0",
                "backend_error",
            ),
        )
        app.state.db.commit()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            filtered = await client.get(
                "/admin/request-logs?status=error&query=curl",
                headers={"Authorization": f"Bearer {admin_secret}"},
            )
            assert filtered.status_code == 200
            payload = filtered.json()
            assert payload["total"] == 1
            assert payload["logs"][0]["request_id"] == "req-error"

            exported = await client.get(
                "/admin/request-logs/export?status=error&query=curl",
                headers={"Authorization": f"Bearer {admin_secret}"},
            )
            assert exported.status_code == 200
            assert exported.headers["content-type"].startswith("text/csv")
            assert "req-error" in exported.text
            assert "req-ok" not in exported.text

    asyncio.run(run())


def test_admin_request_log_detail_merges_log_and_metric_views():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        admin_secret = seed_admin_key(app)
        app.state.db.execute(
            """
            INSERT INTO request_logs(
                request_id, model_name, status, protocol, error_message, created_at, api_key_id, auth_source, client_ip, user_agent, rejection_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "req-detail",
                "demo-model",
                "ok",
                "openai",
                None,
                "2026-05-15 10:00:00",
                7,
                "db",
                "127.0.0.1",
                "Mozilla/5.0",
                None,
            ),
        )
        app.state.db.execute(
            """
            INSERT INTO request_metrics(
                request_id, model_name, protocol, status, latency_ms, prompt_tokens,
                completion_tokens, total_tokens, tokens_per_second, started_at, finished_at,
                backend_type, api_key_id, cache_creation_tokens, cache_read_tokens, cache_miss_tokens,
                error_code, status_detail
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "req-detail",
                "demo-model",
                "openai",
                "ok",
                1234.0,
                100,
                20,
                120,
                16.2,
                "2026-05-15T10:00:00+00:00",
                "2026-05-15T10:00:01+00:00",
                "vllm",
                7,
                5,
                6,
                7,
                None,
                "completed",
            ),
        )
        app.state.db.commit()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get(
                "/admin/request-logs/req-detail",
                headers={"Authorization": f"Bearer {admin_secret}"},
            )
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["request_id"] == "req-detail"
            assert payload["log"]["auth_source"] == "db"
            assert payload["metrics"]["backend_type"] == "vllm"
            assert payload["metrics"]["prompt_tokens"] == 100
            assert payload["metrics"]["cache_read_tokens"] == 6

    asyncio.run(run())


def test_admin_restart_service_returns_accepted_payload():
    async def run():
        app = create_app()
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)

        async def fake_restart():
            return {
                "accepted": True,
                "service": "backend",
                "action": "restart",
                "agent_status": "recovering",
            }

        app.state.restart_agent_backend = fake_restart
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post("/admin/services/restart", headers={"Authorization": f"Bearer {admin_secret}"})
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["accepted"] is True
            assert payload["service"] == "backend"
            assert payload["action"] == "restart"
            assert payload["agent_status"] == "recovering"

    asyncio.run(run())


def test_admin_restart_service_returns_503_when_agent_is_unreachable():
    async def run():
        app = create_app()
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)

        async def fake_restart():
            raise HTTPException(status_code=503, detail="agent control unavailable")

        app.state.restart_agent_backend = fake_restart
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post("/admin/services/restart", headers={"Authorization": f"Bearer {admin_secret}"})
            assert resp.status_code == 503
            assert resp.json()["detail"] == "agent control unavailable"

    asyncio.run(run())


def test_restart_agent_backend_helper_maps_connect_error_to_503():
    async def run():
        app = create_app()
        with patch(
            "llmnode.api.app.httpx.AsyncClient",
            return_value=FakeRestartClient(error=httpx.ConnectError("boom")),
        ):
            try:
                await app.state.restart_agent_backend()
            except HTTPException as exc:
                assert exc.status_code == 503
                assert exc.detail == "agent control unavailable"
            else:
                raise AssertionError("expected HTTPException")

    asyncio.run(run())


def test_admin_status_degrades_when_backend_health_check_raises():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FailingHealthClient(httpx.ReadError("backend down"))
        admin_secret = seed_admin_key(app)
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/admin/status", headers={"Authorization": f"Bearer {admin_secret}"})
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["backend_ready"] is False
            assert payload["backend_error"] == "ReadError: backend down"

    asyncio.run(run())


def test_admin_status_includes_agent_container_snapshot_when_available():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        admin_secret = seed_admin_key(app)

        async def fake_fetch_agent_state():
            return {
                "status": "ready",
                "backend_ready": True,
                "http_ready": True,
                "inference_ready": True,
                "retry_after_seconds": None,
                "failure_count": 0,
                "checked_at": "2026-05-09T00:00:00Z",
            }

        async def fake_run_sync(fn, *args, **kwargs):
            return {
                "exists": True,
                "running": True,
                "status": "running",
                "name": "qwen36-vllm",
            }

        class FakeDriver:
            def snapshot(self):
                return {}

        app.state.fetch_agent_state = fake_fetch_agent_state
        app.state.run_sync = fake_run_sync
        app.state.backend_driver = FakeDriver()
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/admin/status", headers={"Authorization": f"Bearer {admin_secret}"})
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["agent_state"]["status"] == "ready"
            assert payload["agent_state"]["http_ready"] is True
            assert payload["backend_container"]["running"] is True
            assert payload["backend_container"]["name"] == "qwen36-vllm"

    asyncio.run(run())
