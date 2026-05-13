from dataclasses import dataclass
from typing import Dict

from .config import load_settings


@dataclass(frozen=True)
class ModelRoute:
    name: str
    display_name: str
    backend_model: str
    backend_type: str = "vllm"
    enabled: bool = True


def load_model_catalog(path=None) -> Dict[str, ModelRoute]:
    settings = load_settings(path)
    route = ModelRoute(
        name=settings.vllm.model_name,
        display_name=settings.vllm.display_name,
        backend_model=settings.vllm.model_name,
        backend_type=settings.vllm.backend_type,
        enabled=settings.vllm.enabled,
    )
    return {route.name: route}


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
        }
        for route in catalog.values()
    ]
