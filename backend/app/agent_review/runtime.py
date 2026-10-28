from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
PATH = Path(__file__).resolve().parents[2] / "data/agent_automation/task_runtime.json"
_lock = threading.RLock()
_owner = None
_state = None


class TaskCancelled(RuntimeError):
    pass


def _now():
    return datetime.now(TZ)


def _read():
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"latest": {"status": "idle", "steps": []}, "history": []}


def _write():
    payload = _read()
    payload["latest"] = _state
    PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temp.replace(PATH)


def status():
    global _state
    with _lock:
        value = dict(_state or _read()["latest"])
        if value.get("status") in {"running", "cancelling"} and _owner is None:
            value.update(status="interrupted", completed_at_local=_now().isoformat(), error="服务重启，任务中断；不会自动续发模型请求。")
            _state = value
            _write()
            payload = _read()
            if not any(item.get("job_id") == value.get("job_id") for item in payload.get("history", [])):
                payload["history"] = [*payload.get("history", []), value][-100:]
                temp = PATH.with_suffix(".tmp")
                temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                temp.replace(PATH)
        now = _now()
        for source, target in (("started_at_local", "elapsed_seconds"), ("last_progress_at", "idle_seconds")):
            if value.get(source):
                end = datetime.fromisoformat(value["completed_at_local"]) if value.get("completed_at_local") else now
                value[target] = max(0, int((end - datetime.fromisoformat(value[source])).total_seconds()))
        value["overdue"] = bool(_owner and value.get("stage_deadline") and now > datetime.fromisoformat(value["stage_deadline"]))
        return value


def checkpoint():
    with _lock:
        if _owner != threading.get_ident() or not _state:
            return
        if _state.get("cancel_requested"):
            raise TaskCancelled("已取消后续步骤；已发出的请求结束后停止，旧分析保留。")
        if _state.get("stage_deadline") and _now() > datetime.fromisoformat(_state["stage_deadline"]):
            raise TimeoutError("当前阶段超过时限，停止后续步骤；已取得证据保留。")
        if (_now() - datetime.fromisoformat(_state["started_at_local"])).total_seconds() > 900:
            raise TimeoutError("任务超过15分钟总时限，停止后续步骤。")


def progress(stage, detail, *, completed=None, total=None, timeout=300):
    checkpoint()
    with _lock:
        if _owner != threading.get_ident() or not _state:
            return
        now = _now().isoformat()
        _state.update(stage=stage, detail=detail, last_progress_at=now,
                      stage_deadline=(_now() + timedelta(seconds=timeout)).isoformat(),
                      completed_items=completed, total_items=total)
        _write()


AUTOMATIC_SOURCES = frozenset({"scheduled", "premarket", "account_update"})


def is_automatic(source):
    return source in AUTOMATIC_SOURCES


def model_attempt():
    from app.agent_review.plan_engine import settings as plan_settings
    if plan_settings()["external_only"]:
        raise RuntimeError("当前为外部模型协作模式，平台内分析模型已停用；请导出讨论包")
    checkpoint()
    with _lock:
        if _owner == threading.get_ident() and _state:
            if is_automatic(_state.get("source")) and not _state.get("model_requests"):
                from app.agent_review.automation import get_automation_settings
                today = _now().date().isoformat()
                used = sum(bool(item.get("model_requests")) for item in _read().get("history", [])
                           if is_automatic(item.get("source"))
                           and str(item.get("started_at_local", "")).startswith(today))
                if used >= int(get_automation_settings()["max_model_calls_per_day"]):
                    raise RuntimeError("今日自动分析预算已用完（自动任务失败请求也计入）；手动分析不受此限制。")
            _state["model_requests"] = _state.get("model_requests", 0) + 1
            _write()


def model_usage(usage):
    with _lock:
        if _owner == threading.get_ident() and _state:
            _state["tokens"] = _state.get("tokens", 0) + int(usage.get("total_tokens") or 0)
            _write()


def cancel():
    with _lock:
        if _owner and _state:
            _state.update(cancel_requested=True, status="cancelling")
            _write()
        return status()


def tracked(source):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            global _owner, _state
            ident = threading.get_ident()
            with _lock:
                nested = _owner == ident
                if _owner and not nested:
                    raise RuntimeError("已有任务运行，请查看任务进度")
                if not nested:
                    status()
                    _owner = ident
                    job_id = args[0].get("job_id") if source == "workflow" and args and isinstance(args[0], dict) else None
                    _state = {"job_id": job_id or f"task-{uuid4().hex[:12]}", "source": kwargs.get("trigger", source),
                              "status": "running", "started_at_local": _now().isoformat(),
                              "last_progress_at": _now().isoformat(), "stage": "inspect",
                              "detail": "读取账户与任务上下文", "model_requests": 0, "tokens": 0, "steps": []}
                    _write()
            if nested:
                checkpoint()
                return function(*args, **kwargs)
            try:
                result = function(*args, **kwargs)
                checkpoint()
                with _lock:
                    _state["status"] = (result or {}).get("status", "completed") if isinstance(result, dict) else "completed"
                    if _state["status"] not in {"completed", "failed", "cancelled"}:
                        _state["status"] = "failed" if _state["status"] in {"retry_wait", "manual_required"} else "completed"
                    if isinstance(result, dict):
                        for key in ("error", "review_run_id", "steps", "evidence", "new_task_results", "followup_pending", "followup_note", "unchanged"):
                            if result.get(key): _state[key] = result[key]
                return result
            except Exception as exc:
                with _lock:
                    _state.update(status="cancelled" if isinstance(exc, TaskCancelled) else "failed", error=str(exc)[:1000])
                raise
            finally:
                with _lock:
                    try:
                        _state["completed_at_local"] = _now().isoformat()
                        _write()
                        payload = _read()
                        payload["history"] = [*payload.get("history", []), dict(_state)][-100:]
                        temp = PATH.with_suffix(".tmp")
                        temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                        temp.replace(PATH)
                    finally:
                        _owner = None
        return wrapped
    return decorate


def retry_state(source):
    if not is_automatic(source):
        return {"allowed": True, "failures": 0, "next_retry_at": None}
    today = _now().date().isoformat()
    attempts = [item for item in _read().get("history", [])
                if item.get("source") == source and str(item.get("started_at_local", "")).startswith(today)]
    failed = [item for item in attempts if item.get("status") in {"failed", "cancelled", "interrupted"}]
    if not failed:
        return {"allowed": True, "failures": 0, "next_retry_at": None}
    next_retry = datetime.fromisoformat(failed[-1]["completed_at_local"]) + timedelta(minutes=15)
    blocked = len(failed) >= 2 or failed[-1].get("status") == "cancelled"
    return {"allowed": not blocked and _now() >= next_retry, "failures": len(failed),
            "next_retry_at": None if blocked else next_retry.isoformat(), "paused_today": blocked}
