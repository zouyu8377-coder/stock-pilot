from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.portfolio import portfolio_service
from app.analysis_packet.packet_service import build_account_analysis_context
from app.portfolio.import_schemas import PortfolioImportDraftUpdate, PortfolioScreenshotImportOptions
from app.portfolio.import_service import portfolio_import_service, provider_statuses
from app.portfolio.schemas import (
    HoldingSemanticBatchUpdate,
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


@router.get("/portfolio/semantic-suggestions")
def get_portfolio_semantic_suggestions():
    return {
        "success": True,
        "items": [item.model_dump(mode="json") for item in portfolio_service.holding_semantic_suggestions()],
    }


@router.patch("/portfolio/holding-semantics")
def update_portfolio_holding_semantics(payload: HoldingSemanticBatchUpdate):
    return {
        "success": True,
        "data": portfolio_service.update_holding_semantics(payload).model_dump(mode="json"),
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


@router.get("/portfolio/account-analysis-context")
def portfolio_account_analysis_context():
    return {
        "success": True,
        "data": build_account_analysis_context(),
    }


@router.get("/portfolio/import/parser-providers")
def get_portfolio_import_parser_providers():
    return {
        "success": True,
        "data": provider_statuses(),
    }


@router.post("/portfolio/import/screenshot")
async def upload_portfolio_screenshot(
    file: UploadFile = File(...),
    parser_provider: str = Form("local_noop"),
    cloud_send_consent: bool = Form(False),
    user_notice_acknowledged_at: str | None = Form(None),
):
    try:
        content = await file.read()
        draft = portfolio_import_service.create_draft_from_upload(
            filename=file.filename or "portfolio_screenshot",
            content_type=file.content_type or "",
            content=content,
            options=PortfolioScreenshotImportOptions(
                parser_provider=parser_provider,
                cloud_send_consent=cloud_send_consent,
                user_notice_acknowledged_at=user_notice_acknowledged_at,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "success": True,
        "data": draft.model_dump(mode="json"),
    }


@router.get("/portfolio/import/drafts/{draft_id}")
def get_portfolio_import_draft(draft_id: str):
    try:
        draft = portfolio_import_service.get_draft(draft_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Import draft not found") from exc
    return {
        "success": True,
        "data": draft.model_dump(mode="json"),
    }


@router.patch("/portfolio/import/drafts/{draft_id}")
def update_portfolio_import_draft(draft_id: str, payload: PortfolioImportDraftUpdate):
    try:
        draft = portfolio_import_service.update_draft(draft_id, payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Import draft not found") from exc
    return {
        "success": True,
        "data": draft.model_dump(mode="json"),
    }


@router.post("/portfolio/import/drafts/{draft_id}/parse")
def rerun_portfolio_import_parse(draft_id: str):
    try:
        draft = portfolio_import_service.run_ocr_and_parse(draft_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Import draft not found") from exc
    return {
        "success": True,
        "data": draft.model_dump(mode="json"),
    }


@router.post("/portfolio/import/drafts/{draft_id}/confirm")
def confirm_portfolio_import_draft(draft_id: str):
    try:
        result = portfolio_import_service.confirm_draft(draft_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Import draft not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "success": True,
        "data": {
            "draft": result["draft"].model_dump(mode="json"),
            "portfolio": result["state"].model_dump(mode="json"),
        },
    }


@router.delete("/portfolio/import/drafts/{draft_id}")
def reject_portfolio_import_draft(draft_id: str):
    try:
        draft = portfolio_import_service.reject_draft(draft_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Import draft not found") from exc
    return {
        "success": True,
        "data": draft.model_dump(mode="json"),
    }
