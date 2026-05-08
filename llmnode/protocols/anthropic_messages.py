from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AnthropicMessage(BaseModel):
    role: str
    content: Any


class AnthropicMessagesRequest(BaseModel):
    model: str
    max_tokens: int = Field(ge=1)
    messages: List[AnthropicMessage]
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Any] = None
    system: Optional[Any] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    stream: Optional[bool] = False

    def to_backend_payload(self, backend_model: str) -> Dict[str, Any]:
        payload = self.model_dump(exclude_none=True)
        payload["model"] = backend_model
        return payload

