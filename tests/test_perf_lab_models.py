from llmnode.perf.lab_models import PerfRunRequest, expand_matrix


def test_expand_matrix_defaults_to_single_current_profile_point():
    request = PerfRunRequest(profile="vllm_qwen36-27b-nvfp4", targets=[4096])

    points = expand_matrix(request)

    assert len(points) == 1
    assert points[0].point_id == "point-001"
    assert points[0].profile == "vllm_qwen36-27b-nvfp4"
    assert points[0].overrides == {}


def test_expand_matrix_creates_cartesian_product_in_stable_order():
    request = PerfRunRequest(
        profile="vllm_qwen36-27b-nvfp4",
        targets=[4096, 262000],
        matrix={
            "gpu_memory_utilization": [0.55, 0.6],
            "max_model_len": [262144],
            "max_num_seqs": [1, 4],
        },
    )

    points = expand_matrix(request)

    assert [point.point_id for point in points] == ["point-001", "point-002", "point-003", "point-004"]
    assert points[0].overrides == {
        "gpu_memory_utilization": 0.55,
        "max_model_len": 262144,
        "max_num_seqs": 1,
    }
    assert points[-1].overrides == {
        "gpu_memory_utilization": 0.6,
        "max_model_len": 262144,
        "max_num_seqs": 4,
    }


def test_request_rejects_empty_targets():
    try:
        PerfRunRequest(profile="vllm_qwen36-27b-nvfp4", targets=[])
    except ValueError as exc:
        assert "targets must not be empty" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_request_rejects_unknown_matrix_key():
    try:
        PerfRunRequest(
            profile="vllm_qwen36-27b-nvfp4",
            targets=[4096],
            matrix={"tensor_parallel_size": [2]},
        )
    except ValueError as exc:
        assert "unsupported matrix key" in str(exc)
    else:
        raise AssertionError("expected ValueError")
