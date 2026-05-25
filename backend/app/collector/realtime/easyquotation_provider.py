import easyquotation
import pandas as pd

from app.collector.history.base_market_provider import BaseMarketProvider
from app.collector.metadata_provider import metadata_provider


def _pick(data: dict, *keys: str):
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


class EasyQuotationProvider:
    """Tencent realtime quote provider via easyquotation."""

    def __init__(self):
        self.client = easyquotation.use("tencent")

    def get_quote(self, symbol: str):
        data = self.client.real(symbol)
        if not data:
            raise ValueError("easyquotation returned empty data")
        if symbol not in data:
            raise ValueError(f"Quote not found: {symbol}")

        q = data[symbol]
        return {
            "symbol": symbol,
            "price": q.get("now"),
            "change_pct": _pick(q, "涨跌(%)", "change_pct"),
            "name": q.get("name"),
            "volume": q.get("volume"),
            "provider": "easyquotation",
            "hot_status": "ready",
            "market_cap": _pick(q, "总市值", "市值"),
            "float_market_cap": _pick(q, "流通市值"),
            "pe": _pick(q, "PE", "市盈率"),
            "pb": _pick(q, "PB", "市净率"),
            "turnover_rate": _pick(q, "turnover", "换手率", "换手"),
            "volume_ratio": _pick(q, "量比"),
        }


class LocalColdQuoteProvider:
    """Fallback quote from the latest local BaoStock daily bar."""

    def __init__(self):
        self.history_provider = BaseMarketProvider()

    def get_quote(self, symbol: str):
        history = self.history_provider.get_daily_history(symbol, limit=2)
        if history is None or history.empty:
            raise ValueError(f"Local history not found: {symbol}")

        frame = history.copy()
        frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
        if "volume" in frame.columns:
            frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")
        latest = frame.iloc[-1]
        previous = frame.iloc[-2] if len(frame) >= 2 else None
        price = float(latest["close"])
        change_pct = None
        if previous is not None and float(previous["close"]):
            change_pct = round((price / float(previous["close"]) - 1) * 100, 2)

        meta = metadata_provider.get(symbol) or {}
        volume = latest.get("volume") if "volume" in frame.columns else None
        return {
            "symbol": symbol,
            "price": price,
            "change_pct": change_pct,
            "name": meta.get("name") or symbol,
            "volume": None if volume is None or pd.isna(volume) else float(volume),
            "provider": "local_baostock_daily",
            "hot_status": "stale",
        }
