from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from app.agent_review import outcomes


def _history(start: float = 100, daily_step: float = 1) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "date": date(2026, 1, 1) + timedelta(days=index),
            "close": start + daily_step * index,
        }
        for index in range(40)
    ])


def test_register_and_evaluate_opportunity(tmp_path, monkeypatch):
    monkeypatch.setattr(outcomes, "OUTCOME_DIR", tmp_path)
    monkeypatch.setattr(outcomes, "RECOMMENDATIONS_PATH", tmp_path / "recommendations.json")
    monkeypatch.setattr(outcomes, "ACTIONS_PATH", tmp_path / "actions.json")
    monkeypatch.setattr(outcomes.collector, "get_history", lambda symbol, limit=5000: _history())
    monkeypatch.setattr(
        outcomes,
        "_latest_market_point",
        lambda symbol: {"date": "2026-01-01", "close": 100},
    )
    review_run = {
        "run_id": "run-1",
        "completed_at": "2026-01-01T00:00:00+00:00",
        "review": {
            "opportunities": [{
                "item_id": "opp-1",
                "subject": "测试机会",
                "conclusion": "观察期内可能走强",
                "confidence": "medium",
                "evidence_refs": ["rotation:test"],
                "counter_evidence_refs": [],
            }],
            "risks": [],
            "watch_items": [],
        },
    }
    model_input = {
        "evidence_catalog": [{
            "evidence_ref": "rotation:test",
            "facts": {"selected_symbol": "159999"},
        }],
    }

    created = outcomes.register_review_outcomes(review_run, model_input)
    evaluated = outcomes.evaluate_recommendations()

    assert created[0]["target_symbols"] == ["159999"]
    assert created[0]["decision_snapshot"]["evidence"][0]["evidence_ref"] == "rotation:test"
    assert created[0]["lifecycle"]["state"] == "open"
    assert evaluated[0]["outcome"]["verdict"] == "supported"
    assert evaluated[0]["outcome"]["method"] == "deterministic_market_outcome.v3"
    assert evaluated[0]["outcome"]["excess_return_pct"] == 0
    assert evaluated[0]["outcome"]["decision_quality"]["assessment"] == "direction_and_follow_through_supported"
    assert evaluated[0]["lifecycle"]["state"] == "evaluated"


def test_risk_warning_is_supported_by_large_drawdown(tmp_path, monkeypatch):
    monkeypatch.setattr(outcomes, "RECOMMENDATIONS_PATH", tmp_path / "recommendations.json")
    monkeypatch.setattr(outcomes, "ACTIONS_PATH", tmp_path / "actions.json")
    monkeypatch.setattr(outcomes.collector, "get_history", lambda symbol, limit=5000: _history(start=100, daily_step=-1))
    outcomes._write(outcomes.RECOMMENDATIONS_PATH, [{
        "recommendation_id": "risk-1",
        "category": "risk",
        "subject": "测试风险",
        "baselines": {"600000": {"date": "2026-01-01", "close": 100}},
        "horizon_trading_days": 20,
        "outcome": None,
    }])

    evaluated = outcomes.evaluate_recommendations()

    assert evaluated[0]["outcome"]["verdict"] == "supported"
    assert evaluated[0]["outcome"]["symbol_results"]["600000"]["return_pct"] < 0


def test_unconfirmed_snapshot_change_is_excluded_from_learning(tmp_path, monkeypatch):
    monkeypatch.setattr(outcomes, "RECOMMENDATIONS_PATH", tmp_path / "recommendations.json")
    monkeypatch.setattr(outcomes, "ACTIONS_PATH", tmp_path / "actions.json")
    outcomes._write(outcomes.RECOMMENDATIONS_PATH, [])
    outcomes._write(outcomes.ACTIONS_PATH, [{
        "action_id": "candidate-1",
        "symbol": "600000",
        "source": "inferred_from_portfolio_snapshots",
        "user_confirmed": False,
        "outcome": {
            "verdict": "supported",
            "method": "deterministic_position_action.v2",
        },
    }])

    listed = outcomes.list_outcomes()
    feedback = outcomes.build_learning_feedback()

    assert listed["summary"]["action_count"] == 0
    assert listed["summary"]["action_candidates"] == 1
    assert listed["portfolio_actions"][0]["outcome"] is None
    assert listed["portfolio_actions"][0]["excluded_outcome"]["verdict"] == "supported"
    assert feedback["evaluated_count"] == 0


