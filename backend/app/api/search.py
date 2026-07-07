from fastapi import APIRouter, Query

from app.collector.router import collector
from app.collector.metadata_provider import metadata_provider
from app.facts.common import compact_symbol
from app.portfolio.ipo_registry import get_ipo_entry, search_ipo_entries

router = APIRouter()


@router.get("/stocks/search")
def search_stocks(
    q: str = Query(default="", max_length=40),
    limit: int = Query(default=20, ge=1, le=50),
):
    ipo_items = search_ipo_entries(q, limit)
    seen = {item["symbol"] for item in ipo_items}
    metadata_items = [
        item
        for item in metadata_provider.search(q, limit)
        if item.get("symbol") not in seen
    ]
    return {
        "items": [*ipo_items, *metadata_items][:limit],
    }


@router.get("/stocks/{symbol}/quote")
def get_stock_quote(symbol: str):
    code = compact_symbol(symbol)
    ipo = get_ipo_entry(code)
    meta = metadata_provider.get(code) or {}
    quote_status = "ready"
    quote_error = None
    quote = {}
    try:
        quote = collector.get_quote(code)
    except Exception as exc:
        quote_status = "ipo_subscription" if ipo else "unavailable"
        quote_error = str(exc)[:200]

    return {
        "success": True,
        "data": {
            "symbol": code,
            "name": quote.get("name") or (ipo or {}).get("name") or meta.get("name") or code,
            "price": quote.get("price") or (ipo or {}).get("issue_price"),
            "change_pct": quote.get("change_pct"),
            "volume": quote.get("volume"),
            "provider": quote.get("provider") or ((ipo or {}).get("asset_type") if ipo else None),
            "quote_status": quote_status,
            "quote_error": quote_error,
            "industry": meta.get("industry") or (ipo or {}).get("industry"),
            "area": meta.get("area") or (ipo or {}).get("area"),
            "list_date": meta.get("list_date") or (ipo or {}).get("list_date"),
            "asset_type": meta.get("asset_type") or (ipo or {}).get("asset_type"),
            "ipo_status": (ipo or {}).get("ipo_status"),
            "issue_price": (ipo or {}).get("issue_price"),
            "fund_type": meta.get("fund_type"),
            "management": meta.get("management"),
        },
    }
