from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

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
        return args

    @property
    def volumes(self) -> dict[str, dict[str, str]]:
        return {self.model_dir: {"bind": "/model", "mode": "ro"}}

    @property
    def ports(self) -> dict[str, int]:
        return {"8000/tcp": self.host_port}

    @property
    def device_requests(self) -> list[DeviceRequest]:
        return [DeviceRequest(count=-1, capabilities=[["gpu"]])]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def docker_client() -> docker.DockerClient:
    return docker.from_env()


def container_snapshot(spec: VLLMContainerSpec) -> dict[str, Any]:
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


def ensure_container_running(spec: VLLMContainerSpec) -> dict[str, Any]:
    client = docker_client()
    try:
        container = client.containers.get(spec.container_name)
        container.reload()
        if container.status != "running":
            container.start()
        return {"action": "started_existing", "snapshot": container_snapshot(spec)}
    except NotFound:
        try:
            client.containers.run(
                spec.image_name,
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
        except APIError as exc:
            raise RuntimeError(f"failed to start vllm container: {exc}") from exc
        return {"action": "started_new", "snapshot": container_snapshot(spec)}


def stop_container(spec: VLLMContainerSpec) -> dict[str, Any]:
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


def restart_container(spec: VLLMContainerSpec) -> dict[str, Any]:
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
