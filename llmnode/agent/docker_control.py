from __future__ import annotations

from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Union

import docker
from docker.errors import APIError, NotFound
from docker.types import DeviceRequest
import httpx


@dataclass(frozen=True)
class VLLMContainerSpec:
    container_name: str
    image_name: str
    model_dir: str
    model_name: str
    host_port: int
    gpu_memory_utilization: float
    tensor_parallel_size: int
    max_model_len: int
    max_num_seqs: int
    shm_size: str
    enable_auto_tool_choice: bool
    reasoning_parser: str
    tool_call_parser: str
    enable_prefix_caching: bool = False
    kv_cache_dtype: str = ""
    speculative_config: str = ""
    speculative_model_dir: str = ""
    disabled_kernels: str = ""
    profiler_config: str = ""
    profiler_host_dir: str = ""

    @property
    def command(self) -> list[str]:
        args = [
            "--model",
            "/model",
            "--served-model-name",
            self.model_name,
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--trust-remote-code",
            "--tensor-parallel-size",
            str(self.tensor_parallel_size),
            "--gpu-memory-utilization",
            str(self.gpu_memory_utilization),
            "--max-model-len",
            str(self.max_model_len),
            "--max-num-seqs",
            str(self.max_num_seqs),
        ]
        if self.enable_auto_tool_choice:
            args.extend(
                [
                    "--reasoning-parser",
                    self.reasoning_parser,
                    "--enable-auto-tool-choice",
                    "--tool-call-parser",
                    self.tool_call_parser,
                ]
            )
        else:
            args.extend(["--reasoning-parser", self.reasoning_parser])
        if self.enable_prefix_caching:
            args.append("--enable-prefix-caching")
        if self.kv_cache_dtype:
            args.extend(["--kv-cache-dtype", self.kv_cache_dtype])
        if self.speculative_config:
            args.extend(["--speculative-config", self.speculative_config])
        if self.profiler_config:
            args.extend(["--profiler-config", self.profiler_config])
        return args

    @property
    def entrypoint(self) -> list[str] | None:
        return None

    @property
    def volumes(self) -> dict[str, dict[str, str]]:
        volumes = {self.model_dir: {"bind": "/model", "mode": "ro"}}
        if self.speculative_model_dir:
            volumes[self.speculative_model_dir] = {"bind": "/draft-model", "mode": "ro"}
        if self.profiler_host_dir:
            volumes[self.profiler_host_dir] = {"bind": "/tmp/vllm-profile", "mode": "rw"}
        return volumes

    @property
    def ports(self) -> dict[str, tuple[str, int]]:
        return {"8000/tcp": ("127.0.0.1", self.host_port)}

    @property
    def environment(self) -> dict[str, str]:
        if not self.disabled_kernels:
            return {}
        return {"VLLM_DISABLED_KERNELS": self.disabled_kernels}

    @property
    def device_requests(self) -> list[DeviceRequest]:
        return [DeviceRequest(count=-1, capabilities=[["gpu"]])]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LlamaCppContainerSpec:
    container_name: str
    image_name: str
    model_dir: str
    model_file: str
    model_name: str
    host_port: int
    n_gpu_layers: int
    ctx_size: int
    n_parallel: int
    shm_size: str
    n_cpu_moe: int = 0
    spec_draft_model_dir: str = ""
    spec_draft_model_file: str = ""
    spec_type: str = ""
    spec_draft_n_max: int = 0
    flash_attention: bool = False
    jinja: bool = False

    @property
    def entrypoint(self) -> list[str] | None:
        return ["/app/llama-server"]

    @property
    def command(self) -> list[str]:
        args = [
            "--model", f"/model/{self.model_file}",
            "--host", "0.0.0.0",
            "--port", "8080",
            "--n-gpu-layers", str(self.n_gpu_layers),
            "--ctx-size", str(self.ctx_size),
            "--parallel", str(self.n_parallel),
        ]
        if self.n_cpu_moe > 0:
            args.extend(["--n-cpu-moe", str(self.n_cpu_moe)])
        if self.spec_draft_model_file:
            args.extend(["--model-draft", f"/draft-model/{self.spec_draft_model_file}"])
        if self.spec_type:
            args.extend(["--spec-type", self.spec_type])
        if self.spec_draft_n_max > 0:
            args.extend(["--spec-draft-n-max", str(self.spec_draft_n_max)])
        if self.flash_attention:
            args.extend(["-fa", "on"])
        if self.jinja:
            args.append("--jinja")
        return args

    @property
    def volumes(self) -> dict[str, dict[str, str]]:
        volumes = {self.model_dir: {"bind": "/model", "mode": "ro"}}
        if self.spec_draft_model_dir:
            volumes[self.spec_draft_model_dir] = {"bind": "/draft-model", "mode": "ro"}
        return volumes

    @property
    def ports(self) -> dict[str, tuple[str, int]]:
        return {"8080/tcp": ("127.0.0.1", self.host_port)}

    @property
    def device_requests(self) -> list[DeviceRequest]:
        return [DeviceRequest(count=-1, capabilities=[["gpu"]])]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SGLangContainerSpec:
    container_name: str
    image_name: str
    model_dir: str
    model_name: str
    host_port: int
    tp_size: int
    mem_fraction_static: float
    max_running_requests: int
    shm_size: str
    reasoning_parser: str
    speculative_algorithm: str = ""
    speculative_draft_model_dir: str = ""
    extra_args: tuple[str, ...] = ()

    @property
    def entrypoint(self) -> list[str] | None:
        return ["/bin/sh", "-c"]

    @property
    def command(self) -> list[str]:
        parts = [
            "pip install -q distro &&",
            "python", "-m", "sglang.launch_server",
            "--model-path", "/model",
            "--served-model-name", self.model_name,
            "--host", "0.0.0.0",
            "--port", "30000",
            "--tp", str(self.tp_size),
            "--mem-fraction-static", str(self.mem_fraction_static),
            "--max-running-requests", str(self.max_running_requests),
            "--trust-remote-code",
        ]
        if self.reasoning_parser:
            parts += ["--reasoning-parser", self.reasoning_parser]
        if self.speculative_algorithm:
            parts += ["--speculative-algorithm", self.speculative_algorithm]
        if self.speculative_draft_model_dir:
            parts += ["--speculative-draft-model-path", "/draft-model"]
        if self.extra_args:
            parts.extend(self.extra_args)
        return [" ".join(parts)]

    @property
    def volumes(self) -> dict[str, dict[str, str]]:
        volumes = {self.model_dir: {"bind": "/model", "mode": "ro"}}
        if self.speculative_draft_model_dir:
            volumes[self.speculative_draft_model_dir] = {"bind": "/draft-model", "mode": "ro"}
        return volumes

    @property
    def ports(self) -> dict[str, tuple[str, int]]:
        return {"30000/tcp": ("127.0.0.1", self.host_port)}

    @property
    def device_requests(self) -> list[DeviceRequest]:
        return [DeviceRequest(count=-1, capabilities=[["gpu"]])]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


