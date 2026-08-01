from __future__ import annotations

import argparse
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from openai import OpenAI


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROMPTS = REPO_ROOT / "docs" / "evals" / "stock_pilot_model_eval_prompts.json"
DEFAULT_SCHEMA = REPO_ROOT / "docs" / "evals" / "stock_pilot_review_response.schema.json"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "backend" / "data" / "evals" / "model_comparison"
DEFAULT_MODELS = ["minimax-m3", "glm-5.2", "deepseek-v4-pro", "kimi-k2.7-code"]


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", value)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _usage_dict(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if not usage:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    return {
        "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
    }


def _add_usage(total: dict[str, int], current: dict[str, int]) -> None:
    for key in total:
        total[key] += current.get(key, 0)


def _extract_json(content: str) -> tuple[dict[str, Any] | None, str | None]:
    text = content.strip()
    candidates = [text]
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        candidates.insert(0, fenced.group(1))
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        candidates.append(text[first:last + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value, None
    return None, "response did not contain a parseable JSON object"


def _validate_shape(payload: dict[str, Any] | None) -> list[str]:
    if payload is None:
        return ["not_json"]
    errors: list[str] = []
    required = {"review_type", "data_status", "conclusions", "verification_tasks", "summary"}
    missing = required - set(payload)
    if missing:
        errors.append(f"missing_top_level:{','.join(sorted(missing))}")
    if not isinstance(payload.get("data_status"), dict):
        errors.append("data_status_not_object")
    if not isinstance(payload.get("conclusions"), list):
        errors.append("conclusions_not_array")
    if not isinstance(payload.get("verification_tasks"), list):
        errors.append("verification_tasks_not_array")
    for index, item in enumerate(payload.get("conclusions", [])):
        if not isinstance(item, dict):
            errors.append(f"conclusion_{index}_not_object")
            continue
        conclusion_required = {
            "conclusion_id",
            "type",
            "subject",
            "claim",
            "confidence",
            "evidence_refs",
            "counter_evidence_refs",
            "action_semantics",
            "invalidation_conditions",
        }
        item_missing = conclusion_required - set(item)
        if item_missing:
            errors.append(f"conclusion_{index}_missing:{','.join(sorted(item_missing))}")
    return errors


def _tool_schema(tool: dict[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, type_name in tool.get("parameters", {}).items():
        properties[name] = {"type": type_name}
        required.append(name)
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def _resolve_mock_tool(case: dict[str, Any], name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    key = f"{name}:{json.dumps(arguments, ensure_ascii=False, separators=(',', ':'))}"
    result = case.get("mock_tool_results", {}).get(key)
    if result is not None:
        return result
    return {
        "error": "mock_result_not_configured",
        "tool": name,
        "arguments": arguments,
    }


def _build_user_message(case: dict[str, Any], output_template: dict[str, Any]) -> str:
    context_key = "initial_context" if case.get("mode") == "tool_call" else "context"
    payload = {
        "case_id": case["case_id"],
        "task": case["user_prompt"],
        "context": case[context_key],
        "required_output": output_template,
        "output_instruction": "只输出符合 required_output 字段的 JSON 对象，不要输出 Markdown 或额外说明。",
    }
    if case.get("mode") == "tool_call":
        payload["tool_instruction"] = (
            "仅在初始上下文不足时调用最小必要工具。获得工具结果后再输出最终 JSON。"
        )
    return json.dumps(payload, ensure_ascii=False)


def _request(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    tools: list[dict[str, Any]] | None = None,
    json_mode: bool = True,
) -> tuple[Any, bool]:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        return client.chat.completions.create(**kwargs), json_mode
    except Exception as exc:
        message = str(exc).lower()
        if json_mode and any(term in message for term in ("response_format", "json_object", "json mode")):
            kwargs.pop("response_format", None)
            return client.chat.completions.create(**kwargs), False
        raise


def _run_case(
    client: OpenAI,
    *,
    model: str,
    case: dict[str, Any],
    system_prompt: str,
    output_template: dict[str, Any],
    tool_definitions: dict[str, dict[str, Any]],
    max_tokens: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    tool_calls_record: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": _build_user_message(case, output_template)},
    ]
    tools = [
        _tool_schema(tool_definitions[name])
        for name in case.get("available_tools", [])
        if name in tool_definitions
    ]
    json_mode_used = True
    try:
        response, json_mode_used = _request(
            client,
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            tools=tools or None,
            json_mode=True,
        )
        _add_usage(usage, _usage_dict(response))
        message = response.choices[0].message
        finish_reasons = [response.choices[0].finish_reason]

        if message.tool_calls:
            messages.append(message.model_dump(exclude_none=True))
            for call in message.tool_calls:
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {"_raw": call.function.arguments}
                tool_calls_record.append({
                    "name": call.function.name,
                    "arguments": arguments,
                })
                result = _resolve_mock_tool(case, call.function.name, arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
            response, second_json_mode = _request(
                client,
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                tools=tools or None,
                json_mode=json_mode_used,
            )
            json_mode_used = json_mode_used and second_json_mode
            _add_usage(usage, _usage_dict(response))
            message = response.choices[0].message
            finish_reasons.append(response.choices[0].finish_reason)

        content = message.content or ""
        parsed, parse_error = _extract_json(content)
        return {
            "model": model,
            "case_id": case["case_id"],
            "status": "completed",
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "usage": usage,
            "json_mode_used": json_mode_used,
            "finish_reasons": finish_reasons,
            "tool_calls": tool_calls_record,
            "raw_content": content,
            "parsed_output": parsed,
            "parse_error": parse_error,
            "shape_errors": _validate_shape(parsed),
        }
    except Exception as exc:
        return {
            "model": model,
            "case_id": case["case_id"],
            "status": "failed",
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "usage": usage,
            "json_mode_used": json_mode_used,
            "finish_reasons": [],
            "tool_calls": tool_calls_record,
            "raw_content": "",
            "parsed_output": None,
            "parse_error": None,
            "shape_errors": ["request_failed"],
            "error": str(exc)[:1000],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--cases", nargs="*", default=[])
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=2500)
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / "backend" / ".env")
    base_url = os.getenv("LLM_BASE_URL")
    api_key = os.getenv("LLM_API_KEY")
    if not base_url or not api_key:
        raise SystemExit("LLM_BASE_URL and LLM_API_KEY must be configured in backend/.env")

    prompts = _load_json(DEFAULT_PROMPTS)
    output_template = prompts["output_schema"]
    tool_definitions = {item["name"]: item for item in prompts["tool_definitions"]}
    requested_cases = set(args.cases)
    cases = [
        item for item in prompts["cases"]
        if not requested_cases or item["case_id"] in requested_cases
    ]
    missing_cases = requested_cases - {item["case_id"] for item in cases}
    if missing_cases:
        raise SystemExit(f"Unknown case ids: {', '.join(sorted(missing_cases))}")

    run_dir = DEFAULT_OUTPUT_ROOT / _safe_name(args.run_id)
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=httpx.Timeout(180, connect=15),
        max_retries=1,
    )
    jobs: list[tuple[str, dict[str, Any], Path]] = []
    for case in cases:
        for model in args.models:
            output_path = run_dir / "raw" / _safe_name(model) / f"{case['case_id']}.json"
            if args.resume and output_path.exists():
                continue
            jobs.append((model, case, output_path))

    print(
        f"run_id={args.run_id} models={len(args.models)} "
        f"cases={len(cases)} requests={len(jobs)} max_workers={args.max_workers}"
    )
    with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as pool:
        futures = {
            pool.submit(
                _run_case,
                client,
                model=model,
                case=case,
                system_prompt=prompts["system_prompt"],
                output_template=output_template,
                tool_definitions=tool_definitions,
                max_tokens=args.max_tokens,
            ): (model, case["case_id"], output_path)
            for model, case, output_path in jobs
        }
        for future in as_completed(futures):
            model, case_id, output_path = futures[future]
            result = future.result()
            _write_json(output_path, result)
            print(
                f"{model} {case_id} {result['status']} "
                f"{result['elapsed_ms']}ms tokens={result['usage']['total_tokens']} "
                f"shape_errors={len(result['shape_errors'])}"
            )

    manifest = {
        "run_id": args.run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "models": args.models,
        "case_ids": [item["case_id"] for item in cases],
        "max_tokens": args.max_tokens,
        "max_workers": args.max_workers,
        "prompts_path": str(DEFAULT_PROMPTS),
        "schema_path": str(DEFAULT_SCHEMA),
    }
    _write_json(run_dir / "manifest.json", manifest)
    print(f"results={run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
