from llmnode.perf.probe_backend import parse_backend_runtime_sample, parse_vllm_startup_metrics


def test_parse_vllm_startup_metrics_extracts_kv_capacity():
    text = """
    Available KV cache memory: 20.5 GiB
    GPU KV cache size: 83,888 tokens
    Maximum concurrency for 262,144 tokens per request: 1.27x
    """
    result = parse_vllm_startup_metrics(text)
    assert result["available_kv_cache_memory"] == "20.5 GiB"
    assert result["gpu_kv_cache_size_tokens"] == 83888
    assert result["max_concurrency_for_256k"] == 1.27


def test_parse_vllm_kv_shortage_error():
    logs = """
    Model loading took 24.05 GiB memory
    Available KV cache memory: 13.42 GiB
    ValueError: The model's max seq len (262144) is larger than the maximum number of tokens that can be stored in KV cache (217168).
    Try increasing `gpu_memory_utilization` or decreasing `max_model_len`.
    """

    metrics = parse_vllm_startup_metrics(logs)

    assert metrics["model_weight_memory_gib"] == 24.05
    assert metrics["available_kv_cache_memory_gib"] == 13.42
    assert metrics["startup_error_kind"] == "kv_cache_too_small"
    assert metrics["requested_max_model_len"] == 262144
    assert metrics["suggested_max_model_len"] == 217168


def test_llamacpp_runtime_sample_allows_missing_kv_cache_percent():
    result = parse_backend_runtime_sample("llama.cpp", "n_ctx=262144\nn_ctx_seq=262144\n")
    assert result["kv_cache_usage_percent"] is None
    assert result["n_ctx"] == 262144
