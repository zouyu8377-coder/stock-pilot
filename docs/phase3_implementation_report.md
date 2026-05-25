# Phase 3 Implementation Report: Analysis Packet v1

Last updated: 2026-05-24

## 1. Read and Verified Before Implementation

- `docs/phase2_recovery_report.md`
- `docs/phase2_acceptance_checklist.md`
- `git status --short`
- `git diff --stat`
- `git diff -- .`
- `backend/app/evidence/schemas.py`
- `backend/app/analysis_packet/snapshot_builder.py`
- `backend/app/portfolio/schemas.py`
- `backend/app/portfolio/service.py`
- `backend/app/api/portfolio.py`
- `backend/app/api/snapshot.py`
- `backend/app/facts/etf_service.py`
- `backend/app/facts/dragon_tiger_service.py`
- `backend/app/facts/disclosure_service.py`
- `frontend/src/api/client.ts`
- `frontend/src/components/PortfolioPanel.vue`
- `frontend/src/components/AutoFactsPanel.vue`
- `frontend/src/components/AnalysisPromptPanel.vue`
- `backend/tests/test_stage0_foundation.py`
- `backend/tests/test_stage1_facts.py`
- `backend/tests/test_stage2_portfolio.py`

Phase 2 reports show the core portfolio, manual evidence, Stage 0 schema, and Stage 1 facts were usable. No blocking Stage 2 data-error fix was required before Phase 3. The existing dirty working tree and untracked Phase 0-2 files were preserved.

## 2. Phase 3 Scope Implemented

Implemented Analysis Packet v1 only:

- Single-stock packet generation.
- Portfolio packet generation.
- Structured JSON packet output.
- Stable Markdown rendering for copy/paste into an external LLM.
- Historical JSON and Markdown save paths under the existing analysis snapshot data root.
- Frontend single-stock entry with preview and copy.
- Frontend portfolio entry with preview and copy.
- Manual evidence include/exclude update endpoint and UI toggle.
- Privacy boundary text: local generation only, no automatic external LLM call, no automatic account or attachment upload.

Not implemented by design: automatic LLM sending, broker sync, order execution, PDF/RAG, moneyflow, margin, macro baskets, backtesting, recommendation scoring, or Phase 4/5 features.

## 3. Added or Modified Files

Added:

- `backend/app/analysis_packet/packet_service.py`
- `backend/app/api/analysis_packet.py`
- `backend/tests/test_phase3_analysis_packet.py`
- `frontend/src/components/AnalysisPacketPanel.vue`
- `docs/phase3_implementation_report.md`

Modified:

- `backend/app/analysis_packet/__init__.py`
- `backend/app/api/portfolio.py`
- `backend/app/main.py`
- `backend/app/portfolio/schemas.py`
- `backend/app/portfolio/service.py`
- `frontend/src/App.vue`
- `frontend/src/api/client.ts`
- `frontend/src/components/PortfolioPanel.vue`

Pre-existing Phase 0-2 modified/untracked files remain in the working tree and were not reverted.

## 4. Single-Stock Packet Data Structure

Top-level shape:

```json
{
  "meta": {
    "packet_id": "packet_xxx",
    "packet_version": "analysis_packet.v1",
    "generated_at": "2026-05-24T...",
    "analysis_scope": "single_stock",
    "target_symbol": "600000",
    "target_name": "Name600000",
    "user_question": null,
    "market_data_as_of": "2026-05-24T...",
    "daily_k_as_of": "2026-05-22",
    "portfolio_as_of": "2026-05-24T...",
    "source_snapshot_id": "snap_xxx"
  },
  "privacy_notice": "...",
  "stock_profile": {},
  "auto_fact": [],
  "auto_signal": [],
  "manual_account": {},
  "manual_evidence": [],
  "system_hypothesis": [],
  "missing_data_and_boundaries": [],
  "llm_questions": []
}
```

The single-stock packet is built from the existing `build_basic_stock_snapshot` output plus the current local portfolio and included manual evidence for that symbol.

## 5. Portfolio Packet Data Structure

Top-level shape:

```json
{
  "meta": {
    "packet_id": "packet_xxx",
    "packet_version": "analysis_packet.v1",
    "generated_at": "2026-05-24T...",
    "analysis_scope": "portfolio",
    "portfolio_id": "local_default",
    "portfolio_as_of": "2026-05-24T...",
    "source_snapshot_id": "snap_xxx"
  },
  "privacy_notice": "...",
  "account_overview": {},
  "positions": [],
  "primary_theme_exposure": [],
  "related_risk_observations": {},
  "rule_reminders": [],
  "manual_evidence": [],
  "auto_fact_summary": [],
  "missing_data_and_boundaries": [],
  "llm_questions": []
}
```

Portfolio exposure uses `primary_theme` for unique additive attribution. `theme_tags` are shown only as related risk observations and include a non-additive boundary. `COMPOSITE_EXPOSURE` and multi-tag positions are surfaced through the existing composite exposure notes.