AnyContainerSpec = Union[VLLMContainerSpec, LlamaCppContainerSpec, SGLangContainerSpec]


def docker_client() -> docker.DockerClient:
    return docker.from_env()


def _normalized_entrypoint(value: Any) -> list[str] | None:
    if value in (None, "", []):
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _normalized_port_bindings(value: Any) -> dict[str, list[tuple[str, str]]]:
    bindings: dict[str, list[tuple[str, str]]] = {}
    if not isinstance(value, dict):
        return bindings
    for container_port, items in value.items():
        host_ports: list[tuple[str, str]] = []
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("HostPort") is not None:
                    host_ip = str(item.get("HostIp") or "")
                    if host_ip == "0.0.0.0":
                        host_ip = ""
                    host_ports.append((host_ip, str(item["HostPort"])))
        bindings[str(container_port)] = sorted(host_ports)
    return bindings


def _normalized_mount_sources(value: Any) -> dict[str, str]:
    mounts: dict[str, str] = {}
    if not isinstance(value, list):
        return mounts
    for item in value:
        if not isinstance(item, dict):
            continue
        destination = item.get("Destination")
        source = item.get("Source")
        if destination and source:
            mounts[str(destination)] = str(source)
    return mounts


def _normalized_environment(value: Any) -> dict[str, str]:
    environment: dict[str, str] = {}
    if not isinstance(value, list):
        return environment
    for item in value:
        if not isinstance(item, str) or "=" not in item:
            continue
        key, content = item.split("=", 1)
        environment[key] = content
    return environment


