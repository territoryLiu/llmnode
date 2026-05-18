from __future__ import annotations

from typing import Any

from ...models import ModelRoute
from ...protocols.openai_responses import OpenAIResponsesRequest


def build_responses_messages_payload(
    route: ModelRoute,
    payload: OpenAIResponsesRequest,
    previous_messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    messages = payload.to_chat_messages(previous_messages)
    upstream_payload: dict[str, Any] = {
        "model": route.resolved_upstream_model() or payload.model,
        "messages": messages,
    }
    if payload.tools is not None:
        upstream_payload["tools"] = payload.tools
    if payload.tool_choice is not None:
        upstream_payload["tool_choice"] = payload.tool_choice
    if payload.stream:
        upstream_payload["stream"] = True
    if payload.max_output_tokens is not None:
        upstream_payload["max_tokens"] = payload.max_output_tokens
    if payload.temperature is not None:
        upstream_payload["temperature"] = payload.temperature
    if payload.top_p is not None:
        upstream_payload["top_p"] = payload.top_p
    return upstream_payload
