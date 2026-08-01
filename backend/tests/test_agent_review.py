from __future__ import annotations

import json

import pytest

from app.agent_review import service
from app.agent_review import outcomes
from app.agent_review.schemas import DailyReviewOutput


@pytest.fixture(autouse=True)
def isolate_learning_feedback(monkeypatch):
    monkeypatch.setattr(service, "_operation_review_period", lambda reference=None: "daily")
    monkeypatch.setattr(outcomes, "build_learning_feedback", lambda: {
        "contract_version": "agent_learning_feedback.v3",
        "evaluated_count": 0,
        "operation_feedback": {
            "weekly_symbol_operations": {
                "window_start": "2026-07-24",
                "window_end": "2026-07-30",
                "trading_dates": ["2026-07-24", "2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30"],
                "action_count": 0,
                "symbol_count": 0,
                "items": [],
            },
        },
    })


def _context() -> dict:
    return {
        "meta": {
            "data_time": {"portfolio": "2026-07-29", "rotation": "2026-07-29"},
            "freshness": {
                "portfolio": {"status": "fresh"},
                "rotation": {"status": "fresh"},
            },
        },
        "facts": {
            "portfolio": {
                "account": {
                    "position_ratio": 0.5,
                    "account_actual_total_cost": 120000,
                    "account_total_pnl": -20000,
                    "account_total_pnl_pct": -16.67,
                    "account_total_pnl_status": "available",
                    "current_holding_unrealized_pnl": 5000,
                    "current_holding_unrealized_pnl_pct": 5.0,
                    "current_holding_unrealized_pnl_status": "available",
                },
                "holdings": [{"symbol": "600000", "name": "样例"}],
                "holding_trend_evidence": [],
                "market_events": {"events": [{"event_id": "evt-1", "title": "样例事件"}]},
            },
            "rotation": {
                "sector_evidence": [{"sector_id": "ai", "name": "AI"}],
            },
        },
        "inferences": {
            "portfolio": {
                "primary_direction_grouping": [],
                "risk_observations": {"risk_observations": []},
                "opportunity_queue": [],
                "risk_queue": [],
            },
            "rotation": {
                "sector_opportunity_assessments": [
                    {"sector_id": "ai", "opportunity_stage": "early_turning"},
                ],
            },
        },
        "missing_data": [],
    }


def _review() -> DailyReviewOutput:
    return DailyReviewOutput.model_validate({
        "headline": "保持观察，优先核查早期转强方向",
        "data_status": {
            "usable": True,
            "stale_evidence_refs": [],
            "missing_evidence_refs": [],
            "summary": "核心证据可用",
        },
        "opportunities": [{
            "item_id": "opp-1",
            "subject": "AI",
            "conclusion": "出现早期转强迹象，仍需确认持续性。",
            "confidence": "medium",
            "evidence_refs": ["rotation:ai"],
            "counter_evidence_refs": [],
            "action_semantics": "进入观察队列，等待趋势与扩散信号共同确认。",
            "invalidation_conditions": ["相对强度重新转弱"],
        }],
        "risks": [],
        "watch_items": [],
        "verification_tasks": [{
            "priority": "high",
            "subject": "AI",
            "task": "核查连续两个交易日的扩散程度",
            "reason": "单日信号不足以确认趋势",
        }],
        "decision_focus": [{
            "priority": "high",
            "subject": "AI 扩散验证",
            "action": "verify",
            "reason": "单日信号不足，先完成扩散验证。",
            "evidence_refs": ["rotation:ai"],
        }],
        "summary": "当前持仓浮盈，但账户整体仍处于回撤状态；不形成交易指令，仅建立核查队列。",
    })


def test_build_review_model_input_creates_stable_evidence_refs():
    model_input = service.build_review_model_input(_context())
    refs = {item["evidence_ref"] for item in model_input["evidence_catalog"]}
    assert {"account:overview", "holding:600000", "event:evt-1", "rotation:ai", "learning:scorecard"} <= refs
    assert model_input["output_limits"]["max_opportunities"] == 3
    assert "learning_feedback" in model_input
    account = next(item for item in model_input["evidence_catalog"] if item["evidence_ref"] == "account:overview")
    assert account["facts"]["account_state_semantics"] == {
        "priority": "account_total_pnl_over_current_holding_pnl",
        "account_total_state": "drawdown",
        "current_holding_state": "profit",
    }


