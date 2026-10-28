from __future__ import annotations

import pytest

from app.agent_review import coverage_planner, tasks


@pytest.fixture
def task_store(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks, "TASK_DIR", tmp_path)
    monkeypatch.setattr(tasks, "TASKS_PATH", tmp_path / "tasks.json")
    monkeypatch.setattr(tasks, "SOURCE_HEALTH_PATH", tmp_path / "source_health.json")
    return tmp_path


def _dashboard() -> dict:
    return {
        "positions": [
            {
                "symbol": "600001.SH",
                "name": "高权重标的",
                "quantity": 100,
                "portfolio_weight_pct": 20.0,
                "trend": {"data_status": "unavailable"},
                "attractiveness": {"coverage": 35, "dimensions": [
                    {"key": "trend_strength", "coverage": 0, "weight": 25},
                    {"key": "evidence_change", "coverage": 35, "weight": 30},
                ]},
            },
            {
                "symbol": "600002.SH",
                "name": "低权重标的",
                "quantity": 100,
                "portfolio_weight_pct": 2.0,
                "trend": {"data_status": "available"},
                "attractiveness": {"coverage": 40, "dimensions": [
                    {"key": "valuation_consensus", "coverage": 20, "weight": 20},
                ]},
            },
        ],
        "theme_evidence_radar": {"themes": []},
        "market_event_radar": {"events": []},
        "risk_queue": [{"symbol": "600001.SH", "score": 6}],
        "opportunity_queue": [],
    }


def test_coverage_plan_prioritizes_high_weight_decision_sensitive_gaps(monkeypatch):
    monkeypatch.setattr(
        coverage_planner,
        "get_dashboard_bundle",
        lambda force=False: {"dashboard": _dashboard()},
    )

    plan = coverage_planner.build_coverage_plan(max_candidates=10)

    assert plan["summary"]["active_position_count"] == 2
    assert plan["candidates"][0]["target_symbols"] == ["600001"]
    assert plan["candidates"][0]["coverage_gap"]["decision_sensitive"] is True
    assert plan["candidates"][0]["evidence_type"] == "market_snapshot"
    impact = plan["candidates"][0]["coverage_gap"]["dimension_impacts"][0]
    assert impact["coverage_before_pct"] == 0
    assert impact["target_coverage_pct"] == 100
    assert impact["metric"] == "health"
    assert impact["max_account_coverage_gain_pp"] > 0


def test_coverage_plan_explains_retryable_and_blocked_gaps_without_valuation(monkeypatch):
    dashboard = _dashboard()
    dashboard["positions"][0]["attractiveness"]["dimensions"].append({
        "key": "valuation_consensus", "coverage": 20, "weight": 20,
    })
    monkeypatch.setattr(
        coverage_planner,
        "get_dashboard_bundle",
        lambda force=False: {"dashboard": dashboard},
    )
    monkeypatch.setattr(coverage_planner, "coverage_source_blocks", lambda: {
        "600001": "公告索引不可用：缺少 Tushare token",
    })

    plan = coverage_planner.build_coverage_plan(max_candidates=20)
    gaps = {item["evidence_type"]: item for item in plan["candidates"] if item["subject"] == "高权重标的"}

    assert gaps["market_snapshot"]["refreshability"]["state"] == "retryable"
    assert gaps["announcement"]["refreshability"]["state"] == "source_blocked"
    assert "manual_review" not in gaps
    assert plan["summary"]["source_blocked_count"] >= 1
    assert plan["summary"]["manual_review_count"] == 0


def test_coverage_planner_creates_bounded_auto_tasks(task_store, monkeypatch):
    monkeypatch.setattr(
        tasks,
        "build_coverage_plan",
        lambda max_candidates, force=False: {
            "summary": {"health_coverage_pct": 49, "attractiveness_coverage_pct": 45, "joint_coverage_pct": 45, "candidate_count": 2},
            "candidates": [
                {
                    "priority": "high",
                    "priority_score": 90,
                    "subject": "紫金矿业",
                    "task": "补齐估值证据并重新评估覆盖率",
                    "reason": "估值验证不足",
                    "target_symbols": ["601899"],
                    "evidence_type": "manual_review",
                    "missing_evidence": [],
                    "success_criteria": "人工完成估值核查",
                    "coverage_gap": {"dimension": "attractiveness.valuation_consensus", "decision_sensitive": True},
                },
                {
                    "priority": "high",
                    "priority_score": 81,
                    "subject": "紫金矿业",
                    "task": "补齐趋势与波动证据并重新评估覆盖率",
                    "reason": "趋势覆盖不足",
                    "target_symbols": ["601899"],
                    "evidence_type": "market_snapshot",
                    "missing_evidence": ["趋势与波动：覆盖 0% → 目标 100%"],
                    "success_criteria": "取得新事实后重新计算覆盖率",
                    "coverage_gap": {"dimension": "health.trend", "decision_sensitive": True},
                },
                {
                    "priority": "medium",
                    "priority_score": 52,
                    "subject": "药明康德",
                    "task": "补齐公告证据并重新评估覆盖率",
                    "reason": "公告验证不足",
                    "target_symbols": ["603259"],
                    "evidence_type": "announcement",
                    "missing_evidence": [],
                    "success_criteria": "取得新事实后重新计算覆盖率",
                    "coverage_gap": {"dimension": "health.thesis", "decision_sensitive": False},
                },
            ],
        },
    )

    planned = tasks.plan_coverage_gap_tasks({"run_id": "coverage-run"}, max_tasks=1)

    assert planned["created_count"] == 1
    task = planned["created"][0]
    assert task["planning_origin"] == tasks.COVERAGE_GAP_ORIGIN
    assert task["tool"]["name"] == "stock_snapshot"
    assert task["coverage_gap"]["dimension"] == "health.trend"
