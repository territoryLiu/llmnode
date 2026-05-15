from __future__ import annotations

import re
from typing import Any


def _search_group(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        return None
    return match.group(1)


def _search_int(text: str, pattern: str) -> int | None:
    value = _search_group(text, pattern)
    if value is None:
        return None
    return int(value.replace(",", ""))


def _search_float(text: str, pattern: str) -> float | None:
    value = _search_group(text, pattern)
    if value is None:
        return None
    return float(value)


def parse_vllm_startup_metrics(text: str) -> dict[str, Any]:
    return {
        "available_kv_cache_memory": _search_group(text, r"Available KV cache memory:\s*([0-9.]+\s*GiB)"),
        "gpu_kv_cache_size_tokens": _search_int(text, r"GPU KV cache size:\s*([0-9,]+)\s*tokens"),
        "max_concurrency_for_256k": _search_float(
            text,
            r"Maximum concurrency for 262,144 tokens per request:\s*([0-9.]+)x",
        ),
    }


def parse_backend_runtime_sample(backend_type: str, text: str) -> dict[str, Any]:
    if backend_type == "vllm":
        return {
            "kv_cache_usage_percent": _search_float(text, r"GPU KV cache usage:\s*([0-9.]+)%"),
            "prompt_throughput_tokens_per_s": _search_float(
                text,
                r"Avg prompt throughput:\s*([0-9.]+)\s*tokens/s",
            ),
            "generation_throughput_tokens_per_s": _search_float(
                text,
                r"Avg generation throughput:\s*([0-9.]+)\s*tokens/s",
            ),
        }
    if backend_type == "llama.cpp":
        return {
            "kv_cache_usage_percent": None,
            "n_ctx": _search_int(text, r"n_ctx=([0-9]+)"),
            "n_ctx_seq": _search_int(text, r"n_ctx_seq=([0-9]+)"),
        }
    return {
        "kv_cache_usage_percent": None,
        "kv_cache_allocated_tokens": _search_int(text, r"KV Cache is allocated\. #tokens:\s*([0-9,]+)"),
    }
