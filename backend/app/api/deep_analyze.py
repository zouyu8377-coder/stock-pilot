from fastapi import APIRouter, HTTPException
import asyncio

from app.collector.router import collector
from app.collector.metadata_provider import metadata_provider
from app.analysis.indicators import compute_indicators
from app.cache.manager import cache
from app.ai.research_engine import generate_research_report
from app.company_profile.profile_engine import build_company_profile

router = APIRouter()


@router.get("/deep-analyze/{symbol}")
async def deep_analyze(symbol: str):
    try:
        quote = cache.get_hot(symbol)
        if quote is None:
            quote = collector.get_quote(symbol)
            cache.set_hot(symbol, quote)

        history = cache.read_history(symbol)
        if history is None:
            history = collector.get_history(symbol)
            cache.write_history(symbol, history)

        indicators, _ = compute_indicators(history)

        meta = metadata_provider.get(symbol)
        industry = meta["industry"] if meta else None

        # 获取公司画像（带缓存）
        company_profile = build_company_profile(symbol)

        stock_data = {
            "name": quote.get("name"),
            "symbol": symbol,
            "price": quote.get("price"),
            "change_pct": quote.get("change_pct"),
            "industry": industry,
            "indicators": indicators,
            "analysis": None,
            "company_profile": company_profile,
        }

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, generate_research_report, stock_data)

        return {
            "success": True,
            "data": result,
        }

    except Exception as e:
        print(f"Deep analyze failed: {e}")
        return {
            "success": False,
            "message": f"AI分析超时: {str(e)}",
        }