def _container_matches_spec(container: Any, spec: AnyContainerSpec) -> bool:
    attrs = getattr(container, "attrs", {}) or {}
    config = attrs.get("Config", {}) if isinstance(attrs, dict) else {}
    host_config = attrs.get("HostConfig", {}) if isinstance(attrs, dict) else {}

    actual_image = str(config.get("Image") or "")
    actual_cmd = [str(item) for item in config.get("Cmd") or []]
    actual_entrypoint = _normalized_entrypoint(config.get("Entrypoint"))
    actual_ports = _normalized_port_bindings(host_config.get("PortBindings"))
    actual_mounts = _normalized_mount_sources(attrs.get("Mounts"))
    actual_environment = _normalized_environment(config.get("Env"))

    expected_ports = {
        str(port): [(str(host_ip), str(host_port))]
        for port, (host_ip, host_port) in spec.ports.items()
    }
    expected_mounts = {
        details["bind"]: str(Path(source).resolve())
        for source, details in spec.volumes.items()
    }
    expected_environment = getattr(spec, "environment", {})

    return (
        actual_image == spec.image_name
        and actual_cmd == spec.command
        and actual_entrypoint == spec.entrypoint
        and actual_ports == expected_ports
        and actual_mounts == expected_mounts
        and all(actual_environment.get(key) == value for key, value in expected_environment.items())
    )


def container_snapshot(spec: AnyContainerSpec) -> dict[str, Any]:
    client = docker_client()
    try:
        container = client.containers.get(spec.container_name)
    except NotFound:
        return {"exists": False, "running": False, "status": "missing", "name": spec.container_name}
    container.reload()
    return {
        "exists": True,
        "running": container.status == "running",
        "status": container.status,
        "name": container.name,
        "image": container.image.tags[0] if getattr(container.image, "tags", []) else None,
        "attrs": container.attrs,
    }


def ensure_container_running(spec: AnyContainerSpec) -> dict[str, Any]:
    client = docker_client()
    try:
        container = client.containers.get(spec.container_name)
        container.reload()
        if not _container_matches_spec(container, spec):
            with suppress(APIError):
                container.stop(timeout=30)
            container.remove(force=True)
            return _run_new_container(client, spec, action="recreated")
        if container.status == "running":
            return {"action": "already_running", "snapshot": container_snapshot(spec)}
        container.start()
        return {"action": "started_existing", "snapshot": container_snapshot(spec)}
    except NotFound:
        return _run_new_container(client, spec, action="started_new")


def _run_new_container(client: docker.DockerClient, spec: AnyContainerSpec, *, action: str) -> dict[str, Any]:
    try:
        kwargs: dict[str, Any] = dict(
            command=spec.command,
            name=spec.container_name,
            detach=True,
            restart_policy={"Name": "unless-stopped"},
            volumes=spec.volumes,
            ports=spec.ports,
            ipc_mode="host",
            shm_size=spec.shm_size,
            device_requests=spec.device_requests,
        )
        if spec.entrypoint is not None:
            kwargs["entrypoint"] = spec.entrypoint
        environment = getattr(spec, "environment", {})
        if environment:
            kwargs["environment"] = environment
        client.containers.run(spec.image_name, **kwargs)
    except APIError as exc:
        raise RuntimeError(f"failed to start container: {exc}") from exc
    return {"action": action, "snapshot": container_snapshot(spec)}


def stop_container(spec: AnyContainerSpec) -> dict[str, Any]:
    client = docker_client()
    try:
        container = client.containers.get(spec.container_name)
    except NotFound:
        return {"action": "missing", "snapshot": {"exists": False, "running": False, "status": "missing"}}
    try:
        container.stop(timeout=30)
    except APIError as exc:
        raise RuntimeError(f"failed to stop vllm container: {exc}") from exc
    return {"action": "stopped", "snapshot": container_snapshot(spec)}


def restart_container(spec: AnyContainerSpec) -> dict[str, Any]:
    client = docker_client()
    try:
        container = client.containers.get(spec.container_name)
        container.reload()
        if container.status == "running":
            container.restart(timeout=30)
        else:
            container.start()
        return {"action": "restarted_existing", "snapshot": container_snapshot(spec)}
    except NotFound:
        return ensure_container_running(spec)


async def backend_health(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{url.rstrip('/')}/v1/models")
        return response.status_code == 200
    except httpx.HTTPError:
        return False


async def llamacpp_health(url: str) -> bool:
    base = url.rstrip('/')
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{base}/v1/models")
            if resp.status_code == 200:
                return True
            resp2 = await client.get(f"{base}/health")
            return resp2.status_code == 200
    except httpx.HTTPError:
        return False
