from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.agent_review import plan_engine as engine, plans, runtime


@pytest.fixture
def context(monkeypatch):
    snapshot = {"snapshot_time": "2026-09-22T08:00:00Z", "cash_available": 1000, "positions": [{"symbol": "603259", "quantity": 100}]}
    monkeypatch.setattr(engine.research, "account_fingerprint", lambda: "same")
    monkeypatch.setattr(engine.research, "portfolio_service", SimpleNamespace(load_snapshot=lambda: SimpleNamespace(model_dump=lambda **_: snapshot)))
    monkeypatch.setattr(engine, "performance_review", lambda _: {"status": "waiting"})
    market = {"snapshots": [{"symbol": "603259", "history": {"latest_date": "2026-09-22", "target_date": "2026-09-22", "latest_close": 10, "price_vs_ma20_pct": -8}}]}
    calls = []
    def collect(tool, symbols):
        calls.append((tool, symbols))
        return deepcopy(market) if tool == "market" else {"documents": [{"title": "公告", "selected_text": "订单正文"}], "failures": []}
    monkeypatch.setattr(engine, "collect", collect)
    condition = {"label": "趋势走弱", "symbol": "603259", "metric": "price_vs_ma20_pct", "operator": "lt", "threshold": -5, "action": "重新讨论原计划"}
    plan = {"level": "symbol", "target": "603259", "version": 1, "at": "2026-09-21T16:00:00+08:00", "account_fingerprint": "same",
            "baseline": {"positions": [{"symbol": "603259", "quantity": 50}]},
            "content": {"stance": "wait", "conditions": [condition], "condition_mode": "all", "review_on": "2099-01-01", "next_check": "订单公告"}}
    state = plans.state()
    state["plans"]["symbol:603259"] = plan
    state["needs"] = [{"id": "n1", "question": "订单？", "level": "symbol", "target": "603259", "owner": "platform", "status": "open", "tool": "disclosure", "symbols": []}]
    plans.commit(state)
    return snapshot, market, calls, condition


def test_fresh_condition_and_unverified_material(context):
    result = engine.run()
    assert result["status"] == "completed"
    assert result["board"]["model_calls"] == 0
    p = result["board"]["plans"][0]
    assert p["state"] == "discussion_required"
    assert p["conditions"][0]["state"] == "met"
    assert p["operation_review"]["items"][0]["delta"] == 50
    assert "需讨论" in p["operation_review"]["items"][0]["assessment"]
    assert result["board"]["research"][0]["state"] == "material_ready"
    assert plans.state()["needs"][0]["status"] == "open"


def test_stale_prices_are_unknown_not_triggered(context):
    _, market, _, condition = context
    market["snapshots"][0]["history"]["latest_date"] = "2026-09-18"
    result = engine.condition_result(condition, {"603259": market}, {})
    assert result["state"] == "unknown"
    market["snapshots"][0]["history"]["latest_date"] = "2026-09-23"
    assert engine.condition_result(condition, {"603259": market}, {})["state"] == "unknown"


def test_collection_cooldown_and_unchanged_revision(context):
    first = engine.run()["board"]
    second = engine.run()["board"]
    assert first["revision"] == second["revision"]
    assert sum(c[0] == "disclosure" for c in context[2]) == 1


def test_account_mutation_blocks_publish(context, monkeypatch):
    values = iter(["same", "changed"])
    monkeypatch.setattr(engine.research, "account_fingerprint", lambda: next(values))
    assert engine.run()["status"] == "failed"
    assert engine.board()["revision"] == 0


def test_external_mode_blocks_internal_model_before_call():
    engine.configure(False, True)
    with pytest.raises(RuntimeError, match="外部模型"):
        runtime.model_attempt()


def test_compound_risk_requires_all_conditions(context):
    state = plans.state()
    state["plans"]["symbol:603259"]["content"]["conditions"].append({**context[3], "threshold": -20})
    plans.commit(state)
    result = engine.run()["board"]["plans"][0]
    assert result["state"] == "monitoring"
    assert result["triggered_actions"] == []


def test_missing_account_prices_do_not_report_safe_weight(context):
    account = engine.account_values(context[0], {})
    assert account["missing"] is True
    c = {**context[3], "metric": "cash_ratio_pct", "threshold": 5}
    assert engine.condition_result(c, {}, account)["state"] == "unknown"
