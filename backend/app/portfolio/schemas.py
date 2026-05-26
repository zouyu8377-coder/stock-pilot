from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


DEFAULT_PORTFOLIO_ID = "local_default"
DEFAULT_THEME_TAGS = [
    "AI_PCB",
    "AI_THEME_ETF",
    "METAL_RESOURCE",
    "GOLD",
    "TUNGSTEN",
    "CASH_EQUIVALENT",
    "BROAD_INDEX",
    "CASH",
    "REPO",
    "HIGH_VOLATILITY",
    "COMPOSITE_EXPOSURE",
    "OTHER",
    "UNCLASSIFIED",
]
DEFAULT_PRIMARY_THEMES = [
    "AI_PCB",
    "AI_THEME_ETF",
    "METAL_RESOURCE",
    "GOLD",
    "TUNGSTEN",
    "CASH_EQUIVALENT",
    "OTHER",
    "UNCLASSIFIED",
]


class PositionRole(str, Enum):
    CORE = "core"
    TREND = "trend"
    DEFENSIVE = "defensive"
    HEDGE = "hedge"
    OBSERVATION = "observation"
    SHORT_TERM = "short_term"
    CASH_EQUIVALENT = "cash_equivalent"
    UNCLASSIFIED = "unclassified"


class TradeSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class ManualEvidenceReliability(str, Enum):
    A_MANUAL_VERIFIED = "A_manual_verified"
    B_MANUAL_STRUCTURED = "B_manual_structured"
    C_MANUAL_OBSERVATION = "C_manual_observation"


class ManualEvidenceType(str, Enum):
    SHAREHOLDER_COUNT_MANUAL = "shareholder_count_manual"
    UNLOCK_EVENT_MANUAL = "unlock_event_manual"
    INTRADAY_SCREENSHOT = "intraday_screenshot"
    MANUAL_MARKET_OBSERVATION = "manual_market_observation"
    TRADE_PLAN = "trade_plan"
    ANNOUNCEMENT_EXCERPT_MANUAL = "announcement_excerpt_manual"
    SURVEY_EXCERPT_MANUAL = "survey_excerpt_manual"
    MACRO_OBSERVATION_MANUAL = "macro_observation_manual"


class RiskLimits(BaseModel):
    max_position_weight: float = 35.0
    max_theme_weight: float = 50.0
    min_cash_ratio: float = 5.0


class PortfolioPositionInput(BaseModel):
    symbol: str
    name: str = ""
    quantity: float
    available_quantity: float | None = None
    avg_cost: float
    broker_screenshot_price: float | None = None
    broker_screenshot_price_source: str | None = None
    broker_screenshot_price_time: datetime | None = None
    broker_screenshot_market_value: float | None = None
    broker_screenshot_unrealized_pnl: float | None = None
    broker_screenshot_unrealized_pnl_pct: float | None = None
    source_type: str = "manual_account"
    source_name: str | None = None
    import_draft_id: str | None = None
    confirmed_by_user: bool = False
    position_role: PositionRole = PositionRole.OBSERVATION
    theme_tags: list[str] = Field(default_factory=list)
    primary_theme: str | None = None
    semantic_classification_status: str = "unconfirmed"
    semantic_classification_source: str | None = None
    semantic_classification_confirmed_at: datetime | None = None
    user_plan: str = ""
    invalid_condition: str | None = None
    target_max_weight: float | None = None
    notes: str | None = None


class PortfolioPosition(PortfolioPositionInput):
    market_price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None
    unrealized_pnl_pct: float | None = None
    price_source: str = ""
    system_quote_price: float | None = None
    system_quote_retrieved_at: datetime | None = None
    system_quote_market_time: datetime | None = None
    quote_time_status: str = "unavailable"
    data_status: str = "available"
    missing_data: list[str] = Field(default_factory=list)


class PortfolioSnapshotInput(BaseModel):
    snapshot_id: str = Field(default_factory=lambda: f"portfolio_snapshot_{uuid4().hex}")
    portfolio_id: str = DEFAULT_PORTFOLIO_ID
    snapshot_time: datetime = Field(default_factory=datetime.utcnow)
    total_assets: float | None = None
    cash_available: float = 0
    repo_amount: float = 0
    repo_available_date: date | None = None
    notes: str | None = None
    source_type: str = "manual_account"
    source_name: str | None = None
    draft_id: str | None = None
    confirmed_at: datetime | None = None
    risk_limits: RiskLimits = Field(default_factory=RiskLimits)
    positions: list[PortfolioPositionInput] = Field(default_factory=list)


