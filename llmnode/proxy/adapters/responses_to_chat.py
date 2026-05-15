from __future__ import annotations

from typing import Any

from ...models import ModelRoute
from ...protocols.openai_responses import OpenAIResponsesRequest


def build_responses_chat_payload(
    route: ModelRoute,
    payload: OpenAIResponsesRequest,
    previous_messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return payload.to_chat_payload(route.resolved_upstream_model() or payload.model, previous_messages)
