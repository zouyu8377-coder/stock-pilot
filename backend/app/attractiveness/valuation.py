from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from app.collector.realtime.easyquotation_provider import EasyQuotationProvider
from app.facts.common import safe_float
from app.services.etf_share_service import etf_share_service


DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
BASE_MARKET_ROOT = DATA_ROOT / "base_market"


def _percentile(series: pd.Series, value: float | None) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if value is None or clean.empty:
        return None
    return round(float((clean <= value).mean() * 100), 2)


def _compact(symbol: str) -> str:
    return str(symbol or "").split(".", 1)[0].strip().zfill(6)


def _market_path(symbol: str) -> Path:
    code = _compact(symbol)
    exchange = "sh" if code.startswith(("5", "6")) else "sz"
    return BASE_MARKET_ROOT / f"{exchange}.{code}.parquet"


def _is_etf(symbol: str) -> bool:
    return _compact(symbol).startswith(("15", "16", "51", "56", "58"))


@lru_cache(maxsize=512)
def _local_price_reference(path: Path, modified_ns: int) -> dict[str, Any]:
    del modified_ns
    try:
        frame = pd.read_parquet(path, columns=["date", "close"])
    except Exception as exc:
        return {"status": "unavailable", "reason": f"Local price history unavailable: {exc}"}
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna().sort_values("date").tail(756)
    if len(frame) < 60:
        return {"status": "unavailable", "reason": "Insufficient local price history."}
    latest = frame.iloc[-1]
    close = float(latest["close"])
    return {
        "status": "available",
        "as_of": str(latest["date"])[:10],
        "price": close,
        "price_percentile_3y": _percentile(frame["close"], close),
        "price_drawdown_from_3y_high_pct": round((close / float(frame["close"].max()) - 1) * 100, 2),
        "sample_days": int(len(frame)),
        "source": "local_baostock_daily",
    }


@lru_cache(maxsize=512)
def _realtime_multiples(symbol: str) -> dict[str, Any]:
    if _is_etf(symbol):
        return {}
    try:
        quote = EasyQuotationProvider().get_quote(_compact(symbol))
    except Exception:
        return {}
    return {
        "pe_ttm": safe_float(quote.get("pe")),
        "pb": safe_float(quote.get("pb")),
        "quote_source": quote.get("provider"),
    }


def get_valuation_reference(symbol: str, *, force: bool = False) -> dict[str, Any]:
    del force
    path = _market_path(symbol)
    try:
        modified_ns = path.stat().st_mtime_ns
    except OSError:
        return {"status": "unavailable", "reason": "Local price history is missing."}
    reference = _local_price_reference(path, modified_ns)
    if reference.get("status") != "available":
        return reference

    code = _compact(symbol)
    if _is_etf(code):
        share = etf_share_service.observation_for_code(code)
        reference.update({
            "asset_type": "etf",
            "share_change_1d_pct": (
                round(float(share["share_chg_1d"]) * 100, 2)
                if share.get("share_chg_1d") is not None else None
            ),
            "share_change_5d_pct": (
                round(float(share["share_chg_5d"]) * 100, 2)
                if share.get("share_chg_5d") is not None else None
            ),
            "share_change_20d_pct": (
                round(float(share["share_chg_20d"]) * 100, 2)
                if share.get("share_chg_20d") is not None else None
            ),
            "share_data_as_of": share.get("latest_trade_date"),
            "interpretation": "ETF使用自身三年价格位置和份额变化，不等同于上市公司PE/PB估值。",
        })
        return reference

    reference.update({
        "asset_type": "stock",
        **_realtime_multiples(code),
        "interpretation": "当前PE/PB仅作截面参考；核心可比口径为自身三年价格位置。",
    })
    return reference
