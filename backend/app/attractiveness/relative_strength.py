from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd


DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
BASE_MARKET_ROOT = DATA_ROOT / "base_market"
METADATA_PATH = DATA_ROOT / "metadata" / "stock_meta.parquet"
MARKET_BENCHMARK_PATH = BASE_MARKET_ROOT / "sh.000300.parquet"


def _compact(symbol: str) -> str:
    return str(symbol or "").split(".", 1)[0].strip().zfill(6)


def _market_path(symbol: str) -> Path:
    code = _compact(symbol)
    prefix = "sh" if code.startswith(("5", "6")) else "sz"
    return BASE_MARKET_ROOT / f"{prefix}.{code}.parquet"


@lru_cache(maxsize=2048)
def _returns_cached(path: Path, modified_ns: int) -> dict[str, Any] | None:
    try:
        frame = pd.read_parquet(path, columns=["date", "close"])
        closes = pd.to_numeric(frame["close"], errors="coerce").dropna()
        dates = pd.to_datetime(frame["date"], errors="coerce")
    except Exception:
        return None
    if len(closes) < 61:
        return None
    return {
        "as_of": str(dates.iloc[-1])[:10],
        "return_20d_pct": round((closes.iloc[-1] / closes.iloc[-21] - 1) * 100, 2),
        "return_60d_pct": round((closes.iloc[-1] / closes.iloc[-61] - 1) * 100, 2),
    }


def _returns(path: Path) -> dict[str, Any] | None:
    try:
        modified_ns = path.stat().st_mtime_ns
    except OSError:
        return None
    return _returns_cached(path, modified_ns)


def _expected_market_date(today: date | None = None) -> date:
    value = today or date.today()
    value -= timedelta(days=1)
    while value.weekday() >= 5:
        value -= timedelta(days=1)
    return value


def _freshness(as_of: str | None) -> dict[str, Any]:
    try:
        parsed = date.fromisoformat(str(as_of))
    except (TypeError, ValueError):
        return {"status": "unavailable", "stale_days": None}
    stale_days = (_expected_market_date() - parsed).days
    return {
        "status": "fresh" if stale_days <= 3 else "stale",
        "stale_days": max(0, stale_days),
        "expected_as_of": _expected_market_date().isoformat(),
    }


@lru_cache(maxsize=1)
def _metadata() -> pd.DataFrame:
    try:
        return pd.read_parquet(METADATA_PATH, columns=["symbol", "industry"])
    except Exception:
        return pd.DataFrame(columns=["symbol", "industry"])


def _median_benchmark(symbols: list[str]) -> dict[str, Any]:
    rows = [item for item in (_returns(_market_path(symbol)) for symbol in symbols) if item]
    if not rows:
        return {"status": "unavailable", "sample_size": 0}
    latest_date = max(item["as_of"] for item in rows)
    aligned = [item for item in rows if item["as_of"] == latest_date]
    return {
        "status": "available",
        "as_of": latest_date,
        "return_20d_pct": round(float(pd.Series([item["return_20d_pct"] for item in aligned]).median()), 2),
        "return_60d_pct": round(float(pd.Series([item["return_60d_pct"] for item in aligned]).median()), 2),
        "sample_size": len(aligned),
        "freshness": _freshness(latest_date),
    }


def build_relative_benchmarks(
    symbol: str,
    theme_position: dict[str, Any],
    theme_radar: dict[str, Any],
) -> dict[str, Any]:
    code = _compact(symbol)
    market = _returns(MARKET_BENCHMARK_PATH) or {}
    market = {
        "status": "available" if market else "unavailable",
        **market,
        "freshness": _freshness(market.get("as_of")),
        "label": "沪深300",
    }

    meta = _metadata()
    match = meta[meta["symbol"].astype(str).str.zfill(6) == code]
    industry_name = str(match.iloc[0]["industry"]) if not match.empty else ""
    peers = (
        meta[meta["industry"] == industry_name]["symbol"].astype(str).str.zfill(6).tolist()
        if industry_name
        else []
    )
    peers = [item for item in peers if item != code][0:30]
    industry = {
        **_median_benchmark(peers),
        "label": industry_name or "行业",
        "peer_symbols": peers,
    }

    theme_id = theme_position.get("theme_id")
    theme_symbols: list[str] = []
    for theme in theme_radar.get("themes", []):
        if theme.get("theme_id") != theme_id:
            continue
        theme_symbols = [
            _compact(item.get("symbol", ""))
            for item in theme.get("related_positions", [])
            if _compact(item.get("symbol", "")) != code
        ]
        break
    theme = {
        **_median_benchmark(theme_symbols),
        "label": theme_position.get("theme_name") or "相关主题",
        "peer_symbols": theme_symbols,
    }
    return {"market": market, "industry": industry, "theme": theme}
