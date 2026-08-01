from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from app.core.config import settings
from app.portfolio.import_schemas import (
    AccountSummaryDraft,
    HoldingRowDraft,
    ParserProviderName,
    PortfolioImportDraft,
    PortfolioImportDraftUpdate,
    PortfolioScreenshotImportOptions,
    TransactionRowDraft,
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
from app.portfolio.trade_ledger import PortfolioTradeLedger
from app.facts.common import compact_symbol


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
                "display_name": "手工补录",
                "status": "available",
                "enabled": True,
                "configured": True,
                "privacy_boundary": "不发送图片到云端，仅创建可编辑草稿。",
            },
            {
                **volcengine_ark_vision_status(),
                "display_name": "云端视觉解析",
                "privacy_boundary": "选择该方式后，将截图发送至已配置的云端视觉模型。",
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
        trade_ledger: PortfolioTradeLedger | None = None,
        operation_capture: Callable[[], list[dict[str, Any]]] | None = None,
    ):
        self.root = Path(root or Path(settings.PORTFOLIO_DATA_DIR) / "imports")
        self.upload_root = Path(upload_root or "data/uploads/portfolio_screenshots")
        self.root.mkdir(parents=True, exist_ok=True)
        self.upload_root.mkdir(parents=True, exist_ok=True)
        self.ocr_provider = ocr_provider or LocalOcrProvider()
        self.portfolio_service = portfolio_service or PortfolioService()
        self.trade_ledger = trade_ledger or PortfolioTradeLedger(self.root.parent / "trade_ledger")
        self.operation_capture = operation_capture

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
        options: PortfolioScreenshotImportOptions | dict[str, Any] | None = None,
    ) -> PortfolioImportDraft:
        if isinstance(options, dict):
            options = PortfolioScreenshotImportOptions(**options)
        options = options or PortfolioScreenshotImportOptions()
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise ValueError("只允许上传 PNG、JPEG 或 WebP 图片。")
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValueError("图片超过 8MB 限制。")
        if options.parser_provider == "volcengine_ark_vision" and not options.cloud_send_consent:
            raise ValueError("选择云端视觉解析时，必须明确提交云端发送授权。")

        draft_id = f"draft_{uuid4().hex}"
        image_path = self.upload_root / f"{draft_id}{ALLOWED_IMAGE_TYPES[content_type]}"
        image_path.write_bytes(content)
        draft = PortfolioImportDraft(
            draft_id=draft_id,
            source_type="cloud_vision_parsed_broker_screenshot"
            if options.parser_provider == "volcengine_ark_vision"
            else "portfolio_import_draft",
            image_reference=str(image_path),
            screenshot_kind=options.screenshot_kind,
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
            raise ValueError("未取得云端发送授权，不会发送截图到云端视觉模型。")

        draft.ocr_status = "ocr_processing"
        self._write_draft(draft)
        provider = self._provider_for(draft.parser_provider)
        result: OcrResult = (
            provider.parse_image(Path(draft.image_reference), draft.screenshot_kind)
            if hasattr(provider, "parse_image")
            else provider.extract_text(Path(draft.image_reference))
        )
        draft.ocr_provider = result.provider_name
        draft.ocr_raw_text = result.raw_text
        draft.cloud_parse_status = result.status if draft.parser_provider == "volcengine_ark_vision" else None
        draft.provider_error_summary = result.error_summary
        draft.provider_model = result.model_name
        draft.provider_prompt_version = result.prompt_version
        draft.provider_finish_reason = result.finish_reason
        draft.provider_usage = result.usage or {}
        warnings = result.warnings or []

        if result.structured_payload is not None:
            if draft.screenshot_kind == "trade_history":
                transaction_rows, parse_warnings = self.parse_transaction_payload(result.structured_payload)
                draft.transaction_rows_draft = transaction_rows
                draft.transaction_apply_recommendation, draft.transaction_apply_reason = (
                    self.transaction_apply_recommendation(transaction_rows)
                )
                has_rows = bool(transaction_rows)
            else:
                rows, parse_warnings = self.parse_structured_payload(result.structured_payload)
                draft.account_summary_draft = self.parse_account_summary(result.structured_payload)
                draft.holding_rows_draft = rows
                has_rows = bool(rows)
            source_view = result.structured_payload.get("source_view") or {}
            draft.screenshot_displayed_time = source_view.get("screenshot_displayed_time")
            draft.unrecognized_fields = [str(item) for item in (result.structured_payload.get("unrecognized_text") or [])]
            draft.ocr_status = "draft_parsed"
            draft.parse_status = "needs_user_confirmation" if has_rows else "manual_review_required"
            draft.parse_warnings.extend(warnings + parse_warnings)
            draft.needs_user_confirmation = True
            self._write_draft(draft)
            return draft

        if result.status in {"failed_manual_entry_required", "cloud_parse_failed"}:
            draft.ocr_status = "ocr_failed"
            draft.parse_status = "manual_review_required" if result.status == "cloud_parse_failed" else "parse_incomplete"
            draft.parse_warnings.extend(warnings)
            draft.parse_warnings.append("视觉识别未能稳定解析数据行，请在草稿表格中手工补录或修正。")
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
        warnings: list[str] = [str(w) for w in (payload.get("parse_warnings") or [])]
        source_view = payload.get("source_view") or {}
        warnings.extend(str(w) for w in (source_view.get("warnings") or []))
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
            if row.quantity is not None and row.broker_screenshot_price is not None and row.broker_screenshot_market_value is not None:
                expected = row.quantity * row.broker_screenshot_price
                if expected and abs(expected - row.broker_screenshot_market_value) / abs(expected) > 0.08:
                    row.validation_warnings.append("截图价格、数量与市值差异较大，请人工核对。")
            rows.append(row)
        if not rows:
            warnings.append("模型未返回可用持仓行，可在草稿表格中手工新增。")
        return rows, warnings

    def normalize_transaction_row(self, row: TransactionRowDraft) -> TransactionRowDraft:
        symbol, name, status, candidates, warnings = resolve_symbol_or_name(
            row.raw_symbol_text,
            row.raw_name_text,
        )
        row.normalized_symbol = symbol
        row.normalized_name = name
        row.symbol_match_status = status
        row.symbol_candidates = candidates
        row.validation_warnings = [*row.validation_warnings, *warnings]
        side_text = str(row.raw_side_text or row.side or "").strip().lower()
        row.side = (
            "buy" if side_text in {"buy", "买", "买入"}
            else "sell" if side_text in {"sell", "卖", "卖出"}
            else None
        )
        if row.side is None:
            row.validation_warnings.append("买卖方向无法识别。")
        if row.average_price is None or row.average_price <= 0:
            row.validation_warnings.append("成交均价缺失或无效。")
        if row.quantity is None or row.quantity <= 0:
            row.validation_warnings.append("成交量缺失或无效。")
        if row.amount is None or row.amount <= 0:
            row.validation_warnings.append("成交额缺失或无效。")
        if row.average_price and row.quantity and row.amount:
            expected = row.average_price * row.quantity
            tolerance = max(1.0, abs(expected) * 0.01)
            if abs(expected - row.amount) > tolerance:
                row.validation_warnings.append("成交均价×成交量与成交额不一致，请核对。")
        row.validation_warnings = list(dict.fromkeys(row.validation_warnings))
        row.row_confidence = 0.85 if row.normalized_symbol and not row.validation_warnings else 0.45
        return row

    def parse_transaction_payload(self, payload: dict[str, Any]) -> tuple[list[TransactionRowDraft], list[str]]:
        rows: list[TransactionRowDraft] = []
        warnings = [str(item) for item in (payload.get("parse_warnings") or [])]
        source_view = payload.get("source_view") or {}
        warnings.extend(str(item) for item in (source_view.get("warnings") or []))
        for item in payload.get("transactions") or []:
            if not isinstance(item, dict):
                warnings.append("模型返回了非对象成交行，已忽略。")
                continue
            row = TransactionRowDraft(
                raw_symbol_text=str(item.get("raw_symbol") or ""),
                raw_name_text=str(item.get("raw_name") or ""),
                raw_side_text=str(item.get("side") or ""),
                side=item.get("side") if item.get("side") in {"buy", "sell"} else None,
                average_price=_coerce_float(item.get("average_price")),
                quantity=_coerce_float(item.get("quantity")),
                amount=_coerce_float(item.get("amount")),
                occurred_at=item.get("occurred_at"),
                validation_warnings=[str(value) for value in (item.get("warnings") or [])],
            )
            rows.append(self.normalize_transaction_row(row))
        if not rows:
            warnings.append("模型未返回可用成交行。")
        return rows, warnings

    def transaction_apply_recommendation(
        self,
        rows: list[TransactionRowDraft],
    ) -> tuple[str, str]:
        current = {
            compact_symbol(position.symbol): float(position.quantity or 0)
            for position in self.portfolio_service.load_snapshot().positions
        }
        for row in rows:
            if not row.normalized_symbol or not row.side or not row.quantity:
                return "review_required", "存在未完成证券匹配或缺少成交字段的记录。"
            symbol = compact_symbol(row.normalized_symbol)
            quantity = float(row.quantity)
            before = current.get(symbol, 0)
            if row.side == "sell" and quantity > before:
                return (
                    "record_only",
                    f"{row.normalized_name or row.raw_name_text} 卖出 {quantity:g}，超过当前持仓 {before:g}；"
                    "当前持仓很可能已经包含本批成交，建议只记录交易。",
                )
            current[symbol] = before + quantity if row.side == "buy" else before - quantity
        return "apply", "成交数量可基于当前快照顺序应用。"

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
            numeric = parts[name_index + 1 :]
            row = HoldingRowDraft(
                raw_symbol_text=symbol_text,
                raw_name_text=parts[name_index],
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
        if row.avg_cost is None:
            row.validation_warnings.append("平均成本缺失。")
        elif row.avg_cost < 0:
            row.validation_warnings.append("识别到负摊薄成本，请核对截图原值。")
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
        if payload.transaction_rows_draft is not None:
            draft.transaction_rows_draft = [
                self.normalize_transaction_row(row)
                for row in payload.transaction_rows_draft
            ]
            draft.transaction_apply_recommendation, draft.transaction_apply_reason = (
                self.transaction_apply_recommendation(draft.transaction_rows_draft)
            )
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

    def confirm_draft(
        self,
        draft_id: str,
        *,
        apply_transactions_to_portfolio: bool = True,
        user_reason: str | None = None,
    ) -> dict[str, Any]:
        draft = self.get_draft(draft_id)
        if draft.screenshot_kind == "trade_history":
            return self._confirm_trade_draft(
                draft,
                apply_transactions_to_portfolio=apply_transactions_to_portfolio,
                user_reason=user_reason,
            )
        return self._confirm_holdings_draft(draft)

    def _confirm_trade_draft(
        self,
        draft: PortfolioImportDraft,
        *,
        apply_transactions_to_portfolio: bool,
        user_reason: str | None,
    ) -> dict[str, Any]:
        errors: list[str] = []
        for row in draft.transaction_rows_draft:
            if not row.normalized_symbol:
                errors.append(f"{row.raw_name_text or row.raw_symbol_text} 未匹配标准代码。")
            if row.symbol_match_status == "conflict_requires_confirmation" and not row.confirmed_by_user:
                errors.append(f"{row.raw_symbol_text} 名称冲突，需人工确认。")
            if not row.side or row.average_price is None or row.quantity is None or row.amount is None:
                errors.append(f"{row.normalized_name or row.raw_name_text} 缺少买卖方向或成交字段。")
            if row.average_price is not None and row.average_price <= 0:
                errors.append(f"{row.normalized_name or row.raw_name_text} 成交均价必须大于 0。")
            if row.quantity is not None and row.quantity <= 0:
                errors.append(f"{row.normalized_name or row.raw_name_text} 成交量必须大于 0。")
        if not draft.transaction_rows_draft:
            errors.append("成交草稿中没有可确认记录。")
        if errors:
            raise ValueError("；".join(errors))

        state = self.portfolio_service.get_state()
        resulting_snapshot_id: str | None = None
        if apply_transactions_to_portfolio:
            recommendation, reason = self.transaction_apply_recommendation(draft.transaction_rows_draft)
            if recommendation != "apply":
                raise ValueError(f"当前交易不适合直接应用到持仓：{reason}")
            snapshot = self.portfolio_service.load_snapshot()
            input_fields = set(PortfolioPositionInput.model_fields)
            positions = {
                compact_symbol(position.symbol): {
                    key: value
                    for key, value in position.model_dump().items()
                    if key in input_fields
                }
                for position in snapshot.positions
            }
            cash_delta = 0.0
            for row in draft.transaction_rows_draft:
                symbol = compact_symbol(row.normalized_symbol or "")
                quantity = float(row.quantity or 0)
                amount = float(row.amount or (float(row.average_price or 0) * quantity))
                existing = positions.get(symbol)
                if row.side == "buy":
                    old_quantity = float((existing or {}).get("quantity") or 0)
                    old_cost = float((existing or {}).get("avg_cost") or 0)
                    new_quantity = old_quantity + quantity
                    new_cost = (
                        (old_quantity * old_cost + amount) / new_quantity
                        if new_quantity
                        else float(row.average_price or 0)
                    )
                    if existing:
                        existing["quantity"] = new_quantity
                        existing["available_quantity"] = None
                        existing["avg_cost"] = round(new_cost, 6)
                        existing["source_type"] = "confirmed_trade_ledger"
                        existing["source_name"] = "成交截图 + 用户确认"
                        existing["import_draft_id"] = draft.draft_id
                        existing["confirmed_by_user"] = True
                    else:
                        positions[symbol] = {
                            "symbol": row.normalized_symbol or symbol,
                            "name": row.normalized_name or row.raw_name_text,
                            "quantity": new_quantity,
                            "available_quantity": None,
                            "avg_cost": round(new_cost, 6),
                            "source_type": "confirmed_trade_ledger",
                            "source_name": "成交截图 + 用户确认",
                            "import_draft_id": draft.draft_id,
                            "confirmed_by_user": True,
                            "position_role": "observation",
                        }
                    cash_delta -= amount
                else:
                    if not existing or float(existing.get("quantity") or 0) < quantity:
                        raise ValueError(f"{row.normalized_name or row.raw_name_text} 卖出数量超过当前持仓。")
                    old_quantity = float(existing["quantity"])
                    old_cost = float(existing.get("avg_cost") or 0)
                    remaining = old_quantity - quantity
                    cash_delta += amount
                    if remaining <= 1e-8:
                        del positions[symbol]
                    else:
                        existing["quantity"] = remaining
                        existing["available_quantity"] = None
                        existing["avg_cost"] = round(
                            (old_quantity * old_cost - amount) / remaining,
                            6,
                        )
                        existing["source_type"] = "confirmed_trade_ledger"
                        existing["source_name"] = "成交截图 + 用户确认"
                        existing["import_draft_id"] = draft.draft_id
                        existing["confirmed_by_user"] = True

            now = datetime.utcnow()
            snapshot_input = PortfolioSnapshotInput(
                portfolio_id=snapshot.portfolio_id,
                snapshot_time=now,
                total_assets=snapshot.total_assets,
                cash_available=round(float(snapshot.cash_available or 0) + cash_delta, 2),
                account_actual_total_cost=snapshot.account_actual_total_cost,
                repo_amount=snapshot.repo_amount,
                repo_available_date=snapshot.repo_available_date,
                notes=snapshot.notes,
                source_type="broker_trade_screenshot_confirmed",
                source_name="成交截图 + MiniMax M3 + 用户确认",
                draft_id=draft.draft_id,
                confirmed_at=now,
                risk_limits=snapshot.risk_limits,
                positions=[PortfolioPositionInput(**item) for item in positions.values()],
            )
            state = self.portfolio_service.save_snapshot(snapshot_input)
            resulting_snapshot_id = state.snapshot.snapshot_id

        batch = self.trade_ledger.append_confirmed_batch(
            draft,
            applied_to_portfolio=apply_transactions_to_portfolio,
            resulting_snapshot_id=resulting_snapshot_id,
            user_reason=user_reason,
        )
        operation_samples = self.operation_capture() if self.operation_capture else []
        self.portfolio_service.add_manual_evidence(ManualEvidenceCreate(
            symbol=None,
            evidence_type=ManualEvidenceType.INTRADAY_SCREENSHOT,
            title="成交截图确认来源",
            text="成交记录已由用户确认并写入本地交易台账；是否应用到持仓由确认选项决定。",
            source="同花顺成交截图 + 云端视觉解析 + 用户人工确认",
            attachment_path=draft.image_reference,
            image_reference=Path(draft.image_reference).name,
            include_in_analysis_packet=False,
            llm_usage="context_only",
        ))
        now = datetime.utcnow()
        draft.confirmed_at = now
        draft.saved_transaction_batch_id = batch["batch_id"]
        draft.saved_snapshot_id = resulting_snapshot_id
        draft.parse_status = "saved_as_portfolio_snapshot" if resulting_snapshot_id else "user_confirmed"
        draft.ocr_status = "user_confirmed"
        draft.needs_user_confirmation = False
        for row in draft.transaction_rows_draft:
            row.confirmed_by_user = True
        self._write_draft(draft)
        return {
            "draft": draft,
            "state": state,
            "transaction_batch": batch,
            "operation_samples": operation_samples,
        }

    def _confirm_holdings_draft(self, draft: PortfolioImportDraft) -> dict[str, Any]:
        previous_snapshot = self.portfolio_service.load_snapshot()
        previous_positions = {
            compact_symbol(position.symbol): position
            for position in previous_snapshot.positions
        }
        now = datetime.utcnow()
        positions: list[PortfolioPositionInput] = []
        errors: list[str] = []
        confirmed_source_name = (
            "同花顺持仓截图 + 云端视觉解析 + 用户人工确认"
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
            previous = previous_positions.get(compact_symbol(row.normalized_symbol or ""))
            has_draft_semantics = bool(
                row.directions
                or row.theme_tags
                or row.primary_theme
                or row.risk_flags
            )
            directions = (
                row.directions
                or row.theme_tags
                or (list(previous.directions) if previous else [])
            )
            theme_tags = (
                row.theme_tags
                or (list(previous.theme_tags) if previous else [])
            )
            primary_theme = (
                row.primary_theme
                or (previous.primary_theme if previous else None)
            )
            risk_flags = (
                row.risk_flags
                or (list(previous.risk_flags) if previous else [])
            )
            pos_data = {
                "symbol": row.normalized_symbol or "",
                "name": row.normalized_name or row.raw_name_text,
                "quantity": float(row.quantity or 0),
                "available_quantity": row.available_quantity,
                "avg_cost": float(row.avg_cost or 0),
                "broker_screenshot_price": row.broker_screenshot_price,
                "broker_screenshot_price_source": confirmed_source_name,
                "broker_screenshot_price_time": None,
                "broker_screenshot_market_value": row.broker_screenshot_market_value,
                "broker_screenshot_unrealized_pnl": row.broker_screenshot_unrealized_pnl,
                "broker_screenshot_unrealized_pnl_pct": row.broker_screenshot_unrealized_pnl_pct,
                "source_type": "manual_account",
                "source_name": confirmed_source_name,
                "import_draft_id": draft.draft_id,
                "confirmed_by_user": True,
                "position_role": row.position_role or (previous.position_role if previous else "observation"),
                "primary_theme": primary_theme,
                "theme_tags": theme_tags,
                "directions": directions,
                "risk_flags": risk_flags,
                "semantic_classification_status": (
                    "user_confirmed"
                    if has_draft_semantics
                    else previous.semantic_classification_status if previous else "unconfirmed"
                ),
                "semantic_classification_source": (
                    "portfolio_screenshot_user_confirmation"
                    if has_draft_semantics
                    else previous.semantic_classification_source if previous else None
                ),
                "semantic_classification_confirmed_at": (
                    now
                    if has_draft_semantics
                    else previous.semantic_classification_confirmed_at if previous else None
                ),
                "user_plan": row.user_plan or (previous.user_plan if previous else ""),
                "invalid_condition": (
                    row.invalid_condition
                    if row.invalid_condition is not None
                    else previous.invalid_condition if previous else None
                ),
                "target_max_weight": (
                    row.target_max_weight
                    if row.target_max_weight is not None
                    else previous.target_max_weight if previous else None
                ),
                "asset_type": previous.asset_type if previous else "stock",
                "ipo_status": previous.ipo_status if previous else None,
                "issue_price": previous.issue_price if previous else None,
                "expected_list_date": previous.expected_list_date if previous else None,
                "notes": previous.notes if previous else None,
            }
            from app.portfolio.service import _sync_legacy_fields
            _sync_legacy_fields(pos_data)
            positions.append(PortfolioPositionInput(**pos_data))
        if errors:
            raise ValueError("；".join(errors))
        confirmed = draft.account_summary_draft.user_confirmed_values
        snapshot_input = PortfolioSnapshotInput(
            portfolio_id=previous_snapshot.portfolio_id,
            snapshot_time=now,
            total_assets=confirmed.get("total_assets") or draft.account_summary_draft.total_assets_ocr,
            cash_available=float(confirmed.get("cash_available") or draft.account_summary_draft.cash_available_ocr or 0),
            account_actual_total_cost=previous_snapshot.account_actual_total_cost,
            repo_amount=float(confirmed.get("repo_amount") or draft.account_summary_draft.repo_amount_ocr or 0),
            repo_available_date=previous_snapshot.repo_available_date,
            notes=previous_snapshot.notes,
            source_type="broker_screenshot_cloud_parsed_user_confirmed"
            if draft.parser_provider == "volcengine_ark_vision"
            else "broker_screenshot_confirmed",
            source_name=confirmed_source_name,
            draft_id=draft.draft_id,
            confirmed_at=now,
            risk_limits=previous_snapshot.risk_limits,
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
        operation_samples = self.operation_capture() if self.operation_capture else []
        return {
            "draft": draft,
            "state": state,
            "operation_samples": operation_samples,
        }


def _capture_operation_samples() -> list[dict[str, Any]]:
    from app.agent_review.outcomes import capture_portfolio_actions

    return capture_portfolio_actions()


portfolio_import_service = PortfolioImportService(operation_capture=_capture_operation_samples)
