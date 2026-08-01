from __future__ import annotations

from datetime import datetime

import pytest

from app.agent_review import automation


@pytest.fixture(autouse=True)
def default_to_daily_review_day(monkeypatch):
    monkeypatch.setattr(automation, "_is_weekly_review_day", lambda value: False)
    monkeypatch.setattr(
        automation,
        "refresh_learning_policies",
        lambda loop_state: {
            "summary": {"policy_count": 0, "active_count": 0, "monitoring_count": 0},
        },
    )


def test_automation_settings_use_after_close_defaults_without_skipping_today(tmp_path, monkeypatch):
    monkeypatch.setattr(automation, "AUTOMATION_DIR", tmp_path)
    monkeypatch.setattr(automation, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(automation, "RUNS_PATH", tmp_path / "runs.json")

    settings = automation.update_automation_settings({
        "enabled": True,
        "run_time": "15:31",
        "max_model_calls_per_day": 2,
    })

    assert settings["enabled"] is True
    assert settings["run_time"] == "15:31"
    assert settings["max_model_calls_per_day"] == 2
    assert settings["last_scheduled_date"] is None
    assert settings["premarket_enabled"] is True
    assert settings["premarket_time"] == "08:45"
    assert settings["last_premarket_date"] is None


def test_premarket_cycle_executes_only_low_confidence_tasks_and_rechecks_with_model(tmp_path, monkeypatch):
    monkeypatch.setattr(automation, "AUTOMATION_DIR", tmp_path)
    monkeypatch.setattr(automation, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(automation, "RUNS_PATH", tmp_path / "runs.json")
    automation.update_automation_settings({
        "enabled": True,
        "premarket_enabled": True,
        "auto_execute_tools": True,
        "auto_model_review": True,
    })
    latest = {"run_id": "review-before-open", "completed_at": "2026-08-02T15:31:00+08:00"}
    monkeypatch.setattr(automation, "load_latest_review", lambda: latest)
    monkeypatch.setattr(automation, "sync_review_tasks", lambda review: [])
    monkeypatch.setattr(automation, "list_tasks", lambda **kwargs: [{
        "task_id": "low-1",
        "planning_origin": "low_confidence_auto",
        "status": "pending",
    }])
    captured = {}

    def execute(**kwargs):
        captured.update(kwargs)
        return [{"task_id": "low-1", "status": "completed"}]

    monkeypatch.setattr(automation, "execute_pending_tasks", execute)
    monkeypatch.setattr(automation, "_model_calls_today", lambda **kwargs: 0)
    monkeypatch.setattr(
        automation,
        "generate_followup_review",
        lambda parent_run_id: {"run_id": "review-after-evidence"},
    )

    result = automation.run_premarket_cycle()

    assert captured["planning_origins"] == automation.LOW_CONFIDENCE_ORIGINS
    assert result["model_calls"] == 1
    assert [step["step"] for step in result["steps"]] == [
        "premarket_evidence_check",
        "premarket_confidence_update",
    ]
    assert result["steps"][1]["run_id"] == "review-after-evidence"


def test_premarket_cycle_does_not_call_model_without_new_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(automation, "AUTOMATION_DIR", tmp_path)
    monkeypatch.setattr(automation, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(automation, "RUNS_PATH", tmp_path / "runs.json")
    automation.update_automation_settings({"enabled": True, "premarket_enabled": True})
    monkeypatch.setattr(automation, "load_latest_review", lambda: {"run_id": "review-1"})
    monkeypatch.setattr(automation, "sync_review_tasks", lambda review: [])
    monkeypatch.setattr(automation, "list_tasks", lambda **kwargs: [])
    monkeypatch.setattr(automation, "execute_pending_tasks", lambda **kwargs: [])
    monkeypatch.setattr(
        automation,
        "generate_followup_review",
        lambda **kwargs: pytest.fail("没有新证据时不应调用模型"),
    )

    result = automation.run_premarket_cycle()

    assert result["model_calls"] == 0
    assert result["steps"][0]["candidate_count"] == 0


def test_premarket_scheduler_runs_in_window_once_per_day(tmp_path, monkeypatch):
    monkeypatch.setattr(automation, "AUTOMATION_DIR", tmp_path)
    monkeypatch.setattr(automation, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(automation, "RUNS_PATH", tmp_path / "runs.json")
    automation.update_automation_settings({
        "enabled": True,
        "premarket_enabled": True,
        "premarket_time": "08:45",
        "weekdays_only": True,
    })

    class MorningDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 8, 3, 8, 50, tzinfo=automation.TZ)

    monkeypatch.setattr(automation, "datetime", MorningDateTime)
    monkeypatch.setattr(automation, "load_latest_review", lambda: {"run_id": "review-1"})
    monkeypatch.setattr(automation, "sync_review_tasks", lambda review: [])
    monkeypatch.setattr(automation, "list_tasks", lambda **kwargs: [{
        "task_id": "low-1",
        "planning_origin": "low_confidence_auto",
        "status": "pending",
    }])

    assert automation.should_run_premarket_cycle() is True
    automation.mark_premarket_cycle_completed()
    assert automation.should_run_premarket_cycle() is False


def test_automatic_cycle_can_run_outcome_only_without_model(tmp_path, monkeypatch):
    monkeypatch.setattr(automation, "AUTOMATION_DIR", tmp_path)
    monkeypatch.setattr(automation, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(automation, "RUNS_PATH", tmp_path / "runs.json")
    automation.update_automation_settings({
        "enabled": True,
        "auto_model_review": False,
        "auto_execute_tools": False,
    })
    monkeypatch.setattr(automation, "capture_portfolio_actions", lambda: [{"action_id": "a1"}])
    monkeypatch.setattr(automation, "evaluate_portfolio_actions", lambda: [])
    monkeypatch.setattr(automation, "evaluate_recommendations", lambda: [])
    monkeypatch.setattr(automation, "list_outcomes", lambda: {
        "summary": {"action_count": 1, "snapshot_change_count": 1},
        "loop_health": {
            "strategy_context_coverage_pct": 100,
            "matured_evaluation_rate_pct": 0,
        },
    })
    monkeypatch.setattr(automation, "load_latest_review", lambda: None)

    result = automation.run_automatic_cycle(trigger="test")

    assert result["status"] == "completed"
    assert result["model_calls"] == 0
    assert result["steps"][0]["created_actions"] == 1


def test_manual_cycle_does_not_suppress_trade_driven_scheduled_review(tmp_path, monkeypatch):
    monkeypatch.setattr(automation, "AUTOMATION_DIR", tmp_path)
    monkeypatch.setattr(automation, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(automation, "RUNS_PATH", tmp_path / "runs.json")
    automation.update_automation_settings({
        "enabled": True,
        "run_time": "00:00",
        "weekdays_only": False,
        "auto_model_review": False,
        "auto_execute_tools": False,
    })
    monkeypatch.setattr(automation, "capture_portfolio_actions", lambda: [])
    monkeypatch.setattr(automation, "evaluate_portfolio_actions", lambda: [])
    monkeypatch.setattr(automation, "evaluate_recommendations", lambda: [])
    monkeypatch.setattr(automation, "list_outcomes", lambda: {
        "summary": {"action_count": 0, "snapshot_change_count": 0},
        "loop_health": {},
    })
    monkeypatch.setattr(automation, "build_monthly_report", lambda: {
        "month": "2026-07",
        "recommendations": {"evaluated": 0},
        "confirmed_actions": {"evaluated": 0},
    })
    monkeypatch.setattr(automation, "load_latest_review", lambda: None)
    monkeypatch.setattr(
        automation,
        "confirmed_actions_on_local_date",
        lambda value: [{"action_id": "trade-today"}],
    )

    result = automation.run_automatic_cycle(trigger="manual")

    assert result["status"] == "completed"
    assert automation.get_automation_settings()["last_scheduled_date"] is None
    assert automation.should_run_scheduled_cycle() is True


def test_scheduled_cycle_is_skipped_without_confirmed_trade(tmp_path, monkeypatch):
    monkeypatch.setattr(automation, "AUTOMATION_DIR", tmp_path)
    monkeypatch.setattr(automation, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(automation, "RUNS_PATH", tmp_path / "runs.json")
    automation.update_automation_settings({
        "enabled": True,
        "run_time": "00:00",
        "weekdays_only": False,
    })
    monkeypatch.setattr(automation, "confirmed_actions_on_local_date", lambda value: [])

    assert automation.should_run_scheduled_cycle() is False


def test_weekly_review_day_uses_week_actions_and_skips_daily_trade_requirement(tmp_path, monkeypatch):
    monkeypatch.setattr(automation, "AUTOMATION_DIR", tmp_path)
    monkeypatch.setattr(automation, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(automation, "RUNS_PATH", tmp_path / "runs.json")
    automation.update_automation_settings({
        "enabled": True,
        "run_time": "00:00",
        "weekdays_only": False,
    })
    monkeypatch.setattr(automation, "_is_weekly_review_day", lambda value: True)
    monkeypatch.setattr(automation, "confirmed_actions_on_local_date", lambda value: [])
    monkeypatch.setattr(
        automation,
        "build_weekly_operation_summary",
        lambda reference_time=None: {"action_count": 4},
    )

    assert automation.should_run_scheduled_cycle() is True


def test_new_daily_review_can_complete_tool_followup_in_same_cycle(tmp_path, monkeypatch):
    monkeypatch.setattr(automation, "AUTOMATION_DIR", tmp_path)
    monkeypatch.setattr(automation, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(automation, "RUNS_PATH", tmp_path / "runs.json")
    automation.update_automation_settings({
        "enabled": True,
        "weekdays_only": False,
        "auto_model_review": True,
        "auto_execute_tools": True,
        "max_model_calls_per_day": 2,
    })
    monkeypatch.setattr(automation, "capture_portfolio_actions", lambda: [])
    monkeypatch.setattr(automation, "evaluate_portfolio_actions", lambda: [])
    monkeypatch.setattr(automation, "evaluate_recommendations", lambda: [])
    monkeypatch.setattr(automation, "list_outcomes", lambda: {
        "summary": {"action_count": 0, "snapshot_change_count": 0},
        "loop_health": {},
    })
    monkeypatch.setattr(automation, "build_monthly_report", lambda: {
        "month": "2026-07",
        "recommendations": {"evaluated": 0},
        "confirmed_actions": {"evaluated": 0},
    })
    monkeypatch.setattr(automation, "load_latest_review", lambda: None)
    monkeypatch.setattr(automation, "_model_calls_today", lambda **kwargs: 0)
    monkeypatch.setattr(
        automation,
        "generate_daily_review",
        lambda force_context=False: {
            "run_id": "daily-new",
            "completed_at": datetime.now(automation.TZ).isoformat(),
        },
    )
    monkeypatch.setattr(
        automation,
        "execute_pending_tasks",
        lambda origin_run_id: [{"status": "completed"}],
    )
    monkeypatch.setattr(
        automation,
        "task_evidence",
        lambda origin_run_id: [{"evidence_ref": "tool:test"}],
    )
    monkeypatch.setattr(
        automation,
        "generate_followup_review",
        lambda parent_run_id: {"run_id": "followup-new"},
    )

    result = automation.run_automatic_cycle(trigger="manual")

    assert result["model_calls"] == 2
    assert [step["step"] for step in result["steps"]][-4:] == [
        "daily_review",
        "tool_execution",
        "followup_review",
        "followup_tool_execution",
    ]


def test_scheduled_trade_review_has_budget_even_after_manual_review(tmp_path, monkeypatch):
    monkeypatch.setattr(automation, "AUTOMATION_DIR", tmp_path)
    monkeypatch.setattr(automation, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(automation, "RUNS_PATH", tmp_path / "runs.json")
    automation.update_automation_settings({
        "enabled": True,
        "auto_model_review": True,
        "auto_execute_tools": False,
        "max_model_calls_per_day": 2,
    })
    now = datetime.now(automation.TZ)
    automation._write_json(automation.RUNS_PATH, [{
        "trigger": "manual",
        "started_at_local": now.isoformat(),
        "model_calls": 2,
    }])
    monkeypatch.setattr(automation, "capture_portfolio_actions", lambda: [])
    monkeypatch.setattr(automation, "evaluate_portfolio_actions", lambda: [])
    monkeypatch.setattr(automation, "evaluate_recommendations", lambda: [])
    monkeypatch.setattr(automation, "list_outcomes", lambda: {
        "summary": {"action_count": 1, "snapshot_change_count": 1},
        "loop_health": {},
    })
    monkeypatch.setattr(automation, "build_monthly_report", lambda: {
        "month": "2026-07",
        "recommendations": {"evaluated": 0},
        "confirmed_actions": {"evaluated": 0},
    })
    monkeypatch.setattr(automation, "build_rotation_bundle", lambda: {
        "as_of": "2026-07-31",
        "summary": {"stale_count": 0},
        "sectors": [],
    })
    monkeypatch.setattr(automation, "load_latest_review", lambda: {
        "run_id": "manual-today",
        "completed_at": now.isoformat(),
    })
    monkeypatch.setattr(
        automation,
        "generate_daily_review",
        lambda force_context=False: {
            "run_id": "scheduled-after-close",
            "completed_at": now.isoformat(),
        },
    )

    result = automation.run_automatic_cycle(trigger="scheduled")

    assert result["model_calls"] == 1
    assert any(step.get("run_id") == "scheduled-after-close" for step in result["steps"])
