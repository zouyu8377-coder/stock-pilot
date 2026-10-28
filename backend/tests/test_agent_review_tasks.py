from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.agent_review import tasks


def _review_run() -> dict:
    return {
        "run_id": "daily-test-001",
        "review": {
            "verification_tasks": [
                {
                    "priority": "high",
                    "subject": "医药ETF近期走势",
                    "task": "核查医药ETF（159929）近20日走势。",
                    "reason": "轮动证据陈旧",
                },
                {
                    "priority": "high",
                    "subject": "FOMC决议",
                    "task": "核查FOMC决议后的市场反应。",
                    "reason": "宏观事件影响持仓",
                },
                {
                    "priority": "low",
                    "subject": "管理层预期",
                    "task": "与公司管理层确认未来订单预期。",
                    "reason": "本地数据无法验证",
                },
                {
                    "priority": "high",
                    "subject": "紫金矿业价格验证",
                    "task": "核查近期趋势和相对强弱。",
                    "reason": "价格证据不足",
                    "target_symbols": ["601899"],
                    "evidence_type": "market_snapshot",
                    "missing_evidence": ["近期行情"],
                    "success_criteria": "取得最新交易日及近20日行情",
                },
                {
                    "priority": "high",
                    "subject": "沪电股份订单验证",
                    "task": "核查订单与收入结构公告。",
                    "reason": "基本面证据不足",
                    "target_symbols": ["002463"],
                    "evidence_type": "announcement",
                    "missing_evidence": ["订单公告"],
                    "success_criteria": "取得可追溯的公司公告或调研记录",
                },
            ],
        },
    }


@pytest.fixture
def task_store(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks, "TASK_DIR", tmp_path)
    monkeypatch.setattr(tasks, "TASKS_PATH", tmp_path / "tasks.json")
    monkeypatch.setattr(tasks, "SOURCE_HEALTH_PATH", tmp_path / "source_health.json")
    return tmp_path


def test_low_confidence_conclusion_creates_autonomous_verification_task(task_store):
    review_run = {
        "run_id": "low-confidence-001",
        "review": {
            "opportunities": [{
                "subject": "银行方向早期机会",
                "confidence": "low",
                "evidence_refs": ["rotation:bank"],
                "counter_evidence_refs": [],
            }],
            "risks": [],
            "watch_items": [],
            "verification_tasks": [],
        },
    }

    created = tasks.sync_review_tasks(review_run)

    assert len(created) == 1
    assert created[0]["planning_origin"] == "low_confidence_auto"
    assert created[0]["tool"]["name"] == "rotation_refresh"
    assert created[0]["status"] == "pending"


def test_source_health_tracks_partial_success_as_half_weight(task_store):
    tasks._record_source_attempt("stock_snapshot", status="completed")
    tasks._record_source_attempt(
        "stock_snapshot",
        status="partial",
        failure_category="incomplete_history",
    )

    health = tasks.source_health()

    assert health[0]["attempt_count"] == 2
    assert health[0]["success_count"] == 1
    assert health[0]["partial_count"] == 1
    assert health[0]["reliability_pct"] == 75.0


def test_explicit_verification_for_low_confidence_subject_keeps_low_confidence_origin(task_store):
    review_run = {
        "run_id": "low-explicit-001",
        "review": {
            "opportunities": [{
                "subject": "银行方向早期机会",
                "confidence": "low",
                "evidence_refs": ["rotation:bank"],
                "counter_evidence_refs": [],
            }],
            "risks": [],
            "watch_items": [],
            "verification_tasks": [{
                "priority": "high",
                "subject": "银行方向早期机会",
                "task": "重建银行方向轮动证据",
                "evidence_type": "rotation",
            }],
        },
    }

    created = tasks.sync_review_tasks(review_run)

    assert len(created) == 1
    assert created[0]["planning_origin"] == "low_confidence_model_planned"


