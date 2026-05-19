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
    native_protocols_json: list[str] = field(default_factory=list)
    adapter_policies_json: list[str] = field(default_factory=list)
    tool_policies_json: dict[str, bool] = field(default_factory=dict)
    protocol_features_json: dict[str, bool] = field(default_factory=dict)
    source_kind: str = "profile_seed"
    source_ref: str | None = None
    stale: bool = False

    def resolved_upstream_model(self) -> str | None:
        return self.upstream_model or self.backend_model

    def _derived_runtime_capabilities(self) -> dict[str, Any]:
        if self.lifecycle_mode == "managed_local" and self.backend_type == "vllm":
            return {
                "native_protocols": ["chat", "responses", "messages"],
                "adapter_policies": [],
                "tool_policies": {
                    "openai_function_tools": True,
                    "anthropic_function_tools": True,
                    "builtin_tools": False,
                },
                "protocol_features": {
                    "stream": self.capabilities.supports_stream,
                    "count_tokens": True,
                    "json_schema": self.capabilities.supports_json_schema,
                    "previous_response_id": True,
                },
            }
        if self.lifecycle_mode == "external":
            return {
                "native_protocols": [self.upstream_protocol],
                "adapter_policies": [],
                "tool_policies": {
                    "openai_function_tools": self.capabilities.supports_function_tools,
                    "anthropic_function_tools": self.capabilities.supports_function_tools,
                    "builtin_tools": self.capabilities.supports_builtin_tools,
                },
                "protocol_features": {
                    "stream": self.capabilities.supports_stream,
                    "count_tokens": self.upstream_protocol == "messages",
                    "json_schema": self.capabilities.supports_json_schema,
                    "previous_response_id": self.capabilities.supports_previous_response_id_native,
                },
            }
        return {
            "native_protocols": [self.upstream_protocol],
            "adapter_policies": [],
            "tool_policies": {
                "openai_function_tools": self.capabilities.supports_function_tools,
                "anthropic_function_tools": self.capabilities.supports_function_tools,
                "builtin_tools": self.capabilities.supports_builtin_tools,
            },
            "protocol_features": {
                "stream": self.capabilities.supports_stream,
                "count_tokens": False,
                "json_schema": self.capabilities.supports_json_schema,
                "previous_response_id": self.capabilities.supports_previous_response_id_native,
            },
        }

    def runtime_capabilities(self) -> dict[str, Any]:
        derived = self._derived_runtime_capabilities()
        return {
            "native_protocols": self.native_protocols_json or derived["native_protocols"],
            "adapter_policies": self.adapter_policies_json or derived["adapter_policies"],
            "tool_policies": {
                **derived["tool_policies"],
                **self.tool_policies_json,
            },
            "protocol_features": {
                **derived["protocol_features"],
                **self.protocol_features_json,
            },
        }

    def recommended_runtime_semantics(self) -> dict[str, Any]:
        derived = self._derived_runtime_capabilities()
        return {
            "native_protocols_json": list(derived["native_protocols"]),
            "adapter_policies_json": list(derived["adapter_policies"]),
            "protocol_features_json": dict(derived["protocol_features"]),
        }


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
        source_kind="profile_seed",
        source_ref=settings.active_backend_profile,
        stale=False,
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
        native_protocols_json=list(row.get("native_protocols_json") or []),
        adapter_policies_json=list(row.get("adapter_policies_json") or []),
        tool_policies_json=dict(row.get("tool_policies_json") or {}),
        protocol_features_json=dict(row.get("protocol_features_json") or {}),
        source_kind=row.get("source_kind", "profile_seed"),
        source_ref=row.get("source_ref"),
        stale=bool(row.get("stale", False)),
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
            **{
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
                "source_kind": route.source_kind,
                "source_ref": route.source_ref,
                "stale": route.stale,
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
            },
            **{
                "native_protocols_json": route.runtime_capabilities()["native_protocols"],
                "adapter_policies_json": route.runtime_capabilities()["adapter_policies"],
                "tool_policies_json": route.runtime_capabilities()["tool_policies"],
                "protocol_features_json": route.runtime_capabilities()["protocol_features"],
                "recommended_runtime_semantics": route.recommended_runtime_semantics(),
            },
        }
        for route in catalog.values()
    ]
