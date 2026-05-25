from fastapi import APIRouter, HTTPException, Query

from app.analysis_packet import build_portfolio_packet, build_single_stock_packet

router = APIRouter()


@router.post("/analysis-packet/single/{symbol}")
def create_single_stock_packet(symbol: str, user_question: str | None = Query(default=None)):
    try:
        return {
            "success": True,
            **build_single_stock_packet(symbol, user_question=user_question),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Analysis packet failed: {str(exc)}") from exc


@router.post("/analysis-packet/portfolio")
def create_portfolio_packet(user_question: str | None = Query(default=None)):
    try:
        return {
            "success": True,
            **build_portfolio_packet(user_question=user_question),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Portfolio analysis packet failed: {str(exc)}") from exc
