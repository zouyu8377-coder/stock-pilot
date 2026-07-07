from __future__ import annotations

import math
from datetime import date
from typing import Any

import pandas as pd


MIN_SIGNAL_ROWS = 60
MIN_BACKTEST_ROWS = 120


def _column(df: pd.DataFrame, *names: str) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    return None


def _series(df: pd.DataFrame, *names: str) -> pd.Series | None:
    column = _column(df, *names)
    if column is None:
        return None
    values = pd.to_numeric(df[column], errors="coerce")
    return values if values.notna().any() else None


def _finite(value: Any, digits: int = 2) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, digits)


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _pct_return(close: pd.Series, periods: int) -> float | None:
    if len(close) <= periods or close.iloc[-periods - 1] <= 0:
        return None
    return float((close.iloc[-1] / close.iloc[-periods - 1] - 1) * 100)


def _rsi(close: pd.Series, periods: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / periods, adjust=False, min_periods=periods).mean()
    avg_loss = loss.ewm(alpha=1 / periods, adjust=False, min_periods=periods).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    result = 100 - 100 / (1 + rs)
    return result.fillna(50)


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, periods: int = 14) -> pd.Series:
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / periods, adjust=False, min_periods=periods).mean()


def _max_drawdown(close: pd.Series, periods: int = 60) -> float:
    window = close.tail(periods)
    drawdown = window / window.cummax() - 1
    return float(drawdown.min() * 100)


def _score_frame(close: pd.Series, volume: pd.Series | None) -> pd.DataFrame:
    frame = pd.DataFrame(index=close.index)
    frame["close"] = close
    frame["ma20"] = close.rolling(20).mean()
    frame["ma60"] = close.rolling(60).mean()
    frame["return_20d"] = close.pct_change(20)
    frame["return_60d"] = close.pct_change(60)
    frame["volatility_20d"] = close.pct_change().rolling(20).std() * math.sqrt(252)
    frame["rsi14"] = _rsi(close)

    trend = (
        (frame["close"] > frame["ma20"]).astype(float) * 40
        + (frame["ma20"] > frame["ma60"]).astype(float) * 35
        + (frame["ma20"].pct_change(10) > 0).astype(float) * 25
    )
    frame["trend_score"] = trend * 2 - 100

    momentum = (
        frame["return_20d"].clip(-0.15, 0.15) / 0.15 * 55
        + frame["return_60d"].clip(-0.30, 0.30) / 0.30 * 45
    )
    overextension = ((frame["rsi14"] - 70).clip(lower=0) * 1.5).clip(upper=25)
    oversold = ((30 - frame["rsi14"]).clip(lower=0) * 0.5).clip(upper=10)
    frame["momentum_score"] = (momentum - overextension - oversold).clip(-100, 100)

    if volume is not None:
        aligned_volume = volume.reindex(frame.index)
        volume_ratio = aligned_volume / aligned_volume.rolling(20).mean()
        direction = close.pct_change().apply(lambda value: 1 if value > 0 else -1 if value < 0 else 0)
        frame["volume_score"] = ((volume_ratio - 1) * 80 * direction).clip(-100, 100).fillna(0)
    else:
        frame["volume_score"] = 0.0

    volatility_penalty = ((frame["volatility_20d"] - 0.25).clip(lower=0) * 120).clip(upper=35)
    frame["raw_score"] = (
        frame["trend_score"] * 0.45
        + frame["momentum_score"] * 0.35
        + frame["volume_score"] * 0.20
        - volatility_penalty
    ).clip(-100, 100)
    return frame


def _price_limit_pct(symbol: str, name: str, trading_date: date | None) -> float:
    code = symbol.split(".", 1)[0].strip().zfill(6)
    upper_name = name.upper()
    if "ST" in upper_name:
        return 5.0
    if code.startswith(("4", "8", "92")):
        return 30.0
    if code.startswith("688"):
        return 20.0
    if code.startswith(("300", "301")):
        reform_date = date(2020, 8, 24)
        return 20.0 if trading_date is None or trading_date >= reform_date else 10.0
    return 10.0


