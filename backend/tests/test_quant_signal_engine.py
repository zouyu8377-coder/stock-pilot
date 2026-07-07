import pandas as pd

from app.quant.signal_engine import _backtest, _limit_flags, build_quant_signal


def _history(closes: list[float], volume: list[float] | None = None) -> pd.DataFrame:
    volume = volume or [1_000_000] * len(closes)
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=len(closes), freq="B"),
            "open": [value * 0.995 for value in closes],
            "high": [value * 1.02 for value in closes],
            "low": [value * 0.98 for value in closes],
            "close": closes,
            "volume": volume,
        }
    )


def test_quant_signal_builds_bullish_trade_plan_without_lookahead_claims():
    closes = [10 + index * 0.05 for index in range(180)]

    result = build_quant_signal(_history(closes))

    assert result["status"] == "available"
    assert result["score"] > 25
    assert result["action"] in {"buy_setup", "accumulate_on_pullback"}
    assert result["trade_plan"]["stop_price"] < result["trade_plan"]["reference_price"]
    assert result["trade_plan"]["target_price_2r"] > result["trade_plan"]["reference_price"]
    assert 0 < result["trade_plan"]["suggested_max_position_pct"] <= 25
    assert result["backtest"]["status"] == "available"
    assert "next trading day" in result["backtest"]["rule"]


def test_quant_signal_blocks_position_budget_for_bearish_series():
    closes = [30 - index * 0.08 for index in range(180)]

    result = build_quant_signal(_history(closes))

    assert result["status"] == "available"
    assert result["score"] < -25
    assert result["action"] in {"risk_off", "avoid_or_reduce"}
    assert result["trade_plan"]["suggested_max_position_pct"] == 0


def test_quant_signal_does_not_report_backtest_stats_with_short_history():
    closes = [10 + index * 0.03 for index in range(80)]

    result = build_quant_signal(_history(closes))

    assert result["status"] == "available"
    assert result["backtest"]["status"] == "insufficient_history"
    assert "annual_return_pct" not in result["backtest"]


def test_quant_signal_accepts_akshare_chinese_columns():
    closes = [10 + index * 0.04 for index in range(80)]
    frame = pd.DataFrame(
        {
            "收盘": closes,
            "最高": [value * 1.01 for value in closes],
            "最低": [value * 0.99 for value in closes],
            "成交量": [500_000] * len(closes),
        }
    )

    result = build_quant_signal(frame)

    assert result["status"] == "available"
    assert result["metrics"]["atr14"] is not None


def test_backtest_blocks_buying_at_limit_up_close():
    frame = pd.DataFrame(
        {
            "close": [10.0] * 130,
            "ma60": [9.0] * 130,
            "raw_score": [-10.0] * 60 + [40.0] * 70,
        }
    )
    flags = pd.DataFrame(
        {
            "limit_up": [False] * 60 + [True] + [False] * 69,
            "limit_down": [False] * 130,
        }
    )

    constraints = _backtest(frame, flags)["execution_constraints"]
    assert constraints["price_limits_modeled"] is True
    assert constraints["blocked_limit_up_buys"] == 1


def test_backtest_carries_position_when_limit_down_blocks_exit():
    frame = pd.DataFrame(
        {
            "close": [10.0] * 130,
            "ma60": [9.0] * 130,
            "raw_score": [40.0] * 60 + [-10.0] * 70,
        }
    )
    flags = pd.DataFrame(
        {
            "limit_up": [False] * 130,
            "limit_down": [False] * 60 + [True] + [False] * 69,
        }
    )

    constraints = _backtest(frame, flags)["execution_constraints"]
    assert constraints["blocked_limit_down_sells"] == 1
    assert constraints["t_plus_one_modeled"] is True
    assert constraints["minimum_holding_trading_days"] == 1


def test_st_stock_uses_five_percent_price_limit():
    closes = [10 + index * 0.01 for index in range(180)]
    frame = _history(closes)
    limit_day = 100
    previous_close = frame.loc[limit_day - 1, "close"]
    limit_close = previous_close * 1.05
    frame.loc[limit_day, ["open", "high", "low", "close"]] = limit_close
    frame["pctChg"] = frame["close"].pct_change() * 100

    flags = _limit_flags(
        frame,
        pd.to_numeric(frame["close"]),
        symbol="600000",
        name="ST测试",
    )

    assert bool(flags.loc[limit_day, "limit_up"]) is True
    assert flags.loc[limit_day, "limit_pct"] == 5.0
