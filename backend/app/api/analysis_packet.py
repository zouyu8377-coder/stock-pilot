from fastapi import APIRouter, HTTPException, Query

from app.analysis_packet import build_portfolio_packet, build_single_stock_packet
from app.analysis_packet.packet_service import build_account_analysis_context, render_compact_markdown, render_packet_markdown

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
def create_portfolio_packet(
    user_question: str | None = Query(default=None),
    mode: str = Query(default="compact"),
    stale_draft: bool = Query(default=False),
):
    try:
        if mode == "audit":
            result = build_portfolio_packet(user_question=user_question)
            return {"success": True, **result}
        # compact mode (default)
        context = build_account_analysis_context(
            mode="compact",
            snapshot_status_note=(
                "基于已保存快照生成；页面存在未保存修改，未纳入本上下文。"
                if stale_draft else None
            ),
        )
        return {
            "success": True,
            "packet": context,
            "markdown": render_compact_markdown(context),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Portfolio analysis packet failed: {str(exc)}") from exc
