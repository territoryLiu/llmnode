import json

from llmnode.perf.lab_models import PerfRunRequest
from llmnode.perf.lab_models import expand_matrix
from llmnode.perf.lab_store import PerfRunStore


def test_store_creates_run_files(tmp_path):
    store = PerfRunStore(tmp_path)
    request = PerfRunRequest(profile="vllm_qwen36-27b-nvfp4", targets=[4096])
    points = expand_matrix(request)

    run = store.create_run(request, points)

    run_dir = tmp_path / run["run_id"]
    assert (run_dir / "run.json").exists()
    assert (run_dir / "matrix.json").exists()
    assert json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["status"] == "queued"


def test_store_updates_point_status_and_errors(tmp_path):
    store = PerfRunStore(tmp_path)
    request = PerfRunRequest(profile="vllm_qwen36-27b-nvfp4", targets=[4096])
    run = store.create_run(request, expand_matrix(request))

    store.update_point(
        run["run_id"],
        "point-001",
        status="startup_failed",
        errors=[{"message": "KV cache too small"}],
    )

    point_dir = tmp_path / run["run_id"] / "points" / "point-001"
    assert json.loads((point_dir / "summary.json").read_text(encoding="utf-8"))["status"] == "startup_failed"
    assert json.loads((point_dir / "errors.json").read_text(encoding="utf-8"))["errors"][0]["message"] == (
        "KV cache too small"
    )


def test_store_lists_runs_newest_first(tmp_path):
    store = PerfRunStore(tmp_path)
    first_request = PerfRunRequest(profile="a", targets=[1])
    second_request = PerfRunRequest(profile="b", targets=[1])
    first = store.create_run(first_request, expand_matrix(first_request))
    second = store.create_run(second_request, expand_matrix(second_request))

    runs = store.list_runs()

    assert [run["run_id"] for run in runs] == [second["run_id"], first["run_id"]]