def test_validate_review_rejects_unknown_evidence():
    model_input = service.build_review_model_input(_context())
    payload = _review().model_dump(mode="json")
    payload["opportunities"][0]["evidence_refs"] = ["rotation:not-provided"]
    _, errors, _ = service._validate_review(payload, model_input)
    assert any("未提供的证据编号" in error for error in errors)


def test_validate_review_rejects_direct_trade_instruction():
    model_input = service.build_review_model_input(_context())
    payload = _review().model_dump(mode="json")
    payload["opportunities"][0]["action_semantics"] = "建议立即买入并加仓。"
    _, errors, _ = service._validate_review(payload, model_input)
    assert "输出包含禁止的直接交易指令" in errors


def test_validate_review_demotes_stale_rotation_opportunity():
    context = _context()
    context["meta"]["freshness"]["rotation"]["status"] = "stale"
    model_input = service.build_review_model_input(context)

    review, errors, warnings = service._validate_review(
        _review().model_dump(mode="json"),
        model_input,
    )

    assert errors == []
    assert review.opportunities == []
    assert review.watch_items[0].subject == "AI"
    assert review.watch_items[0].confidence == "low"
    assert any("已降级为观察项" in warning for warning in warnings)


def test_validate_review_requires_account_drawdown_in_summary():
    model_input = service.build_review_model_input(_context())
    payload = _review().model_dump(mode="json")
    payload["summary"] = "当前持仓盈利，不形成交易指令，仅建立核查队列。"

    _, errors, _ = service._validate_review(payload, model_input)

    assert any("账户整体处于回撤" in error for error in errors)

    payload["summary"] = "当前持仓浮盈，但账户整体仍处于回撤状态，应优先审视历史亏损。"
    _, errors, _ = service._validate_review(payload, model_input)
    assert not any("账户整体处于回撤" in error for error in errors)


