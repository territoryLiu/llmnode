from __future__ import annotations

from dataclasses import dataclass

from .backend import VLLMBackendClient


@dataclass
class VLLMClient(VLLMBackendClient):
    pass


def build_messages_request(model: str, prompt: str) -> dict:
    return {
        "model": model,
        "max_tokens": 16,
        "messages": [{"role": "user", "content": prompt}],
    }
