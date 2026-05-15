from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class NormalizedRequest:
    client_protocol: str
    model: str
    messages: list[dict[str, Any]]
    system_prompt: Any | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any = None
    stream: bool = False
    max_output_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    response_format: dict[str, Any] | None = None
    previous_response_id: str | None = None
    raw_request: dict[str, Any] | None = None
