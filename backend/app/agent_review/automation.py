from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo
from app.agent_review import runtime

from app.agent_review.outcomes import (
    build_weekly_operation_summary,
    capture_portfolio_actions,
    confirmed_actions_on_local_date,
    evaluate_portfolio_actions,
    evaluate_recommendations,
    list_outcomes,
)
from app.agent_review.reports import build_monthly_report
from app.agent_review.learning_policy import refresh_learning_policies
from app.agent_review.service import (
    generate_daily_review,
    generate_followup_review,
    load_latest_review,
)
from app.agent_review.tasks import (
    COVERAGE_GAP_ORIGIN,
    execute_pending_tasks,
    list_tasks,
    plan_coverage_gap_tasks,
    sync_review_tasks,
    task_evidence,
    task_health,
)
from app.rotation.service import build_rotation_bundle
from app.portfolio.dashboard_cache import invalidate_dashboard_cache
from app.agent_review.coverage_planner import build_coverage_plan


BACKEND_DIR = Path(__file__).resolve().parents[2]
AUTOMATION_DIR = BACKEND_DIR / "data" / "agent_automation"
SETTINGS_PATH = AUTOMATION_DIR / "settings.json"
RUNS_PATH = AUTOMATION_DIR / "runs.json"
TZ = ZoneInfo("Asia/Shanghai")


def _is_weekly_review_day(value: datetime) -> bool:
    return value.astimezone(TZ).weekday() == 4
_RUN_LOCK = threading.Lock()

DEFAULT_SETTINGS = {
    "analysis_after_account_update": False,
    "enabled": False,
    "run_time": "15:31",
    "premarket_enabled": True,
    "premarket_time": "08:45",
    "weekdays_only": True,
    "auto_execute_tools": True,
    "auto_model_review": True,
    "max_model_calls_per_day": 2,
    "max_proactive_tasks_per_day": 5,
    "last_scheduled_date": None,
    "last_premarket_date": None,
}

LOW_CONFIDENCE_ORIGINS = {"low_confidence_auto", "low_confidence_model_planned"}
PREMARKET_EVIDENCE_ORIGINS = {*LOW_CONFIDENCE_ORIGINS, COVERAGE_GAP_ORIGIN}
CONFIDENCE_REFRESH_TRIGGERS = {"premarket", "manual_confidence"}


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def get_automation_settings() -> dict[str, Any]:
    return {**DEFAULT_SETTINGS, **_read_json(SETTINGS_PATH, {})}


