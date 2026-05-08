from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_FILE = PROJECT_ROOT / "config" / "models.yaml"


@dataclass(frozen=True)
class ModelRoute:
    name: str
    display_name: str
    backend_model: str
    backend_type: str = "vllm"
    enabled: bool = True


def load_model_catalog(path: Path | None = None) -> Dict[str, ModelRoute]:
    file_path = path or MODELS_FILE
    if file_path.exists():
        raw = yaml.safe_load(file_path.read_text()) or {}
        items = raw.get("models", [])
    else:
        items = []

    catalog: Dict[str, ModelRoute] = {}
    for item in items:
        route = ModelRoute(
            name=item["name"],
            display_name=item.get("display_name", item["name"]),
            backend_model=item.get("backend_model", item["name"]),
            backend_type=item.get("backend_type", "vllm"),
            enabled=bool(item.get("enabled", True)),
        )
        catalog[route.name] = route

    if not catalog:
        fallback = ModelRoute(
            name="qwen36-35b-a3b",
            display_name="Qwen3.6 35B A3B",
            backend_model="qwen36-35b-a3b",
            backend_type="vllm",
        )
        catalog[fallback.name] = fallback

    return catalog


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
