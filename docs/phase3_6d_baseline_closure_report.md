# Phase 3.6D-Closure Baseline Report

## Scope

This closure audits the mixed uncommitted worktree, preserves the manual-account and account-semantics baseline, verifies it, and commits a rollback point before personal investment dashboard work.

This round does not build a dashboard, call external AI, add account-level AI execution, continue OCR, continue Volcengine/Ark vision parsing, add screenshot upload UI, add new data sources, or activate single-position, theme-limit, cash-floor, or repo cash-equivalent decision rules.

User product decision: the current portfolio maintenance flow is pure manual update. Historical OCR/screenshot/cloud-vision code may remain in history, but it is not the active product flow.

## Start State

| Item | Result |
|---|---|
| Start branch | `feature/cloud-vision-portfolio-import` |
| Start HEAD | `b66d3fc8e7582f9e5b058d67c624e41e5ff264f4` |
| Worktree clean at start | No |
| Staged changes at start | None |
| Backup path | `C:\Project\Stock-Pilot_backup_before_dashboard_baseline_20260525_232459` |
| Backup time | `2026-05-25T23:25:10.4620651+08:00` |
| Backup status | Success |
| Sensitive values in report | Not printed |

## Initial Uncommitted Summary

Tracked modified files covered backend portfolio schema/service/API, Analysis Packet, AccountAnalysisContext, frontend portfolio/manual semantics UI, packet button naming, ETF quote/metadata support, tests, and docs.

Untracked files at audit start:

- `backend/app/core/etf_data_updater.py`
- `backend/scripts/bootstrap_etf_metadata.py`
- `docs/account_ai_context_design.md`
- `docs/phase3_6d_acceptance_checklist.md`
- `docs/phase3_6d_account_semantics_pre_dashboard_report.md`

Historical commits already include screenshot/OCR/cloud vision work:

- `1f02688 Add confirm-before-save portfolio screenshot import draft flow`
- `41189e6 Add consent-gated cloud vision parsing for portfolio screenshots`
- `0cc4cc5 Simplify cloud vision import flow and neutralize provider wording`

## File-Level Audit

| Category | Files | Decision |
|---|---|---|
| A. Include in baseline | `backend/app/portfolio/schemas.py`, `backend/app/portfolio/service.py`, `backend/app/api/portfolio.py`, `backend/app/analysis_packet/packet_service.py`, `backend/tests/test_stage2_portfolio.py`, `backend/tests/test_phase3_analysis_packet.py`, `frontend/src/components/PortfolioPanel.vue`, `frontend/src/components/AnalysisPacketPanel.vue`, `frontend/src/api/client.ts`, `frontend/src/App.vue`, docs listed below | Manual account maintenance, semantic confirmation, Packet/account context boundaries, and tests. Include after verification. |
| A. Include in baseline | `backend/app/api/search.py`, `backend/app/api/system.py`, `backend/app/collector/history/base_market_provider.py`, `backend/app/collector/metadata_provider.py`, `backend/app/collector/realtime/easyquotation_provider.py`, `backend/app/collector/router.py`, `backend/app/core/data_update_worker.py`, `backend/app/core/data_updater.py`, `backend/app/core/etf_data_updater.py`, `backend/scripts/bootstrap_etf_metadata.py`, `backend/.gitignore` | ETF metadata/quote/update support used by the manual-account synthetic holdings and future local packet context. Include after verification. |
| B. Historical, not active flow | `backend/app/portfolio/import_service.py`, `backend/app/portfolio/import_schemas.py`, `backend/app/portfolio/ocr_provider.py`, screenshot import API routes already in history, existing Phase 3.6B/3.6C docs/tests | Keep historical code. Do not expand it. Mark as `implemented_but_not_active_in_current_product_flow`. |
| C. Excluded current experiment | Current uncommitted changes to `backend/app/portfolio/ocr_provider.py`, `backend/tests/test_phase3_6b_portfolio_import.py`, and `backend/app/core/config.py` that added extra Volcengine/Ark vision preflight/content-mode compatibility | Backed up first, then excluded from this baseline because they only continue cloud vision compatibility work and are not manual-account dependencies. |
| D. Never commit | `backend/.env`, local tokens/API keys, `backend/data/portfolio/`, `backend/data/analysis_snapshots/`, `backend/data/tushare/`, `backend/data/account_exports/`, uploads, attachments, screenshots, logs, caches, real generated Packets | Must remain ignored and outside Git. |

## Required Answers

1. Current manual holding flow depends on portfolio schemas/service/API, semantic suggestion/update endpoints, frontend manual rows, search/quote helpers, ETF metadata/quote support, and Analysis Packet account context code.
2. The current user-visible portfolio panel no longer shows upload screenshot or cloud vision parsing as a main flow.
3. No active visible OCR/cloud vision entry needs further implementation in this closure. Historical backend routes remain but are not surfaced as the product path.
4. OCR/screenshot/cloud vision exists in historical commits, so it is retained as an inactive legacy module rather than removed by history rewrite.
5. `AccountAnalysisContext` uses saved local facts plus user-confirmed semantics and does not rely on the inactive rules listed below.
6. Planned commit files are the A-category files and these docs.
7. Excluded files are the C-category cloud-vision compatibility increments and all D-category sensitive/local data.