def test_execute_pending_tasks_can_be_limited_to_planning_origin(monkeypatch):
    queued = [
        {
            "task_id": "low-task",
            "status": "pending",
            "planning_origin": "low_confidence_auto",
            "tool": {"auto_executable": True},
        },
        {
            "task_id": "normal-task",
            "status": "pending",
            "planning_origin": "model_planned",
            "tool": {"auto_executable": True},
        },
    ]
    executed: list[str] = []
    monkeypatch.setattr(tasks, "recover_interrupted_tasks", lambda: [])
    monkeypatch.setattr(tasks, "list_tasks", lambda **kwargs: queued)
    monkeypatch.setattr(
        tasks,
        "execute_task",
        lambda task_id: executed.append(task_id) or {"task_id": task_id, "status": "completed"},
    )

    result = tasks.execute_pending_tasks(planning_origins={"low_confidence_auto"})

    assert executed == ["low-task"]
    assert result[0]["task_id"] == "low-task"


def test_existing_model_task_is_migrated_when_subject_becomes_low_confidence(task_store):
    review_run = {
        "run_id": "confidence-change-001",
        "review": {
            "opportunities": [{"subject": "银行方向", "confidence": "medium"}],
            "risks": [],
            "watch_items": [],
            "verification_tasks": [{
                "subject": "银行方向",
                "task": "重建银行方向轮动证据",
                "evidence_type": "rotation",
            }],
        },
    }
    first = tasks.sync_review_tasks(review_run)
    assert first[0]["planning_origin"] == "model_planned"

    review_run["review"]["opportunities"][0]["confidence"] = "low"
    migrated = tasks.sync_review_tasks(review_run)

    assert len(migrated) == 1
    assert migrated[0]["planning_origin"] == "low_confidence_model_planned"


def test_sync_review_tasks_maps_only_whitelisted_tools(task_store):
    created = tasks.sync_review_tasks(_review_run())
    by_subject = {item["subject"]: item for item in created}

    stock = by_subject["医药ETF近期走势"]
    assert stock["tool"]["name"] == "stock_snapshot"
    assert stock["tool"]["arguments"] == {"symbols": ["159929"]}
    assert stock["status"] == "pending"

    event = by_subject["FOMC决议"]
    assert event["tool"]["name"] == "event_snapshot"
    assert event["status"] == "pending"

    manual = by_subject["管理层预期"]
    assert manual["tool"]["name"] == "manual_review"
    assert manual["status"] == "manual_required"

    named_stock = by_subject["紫金矿业价格验证"]
    assert named_stock["tool"]["name"] == "stock_snapshot"
    assert named_stock["tool"]["arguments"] == {"symbols": ["601899"]}
    assert named_stock["success_criteria"] == "取得最新交易日及近20日行情"

    disclosure = by_subject["沪电股份订单验证"]
    assert disclosure["tool"]["name"] == "disclosure_snapshot"
    assert disclosure["tool"]["arguments"] == {"symbols": ["002463"]}


def test_sync_review_tasks_is_idempotent_per_review(task_store):
    tasks.sync_review_tasks(_review_run())
    tasks.sync_review_tasks(_review_run())
    persisted = json.loads(tasks.TASKS_PATH.read_text(encoding="utf-8"))
    assert len(persisted) == 5


def test_execute_task_persists_tool_evidence(task_store, monkeypatch):
    created = tasks.sync_review_tasks(_review_run())
    stock = next(item for item in created if item["tool"]["name"] == "stock_snapshot")
    monkeypatch.setattr(
        tasks,
        "_execute_tool",
        lambda name, arguments: {
            "symbol": arguments["symbols"][0],
            "history": {"latest_date": "2026-07-29"},
        },
    )

    completed = tasks.execute_task(stock["task_id"])

    assert completed["status"] == "completed"
    assert completed["attempt_count"] == 1
    assert completed["result"]["evidence_ref"] == f"tool:{stock['task_id']}"
    evidence = tasks.task_evidence(origin_run_id="daily-test-001")
    assert evidence[0]["facts"]["symbol"] == "159929"


def test_execute_task_rejects_manual_tool(task_store):
    created = tasks.sync_review_tasks(_review_run())
    manual = next(item for item in created if item["status"] == "manual_required")

    with pytest.raises(ValueError, match="需要人工核查"):
        tasks.execute_task(manual["task_id"])


