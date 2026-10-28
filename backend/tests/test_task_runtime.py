from datetime import timedelta
import threading

import pytest
from app.agent_review import runtime, workflow, automation


@pytest.fixture(autouse=True)
def enable_legacy_mock_model(isolate_task_runtime):
    # These tests exercise the legacy budget path without provider requests.
    from app.agent_review.plan_engine import configure
    configure(False, False)


def test_automatic_task_is_visible_to_manual_entry_and_cancellable():
    entered, release = threading.Event(), threading.Event()
    published = []
    @runtime.tracked("premarket")
    def automatic():
        runtime.progress("inspect", "核验公告", completed=1, total=3)
        entered.set()
        release.wait(2)
        runtime.checkpoint()
        published.append(True)
    def run():
        try: automatic()
        except runtime.TaskCancelled: pass
    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert entered.wait(1)
        state = workflow.start_workflow()
        assert state["source"] == "premarket"
        assert state["completed_items"] == 1
        assert runtime.cancel()["status"] == "cancelling"
    finally:
        release.set()
        thread.join(3)
    assert not published
    assert runtime.status()["status"] == "cancelled"
    assert runtime.retry_state("premarket")["paused_today"]


def test_failures_consume_budget_and_backoff(monkeypatch):
    # Advancing the backoff must not accidentally cross the daily budget reset.
    now = runtime._now().replace(hour=12, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(runtime, "_now", lambda: now)
    monkeypatch.setattr(automation, "get_automation_settings", lambda: {"max_model_calls_per_day": 1})
    @runtime.tracked("premarket")
    def fail():
        runtime.model_attempt()
        raise ValueError("provider failure")
    with pytest.raises(ValueError): fail()
    assert runtime.status()["model_requests"] == 1
    assert not runtime.retry_state("premarket")["allowed"]
    now += timedelta(minutes=16)
    assert runtime.retry_state("premarket")["allowed"]
    with pytest.raises(RuntimeError, match="预算"): fail()
    assert runtime.retry_state("premarket")["paused_today"]


def test_stage_timeout_stops_publication(monkeypatch):
    now = runtime._now()
    monkeypatch.setattr(runtime, "_now", lambda: now)
    @runtime.tracked("manual_review")
    def slow():
        nonlocal now
        runtime.progress("analyze", "等待模型", timeout=10)
        now += timedelta(seconds=11)
        assert runtime.status()["overdue"]
        runtime.checkpoint()
    with pytest.raises(TimeoutError): slow()
    assert runtime.status()["status"] == "failed"


@pytest.mark.parametrize("source", ["workflow", "manual", "manual_review", "manual_followup", "manual_confidence", "manual_evidence"])
def test_manual_requests_ignore_zero_daily_quota(monkeypatch, source):
    monkeypatch.setattr(automation, "get_automation_settings", lambda: {"max_model_calls_per_day": 0})
    @runtime.tracked(source)
    def manual():
        runtime.model_attempt()
        runtime.model_usage({"total_tokens": 12})
    for _ in range(3):
        manual()
        assert runtime.status()["model_requests"] == 1
        assert runtime.status()["tokens"] == 12
    assert runtime.retry_state(source)["allowed"]


def test_manual_usage_does_not_consume_auto_budget_and_nested_calls_keep_origin(monkeypatch):
    monkeypatch.setattr(automation, "get_automation_settings", lambda: {"max_model_calls_per_day": 1})
    @runtime.tracked("manual_review")
    def review():
        runtime.model_attempt()
    @runtime.tracked("scheduled")
    def scheduled():
        review()
    review()
    review()
    scheduled()
    assert runtime.status()["source"] == "scheduled"
    with pytest.raises(RuntimeError, match="自动分析预算"):
        scheduled()
    review()


def test_api_exposes_automatic_progress_and_cancel():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.agent_review import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    entered, release = threading.Event(), threading.Event()
    @runtime.tracked("premarket")
    def automatic():
        runtime.progress("inspect", "API test", completed=1, total=2)
        entered.set()
        release.wait(3)
        runtime.checkpoint()
    def run():
        try: automatic()
        except runtime.TaskCancelled: pass
    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert entered.wait(1)
        assert client.get("/agent/review/workflow").json()["data"]["source"] == "premarket"
        response = client.post("/agent/review/workflow")
        assert response.status_code == 202
        assert response.json()["data"]["completed_items"] == 1
        assert client.post("/agent/review/workflow/cancel").json()["data"]["status"] == "cancelling"
    finally:
        release.set()
        thread.join(3)


@pytest.mark.parametrize("path", ["/automation/premarket/run", "/automation/confidence-refresh"])
def test_morning_buttons_use_manual_origin(monkeypatch, path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import agent_review
    seen = []
    monkeypatch.setattr(agent_review, "run_premarket_cycle", lambda **kw: seen.append(kw["trigger"]) or {"status": "completed"})
    monkeypatch.setattr(agent_review, "mark_premarket_cycle_completed", lambda: None)
    app = FastAPI()
    app.include_router(agent_review.router)
    assert TestClient(app).post("/agent/review" + path).status_code == 200
    assert seen == ["manual_confidence"]
