from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.portfolio.import_schemas import (
    AccountSummaryDraft,
    HoldingRowDraft,
    PortfolioImportDraft,
    PortfolioImportDraftUpdate,
)
from app.portfolio.ocr_provider import LocalOcrProvider, OcrResult
from app.portfolio.schemas import (
    ManualEvidenceCreate,
    ManualEvidenceType,
    PortfolioPositionInput,
    PortfolioSnapshotInput,
)
from app.portfolio.service import PortfolioService
from app.portfolio.symbol_resolver import resolve_symbol_or_name


MAX_UPLOAD_BYTES = 8 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}


def _to_float(value: str | None) -> float | None:
    if not value:
        return None
    text = value.replace(",", "").replace("%", "").strip()
    if not text or text in {"-", "--"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


class PortfolioImportService:
    def __init__(
        self,
        root: str | Path | None = None,
        upload_root: str | Path | None = None,
        ocr_provider: LocalOcrProvider | None = None,
        portfolio_service: PortfolioService | None = None,
    ):
        self.root = Path(root or Path(settings.PORTFOLIO_DATA_DIR) / "imports")
        self.upload_root = Path(upload_root or "data/uploads/portfolio_screenshots")
        self.root.mkdir(parents=True, exist_ok=True)
        self.upload_root.mkdir(parents=True, exist_ok=True)
        self.ocr_provider = ocr_provider or LocalOcrProvider()
        self.portfolio_service = portfolio_service or PortfolioService()

    def _draft_path(self, draft_id: str) -> Path:
        return self.root / f"{draft_id}.json"

    def _write_draft(self, draft: PortfolioImportDraft) -> None:
        self._draft_path(draft.draft_id).write_text(
            json.dumps(draft.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def get_draft(self, draft_id: str) -> PortfolioImportDraft:
        path = self._draft_path(draft_id)
        if not path.exists():
            raise FileNotFoundError(draft_id)
        return PortfolioImportDraft(**json.loads(path.read_text(encoding="utf-8")))

    def create_draft_from_upload(self, filename: str, content_type: str, content: bytes) -> PortfolioImportDraft:
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise ValueError("只允许上传 PNG、JPEG 或 WebP 图片。")
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValueError("图片超过 8MB 限制。")
        draft_id = f"draft_{uuid4().hex}"
        ext = ALLOWED_IMAGE_TYPES[content_type]
        image_path = self.upload_root / f"{draft_id}{ext}"
        image_path.write_bytes(content)
        draft = PortfolioImportDraft(
            draft_id=draft_id,
            image_reference=str(image_path),
            ocr_status="uploaded",
            parse_status="uploaded",
            parse_warnings=[f"已上传脱敏截图：{filename}。"],
        )
        self._write_draft(draft)
        return self.run_ocr_and_parse(draft_id)

    def run_ocr_and_parse(self, draft_id: str) -> PortfolioImportDraft:
        draft = self.get_draft(draft_id)
        draft.ocr_status = "ocr_processing"
        self._write_draft(draft)
        result: OcrResult = self.ocr_provider.extract_text(Path(draft.image_reference))
        draft.ocr_provider = result.provider_name
        draft.ocr_raw_text = result.raw_text
        warnings = result.warnings or []
        if result.status == "failed_manual_entry_required":
            draft.ocr_status = "ocr_failed"
            draft.parse_status = "parse_incomplete"
            draft.parse_warnings.extend(warnings)
            draft.parse_warnings.append("OCR 未能稳定识别持仓行，请在草稿表格中手工补录或修正。")
            draft.needs_user_confirmation = True
            self._write_draft(draft)
            return draft

        draft.ocr_status = "draft_parsed"
        rows, parse_warnings = self.parse_ocr_text(result.raw_text)
        draft.holding_rows_draft = rows
        draft.parse_warnings.extend(warnings + parse_warnings)
        draft.parse_status = "needs_user_confirmation" if rows else "parse_incomplete"
        draft.needs_user_confirmation = True
        self._write_draft(draft)
        return draft

    def parse_ocr_text(self, text: str) -> tuple[list[HoldingRowDraft], list[str]]:
        rows: list[HoldingRowDraft] = []
        warnings: list[str] = []
        for line in text.splitlines():
            clean = line.strip()
            if not clean or clean.startswith("#"):
                continue
            parts = re.split(r"[\t|,， ]+", clean)
            if len(parts) < 3:
                warnings.append(f"无法解析行：{clean}")
                continue
            symbol_text = parts[0] if re.search(r"\d{6}", parts[0]) else ""
            name_index = 1 if symbol_text else 0
            name_text = parts[name_index]
            numeric = parts[name_index + 1 :]
            row = HoldingRowDraft(
                raw_symbol_text=symbol_text,
                raw_name_text=name_text,
                raw_quantity_text=numeric[0] if len(numeric) > 0 else "",
                raw_available_quantity_text=numeric[1] if len(numeric) > 1 else "",
                raw_avg_cost_text=numeric[2] if len(numeric) > 2 else "",
                raw_screenshot_price_text=numeric[3] if len(numeric) > 3 else "",
                raw_market_value_text=numeric[4] if len(numeric) > 4 else "",
                raw_unrealized_pnl_text=numeric[5] if len(numeric) > 5 else "",
                raw_unrealized_pnl_pct_text=numeric[6] if len(numeric) > 6 else "",
            )
            row.quantity = _to_float(row.raw_quantity_text)
            row.available_quantity = _to_float(row.raw_available_quantity_text)
            row.avg_cost = _to_float(row.raw_avg_cost_text)
            row.broker_screenshot_price = _to_float(row.raw_screenshot_price_text)
            row.broker_screenshot_market_value = _to_float(row.raw_market_value_text)
            row.broker_screenshot_unrealized_pnl = _to_float(row.raw_unrealized_pnl_text)
            row.broker_screenshot_unrealized_pnl_pct = _to_float(row.raw_unrealized_pnl_pct_text)
            self.normalize_row(row)
            rows.append(row)
        if not rows:
            warnings.append("未能从 OCR 文本中解析出持仓行，可在确认页手工新增。")
        return rows, warnings

    def normalize_row(self, row: HoldingRowDraft) -> HoldingRowDraft:
        symbol, name, status, candidates, warnings = resolve_symbol_or_name(row.raw_symbol_text, row.raw_name_text)
        row.normalized_symbol = symbol
        row.normalized_name = name
        row.symbol_match_status = status
        row.symbol_candidates = candidates
        row.validation_warnings.extend(warnings)
        if candidates:
            first = candidates[0]
            row.external_driver_profile_id = first.external_driver_profile_id
            row.external_driver_mapping_status = first.external_driver_mapping_status
            if first.external_driver_mapping_status == "configured":
                row.suggested_theme_tags = [first.external_driver_profile_id or ""]
        if row.quantity is None or row.quantity < 0:
            row.validation_warnings.append("持仓数量缺失或无效。")
        if row.available_quantity is not None and row.quantity is not None and row.available_quantity > row.quantity:
            row.validation_warnings.append("可用数量大于持仓数量，请核对。")
        if row.avg_cost is None or row.avg_cost <= 0:
            row.validation_warnings.append("平均成本缺失或无效。")
        row.row_confidence = 0.8 if status == "exact_code_match" and not row.validation_warnings else 0.45
        return row

    def update_draft(self, draft_id: str, payload: PortfolioImportDraftUpdate) -> PortfolioImportDraft:
        draft = self.get_draft(draft_id)
        if payload.account_summary_draft is not None:
            draft.account_summary_draft = payload.account_summary_draft
        if payload.holding_rows_draft is not None:
            draft.holding_rows_draft = [self.normalize_row(row) for row in payload.holding_rows_draft]
        if payload.parse_warnings is not None:
            draft.parse_warnings = payload.parse_warnings
        draft.parse_status = "needs_user_confirmation"
        self._write_draft(draft)
        return draft

    def reject_draft(self, draft_id: str) -> PortfolioImportDraft:
        draft = self.get_draft(draft_id)
        draft.parse_status = "user_rejected"
        draft.needs_user_confirmation = False
        self._write_draft(draft)
        return draft

    def confirm_draft(self, draft_id: str) -> dict[str, Any]:
        draft = self.get_draft(draft_id)
        positions: list[PortfolioPositionInput] = []
        errors: list[str] = []
        for row in draft.holding_rows_draft:
            row_errors: list[str] = []
            if not row.normalized_symbol:
                row_errors.append(f"{row.raw_name_text or row.raw_symbol_text} 未匹配标准代码。")
            if row.symbol_match_status == "conflict_requires_confirmation" and not row.confirmed_by_user:
                row_errors.append(f"{row.raw_symbol_text} 名称冲突，需人工确认。")
            if row.quantity is None or row.avg_cost is None:
                row_errors.append(f"{row.normalized_symbol or row.raw_name_text} 缺少持仓数量或平均成本。")
            if row_errors:
                errors.extend(row_errors)
                continue
            positions.append(PortfolioPositionInput(
                symbol=row.normalized_symbol or "",
                name=row.normalized_name or row.raw_name_text,
                quantity=float(row.quantity or 0),
                available_quantity=row.available_quantity,
                avg_cost=float(row.avg_cost or 0),
                broker_screenshot_price=row.broker_screenshot_price,
                broker_screenshot_price_source=draft.source_name,
                broker_screenshot_price_time=None,
                broker_screenshot_market_value=row.broker_screenshot_market_value,
                broker_screenshot_unrealized_pnl=row.broker_screenshot_unrealized_pnl,
                broker_screenshot_unrealized_pnl_pct=row.broker_screenshot_unrealized_pnl_pct,
                source_type="manual_account",
                source_name=f"{draft.source_name} + 用户人工确认",
                import_draft_id=draft.draft_id,
                confirmed_by_user=True,
                position_role=row.position_role or "observation",
                primary_theme=row.primary_theme,
                theme_tags=row.theme_tags,
                user_plan=row.user_plan or "",
                invalid_condition=row.invalid_condition,
                target_max_weight=row.target_max_weight,
            ))
        if errors:
            raise ValueError("；".join(errors))
        now = datetime.utcnow()
        confirmed = draft.account_summary_draft.user_confirmed_values
        snapshot_input = PortfolioSnapshotInput(
            snapshot_time=now,
            total_assets=confirmed.get("total_assets") or draft.account_summary_draft.total_assets_ocr,
            cash_available=float(confirmed.get("cash_available") or draft.account_summary_draft.cash_available_ocr or 0),
            repo_amount=float(confirmed.get("repo_amount") or draft.account_summary_draft.repo_amount_ocr or 0),
            source_type="broker_screenshot_confirmed",
            source_name=f"{draft.source_name} + 用户人工确认",
            draft_id=draft.draft_id,
            confirmed_at=now,
            positions=positions,
        )
        state = self.portfolio_service.save_snapshot(snapshot_input)
        self.portfolio_service.add_manual_evidence(ManualEvidenceCreate(
            symbol=None,
            evidence_type=ManualEvidenceType.INTRADAY_SCREENSHOT,
            title="持仓截图识别来源",
            text="截图仅作为本地账户快照来源附件；默认不纳入 Analysis Packet。",
            source=f"{draft.source_name} + 用户人工确认",
            attachment_path=draft.image_reference,
            image_reference=Path(draft.image_reference).name,
            include_in_analysis_packet=False,
            llm_usage="context_only",
        ))
        draft.confirmed_at = now
        draft.saved_snapshot_id = state.snapshot.snapshot_id
        draft.parse_status = "saved_as_portfolio_snapshot"
        draft.ocr_status = "user_confirmed"
        draft.needs_user_confirmation = False
        for row in draft.holding_rows_draft:
            row.confirmed_by_user = True
        self._write_draft(draft)
        return {"draft": draft, "state": state}


portfolio_import_service = PortfolioImportService()