def test_confirmed_trade_ledger_creates_learning_eligible_action(tmp_path, monkeypatch):
    ledger_path = tmp_path / "transactions.json"
    monkeypatch.setattr(outcomes, "TRADE_LEDGER_PATH", ledger_path)
    monkeypatch.setattr(
        outcomes,
        "_market_point_at",
        lambda symbol, value: {"date": "2026-07-30", "close": 10},
    )
    outcomes._write(ledger_path, [{
        "batch_id": "batch-1",
        "confirmed_at": "2026-07-30T07:00:00+00:00",
        "user_reason": "降低高波动敞口",
        "transactions": [{
            "transaction_id": "trade-1",
            "symbol": "002463.SZ",
            "name": "沪电股份",
            "side": "sell",
            "quantity": 200,
            "average_price": 105.25,
            "amount": 21050,
        }],
    }])

    created, _ = outcomes._confirmed_trade_actions(existing_ids=set(), snapshots_by_id={})

    assert created[0]["action_id"] == "trade-1"
    assert created[0]["symbol"] == "002463"
    assert created[0]["user_confirmed"] is True
    assert created[0]["learning_eligible"] is True
    assert created[0]["user_reason"] == "降低高波动敞口"


def test_action_strategy_comparison_only_uses_recommendations_available_at_action_time(tmp_path, monkeypatch):
    monkeypatch.setattr(outcomes, "RECOMMENDATIONS_PATH", tmp_path / "recommendations.json")
    monkeypatch.setattr(outcomes, "REVIEW_DIR", tmp_path / "reviews")
    outcomes._write(outcomes.RECOMMENDATIONS_PATH, [
        {
            "recommendation_id": "risk-before",
            "created_at": "2026-07-30T06:00:00+00:00",
            "category": "risk",
            "subject": "趋势风险",
            "target_symbols": ["002463"],
            "decision_snapshot": {"action_semantics": "审视风险"},
        },
        {
            "recommendation_id": "opportunity-after",
            "created_at": "2026-07-30T08:00:00+00:00",
            "category": "opportunity",
            "subject": "事后机会",
            "target_symbols": ["002463"],
        },
    ])

    comparison = outcomes._strategy_comparison(
        "002463",
        "reduced",
        "2026-07-30T07:00:00+00:00",
    )

    assert comparison["status"] == "aligned"
    assert comparison["aligned_recommendation_ids"] == ["risk-before"]
    assert comparison["conflicted_recommendation_ids"] == []
    assert [item["recommendation_id"] for item in comparison["matched_recommendations"]] == ["risk-before"]


def test_confirmed_holdings_snapshot_creates_complete_change_event():
    previous = {
        "snapshot_id": "before",
        "total_assets": 100000,
        "cash_available": 40000,
        "repo_amount": 0,
        "positions": [{
            "symbol": "603259.SH",
            "name": "药明康德",
            "quantity": 100,
            "avg_cost": 120,
            "broker_screenshot_market_value": 12500,
        }],
    }
    current = {
        "snapshot_id": "after",
        "snapshot_time": "2026-07-30T07:00:00+00:00",
        "total_assets": 101000,
        "cash_available": 30000,
        "repo_amount": 0,
        "draft_id": "draft-1",
        "positions": [{
            "symbol": "603259.SH",
            "name": "药明康德",
            "quantity": 150,
            "avg_cost": 122,
            "broker_screenshot_market_value": 19000,
        }],
    }

    event = outcomes._snapshot_change_event(previous, current)

    assert event["account_changes"]["total_assets_delta"] == 1000
    assert event["account_changes"]["cash_delta"] == -10000
    assert event["position_changes"][0]["quantity_delta"] == 50
    assert event["position_changes"][0]["avg_cost_delta"] == 2
    assert event["position_changes"][0]["market_value_delta"] == 6500


