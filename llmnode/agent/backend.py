from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .docker_control import (
    LlamaCppContainerSpec,
    SGLangContainerSpec,
    VLLMContainerSpec,
    backend_health,
    llamacpp_health,
    container_snapshot,
    ensure_container_running,
    restart_container,
    stop_container,
)


class BackendDriver(Protocol):
    backend_type: str

    async def health(self, backend_url: str) -> bool: ...

    async def probe(self, backend_url: str, model_name: str) -> dict[str, Any]: ...

    def snapshot(self) -> dict[str, Any]: ...

    def start(self) -> dict[str, Any]: ...

    def stop(self) -> dict[str, Any]: ...

    def restart(self) -> dict[str, Any]: ...


@dataclass
class VLLMBackendDriver:
    spec: VLLMContainerSpec
    backend_type: str = "vllm"

    async def health(self, backend_url: str) -> bool:
        return await backend_health(backend_url)

    async def probe(self, backend_url: str, model_name: str) -> dict[str, Any]:
        import httpx as _httpx
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
            "stream": False,
        }
        async with _httpx.AsyncClient(base_url=backend_url, timeout=30) as client:
            resp = await client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            return {"ok": True, "response": resp.json()}

    def snapshot(self) -> dict[str, Any]:
        return container_snapshot(self.spec)

    def start(self) -> dict[str, Any]:
        return ensure_container_running(self.spec)

    def stop(self) -> dict[str, Any]:
        return stop_container(self.spec)

    def restart(self) -> dict[str, Any]:
        return restart_container(self.spec)


@dataclass
class LlamaCppBackendDriver:
    spec: LlamaCppContainerSpec
    backend_type: str = "llama.cpp"

    async def health(self, backend_url: str) -> bool:
        return await llamacpp_health(backend_url)

    async def probe(self, backend_url: str, model_name: str) -> dict[str, Any]:
        import httpx as _httpx
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
            "stream": False,
        }
        async with _httpx.AsyncClient(base_url=backend_url, timeout=30) as client:
            resp = await client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            return {"ok": True, "response": resp.json()}

    def snapshot(self) -> dict[str, Any]:
        return container_snapshot(self.spec)

    def start(self) -> dict[str, Any]:
        return ensure_container_running(self.spec)

    def stop(self) -> dict[str, Any]:
        return stop_container(self.spec)

    def restart(self) -> dict[str, Any]:
        return restart_container(self.spec)


@dataclass
class SGLangBackendDriver:
    spec: SGLangContainerSpec
    backend_type: str = "sglang"

    async def health(self, backend_url: str) -> bool:
        return await backend_health(backend_url)

    async def probe(self, backend_url: str, model_name: str) -> dict[str, Any]:
        import httpx as _httpx
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
            "stream": False,
        }
        async with _httpx.AsyncClient(base_url=backend_url, timeout=30) as client:
            resp = await client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            return {"ok": True, "response": resp.json()}

    def snapshot(self) -> dict[str, Any]:
        return container_snapshot(self.spec)

    def start(self) -> dict[str, Any]:
        return ensure_container_running(self.spec)

    def stop(self) -> dict[str, Any]:
        return stop_container(self.spec)

    def restart(self) -> dict[str, Any]:
        return restart_container(self.spec)

