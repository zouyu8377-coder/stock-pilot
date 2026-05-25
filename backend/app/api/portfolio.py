from fastapi import APIRouter, HTTPException

from app.portfolio import portfolio_service
from app.portfolio.schemas import (
    ManualEvidenceCreate,
    ManualEvidenceIncludeUpdate,
    PortfolioSnapshotInput,
    TradeSimulationRequest,
)

router = APIRouter()


@router.get("/portfolio")
def get_portfolio():
    return {
        "success": True,
        "data": portfolio_service.get_state().model_dump(mode="json"),
    }


@router.put("/portfolio")
def save_portfolio(payload: PortfolioSnapshotInput):
    return {
        "success": True,
        "data": portfolio_service.save_snapshot(payload).model_dump(mode="json"),
    }


@router.post("/portfolio/simulate")
def simulate_trade(payload: TradeSimulationRequest):
    try:
        result = portfolio_service.simulate_trade(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "success": True,
        "data": result.model_dump(mode="json"),
    }


@router.get("/portfolio/manual-evidence")
def list_manual_evidence():
    return {
        "success": True,
        "items": [item.model_dump(mode="json") for item in portfolio_service.list_manual_evidence()],
    }


@router.post("/portfolio/manual-evidence")
def add_manual_evidence(payload: ManualEvidenceCreate):
    return {
        "success": True,
        "data": portfolio_service.add_manual_evidence(payload).model_dump(mode="json"),
    }


@router.delete("/portfolio/manual-evidence/{evidence_id}")
def delete_manual_evidence(evidence_id: str):
    if not portfolio_service.delete_manual_evidence(evidence_id):
        raise HTTPException(status_code=404, detail="Manual evidence not found")
    return {"success": True}


@router.patch("/portfolio/manual-evidence/{evidence_id}/include")
def update_manual_evidence_include(evidence_id: str, payload: ManualEvidenceIncludeUpdate):
    updated = portfolio_service.update_manual_evidence_include(evidence_id, payload.include_in_analysis_packet)
    if updated is None:
        raise HTTPException(status_code=404, detail="Manual evidence not found")
    return {
        "success": True,
        "data": updated.model_dump(mode="json"),
    }


@router.get("/portfolio/analysis-snapshot")
def portfolio_analysis_snapshot():
    return {
        "success": True,
        "data": portfolio_service.build_portfolio_snapshot().model_dump(mode="json"),
    }
