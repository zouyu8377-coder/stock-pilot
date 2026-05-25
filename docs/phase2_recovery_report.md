# Phase 2 Recovery Report

Last updated: 2026-05-24

## 1. Repository Baseline

- Branch: `master`
- Upstream: up to date with `origin/master`
- Working tree: dirty before this recovery pass.
- Staged changes: none.
- Pre-existing modified files: `.gitignore`, `backend/.env.example`, `backend/.gitignore`, `backend/app/company_profile/providers/tushare_provider.py`, `backend/app/core/config.py`, `backend/app/main.py`, `backend/requirements.txt`, `backend/scripts/bootstrap_stock_metadata.py`, `frontend/src/App.vue`, `frontend/src/api/client.ts`.
- Pre-existing untracked phase files include: `backend/app/evidence/`, `backend/app/analysis_packet/`, `backend/app/facts/`, `backend/app/tushare/`, `backend/app/portfolio/`, `backend/app/api/facts.py`, `backend/app/api/snapshot.py`, `backend/app/api/portfolio.py`, `backend/tests/`, `frontend/src/components/AutoFactsPanel.vue`, `frontend/src/components/PortfolioPanel.vue`, `docs/stage0_foundation_notes.md`, `docs/tushare_capability_report.*`, `scripts/`.

## 2. Stage 0 Status

Status: partially complete, usable with minor risks.

- `EvidenceItem` exists in `backend/app/evidence/schemas.py` with explicit `auto_fact`, `auto_signal`, `manual_account`, `manual_evidence`, and `system_hypothesis` categories.
- `AnalysisSnapshot` supports `evidence_items`, `missing_data`, `system_hypotheses`, `analysis_scope`, `target_symbols`, `portfolio_as_of`, and `version`.
- Validators prevent `system_hypothesis` from being treated as unrestricted fact.
- Risk: schema is versioned as `analysis_snapshot.v0`; future compatibility should stay additive.

## 3. Stage 1 Status

Status: partially complete, currently testable.

- Tushare cache/client/facts modules exist for ETF facts, dragon-tiger events, announcements, and surveys.
- Fact services construct `EvidenceItem` records and are wired through `/api/facts/*`.
- Single-stock snapshot builder appends Stage 1 fact evidence.
- Risk: Tushare availability depends on backend-only `TUSHARE_TOKEN`; without it, low-frequency facts must degrade gracefully.

## 4. Stage 2 Completion Matrix

| Item | Current status | Notes |
| --- | --- | --- |
| Portfolio snapshot persistence | Exists and usable | JSON storage under `PORTFOLIO_DATA_DIR`; no database introduced. |
| Cash/repo fields | Exists and usable | `cash_available`, `repo_amount`, `repo_available_date`, `notes` present. |
| Holding details | Exists but incomplete | Core fields present; pre-recovery code used cost fallback when quote missing. |
| Market price enrichment | Exists but incomplete | Reuses `collector.get_quote`; must not fabricate values on quote failure. |
| Primary theme exposure | Exists and usable | Uses `primary_theme` for unique attribution. |
| Risk tag exposure | Exists and usable | Separate risk grouping exists; needs clear non-additive wording. |
| Composite exposure notes | Exists and usable | Emits multi-tag notes. |
| Portfolio metrics | Exists and usable | Total assets, market value, weights, cash/repo, PnL ranking exist. |
| Rule reminders | Exists but incomplete | String warnings exist; must also enter `system_hypotheses`. |
| Trade simulation | Exists but incomplete | Buy/sell simulation exists; needs sell availability validation and input aliases. |
| Manual evidence | Exists and usable | Add/list/delete implemented; update not implemented this phase. |
| Portfolio AnalysisSnapshot | Exists but incomplete | Evidence items generated; warnings not yet emitted as `system_hypotheses`. |
| Frontend phase2 panel | Exists and buildable | Minimal portfolio, evidence, simulation UI exists; UI polish deferred. |

## 5. Bugs and Gaps Found

- Missing realtime quotes were converted to `manual_fallback` using average cost, which could fabricate market value and PnL.
- Holding schema did not expose explicit `data_status` or per-position `missing_data`.
- Sell simulation did not reject quantity above `available_quantity`.
- Trade simulation input used `side`, `reason`, and `planned`; requested field names include `action`, `trading_reason`, and `is_planned_trade`.
- Portfolio warnings were not represented as `EvidenceItem` records in `AnalysisSnapshot.system_hypotheses`.
- Stage 2 tests covered only three scenarios; required edge cases were incomplete.

