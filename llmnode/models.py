from dataclasses import dataclass, field
from typing import Any, Dict

from .config import load_settings


@dataclass(frozen=True)
class ModelCapabilities:
    supports_responses: bool = False
    supports_chat: bool = True
    supports_messages: bool = False
    supports_stream: bool = True
    supports_function_tools: bool = True
    supports_builtin_tools: bool = False
    supports_previous_response_id_native: bool = False
    supports_json_schema: bool = False


@dataclass(frozen=True)
class ModelRoute:
    name: str
    display_name: str
    backend_model: str | None = None
    backend_type: str | None = "vllm"
    enabled: bool = True
    lifecycle_mode: str = "managed_local"
    upstream_protocol: str = "chat"
    upstream_base_url: str | None = None
    upstream_model: str | None = None
    upstream_auth_kind: str = "none"
    upstream_auth_ref: str | None = None
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)

    def resolved_upstream_model(self) -> str | None:
        return self.upstream_model or self.backend_model


def load_model_catalog(path=None) -> Dict[str, ModelRoute]:
    settings = load_settings(path)
    route = ModelRoute(
        name=settings.vllm.model_name,
        display_name=settings.vllm.display_name,
        backend_model=settings.vllm.model_name,
        backend_type=settings.vllm.backend_type,
        enabled=settings.vllm.enabled,
        lifecycle_mode="managed_local",
        upstream_protocol="chat",
        upstream_base_url=settings.gateway.backend_url,
        upstream_model=settings.vllm.model_name,
        upstream_auth_kind="none",
    )
    return {route.name: route}


def model_route_from_row(row: dict[str, Any]) -> ModelRoute:
    capabilities_payload = row.get("capabilities_json") or {}
    if isinstance(capabilities_payload, ModelCapabilities):
        capabilities = capabilities_payload
    else:
        capabilities = ModelCapabilities(**capabilities_payload)
    return ModelRoute(
        name=row["name"],
        display_name=row["display_name"],
        backend_model=row.get("backend_model"),
        backend_type=row.get("backend_type"),
        enabled=bool(row.get("enabled", True)),
        lifecycle_mode=row.get("lifecycle_mode", "managed_local"),
        upstream_protocol=row.get("upstream_protocol", "chat"),
        upstream_base_url=row.get("upstream_base_url"),
        upstream_model=row.get("upstream_model"),
        upstream_auth_kind=row.get("upstream_auth_kind", "none"),
        upstream_auth_ref=row.get("upstream_auth_ref"),
        capabilities=capabilities,
    )


def logical_models_for_api(catalog: Dict[str, ModelRoute]) -> list[dict]:
    return [
        {
            "id": route.name,
            "object": "model",
            "created": 1677610602,
            "owned_by": "llmnode",
        }
        for route in catalog.values()
        if route.enabled
    ]


def model_routes_for_admin(catalog: Dict[str, ModelRoute]) -> list[dict]:
    return [
        {
            "name": route.name,
            "display_name": route.display_name,
            "backend_model": route.backend_model,
            "backend_type": route.backend_type,
            "enabled": route.enabled,
            "lifecycle_mode": route.lifecycle_mode,
            "upstream_protocol": route.upstream_protocol,
            "upstream_base_url": route.upstream_base_url,
            "upstream_model": route.resolved_upstream_model(),
            "upstream_auth_kind": route.upstream_auth_kind,
            "upstream_auth_ref": route.upstream_auth_ref,
            "capabilities_json": {
                "supports_responses": route.capabilities.supports_responses,
                "supports_chat": route.capabilities.supports_chat,
                "supports_messages": route.capabilities.supports_messages,
                "supports_stream": route.capabilities.supports_stream,
                "supports_function_tools": route.capabilities.supports_function_tools,
                "supports_builtin_tools": route.capabilities.supports_builtin_tools,
                "supports_previous_response_id_native": route.capabilities.supports_previous_response_id_native,
                "supports_json_schema": route.capabilities.supports_json_schema,
            },
        }
        for route in catalog.values()
    ]
