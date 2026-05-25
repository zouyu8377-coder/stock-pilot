from fastapi import APIRouter, HTTPException, Query

from app.analysis_packet.snapshot_builder import build_basic_stock_snapshot

router = APIRouter()


@router.get("/analysis-snapshot/{symbol}")
def analysis_snapshot(symbol: str, user_question: str | None = Query(default=None)):
    try:
        snapshot = build_basic_stock_snapshot(symbol, user_question=user_question)
        return {
            "success": True,
            "data": snapshot.model_dump(mode="json"),
        }
    except Exception as e:
        print(f"Analysis snapshot failed: {e}")
        raise HTTPException(status_code=502, detail=f"Analysis snapshot failed: {str(e)}") from e
