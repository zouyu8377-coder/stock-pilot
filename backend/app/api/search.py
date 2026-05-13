from fastapi import APIRouter, Query

from app.collector.metadata_provider import metadata_provider

router = APIRouter()


@router.get("/stocks/search")
def search_stocks(
    q: str = Query(default="", max_length=40),
    limit: int = Query(default=20, ge=1, le=50),
):
    return {
        "items": metadata_provider.search(q, limit),
    }
