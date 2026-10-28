from datetime import date, time

import pandas as pd

from app.analysis_packet.snapshot_builder import _daily_k_summary
from app.collector.history.base_market_provider import normalize_symbol
from app.collector.realtime.easyquotation_provider import _quote_symbol
from app.core.data_updater import get_last_trading_date
from app.market_breadth import service as breadth_service


def test_daily_k_target_uses_current_trade_day_only_after_close():
    assert get_last_trading_date(date(2026, 8, 17), time(10, 0)) == date(2026, 8, 14)
    assert get_last_trading_date(date(2026, 8, 17), time(15, 30)) == date(2026, 8, 17)
    assert get_last_trading_date(date(2026, 8, 16), time(16, 0)) == date(2026, 8, 14)


def test_base_market_symbol_normalization_accepts_ts_code_and_baostock_code():
    assert normalize_symbol("603259.SH") == "sh.603259"
    assert normalize_symbol("SZ.002463") == "sz.002463"
    assert normalize_symbol("159929.SZ") == "sz.159929"
    assert normalize_symbol("sh.000001") == "sh.000001"
    assert normalize_symbol("000300.SH") == "sh.000300"
    assert normalize_symbol("000001") == "sz.000001"


def test_realtime_quote_symbol_normalization_accepts_ts_code_and_baostock_code():
    assert _quote_symbol("603259.SH") == "603259"
    assert _quote_symbol("SZ.002463") == "002463"


def test_daily_k_summary_includes_volume_amount_and_turnover_fields():
    history = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=25),
        "open": range(25),
        "high": range(25),
        "low": range(25),
        "close": range(25),
        "volume": range(100, 125),
        "amount": range(1000, 1025),
        "turn": [1.2] * 25,
        "pctChg": [1.0] * 25,
    })

    summary = _daily_k_summary(history)

    assert summary["turnover_rate"] == 1.2
    assert summary["volume_ma_5"] is not None
    assert summary["volume_ma_10"] is not None
    assert summary["volume_ma_20"] is not None
    assert summary["amount_ma_20"] is not None
    assert summary["volume_vs_ma_20_ratio"] is not None


def test_market_breadth_aggregates_shenzhen_and_shanghai(tmp_path, monkeypatch):
    market_dir = tmp_path / "base_market"
    market_dir.mkdir()
    metadata = tmp_path / "stock_meta.parquet"
    cache_file = tmp_path / "market_breadth.json"
    pd.DataFrame({"ts_code": ["600000.SH", "000001.SZ"]}).to_parquet(metadata, index=False)
    dates = pd.date_range("2026-08-08", periods=5, freq="B").strftime("%Y-%m-%d")
    pd.DataFrame({"date": dates, "amount": [50_000_000] * 4 + [100_000_000], "pctChg": [0.1] * 4 + [10.0]}).to_parquet(market_dir / "sh.600000.parquet", index=False)
    pd.DataFrame({"date": dates, "amount": [100_000_000] * 4 + [200_000_000], "pctChg": [-0.1] * 4 + [-10.0]}).to_parquet(market_dir / "sz.000001.parquet", index=False)
    monkeypatch.setattr(breadth_service, "MARKET_DIR", market_dir)
    monkeypatch.setattr(breadth_service, "METADATA_FILE", metadata)
    monkeypatch.setattr(breadth_service, "CACHE_FILE", cache_file)

    result = breadth_service.rebuild_market_breadth("2026-08-14")

    assert result["coverage_count"] == 2
    assert result["total"]["advance_count"] == 1
    assert result["total"]["decline_count"] == 1
    assert result["total"]["turnover_100m_yuan"] == 3.0
    assert result["total"]["limit_up_count"] == 1
    assert result["total"]["limit_down_count"] == 1
    assert result["total"]["turnover_change_pct"] == 100.0
    assert result["total"]["turnover_ma_5_100m_yuan"] == 1.8