def test_validate_review_requires_every_weekly_operation_symbol(monkeypatch):
    monkeypatch.setattr(service, "_operation_review_period", lambda reference=None: "weekly")
    monkeypatch.setattr(outcomes, "build_learning_feedback", lambda: {
        "contract_version": "agent_learning_feedback.v3",
        "operation_feedback": {
            "weekly_symbol_operations": {
                "window_start": "2026-07-25",
                "window_end": "2026-07-31",
                "trading_dates": ["2026-07-25", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31"],
                "action_count": 2,
                "symbol_count": 1,
                "items": [{
                    "evidence_ref": "operation:weekly:2026-07-31:600000",
                    "symbol": "600000",
                    "name": "浦发银行",
                    "operation_count": 2,
                }],
            },
        },
    })
    model_input = service.build_review_model_input(_context())
    payload = _review().model_dump(mode="json")

    _, errors, _ = service._validate_review(payload, model_input)
    assert any("周复盘应至少选择一个代表性标的" in error for error in errors)

    payload["weekly_operation_review"] = {
        "window_start": "",
        "window_end": "",
        "trading_days": [],
        "action_count": 0,
        "symbol_count": 0,
        "items": [{
            "symbol": "600000",
            "name": "浦发银行",
            "operation_summary": "一买一卖，净变化为零。",
            "strategy_reflection": "当时没有直接建议，不能判断策略一致性。",
            "next_review_condition": "补充交易理由并观察后续表现。",
            "evidence_refs": ["operation:weekly:2026-07-31:600000"],
        }],
        "overall_reflection": "本周存在往返操作，需要核查交易纪律。",
    }
    review, errors, _ = service._validate_review(payload, model_input)
    assert errors == []
    assert review.weekly_operation_review.action_count == 2
    assert review.weekly_operation_review.symbol_count == 1


def test_validate_review_requires_every_daily_operation(monkeypatch):
    action_id = "snapshot-a:snapshot-b:600000"
    monkeypatch.setattr(outcomes, "build_learning_feedback", lambda: {
        "contract_version": "agent_learning_feedback.v3",
        "operation_feedback": {
            "weekly_symbol_operations": {
                "window_start": "2026-07-25",
                "window_end": "2026-07-31",
                "trading_dates": ["2026-07-25", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31"],
                "action_count": 1,
                "symbol_count": 1,
                "items": [{
                    "evidence_ref": "operation:weekly:2026-07-31:600000",
                    "symbol": "600000",
                    "name": "浦发银行",
                    "operation_count": 1,
                    "sequence": [{
                        "action_id": action_id,
                        "trading_date": "2026-07-31",
                        "action_type": "increased",
                        "quantity_delta": 1000,
                        "strategy_status": "aligned",
                        "user_reason": "估值修复",
                    }],
                }],
            },
        },
    })
    model_input = service.build_review_model_input(_context())
    payload = _review().model_dump(mode="json")
    payload["weekly_operation_review"] = {
        "window_start": "",
        "window_end": "",
        "trading_days": [],
        "action_count": 0,
        "symbol_count": 0,
        "items": [{
            "symbol": "600000",
            "name": "浦发银行",
            "operation_summary": "本周净买入1000股。",
            "strategy_reflection": "操作与当时策略一致。",
            "next_review_condition": "观察后续相对收益。",
            "evidence_refs": ["operation:weekly:2026-07-31:600000"],
        }],
        "overall_reflection": "本周操作方向一致。",
    }

    _, errors, _ = service._validate_review(payload, model_input)
    assert any("日复盘应至少选择一项代表性操作" in error for error in errors)

    payload["daily_operation_review"] = {
        "trading_date": "",
        "action_count": 0,
        "items": [{
            "action_id": "ps-a:ps-b:600000",
            "symbol": "600000",
            "name": "浦发银行",
            "action_type": "buy",
            "operation_summary": "买入1000股。",
            "strategy_reflection": "当时AI建议买入，操作与策略一致，理由已记录。",
            "next_review_condition": "观察后续相对收益。",
            "evidence_refs": ["operation:action:ps-a:ps-b:600000"],
        }],
        "overall_reflection": "当日一笔操作有明确理由。",
    }
    review, errors, _ = service._validate_review(payload, model_input)
    assert errors == []
    assert review.daily_operation_review.trading_date == "2026-07-31"
    assert review.daily_operation_review.action_count == 1
    assert review.daily_operation_review.items[0].action_id == action_id
    assert review.daily_operation_review.items[0].evidence_refs == [f"operation:action:{action_id}"]


def test_normalize_review_payload_cleans_symbols_and_caps_task_targets():
    payload = {
        "verification_tasks": [{
            "target_symbols": [
                "600000.SH", "000001.SZ", "000002.SZ", "000003.SZ",
                "000004.SZ", "000005.SZ", "600000",
            ],
        }],
        "daily_operation_review": {"items": [{"symbol": "600000.SH", "action_type": "increased"}]},
        "weekly_operation_review": {"items": [{"symbol": "000001.SZ"}]},
    }
    normalized = service._normalize_review_payload(payload)
    assert normalized["verification_tasks"][0]["target_symbols"] == [
        "600000", "000001", "000002", "000003", "000004",
    ]
    assert normalized["daily_operation_review"]["items"][0]["symbol"] == "600000"
    assert normalized["daily_operation_review"]["items"][0]["action_type"] == "buy"
    assert normalized["weekly_operation_review"]["items"][0]["symbol"] == "000001"


def test_normalize_review_payload_accepts_null_irrelevant_sections():
    normalized = service._normalize_review_payload({
        "verification_tasks": None,
        "daily_operation_review": None,
        "weekly_operation_review": {"window_start": None, "items": []},
    })
    assert normalized["verification_tasks"] == []
    assert normalized["daily_operation_review"]["trading_date"] == ""
    assert normalized["daily_operation_review"]["items"] == []
    assert normalized["weekly_operation_review"]["window_start"] == ""


def test_generate_daily_review_persists_validated_result(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "REVIEW_DIR", tmp_path)
    monkeypatch.setattr(service, "LATEST_PATH", tmp_path / "latest.json")
    monkeypatch.setattr(service, "build_daily_review_context", lambda force=False: _context())
    monkeypatch.setattr(service, "_model_name", lambda: "deepseek-v4-pro")
    monkeypatch.setattr(service, "_sync_tasks", lambda payload: None)
    monkeypatch.setattr(service, "_register_outcomes", lambda payload, model_input: None)
    monkeypatch.setattr(
        service,
        "_generate_with_correction",
        lambda model_input: (_review(), {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}, []),
    )

    result = service.generate_daily_review(force_context=True)

    assert result["status"] == "completed"
    assert result["model"] == "deepseek-v4-pro"
    assert result["context"]["force_context"] is True
    assert result["review"]["opportunities"][0]["evidence_refs"] == ["rotation:ai"]
    persisted = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert persisted["run_id"] == result["run_id"]


def test_failed_run_does_not_replace_latest(tmp_path, monkeypatch):
    latest_path = tmp_path / "latest.json"
    latest_path.write_text(json.dumps({"run_id": "existing"}), encoding="utf-8")
    monkeypatch.setattr(service, "REVIEW_DIR", tmp_path)
    monkeypatch.setattr(service, "LATEST_PATH", latest_path)
    monkeypatch.setattr(service, "build_daily_review_context", lambda force=False: _context())
    monkeypatch.setattr(service, "_model_name", lambda: "deepseek-v4-pro")
    monkeypatch.setattr(service, "_sync_tasks", lambda payload: None)
    monkeypatch.setattr(service, "_register_outcomes", lambda payload, model_input: None)
    monkeypatch.setattr(
        service,
        "_generate_with_correction",
        lambda model_input: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
    )

    with pytest.raises(RuntimeError, match="provider unavailable"):
        service.generate_daily_review()

    assert json.loads(latest_path.read_text(encoding="utf-8"))["run_id"] == "existing"


def test_followup_review_uses_completed_tool_evidence(tmp_path, monkeypatch):
    from app.agent_review import tasks

    parent = {
        "run_id": "daily-parent-001",
        "status": "completed",
        "review": _review().model_dump(mode="json"),
    }
    latest_path = tmp_path / "latest.json"
    latest_path.write_text(json.dumps(parent, ensure_ascii=False), encoding="utf-8")
    captured = {}
    monkeypatch.setattr(service, "REVIEW_DIR", tmp_path)
    monkeypatch.setattr(service, "LATEST_PATH", latest_path)
    monkeypatch.setattr(service, "build_daily_review_context", lambda force=False: _context())
    monkeypatch.setattr(service, "_model_name", lambda: "deepseek-v4-pro")
    monkeypatch.setattr(service, "_sync_tasks", lambda payload: None)
    monkeypatch.setattr(service, "_register_outcomes", lambda payload, model_input: None)
    monkeypatch.setattr(
        tasks,
        "task_evidence",
        lambda origin_run_id: [{
            "evidence_ref": "tool:task-001",
            "scope": "tool_verification",
            "task_id": "task-001",
            "subject": "AI",
            "facts": {"verification_status": "partial"},
        }],
    )

    def fake_generate(model_input):
        captured["input"] = model_input
        return _review(), {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}, []

    monkeypatch.setattr(service, "_generate_with_correction", fake_generate)

    result = service.generate_followup_review(parent_run_id="daily-parent-001")

    assert result["review_mode"] == "verification_followup"
    assert result["parent_run_id"] == "daily-parent-001"
    assert result["context"]["tool_evidence_count"] == 1
    refs = {item["evidence_ref"] for item in captured["input"]["evidence_catalog"]}
    assert "tool:task-001" in refs


def test_trade_reason_suggestion_is_constrained_to_editable_draft(monkeypatch):
    monkeypatch.setattr(
        service,
        "_call_model",
        lambda messages: (
            json.dumps({
                "reason_summary": "卖出部分沪电股份，降低高波动敞口；具体触发条件待用户补充。",
                "confidence": "medium",
                "questions": ["本次交易由哪个失效条件触发？"],
            }, ensure_ascii=False),
            {"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50},
            "stop",
        ),
    )
    monkeypatch.setattr(service, "_model_name", lambda: "deepseek-v4-pro")

    result = service.suggest_trade_reason(
        [{"normalized_symbol": "002463", "side": "sell", "quantity": 200}],
        [{"symbol": "002463", "name": "沪电股份"}],
    )

    assert result["confidence"] == "medium"
    assert "待用户补充" in result["reason_summary"]
    assert result["questions"] == ["本次交易由哪个失效条件触发？"]
