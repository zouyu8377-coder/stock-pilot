from __future__ import annotations

import json
from datetime import datetime, timezone

from app.portfolio import task_evidence


def test_completed_market_snapshot_becomes_auditable_trend_override(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps([{
        "task_id": "task-market-1",
        "planning_origin": "coverage_gap_auto",
        "tool": {"name": "stock_snapshot"},
        "status": "completed",
        "result": {"payload": {
            "retrieved_at": "2026-08-16T01:00:00+00:00",
            "snapshots": [{
                "symbol": "603259",
                "quote": {"price": 159.24, "change_pct": -1.9},
                "history": {
                    "latest_date": "2026-08-14",
                    "latest_close": 159.24,
                    "ma20": 138.7,
                    "price_vs_ma20_pct": 14.8,
                    "return_5d_pct": 2.85,
                    "return_20d_pct": 35.08,
                    "return_60d_pct": 52.78,
                },
            }],
        }},
    }]), encoding="utf-8")
    monkeypatch.setattr(task_evidence, "TASKS_PATH", path)

    overrides = task_evidence.completed_market_trend_overrides(
        now=datetime(2026, 8, 16, 2, 0, tzinfo=timezone.utc),
    )

    assert overrides["603259"]["data_status"] == "available"
    assert overrides["603259"]["daily_k_as_of"] == "2026-08-14"
    assert overrides["603259"]["evidence_task_id"] == "task-market-1"
    assert overrides["603259"]["trend_state"] == "站上MA20"


def test_missing_tushare_token_does_not_permanently_block_disclosure_retry(tmp_path, monkeypatch):
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps([{
        "planning_origin": "coverage_gap_auto",
        "target_symbols": ["603259.SH"],
        "status": "partial",
        "result": {"payload": {
            "remaining_gaps": [
                "603259 disclosure index unavailable: Tushare token is not configured."
            ],
        }},
    }]), encoding="utf-8")
    monkeypatch.setattr(task_evidence, "TASKS_PATH", path)

    assert task_evidence.coverage_source_blocks() == {}
