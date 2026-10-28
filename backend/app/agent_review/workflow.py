from __future__ import annotations

import threading
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.agent_review import automation as cycle
from app.agent_review import runtime
from app.agent_review.research import plan_research_tasks, account_fingerprint


STATE_PATH = cycle.AUTOMATION_DIR / "workflow.json"
QUEUE_PATH = cycle.AUTOMATION_DIR / "account_update_queue.json"
_lock = threading.RLock()
_worker: threading.Thread | None = None


def _save(state: dict[str, Any]) -> None:
    with _lock:
        cycle._write_json(STATE_PATH, state)


def workflow_status() -> dict[str, Any]:
    current = runtime.status()
    if current.get("status") != "idle":
        source = current.get("source", "workflow")
        current["retry"] = runtime.retry_state(source)
        return current
    with _lock:
        state = cycle._read_json(STATE_PATH, {"status": "idle", "steps": []})
        if state.get("status") == "running" and not (_worker and _worker.is_alive()):
            state.update(status="interrupted", error="服务已重启，上次分析未完成；可重新巡检。")
            _save(state)
        return state


@runtime.tracked("workflow")
def _run(state: dict[str, Any], *, trigger="workflow") -> None:
    acquired = cycle._RUN_LOCK.acquire(blocking=False)
    try:
        if not acquired:
            raise RuntimeError("已有自动巡检或复盘运行，请等待其完成")
        from app.agent_review.plan_engine import settings as plan_settings, run as run_local
        if plan_settings()["external_only"]:
            runtime.progress("inspect", "执行本地取证、计划条件检查与持仓变化回顾；不调用模型")
            result = run_local()
            if result["status"] != "completed":
                raise RuntimeError(result.get("error") or "已有本地检查在运行，请查看计划监控进度")
            state.update(status="completed", model_calls=0, external_discussion_required=True)
            for step in state["steps"]:
                step["status"] = "completed" if step["key"] in {"inspect", "review"} else "skipped"
            runtime.progress("review", "本地检查完成；研判与计划修正等待外部模型讨论")
            return state
        settings = cycle.get_automation_settings()

        def stage(name: str) -> None:
            runtime.progress(name, {"inspect": "巡检账户与证据", "analyze": "生成综合分析", "advise": "发布建议", "review": "回顾历史表现"}[name])
            for step in state["steps"]:
                if step["status"] == "running":
                    step["status"] = "completed"
            next(step for step in state["steps"] if step["key"] == name)["status"] = "running"
            _save(state)

        stage("inspect")
        cycle.capture_portfolio_actions()
        cycle.invalidate_dashboard_cache()
        latest = cycle.load_latest_review()
        origin = latest["run_id"] if latest else f"research-{account_fingerprint()[:12]}"
        executed = []
        if settings["auto_execute_tools"]:
            plan_research_tasks(origin, int(settings["max_proactive_tasks_per_day"]))
            if latest:
                cycle.sync_review_tasks(latest)
                cycle.plan_coverage_gap_tasks(latest, max_tasks=int(settings["max_proactive_tasks_per_day"]), force=True)
            executed = cycle.execute_pending_tasks(
                origin_run_id=origin, max_tasks=int(settings["max_proactive_tasks_per_day"]),
            )
        state["evidence"] = {
            "executed": len(executed),
            "partial": sum(item.get("status") == "partial" for item in executed),
            "failed": sum(item.get("status") in {"failed", "retry_wait"} for item in executed),
        }
        stage("analyze")
        state["model_calls"] = 1
        # Rebuild the context after tools finish; never present the old review as a new result.
        executed_refs = {str((item.get("result") or {}).get("evidence_ref") or f"tool:{item.get('task_id')}")
                         for item in executed if item.get("status") in {"completed", "partial"}}
        evidence = [item for item in cycle.task_evidence(origin_run_id=origin)
                    if item.get("evidence_ref") in executed_refs] if executed else []
        latest = cycle.generate_daily_review(force_context=True, tool_evidence=evidence)
        state["review_run_id"] = latest["run_id"]
        state["unchanged"] = latest.get("unchanged", False)
        if state["unchanged"]:
            state["model_calls"] = 0
        stage("advise")
        cycle.sync_review_tasks(latest)
        # New findings get one bounded collection pass in this same cycle.
        remaining = max(0, int(settings["max_proactive_tasks_per_day"]) - len(executed))
        if settings["auto_execute_tools"] and remaining and not state["unchanged"]:
            runtime.progress("inspect", "执行本轮新发现的核查任务")
            fresh_tasks = cycle.execute_pending_tasks(origin_run_id=latest["run_id"], max_tasks=remaining)
            state["new_task_results"] = {"executed": len(fresh_tasks),
                "usable": sum(item.get("status") in {"completed", "partial"} for item in fresh_tasks)}
            if any(item.get("status") == "completed" for item in fresh_tasks):
                state["followup_pending"] = True
                # Manual runs have no daily quota, but only one evidence follow-up per run.
                try:
                    state["model_calls"] += 1
                    latest = cycle.generate_followup_review(parent_run_id=latest["run_id"])
                    state["review_run_id"] = latest["run_id"]
                    state["followup_pending"] = False
                except Exception as exc:
                    state["followup_note"] = f"新证据已保存，结论复核尚未完成：{str(exc)[:300]}"
        cycle.invalidate_dashboard_cache()
        stage("review")
        cycle.evaluate_portfolio_actions()
        cycle.evaluate_recommendations()
        state["steps"][-1]["status"] = "completed"
        state["status"] = "completed"
    except Exception as exc:
        state.update(status="failed", error=str(exc)[:1000])
        for step in state["steps"]:
            if step["status"] == "running":
                step["status"] = "failed"
    finally:
        state["completed_at_local"] = datetime.now(cycle.TZ).isoformat()
        _save(state)
        if acquired:
            try:
                runs = cycle._runs()
                runs.append({**state, "trigger": trigger, "automation_run_id": state["job_id"]})
                cycle._write_json(cycle.RUNS_PATH, runs[-200:])
            finally:
                cycle._RUN_LOCK.release()
    return state


