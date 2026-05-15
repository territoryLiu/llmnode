from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OpenAIResponsesRequest(BaseModel):
    model: str
    input: Any = None
    previous_response_id: str | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any = None
    stream: bool = False
    max_output_tokens: int | None = Field(default=None, ge=1)
    output_format: dict[str, Any] | None = None
    temperature: float | None = None
    top_p: float | None = None

    def input_items(self) -> list[dict[str, Any]]:
        if self.input is None:
            return []
        if isinstance(self.input, str):
            return [{"role": "user", "content": self.input}]
        if isinstance(self.input, dict):
            return [self._normalize_message(self.input)]
        if isinstance(self.input, list):
            return [self._normalize_message(item) for item in self.input]
        raise ValueError("input must be a string, object, or array")

    def to_chat_messages(self, previous_messages: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        messages = list(previous_messages or [])
        messages.extend(self.input_items())
        return messages

    def to_chat_payload(
        self,
        backend_model: str,
        previous_messages: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": backend_model,
            "messages": self.to_chat_messages(previous_messages),
        }
        if self.tools is not None:
            payload["tools"] = self.tools
        if self.tool_choice is not None:
            payload["tool_choice"] = self.tool_choice
        if self.stream:
            payload["stream"] = True
        if self.max_output_tokens is not None:
            payload["max_tokens"] = self.max_output_tokens
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.top_p is not None:
            payload["top_p"] = self.top_p
        response_format = self._to_chat_response_format()
        if response_format is not None:
            payload["response_format"] = response_format
        return payload

    def _normalize_message(self, item: Any) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ValueError("input message items must be objects")
        role = item.get("role")
        if item.get("type") == "message" and role is None:
            role = "user"
        if not isinstance(role, str) or not role.strip():
            raise ValueError("input message role must be a non-empty string")
        if "content" not in item:
            raise ValueError("input message content is required")
        return {
            "role": role.strip(),
            "content": self._normalize_content(item.get("content")),
        }

    def _normalize_content(self, content: Any) -> Any:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts: list[str] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") in {"input_text", "output_text", "text"} and isinstance(block.get("text"), str):
                    text_parts.append(block["text"])
            if text_parts:
                return "".join(text_parts)
        return content

    def _to_chat_response_format(self) -> dict[str, Any] | None:
        if not isinstance(self.output_format, dict):
            return None
        if self.output_format.get("type") != "json_schema":
            return self.output_format
        schema = self.output_format.get("schema")
        if not isinstance(schema, dict):
            return None
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "response",
                "schema": schema,
            },
        }