## 6. Planned Recovery Changes This Round

- Keep the existing portfolio service and JSON storage style.
- Add explicit position data status and missing-data reporting.
- Stop computing market value and PnL when price, quantity, or cost is invalid.
- Add sell availability validation and cash-overrun risk notes for simulation.
- Accept conservative aliases for requested simulation input names.
- Convert portfolio rule warnings into `system_hypothesis` evidence items.
- Expand backend tests for empty portfolio, composite exposure, missing price, limits, simulation boundaries, manual evidence, and Stage 0/1 compatibility.
- Update frontend API/types minimally for added fields.

## 7. Out of Scope This Round

- Brokerage sync, automatic orders, full ledger accounting, automatic shareholder/unlock feeds, margin/moneyflow/macros, PDF parsing, RAG, markdown export, automatic LLM sending, backtesting, scoring calibration, or large UI redesign.

## 8. Baseline Verification

- `cd backend; python -m pytest`: passed, 17 tests.
- `cd backend; python -m compileall app`: passed.
- `cd frontend; npm run build`: passed.

## 9. Recovery Changes Applied

Key files touched or completed in this pass:

- `backend/app/portfolio/schemas.py`
- `backend/app/portfolio/service.py`
- `backend/app/api/portfolio.py`
- `backend/tests/test_stage2_portfolio.py`
- `frontend/src/api/client.ts`
- `docs/phase2_recovery_report.md`
- `docs/phase2_acceptance_checklist.md`

Existing phase files confirmed as part of the recovered implementation:

- `backend/app/evidence/schemas.py`
- `backend/app/analysis_packet/snapshot_builder.py`
- `backend/app/facts/*`
- `backend/app/tushare/*`
- `backend/app/api/facts.py`
- `backend/app/api/snapshot.py`
- `frontend/src/components/PortfolioPanel.vue`
- `frontend/src/components/AutoFactsPanel.vue`

## 10. Completed Items

- Portfolio snapshot JSON persistence for cash, repo, risk limits, notes, and positions.
- Holding enrichment through the existing realtime quote collector.
- Explicit per-position `data_status` and `missing_data`.
- Missing price no longer fabricates market value, unrealized PnL, or PnL percentage.
- Primary-theme unique attribution remains separate from multi-tag risk observations.
- Composite exposure notes remain non-additive and informational.
- Rule reminders are available in metrics and are also converted to `system_hypothesis` evidence in portfolio snapshots.
- Read-only trade simulation supports `buy` and `sell`, amount-derived quantity, requested aliases `action`, `trading_reason`, and `is_planned_trade`, cash-overrun reminders, and sell availability validation.
- Manual evidence add/list/delete remains wired to unified EvidenceItem conversion.
- Minimal frontend typing updated for nullable valuation fields and missing-data payloads.

## 11. Remaining Limitations

- Manual evidence update is not implemented; add/list/delete are available.
- Frontend is intentionally minimal and still needs later UX polish, especially around displaying missing price status and simulation validation errors.
- Default risk limits are only placeholders for user discipline. They must not be treated as the user's confirmed trading policy.
- Realtime quote quality depends on the existing easyquotation provider; missing/failed quotes are surfaced rather than replaced.
- No broker sync, order execution, ledger, automatic shareholder/unlock feeds, export, RAG, or external LLM sending was added.

## 12. Data Semantics

- `manual_account`: portfolio snapshot, positions, cash, repo, user plans, invalid conditions.
- `manual_evidence`: user-entered shareholder counts, intraday observations, screenshots/references, manual excerpts, and macro observations.
- `system_hypothesis`: rule reminders and concentration/cash warnings, always reliability `H` and LLM usage `hypothesis_only`.
- `auto_fact` and `auto_signal`: Stage 0/1 automatic evidence remains separate and was not merged with account data.

## 13. Final Verification

- `cd backend; python -m pytest`: passed, 22 tests.
- `cd backend; python -m compileall app`: passed.
- `cd frontend; npm run build`: passed.
- FastAPI smoke test with `TestClient`: `/api/portfolio`, `/api/portfolio/manual-evidence`, `/api/portfolio/analysis-snapshot`, and `/api/portfolio/simulate` returned 200.

## 14. Before Phase 3

- User should confirm real risk limits: max single position, max theme exposure, minimum cash ratio, and whether repo is considered cash-equivalent for their own workflow.
- User should verify the local portfolio data in `backend/data/portfolio/` if present, because this pass did not overwrite or delete user data.
- Phase 3 should start only after Stage 2 API behavior and minimal frontend entry points are accepted.
