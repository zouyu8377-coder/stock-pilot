from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.agent_context import (
    build_daily_review_context,
    build_portfolio_agent_context,
    build_rotation_agent_context,
    build_stock_agent_context,
    render_agent_context_markdown,
)

router = APIRouter(prefix="/agent/context", tags=["agent-context"])


@router.get("/daily-review")
def daily_review_context(force: bool = Query(False)):
    return {"success": True, "data": build_daily_review_context(force=force)}


@router.get("/daily-review/markdown", response_class=PlainTextResponse)
def daily_review_markdown(force: bool = Query(False)):
    return render_agent_context_markdown(build_daily_review_context(force=force))


@router.get("/portfolio")
def portfolio_context(force: bool = Query(False)):
    return {"success": True, "data": build_portfolio_agent_context(force=force)}


@router.get("/portfolio/markdown", response_class=PlainTextResponse)
def portfolio_markdown(force: bool = Query(False)):
    return render_agent_context_markdown(build_portfolio_agent_context(force=force))


@router.get("/rotation")
def rotation_context(force: bool = Query(False)):
    return {"success": True, "data": build_rotation_agent_context(force=force)}


@router.get("/rotation/markdown", response_class=PlainTextResponse)
def rotation_markdown(force: bool = Query(False)):
    return render_agent_context_markdown(build_rotation_agent_context(force=force))


@router.get("/stock/{symbol}")
def stock_context(symbol: str, user_question: str | None = Query(default=None)):
    try:
        return {
            "success": True,
            "data": build_stock_agent_context(symbol, user_question=user_question),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent stock context failed: {str(exc)}") from exc


@router.get("/stock/{symbol}/markdown", response_class=PlainTextResponse)
def stock_markdown(symbol: str, user_question: str | None = Query(default=None)):
    try:
        context = build_stock_agent_context(symbol, user_question=user_question)
        return render_agent_context_markdown(context)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent stock context failed: {str(exc)}") from exc
