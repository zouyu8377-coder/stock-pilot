from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Text = Annotated[str, Field(max_length=2000)]
Symbol = Annotated[str, Field(pattern=r"^\d{6}$")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Start(Strict):
    question: str = Field(default="审视当前账户的实质风险、持仓与观察标的机会，结合技术面、财报与外部环境给出下一步计划。", min_length=1, max_length=4000)
    provider: Literal["codex", "api"] = "codex"
    refresh: bool = True
    consent: bool = False
    max_model_calls: int = Field(default=3, ge=1, le=4)


class EvidenceRequest(Strict):
    tool: Literal["market", "disclosure", "events"]
    symbols: list[Symbol] = Field(min_length=1, max_length=5)
    reason: Text


class Finding(Strict):
    level: Literal["account", "direction", "symbol"]
    target: str = Field(min_length=1, max_length=100)
    action: Literal["hold", "increase", "reduce", "avoid", "watch", "wait"]
    conclusion: Text
    reasoning: str = Field(min_length=1, max_length=5000)
    confidence: Literal["high", "medium", "low", "unknown"]
    confidence_reason: Text
    trigger: Text
    invalidation: Text
    horizon: Text
    evidence_refs: list[Annotated[str, Field(max_length=160)]] = Field(min_length=1, max_length=15)


class ExternalSource(Strict):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(pattern=r"^https://", max_length=2000)
    published_at: str = Field(max_length=80)
    excerpt: Text


class Analysis(Strict):
    context_version: int = Field(ge=1)
    context_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: Literal["request_evidence", "final"]
    summary: Text
    account_state: Literal["stable", "attention", "high_risk", "insufficient_data"]
    requests: list[EvidenceRequest] = Field(max_length=3)
    findings: list[Finding] = Field(max_length=15)
    unresolved: list[Text] = Field(max_length=15)
    lessons: list[Text] = Field(max_length=8)
    external_sources: list[ExternalSource] = Field(max_length=15)


class Confirm(Strict):
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class SettingsUpdate(Strict):
    api_enabled: bool = False
    codex_model: str = Field(default="", max_length=100)
    web_search: bool = True
    auto_apply_verified_holdings: bool = True


class AccountImport(Strict):
    source_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    observed_at: str
    complete: bool
    expected_fingerprint: str
    cash_available: float = Field(ge=0)
    total_market_value: float = Field(ge=0)
    total_assets: float = Field(ge=0)
    positions: list[dict] = Field(max_length=100)
