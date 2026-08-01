from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Confidence = Literal["high", "medium", "low"]
Priority = Literal["high", "medium", "low"]
EvidenceType = Literal[
    "market_snapshot",
    "rotation",
    "event_outcome",
    "announcement",
    "financial",
    "manual",
]
ChangeType = Literal["new", "strengthened", "weakened", "resolved", "unchanged"]
FocusAction = Literal["verify", "monitor", "review_risk", "wait", "no_action"]


class ReviewDataStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usable: bool
    stale_evidence_refs: list[str] = Field(default_factory=list)
    missing_evidence_refs: list[str] = Field(default_factory=list)
    summary: str = Field(max_length=180)


class ReviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    subject: str = Field(max_length=40)
    conclusion: str = Field(max_length=160)
    confidence: Confidence
    evidence_refs: list[str] = Field(default_factory=list, max_length=5)
    counter_evidence_refs: list[str] = Field(default_factory=list, max_length=3)
    action_semantics: str = Field(max_length=120)
    invalidation_conditions: list[str] = Field(default_factory=list, max_length=2)


class VerificationTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: Priority
    subject: str = Field(max_length=40)
    task: str = Field(max_length=120)
    reason: str = Field(max_length=120)
    target_symbols: list[str] = Field(default_factory=list, max_length=5)
    evidence_type: EvidenceType = "manual"
    missing_evidence: list[str] = Field(default_factory=list, max_length=4)
    success_criteria: str = Field(default="", max_length=120)


class ReviewChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(max_length=40)
    change_type: ChangeType
    summary: str = Field(max_length=120)
    evidence_refs: list[str] = Field(default_factory=list, max_length=4)


class DecisionFocus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: Priority
    subject: str = Field(max_length=40)
    action: FocusAction
    reason: str = Field(max_length=120)
    evidence_refs: list[str] = Field(default_factory=list, max_length=4)


class DailyOperationReflection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=1, max_length=80)
    symbol: str = Field(pattern=r"^\d{6}$")
    name: str = Field(max_length=30)
    action_type: Literal["buy", "sell"]
    operation_summary: str = Field(max_length=120)
    strategy_reflection: str = Field(max_length=160)
    next_review_condition: str = Field(max_length=120)
    evidence_refs: list[str] = Field(default_factory=list, min_length=1, max_length=2)


class DailyOperationReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trading_date: str = ""
    action_count: int = 0
    items: list[DailyOperationReflection] = Field(default_factory=list, max_length=3)
    overall_reflection: str = Field(default="当日没有需要复盘的已确认操作。", max_length=220)


class WeeklyOperationReflection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(pattern=r"^\d{6}$")
    name: str = Field(max_length=30)
    operation_summary: str = Field(max_length=140)
    strategy_reflection: str = Field(max_length=160)
    next_review_condition: str = Field(max_length=120)
    evidence_refs: list[str] = Field(default_factory=list, min_length=1, max_length=3)


class WeeklyOperationReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_start: str = ""
    window_end: str = ""
    trading_days: list[str] = Field(default_factory=list, max_length=5)
    action_count: int = 0
    symbol_count: int = 0
    items: list[WeeklyOperationReflection] = Field(default_factory=list, max_length=3)
    overall_reflection: str = Field(default="本周期没有需要复盘的已确认操作。", max_length=220)


class DailyReviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str = Field(max_length=80)
    data_status: ReviewDataStatus
    opportunities: list[ReviewItem] = Field(default_factory=list, max_length=3)
    risks: list[ReviewItem] = Field(default_factory=list, max_length=3)
    watch_items: list[ReviewItem] = Field(default_factory=list, max_length=3)
    verification_tasks: list[VerificationTask] = Field(default_factory=list, max_length=6)
    changes_since_previous_review: list[ReviewChange] = Field(default_factory=list, max_length=5)
    decision_focus: list[DecisionFocus] = Field(default_factory=list, max_length=3)
    operation_review_period: Literal["daily", "weekly"] = "daily"
    daily_operation_review: DailyOperationReview = Field(default_factory=DailyOperationReview)
    weekly_operation_review: WeeklyOperationReview = Field(default_factory=WeeklyOperationReview)
    summary: str = Field(max_length=240)