## 6. Markdown Export Structure Example

Markdown sections are stable and intentionally plain:

```md
# Stock-Pilot Analysis Packet v1 - single_stock

## Privacy and External Sharing Boundary
...

## Packet Metadata
- packet_version: analysis_packet.v1
- analysis_scope: single_stock

## Target Basic Information
...

## Auto Fact
...

## Auto Signal
Auxiliary observations only; these are not factual conclusions or buy/sell instructions.

## Manual Account
...

## Manual Evidence
...

## System Hypothesis and Risk Reminders
System-generated, must be questioned and manually verified.

## Missing Data and Interpretation Boundaries
...

## Neutral Questions for an External LLM
...

No buy/sell recommendation is generated by this packet.
```

The portfolio Markdown swaps in account overview, current holdings, primary theme exposure, related risk observations, rule reminders, manual evidence, and auto fact summary.

## 7. JSON Snapshot Save Method

Packet JSON and Markdown are both saved without overwriting historical exports:

- Single stock: `settings.ANALYSIS_SNAPSHOT_DIR/analysis_packets/single_stock/{symbol}/{packet_id}.json`
- Single stock Markdown: same folder, `{packet_id}.md`
- Portfolio: `settings.ANALYSIS_SNAPSHOT_DIR/analysis_packets/portfolio/{portfolio_id}/{packet_id}.json`
- Portfolio Markdown: same folder, `{packet_id}.md`

Each packet contains `packet_id`, `generated_at`, `analysis_scope`, target symbol or portfolio id, and `packet_version`.

## 8. Manual Evidence Include/Exclude

Manual evidence inclusion is controlled by `include_in_analysis_packet`.

- `true`: converted to EvidenceItem-compatible packet evidence and exported.
- `false`: excluded from packet JSON and Markdown.
- New endpoint: `PATCH /api/portfolio/manual-evidence/{evidence_id}/include`.
- Existing add/list/delete behavior remains.
- Frontend portfolio panel now exposes an Include/Exclude toggle.

Screenshots or attachments are only referenced by fields already present in the manual evidence record. The packet does not claim image OCR or attachment parsing.

## 9. Source, Reliability, and Interpretation Boundaries

Packet evidence uses EvidenceItem-compatible fields:

- `title`
- `category`
- `evidence_type`
- `source`
- `source_endpoint`
- `as_of_time` or `as_of_date`
- `fetched_at` or recorded time through `fetched_at`
- `reliability`
- `llm_usage`
- `interpretation_limit`
- `data_status`
- `payload` or summarized payload

Facts, weak signals, manual account data, manual evidence, and system hypotheses remain separate. System hypotheses use reliability `H` and `hypothesis_only`. Markdown explicitly labels technical indicators as auxiliary observations, not conclusions.

## 10. Privacy and No Automatic External Transfer

Implemented boundaries:

- Packet generation is local backend processing.
- Frontend only previews Markdown/JSON and copies when the user clicks copy.
- No external LLM API is called by the packet feature.
- No account information or manual attachment is uploaded by the packet feature.
- UI warns that exports may include real holdings, cost, cash, plans, and manual evidence.

## 11. Tests and Build Results

Executed:

- `cd backend; python -m pytest` - passed, 26 tests.
- `cd backend; python -m pytest tests/test_phase3_analysis_packet.py` - passed, 4 tests.
- `cd backend; python -m compileall app` - passed.
- `cd frontend; npm run build` - passed.

Warnings observed:

- Existing Pydantic class-based config deprecation.
- Existing/use-site `datetime.utcnow()` deprecation warnings.

## 12. Known Limits

- Real Stage 1 low-frequency facts still depend on backend `TUSHARE_TOKEN`; unavailable facts degrade into missing/unavailable status.
- Portfolio price timestamps use the current local portfolio snapshot time because the existing quote enrichment does not expose a provider quote timestamp.
- Announcement and survey packet entries are indexes unless the user manually records excerpts; no full-text business impact is inferred.
- The frontend remains intentionally minimal and uses the existing Phase 2 panel layout.
- Existing mojibake text in several Phase 0-2 UI/service strings was not broadly corrected because that would be unrelated cleanup.

## 13. Manual Checks Recommended Before Phase 4

- Generate a real single-stock packet for a held stock and verify cost, quantity, weight, user plan, and invalid condition.
- Generate a real single-stock packet for a non-held stock and verify the manual account section says no local holding.
- Generate a real supported ETF packet and verify ETF share/NAV facts appear without trend conclusions.
- Generate a stock packet with dragon-tiger, announcement, or survey indexes and verify boundaries are visible.
- Toggle manual evidence Include/Exclude and verify Markdown changes.
- Generate a portfolio packet and verify cash, repo, primary theme exposure, risk tag observations, and composite notes.
- Confirm the user's real risk limits before relying on rule reminders in later phases.