def test_execute_failure_is_auditable(task_store, monkeypatch):
    created = tasks.sync_review_tasks(_review_run())
    event = next(item for item in created if item["tool"]["name"] == "event_snapshot")
    monkeypatch.setattr(
        tasks,
        "_execute_tool",
        lambda name, arguments: (_ for _ in ()).throw(RuntimeError("source offline")),
    )

    failed = tasks.execute_task(event["task_id"])

    assert failed["status"] == "retry_wait"
    assert failed["result"] is None
    assert failed["error"] == "source offline"
    assert failed["failure_category"] == "transient_source_error"
    assert failed["next_retry_at"]


def test_partial_tool_result_does_not_claim_task_completed(task_store, monkeypatch):
    created = tasks.sync_review_tasks(_review_run())
    event = next(item for item in created if item["tool"]["name"] == "event_snapshot")
    monkeypatch.setattr(
        tasks,
        "_execute_tool",
        lambda name, arguments: {
            "verification_status": "partial",
            "remaining_gaps": ["尚无事件落地后的市场反应"],
        },
    )

    partial = tasks.execute_task(event["task_id"])

    assert partial["status"] == "partial"
    evidence = tasks.task_evidence(origin_run_id="daily-test-001")
    assert evidence[0]["facts"]["remaining_gaps"]


def test_company_name_without_code_resolves_to_stock_snapshot(task_store):
    review = {
        "run_id": "daily-name-only",
        "review": {
            "verification_tasks": [{
                "priority": "medium",
                "subject": "紫金矿业技术观察",
                "task": "核查紫金矿业近期价格趋势。",
                "reason": "趋势结论置信度低",
            }],
        },
    }

    created = tasks.sync_review_tasks(review)

    assert created[0]["tool"]["name"] == "stock_snapshot"
    assert created[0]["tool"]["arguments"] == {"symbols": ["601899"]}


def test_spaced_etf_name_and_financial_type_resolve_to_disclosure(task_store):
    review = {
        "run_id": "daily-spaced-etf",
        "review": {
            "verification_tasks": [{
                "priority": "medium",
                "subject": "黄金 ETF 财务核查",
                "task": "核查基金公开报告中的持仓变化。",
                "reason": "底层暴露证据不足",
                "evidence_type": "financial",
            }],
        },
    }

    created = tasks.sync_review_tasks(review)

    assert created[0]["target_symbols"] == ["159934"]
    assert created[0]["tool"]["name"] == "disclosure_snapshot"


def test_disclosure_snapshot_combines_public_facts_and_local_verification(monkeypatch):
    from app.disclosure_verification import service
    monkeypatch.setattr(service, "verify_symbol_disclosures", lambda symbol: {
        "status": "verified", "counts": {"supported": 1},
    })
    monkeypatch.setattr(
        tasks,
        "get_disclosure_facts",
        lambda symbol, force=False: {
            "success": True,
            "data_status": "fresh",
            "data": {
                "announcements": [{"title": "订单公告"}],
                "surveys": [{"title": "机构调研"}],
            },
        },
    )
    monkeypatch.setattr(
        tasks,
        "load_disclosure_verification",
        lambda symbol: {"symbol": symbol, "verification_status": "verified"},
    )

    result = tasks._execute_tool("disclosure_snapshot", {"symbols": ["002463"]})

    assert result["verification_status"] == "complete"
    assert result["snapshots"][0]["symbol"] == "002463"
    assert result["snapshots"][0]["announcements"][0]["title"] == "订单公告"


def test_interrupted_running_task_returns_to_pending_queue(task_store):
    task = tasks.sync_review_tasks(_review_run())[0]
    stored = json.loads(tasks.TASKS_PATH.read_text(encoding="utf-8"))
    stored[0]["status"] = "running"
    stored[0]["started_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    tasks.TASKS_PATH.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")

    recovered = tasks.recover_interrupted_tasks(stale_minutes=15)

    assert recovered[0]["status"] == "pending"
    assert recovered[0]["recovery_count"] == 1
    assert recovered[0]["failure_category"] == "interrupted"
