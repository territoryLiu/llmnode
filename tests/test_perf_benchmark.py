from pathlib import Path
import json

import llmnode.perf.benchmark as benchmark_module
from llmnode.perf.benchmark import write_benchmark_outputs
from llmnode.perf.benchmark import _summarize_attempts
from llmnode.perf.models import BenchmarkRun


def test_benchmark_models_expose_expected_fields():
    run = BenchmarkRun(
        run_id="demo",
        backend_type="vllm",
        model_name="qwen",
        endpoint="http://127.0.0.1:15673",
        targets=[4096],
    )
    assert run.run_id == "demo"
    assert run.backend_type == "vllm"
    assert run.targets == [4096]


class FakeTokenizer:
    def apply_chat_template(self, messages, tokenize=True, add_generation_prompt=True):
        content = messages[0]["content"]
        return [1] * len(content.split())


class FakeBatchEncoding:
    def __init__(self, token_count: int):
        self.encodings = [type("FakeEncoding", (), {"ids": list(range(token_count))})()]

    def __len__(self):
        return 2


class FakeBatchEncodingTokenizer:
    def apply_chat_template(self, messages, tokenize=True, add_generation_prompt=True):
        content = messages[0]["content"]
        return FakeBatchEncoding(len(content.split()))


def test_prompt_builder_returns_prompt_not_exceeding_target():
    from llmnode.perf.prompt_builder import build_prompt_for_target

    prompt, actual = build_prompt_for_target(
        tokenizer=FakeTokenizer(),
        target_prompt_tokens=8,
        base_fragment="hello",
    )
    assert actual <= 8
    assert isinstance(prompt, str)


def test_prompt_builder_counts_batch_encoding_tokens_not_container_fields():
    from llmnode.perf.prompt_builder import build_prompt_for_target

    prompt, actual = build_prompt_for_target(
        tokenizer=FakeBatchEncodingTokenizer(),
        target_prompt_tokens=8,
        base_fragment="hello",
    )

    assert actual == 8
    assert len(prompt.split()) == 8


def test_write_benchmark_outputs_creates_summary_and_samples(tmp_path: Path):
    run = BenchmarkRun(
        run_id="demo",
        backend_type="vllm",
        model_name="qwen",
        endpoint="http://127.0.0.1:15673",
        targets=[4096],
    )
    output_dir = write_benchmark_outputs(tmp_path, run, [], [])
    assert (output_dir / "summary.json").exists()
    assert (output_dir / "samples.jsonl").exists()


def test_benchmark_cli_defaults():
    from scripts.benchmark_backend import build_parser

    parser = build_parser()
    args = parser.parse_args([])
    assert args.max_tokens == 64
    assert args.sample_interval == 1.0
    assert args.warmup_runs == 1
    assert args.measure_runs == 3
    assert args.concurrency == 1


def test_benchmark_cli_accepts_concurrency():
    from scripts.benchmark_backend import build_parser

    parser = build_parser()
    args = parser.parse_args(["--concurrency", "2"])

    assert args.concurrency == 2


def test_streaming_benchmark_cli_can_force_output_tokens():
    from scripts.benchmark_streaming import build_parser

    args = build_parser().parse_args(["--max-tokens", "800", "--force-output-tokens"])

    assert args.max_tokens == 800
    assert args.force_output_tokens is True


def test_streaming_benchmark_cli_accepts_concurrency():
    from scripts.benchmark_streaming import build_parser

    args = build_parser().parse_args(["--concurrency", "3"])

    assert args.concurrency == 3


def test_streaming_summary_reports_unique_batch_throughput():
    summary = benchmark_module._summarize_streaming_attempts([
        {
            "kind": "measure",
            "result": "success",
            "completion_tokens": 800,
            "batch_index": 1,
            "batch_latency_ms": 10000.0,
            "batch_output_tokens_per_second": 160.0,
        },
        {
            "kind": "measure",
            "result": "success",
            "completion_tokens": 800,
            "batch_index": 1,
            "batch_latency_ms": 10000.0,
            "batch_output_tokens_per_second": 160.0,
        },
        {
            "kind": "measure",
            "result": "success",
            "completion_tokens": 800,
            "batch_index": 2,
            "batch_latency_ms": 8000.0,
            "batch_output_tokens_per_second": 200.0,
        },
        {
            "kind": "measure",
            "result": "success",
            "completion_tokens": 800,
            "batch_index": 2,
            "batch_latency_ms": 8000.0,
            "batch_output_tokens_per_second": 200.0,
        },
    ])

    assert summary["batch_latency_ms_avg"] == 9000.0
    assert summary["aggregate_output_tokens_per_second_avg"] == 180.0
    assert summary["aggregate_output_tokens_per_second_min"] == 160.0
    assert summary["aggregate_output_tokens_per_second_max"] == 200.0


