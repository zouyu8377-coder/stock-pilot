from fastapi import APIRouter
from pydantic import BaseModel

from app.collector.router import collector
from app.collector.metadata_provider import metadata_provider
from app.analysis.indicators import compute_indicators
from app.cache.manager import cache
from app.ai.analyzer import analyze_stock

router = APIRouter()


class AnalyzeRequest(BaseModel):
    symbols: list[str]


@router.post("/analyze")
def analyze(req: AnalyzeRequest):
    stocks = []

    for symbol in req.symbols:
        quote = cache.get_hot(symbol)

        if quote is None:
            print(f"HOT CACHE MISS: {symbol}")
            quote = collector.get_quote(symbol)
            cache.set_hot(symbol, quote)
        else:
            print(f"HOT CACHE HIT: {symbol}")

        history = None
        indicators = None
        history_ready = False

        indicators = cache.read_indicators(symbol)
        ma_series = None

        try:
            history = collector.get_history(symbol)
            cache.write_history(symbol, history)
            indicators, ma_series = compute_indicators(history)
            cache.write_indicators(symbol, indicators)
            history_ready = True
        except Exception as e:
            print(f"Cold path failed for {symbol}: {e}")

        result = {
            **quote,
            "cold_status": "ready" if history_ready else "loading",
            "ai_status": "pending",
            "history_ready": history_ready,
            "indicators": indicators,
        }

        # Add metadata
        meta = metadata_provider.get(symbol)
        if meta:
            result["industry"] = meta["industry"]
            result["area"] = meta["area"]
            result["list_date"] = meta["list_date"]

        # Add MA series for chart overlay
        if ma_series:
            result["ma_series"] = ma_series

        try:
            analysis = analyze_stock(result)

            result["analysis"] = analysis
            result["ai_status"] = "ready"

        except Exception as e:
            print(f"AI analysis failed: {e}")

            result["analysis"] = None
            result["ai_status"] = "failed"

        stocks.append(result)

    return {
        "status": "success",
        "stocks": stocks,
    }
