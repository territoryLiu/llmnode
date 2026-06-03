import time
from pathlib import Path

from llmnode.perf.lab_models import PerfRunRequest
from llmnode.perf.lab_models import expand_matrix
from llmnode.perf.lab_runner import LocalPerfPointExecutor
from llmnode.perf.lab_runner import PerfLabRunner
from llmnode.perf.lab_store import PerfRunStore


class FakeExecutor:
    def __init__(self):
        self.executed = []

    def execute_point(self, *, run_id, point, request, store, cancel_requested):
        self.executed.append(point.point_id)
        store.update_point(run_id, point.point_id, status="completed", summary={"result": "success"})


def wait_until_done(runner, run_id):
    for _ in range(50):
        payload = runner.get_run(run_id)
        if payload["status"] in {"completed", "completed_with_errors", "failed", "cancelled"}:
            return payload
        time.sleep(0.02)
    raise AssertionError("run did not finish")


def test_runner_rejects_second_active_run(tmp_path):
    store = PerfRunStore(tmp_path)
    runner = PerfLabRunner(store=store, executor=FakeExecutor())
    request = PerfRunRequest(profile="vllm_qwen36-27b-nvfp4", targets=[4096])

    first = runner.create_run(request)
    second = runner.create_run(request)

    assert first["status"] == "queued"
    assert second["status_code"] == 409


def test_runner_completes_run(tmp_path):
    store = PerfRunStore(tmp_path)
    executor = FakeExecutor()
    runner = PerfLabRunner(store=store, executor=executor)

    run = runner.create_run(PerfRunRequest(profile="vllm_qwen36-27b-nvfp4", targets=[4096]))
    final = wait_until_done(runner, run["run_id"])

    assert final["status"] == "completed"
    assert executor.executed == ["point-001"]


def test_runner_accepts_cancel_request(tmp_path):
    store = PerfRunStore(tmp_path)
    runner = PerfLabRunner(store=store, executor=FakeExecutor())
    run = runner.create_run(PerfRunRequest(profile="vllm_qwen36-27b-nvfp4", targets=[4096]))

    response = runner.cancel_run(run["run_id"])

    assert response["status"] in {"cancel_requested", "completed", "cancelled"}


class FakeControl:
    def __init__(self):
        self.calls = []

    def stop(self, profile):
        self.calls.append(("stop", profile))

    def start(self, profile, overrides):
        self.calls.append(("start", profile, overrides))

    def wait_healthy(self, profile):
        self.calls.append(("wait_healthy", profile))
        return True

    def startup_metrics(self, profile):
        return {"model_weight_memory_gib": 24.05, "available_kv_cache_memory_gib": 17.38}


class FakeBenchmark:
    def __call__(self, *, profile, targets, max_tokens, warmup_runs, measure_runs, sample_interval, output_dir, concurrency):
        point_dir = Path(output_dir)
        point_dir.mkdir(parents=True, exist_ok=True)
        (point_dir / "summary.json").write_text('{"steps": []}', encoding="utf-8")
        (point_dir / "samples.jsonl").write_text("", encoding="utf-8")


def test_local_executor_runs_control_and_benchmark(tmp_path):
    store = PerfRunStore(tmp_path)
    request = PerfRunRequest(profile="vllm_qwen36-27b-nvfp4", targets=[4096])
    run = store.create_run(request, expand_matrix(request))
    point = expand_matrix(request)[0]
    control = FakeControl()
    executor = LocalPerfPointExecutor(control=control, benchmark=FakeBenchmark())

    executor.execute_point(run_id=run["run_id"], point=point, request=request, store=store, cancel_requested=lambda: False)

    assert control.calls[0] == ("stop", "vllm_qwen36-27b-nvfp4")
    assert store.get_run(run["run_id"])["matrix"][0]["status"] == "completed"
