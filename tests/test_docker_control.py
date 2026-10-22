from llmnode.agent.docker_control import SGLangContainerSpec, VLLMContainerSpec, ensure_container_running


class FakeContainer:
    def __init__(self, *, status: str = "exited"):
        self.status = status
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
    assert client.containers.run_calls[0][1]["ports"] == {"8000/tcp": ("127.0.0.1", 15673)}


def test_container_specs_bind_ports_to_loopback():
    from llmnode.agent.docker_control import LlamaCppContainerSpec, SGLangContainerSpec

    assert VLLMContainerSpec(
        container_name="vllm", image_name="image", model_dir="/model", model_name="model",
        host_port=15673, gpu_memory_utilization=0.5, tensor_parallel_size=1,
        max_model_len=1024, max_num_seqs=1, shm_size="1g", enable_auto_tool_choice=False,
        reasoning_parser="", tool_call_parser="",
    ).ports == {"8000/tcp": ("127.0.0.1", 15673)}
    assert LlamaCppContainerSpec(
        container_name="llama", image_name="image", model_dir="/model", model_file="model.gguf",
        model_name="model", host_port=15674, n_gpu_layers=1, ctx_size=1024, n_parallel=1,
        shm_size="1g",
    ).ports == {"8080/tcp": ("127.0.0.1", 15674)}
    assert SGLangContainerSpec(
        container_name="sglang", image_name="image", model_dir="/model", model_name="model",
        host_port=15675, tp_size=1, mem_fraction_static=0.5, max_running_requests=1,
        shm_size="1g", reasoning_parser="",
    ).ports == {"30000/tcp": ("127.0.0.1", 15675)}


def test_llamacpp_container_spec_builds_dspark_cpu_offload_command():
    from llmnode.agent.docker_control import LlamaCppContainerSpec

    spec = LlamaCppContainerSpec(
        container_name="llama", image_name="image", model_dir="/target",
        model_file="target.gguf", model_name="model", host_port=15674,
        n_gpu_layers=16, ctx_size=16384, n_parallel=1, shm_size="16g",
        n_cpu_moe=999,
        spec_draft_model_dir="/dspark", spec_draft_model_file="dspark.gguf",
        spec_type="draft-dspark", spec_draft_n_max=3,
        flash_attention=True, jinja=True,
    )

    assert spec.command == [
        "--model", "/model/target.gguf", "--host", "0.0.0.0", "--port", "8080",
        "--n-gpu-layers", "16", "--ctx-size", "16384", "--parallel", "1",
        "--n-cpu-moe", "999", "--model-draft", "/draft-model/dspark.gguf",
        "--spec-type", "draft-dspark", "--spec-draft-n-max", "3",
        "-fa", "on", "--jinja",
    ]
    assert spec.volumes == {
        "/target": {"bind": "/model", "mode": "ro"},
        "/dspark": {"bind": "/draft-model", "mode": "ro"},
    }


def test_ensure_container_running_recreates_running_drifted_container(monkeypatch):
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
    container = FakeContainer(status="running")
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


def test_vllm_container_spec_supports_profiler_volume():
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
        profiler_config='{"profiler":"torch","torch_profiler_dir":"/tmp/vllm-profile"}',
        profiler_host_dir="/proj02/liuheshan/llmnode/runtime/data/profiles/stage4",
    )

    assert spec.command[-2:] == [
        "--profiler-config",
        '{"profiler":"torch","torch_profiler_dir":"/tmp/vllm-profile"}',
    ]
    assert spec.volumes["/proj02/liuheshan/llmnode/runtime/data/profiles/stage4"] == {
        "bind": "/tmp/vllm-profile",
        "mode": "rw",
    }


def test_vllm_container_spec_supports_kv_cache_dtype():
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
        kv_cache_dtype="fp8",
    )

    assert "--kv-cache-dtype" in spec.command
    assert spec.command[spec.command.index("--kv-cache-dtype") + 1] == "fp8"


