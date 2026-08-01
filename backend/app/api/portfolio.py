import asyncio
from dataclasses import asdict

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile

from app.disclosure_verification import refresh_portfolio_disclosure_verifications
from app.portfolio import portfolio_service
from app.analysis_packet.packet_service import build_account_analysis_context
from app.portfolio.dashboard_cache import get_dashboard_bundle, invalidate_dashboard_cache
from app.portfolio.import_schemas import (
    PortfolioImportConfirmOptions,
    PortfolioImportDraftUpdate,
    PortfolioScreenshotImportOptions,
)
from app.portfolio.import_service import portfolio_import_service, provider_statuses
from app.portfolio.schemas import (
    HoldingSemanticBatchUpdate,
    ManualEvidenceCreate,
    ManualEvidenceIncludeUpdate,
    PortfolioSnapshotInput,
    TradeSimulationRequest,
)
from app.services.portfolio_etf_share_sync import sync_new_etf_share_data
from app.agent_review.service import suggest_trade_reason

router = APIRouter()


@router.get("/portfolio")
def get_portfolio():
    return {
        "success": True,
        "data": portfolio_service.get_state().model_dump(mode="json"),
    }


@router.put("/portfolio")
def save_portfolio(payload: PortfolioSnapshotInput):
    previous_snapshot = portfolio_service.load_snapshot()
    state = portfolio_service.save_snapshot(payload)
    invalidate_dashboard_cache()
    etf_share_update = sync_new_etf_share_data(previous_snapshot, state.snapshot)
    return {
        "success": True,
        "data": state.model_dump(mode="json"),
        "etf_share_update": [asdict(item) for item in etf_share_update],
    }


@router.get("/portfolio/semantic-suggestions")
def get_portfolio_semantic_suggestions():
    return {
        "success": True,
        "items": [item.model_dump(mode="json") for item in portfolio_service.holding_semantic_suggestions()],
    }


@router.patch("/portfolio/holding-semantics")
def update_portfolio_holding_semantics(payload: HoldingSemanticBatchUpdate):
    invalidate_dashboard_cache()
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
    invalidate_dashboard_cache()
    return {
        "success": True,
        "data": portfolio_service.add_manual_evidence(payload).model_dump(mode="json"),
    }


@router.delete("/portfolio/manual-evidence/{evidence_id}")
def delete_manual_evidence(evidence_id: str):
    if not portfolio_service.delete_manual_evidence(evidence_id):
        raise HTTPException(status_code=404, detail="Manual evidence not found")
    invalidate_dashboard_cache()
    return {"success": True}


@router.patch("/portfolio/manual-evidence/{evidence_id}/include")
def update_manual_evidence_include(evidence_id: str, payload: ManualEvidenceIncludeUpdate):
    updated = portfolio_service.update_manual_evidence_include(evidence_id, payload.include_in_analysis_packet)
    if updated is None:
        raise HTTPException(status_code=404, detail="Manual evidence not found")
    invalidate_dashboard_cache()
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
def portfolio_account_analysis_context(mode: str = Query(default="compact"), force: bool = Query(False)):
    if mode == "compact":
        data = get_dashboard_bundle(force=force)["context"]
    else:
        data = build_account_analysis_context(mode=mode)
    return {
        "success": True,
        "data": data,
    }


@router.get("/portfolio/dashboard")
def portfolio_dashboard(force: bool = Query(False)):
    bundle = get_dashboard_bundle(force=force)
    data = bundle["dashboard"]
    data["_cache"] = bundle["cache"]
    return {
        "success": True,
        "data": data,
    }


@router.post("/portfolio/disclosure-verification/refresh")
def refresh_portfolio_disclosures(background_tasks: BackgroundTasks, force: bool = Query(False)):
    background_tasks.add_task(refresh_portfolio_disclosure_verifications, force=force)
    return {
        "success": True,
        "status": "scheduled",
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
    screenshot_kind: str = Form("current_holdings"),
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
                screenshot_kind=screenshot_kind,
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
def confirm_portfolio_import_draft(
    draft_id: str,
    payload: PortfolioImportConfirmOptions | None = None,
):
    try:
        options = payload or PortfolioImportConfirmOptions()
        previous_snapshot = portfolio_service.load_snapshot()
        result = portfolio_import_service.confirm_draft(
            draft_id,
            apply_transactions_to_portfolio=options.apply_transactions_to_portfolio,
            user_reason=options.user_reason,
        )
        invalidate_dashboard_cache()
        etf_share_update = sync_new_etf_share_data(previous_snapshot, result["state"].snapshot)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Import draft not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "success": True,
        "data": {
            "draft": result["draft"].model_dump(mode="json"),
            "portfolio": result["state"].model_dump(mode="json"),
            "transaction_batch": result.get("transaction_batch"),
            "operation_samples": result.get("operation_samples", []),
        },
        "etf_share_update": [asdict(item) for item in etf_share_update],
    }


@router.post("/portfolio/import/drafts/{draft_id}/suggest-reason")
async def suggest_portfolio_trade_reason(draft_id: str):
    try:
        draft = portfolio_import_service.get_draft(draft_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Import draft not found") from exc
    if draft.screenshot_kind != "trade_history":
        raise HTTPException(status_code=422, detail="仅交易行为截图支持生成交易理由草稿")
    if not draft.cloud_send_consent:
        raise HTTPException(status_code=422, detail="需要先同意将结构化成交信息发送至已配置模型")
    transactions = [
        row.model_dump(mode="json")
        for row in draft.transaction_rows_draft
    ]
    positions = portfolio_service.get_state().snapshot.model_dump(mode="json").get("positions", [])
    try:
        result = await asyncio.to_thread(suggest_trade_reason, transactions, positions)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"交易理由草稿生成失败：{str(exc)}") from exc
    return {"success": True, "data": result}


@router.get("/portfolio/transactions")
def get_portfolio_transactions(limit: int = Query(50, ge=1, le=500)):
    return {
        "success": True,
        "items": portfolio_import_service.trade_ledger.list_batches(limit),
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
