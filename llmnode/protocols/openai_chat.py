from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class OpenAIChatMessage(BaseModel):
    role: str
    content: Any


class OpenAIChatCompletionsRequest(BaseModel):
    model: str
    messages: List[OpenAIChatMessage]
    max_tokens: Optional[int] = Field(default=None, ge=1)
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Any] = None
    stream: Optional[bool] = False

    def to_backend_payload(self, backend_model: str) -> Dict[str, Any]:
        payload = self.model_dump(exclude_none=True)
        payload["model"] = backend_model
        return payload

