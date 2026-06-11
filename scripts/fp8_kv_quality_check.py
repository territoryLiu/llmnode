from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib import request


CASES = [
    {
        "id": "long_context_consistency",
        "kind": "long_context",
        "max_tokens": 512,
        "messages": [
            {"role": "system", "content": "You are a precise evaluator. Follow the requested output format exactly."},
            {
                "role": "user",
                "content": "Read the synthetic context and answer with exactly three bullet points.\n\n"
                + "\n".join(
                    f"Record {i}: item=alpha-{i}; owner=team-{i % 7}; checksum={i * 17 % 997}."
                    for i in range(1, 900)
                )
                + "\n\nQuestion: Which owner appears in Record 777, what is its item, and what is its checksum? Include the literal strings only.",
            },
        ],
        "checks": ["team-0", "alpha-777", "248"],
    },
    {
        "id": "code_generation",
        "kind": "code",
        "max_tokens": 512,
        "messages": [
            {"role": "system", "content": "Return only Python code, no markdown."},
            {
                "role": "user",
                "content": "Write a Python function stable_top_k(items, k) that returns the k largest numeric items preserving input order for ties. Include a short docstring and handle k <= 0.",
            },
        ],
        "checks": ["def stable_top_k", "sorted", "k <= 0"],
    },
    {
        "id": "math_reasoning",
        "kind": "math",
        "max_tokens": 512,
        "messages": [
            {"role": "system", "content": "Solve carefully. End with 'ANSWER: <number>'."},
            {
                "role": "user",
                "content": "A cache has 70,560 slots. A setting increases it to 87,024 slots. What is the percentage increase, rounded to two decimals?",
            },
        ],
        "checks": ["23.33"],
    },
    {
        "id": "structured_json",
        "kind": "json",
        "max_tokens": 512,
        "messages": [
            {"role": "system", "content": "Return valid JSON only."},
            {
                "role": "user",
                "content": "Return JSON with keys decision, risks, next_steps. decision must be 'capacity_only'. risks must be an array containing 'quality_regression'. next_steps must be an array of two strings.",
            },
        ],
        "json_required": True,
        "checks": ["capacity_only", "quality_regression"],
    },
    {
        "id": "tool_call_json_stability",
        "kind": "tool_json",
        "max_tokens": 512,
        "messages": [
            {"role": "system", "content": "You emit tool calls as JSON only. Do not add prose."},
            {
                "role": "user",
                "content": 'Call benchmark_backend with profile=\'vllm_qwen36-27b-awq-int4-fp8-kv\', target=65536, max_tokens=512, concurrency=2. Return exactly {"tool":...,"arguments":...}.',
            },
        ],
        "json_required": True,
        "checks": ["benchmark_backend", "65536", "512"],
    },
]


def extract_message_text(message: dict) -> str:
    return "\n".join(
        str(message.get(key) or "")
        for key in ("content", "reasoning_content", "reasoning")
        if message.get(key)
    )


def post_json(url: str, payload: dict, timeout: int = 360) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def evaluate(case: dict, text: str) -> dict:
    checks = []
    lower = text.lower()
    for expected in case.get("checks", []):
        checks.append({"contains": expected, "passed": str(expected).lower() in lower})
    json_result = None
    if case.get("json_required"):
        try:
            json_result = json.loads(text)
            json_ok = True
        except Exception as exc:
            json_result = str(exc)
            json_ok = False
        checks.append({"valid_json": True, "passed": json_ok})
    return {"passed": all(item["passed"] for item in checks), "checks": checks, "json_result": json_result}


def _case_map(result: dict) -> dict:
    return {row["case_id"]: row for row in result.get("rows", [])}


def _valid_json(row: dict) -> bool | None:
    for check in row.get("evaluation", {}).get("checks", []):
        if check.get("valid_json") is True:
            return bool(check.get("passed"))
    return None


