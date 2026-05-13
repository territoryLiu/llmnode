from llmnode.agent.docker_control import VLLMContainerSpec, ensure_container_running


class FakeContainer:
    def __init__(self):
        self.status = "exited"
        self.attrs = {
            "Config": {
                "Image": "vllm/vllm-openai:nightly",
                "Cmd": [
                    "--model",
                    "/model",
                    "--served-model-name",
                    "qwen36-35b-a3b-fp8",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "8000",
                    "--trust-remote-code",
                    "--tensor-parallel-size",
                    "1",
                    "--gpu-memory-utilization",
                    "0.65",
                    "--max-model-len",
                    "262144",
                    "--max-num-seqs",
                    "4",
                    "--reasoning-parser",
                    "qwen3",
                    "--enable-auto-tool-choice",
                    "--tool-call-parser",
                    "qwen3_coder",
                ],
                "Entrypoint": None,
            },
            "HostConfig": {
                "PortBindings": {
                    "8000/tcp": [{"HostIp": "", "HostPort": "8000"}],
                },
            },
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": "/proj02/liuheshan/llmnode/models/Qwen/Qwen3.6-35B-A3B-FP8",
                    "Destination": "/model",
                    "Mode": "ro",
                    "RW": False,
                }
            ],
        }
        self.stopped = False
        self.removed = False

    def reload(self):
        return None

    def start(self):
        raise AssertionError("drifted container should not be started directly")

    def stop(self, timeout=30):
        self.stopped = True

    def remove(self, force=False):
        self.removed = True


class FakeContainers:
    def __init__(self, container: FakeContainer):
        self.container = container
        self.run_calls = []

    def get(self, name: str):
        assert name == "qwen36-vllm"
        return self.container

    def run(self, image_name: str, **kwargs):
        self.run_calls.append((image_name, kwargs))
        self.container.status = "running"


class FakeClient:
    def __init__(self, container: FakeContainer):
        self.containers = FakeContainers(container)


def test_ensure_container_running_recreates_drifted_container(monkeypatch):
    spec = VLLMContainerSpec(
        container_name="qwen36-vllm",
        image_name="vllm/vllm-openai:nightly",
        model_dir="/proj02/liuheshan/llmnode/models/Qwen/Qwen3.6-35B-A3B-FP8",
        model_name="qwen36-35b-a3b-fp8",
        host_port=15673,
        gpu_memory_utilization=0.65,
        tensor_parallel_size=1,
        max_model_len=262144,
        max_num_seqs=4,
        shm_size="16g",
        enable_auto_tool_choice=True,
        reasoning_parser="qwen3",
        tool_call_parser="qwen3_coder",
    )
    container = FakeContainer()
    client = FakeClient(container)

    monkeypatch.setattr("llmnode.agent.docker_control.docker_client", lambda: client)
    monkeypatch.setattr(
        "llmnode.agent.docker_control.container_snapshot",
        lambda spec: {"exists": True, "running": True, "name": spec.container_name},
    )

    result = ensure_container_running(spec)

    assert result["action"] == "recreated"
    assert container.stopped is True
    assert container.removed is True
    assert len(client.containers.run_calls) == 1
