from llmnode.proxy.vllm_client import build_messages_request


def test_build_messages_request_uses_local_backend():
    payload = build_messages_request("qwen36-35b-a3b", "hello")
    assert payload["model"] == "qwen36-35b-a3b"