def compare_results(baseline: dict, candidate: dict) -> dict:
    baseline_rows = _case_map(baseline)
    candidate_rows = _case_map(candidate)
    rows = []
    regressions = []
    missing = sorted(set(baseline_rows) - set(candidate_rows))

    for case_id in sorted(set(baseline_rows) | set(candidate_rows)):
        base = baseline_rows.get(case_id)
        cand = candidate_rows.get(case_id)
        if not base or not cand:
            continue

        base_passed = bool(base.get("passed"))
        cand_passed = bool(cand.get("passed"))
        base_json = _valid_json(base)
        cand_json = _valid_json(cand)
        regression_reasons = []

        if base_passed and not cand_passed:
            regression_reasons.append("baseline_passed_candidate_failed")
        if base.get("ok") and not cand.get("ok"):
            regression_reasons.append("candidate_request_failed")
        if base_json is True and cand_json is False:
            regression_reasons.append("valid_json_regressed")

        row = {
            "case_id": case_id,
            "baseline_passed": base_passed,
            "candidate_passed": cand_passed,
            "baseline_valid_json": base_json,
            "candidate_valid_json": cand_json,
            "regression": bool(regression_reasons),
            "regression_reasons": regression_reasons,
        }
        rows.append(row)
        if row["regression"]:
            regressions.append(row)

    return {
        "baseline_model": baseline.get("model"),
        "candidate_model": candidate.get("model"),
        "baseline_passed": baseline.get("passed"),
        "candidate_passed": candidate.get("passed"),
        "total_cases": len(rows),
        "missing_candidate_cases": missing,
        "regression_count": len(regressions) + len(missing),
        "passed": not regressions and not missing,
        "rows": rows,
    }


def run(endpoint: str, model: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in CASES:
        payload = {
            "model": model,
            "messages": case["messages"],
            "max_tokens": case["max_tokens"],
            "temperature": 0,
        }
        start = time.time()
        ok = True
        err = None
        text = ""
        raw = None
        try:
            raw = post_json(endpoint.rstrip("/") + "/chat/completions", payload)
            text = extract_message_text(raw["choices"][0]["message"])
        except Exception as exc:
            ok = False
            err = repr(exc)
        elapsed_ms = (time.time() - start) * 1000
        eval_result = evaluate(case, text) if ok else {"passed": False, "checks": [], "json_result": None}
        row = {
            "case_id": case["id"],
            "kind": case["kind"],
            "ok": ok,
            "error": err,
            "latency_ms": round(elapsed_ms, 2),
            "passed": bool(eval_result["passed"]),
            "evaluation": eval_result,
            "text": text,
            "usage": raw.get("usage") if isinstance(raw, dict) else None,
        }
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))

    output.write_text(
        json.dumps(
            {
                "endpoint": endpoint,
                "model": model,
                "total": len(rows),
                "passed": sum(1 for row in rows if row["passed"]),
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def compare_files(baseline: Path, candidate: Path, output: Path | None) -> None:
    baseline_result = json.loads(baseline.read_text(encoding="utf-8"))
    candidate_result = json.loads(candidate.read_text(encoding="utf-8"))
    result = compare_results(baseline_result, candidate_result)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--endpoint", default="http://127.0.0.1:15673/v1")
    run_parser.add_argument("--model", required=True)
    run_parser.add_argument("--output", required=True)

    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--baseline", required=True)
    compare_parser.add_argument("--candidate", required=True)
    compare_parser.add_argument("--output")

    parser.add_argument("--endpoint", default="http://127.0.0.1:15673/v1")
    parser.add_argument("--model")
    parser.add_argument("--output")
    args = parser.parse_args()

    if args.command == "compare":
        compare_files(Path(args.baseline), Path(args.candidate), Path(args.output) if args.output else None)
        return

    if args.command in (None, "run"):
        if not args.model or not args.output:
            parser.error("--model and --output are required")
        run(args.endpoint, args.model, Path(args.output))
        return

    parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
