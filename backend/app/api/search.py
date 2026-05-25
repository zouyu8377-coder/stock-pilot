from fastapi import APIRouter, Query

from app.collector.router import collector
from app.collector.metadata_provider import metadata_provider
from app.facts.common import compact_symbol

router = APIRouter()


@router.get("/stocks/search")
def search_stocks(
    q: str = Query(default="", max_length=40),
    limit: int = Query(default=20, ge=1, le=50),
):
    return {
        "items": metadata_provider.search(q, limit),
    }


@router.get("/stocks/{symbol}/quote")
def get_stock_quote(symbol: str):
    code = compact_symbol(symbol)
    meta = metadata_provider.get(code) or {}
    quote_status = "ready"
    quote_error = None
    quote = {}
    try:
        quote = collector.get_quote(code)
    except Exception as exc:
        quote_status = "unavailable"
        quote_error = str(exc)[:200]

    return {
        "success": True,
        "data": {
            "symbol": code,
            "name": quote.get("name") or meta.get("name") or code,
            "price": quote.get("price"),
            "change_pct": quote.get("change_pct"),
            "volume": quote.get("volume"),
            "provider": quote.get("provider"),
            "quote_status": quote_status,
            "quote_error": quote_error,
            "industry": meta.get("industry"),
            "area": meta.get("area"),
            "list_date": meta.get("list_date"),
            "asset_type": meta.get("asset_type"),
            "fund_type": meta.get("fund_type"),
            "management": meta.get("management"),
        },
    }
