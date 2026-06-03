from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from itertools import product
from typing import Any
from typing import Literal


PerfRunStatus = Literal[
    "queued",
    "running",
    "completed",
    "completed_with_errors",
    "failed",
    "cancel_requested",
    "cancelled",
]

PerfPointStatus = Literal[
    "pending",
    "starting",
    "startup_failed",
    "healthy",
    "benchmarking",
    "benchmark_failed",
    "completed",
    "cancelled",
]

SUPPORTED_MATRIX_KEYS = ("gpu_memory_utilization", "max_model_len", "max_num_seqs")


@dataclass
class PerfRunRequest:
    profile: str
    targets: list[int]
    max_tokens: int = 64
    warmup_runs: int = 1
    measure_runs: int = 3
    sample_interval: float = 1.0
    concurrency: int = 1
    restart_backend: bool = True
    matrix: dict[str, list[Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.profile.strip():
            raise ValueError("profile must not be empty")
        if not self.targets:
            raise ValueError("targets must not be empty")
        if any(int(target) <= 0 for target in self.targets):
            raise ValueError("targets must be positive")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if self.warmup_runs < 0:
            raise ValueError("warmup_runs must be non-negative")
        if self.measure_runs <= 0:
            raise ValueError("measure_runs must be positive")
        if self.sample_interval <= 0:
            raise ValueError("sample_interval must be positive")
        if self.concurrency <= 0:
            raise ValueError("concurrency must be positive")
        for key, values in self.matrix.items():
            if key not in SUPPORTED_MATRIX_KEYS:
                raise ValueError(f"unsupported matrix key: {key}")
            if not values:
                raise ValueError(f"matrix key {key} must contain at least one value")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PerfMatrixPoint:
    point_id: str
    profile: str
    overrides: dict[str, Any]
    status: PerfPointStatus = "pending"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def expand_matrix(request: PerfRunRequest) -> list[PerfMatrixPoint]:
    if not request.matrix:
        return [PerfMatrixPoint(point_id="point-001", profile=request.profile, overrides={})]

    keys = [key for key in SUPPORTED_MATRIX_KEYS if key in request.matrix]
    points: list[PerfMatrixPoint] = []
    for index, values in enumerate(product(*(request.matrix[key] for key in keys)), start=1):
        overrides = {key: value for key, value in zip(keys, values)}
        points.append(
            PerfMatrixPoint(
                point_id=f"point-{index:03d}",
                profile=request.profile,
                overrides=overrides,
            )
        )
    return points
