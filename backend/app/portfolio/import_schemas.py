from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


ImportStatus = Literal[
    "uploaded",
    "ocr_processing",
    "draft_parsed",
    "needs_user_confirmation",
    "user_confirmed",
    "saved_as_portfolio_snapshot",
    "ocr_failed",
    "parse_incomplete",
    "user_rejected",
]


class SymbolCandidate(BaseModel):
    symbol: str
    name: str
    industry: str | None = None
    area: str | None = None
    external_driver_profile_id: str | None = None
    external_driver_mapping_status: str | None = None


class AccountSummaryDraft(BaseModel):
    total_assets_ocr: float | None = None
    cash_available_ocr: float | None = None
    total_market_value_ocr: float | None = None
    total_pnl_ocr: float | None = None
    repo_amount_ocr: float | None = None
    repo_available_date_ocr: str | None = None
    field_confidence: dict[str, float] = Field(default_factory=dict)
    user_confirmed_values: dict[str, Any] = Field(default_factory=dict)


class HoldingRowDraft(BaseModel):
    row_id: str = Field(default_factory=lambda: f"row_{uuid4().hex}")
    raw_symbol_text: str = ""
    raw_name_text: str = ""
    raw_quantity_text: str = ""
    raw_available_quantity_text: str = ""
    raw_avg_cost_text: str = ""
    raw_screenshot_price_text: str = ""
    raw_market_value_text: str = ""
    raw_unrealized_pnl_text: str = ""
    raw_unrealized_pnl_pct_text: str = ""
    normalized_symbol: str | None = None
    normalized_name: str | None = None
    symbol_match_status: str = "unresolved"
    symbol_candidates: list[SymbolCandidate] = Field(default_factory=list)
    external_driver_profile_id: str | None = None
    external_driver_mapping_status: str | None = None
    quantity: float | None = None
    available_quantity: float | None = None
    avg_cost: float | None = None
    broker_screenshot_price: float | None = None
    broker_screenshot_market_value: float | None = None
    broker_screenshot_unrealized_pnl: float | None = None
    broker_screenshot_unrealized_pnl_pct: float | None = None
    row_confidence: float = 0
    validation_warnings: list[str] = Field(default_factory=list)
    requires_user_confirmation: bool = True
    position_role: str | None = None
    primary_theme: str | None = None
    theme_tags: list[str] = Field(default_factory=list)
    suggested_theme_tags: list[str] = Field(default_factory=list)
    user_plan: str = ""
    invalid_condition: str | None = None
    target_max_weight: float | None = None
    confirmed_by_user: bool = False


class PortfolioImportDraft(BaseModel):
    draft_id: str = Field(default_factory=lambda: f"draft_{uuid4().hex}")
    source_type: str = "broker_screenshot"
    source_name: str = "同花顺持仓截图"
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    image_reference: str
    ocr_provider: str = "local_noop"
    ocr_status: ImportStatus = "uploaded"
    ocr_raw_text: str = ""
    parse_status: ImportStatus = "uploaded"
    needs_user_confirmation: bool = True
    screenshot_displayed_time: str | None = None
    account_summary_draft: AccountSummaryDraft = Field(default_factory=AccountSummaryDraft)
    holding_rows_draft: list[HoldingRowDraft] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)
    unrecognized_fields: list[str] = Field(default_factory=list)
    confirmed_at: datetime | None = None
    saved_snapshot_id: str | None = None


class PortfolioImportDraftUpdate(BaseModel):
    account_summary_draft: AccountSummaryDraft | None = None
    holding_rows_draft: list[HoldingRowDraft] | None = None
    parse_warnings: list[str] | None = None

