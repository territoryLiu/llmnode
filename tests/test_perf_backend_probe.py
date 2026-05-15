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


def test_llamacpp_runtime_sample_allows_missing_kv_cache_percent():
    result = parse_backend_runtime_sample("llama.cpp", "n_ctx=262144\nn_ctx_seq=262144\n")
    assert result["kv_cache_usage_percent"] is None
    assert result["n_ctx"] == 262144
