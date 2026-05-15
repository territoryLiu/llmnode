from pathlib import Path

from llmnode.perf.benchmark import write_benchmark_outputs
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


def test_prompt_builder_returns_prompt_not_exceeding_target():
    from llmnode.perf.prompt_builder import build_prompt_for_target

    prompt, actual = build_prompt_for_target(
        tokenizer=FakeTokenizer(),
        target_prompt_tokens=8,
        base_fragment="hello",
    )
    assert actual <= 8
    assert isinstance(prompt, str)


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
