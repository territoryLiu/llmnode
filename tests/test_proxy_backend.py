import asyncio

import httpx

from llmnode.proxy.backend import VLLMBackendClient, stream_bytes_from


def test_external_stream_uses_bounded_read_timeout(monkeypatch):
    captured: dict[str, httpx.Timeout] = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        async def aiter_bytes(self):
            yield b"data"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    class FakeClient:
        def __init__(self, *, base_url, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def stream(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("llmnode.proxy.backend.httpx.AsyncClient", FakeClient)

    async def run():
        return [chunk async for chunk in stream_bytes_from("http://upstream", "/v1/responses", {}, timeout_seconds=123)]

    assert asyncio.run(run()) == [b"data"]
    assert captured["timeout"].read == 123
    assert captured["timeout"].connect == 10.0


def test_managed_stream_uses_configured_idle_timeout(monkeypatch):
    captured: dict[str, httpx.Timeout] = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        async def aiter_bytes(self):
            yield b"data"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    class FakeClient:
        def __init__(self, *, base_url, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def stream(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("llmnode.proxy.backend.httpx.AsyncClient", FakeClient)
    client = VLLMBackendClient("http://backend", request_timeout_seconds=234, health_timeout_seconds=11)

    async def run():
        return [chunk async for chunk in client.stream_bytes("/v1/chat/completions", {})]

    assert asyncio.run(run()) == [b"data"]
    assert captured["timeout"].read == 234
    assert captured["timeout"].connect == 11
