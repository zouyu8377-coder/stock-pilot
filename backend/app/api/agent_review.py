import asyncio
import os

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agent_review import (
    generate_daily_review,
    generate_followup_review,
    get_agent_review_status,
    load_latest_review,
    list_review_history,
)
from app.agent_review.tasks import (
    execute_pending_tasks,
    execute_task,
    list_tasks,
    sync_review_tasks,
    update_task_status,
)
from app.agent_review.automation import (
    automation_status,
    get_automation_settings,
    mark_premarket_cycle_completed,
    run_premarket_cycle,
    run_automatic_cycle,
    update_automation_settings,
)
from app.agent_review.outcomes import (
    annotate_portfolio_action,
    capture_portfolio_actions,
    evaluate_portfolio_actions,
    evaluate_recommendations,
    list_outcomes,
)
from app.agent_review.reports import build_monthly_report
from app.agent_review.learning_policy import learning_policy_snapshot


router = APIRouter(prefix="/agent/review", tags=["agent-review"])
_review_lock = asyncio.Lock()


class AutomationSettingsUpdate(BaseModel):
    enabled: bool | None = None
    run_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    premarket_enabled: bool | None = None
    premarket_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    weekdays_only: bool | None = None
    auto_execute_tools: bool | None = None
    auto_model_review: bool | None = None
    max_model_calls_per_day: int | None = Field(default=None, ge=0, le=3)


class ActionAnnotation(BaseModel):
    confirmed: bool
    reason: str | None = Field(default=None, max_length=500)
    dismissed: bool = False


@router.get("/status")
def agent_review_status():
    return {"success": True, "data": get_agent_review_status()}


@router.get("/latest")
def latest_agent_review():
    data = load_latest_review()
    if not data:
        raise HTTPException(status_code=404, detail="尚未生成 AI 复盘")
    return {"success": True, "data": data}


@router.get("/history")
def agent_review_history(limit: int = Query(10, ge=1, le=50)):
    return {"success": True, "items": list_review_history(limit)}


def _latest_tasks() -> tuple[dict, list[dict]]:
    latest = load_latest_review()
    if not latest:
        raise HTTPException(status_code=404, detail="尚未生成 AI 复盘")
    tasks = list_tasks(origin_run_id=latest["run_id"])
    if not tasks:
        tasks = sync_review_tasks(latest)
    return latest, tasks


@router.get("/tasks")
def agent_review_tasks():
    latest, tasks = _latest_tasks()
    return {
        "success": True,
        "origin_run_id": latest["run_id"],
        "items": tasks,
    }


@router.post("/tasks/{task_id}/execute")
async def execute_agent_review_task(task_id: str):
    try:
        task = await asyncio.to_thread(execute_task, task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "data": task}


@router.patch("/tasks/{task_id}/status")
def change_agent_review_task_status(
    task_id: str,
    status: str = Query(..., pattern="^(pending|manual_required|dismissed)$"),
):
    try:
        task = update_task_status(task_id, status)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "data": task}


@router.post("/tasks/execute-pending")
async def execute_pending_agent_review_tasks():
    latest, _ = _latest_tasks()
    results = await asyncio.to_thread(
        execute_pending_tasks,
        origin_run_id=latest["run_id"],
    )
    return {"success": True, "items": results}


@router.post("/daily")
async def create_daily_agent_review(force_context: bool = Query(False)):
    if _review_lock.locked():
        raise HTTPException(status_code=409, detail="已有复盘任务正在运行")
    timeout_seconds = float(os.getenv("AGENT_REVIEW_REQUEST_TIMEOUT_SECONDS", "240"))
    async with _review_lock:
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(generate_daily_review, force_context=force_context),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise HTTPException(status_code=504, detail="AI 复盘超时，请稍后重试") from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"AI 复盘失败：{str(exc)}") from exc
    return {"success": True, "data": result}


@router.post("/cycle")
async def run_agent_review_cycle():
    if _review_lock.locked():
        raise HTTPException(status_code=409, detail="已有复盘任务正在运行")
    latest, _ = _latest_tasks()
    timeout_seconds = float(os.getenv("AGENT_REVIEW_REQUEST_TIMEOUT_SECONDS", "240")) + 90
    async with _review_lock:
        try:
            executed = await asyncio.to_thread(
                execute_pending_tasks,
                origin_run_id=latest["run_id"],
            )
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    generate_followup_review,
                    parent_run_id=latest["run_id"],
                ),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise HTTPException(status_code=504, detail="核查复盘超时，请稍后重试") from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"核查复盘失败：{str(exc)}") from exc
    return {
        "success": True,
        "data": result,
        "executed_tasks": executed,
    }


@router.get("/automation")
def get_agent_automation_status():
    return {"success": True, "data": automation_status()}


@router.put("/automation/settings")
def save_agent_automation_settings(payload: AutomationSettingsUpdate):
    try:
        settings = update_automation_settings(payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "data": settings}


@router.post("/automation/run")
async def run_agent_automation_now():
    try:
        result = await asyncio.to_thread(run_automatic_cycle, trigger="manual")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"自动任务循环失败：{str(exc)}") from exc
    return {"success": True, "data": result}


@router.post("/automation/premarket/run")
async def run_agent_premarket_now():
    try:
        result = await asyncio.to_thread(run_premarket_cycle, trigger="premarket")
        mark_premarket_cycle_completed()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"开盘前取证失败：{str(exc)}") from exc
    return {"success": True, "data": result}


@router.get("/outcomes")
def get_agent_outcomes():
    capture_portfolio_actions()
    evaluate_recommendations()
    evaluate_portfolio_actions()
    return {"success": True, "data": list_outcomes()}


@router.get("/outcomes/monthly")
def get_agent_monthly_report(
    month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
):
    return {"success": True, "data": build_monthly_report(month)}


@router.get("/learning-policies")
def get_agent_learning_policies():
    return {"success": True, "data": learning_policy_snapshot()}


@router.patch("/outcomes/actions/{action_id}")
def annotate_agent_portfolio_action(action_id: str, payload: ActionAnnotation):
    try:
        result = annotate_portfolio_action(
            action_id,
            confirmed=payload.confirmed,
            reason=payload.reason,
            dismissed=payload.dismissed,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "data": result}