## Manual Account Flow

Manual portfolio maintenance is the active flow:

- edit holding quantity, available quantity, average cost, cash, and repo amount;
- choose or search stock/ETF symbols;
- maintain `primary_theme`;
- maintain `theme_tags`;
- maintain `position_role`;
- save semantic confirmation separately from full snapshot save;
- generate Portfolio Packet;
- generate Single-stock Packet;
- generate local AccountAnalysisContext.

The page copy frames the workflow as manual account maintenance. It does not require screenshots, OCR, or a cloud service to maintain the portfolio.

## Page Boundaries

Portfolio area:

- Button: `生成组合证据包 / Generate Portfolio Packet`
- Responsibility: account holdings, theme structure, external drivers, future account review input.

Single-stock area:

- Button: `生成单票证据包 / Generate Stock Packet`
- Responsibility: one-symbol evidence research; may display holding relationship read-only; account-level analysis belongs to the future dashboard.

No dashboard page and no account-level AI call are introduced in this closure.

## Semantics and Theme Aggregation

Supported persisted fields:

- `primary_theme`
- `theme_tags`
- `position_role`
- `semantic_classification_status`
- `semantic_classification_source`
- `semantic_classification_confirmed_at`

System suggestions are separate from user confirmation. Suggestions are not treated as account facts until the user saves confirmation.

Official theme exposure uses only confirmed `primary_theme`. `theme_tags` remain non-additive related observations. Unclassified holdings produce a semantic data gap, not a limit violation.

Synthetic validation portfolio:

- Zijin Mining -> `METAL_RESOURCE`, tags `METAL_RESOURCE`, `GOLD`, `COMPOSITE_EXPOSURE`
- Luoyang Molybdenum -> `METAL_RESOURCE`
- Hudian -> `AI_PCB`
- Shennan -> `AI_PCB`
- ChiNext AI ETF -> `AI_THEME_ETF`
- Gold ETF -> `GOLD`

Expected result: `METAL_RESOURCE` only sums Zijin/Luoyang, `AI_PCB` only sums Hudian/Shennan, `AI_THEME_ETF` stands alone, `GOLD` only sums Gold ETF, and Zijin's `GOLD` tag does not double count into official gold exposure.

## AccountAnalysisContext Audit

`AccountAnalysisContext` is a local structured input and does not call an external LLM. It includes:

- `meta`
- `account_facts`
- `holdings`
- confirmed `primary_theme`, `theme_tags`, `position_role`
- `official_theme_exposure`
- `related_theme_observations`
- `external_driver_summary`
- `data_gaps`
- `ai_analysis_boundary`

Inactive for current AI reasoning:

- single-position limit reminder;
- theme exposure limit reminder;
- cash floor;
- repo cash-equivalent policy.

Placeholder reminders are marked as unconfirmed system placeholders and inactive for AI reasoning.

Privacy boundary: account context may contain real holdings, costs, cash, and plans. It is generated locally and may only be sent to a configured AI service after explicit user action in a future flow.

## User Follow-Up Before Dashboard

Before relying on real-account theme views in the dashboard, the user must personally confirm for real holdings:

- `primary_theme`
- `theme_tags`
- `position_role`

The user should then generate a new real local Portfolio Packet and confirm the theme structure matches their understanding. That real Packet must not be committed to Git or copied into public reports.

## Privacy and Git Checks

Sensitive path checks and content scanning are recorded after verification.

Paths that must remain ignored include:

- `backend/.env`
- `backend/data/portfolio/`
- `backend/data/analysis_snapshots/`
- `backend/data/tushare/`
- `backend/data/account_exports/`
- uploads, attachments, screenshots, logs, caches, and generated real packets.

## Verification Results

| Check | Result |
|---|---|
| `cd backend && python -m pytest -q` | Passed, 54 tests |
| `cd backend && python -m compileall app` | Passed |
| `cd frontend && npm run build` | Passed |
| API smoke | Passed with temporary synthetic portfolio: portfolio read, semantic suggestions/update, portfolio reread, Portfolio Packet, Single-stock Packet, AccountAnalysisContext, external driver summary, shared driver de-duplication, unclassified semantic gap, official primary-theme exposure |
| Browser smoke | Passed on `http://127.0.0.1:5173`: manual flow, Portfolio Packet button, semantic confirmation area, Single-stock Packet button, no misleading OCR/cloud main-flow entry, no new dashboard AI entry |
| Sensitive scan | Passed: no secret pattern match in planned files; no real account packet/export/screenshot intentionally included |
| `git add -n` preview | Passed; only A-category planned files/docs shown |

## Final Commit

| Item | Result |
|---|---|
| Final branch | `feature/account-semantics-before-dashboard` |
| Baseline commit | This commit: `Add confirmed account semantics before portfolio dashboard`; exact final hash is recorded in the final closure response because writing a commit's own hash into the commit would change that hash. |
| Final `git status --short` | Recorded after commit in final closure response |
| Worktree clean | Recorded after commit in final closure response |
| Recommended dashboard base | `feature/account-semantics-before-dashboard` at the final baseline commit |

## Recommendation Gate

Dashboard MVP should start only after this report is complete, tests and smoke checks pass, privacy checks pass, and the baseline commit exists.
