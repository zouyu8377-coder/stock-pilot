from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class EvidenceCategory(str, Enum):
    AUTO_FACT = "auto_fact"
    AUTO_SIGNAL = "auto_signal"
    MANUAL_ACCOUNT = "manual_account"
    MANUAL_EVIDENCE = "manual_evidence"
    SYSTEM_HYPOTHESIS = "system_hypothesis"


class EvidenceReliability(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    H = "H"
    A_MANUAL_VERIFIED = "A_manual_verified"
    B_MANUAL_STRUCTURED = "B_manual_structured"
    C_MANUAL_OBSERVATION = "C_manual_observation"


class LlmUsage(str, Enum):
    FACT = "fact"
    FACT_WITH_LIMIT = "fact_with_limit"
    WEAK_SIGNAL_ONLY = "weak_signal_only"
    CONTEXT_ONLY = "context_only"
    HYPOTHESIS_ONLY = "hypothesis_only"


class DataStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    STALE = "stale"
    MANUAL_REQUIRED = "manual_required"
    UNSUPPORTED = "unsupported"


class EvidenceType(str, Enum):
    REALTIME_QUOTE = "realtime_quote"
    DAILY_K_SUMMARY = "daily_k_summary"
    TECHNICAL_INDICATOR = "technical_indicator"
    COMPANY_PROFILE = "company_profile"
    DATA_COVERAGE = "data_coverage"
    ETF_SHARE_CHANGE = "etf_share_change"
    DRAGON_TIGER_EVENT = "dragon_tiger_event"
    ANNOUNCEMENT_INDEX = "announcement_index"
    SURVEY_INDEX = "survey_index"
    MARGIN_CHANGE = "margin_change"
    VENDOR_MONEYFLOW = "vendor_moneyflow"
    SHAREHOLDER_COUNT_MANUAL = "shareholder_count_manual"
    UNLOCK_EVENT_MANUAL = "unlock_event_manual"
    PORTFOLIO_POSITION = "portfolio_position"
    PORTFOLIO_CASH = "portfolio_cash"
    TRADE_PLAN = "trade_plan"
    SYSTEM_MARKET_REGIME = "system_market_regime"
    INTRADAY_SCREENSHOT = "intraday_screenshot"
    MANUAL_MARKET_OBSERVATION = "manual_market_observation"
    ANNOUNCEMENT_EXCERPT_MANUAL = "announcement_excerpt_manual"
    SURVEY_EXCERPT_MANUAL = "survey_excerpt_manual"
    MACRO_OBSERVATION_MANUAL = "macro_observation_manual"
    EXTERNAL_DRIVER_FACT = "external_driver_fact"
    EXTERNAL_DRIVER_SIGNAL = "external_driver_signal"


class EvidenceItem(BaseModel):
    evidence_id: str = Field(default_factory=lambda: f"ev_{uuid4().hex}")
    symbol: str | None = None
    evidence_type: EvidenceType
    category: EvidenceCategory
    title: str
    value: Any = None
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str
    source_endpoint: str | None = None
    as_of_time: datetime | None = None
    as_of_date: date | None = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    reliability: EvidenceReliability
    llm_usage: LlmUsage
    interpretation_limit: str | None = None
    freshness_days: int | None = None
    data_status: DataStatus = DataStatus.AVAILABLE
    notes: str | None = None

    @model_validator(mode="after")
    def enforce_usage_boundaries(self) -> "EvidenceItem":
        if self.category == EvidenceCategory.SYSTEM_HYPOTHESIS:
            if self.reliability != EvidenceReliability.H:
                raise ValueError("system_hypothesis evidence must use reliability=H")
            if self.llm_usage in {LlmUsage.FACT, LlmUsage.FACT_WITH_LIMIT}:
                raise ValueError("system_hypothesis evidence cannot be used as fact")

        if self.category == EvidenceCategory.AUTO_SIGNAL and self.llm_usage == LlmUsage.FACT:
            raise ValueError("auto_signal evidence cannot have unrestricted fact usage")

        if self.freshness_days is None:
            anchor = self.as_of_time.date() if self.as_of_time else self.as_of_date
            if anchor:
                self.freshness_days = max((self.fetched_at.date() - anchor).days, 0)
        return self


class AnalysisScope(str, Enum):
    SINGLE_STOCK = "single_stock"
    PORTFOLIO = "portfolio"


class AnalysisSnapshot(BaseModel):
    snapshot_id: str = Field(default_factory=lambda: f"snap_{uuid4().hex}")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    analysis_scope: AnalysisScope
    target_symbols: list[str]
    user_question: str | None = None
    market_data_as_of: datetime | None = None
    daily_k_as_of: date | None = None
    financial_data_as_of: date | None = None
    portfolio_as_of: datetime | None = None
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    missing_data: list[dict[str, Any] | str] = Field(default_factory=list)
    system_hypotheses: list[EvidenceItem] = Field(default_factory=list)
    version: str = "analysis_snapshot.v0"
