from llmnode.perf.probe_gpu import classify_gpu_processes


def test_classify_gpu_processes_separates_backend_and_other():
    rows = [
        {"pid": 101, "process_name": "python", "used_memory_mb": 12000},
        {"pid": 202, "process_name": "python", "used_memory_mb": 2048},
    ]
    result = classify_gpu_processes(rows, backend_pids={101})
    assert result["backend_process_used_mb"] == 12000
    assert result["other_processes_total_mb"] == 2048
    assert result["other_processes"][0]["pid"] == 202
