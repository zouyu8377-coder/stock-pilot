import json
from datetime import datetime
from types import SimpleNamespace

from app.agent_review import outcomes, service
from test_agent_review import _context


def test_daily_record_date_does_not_follow_stale_daily_k(monkeypatch):
    monkeypatch.setattr(service, "_now", lambda: datetime.fromisoformat("2026-09-15T17:00:00+08:00"))
    monkeypatch.setattr(outcomes, "build_learning_feedback", lambda: {
        "operation_feedback": {"weekly_symbol_operations": {
            "window_end": "2026-09-14", "records_checked_through": "2026-09-15", "items": []}}})
    result = service.build_review_model_input(_context())
    operations = result["learning_feedback"]["operation_feedback"]
    assert operations["daily_actions"]["trading_date"] == "2026-09-15"
    assert operations["weekly_symbol_operations"]["window_end"] == "2026-09-14"


def test_saved_structure_delta_is_not_a_confirmed_trade(tmp_path, monkeypatch):
    before = {"snapshot_id": "old", "snapshot_time": "2026-09-14T08:00:00Z", "cash_available": 200,
              "positions": [{"symbol": "603259", "quantity": 100, "avg_cost": -5}]}
    current = {"snapshot_id": "new", "snapshot_time": "2026-09-15T09:16:07Z", "cash_available": 100,
               "source_type": "manual", "positions": [{"symbol": "603259", "quantity": 200, "avg_cost": -2}]}
    path = tmp_path / "old.json"
    path.write_text(json.dumps(before), encoding="utf-8")
    original = path.read_bytes()
    snapshot = SimpleNamespace(model_dump=lambda **kwargs: current)
    monkeypatch.setattr(outcomes, "portfolio_service", SimpleNamespace(snapshots_dir=tmp_path, load_snapshot=lambda: snapshot))
    result = outcomes.current_account_record_status()
    assert result["holdings_updated_at"] == "2026-09-15T17:16:07+08:00"
    change = result["latest_saved_change"]
    assert change["event_type"] == "saved_account_snapshot_diff"
    assert change["user_confirmed"] is False
    assert change["position_changes"][0]["quantity_delta"] == 100
    assert change["account_changes"]["cash_delta"] == -100
    assert path.read_bytes() == original
    assert len(list(tmp_path.iterdir())) == 1
