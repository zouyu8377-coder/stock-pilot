import asyncio
import os
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query

from app.ai.prompt_builder import build_human_prompt
from app.ai.analyzer import analyze_stock
from app.ai.research_engine import generate_research_report, _build_fallback
from app.analysis.data_coverage import build_data_coverage
from app.analysis.indicators import compute_indicators
from app.cache.manager import cache
from app.collector.metadata_provider import metadata_provider
from app.collector.router import collector
from app.company_profile.profile_engine import build_company_profile
from app.strategy.model_selector import select_models
from app.strategy.regime_engine import detect_market_regime

router = APIRouter()
DEEP_ANALYZE_TIMEOUT_SECONDS = float(os.getenv("DEEP_ANALYZE_TIMEOUT_SECONDS", "180"))
DEEP_ANALYZE_CACHE_MINUTES = int(os.getenv("DEEP_ANALYZE_CACHE_MINUTES", "30"))
_analysis_locks: dict[str, asyncio.Lock] = {}


def _build_stock_data(symbol: str) -> dict:
    quote = cache.get_hot(symbol)
    if quote is None:
        quote = collector.get_quote(symbol)
        cache.set_hot(symbol, quote)

    history = collector.get_history(symbol)
    cache.write_history(symbol, history)

    indicators, _ma_series = compute_indicators(history)

    meta = metadata_provider.get(symbol)
    industry = meta["industry"] if meta else None

    company_profile = build_company_profile(symbol)

    stock_data = {
        "name": quote.get("name"),
        "symbol": symbol,
        "price": quote.get("price"),
        "change_pct": quote.get("change_pct"),
        "industry": industry,
        "indicators": indicators,
        "analysis": {},
        "company_profile": company_profile,
    }
    stock_data["analysis"] = analyze_stock(stock_data)

    strategy_context = detect_market_regime(stock_data, company_profile)
    select_models(strategy_context)
    stock_data["strategy_context"] = strategy_context
    stock_data["data_coverage"] = build_data_coverage(company_profile, history, stock_data)

    return stock_data


@router.get("/deep-analyze/{symbol}")
async def deep_analyze(symbol: str, force: bool = Query(False)):
    try:
        if not force:
            cached = cache.read_deep_analysis(symbol, timedelta(minutes=DEEP_ANALYZE_CACHE_MINUTES))
            if cached and not cached.get("is_fallback"):
                cached["cache_hit"] = True
                return {
                    "success": True,
                    "data": cached,
                }

        lock = _analysis_locks.setdefault(symbol, asyncio.Lock())
        async with lock:
            if not force:
                cached = cache.read_deep_analysis(symbol, timedelta(minutes=DEEP_ANALYZE_CACHE_MINUTES))
                if cached and not cached.get("is_fallback"):
                    cached["cache_hit"] = True
                    return {
                        "success": True,
                        "data": cached,
                    }

            result = await _run_deep_analysis(symbol)
            if not result.get("is_fallback"):
                cache.write_deep_analysis(symbol, result)

        return {
            "success": True,
            "data": result,
        }

    except Exception as e:
        print(f"Deep analyze failed: {e}")
        raise HTTPException(status_code=502, detail=f"Deep analysis failed: {str(e)}") from e


async def _run_deep_analysis(symbol: str) -> dict:
    stock_data = _build_stock_data(symbol)

    loop = asyncio.get_running_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(None, generate_research_report, stock_data),
            timeout=DEEP_ANALYZE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        result = _build_fallback(
            f"AI analysis timed out after {DEEP_ANALYZE_TIMEOUT_SECONDS:.0f}s",
            stock_data,
        )
    return result


@router.get("/deep-analyze-prompt/{symbol}")
async def deep_analyze_prompt(symbol: str):
    try:
        stock_data = _build_stock_data(symbol)
        prompt = build_human_prompt(stock_data)

        return {
            "success": True,
            "prompt": prompt,
        }

    except Exception as e:
        print(f"Deep analyze prompt failed: {e}")
        raise HTTPException(status_code=502, detail=f"Prompt data build failed: {str(e)}") from e