def start_workflow(*, trigger="workflow") -> dict[str, Any]:
    global _worker
    with _lock:
        current = runtime.status()
        if current.get("status") in {"running", "cancelling"}:
            return workflow_status()
        if _worker and _worker.is_alive():
            return workflow_status()
        if cycle._RUN_LOCK.locked():
            raise RuntimeError("已有自动巡检或复盘运行，请等待其完成")
        state = {
            "job_id": f"workflow-{uuid4().hex[:12]}", "status": "running",
            "started_at_local": datetime.now(cycle.TZ).isoformat(),
            "model_calls": 0, "error": None,
            "steps": [{"key": key, "status": "pending"} for key in ("inspect", "analyze", "advise", "review")],
        }
        _save(state)
        _worker = threading.Thread(target=_run, args=(state,), kwargs={"trigger": trigger}, daemon=True, name="agent-workflow")
        _worker.start()
        return dict(state)


def queue_account_update():
    from app.agent_review.research import account_fingerprint
    with _lock:
        if not cycle.get_automation_settings().get("analysis_after_account_update"):
            return {"status": "disabled"}
        queued = {"status": "pending", "account_fingerprint": account_fingerprint(), "queued_at": datetime.now(cycle.TZ).isoformat()}
        try:
            cycle._write_json(QUEUE_PATH, queued)
        except OSError:
            # The portfolio is already committed; a queue failure must not imply a failed save.
            return {"status": "failed", "detail": "账户已保存，自动分析排队失败，请手动更新分析"}
        return queued


def start_pending_account_analysis():
    with _lock:
        queued = cycle._read_json(QUEUE_PATH, {})
        if queued.get("status") != "pending" or not cycle.get_automation_settings().get("analysis_after_account_update"):
            return
        if runtime.status().get("status") in {"running", "cancelling"} or cycle._RUN_LOCK.locked():
            return
        if not runtime.retry_state("account_update")["allowed"]:
            return
        state = start_workflow(trigger="account_update")
        cycle._write_json(QUEUE_PATH, {**queued, "status": "started", "job_id": state["job_id"]})