def _limit_flags(
    history: pd.DataFrame,
    close: pd.Series,
    *,
    symbol: str,
    name: str,
) -> pd.DataFrame:
    high = _series(history, "high", "最高")
    low = _series(history, "low", "最低")
    pct_change = _series(history, "pctChg", "pct_chg", "涨跌幅")
    date_column = _column(history, "date", "日期")
    dates = (
        pd.to_datetime(history[date_column], errors="coerce").reindex(close.index)
        if date_column
        else pd.Series(pd.NaT, index=close.index)
    )
    if pct_change is None:
        pct_change = close.pct_change() * 100
    else:
        pct_change = pct_change.reindex(close.index)
    if high is not None:
        at_high = close >= high.reindex(close.index) * (1 - 1e-6)
    else:
        at_high = pd.Series(True, index=close.index)
    if low is not None:
        at_low = close <= low.reindex(close.index) * (1 + 1e-6)
    else:
        at_low = pd.Series(True, index=close.index)

    thresholds = pd.Series(
        [
            _price_limit_pct(
                symbol,
                name,
                value.date() if not pd.isna(value) else None,
            )
            for value in dates
        ],
        index=close.index,
        dtype=float,
    )
    tolerance = 0.2
    return pd.DataFrame(
        {
            "limit_pct": thresholds,
            "limit_up": at_high & (pct_change >= thresholds - tolerance),
            "limit_down": at_low & (pct_change <= -thresholds + tolerance),
        },
        index=close.index,
    )


def _action(score: float, close: float, ma20: float, ma60: float) -> str:
    if score >= 55 and close > ma20 > ma60:
        return "buy_setup"
    if score >= 25 and close > ma20:
        return "accumulate_on_pullback"
    if score <= -55 and close < ma20 < ma60:
        return "avoid_or_reduce"
    if score <= -25 and close < ma20:
        return "risk_off"
    return "hold_or_wait"


def _backtest(
    frame: pd.DataFrame,
    limit_flags: pd.DataFrame,
) -> dict[str, Any]:
    usable = frame.dropna(subset=["raw_score", "ma60"]).copy()
    if len(usable) < MIN_BACKTEST_ROWS:
        return {
            "status": "insufficient_history",
            "sample_days": int(len(usable)),
            "minimum_days": MIN_BACKTEST_ROWS,
            "note": "No statistical win rate is reported when history is insufficient.",
        }

    usable = usable.join(limit_flags, how="left")
    returns = usable["close"].pct_change().fillna(0)
    position = pd.Series(0.0, index=usable.index)
    held = False
    acquired_index: int | None = None
    blocked_limit_up_buys = 0
    blocked_limit_down_sells = 0
    blocked_t1_sells = 0
    completed_trades = 0

    for row_number, (_, row) in enumerate(usable.iterrows()):
        position.iloc[row_number] = 1.0 if held else 0.0
        wants_position = bool(row["raw_score"] >= 25)
        if wants_position and not held:
            if bool(row.get("limit_up", False)):
                blocked_limit_up_buys += 1
                continue
            held = True
            acquired_index = row_number
        elif not wants_position and held:
            if acquired_index is not None and row_number <= acquired_index:
                blocked_t1_sells += 1
                continue
            if bool(row.get("limit_down", False)):
                blocked_limit_down_sells += 1
                continue
            held = False
            acquired_index = None
            completed_trades += 1

    strategy_returns = position * returns
    active = strategy_returns[position > 0]
    equity = (1 + strategy_returns).cumprod()
    benchmark = (1 + returns).cumprod()
    years = max(len(strategy_returns) / 252, 1 / 252)
    annual_return = equity.iloc[-1] ** (1 / years) - 1
    benchmark_annual_return = benchmark.iloc[-1] ** (1 / years) - 1
    annual_volatility = strategy_returns.std() * math.sqrt(252)
    sharpe = annual_return / annual_volatility if annual_volatility > 0 else None
    drawdown = equity / equity.cummax() - 1

    return {
        "status": "available",
        "sample_days": int(len(usable)),
        "rule": (
            "Trade at daily close when score >= 25; a limit-up close cannot be bought, "
            "a limit-down close cannot be sold, and shares bought today are sellable "
            "from the next trading day."
        ),
        "annual_return_pct": _finite(annual_return * 100),
        "benchmark_annual_return_pct": _finite(benchmark_annual_return * 100),
        "max_drawdown_pct": _finite(drawdown.min() * 100),
        "sharpe": _finite(sharpe),
        "exposure_pct": _finite(position.mean() * 100),
        "positive_active_day_pct": _finite((active > 0).mean() * 100) if not active.empty else None,
        "completed_trades": completed_trades,
        "execution_constraints": {
            "price_limits_modeled": True,
            "t_plus_one_modeled": True,
            "minimum_holding_trading_days": 1,
            "blocked_limit_up_buys": blocked_limit_up_buys,
            "blocked_limit_down_sells": blocked_limit_down_sells,
            "blocked_t1_sells": blocked_t1_sells,
        },
        "limitations": [
            "Exploratory single-asset backtest, not walk-forward parameter validation.",
            "Fees, slippage, and suspension are intentionally not modeled.",
        ],
    }


