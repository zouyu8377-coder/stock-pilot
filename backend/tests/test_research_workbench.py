from copy import deepcopy
from datetime import datetime

import pytest

from app.agent_review import research, service, tasks
from app.portfolio.schemas import PortfolioSnapshot


@pytest.fixture
def dossier(tmp_path, monkeypatch):
    snapshot = PortfolioSnapshot(positions=[{"symbol": "603259", "name": "药明康德", "quantity": 100, "avg_cost": -10, "directions": ["CXO"]}])
    monkeypatch.setattr(research, "ROOT", tmp_path)
    monkeypatch.setattr(research.portfolio_service, "load_snapshot", lambda: snapshot)
    monkeypatch.setattr(research, "_symbol_context", lambda s: {"questions": ["订单是否增长？"]})
    verification = {}
    monkeypatch.setattr(research, "load_disclosure_verification", lambda s: verification)
    monkeypatch.setattr(tasks, "list_tasks", lambda **kw: [])
    item = {"item_id": "one", "subject": "集中度", "target_symbols": ["603259.SH"], "suggested_action": "hold", "action_semantics": "暂不增持", "conclusion": "集中度需监控", "confidence": "medium"}
    latest = {"run_id": "r1", "completed_at": research.now(), "account_fingerprint": research.account_fingerprint(),
              "review": {"risks": [item], "watch_items": [{**item, "item_id": "two", "subject": "量价背离"}]}}
    monkeypatch.setattr(service, "load_latest_review", lambda: latest)
    return snapshot, verification, latest


def test_dossier_separates_index_material_from_verified_answer(dossier):
    _, verification, _ = dossier
    assert research.build_workbench()["dossiers"][0]["questions"][0]["status"] == "not_checked"
    verification.update(documents=[{"title": "半年报"}], trigger="announcement_index_no_change", index_checked_at=research.now())
    question = research.build_workbench()["dossiers"][0]["questions"][0]
    assert question["status"] == "checked_no_new"
    assert question["answer"] == ""
    verification.update(current_items=[{"question": "订单是否增长？", "status": "supported", "quote_verified": True, "conclusion": "同比增长", "quote": "示例原文", "source_url": "https://example.com/report"}])
    question = research.build_workbench()["dossiers"][0]["questions"][0]
    assert question["status"] == "body_verified"
    assert question["sources"][0]["quote"] == "示例原文"


def test_unrelated_or_unverified_quote_cannot_answer_question(dossier):
    _, verification, _ = dossier
    verification.update(current_items=[{"question": "收入是否增长？", "quote_verified": True, "status": "supported"},
                                       {"question": "订单是否增长？", "quote_verified": False, "status": "supported"}])
    question = research.build_workbench()["dossiers"][0]["questions"][0]
    assert question["status"] != "body_verified"
    assert not question["sources"]


def test_same_holding_is_merged_and_response_never_changes_portfolio(dossier):
    snapshot, _, latest = dossier
    before = snapshot.model_dump()
    action = research.build_workbench()["actions"][0]
    assert len(research.build_workbench()["actions"]) == 1
    assert len(action["related"]) == 1
    research.respond_to_action(action["id"], action["version"], "monitoring", "观察下一次披露")
    assert research.build_workbench()["actions"][0]["state"] == "monitoring"
    assert snapshot.model_dump() == before
    latest["review"]["risks"][0]["conclusion"] = "出现新风险"
    assert research.build_workbench()["actions"][0]["changed_since_response"]
    with pytest.raises(ValueError, match="变化"):
        research.respond_to_action(action["id"], action["version"], "monitoring", "")


def test_response_requires_reason_and_current_account(dossier):
    snapshot, _, latest = dossier
    action = research.build_workbench()["actions"][0]
    with pytest.raises(ValueError, match="原因"):
        research.respond_to_action(action["id"], action["version"], "dismissed", "")
    snapshot.cash_available += 100
    with pytest.raises(ValueError, match="变化"):
        research.respond_to_action(action["id"], action["version"], "monitoring", "")


def test_unchanged_trade_ledger_is_not_reviewed_twice():
    model_input = {"operation_review_period": "daily", "learning_feedback": {"operation_feedback": {
        "daily_actions": {"trading_date": "2026-09-15", "action_count": 1, "items": [{"action_id": "a"}]}}}}
    original = deepcopy(model_input)
    service._skip_unchanged_operations(model_input, {})
    service._skip_unchanged_operations(original, {"operation_fingerprint": model_input["operation_fingerprint"]})
    assert original["learning_feedback"]["operation_feedback"]["daily_actions"]["items"] == []
    assert original["learning_feedback"]["operation_feedback"]["daily_actions"]["action_count"] == 0


def test_same_evidence_and_account_reuses_report(tmp_path, monkeypatch):
    from test_agent_review import _review
    monkeypatch.setattr(service, "REVIEW_DIR", tmp_path)
    monkeypatch.setattr(service, "LATEST_PATH", tmp_path / "latest.json")
    monkeypatch.setattr(research, "account_fingerprint", lambda: "same-account")
    monkeypatch.setattr(service, "build_daily_review_context", lambda **kw: {})
    monkeypatch.setattr(service, "build_review_model_input", lambda c: {"operation_review_period": "daily", "evidence_catalog": [{"facts": {"price": 10}}]})
    monkeypatch.setattr(service, "_sync_tasks", lambda *a: None)
    monkeypatch.setattr(service, "_register_outcomes", lambda *a: None)
    calls = []
    monkeypatch.setattr(service, "_generate_with_correction", lambda i: (calls.append(i) or _review(), {}, []))
    first = service.generate_daily_review()
    second = service.generate_daily_review()
    assert len(calls) == 1
    assert second["unchanged"]
    assert first["run_id"] == second["run_id"]


def test_mid_analysis_account_change_rejects_publication(tmp_path, monkeypatch):
    from test_agent_review import _review
    monkeypatch.setattr(service, "REVIEW_DIR", tmp_path)
    monkeypatch.setattr(service, "LATEST_PATH", tmp_path / "latest.json")
    values = iter(["before", "after"])
    monkeypatch.setattr(research, "account_fingerprint", lambda: next(values))
    monkeypatch.setattr(service, "build_daily_review_context", lambda **kw: {})
    monkeypatch.setattr(service, "build_review_model_input", lambda c: {"evidence_catalog": []})
    monkeypatch.setattr(service, "_generate_with_correction", lambda i: (_review(), {}, []))
    with pytest.raises(ValueError, match="账户发生变化"):
        service.generate_daily_review()
    assert not service.LATEST_PATH.exists()
