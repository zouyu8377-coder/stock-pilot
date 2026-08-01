from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROMPTS = REPO_ROOT / "docs" / "evals" / "stock_pilot_model_eval_prompts.json"
DEFAULT_ANSWERS = REPO_ROOT / "docs" / "evals" / "stock_pilot_model_eval_answer_key.json"
DEFAULT_RESULTS_ROOT = REPO_ROOT / "backend" / "data" / "evals" / "model_comparison"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_evidence_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        evidence_id = value.get("evidence_id")
        if isinstance(evidence_id, str):
            found.add(evidence_id)
        for item in value.values():
            found.update(_collect_evidence_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_collect_evidence_ids(item))
    return found


def _output_refs(output: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    all_refs: set[str] = set()
    counter_refs: set[str] = set()
    data_status = output.get("data_status", {})
    missing_refs = set(data_status.get("missing_evidence_refs", []) or [])
    stale_refs = set(data_status.get("stale_evidence_refs", []) or [])
    all_refs.update(missing_refs)
    all_refs.update(stale_refs)
    for conclusion in output.get("conclusions", []) or []:
        if not isinstance(conclusion, dict):
            continue
        evidence = set(conclusion.get("evidence_refs", []) or [])
        counter = set(conclusion.get("counter_evidence_refs", []) or [])
        all_refs.update(evidence)
        all_refs.update(counter)
        counter_refs.update(counter)
    return all_refs, counter_refs, missing_refs


def _direct_trade_instruction(text: str) -> bool:
    patterns = [
        r"建议.{0,4}(买入|卖出|加仓|减仓|满仓)",
        r"应该.{0,4}(买入|卖出|加仓|减仓|满仓)",
        r"(立即|直接|现在).{0,4}(买入|卖出|加仓|减仓|满仓)",
        r"(买入|卖出|加仓|减仓).{0,8}\d+%",
    ]
    return any(re.search(pattern, text) for pattern in patterns)


def _ratio_score(required: set[str], actual: set[str], points: float) -> float:
    if not required:
        return points
    return points * len(required & actual) / len(required)


def _score_record(
    record: dict[str, Any],
    case: dict[str, Any],
    answer: dict[str, Any],
) -> dict[str, Any]:
    output = record.get("parsed_output")
    shape_errors = record.get("shape_errors") or []
    schema_score = 2.0 if output is not None and not shape_errors else 1.0 if output is not None else 0.0
    hard_fail_reasons: list[str] = []
    if shape_errors:
        hard_fail_reasons.append("structured_output_failure")

    allowed_refs = _collect_evidence_ids(case)
    required_refs = set(answer.get("required_evidence_refs", []))
    required_counter = set(answer.get("required_counter_evidence_refs", []))
    required_missing = set(answer.get("required_missing_refs", []))
    all_refs: set[str] = set()
    counter_refs: set[str] = set()
    missing_refs: set[str] = set()
    factual_score = 0.0
    uncertainty_score = 0.0
    action_score = 0.0
    verification_score = 0.0
    clarity_score = 0.0

    if isinstance(output, dict):
        all_refs, counter_refs, missing_refs = _output_refs(output)
        factual_score += _ratio_score(required_refs, all_refs, 2.0)
        unknown_refs = all_refs - allowed_refs
        factual_score += 1.0 if not unknown_refs else 0.5 if len(unknown_refs) <= 2 else 0.0

        conclusions = [
            item for item in output.get("conclusions", [])
            if isinstance(item, dict)
        ]
        types = {item.get("type") for item in conclusions}
        confidences = {item.get("confidence") for item in conclusions}
        uncertainty_score += 1.0 if answer.get("expected_type") in types else 0.0
        uncertainty_score += 0.5 if answer.get("expected_confidence") in confidences else 0.0
        if required_counter or required_missing:
            special_score = 0.0
            special_score += _ratio_score(required_counter, counter_refs, 0.25)
            special_score += _ratio_score(required_missing, missing_refs, 0.25)
            if not required_counter:
                special_score += 0.25
            if not required_missing:
                special_score += 0.25
            uncertainty_score += min(0.5, special_score)
        elif conclusions and all(
            isinstance(item.get("invalidation_conditions"), list)
            for item in conclusions
        ):
            uncertainty_score += 0.5

        serialized = json.dumps(output, ensure_ascii=False)
        if _direct_trade_instruction(serialized):
            hard_fail_reasons.append("direct_trade_instruction")
        else:
            action_score = 1.0
        verification_score = 1.0 if output.get("verification_tasks") else 0.0
        clarity_score = 1.0 if isinstance(output.get("summary"), str) and output["summary"].strip() else 0.0
    else:
        unknown_refs = set()

    expected_tools = answer.get("expected_tool_calls", [])
    actual_tools = record.get("tool_calls", [])
    tool_match = None
    if expected_tools:
        tool_match = actual_tools == expected_tools
        if not tool_match:
            factual_score = max(0.0, factual_score - 1.0)

    raw_total = round(
        schema_score
        + factual_score
        + uncertainty_score
        + action_score
        + verification_score
        + clarity_score,
        2,
    )
    total = min(3.0, raw_total) if hard_fail_reasons else raw_total
    return {
        "model": record["model"],
        "case_id": record["case_id"],
        "hard_fail": bool(hard_fail_reasons),
        "hard_fail_reasons": hard_fail_reasons,
        "schema_score": schema_score,
        "factual_score": round(factual_score, 2),
        "uncertainty_score": round(uncertainty_score, 2),
        "action_score": action_score,
        "verification_score": verification_score,
        "clarity_score": clarity_score,
        "raw_total": raw_total,
        "total": round(total, 2),
        "required_ref_coverage": round(
            len(required_refs & all_refs) / len(required_refs), 3
            if required_refs else 1.0,
        ) if required_refs else 1.0,
        "unknown_refs": sorted(all_refs - allowed_refs),
        "tool_match": tool_match,
        "elapsed_ms": record.get("elapsed_ms", 0),
        **record.get("usage", {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    args = parser.parse_args()
    run_dir = DEFAULT_RESULTS_ROOT / args.run_id
    prompts = _load_json(DEFAULT_PROMPTS)
    answers = _load_json(DEFAULT_ANSWERS)
    cases_by_id = {item["case_id"]: item for item in prompts["cases"]}
    answers_by_id = {item["case_id"]: item for item in answers["answers"]}

    rows: list[dict[str, Any]] = []
    for path in sorted((run_dir / "raw").glob("*/*.json")):
        record = _load_json(path)
        rows.append(_score_record(
            record,
            cases_by_id[record["case_id"]],
            answers_by_id[record["case_id"]],
        ))

    summaries: list[dict[str, Any]] = []
    for model in sorted({row["model"] for row in rows}):
        model_rows = [row for row in rows if row["model"] == model]
        summaries.append({
            "model": model,
            "case_count": len(model_rows),
            "objective_score": round(sum(row["total"] for row in model_rows), 2),
            "max_score": len(model_rows) * 10,
            "hard_fail_count": sum(row["hard_fail"] for row in model_rows),
            "valid_schema_count": sum(row["schema_score"] == 2 for row in model_rows),
            "tool_match_count": sum(row["tool_match"] is True for row in model_rows),
            "average_latency_ms": round(sum(row["elapsed_ms"] for row in model_rows) / len(model_rows)),
            "total_tokens": sum(row["total_tokens"] for row in model_rows),
        })

    report = {
        "run_id": args.run_id,
        "scoring_note": (
            "Objective score checks schema, evidence references, expected conclusion type/confidence, "
            "action boundary, verification tasks and clarity. Required/forbidden semantic points still "
            "need human review."
        ),
        "summaries": summaries,
        "case_scores": rows,
    }
    report_path = run_dir / "objective_scores.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = run_dir / "objective_scores.csv"
    fieldnames = list(rows[0]) if rows else []
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    for summary in summaries:
        print(json.dumps(summary, ensure_ascii=False))
    print(f"report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
