from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, Protocol

import httpx


class BackendClient(Protocol):
    backend_type: str

    async def post_json(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]: ...

    async def health(self) -> bool: ...

    async def stream_bytes(self, path: str, payload: Dict[str, Any]) -> AsyncIterator[bytes]: ...


@dataclass
class VLLMBackendClient:
    base_url: str
    backend_type: str = "vllm"
    request_timeout_seconds: int = 300
    health_timeout_seconds: int = 10

    async def post_json(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.request_timeout_seconds) as client:
            response = await client.post(path, json=payload)
            response.raise_for_status()
            return response.json()

    async def health(self) -> bool:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.health_timeout_seconds) as client:
            response = await client.get("/v1/models")
            return response.status_code == 200

    async def stream_bytes(self, path: str, payload: Dict[str, Any]) -> AsyncIterator[bytes]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=None) as client:
            async with client.stream("POST", path, json=payload) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
