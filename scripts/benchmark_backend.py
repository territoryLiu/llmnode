from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llmnode.perf.benchmark import run_benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", nargs="*", type=int, default=[4096, 32768, 65536, 131072, 262000])
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--sample-interval", type=float, default=1.0)
    parser.add_argument("--output-dir", type=str, default="")
    parser.add_argument("--profile", type=str, default="")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    run_benchmark(
        targets=args.targets,
        max_tokens=args.max_tokens,
        sample_interval=args.sample_interval,
        output_dir=args.output_dir,
        profile=args.profile,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