def build_quant_signal(
    history: pd.DataFrame,
    *,
    symbol: str = "",
    name: str = "",
) -> dict[str, Any]:
    if history is None or history.empty:
        return {"status": "unavailable", "reason": "empty_history"}

    close = _series(history, "close", "收盘")
    if close is None:
        return {"status": "unavailable", "reason": "close_column_missing"}
    close = close.dropna()
    if len(close) < MIN_SIGNAL_ROWS:
        return {
            "status": "unavailable",
            "reason": "insufficient_history",
            "sample_days": int(len(close)),
            "minimum_days": MIN_SIGNAL_ROWS,
        }

    volume = _series(history, "volume", "成交量")
    if volume is not None:
        volume = volume.reindex(close.index)
    high = _series(history, "high", "最高")
    low = _series(history, "low", "最低")

    frame = _score_frame(close, volume)
    limit_flags = _limit_flags(history, close, symbol=symbol, name=name)
    latest = frame.iloc[-1]
    current_price = float(close.iloc[-1])
    ma20 = float(latest["ma20"])
    ma60 = float(latest["ma60"])
    score = float(latest["raw_score"])
    volatility_pct = float(latest["volatility_20d"] * 100)
    action = _action(score, current_price, ma20, ma60)

    atr_value = None
    if high is not None and low is not None:
        aligned = pd.concat(
            [high.reindex(close.index), low.reindex(close.index), close],
            axis=1,
        ).dropna()
        if len(aligned) >= 20:
            atr_value = float(_atr(aligned.iloc[:, 0], aligned.iloc[:, 1], aligned.iloc[:, 2]).iloc[-1])
            if not math.isfinite(atr_value):
                atr_value = None
    if atr_value is None:
        atr_value = current_price * max(volatility_pct / 100 / math.sqrt(252), 0.015)

    recent_low = float(close.tail(20).min())
    stop_price = max(0.01, min(current_price - 2 * atr_value, recent_low * 0.995))
    risk_per_share = max(current_price - stop_price, current_price * 0.01)
    target_price = current_price + 2 * risk_per_share
    risk_pct = risk_per_share / current_price * 100
    confidence = int(round(_clip(50 + abs(score) * 0.45 - max(volatility_pct - 35, 0) * 0.5, 5, 90)))
    max_position_pct = _clip(0.75 / max(risk_pct / 100, 0.01), 5, 25)
    if action in {"risk_off", "avoid_or_reduce"}:
        max_position_pct = 0

    factor_scores = {
        "trend": _finite(latest["trend_score"]),
        "momentum": _finite(latest["momentum_score"]),
        "volume_confirmation": _finite(latest["volume_score"]),
    }
    return {
        "status": "available",
        "model": "multi_factor_trend_momentum_v1",
        "sample_days": int(len(close)),
        "score": _finite(score),
        "action": action,
        "confidence": confidence,
        "factor_scores": factor_scores,
        "metrics": {
            "return_5d_pct": _finite(_pct_return(close, 5)),
            "return_20d_pct": _finite(_pct_return(close, 20)),
            "return_60d_pct": _finite(_pct_return(close, 60)),
            "annualized_volatility_20d_pct": _finite(volatility_pct),
            "atr14": _finite(atr_value),
            "atr14_pct": _finite(atr_value / current_price * 100),
            "max_drawdown_60d_pct": _finite(_max_drawdown(close)),
        },
        "trade_plan": {
            "reference_price": _finite(current_price),
            "entry_zone": [_finite(current_price - 0.5 * atr_value), _finite(current_price + 0.25 * atr_value)],
            "stop_price": _finite(stop_price),
            "target_price_2r": _finite(target_price),
            "risk_per_share_pct": _finite(risk_pct),
            "minimum_reward_risk": 2.0,
            "suggested_max_position_pct": _finite(max_position_pct),
            "position_sizing_rule": "Risk at most 0.75% of account equity at the model stop.",
        },
        "backtest": _backtest(frame, limit_flags),
        "constraints": [
            "Quant output is a rules-based decision aid, not an execution instruction.",
            "Do not override stale or missing market data, portfolio limits, or user invalidation rules.",
        ],
    }
