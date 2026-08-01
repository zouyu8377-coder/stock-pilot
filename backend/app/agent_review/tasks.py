from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from app.agent_context.service import build_portfolio_agent_context
from app.collector.router import collector
from app.core.data_updater import get_last_trading_date
from app.disclosure_verification import load_disclosure_verification
from app.facts import get_disclosure_facts
from app.facts.common import compact_symbol
from app.portfolio.symbol_resolver import KNOWN_SYMBOLS
from app.rotation.service import build_rotation_bundle, load_rotation_status


BACKEND_DIR = Path(__file__).resolve().parents[2]
TASK_DIR = BACKEND_DIR / "data" / "agent_tasks"
TASKS_PATH = TASK_DIR / "tasks.json"
SOURCE_HEALTH_PATH = TASK_DIR / "source_health.json"
TASK_CONTRACT_VERSION = "agent_task.v2"
_LOCK = threading.Lock()

TOOL_LABELS = {
    "stock_snapshot": "核查标的行情",
    "rotation_refresh": "重建轮动证据",
    "event_snapshot": "核查事件雷达",
    "disclosure_snapshot": "核查公告与调研事实",
    "manual_review": "人工核查",
}
AUTO_TOOLS = {"stock_snapshot", "rotation_refresh", "event_snapshot", "disclosure_snapshot"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_tasks() -> list[dict[str, Any]]:
    if not TASKS_PATH.exists():
        return []
    try:
        payload = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _write_tasks(items: list[dict[str, Any]]) -> None:
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = TASKS_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(TASKS_PATH)


def _read_source_health() -> dict[str, Any]:
    if not SOURCE_HEALTH_PATH.exists():
        return {}
    try:
        payload = json.loads(SOURCE_HEALTH_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_source_health(payload: dict[str, Any]) -> None:
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = SOURCE_HEALTH_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(SOURCE_HEALTH_PATH)


def _record_source_attempt(
    tool_name: str,
    *,
    status: str,
    failure_category: str | None = None,
) -> None:
    with _LOCK:
        health = _read_source_health()
        item = dict(health.get(tool_name) or {})
        item["tool_name"] = tool_name
        item["attempt_count"] = int(item.get("attempt_count") or 0) + 1
        key = "success_count" if status == "completed" else "partial_count" if status == "partial" else "failure_count"
        item[key] = int(item.get(key) or 0) + 1
        item["last_attempt_at"] = _now_iso()
        item["last_status"] = status
        if status in {"completed", "partial"}:
            item["last_success_at"] = _now_iso()
        if failure_category:
            item["last_failure_category"] = failure_category
            item["last_error_at"] = _now_iso()
        attempts = int(item["attempt_count"])
        item["reliability_pct"] = round(
            (int(item.get("success_count") or 0) + 0.5 * int(item.get("partial_count") or 0)) / attempts * 100,
            1,
        )
        health[tool_name] = item
        _write_source_health(health)


def source_health() -> list[dict[str, Any]]:
    return sorted(_read_source_health().values(), key=lambda item: str(item.get("tool_name") or ""))


def _task_key(subject: str, task: str) -> str:
    normalized = re.sub(r"\s+", "", f"{subject}|{task}").lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def _symbols_from_verification(verification: dict[str, Any], text: str) -> list[str]:
    normalized_text = re.sub(r"\s+", "", text).lower()
    structured = [
        compact_symbol(str(value))
        for value in verification.get("target_symbols") or []
        if re.fullmatch(r"\d{6}(?:\.(?:SH|SZ|BJ))?", str(value).strip(), re.IGNORECASE)
    ]
    explicit = [
        compact_symbol(value)
        for value in re.findall(r"(?<!\d)(\d{6})(?!\d)", text)
    ]
    named = [
        code
        for code, name in KNOWN_SYMBOLS.items()
        if name and re.sub(r"\s+", "", name).lower() in normalized_text
    ]
    return list(dict.fromkeys([*structured, *explicit, *named]))


def _infer_tool(verification: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    subject = str(verification.get("subject") or "")
    task = str(verification.get("task") or "")
    text = f"{subject} {task}"
    evidence_type = str(verification.get("evidence_type") or "")
    symbols = _symbols_from_verification(verification, text)
    if evidence_type == "event_outcome":
        return "event_snapshot", {"query": text}, "结构化证据类型指定为事件结果"
    if evidence_type == "rotation":
        return "rotation_refresh", {}, "结构化证据类型指定为轮动验证"
    if evidence_type in {"announcement", "financial"} and symbols:
        return "disclosure_snapshot", {"symbols": symbols}, "结构化证据类型指定为公告或财务核查"
    if evidence_type == "market_snapshot" and symbols:
        return "stock_snapshot", {"symbols": symbols}, "结构化证据类型指定为标的行情"
    if re.search(r"FOMC|CPI|非农|事件|宏观|决议|数据公布", text, re.IGNORECASE):
        return "event_snapshot", {"query": text}, "任务需要核查现有重要事件与组合影响"
    if symbols and re.search(r"公告|调研|订单|业绩|财报|收入|利润|毛利率", text, re.IGNORECASE):
        return "disclosure_snapshot", {"symbols": symbols}, "标的明确且任务需要公告或调研事实"
    if symbols:
        return "stock_snapshot", {"symbols": symbols}, "从结构化字段、代码或名称识别到明确标的"
    if re.search(r"轮动|板块|行业|方向|量能|资金流|ETF|趋势", text, re.IGNORECASE):
        return "rotation_refresh", {}, "任务需要重建本地轮动证据"
    return "manual_review", {}, "当前白名单工具无法可靠完成该核查"


def _low_confidence_verifications(review: dict[str, Any]) -> list[dict[str, Any]]:
    planned = []
    explicit_subjects = {
        str(item.get("subject") or "").strip()
        for item in review.get("verification_tasks", [])
    }
    for group_name in ("opportunities", "risks", "watch_items"):
        for item in review.get(group_name, []):
            if item.get("confidence") != "low":
                continue
            subject = str(item.get("subject") or "").strip()
            if not subject or subject in explicit_subjects:
                continue
            refs = [
                str(value)
                for value in [*(item.get("evidence_refs") or []), *(item.get("counter_evidence_refs") or [])]
            ]
            symbols = list(dict.fromkeys(
                match.group(1)
                for ref in refs
                if (match := re.search(r"(?:holding|stock):([0-9]{6})", ref))
            ))
            if any(ref.startswith("rotation:") for ref in refs):
                evidence_type = "rotation"
                missing = ["更新轮动行情并确认强度、扩散和阶段信号"]
            elif any(ref.startswith("event:") for ref in refs):
                evidence_type = "event_outcome"
                missing = ["确认事件状态及落地后的可观察事实"]
            elif symbols:
                evidence_type = "market_snapshot"
                missing = ["取得最新行情、趋势与相对基准表现"]
            else:
                evidence_type = "manual"
                missing = ["当前白名单来源无法定位足够的结构化事实"]
            planned.append({
                "priority": "medium",
                "subject": subject,
                "task": f"补齐“{subject}”低置信度判断所缺事实",
                "reason": "该结论置信度低且没有配套核查任务，系统自动进入取证队列",
                "target_symbols": symbols[:5],
                "evidence_type": evidence_type,
                "missing_evidence": missing,
                "success_criteria": "取得可追溯的新事实后重新评价，未取得时保持低置信度",
                "planning_origin": "low_confidence_auto",
            })
            explicit_subjects.add(subject)
            if len(planned) >= 3:
                return planned
    return planned


def sync_review_tasks(review_run: dict[str, Any]) -> list[dict[str, Any]]:
    review = review_run.get("review") or {}
    run_id = str(review_run.get("run_id") or "")
    now = _now_iso()
    with _LOCK:
        items = _read_tasks()
        existing_keys = {
            (item.get("origin_run_id"), item.get("task_key"))
            for item in items
        }
        low_confidence_subjects = {
            str(item.get("subject") or "").strip()
            for group_name in ("opportunities", "risks", "watch_items")
            for item in review.get(group_name, [])
            if item.get("confidence") == "low"
        }
        for existing in items:
            if (
                existing.get("origin_run_id") == run_id
                and str(existing.get("subject") or "").strip() in low_confidence_subjects
                and existing.get("planning_origin") == "model_planned"
            ):
                existing["planning_origin"] = "low_confidence_model_planned"
                existing["updated_at"] = now
        verifications = [
            {
                **verification,
                "planning_origin": (
                    "low_confidence_model_planned"
                    if str(verification.get("subject") or "").strip() in low_confidence_subjects
                    else verification.get("planning_origin", "model_planned")
                ),
            }
            for verification in review.get("verification_tasks", [])
        ]
        verifications.extend(_low_confidence_verifications(review))
        for verification in verifications[:9]:
            subject = str(verification.get("subject") or "").strip()
            task_text = str(verification.get("task") or "").strip()
            key = _task_key(subject, task_text)
            if (run_id, key) in existing_keys:
                continue
            for existing in items:
                if (
                    existing.get("task_key") == key
                    and existing.get("origin_run_id") != run_id
                    and existing.get("status") in {"pending", "running", "retry_wait", "failed", "partial"}
                ):
                    existing["status"] = "superseded"
                    existing["superseded_by_run_id"] = run_id
                    existing["updated_at"] = now
            tool_name, arguments, mapping_reason = _infer_tool(verification)
            status = "pending" if tool_name in AUTO_TOOLS else "manual_required"
            items.append({
                "contract_version": TASK_CONTRACT_VERSION,
                "task_id": f"task-{uuid4().hex[:12]}",
                "task_key": key,
                "origin_run_id": run_id,
                "priority": verification.get("priority", "medium"),
                "subject": subject,
                "task": task_text,
                "reason": verification.get("reason", ""),
                "target_symbols": _symbols_from_verification(verification, f"{subject} {task_text}"),
                "evidence_type": verification.get("evidence_type", "manual"),
                "missing_evidence": verification.get("missing_evidence", []),
                "success_criteria": verification.get("success_criteria", ""),
                "planning_origin": verification.get("planning_origin", "model_planned"),
                "status": status,
                "tool": {
                    "name": tool_name,
                    "label": TOOL_LABELS[tool_name],
                    "arguments": arguments,
                    "auto_executable": tool_name in AUTO_TOOLS,
                    "mapping_reason": mapping_reason,
                },
                "created_at": now,
                "updated_at": now,
                "started_at": None,
                "completed_at": None,
                "attempt_count": 0,
                "max_attempts": 3,
                "next_retry_at": None,
                "last_error_at": None,
                "failure_category": None,
                "recovery_count": 0,
                "result": None,
                "error": None,
            })
        _write_tasks(items)
        return [item for item in items if item.get("origin_run_id") == run_id]


def list_tasks(*, origin_run_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    with _LOCK:
        items = _read_tasks()
    if origin_run_id:
        items = [item for item in items if item.get("origin_run_id") == origin_run_id]
    return list(reversed(items[-max(1, min(limit, 500)):]))


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    if pd.isna(value):
        return None
    return value


def _stock_snapshot(arguments: dict[str, Any]) -> dict[str, Any]:
    raw_symbols = arguments.get("symbols") or [arguments.get("symbol")]
    symbols = list(dict.fromkeys(
        compact_symbol(str(value or ""))
        for value in raw_symbols
        if value
    ))
    if not symbols or any(not re.fullmatch(r"\d{6}", symbol) for symbol in symbols):
        raise ValueError("stock_snapshot 需要一个或多个合法六位证券代码")
    target_date = get_last_trading_date()
    snapshots: list[dict[str, Any]] = []
    remaining_gaps: list[str] = []
    for symbol in symbols:
        quote_error = None
        try:
            quote = collector.get_quote(symbol)
        except Exception as exc:
            quote = {}
            quote_error = str(exc)[:240]
        history = collector.get_history(symbol, limit=65).copy()
        history["date"] = pd.to_datetime(history["date"], errors="coerce")
        for column in ("close", "amount", "volume"):
            if column in history:
                history[column] = pd.to_numeric(history[column], errors="coerce")
        history = history.dropna(subset=["date", "close"]).sort_values("date")
        if history.empty:
            remaining_gaps.append(f"{symbol} 本地历史行情不可用")
            continue
        latest_close = float(history["close"].iloc[-1])
        latest_date = history["date"].iloc[-1].date()

        def period_return(days: int) -> float | None:
            if len(history) <= days:
                return None
            base = float(history["close"].iloc[-days - 1])
            return round((latest_close / base - 1) * 100, 2) if base else None

        ma20 = float(history["close"].tail(20).mean()) if len(history) >= 20 else None
        amount_5 = history["amount"].tail(5).mean() if "amount" in history else None
        amount_20 = history["amount"].tail(20).mean() if "amount" in history else None
        volume_5 = history["volume"].tail(5).mean() if "volume" in history else None
        volume_20 = history["volume"].tail(20).mean() if "volume" in history else None

        def ratio(current: Any, base: Any) -> float | None:
            if pd.isna(current) or pd.isna(base) or not float(base):
                return None
            return round((float(current) / float(base) - 1) * 100, 2)

        if latest_date < target_date:
            remaining_gaps.append(
                f"{symbol} 历史行情仅到 {latest_date.isoformat()}，目标日期为 {target_date.isoformat()}"
            )
        if quote_error:
            remaining_gaps.append(f"{symbol} 实时行情不可用：{quote_error}")
        snapshots.append({
            "symbol": symbol,
            "quote": _jsonable(quote),
            "quote_error": quote_error,
            "history": {
                "latest_date": latest_date.isoformat(),
                "target_date": target_date.isoformat(),
                "latest_close": round(latest_close, 4),
                "return_5d_pct": period_return(5),
                "return_20d_pct": period_return(20),
                "return_60d_pct": period_return(60),
                "ma20": round(ma20, 4) if ma20 is not None else None,
                "price_vs_ma20_pct": (
                    round((latest_close / ma20 - 1) * 100, 2)
                    if ma20
                    else None
                ),
                "amount_ratio_5d_pct": ratio(amount_5, amount_20),
                "volume_ratio_5d_pct": ratio(volume_5, volume_20),
                "rows": int(len(history)),
            },
        })
    return {
        "retrieved_at": _now_iso(),
        "verification_status": "partial" if remaining_gaps else "complete",
        "snapshots": snapshots,
        "remaining_gaps": remaining_gaps,
        "boundary": "实时行情可能来自降级数据源；历史指标来自本地冷数据。",
    }


def _rotation_refresh(_: dict[str, Any]) -> dict[str, Any]:
    before = load_rotation_status()
    bundle = build_rotation_bundle()
    after = load_rotation_status()
    return {
        "retrieved_at": _now_iso(),
        "verification_status": "complete" if after.get("status") == "complete" else "partial",
        "remaining_gaps": (
            []
            if after.get("status") == "complete"
            else [f"轮动底层数据状态仍为 {after.get('status') or 'unknown'}"]
        ),
        "before_status": before.get("status"),
        "after_status": after.get("status"),
        "as_of": bundle.get("as_of"),
        "sector_count": len(bundle.get("sectors", [])),
        "summary": bundle.get("summary", {}),
        "potential_opportunities": [
            {
                "sector_id": item.get("sector_id"),
                "name": item.get("name"),
                "selected_symbol": item.get("selected_symbol"),
                "latest_date": item.get("latest_date"),
                "score": item.get("score", {}).get("total"),
                "data_quality": item.get("data_quality"),
            }
            for item in bundle.get("potential_opportunities", [])[:5]
        ],
        "boundary": (
            "该工具重建轮动计算，不绕过冷数据边界；若底层行情陈旧，结果仍会标记为 stale。"
        ),
    }


def _event_snapshot(arguments: dict[str, Any]) -> dict[str, Any]:
    context = build_portfolio_agent_context(force=False)
    radar = context.get("facts", {}).get("market_events", {})
    query = str(arguments.get("query") or "")
    asks_for_reaction = bool(re.search(r"后|反应|落地|影响|变化", query))
    remaining_gaps = (
        ["事件雷达只能确认日程与预设影响，尚未取得事件落地后的市场反应数据"]
        if asks_for_reaction
        else []
    )
    return {
        "retrieved_at": _now_iso(),
        "verification_status": "partial" if remaining_gaps else "complete",
        "remaining_gaps": remaining_gaps,
        "registry_updated_at": radar.get("registry_updated_at"),
        "high_impact_count": radar.get("high_impact_count"),
        "next_event": radar.get("next_event"),
        "events": [
            {
                key: event.get(key)
                for key in (
                    "event_id",
                    "date",
                    "title",
                    "status",
                    "impact_level",
                    "days_until",
                    "portfolio_readout",
                )
            }
            for event in radar.get("events", [])[:8]
        ],
        "boundary": radar.get("boundary"),
    }


def _disclosure_snapshot(arguments: dict[str, Any]) -> dict[str, Any]:
    symbols = list(dict.fromkeys(
        compact_symbol(str(value))
        for value in arguments.get("symbols") or []
        if value
    ))
    if not symbols:
        raise ValueError("disclosure_snapshot 需要至少一个证券代码")
    snapshots: list[dict[str, Any]] = []
    remaining_gaps: list[str] = []
    for symbol in symbols:
        facts = get_disclosure_facts(symbol, force=False)
        verification = load_disclosure_verification(symbol)
        if not facts.get("success"):
            remaining_gaps.append(
                f"{symbol} 公告与调研索引不可用：{facts.get('message') or 'unknown'}"
            )
        snapshots.append({
            "symbol": symbol,
            "data_status": facts.get("data_status"),
            "announcements": (facts.get("data") or {}).get("announcements", [])[:10],
            "surveys": (facts.get("data") or {}).get("surveys", [])[:10],
            "thesis_verification": {
                key: (verification or {}).get(key)
                for key in ("status", "generated_at", "counts", "overall_summary", "items")
            } if verification else None,
        })
    return {
        "retrieved_at": _now_iso(),
        "verification_status": "partial" if remaining_gaps else "complete",
        "snapshots": snapshots,
        "remaining_gaps": remaining_gaps,
        "boundary": "公告索引与调研记录用于事实核查；Thesis 结论仅采用已通过公告原文引用校验的项目。",
    }


def _execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if tool_name == "stock_snapshot":
        return _stock_snapshot(arguments)
    if tool_name == "rotation_refresh":
        return _rotation_refresh(arguments)
    if tool_name == "event_snapshot":
        return _event_snapshot(arguments)
    if tool_name == "disclosure_snapshot":
        return _disclosure_snapshot(arguments)
    raise ValueError(f"工具 {tool_name} 不在自动执行白名单中")


def _failure_category(error: Exception) -> tuple[str, bool]:
    text = str(error).lower()
    if any(token in text for token in ("timeout", "timed out", "连接", "network", "offline", "暂时", "rate limit")):
        return "transient_source_error", True
    if any(token in text for token in ("需要至少", "不在自动执行白名单", "人工核查", "invalid", "缺少")):
        return "invalid_task", False
    return "tool_error", True


def recover_interrupted_tasks(*, stale_minutes: int = 15) -> list[dict[str, Any]]:
    cutoff = _now() - timedelta(minutes=max(1, stale_minutes))
    recovered: list[dict[str, Any]] = []
    with _LOCK:
        items = _read_tasks()
        for task in items:
            if task.get("status") != "running":
                continue
            started_at = task.get("started_at")
            try:
                started = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                started = cutoff - timedelta(seconds=1)
            if started > cutoff:
                continue
            task["status"] = "pending"
            task["updated_at"] = _now_iso()
            task["recovery_count"] = int(task.get("recovery_count") or 0) + 1
            task["error"] = "检测到上次执行中断，已恢复到待执行队列"
            task["failure_category"] = "interrupted"
            recovered.append(task)
        if recovered:
            _write_tasks(items)
    return recovered


def task_health() -> dict[str, Any]:
    items = _read_tasks()
    status_counts: dict[str, int] = {}
    failure_counts: dict[str, int] = {}
    for task in items:
        status = str(task.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        category = task.get("failure_category")
        if category:
            failure_counts[str(category)] = failure_counts.get(str(category), 0) + 1
    return {
        "total": len(items),
        "status_counts": status_counts,
        "failure_counts": failure_counts,
        "retryable_count": sum(
            1 for task in items
            if task.get("status") in {"pending", "retry_wait"}
            and task.get("tool", {}).get("auto_executable")
        ),
        "source_health": source_health(),
    }


def execute_task(task_id: str) -> dict[str, Any]:
    with _LOCK:
        items = _read_tasks()
        index = next((i for i, item in enumerate(items) if item.get("task_id") == task_id), None)
        if index is None:
            raise KeyError("核查任务不存在")
        task = items[index]
        tool = task.get("tool") or {}
        if not tool.get("auto_executable"):
            raise ValueError("该任务需要人工核查，不能自动执行")
        task.update({
            "status": "running",
            "started_at": _now_iso(),
            "updated_at": _now_iso(),
            "attempt_count": int(task.get("attempt_count") or 0) + 1,
            "error": None,
            "next_retry_at": None,
        })
        items[index] = task
        _write_tasks(items)

    try:
        payload = _execute_tool(str(tool.get("name")), dict(tool.get("arguments") or {}))
        result = {
            "evidence_ref": f"tool:{task_id}",
            "tool_name": tool.get("name"),
            "completed_at": _now_iso(),
            "payload": payload,
        }
        status = "partial" if payload.get("verification_status") == "partial" else "completed"
        error = None
    except Exception as exc:
        result = None
        category, retryable = _failure_category(exc)
        attempts = int(task.get("attempt_count") or 0)
        max_attempts = int(task.get("max_attempts") or 3)
        status = "retry_wait" if retryable and attempts < max_attempts else "failed"
        error = str(exc)[:500]
        retry_at = (
            (_now() + timedelta(minutes=min(60, 5 * (2 ** max(0, attempts - 1))))).isoformat()
            if status == "retry_wait"
            else None
        )
    else:
        category = None
        retry_at = None

    with _LOCK:
        items = _read_tasks()
        index = next(i for i, item in enumerate(items) if item.get("task_id") == task_id)
        items[index].update({
            "status": status,
            "completed_at": _now_iso(),
            "updated_at": _now_iso(),
            "result": result,
            "error": error,
            "failure_category": category,
            "last_error_at": _now_iso() if error else None,
            "next_retry_at": retry_at,
        })
        _write_tasks(items)
        updated = items[index]
    _record_source_attempt(
        str(tool.get("name") or "unknown"),
        status=status,
        failure_category=category,
    )
    return updated


def execute_pending_tasks(
    *,
    origin_run_id: str | None = None,
    planning_origins: set[str] | None = None,
) -> list[dict[str, Any]]:
    recover_interrupted_tasks()
    tasks = list_tasks(origin_run_id=origin_run_id, limit=500)
    now = _now()

    def due(task: dict[str, Any]) -> bool:
        if task.get("status") == "pending":
            return True
        if task.get("status") != "retry_wait":
            return False
        value = task.get("next_retry_at")
        if not value:
            return True
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")) <= now
        except ValueError:
            return True

    executable = [
        task for task in reversed(tasks)
        if due(task)
        and task.get("tool", {}).get("auto_executable")
        and (
            planning_origins is None
            or str(task.get("planning_origin") or "") in planning_origins
        )
    ]
    return [execute_task(str(task["task_id"])) for task in executable]


def task_evidence(*, origin_run_id: str) -> list[dict[str, Any]]:
    return [
        {
            "evidence_ref": task["result"]["evidence_ref"],
            "scope": "tool_verification",
            "task_id": task["task_id"],
            "subject": task.get("subject"),
            "evidence_type": task.get("evidence_type"),
            "success_criteria": task.get("success_criteria"),
            "facts": task["result"]["payload"],
        }
        for task in reversed(list_tasks(origin_run_id=origin_run_id, limit=100))
        if task.get("status") in {"completed", "partial"} and task.get("result")
    ]


def update_task_status(task_id: str, status: str) -> dict[str, Any]:
    if status not in {"pending", "manual_required", "dismissed"}:
        raise ValueError("不支持的任务状态")
    with _LOCK:
        items = _read_tasks()
        index = next((i for i, item in enumerate(items) if item.get("task_id") == task_id), None)
        if index is None:
            raise KeyError("核查任务不存在")
        items[index]["status"] = status
        items[index]["updated_at"] = _now_iso()
        _write_tasks(items)
        return items[index]
