from datetime import datetime, timedelta
from copy import deepcopy

import pytest

from app.agent_review import plans


@pytest.fixture
def proposal(tmp_path, monkeypatch):
    monkeypatch.setattr(plans, "ROOT", tmp_path)
    monkeypatch.setattr(plans.research, "account_fingerprint", lambda: "account1")
    request_id = "discussion-" + "a" * 32
    plans.write(tmp_path / f"{request_id}.json", {
        "fingerprint": "f1", "account": "account1", "revision": 0,
        "expires_at": (datetime.now(plans.research.TZ) + timedelta(hours=1)).isoformat(),
        "payload": {"discussion": {"level": "symbol", "target": "603259", "stage": "decision", "question": "是否继续持有"},
                    "evidence": {"evidence_catalog": [{"evidence_ref": "holding:603259"}]}}})
    return {"request_id": request_id, "fingerprint": "f1", "conclusion": "等待新增订单核验",
        "plan": {"thesis": "订单改善", "stance": "wait", "horizon": "一季度", "rationale": "缺少订单正文",
                 "counter_evidence": "订单下滑", "entry_condition": "订单验证后再讨论", "exit_condition": "逻辑失效",
                 "risk_budget": "不得突破用户上限", "next_check": "取得订单原文", "review_on": "2026-09-22",
                 "confidence": "low", "confidence_reason": "证据不足", "evidence_refs": ["holding:603259"]},
        "research": [{"question": "订单变化", "impact": "影响增长判断", "source_needed": "公司公告",
                      "owner": "platform", "priority": "high"}], "lesson_candidates": ["不能把缺数据当利空"]}


def test_preview_confirm_history_and_idempotence(proposal):
    before = deepcopy(plans.state())
    with pytest.raises(ValueError, match="预览"):
        plans.import_proposal(proposal, True)
    preview = plans.import_proposal(proposal)
    assert preview["before"] is None
    assert plans.state() == before
    assert plans.import_proposal(proposal, True)["status"] == "confirmed"
    data = plans.state()
    assert data["plans"]["symbol:603259"]["version"] == 1
    assert data["memories"][0]["status"] == "candidate"
    assert data["needs"][0]["status"] == "open"
    assert data["history"][0]["before"] is None
    assert plans.import_proposal(proposal, True)["status"] == "already_confirmed"
    assert plans.state() == data


@pytest.mark.parametrize("case", ["account", "memory", "fingerprint", "source", "edited", "expired", "research", "date"])
def test_stale_or_invalid_proposals_rejected(proposal, monkeypatch, case):
    plans.import_proposal(proposal)
    if case == "account": monkeypatch.setattr(plans.research, "account_fingerprint", lambda: "account2")
    if case == "memory": plans.add_memory(plans.Memory(level="account", target="账户", kind="constraint", text="保留现金"))
    if case == "fingerprint": proposal["fingerprint"] = "wrong"
    if case == "source": proposal["plan"]["evidence_refs"] = ["invented"]
    if case == "edited": proposal["plan"]["thesis"] = "changed"
    if case == "date": proposal["plan"]["review_on"] = "2026-99-99"
    if case in {"expired", "research"}:
        path = plans.ROOT / f"{proposal['request_id']}.json"
        p = plans.read(path, {})
        if case == "expired": p["expires_at"] = "2020-01-01T00:00:00+08:00"
        else: p["payload"]["discussion"]["stage"] = "research"
        plans.write(path, p)
    with pytest.raises(ValueError): plans.import_proposal(proposal, True)
    assert not plans.state()["plans"]


def test_material_is_not_verified_fact(proposal):
    plans.import_proposal(proposal)
    plans.import_proposal(proposal, True)
    n = plans.state()["needs"][0]
    with pytest.raises(ValueError): plans.update_need(n["id"], "supplied", "")
    row = plans.update_need(n["id"], "supplied", "用户提供公告链接")
    assert row["status"] == "supplied"
    assert "verified" not in row


def test_candidate_symbol_validation():
    with pytest.raises(ValueError): plans.key("symbol", "hello")
    assert plans.key("symbol", "600000") == "symbol:600000"


def test_memory_adoption_and_archive_preserve_history(proposal):
    plans.import_proposal(proposal)
    plans.import_proposal(proposal, True)
    memory = plans.state()["memories"][0]
    plans.review_memory(memory["id"], "user_confirmed")
    assert plans.state()["memories"][0]["status"] == "user_confirmed"
    plans.review_memory(memory["id"], "archived")
    assert plans.state()["memories"][0]["status"] == "archived"
    assert plans.state()["history"][-1]["before"]["status"] == "user_confirmed"


def test_export_includes_memory_and_uses_no_model(proposal, monkeypatch, tmp_path):
    from app.agent_review import exchange
    monkeypatch.setattr(exchange, "EXCHANGE_DIR", tmp_path)
    plans.write(tmp_path / "test.json", {"model_input": {"evidence_catalog": []}})
    monkeypatch.setattr(exchange, "export_request", lambda: {"request_id": "test"})
    plans.add_memory(plans.Memory(level="account", target="账户", kind="constraint", text="保留流动资金"))
    result = plans.export_discussion(plans.Discussion(level="direction", target="医药", stage="research", question="研究哪些事实"))
    packet = plans.read(plans.ROOT / f"{result['request_id']}.json", {})
    assert packet["payload"]["memories"][0]["text"] == "保留流动资金"
    assert packet["payload"]["discussion"]["stage"] == "research"
    assert "response_schema" in result["prompt"]


def test_research_answer_requires_exact_supplied_quote(proposal):
    data = plans.state()
    data["needs"] = [{"id": "n1", "level": "symbol", "target": "603259", "status": "open"}]
    plans.write(plans.ROOT / "state.json", data)
    path = plans.ROOT / f"{proposal['request_id']}.json"
    packet = plans.read(path, {})
    packet["payload"]["evidence"]["evidence_catalog"].append({"evidence_ref": "plan:need:n1", "facts": {"id": "n1", "data": {"documents": [{"selected_text": "本期新增订单同比增长百分之十。", "pdf_url": "https://static.cninfo.com.cn/report.pdf", "title": "季报"}]}}})
    plans.write(path, packet)
    proposal["research_answers"] = [{"need_id": "n1", "conclusion": "订单增长", "stance": "supported", "evidence_ref": "plan:need:n1", "quote": "本期新增订单同比增长百分之十。"}]
    plans.import_proposal(proposal)
    bad = deepcopy(proposal)
    bad["research_answers"][0]["quote"] = "这个公司所有风险已消除"
    with pytest.raises(ValueError, match="原文"):
        plans.import_proposal(bad)
    plans.import_proposal(proposal, True)
    answer = plans.state()["needs"][0]
    assert answer["status"] == "reviewed"
    assert answer["answer"]["quote_verified"] is True