def test_vllm_container_spec_supports_prefix_caching():
    spec = VLLMContainerSpec(
        container_name="qwen38-vllm",
        image_name="vllm/vllm-openai:nightly",
        model_dir="/proj02/liuheshan/llmnode/models/Qwen/Qwen3.8-27B-AWQ-INT4",
        model_name="qwen38-27b-awq-int4",
        host_port=15673,
        gpu_memory_utilization=0.55,
        tensor_parallel_size=1,
        max_model_len=262144,
        max_num_seqs=4,
        shm_size="16g",
        enable_auto_tool_choice=True,
        reasoning_parser="qwen3",
        tool_call_parser="qwen3_coder",
        enable_prefix_caching=True,
    )

    assert "--enable-prefix-caching" in spec.command


def test_vllm_container_spec_supports_mtp_speculative_config():
    speculative_config = '{"method":"mtp","num_speculative_tokens":1}'
    spec = VLLMContainerSpec(
        container_name="qwen38-vllm",
        image_name="vllm/vllm-openai:nightly",
        model_dir="/proj02/liuheshan/llmnode/models/Qwen/Qwen3.8-27B-AWQ-INT4",
        model_name="qwen38-27b-awq-int4",
        host_port=15673,
        gpu_memory_utilization=0.55,
        tensor_parallel_size=1,
        max_model_len=262144,
        max_num_seqs=4,
        shm_size="16g",
        enable_auto_tool_choice=True,
        reasoning_parser="qwen3",
        tool_call_parser="qwen3_coder",
        speculative_config=speculative_config,
    )

    assert "--speculative-config" in spec.command
    assert spec.command[spec.command.index("--speculative-config") + 1] == speculative_config


def test_vllm_container_spec_mounts_speculative_model_read_only():
    spec = VLLMContainerSpec(
        container_name="qwen38-vllm",
        image_name="vllm/vllm-openai:nightly",
        model_dir="/models/Qwen3.8-27B-AWQ-INT4",
        model_name="qwen38-27b-awq-int4",
        host_port=15673,
        gpu_memory_utilization=0.55,
        tensor_parallel_size=1,
        max_model_len=262144,
        max_num_seqs=4,
        shm_size="16g",
        enable_auto_tool_choice=True,
        reasoning_parser="qwen3",
        tool_call_parser="qwen3_coder",
        speculative_config='{"method":"dflash","model":"/draft-model","num_speculative_tokens":7}',
        speculative_model_dir="/models/Qwen3.8-27B-DFlash2",
    )

    assert spec.volumes["/models/Qwen3.8-27B-DFlash2"] == {
        "bind": "/draft-model",
        "mode": "ro",
    }

def test_sglang_container_spec_supports_dflash2_draft_model():
    spec = SGLangContainerSpec(
        container_name="sglang", image_name="image", model_dir="/model",
        model_name="model", host_port=15673, tp_size=1,
        mem_fraction_static=0.7, max_running_requests=4, shm_size="16g",
        reasoning_parser="qwen3", speculative_algorithm="DFLASH",
        speculative_draft_model_dir="/draft",
        extra_args=("--speculative-num-draft-tokens", "8"),
    )
    command = " ".join(spec.command).split()

    assert "--speculative-algorithm" in command
    assert command[command.index("--speculative-algorithm") + 1] == "DFLASH"
    assert command[command.index("--speculative-draft-model-path") + 1] == "/draft-model"
    assert command[-2:] == ["--speculative-num-draft-tokens", "8"]
    assert spec.volumes["/draft"] == {"bind": "/draft-model", "mode": "ro"}


def test_vllm_container_spec_exposes_disabled_kernels_environment():
    spec = VLLMContainerSpec(
        container_name="qwen38-vllm",
        image_name="vllm/vllm-openai:nightly",
        model_dir="/models/Qwen3.8-27B-NVFP4",
        model_name="qwen38-27b-nvfp4",
        host_port=15673,
        gpu_memory_utilization=0.55,
        tensor_parallel_size=1,
        max_model_len=262144,
        max_num_seqs=4,
        shm_size="16g",
        enable_auto_tool_choice=True,
        reasoning_parser="qwen3",
        tool_call_parser="qwen3_coder",
        disabled_kernels="HummingFP8ScaledMMLinearKernel",
    )

    assert spec.environment == {
        "VLLM_DISABLED_KERNELS": "HummingFP8ScaledMMLinearKernel"
    }
