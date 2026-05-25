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
    ParserProviderName,
    PortfolioImportDraft,
    PortfolioImportDraftUpdate,
    PortfolioScreenshotImportOptions,
)
from app.portfolio.ocr_provider import (
    LocalOcrProvider,
    OcrResult,
    PortfolioImageParserProvider,
    VolcengineArkVisionPortfolioImageParser,
    volcengine_ark_vision_status,
)
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
    if not text or text in {"-", "--", "null", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return _to_float(str(value))


def provider_statuses() -> dict[str, Any]:
    default_provider = settings.PORTFOLIO_VISION_PROVIDER
    if default_provider not in {"local_noop", "volcengine_ark_vision"}:
        default_provider = "local_noop"
    return {
        "default_provider": default_provider,
        "providers": [
            {
                "provider": "local_noop",
                "display_name": "手工补录 / 本地不解析",
                "status": "available",
                "enabled": True,
                "configured": True,
                "privacy_boundary": "不发送图片到云端，仅创建可编辑草稿。",
            },
            {
                **volcengine_ark_vision_status(),
                "display_name": "火山方舟云端视觉解析",
                "privacy_boundary": "仅在用户主动勾选同意后，将截图以 base64 图片输入发送至已配置的火山方舟视觉模型。",
            },
        ],
    }


class PortfolioImportService:
    def __init__(
        self,
        root: str | Path | None = None,
        upload_root: str | Path | None = None,
        ocr_provider: PortfolioImageParserProvider | None = None,
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

    def _provider_for(self, provider_name: str | None) -> PortfolioImageParserProvider:
        if provider_name == "volcengine_ark_vision":
            return VolcengineArkVisionPortfolioImageParser()
        return self.ocr_provider

    def get_draft(self, draft_id: str) -> PortfolioImportDraft:
        path = self._draft_path(draft_id)
        if not path.exists():
            raise FileNotFoundError(draft_id)
        return PortfolioImportDraft(**json.loads(path.read_text(encoding="utf-8")))

    def create_draft_from_upload(
        self,
        filename: str,
        content_type: str,
        content: bytes,
        options: PortfolioScreenshotImportOptions | None = None,
    ) -> PortfolioImportDraft:
        if isinstance(options, dict):
            options = PortfolioScreenshotImportOptions(**options)
        options = options or PortfolioScreenshotImportOptions()
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise ValueError("只允许上传 PNG、JPEG 或 WebP 图片。")
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValueError("图片超过 8MB 限制。")
        if options.parser_provider == "volcengine_ark_vision" and not options.cloud_send_consent:
            raise ValueError("选择火山方舟云端视觉解析时，必须先勾选同意将截图发送至已配置的云端视觉模型。")

        draft_id = f"draft_{uuid4().hex}"
        ext = ALLOWED_IMAGE_TYPES[content_type]
        image_path = self.upload_root / f"{draft_id}{ext}"
        image_path.write_bytes(content)
        draft = PortfolioImportDraft(
            draft_id=draft_id,
            source_type=(
                "cloud_vision_parsed_broker_screenshot"
                if options.parser_provider == "volcengine_ark_vision"
                else "portfolio_import_draft"
            ),
            image_reference=str(image_path),
            parser_provider=options.parser_provider,
            cloud_send_consent=options.cloud_send_consent,
            user_notice_acknowledged_at=options.user_notice_acknowledged_at,
            ocr_provider=options.parser_provider,
            ocr_status="uploaded",
            parse_status="uploaded",
            parse_warnings=[f"已上传截图并创建待确认草稿：{filename}。"],
        )
        self._write_draft(draft)
        return self.run_ocr_and_parse(draft_id, options.parser_provider)

    def run_ocr_and_parse(self, draft_id: str, parser_provider: ParserProviderName | str | None = None) -> PortfolioImportDraft:
        draft = self.get_draft(draft_id)
        if parser_provider:
            draft.parser_provider = str(parser_provider)
        if draft.parser_provider == "volcengine_ark_vision" and not draft.cloud_send_consent:
            raise ValueError("未取得云端发送同意，不会发送截图到火山方舟视觉模型。")

        draft.ocr_status = "ocr_processing"
        self._write_draft(draft)
        provider = self._provider_for(draft.parser_provider)
        if hasattr(provider, "parse_image"):
            result: OcrResult = provider.parse_image(Path(draft.image_reference))
        else:
            result = provider.extract_text(Path(draft.image_reference))
        draft.ocr_provider = result.provider_name
        draft.ocr_raw_text = result.raw_text
        draft.cloud_parse_status = result.status if draft.parser_provider == "volcengine_ark_vision" else None
        draft.provider_error_summary = result.error_summary
        warnings = result.warnings or []

        if result.structured_payload is not None:
            rows, parse_warnings = self.parse_structured_payload(result.structured_payload)
            draft.account_summary_draft = self.parse_account_summary(result.structured_payload)
            draft.holding_rows_draft = rows
            source_view = result.structured_payload.get("source_view") or {}
            draft.screenshot_displayed_time = source_view.get("screenshot_displayed_time")
            draft.unrecognized_fields = [str(item) for item in (result.structured_payload.get("unrecognized_text") or [])]
            draft.ocr_status = "draft_parsed"
            draft.parse_status = "needs_user_confirmation" if rows else "manual_review_required"
            draft.parse_warnings.extend(warnings + parse_warnings)
            draft.needs_user_confirmation = True
            self._write_draft(draft)
            return draft

        if result.status in {"failed_manual_entry_required", "cloud_parse_failed"}:
            draft.ocr_status = "ocr_failed"
            draft.parse_status = "manual_review_required" if result.status == "cloud_parse_failed" else "parse_incomplete"
            draft.parse_warnings.extend(warnings)
            draft.parse_warnings.append("视觉解析未能稳定识别持仓行，请在草稿表格中手工补录或修正。")
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

    def parse_account_summary(self, payload: dict[str, Any]) -> AccountSummaryDraft:
        account = payload.get("account_summary") or {}
        return AccountSummaryDraft(
            total_assets_ocr=_coerce_float(account.get("total_assets")),
            cash_available_ocr=_coerce_float(account.get("cash_available")),
            total_market_value_ocr=_coerce_float(account.get("total_market_value")),
            total_pnl_ocr=_coerce_float(account.get("total_unrealized_pnl")),
            repo_amount_ocr=_coerce_float(account.get("repo_amount")),
            repo_available_date_ocr=account.get("repo_available_date"),
        )

    def parse_structured_payload(self, payload: dict[str, Any]) -> tuple[list[HoldingRowDraft], list[str]]:
        rows: list[HoldingRowDraft] = []
        warnings: list[str] = []
        for warning in (payload.get("parse_warnings") or []):
            warnings.append(str(warning))
        source_view = payload.get("source_view") or {}
        for warning in (source_view.get("warnings") or []):
            warnings.append(str(warning))

        for item in payload.get("holdings") or []:
            if not isinstance(item, dict):
                warnings.append("模型返回了非对象持仓行，已忽略。")
                continue
            if {"advice", "recommendation", "buy_sell", "investment_opinion"} & set(item):
                warnings.append("模型返回了投资建议类字段，已忽略，不写入持仓草稿核心结构。")
            row = HoldingRowDraft(
                raw_symbol_text=str(item.get("raw_symbol") or ""),
                raw_name_text=str(item.get("raw_name") or ""),
                raw_quantity_text="" if item.get("quantity") is None else str(item.get("quantity")),
                raw_available_quantity_text="" if item.get("available_quantity") is None else str(item.get("available_quantity")),
                raw_avg_cost_text="" if item.get("avg_cost") is None else str(item.get("avg_cost")),
                raw_screenshot_price_text="" if item.get("screenshot_price") is None else str(item.get("screenshot_price")),
                raw_market_value_text="" if item.get("market_value") is None else str(item.get("market_value")),
                raw_unrealized_pnl_text="" if item.get("unrealized_pnl") is None else str(item.get("unrealized_pnl")),
                raw_unrealized_pnl_pct_text="" if item.get("unrealized_pnl_pct") is None else str(item.get("unrealized_pnl_pct")),
                quantity=_coerce_float(item.get("quantity")),
                available_quantity=_coerce_float(item.get("available_quantity")),
                avg_cost=_coerce_float(item.get("avg_cost")),
                broker_screenshot_price=_coerce_float(item.get("screenshot_price")),
                broker_screenshot_market_value=_coerce_float(item.get("market_value")),
                broker_screenshot_unrealized_pnl=_coerce_float(item.get("unrealized_pnl")),
                broker_screenshot_unrealized_pnl_pct=_coerce_float(item.get("unrealized_pnl_pct")),
                validation_warnings=[str(w) for w in (item.get("warnings") or [])],
            )
            self.normalize_row(row)
            if (
                row.quantity is not None
                and row.broker_screenshot_price is not None
                and row.broker_screenshot_market_value is not None
            ):
                expected = row.quantity * row.broker_screenshot_price
                if expected and abs(expected - row.broker_screenshot_market_value) / abs(expected) > 0.08:
                    row.validation_warnings.append("截图价格、数量与市值差异较大，请人工核对。")
            rows.append(row)
        if not rows:
            warnings.append("模型未返回可用持仓行，可在草稿表格中手工新增。")
        return rows, warnings

    def parse_ocr_text(self, text: str) -> tuple[list[HoldingRowDraft], list[str]]:
        rows: list[HoldingRowDraft] = []
        warnings: list[str] = []
        for line in text.splitlines():
            clean = line.strip()
            if not clean or clean.startswith("#"):
                continue
            parts = re.split(r"[\t|,，\s]+", clean)
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
            warnings.append("未能从识别文本中解析出持仓行，可在确认页手工新增。")
        return rows, warnings

    def normalize_row(self, row: HoldingRowDraft) -> HoldingRowDraft:
        existing_warnings = list(row.validation_warnings)
        row.validation_warnings = existing_warnings
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
        if row.available_quantity is not None and row.available_quantity < 0:
            row.validation_warnings.append("可用数量不能为负数。")
        if row.available_quantity is not None and row.quantity is not None and row.available_quantity > row.quantity:
            row.validation_warnings.append("可用数量大于持仓数量，请核对。")
        if row.avg_cost is None or row.avg_cost <= 0:
            row.validation_warnings.append("平均成本缺失或无效。")
        if row.broker_screenshot_price is not None and row.broker_screenshot_price < 0:
            row.validation_warnings.append("截图价格不能为负数。")
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
        confirmed_source_name = (
            "同花顺持仓截图 + 火山方舟视觉解析 + 用户人工确认"
            if draft.parser_provider == "volcengine_ark_vision"
            else f"{draft.source_name} + 用户人工确认"
        )
        for row in draft.holding_rows_draft:
            row_errors: list[str] = []
            if not row.normalized_symbol:
                row_errors.append(f"{row.raw_name_text or row.raw_symbol_text} 未匹配标准代码。")
            if row.symbol_match_status == "conflict_requires_confirmation" and not row.confirmed_by_user:
                row_errors.append(f"{row.raw_symbol_text} 名称冲突，需人工确认。")
            if row.quantity is None or row.avg_cost is None:
                row_errors.append(f"{row.normalized_symbol or row.raw_name_text} 缺少持仓数量或平均成本。")
            if row.available_quantity is not None and row.quantity is not None and row.available_quantity > row.quantity:
                row_errors.append(f"{row.normalized_symbol or row.raw_name_text} 可用数量大于持仓数量。")
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
                broker_screenshot_price_source=confirmed_source_name,
                broker_screenshot_price_time=None,
                broker_screenshot_market_value=row.broker_screenshot_market_value,
                broker_screenshot_unrealized_pnl=row.broker_screenshot_unrealized_pnl,
                broker_screenshot_unrealized_pnl_pct=row.broker_screenshot_unrealized_pnl_pct,
                source_type="manual_account",
                source_name=confirmed_source_name,
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
            source_type=(
                "broker_screenshot_cloud_parsed_user_confirmed"
                if draft.parser_provider == "volcengine_ark_vision"
                else "broker_screenshot_confirmed"
            ),
            source_name=confirmed_source_name,
            draft_id=draft.draft_id,
            confirmed_at=now,
            positions=positions,
        )
        state = self.portfolio_service.save_snapshot(snapshot_input)
        self.portfolio_service.add_manual_evidence(ManualEvidenceCreate(
            symbol=None,
            evidence_type=ManualEvidenceType.INTRADAY_SCREENSHOT,
            title="持仓截图确认来源",
            text="截图仅作为本地账户快照来源附件；默认不纳入 Analysis Packet。",
            source=confirmed_source_name,
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