def test_summarize_attempts_uses_measured_runs_only():
    summary = _summarize_attempts([
        {"kind": "warmup", "latency_ms": 1200.0, "completion_tokens": 64, "completion_tokens_per_second": 53.3, "http_status": 200, "result": "success"},
        {"kind": "measure", "latency_ms": 800.0, "completion_tokens": 64, "completion_tokens_per_second": 80.0, "http_status": 200, "result": "success"},
        {"kind": "measure", "latency_ms": 1000.0, "completion_tokens": 64, "completion_tokens_per_second": 64.0, "http_status": 200, "result": "success"},
        {"kind": "measure", "latency_ms": 1200.0, "completion_tokens": 64, "completion_tokens_per_second": 53.3333333333, "http_status": 200, "result": "success"},
    ])
    assert summary["measured_runs"] == 3
    assert summary["warmup_runs"] == 1
    assert round(summary["latency_ms_avg"], 2) == 1000.00
    assert round(summary["latency_ms_p50"], 2) == 1000.00
    assert round(summary["completion_tokens_per_second_avg"], 2) == 65.78
    assert summary["http_status"] == 200
    assert summary["result"] == "success"

def test_summarize_attempts_records_success_rate():
    summary = _summarize_attempts([
        {"kind": "measure", "result": "success", "latency_ms": 100.0, "completion_tokens_per_second": 10.0},
        {"kind": "measure", "result": "timeout"},
    ])

    assert summary["success_count"] == 1
    assert summary["error_count"] == 1
    assert summary["success_rate"] == 0.5


def test_summarize_attempts_records_service_token_fields():
    summary = _summarize_attempts([
        {
            "kind": "warmup",
            "latency_ms": 1200.0,
            "prompt_tokens": 4096,
            "completion_tokens": 64,
            "total_tokens": 4160,
            "completion_tokens_per_second": 53.3,
            "http_status": 200,
            "finish_reason": "length",
            "prompt_token_mismatch": False,
            "result": "success",
        },
        {
            "kind": "measure",
            "latency_ms": 1000.0,
            "prompt_tokens": 262000,
            "completion_tokens": 64,
            "total_tokens": 262064,
            "completion_tokens_per_second": 64.0,
            "http_status": 200,
            "finish_reason": "stop",
            "prompt_token_mismatch": True,
            "result": "success",
        },
    ])

    assert summary["prompt_tokens"] == 262000
    assert summary["completion_tokens"] == 64
    assert summary["total_tokens"] == 262064
    assert summary["finish_reason"] == "stop"
    assert summary["prompt_token_mismatch"] is True

def test_summarize_attempts_records_error_message():
    summary = _summarize_attempts([
        {
            "kind": "measure",
            "http_status": 400,
            "error_message": "maximum context length exceeded",
            "result": "error",
        },
    ])

    assert summary["result"] == "error"
    assert summary["error_message"] == "maximum context length exceeded"


def test_load_tokenizer_falls_back_when_tokenizer_class_is_unknown(tmp_path: Path, monkeypatch):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "tokenizer_config.json").write_text(
        json.dumps({"tokenizer_class": "TokenizersBackend", "processor_class": "Qwen3VLProcessor"}),
        encoding="utf-8",
    )

    calls: list[dict] = []

    class FakeAutoTokenizer:
        @staticmethod
        def from_pretrained(path, trust_remote_code=True):
            calls.append({"path": path, "trust_remote_code": trust_remote_code})
            if len(calls) == 1:
                raise ValueError("Tokenizer class TokenizersBackend does not exist or is not currently imported.")
            return {"ok": True}

    monkeypatch.setitem(
        __import__("sys").modules,
        "transformers",
        type("FakeTransformers", (), {"AutoTokenizer": FakeAutoTokenizer}),
    )

    tokenizer = benchmark_module._load_tokenizer(str(model_dir))

    assert tokenizer == {"ok": True}
    assert len(calls) == 2
    assert calls[0]["path"] == str(model_dir)
    assert calls[1]["path"] != str(model_dir)
