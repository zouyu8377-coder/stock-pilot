from fastapi import APIRouter, Query

from app.facts import get_disclosure_facts, get_dragon_tiger_facts, get_etf_facts

router = APIRouter()


@router.get("/facts/etf/{symbol}")
def etf_facts(symbol: str, force: bool = Query(False)):
    return get_etf_facts(symbol, force=force)


@router.get("/facts/dragon-tiger/{symbol}")
def dragon_tiger_facts(symbol: str, force: bool = Query(False)):
    return get_dragon_tiger_facts(symbol, force=force)


@router.get("/facts/disclosures/{symbol}")
def disclosure_facts(symbol: str, force: bool = Query(False)):
    return get_disclosure_facts(symbol, force=force)