def test_symbol_suffix_only_change_is_dismissed_as_artifact():
    records = [
        {
            "action_id": "before:after:159929",
            "symbol": "159929",
            "source": "inferred_from_portfolio_snapshots",
            "action_type": "closed",
            "quantity_before": 100,
            "quantity_after": 0,
        },
        {
            "action_id": "before:after:159929.SZ",
            "symbol": "159929.SZ",
            "source": "inferred_from_portfolio_snapshots",
            "action_type": "opened",
            "quantity_before": 0,
            "quantity_after": 100,
        },
    ]

    changed = outcomes._collapse_symbol_format_artifacts(records)

    assert changed is True
    assert all(item["decision_status"] == "dismissed" for item in records)
    assert all(item["record_quality"] == "symbol_format_artifact" for item in records)


def test_action_attribution_explains_sell_as_avoided_decline():
    attribution = outcomes._action_attribution(
        {
            "action_type": "reduced",
            "quantity_before": 1000,
            "quantity_after": 600,
            "quantity_delta": -400,
            "user_reason": "趋势跌破并降低风险敞口",
            "ai_strategy_comparison": {"status": "aligned"},
        },
        result={
            "baseline_close": 10,
            "evaluation_close": 8,
            "return_pct": -20,
            "max_adverse_move_pct": -22,
            "max_runup_pct": 1,
        },
        excess_return=-15,
        verdict="supported",
    )

    assert attribution["estimated_position_effect_pnl"] == 800
    assert attribution["estimated_benchmark_adjusted_pnl"] == 600
    assert attribution["path_interpretation"] == "risk_reduction_avoided_decline"
    assert attribution["strategy_fit"] == "aligned_and_supported"
    assert attribution["reason_capture"] == "recorded"
    assert attribution["transaction_cost"]["status"] == "unavailable"


def test_weekly_actions_are_grouped_by_symbol_and_preserve_reversals(monkeypatch):
    monkeypatch.setattr(outcomes, "_latest_market_point", lambda symbol: {"date": "2026-07-31", "close": 11})
    monkeypatch.setattr(outcomes, "_market_point_at", lambda symbol, value: {"date": "2026-07-30", "close": 10})
    actions = [
        {
            "action_id": "buy-1",
            "symbol": "600000",
            "name": "浦发银行",
            "action_type": "increased",
            "quantity_before": 100,
            "quantity_after": 150,
            "quantity_delta": 50,
            "snapshot_time": "2026-07-30T02:00:00+00:00",
            "decision_status": "confirmed",
            "user_confirmed": True,
            "learning_eligible": True,
            "baseline": {"date": "2026-07-30", "close": 10},
            "ai_strategy_comparison": {"status": "aligned", "matched_recommendations": []},
        },
        {
            "action_id": "sell-1",
            "symbol": "600000",
            "name": "浦发银行",
            "action_type": "reduced",
            "quantity_before": 150,
            "quantity_after": 120,
            "quantity_delta": -30,
            "snapshot_time": "2026-07-31T02:00:00+00:00",
            "decision_status": "confirmed",
            "user_confirmed": True,
            "learning_eligible": True,
            "baseline": {"date": "2026-07-31", "close": 11},
            "ai_strategy_comparison": {"status": "conflicted", "matched_recommendations": []},
        },
    ]

    grouped = outcomes._aggregate_weekly_actions(actions, ["2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31"])

    assert len(grouped) == 1
    assert grouped[0]["operation_count"] == 2
    assert grouped[0]["net_quantity"] == 20
    assert grouped[0]["pattern"] == "two_way_net_buy"
    assert grouped[0]["reversal_count"] == 1
    assert grouped[0]["strategy_comparison_counts"] == {"aligned": 1, "conflicted": 1}
