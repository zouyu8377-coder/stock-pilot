import asyncio

from fastapi import APIRouter, HTTPException

from app.ai.prompt_builder import build_human_prompt
from app.ai.research_engine import generate_research_report
from app.analysis.indicators import compute_indicators
from app.cache.manager import cache
from app.collector.metadata_provider import metadata_provider
from app.collector.router import collector
from app.company_profile.profile_engine import build_company_profile
from app.strategy.model_selector import select_models
from app.strategy.regime_engine import detect_market_regime

router = APIRouter()


def _build_stock_data(symbol: str) -> dict:
    quote = cache.get_hot(symbol)
    if quote is None:
        quote = collector.get_quote(symbol)
        cache.set_hot(symbol, quote)

    history = collector.get_history(symbol)
    cache.write_history(symbol, history)

    indicators, analysis = compute_indicators(history)

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
        "analysis": analysis,
        "company_profile": company_profile,
    }

    strategy_context = detect_market_regime(stock_data, company_profile)
    select_models(strategy_context)
    stock_data["strategy_context"] = strategy_context

    return stock_data


@router.get("/deep-analyze/{symbol}")
async def deep_analyze(symbol: str):
    try:
        stock_data = _build_stock_data(symbol)

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, generate_research_report, stock_data)

        return {
            "success": True,
            "data": result,
        }

    except Exception as e:
        print(f"Deep analyze failed: {e}")
        raise HTTPException(status_code=502, detail=f"Deep analysis failed: {str(e)}") from e


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
