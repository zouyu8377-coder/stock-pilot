from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Start(Strict):
    scenario: Literal[
        "evidence_gap", "sufficient", "stale_handoff", "conflicting_evidence",
        "tool_failure", "unavailable", "permission_blocked",
    ] = "evidence_gap"
    mode: Literal["sample", "manual"] = "sample"
    public_market: bool = False
    question: str = Field(default="这份模拟组合的判断是否有充分证据？请核对量价与财报，并指出不能确认的部分。", min_length=1, max_length=2000)


class ToolRequest(Strict):
    tool: str = Field(min_length=1, max_length=40)
    symbols: list[str] = Field(min_length=1, max_length=3)
    topic: Literal["overview", "cashflow"] = "overview"
    reason: str = Field(min_length=1, max_length=500)


class Finding(Strict):
    title: str = Field(min_length=1, max_length=200)
    conclusion: str = Field(min_length=1, max_length=2000)
    reasoning: str = Field(min_length=1, max_length=3000)
    confidence: Literal["high", "medium", "low", "unknown"]
    evidence_refs: list[str] = Field(min_length=1, max_length=20)


class Report(Strict):
    summary: str = Field(min_length=1, max_length=3000)
    findings: list[Finding] = Field(min_length=1, max_length=10)
    unresolved: list[str] = Field(max_length=20)


class AnalystReply(Strict):
    run_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    context_version: int = Field(ge=1)
    context_fingerprint: str = Field(min_length=64, max_length=64)
    response_id: str = Field(min_length=1, max_length=100)
    provider: str = Field(min_length=1, max_length=100)
    action: Literal["request_evidence", "final"]
    requests: list[ToolRequest] = Field(default_factory=list, max_length=3)
    report: Report | None = None


class Revision(Strict):
    revision: int = Field(ge=1)


class Submission(Revision):
    reply: AnalystReply


class Confirmation(Revision):
    preview_digest: str = Field(min_length=64, max_length=64)
