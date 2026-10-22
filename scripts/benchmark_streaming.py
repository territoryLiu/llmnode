"""Streaming latency benchmark: TTFT, prefill, decode, TPOT split.

Usage:
    python scripts/benchmark_streaming.py --profile vllm_qwen36-27b-awq-int4 --targets 16384 65536 --max-tokens 512
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llmnode.perf.benchmark import run_streaming_benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Streaming latency benchmark: measures TTFT, prefill, decode, TPOT split."
    )
    parser.add_argument(
        "--targets",
        nargs="*",
        type=int,
        default=[16384, 65536],
        help="Target prompt token counts (default: 16384 65536 = 16K 64K).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=512,
        help="Max output tokens per request (default: 512).",
    )
    parser.add_argument(
        "--force-output-tokens",
        action="store_true",
        help="Force generation to max-tokens with min_tokens and ignore_eos.",
    )
    parser.add_argument(
        "--sample-interval",
        type=float,
        default=1.0,
        help="GPU/backend sampling interval in seconds (default: 1.0).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        help="Output directory for benchmark results.",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default="",
        help="Backend profile name (e.g. vllm_qwen36-27b-awq-int4).",
    )
    parser.add_argument(
        "--warmup-runs",
        type=int,
        default=1,
        help="Number of warmup runs before measurement (default: 1).",
    )
    parser.add_argument(
        "--measure-runs",
        type=int,
        default=3,
        help="Number of measurement runs (default: 3).",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Concurrent requests per measured batch (default: 1).",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    path = run_streaming_benchmark(
        targets=args.targets,
        max_tokens=args.max_tokens,
        force_output_tokens=args.force_output_tokens,
        sample_interval=args.sample_interval,
        output_dir=args.output_dir,
        profile=args.profile,
        warmup_runs=args.warmup_runs,
        measure_runs=args.measure_runs,
        concurrency=max(args.concurrency, 1),
    )
    print(f"\nResults saved to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
