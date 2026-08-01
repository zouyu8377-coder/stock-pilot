from __future__ import annotations

from app.agent_review import learning_policy


def _loop_state(sample_count: int = 3) -> dict:
    return {
        "recommendations": [
            {
                "recommendation_id": f"rec-{index}",
                "outcome": {
                    "verdict": "not_supported",
                    "reason_categories": ["risk_omission"],
                },
            }
            for index in range(sample_count)
        ],
        "portfolio_actions": [],
        "weekly_operations": {"symbol_count": 0, "items": []},
    }


def test_repeated_adverse_outcomes_activate_versioned_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(learning_policy, "POLICY_DIR", tmp_path)
    monkeypatch.setattr(learning_policy, "POLICY_PATH", tmp_path / "policies.json")

    first = learning_policy.refresh_learning_policies(_loop_state())
    second = learning_policy.refresh_learning_policies(_loop_state())
    expanded = learning_policy.refresh_learning_policies(_loop_state(sample_count=4))

    assert first["summary"]["active_count"] == 1
    assert first["policies"][0]["status"] == "active"
    assert first["policies"][0]["version"] == 1
    assert second["policies"][0]["version"] == 1
    assert expanded["policies"][0]["version"] == 2
    assert expanded["policies"][0]["history"][-1]["sample_count"] == 4


def test_missing_trade_reasons_remain_monitoring_before_sample_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr(learning_policy, "POLICY_DIR", tmp_path)
    monkeypatch.setattr(learning_policy, "POLICY_PATH", tmp_path / "policies.json")
    state = {
        "recommendations": [],
        "portfolio_actions": [
            {"action_id": "trade-1", "learning_eligible": True, "user_reason": None},
            {"action_id": "trade-2", "learning_eligible": True, "user_reason": None},
        ],
        "weekly_operations": {"symbol_count": 0, "items": []},
    }

    registry = learning_policy.refresh_learning_policies(state)

    assert registry["policies"][0]["policy_id"] == "process:missing_trade_reason"
    assert registry["policies"][0]["status"] == "monitoring"
    assert registry["policies"][0]["adverse_rate_pct"] == 100.0
