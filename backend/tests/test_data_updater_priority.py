from __future__ import annotations

from datetime import date
from pathlib import Path

from app.core import data_updater as updater
from app.core import etf_data_updater as etf_updater


def test_run_sync_update_defers_slow_market_after_core_ready(tmp_path, monkeypatch):
    symbols = ["sh.000300", "sh.600001", "sh.600002", "sh.600003"]
    updated: set[str] = set()

    monkeypatch.setattr(updater, "STATUS_FILE", tmp_path / "update_status.json")
    monkeypatch.setattr(updater, "REQUEST_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(updater, "SLOW_SYMBOL_SECONDS", 5)
    monkeypatch.setattr(updater, "SLOW_PROBE_SYMBOLS", 2)
    monkeypatch.setattr(updater, "SLOW_DEGRADE_AFTER", 2)
    monkeypatch.setattr(updater, "_ensure_baostock_login", lambda: None)
    monkeypatch.setattr(updater, "_logout_baostock", lambda: None)
    monkeypatch.setattr(updater, "_market_files", lambda active_symbols=None: [Path(f"{symbol}.parquet") for symbol in symbols])

    def fake_check_update_status(target_date):
        remaining = [symbol for symbol in symbols if symbol not in updated]
        return not remaining, remaining, len(symbols)

    def fake_update_single_symbol(path, target_date):
        updated.add(path.stem)
        return True, None

    ticks = iter([0.0, 0.1, 1.0, 7.0, 8.0, 14.0, 15.0, 21.0])
    monkeypatch.setattr(updater.time, "perf_counter", lambda: next(ticks))
    monkeypatch.setattr(updater, "check_update_status", fake_check_update_status)
    monkeypatch.setattr(updater, "update_single_symbol", fake_update_single_symbol)

    result = updater.run_sync_update(date(2026, 6, 15), priority_symbols={"sh.000300"})
    status = updater.load_update_status()

    assert result["deferred"] is True
    assert status["status"] == "market_deferred"
    assert status["core_status"] == "complete"
    assert status["core_completed"] == 1
    assert status["market_processed"] == 2
    assert "sh.000300" in updated


def test_run_sync_etf_update_defers_slow_market_after_core_ready(tmp_path, monkeypatch):
    symbols = ["sz.159382", "sz.159001", "sz.159002", "sz.159003"]
    updated: set[str] = set()
    rows = updater.pd.DataFrame({"baostock_code": symbols})

    monkeypatch.setattr(etf_updater, "ETF_STATUS_FILE", tmp_path / "etf_update_status.json")
    monkeypatch.setattr(etf_updater, "REQUEST_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(etf_updater, "ETF_SLOW_SYMBOL_SECONDS", 5)
    monkeypatch.setattr(etf_updater, "SLOW_PROBE_SYMBOLS", 2)
    monkeypatch.setattr(etf_updater, "SLOW_DEGRADE_AFTER", 2)
    monkeypatch.setattr(etf_updater, "_ensure_baostock_login", lambda: None)
    monkeypatch.setattr(etf_updater, "_logout_baostock", lambda: None)
    monkeypatch.setattr(etf_updater, "load_etf_symbols", lambda: rows)
    monkeypatch.setattr(etf_updater, "is_symbol_updated", lambda path, target_date: path.stem in updated)

    def fake_update_single_etf(code, target_date):
        updated.add(code)
        return True, None

    ticks = iter([0.0, 0.1, 1.0, 7.0, 8.0, 14.0, 15.0, 21.0])
    monkeypatch.setattr(etf_updater.time, "perf_counter", lambda: next(ticks))
    monkeypatch.setattr(etf_updater, "update_single_etf", fake_update_single_etf)

    result = etf_updater.run_sync_etf_update(date(2026, 6, 15), priority_symbols={"sz.159382"})
    status = etf_updater.load_etf_update_status()

    assert result["deferred"] is True
    assert status["status"] == "market_deferred"
    assert status["core_status"] == "complete"
    assert status["core_completed"] == 1
    assert status["market_processed"] == 2
    assert etf_updater.etf_needs_update(date(2026, 6, 15)) is False
