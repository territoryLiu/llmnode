import asyncio
from unittest.mock import patch

import httpx
from fastapi import HTTPException

from llmnode.api.app import create_app
from llmnode.proxy.vllm_client import VLLMClient
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


def test_admin_events_endpoint_returns_rows():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        write_agent_event(app.state.db, "ready", "backend healthy")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/admin/events", headers={"Authorization": "Bearer dev-key"})
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["events"][0]["status"] == "ready"

    asyncio.run(run())


def test_admin_logs_alias_matches_request_logs():
    async def run():
        app = create_app()
        app.state.ctx.backend_client = FakeClient()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer dev-key"},
                json={
                    "model": "claude-sonnet-4-5-20250929",
                    "messages": [{"role": "user", "content": "hello"}],
                    "max_tokens": 16,
                },
            )
            logs_resp = await client.get("/admin/logs", headers={"Authorization": "Bearer dev-key"})
            request_logs_resp = await client.get("/admin/request-logs", headers={"Authorization": "Bearer dev-key"})
            assert logs_resp.status_code == 200
            assert logs_resp.json()["logs"] == request_logs_resp.json()["logs"]

    asyncio.run(run())


def test_admin_restart_service_returns_accepted_payload():
    async def run():
        app = create_app()
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
            resp = await client.post("/admin/services/restart", headers={"Authorization": "Bearer dev-key"})
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
        transport = httpx.ASGITransport(app=app)

        async def fake_restart():
            raise HTTPException(status_code=503, detail="agent control unavailable")

        app.state.restart_agent_backend = fake_restart
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post("/admin/services/restart", headers={"Authorization": "Bearer dev-key"})
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
