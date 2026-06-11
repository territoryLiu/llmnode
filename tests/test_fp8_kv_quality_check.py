import json

from scripts.fp8_kv_quality_check import compare_results, evaluate, extract_message_text


def test_extract_message_text_reads_reasoning_fallback():
    message = {"content": None, "reasoning": "reasoning text"}

    assert extract_message_text(message) == "reasoning text"


def test_evaluate_accepts_expected_substrings():
    result = evaluate({"checks": ["alpha-777", "248"]}, "- alpha-777\n- 248")

    assert result["passed"] is True


def test_evaluate_requires_strict_json_when_requested():
    result = evaluate({"checks": ["capacity_only"], "json_required": True}, '{"decision": "capacity_only"}\nextra')

    assert result["passed"] is False
    assert result["checks"][-1] == {"valid_json": True, "passed": False}


def test_evaluate_valid_json_passes():
    text = json.dumps({"decision": "capacity_only", "risks": ["quality_regression"]})

    result = evaluate({"checks": ["capacity_only", "quality_regression"], "json_required": True}, text)

    assert result["passed"] is True


def test_compare_results_flags_new_candidate_failure():
    baseline = {
        "model": "awq",
        "passed": 1,
        "rows": [{"case_id": "math_reasoning", "ok": True, "passed": True, "evaluation": {"checks": []}}],
    }
    candidate = {
        "model": "awq-fp8-kv",
        "passed": 0,
        "rows": [{"case_id": "math_reasoning", "ok": True, "passed": False, "evaluation": {"checks": []}}],
    }

    result = compare_results(baseline, candidate)

    assert result["passed"] is False
    assert result["regression_count"] == 1
    assert result["rows"][0]["regression_reasons"] == ["baseline_passed_candidate_failed"]


def test_compare_results_allows_existing_json_failure_shape():
    checks = [{"valid_json": True, "passed": False}]
    baseline = {
        "model": "awq",
        "passed": 0,
        "rows": [{"case_id": "structured_json", "ok": True, "passed": False, "evaluation": {"checks": checks}}],
    }
    candidate = {
        "model": "awq-fp8-kv",
        "passed": 0,
        "rows": [{"case_id": "structured_json", "ok": True, "passed": False, "evaluation": {"checks": checks}}],
    }

    result = compare_results(baseline, candidate)

    assert result["passed"] is True
    assert result["regression_count"] == 0
