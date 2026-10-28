from copy import deepcopy
import threading

import pytest


@pytest.fixture(autouse=True)
def enable_legacy_mock_model(isolate_task_runtime):
    from app.agent_review.plan_engine import configure
    configure(False, False)

from app.agent_review import workflow
from app.disclosure_verification import service as disclosure
from app.rotation.service import _classify_opportunity


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "STATE_PATH", tmp_path / "workflow.json")
    monkeypatch.setattr(workflow.cycle, "RUNS_PATH", tmp_path / "runs.json")
    monkeypatch.setattr(workflow.cycle, "_RUN_LOCK", threading.Lock())
    monkeypatch.setattr(workflow, "_worker", None)
    monkeypatch.setattr(workflow, "plan_research_tasks", lambda *a, **k: [])
    monkeypatch.setattr(workflow, "QUEUE_PATH", tmp_path / "queue.json")
    order = []
    for name in ("capture_portfolio_actions", "sync_review_tasks", "invalidate_dashboard_cache", "evaluate_portfolio_actions", "evaluate_recommendations"):
        monkeypatch.setattr(workflow.cycle, name, lambda *a, _name=name, **k: order.append(_name))
    monkeypatch.setattr(workflow.cycle, "get_automation_settings", lambda: dict(workflow.cycle.DEFAULT_SETTINGS))
    monkeypatch.setattr(workflow.cycle, "load_latest_review", lambda: {"run_id": "previous"})
    monkeypatch.setattr(workflow.cycle, "plan_coverage_gap_tasks", lambda *a, **k: None)
    monkeypatch.setattr(workflow.cycle, "execute_pending_tasks", lambda **k: order.append("tools") or [])
    monkeypatch.setattr(workflow.cycle, "generate_daily_review", lambda **k: order.append(("model", k["force_context"])) or {"run_id": "new"})
    monkeypatch.setattr(workflow.cycle, "_model_calls_today", lambda: 0)
    return order


def finish():
    workflow._worker.join(timeout=3)
    assert not workflow._worker.is_alive()
    return workflow.workflow_status()


def test_workflow_collects_before_analysis_and_persists_result(isolated):
    workflow.start_workflow()
    state = finish()
    assert state["status"] == "completed"
    assert state["review_run_id"] == "new"
    assert isolated.index("tools") < isolated.index(("model", True))
    assert all(step["status"] == "completed" for step in state["steps"])


def test_manual_workflow_ignores_daily_model_budget(isolated, monkeypatch):
    monkeypatch.setattr(workflow.cycle, "_model_calls_today", lambda: 2)
    workflow.start_workflow()
    state = finish()
    assert state["status"] == "completed"
    assert state["review_run_id"] == "new"
    assert ("model", True) in isolated


def test_failed_tool_does_not_prevent_bounded_analysis(isolated, monkeypatch):
    monkeypatch.setattr(workflow.cycle, "execute_pending_tasks", lambda **kwargs: [{"status": "failed", "result": None}])
    monkeypatch.setattr(workflow.cycle, "task_evidence", lambda **kwargs: [])
    workflow.start_workflow()
    state = finish()
    assert state["status"] == "completed"
    assert state["evidence"]["failed"] == 1


def test_new_tasks_execute_and_followup_is_bounded(isolated, monkeypatch):
    count = []
    def execute(**kwargs):
        count.append(kwargs)
        return [] if len(count) == 1 else [{"status": "completed"}]
    monkeypatch.setattr(workflow.cycle, "execute_pending_tasks", execute)
    monkeypatch.setattr(workflow.cycle, "generate_followup_review", lambda **kwargs: {"run_id": "verified"})
    workflow.start_workflow()
    state = finish()
    assert state["review_run_id"] == "verified"
    assert len(count) == 2
    assert count[1]["origin_run_id"] == "new"
    assert state["new_task_results"]["executed"] == 1


def test_repeated_click_returns_same_job(isolated, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def model(**kwargs):
        entered.set()
        release.wait(3)
        return {"run_id": "new"}
    monkeypatch.setattr(workflow.cycle, "generate_daily_review", model)
    first = workflow.start_workflow()
    try:
        assert entered.wait(2)
        assert workflow.start_workflow()["job_id"] == first["job_id"]
    finally:
        release.set()
        finish()


def test_account_update_requires_consent_and_queues_while_busy(isolated, monkeypatch):
    assert workflow.queue_account_update()["status"] == "disabled"
    assert not workflow.QUEUE_PATH.exists()
    monkeypatch.setattr(workflow.cycle, "get_automation_settings", lambda: {**workflow.cycle.DEFAULT_SETTINGS, "analysis_after_account_update": True})
    assert workflow.queue_account_update()["status"] == "pending"
    from app.agent_review import runtime
    original_status = runtime.status
    monkeypatch.setattr(runtime, "status", lambda: {"status": "running"})
    workflow.start_pending_account_analysis()
    assert workflow.cycle._read_json(workflow.QUEUE_PATH, {})["status"] == "pending"
    monkeypatch.setattr(runtime, "status", original_status)
    workflow.start_pending_account_analysis()
    state = finish()
    assert state["source"] == "account_update"
    assert workflow.cycle._read_json(workflow.QUEUE_PATH, {})["status"] == "started"


def test_restart_marks_running_job_interrupted(isolated):
    workflow._save({"status": "running", "steps": []})
    assert workflow.workflow_status()["status"] == "interrupted"


@pytest.mark.parametrize("field", ["ma", "relative", "stale", "flow"])
def test_missing_or_stale_rotation_is_not_confirmed_opportunity(field):
    item = {"data_quality": "complete", "score": {"total": 65, "trend": 15, "flow": 15},
            "returns": {"return_5d": 2, "return_20d": 4}, "latest_close": 10,
            "moving_averages": {"ma20": 10}, "relative_strength": {"relative_strength_20d": 2}}
    item = deepcopy(item)
    if field == "ma": item["moving_averages"]["ma20"] = None
    if field == "relative": item["relative_strength"]["relative_strength_20d"] = None
    if field == "stale": item["data_quality"] = "stale"
    if field == "flow": item["score"]["flow"] = 0
    assert _classify_opportunity(item)["stage"] != "potential_opportunity"


def test_legacy_discovered_ids_are_not_all_processed():
    cached = {"seen_announcement_ids": ["read", "unread"], "documents": [{"announcement_id": "read"}]}
    assert disclosure._announcement_ids(cached) == {"read"}
    cached["processed_announcement_ids"] = []
    assert disclosure._announcement_ids(cached) == set()