def update_automation_settings(payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_automation_settings()
    allowed = set(DEFAULT_SETTINGS) - {"last_scheduled_date", "last_premarket_date"}
    for key in allowed:
        if key in payload:
            settings[key] = payload[key]
    hour, minute = [int(value) for value in str(settings["run_time"]).split(":", 1)]
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("run_time 必须是 HH:MM")
    premarket_hour, premarket_minute = [int(value) for value in str(settings["premarket_time"]).split(":", 1)]
    if not (0 <= premarket_hour <= 23 and 0 <= premarket_minute <= 59):
        raise ValueError("premarket_time 必须是 HH:MM")
    calls = int(settings["max_model_calls_per_day"])
    if not 0 <= calls <= 3:
        raise ValueError("每日模型调用上限必须在 0 到 3 之间")
    settings["max_model_calls_per_day"] = calls
    proactive_tasks = int(settings["max_proactive_tasks_per_day"])
    if not 1 <= proactive_tasks <= 8:
        raise ValueError("每日主动取证上限必须在 1 到 8 之间")
    settings["max_proactive_tasks_per_day"] = proactive_tasks
    _write_json(SETTINGS_PATH, settings)
    return settings


def _runs() -> list[dict[str, Any]]:
    payload = _read_json(RUNS_PATH, [])
    return payload if isinstance(payload, list) else []


def _model_calls_today(*, trigger: str | None = None) -> int:
    today = datetime.now(TZ).date().isoformat()
    return sum(
        int(item.get("model_calls") or 0)
        for item in _runs()
        if str(item.get("started_at_local") or "").startswith(today)
        and (trigger is None or item.get("trigger") == trigger)
    )


def _confidence_refresh_model_calls_today() -> int:
    """Only scheduled morning refreshes consume the daily morning quota."""
    today = datetime.now(TZ).date().isoformat()
    return sum(
        int(item.get("model_calls") or 0)
        for item in _runs()
        if str(item.get("started_at_local") or "").startswith(today)
        and item.get("trigger") == "premarket"
    )


def _review_local_date(review: dict[str, Any] | None) -> str | None:
    if not review or not review.get("completed_at"):
        return None
    value = datetime.fromisoformat(str(review["completed_at"]).replace("Z", "+00:00"))
    return value.astimezone(TZ).date().isoformat()


@runtime.tracked("manual")
def run_automatic_cycle(*, trigger: str = "manual") -> dict[str, Any]:
    if not _RUN_LOCK.acquire(blocking=False):
        raise RuntimeError("自动任务循环正在运行")
    started = datetime.now(TZ)
    run = {
        "automation_run_id": f"automation-{uuid4().hex[:12]}",
        "trigger": trigger,
        "status": "running",
        "started_at_local": started.isoformat(),
        "completed_at_local": None,
        "model_calls": 0,
        "steps": [],
        "error": None,
    }
    try:
        settings = get_automation_settings()
        created_actions = capture_portfolio_actions()
        evaluated_actions = evaluate_portfolio_actions()
        evaluated_recommendations = evaluate_recommendations()
        loop_state = list_outcomes()
        run["steps"].append({
            "step": "outcome_review",
            "status": "completed",
            "created_actions": len(created_actions),
            "evaluated_actions": len(evaluated_actions),
            "evaluated_recommendations": len(evaluated_recommendations),
            "operation_samples": loop_state["summary"]["action_count"],
            "snapshot_changes": loop_state["summary"].get("snapshot_change_count", 0),
            "strategy_context_coverage_pct": (
                loop_state.get("loop_health", {}).get("strategy_context_coverage_pct")
            ),
            "matured_evaluation_rate_pct": (
                loop_state.get("loop_health", {}).get("matured_evaluation_rate_pct")
            ),
        })
        policy_registry = refresh_learning_policies(loop_state)
        run["steps"].append({
            "step": "learning_policy_refresh",
            "status": "completed",
            **policy_registry.get("summary", {}),
        })
        monthly_report = build_monthly_report()
        run["steps"].append({
            "step": "monthly_scorecard",
            "status": "completed",
            "month": monthly_report["month"],
            "evaluated_recommendations": monthly_report["recommendations"]["evaluated"],
            "evaluated_confirmed_actions": monthly_report["confirmed_actions"]["evaluated"],
        })

        rotation = build_rotation_bundle()
        run["steps"].append({
            "step": "rotation_preflight",
            "status": "completed",
            "as_of": rotation.get("as_of"),
            "data_status": (
                "stale"
                if int(rotation.get("summary", {}).get("stale_count") or 0) > 0
                else "complete"
            ),
            "sector_count": len(rotation.get("sectors", [])),
        })

        latest = load_latest_review()
        today = started.date().isoformat()
        manual = not runtime.is_automatic(trigger)
        call_budget = 2 if manual else max(
            0,
            int(settings["max_model_calls_per_day"])
            - _model_calls_today(trigger=trigger),
        )
        review_required = manual or trigger == "scheduled" or _review_local_date(latest) != today
        if settings["auto_model_review"] and call_budget > 0 and review_required:
            run["model_calls"] += 1
            latest = generate_daily_review(force_context=False)
            review_step = "weekly_review" if _is_weekly_review_day(started) else "daily_review"
            run["steps"].append({"step": review_step, "status": "completed", "run_id": latest["run_id"]})
        elif latest:
            sync_review_tasks(latest)

        executed = []
        if latest and settings["auto_execute_tools"]:
            executed = execute_pending_tasks(origin_run_id=None)
            run["steps"].append({
                "step": "tool_execution",
                "status": "completed",
                "executed": len(executed),
                "partial": sum(1 for item in executed if item.get("status") == "partial"),
                "failed": sum(1 for item in executed if item.get("status") == "failed"),
            })

        remaining_budget = (2 - int(run["model_calls"])) if manual else max(
            0,
            int(settings["max_model_calls_per_day"])
            - _model_calls_today(trigger=trigger)
            - int(run["model_calls"]),
        )
        if (
            latest
            and trigger != "scheduled"
            and settings["auto_model_review"]
            and remaining_budget > 0
            and task_evidence(origin_run_id=latest["run_id"])
        ):
            run["model_calls"] += 1
            latest = generate_followup_review(parent_run_id=latest["run_id"])
            run["steps"].append({"step": "followup_review", "status": "completed", "run_id": latest["run_id"]})
            if settings["auto_execute_tools"]:
                followup_executed = execute_pending_tasks(origin_run_id=latest["run_id"])
                if followup_executed:
                    run["steps"].append({
                        "step": "followup_tool_execution",
                        "status": "completed",
                        "executed": len(followup_executed),
                        "note": "新证据将在下一次复盘中吸收；单轮最多进行一次后续模型复核。",
                    })

        run["status"] = "completed"
        return run
    except Exception as exc:
        run["status"] = "failed"
        run["error"] = str(exc)[:1000]
        raise
    finally:
        run["completed_at_local"] = datetime.now(TZ).isoformat()
        runs = _runs()
        runs.append(run)
        _write_json(RUNS_PATH, runs[-200:])
        _RUN_LOCK.release()


@runtime.tracked("premarket")
def run_premarket_cycle(*, trigger: str = "premarket") -> dict[str, Any]:
    """Verify low-confidence conclusions before the market without duplicating a close review."""
    if not _RUN_LOCK.acquire(blocking=False):
        raise RuntimeError("自动任务循环正在运行")
    started = datetime.now(TZ)
    run = {
        "automation_run_id": f"automation-{uuid4().hex[:12]}",
        "trigger": trigger,
        "status": "running",
        "started_at_local": started.isoformat(),
        "completed_at_local": None,
        "model_calls": 0,
        "steps": [],
        "error": None,
    }
    try:
        settings = get_automation_settings()
        latest = load_latest_review()
        if not latest:
            run["steps"].append({
                "step": "premarket_evidence_check",
                "status": "skipped",
                "reason": "尚无复盘结论可供核查",
            })
            run["status"] = "completed"
            return run

        sync_review_tasks(latest)
        coverage_plan = plan_coverage_gap_tasks(
            latest,
            max_tasks=int(settings["max_proactive_tasks_per_day"]),
        )
        low_confidence_tasks = [
            item
            for item in list_tasks(origin_run_id=latest["run_id"], limit=500)
            if str(item.get("planning_origin") or "") in PREMARKET_EVIDENCE_ORIGINS
            and item.get("status") in {"pending", "retry_wait"}
        ]
        executed = []
        if settings["auto_execute_tools"]:
            executed = execute_pending_tasks(
                origin_run_id=latest["run_id"],
                planning_origins=PREMARKET_EVIDENCE_ORIGINS,
                max_tasks=int(settings["max_proactive_tasks_per_day"]),
            )
        usable_evidence = [
            item for item in executed
            if item.get("status") in {"completed", "partial"}
        ]
        run["steps"].append({
            "step": "proactive_coverage_planning",
            "status": "completed",
            "created": coverage_plan["created_count"],
            "candidate_count": coverage_plan["summary"]["candidate_count"],
            "coverage_before": coverage_plan["summary"],
            "budget": int(settings["max_proactive_tasks_per_day"]),
        })
        invalidate_dashboard_cache()
        coverage_after = build_coverage_plan(max_candidates=0, force=True)["summary"]
        run["steps"].append({
            "step": "premarket_evidence_check",
            "status": "completed",
            "candidate_count": len(low_confidence_tasks),
            "executed": len(executed),
            "usable_evidence": len(usable_evidence),
            "failed": sum(1 for item in executed if item.get("status") == "failed"),
            "coverage_before": coverage_plan["summary"],
            "coverage_after": coverage_after,
        })

        model_budget_available = not runtime.is_automatic(trigger) or _confidence_refresh_model_calls_today() < 1
        decision_relevant_evidence = [
            item for item in usable_evidence
            if (item.get("coverage_gap") or {}).get("decision_sensitive", True)
        ]
        if settings["auto_model_review"] and decision_relevant_evidence and model_budget_available:
            run["model_calls"] = 1
            updated = generate_followup_review(parent_run_id=latest["run_id"])
            run["steps"].append({
                "step": "premarket_confidence_update",
                "status": "completed",
                "run_id": updated["run_id"],
                "parent_run_id": latest["run_id"],
            })
        elif usable_evidence:
            run["steps"].append({
                "step": "premarket_confidence_update",
                "status": "deferred",
                "reason": "DeepSeek未启用或今日晨间模型调用已完成，新证据保留到下一次复盘",
            })
        run["status"] = "completed"
        return run
    except Exception as exc:
        run["status"] = "failed"
        run["error"] = str(exc)[:1000]
        raise
    finally:
        run["completed_at_local"] = datetime.now(TZ).isoformat()
        runs = _runs()
        runs.append(run)
        _write_json(RUNS_PATH, runs[-200:])
        _RUN_LOCK.release()


def automation_status() -> dict[str, Any]:
    settings = get_automation_settings()
    runs = _runs()
    now = datetime.now(TZ)
    today = now.date().isoformat()
    today_actions = confirmed_actions_on_local_date(today)
    latest_review = load_latest_review()
    latest_tasks = list_tasks(origin_run_id=latest_review.get("run_id"), limit=500) if latest_review else []
    low_confidence_tasks = [
        item for item in latest_tasks
        if str(item.get("planning_origin") or "") in LOW_CONFIDENCE_ORIGINS
        and item.get("status") in {"pending", "retry_wait"}
    ]
    latest_confidence_run = next(
        (item for item in reversed(runs) if item.get("trigger") in CONFIDENCE_REFRESH_TRIGGERS),
        None,
    )
    coverage_tasks = [
        item for item in latest_tasks
        if str(item.get("planning_origin") or "") == COVERAGE_GAP_ORIGIN
        and item.get("status") in {"pending", "retry_wait", "manual_required"}
    ]
    latest_coverage_plan = next(
        (
            step for step in reversed((latest_confidence_run or {}).get("steps", []))
            if step.get("step") == "proactive_coverage_planning"
        ),
        None,
    )
    latest_evidence_check = next(
        (
            step for step in reversed((latest_confidence_run or {}).get("steps", []))
            if step.get("step") == "premarket_evidence_check"
        ),
        None,
    )
    # Older runs did not persist the pre-refresh snapshot. The paired planning
    # step is from the same run and preserves the historical comparison.
    if latest_evidence_check and not latest_evidence_check.get("coverage_before") and latest_coverage_plan:
        previous_coverage = latest_coverage_plan.get("coverage_before")
        if previous_coverage:
            latest_evidence_check = {**latest_evidence_check, "coverage_before": previous_coverage}
    current_plan = build_coverage_plan(max_candidates=30) if latest_review else None
    current_coverage = current_plan["summary"] if current_plan else None
    return {
        "settings": settings,
        "running": _RUN_LOCK.locked(),
        "model_calls_today": _model_calls_today(),
        "scheduled_model_calls_today": _model_calls_today(trigger="scheduled"),
        "latest_run": runs[-1] if runs else None,
        "recent_runs": list(reversed(runs[-10:])),
        "task_health": task_health(),
        "trade_trigger": {
            "mode": "weekly_summary" if _is_weekly_review_day(now) else "confirmed_trade_after_close",
            "review_period": "weekly" if _is_weekly_review_day(now) else "daily",
            "run_time": settings["run_time"],
            "today_confirmed_action_count": len(today_actions),
            "has_confirmed_trade_today": bool(today_actions),
            "last_scheduled_date": settings.get("last_scheduled_date"),
        },
        "premarket_trigger": {
            "enabled": bool(settings.get("premarket_enabled")),
            "run_time": settings["premarket_time"],
            "pending_low_confidence_count": len(low_confidence_tasks),
            "last_premarket_date": settings.get("last_premarket_date"),
            "latest_run_completed_at": latest_confidence_run.get("completed_at_local") if latest_confidence_run else None,
            "model_call_policy": "有新增可用证据时最多调用DeepSeek一次；无任务或无新证据时不调用",
        },
        "coverage_planner": {
            "pending_count": len(coverage_tasks),
            "daily_budget": int(settings["max_proactive_tasks_per_day"]),
            "last_plan": latest_coverage_plan,
            "last_evidence_check": latest_evidence_check,
            "current_coverage": current_coverage,
            "remaining_gaps": (current_plan or {}).get("candidates", [])[:8],
            "policy": "按持仓权重、决策影响、事件紧迫度、数据陈旧度和自动可取性排序；只执行预算内任务。",
        },
        "latest_review_completed_at": latest_review.get("completed_at") if latest_review else None,
        "server_time": now.isoformat(),
    }


def should_run_scheduled_cycle() -> bool:
    if not runtime.retry_state("scheduled")["allowed"]:
        return False
    settings = get_automation_settings()
    if not settings["enabled"] or _RUN_LOCK.locked():
        return False
    now = datetime.now(TZ)
    if settings["weekdays_only"] and now.weekday() >= 5:
        return False
    if settings.get("last_scheduled_date") == now.date().isoformat():
        return False
    hour, minute = [int(value) for value in str(settings["run_time"]).split(":", 1)]
    if (now.hour, now.minute) < (hour, minute):
        return False
    if _is_weekly_review_day(now):
        return bool(build_weekly_operation_summary(reference_time=now).get("action_count"))
    return bool(confirmed_actions_on_local_date(now.date().isoformat()))


def should_run_premarket_cycle() -> bool:
    if not runtime.retry_state("premarket")["allowed"]:
        return False
    settings = get_automation_settings()
    if not settings["enabled"] or not settings.get("premarket_enabled") or _RUN_LOCK.locked():
        return False
    now = datetime.now(TZ)
    if settings["weekdays_only"] and now.weekday() >= 5:
        return False
    if settings.get("last_premarket_date") == now.date().isoformat():
        return False
    hour, minute = [int(value) for value in str(settings["premarket_time"]).split(":", 1)]
    if (now.hour, now.minute) < (hour, minute) or (now.hour, now.minute) >= (15, 30):
        return False
    latest = load_latest_review()
    if not latest:
        return False
    # Inspect the account even without trades or old pending tasks; run once after startup catch-up.
    return True


def mark_scheduled_cycle_completed() -> None:
    settings = get_automation_settings()
    settings["last_scheduled_date"] = datetime.now(TZ).date().isoformat()
    _write_json(SETTINGS_PATH, settings)


def mark_premarket_cycle_completed() -> None:
    settings = get_automation_settings()
    settings["last_premarket_date"] = datetime.now(TZ).date().isoformat()
    _write_json(SETTINGS_PATH, settings)
