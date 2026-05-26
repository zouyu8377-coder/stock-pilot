from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import requests

from app.core.config import settings


YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

FACTOR_CONFIG: dict[str, dict[str, str]] = {
    "comex_copper_yahoo": {
        "display_name": "COMEX Copper Futures Reference",
        "yahoo_symbol": "HG=F",
        "product": "Copper",
        "market": "COMEX",
        "currency": "USD",
    },
    "comex_gold_yahoo": {
        "display_name": "COMEX Gold Futures Reference",
        "yahoo_symbol": "GC=F",
        "product": "Gold",
        "market": "COMEX",
        "currency": "USD",
    },
    "comex_silver_yahoo": {
        "display_name": "COMEX Silver Futures Reference",
        "yahoo_symbol": "SI=F",
        "product": "Silver",
        "market": "COMEX",
        "currency": "USD",
    },
}


class YahooComexError(Exception):
    pass


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
        if pd.isna(v):
            return None
        return round(v, 4)
    except (TypeError, ValueError):
        return None


def _parse_yahoo_chart(result: dict[str, Any]) -> pd.DataFrame:
    """Parse Yahoo Finance v8 chart result into a DataFrame with trade_date, open, high, low, close."""
    meta = result.get("chart", {}).get("result", [{}])[0]
    if not meta:
        raise YahooComexError("Empty chart result")

    timestamps = meta.get("timestamp", [])
    indicators = meta.get("indicators", {}).get("quote", [{}])[0]
    if not timestamps:
        raise YahooComexError("No timestamps in chart result")

    opens = indicators.get("open", [])
    highs = indicators.get("high", [])
    lows = indicators.get("low", [])
    closes = indicators.get("close", [])
    volumes = indicators.get("volume", [])

    rows = []
    for i, ts in enumerate(timestamps):
        if ts is None:
            continue
        dt = datetime.fromtimestamp(ts)
        close = _safe_float(closes[i]) if i < len(closes) else None
        if close is None:
            continue
        rows.append({
            "trade_date": dt.strftime("%Y%m%d"),
            "open": _safe_float(opens[i]) if i < len(opens) else None,
            "high": _safe_float(highs[i]) if i < len(highs) else None,
            "low": _safe_float(lows[i]) if i < len(lows) else None,
            "close": close,
            "volume": _safe_float(volumes[i]) if i < len(volumes) else None,
        })

    if not rows:
        raise YahooComexError("No valid price rows after parsing")

    df = pd.DataFrame(rows)
    df = df.sort_values("trade_date", ascending=False).reset_index(drop=True)
    return df


def _latest_meta(result: dict[str, Any]) -> dict[str, Any]:
    meta = result.get("chart", {}).get("result", [{}])[0].get("meta", {})
    return {
        "currency": meta.get("currency"),
        "exchange_name": meta.get("exchangeName"),
        "instrument_type": meta.get("instrumentType"),
        "regular_market_price": _safe_float(meta.get("regularMarketPrice")),
        "previous_close": _safe_float(meta.get("previousClose")),
        "regular_market_time": meta.get("regularMarketTime"),
    }


def fetch_yahoo_comex_series(
    factor_id: str,
    range_days: str = "30d",
    interval: str = "1d",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    config = FACTOR_CONFIG.get(factor_id)
    if not config:
        raise YahooComexError(f"Unknown COMEX factor: {factor_id}")

    yahoo_symbol = config["yahoo_symbol"]
    url = YAHOO_CHART_URL.format(symbol=yahoo_symbol)
    params = {"interval": interval, "range": range_days}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
    except requests.RequestException as exc:
        raise YahooComexError(f"Yahoo request failed: {exc}") from exc

    if resp.status_code != 200:
        raise YahooComexError(f"Yahoo returned HTTP {resp.status_code}")

    try:
        data = resp.json()
    except json.JSONDecodeError as exc:
        raise YahooComexError(f"Yahoo response is not valid JSON: {exc}") from exc

    error_info = data.get("chart", {}).get("error")
    if error_info:
        raise YahooComexError(f"Yahoo chart error: {error_info}")

    df = _parse_yahoo_chart(data)
    meta = _latest_meta(data)
    meta.update({
        "yahoo_symbol": yahoo_symbol,
        "factor_id": factor_id,
        "provider": "yahoo_finance",
        "provider_endpoint": "v8/finance/chart",
        "retrieved_at": datetime.utcnow().isoformat(),
        "quote_delay_status": "delayed_or_unverified",
        "source_note": (
            "Yahoo Finance COMEX delayed quote reference; programmatic access is best-effort "
            "and may change. Not official CME settlement data."
        ),
    })
    return df, meta


def get_comex_fact(
    factor_id: str,
    range_days: str = "30d",
    include_series: bool = False,
) -> dict[str, Any]:
    """Return a standardized COMEX external driver fact dict."""
    try:
        df, meta = fetch_yahoo_comex_series(factor_id, range_days=range_days)
    except YahooComexError as exc:
        return {
            "factor_id": factor_id,
            "data_status": "unavailable",
            "reason": str(exc),
            "provider": "yahoo_finance",
            "quote_delay_status": "delayed_or_unverified",
        }

    if df.empty:
        return {
            "factor_id": factor_id,
            "data_status": "unavailable",
            "reason": "Parsed DataFrame is empty.",
            "provider": "yahoo_finance",
            "quote_delay_status": "delayed_or_unverified",
        }

    latest = df.iloc[0].to_dict()
    prev = df.iloc[1].to_dict() if len(df) > 1 else {}
    prev_close = _safe_float(prev.get("close")) if prev else None
    close = _safe_float(latest.get("close"))
    change = None
    change_pct = None
    if close is not None and prev_close is not None and prev_close != 0:
        change = round(close - prev_close, 4)
        change_pct = round((close / prev_close - 1) * 100, 4)

    def _change_n(offset: int) -> float | None:
        if len(df) <= offset:
            return None
        curr = _safe_float(df.iloc[0].get("close"))
        past = _safe_float(df.iloc[offset].get("close"))
        if curr is None or past is None or past == 0:
            return None
        return round((curr / past - 1) * 100, 4)

    result = {
        "factor_id": factor_id,
        "display_name": FACTOR_CONFIG[factor_id]["display_name"],
        "provider": "yahoo_finance",
        "market": "COMEX",
        "yahoo_symbol": meta["yahoo_symbol"],
        "currency": meta.get("currency") or "USD",
        "quote_type": "delayed_reference",
        "quote_delay_status": "delayed_or_unverified",
        "data_status": "available",
        "trade_date": latest.get("trade_date"),
        "close": close,
        "open": _safe_float(latest.get("open")),
        "high": _safe_float(latest.get("high")),
        "low": _safe_float(latest.get("low")),
        "volume": _safe_float(latest.get("volume")),
        "previous_close": prev_close,
        "change": change,
        "change_pct": change_pct,
        "returns_pct": {
            "1d": change_pct,
            "5d": _change_n(4),
            "20d": _change_n(19),
        },
        "provider_retrieved_at": meta["retrieved_at"],
        "provider_market_time": meta.get("regular_market_time"),
        "contract_display_name": None,
        "source_endpoint_or_method": "v8/finance/chart",
        "interpretation_limit": (
            "Yahoo Finance COMEX delayed reference only; not official CME settlement, "
            "not realtime, not a causal conclusion, and not trading advice. "
            "Does not replace domestic futures prices."
        ),
        "meta": {k: v for k, v in meta.items() if k not in {"series"}},
    }
    if include_series:
        result["series"] = df.head(30).to_dict("records")
    return result