class PortfolioSnapshot(PortfolioSnapshotInput):
    positions: list[PortfolioPosition] = Field(default_factory=list)


class ThemeExposure(BaseModel):
    theme: str
    market_value: float
    weight_pct: float
    symbols: list[str] = Field(default_factory=list)


class PortfolioMetrics(BaseModel):
    total_assets: float
    total_market_value: float
    cash_available: float
    repo_amount: float
    snapshot_total_assets: float | None = None
    snapshot_cash_available: float | None = None
    snapshot_repo_amount: float | None = None
    estimated_total_assets_using_current_quotes: float
    estimated_position_weight_pct: float
    estimated_cash_weight_pct: float
    estimated_repo_weight_pct: float
    valuation_basis: str = "current_quote_estimate"
    cash_ratio_pct: float
    repo_ratio_pct: float
    invested_ratio_pct: float
    position_weights: list[dict[str, Any]] = Field(default_factory=list)
    pnl_contributors: list[dict[str, Any]] = Field(default_factory=list)
    primary_theme_exposures: list[ThemeExposure] = Field(default_factory=list)
    risk_tag_exposures: list[ThemeExposure] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    total_cost_basis: float | None = None
    total_unrealized_pnl: float | None = None
    total_unrealized_pnl_pct: float | None = None
    total_unrealized_pnl_status: str = "unavailable"
    excluded_symbols: list[str] = Field(default_factory=list)
    composite_exposure_notes: list[str] = Field(default_factory=list)
    missing_data: list[dict[str, Any]] = Field(default_factory=list)


class PortfolioState(BaseModel):
    snapshot: PortfolioSnapshot
    metrics: PortfolioMetrics
    supported_theme_tags: list[str] = Field(default_factory=lambda: DEFAULT_THEME_TAGS.copy())
    supported_primary_themes: list[str] = Field(default_factory=lambda: DEFAULT_PRIMARY_THEMES.copy())
    supported_position_roles: list[str] = Field(default_factory=lambda: [item.value for item in PositionRole])


class HoldingSemanticSuggestion(BaseModel):
    symbol: str
    suggested_primary_theme: str | None = None
    suggested_theme_tags: list[str] = Field(default_factory=list)
    suggested_position_role: PositionRole = PositionRole.OBSERVATION
    source: str = "system_symbol_mapping"
    source_detail: str | None = None
    requires_user_confirmation: bool = True
    note: str | None = None


class HoldingSemanticUpdate(BaseModel):
    symbol: str
    primary_theme: str | None = None
    theme_tags: list[str] = Field(default_factory=list)
    position_role: PositionRole = PositionRole.OBSERVATION


class HoldingSemanticBatchUpdate(BaseModel):
    updates: list[HoldingSemanticUpdate] = Field(default_factory=list)


class ManualEvidenceCreate(BaseModel):
    symbol: str | None = None
    evidence_type: ManualEvidenceType
    title: str
    value: Any = None
    text: str = ""
    as_of_time: datetime | None = None
    as_of_date: date | None = None
    source: str = "user_manual_entry"
    reliability: ManualEvidenceReliability = ManualEvidenceReliability.B_MANUAL_STRUCTURED
    llm_usage: str = "fact_with_limit"
    attachment_path: str | None = None
    image_reference: str | None = None
    notes: str | None = None
    include_in_analysis_packet: bool = True
    holder_num: int | None = None
    end_date: date | None = None
    announcement_date: date | None = None
    change_from_previous: float | None = None
    screenshot: str | None = None


class ManualEvidenceRecord(ManualEvidenceCreate):
    evidence_id: str = Field(default_factory=lambda: f"manual_{uuid4().hex}")
    recorded_at: datetime = Field(default_factory=datetime.utcnow)


class ManualEvidenceIncludeUpdate(BaseModel):
    include_in_analysis_packet: bool


class TradeSimulationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    side: TradeSide = Field(alias="action")
    symbol: str
    name: str = ""
    quantity: float | None = None
    amount: float | None = None
    estimated_price: float
    reason: str = Field(default="", alias="trading_reason")
    planned: bool = Field(default=True, alias="is_planned_trade")
    position_role: PositionRole = PositionRole.OBSERVATION
    theme_tags: list[str] = Field(default_factory=list)
    primary_theme: str | None = None


class TradeSimulationResult(BaseModel):
    before: PortfolioMetrics
    after: PortfolioMetrics
    trade: dict[str, Any]
    deltas: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
