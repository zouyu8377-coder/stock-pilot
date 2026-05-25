# Phase 3.6D Account Semantics Before Dashboard Report

## Baseline

- Starting branch: `feature/cloud-vision-portfolio-import`.
- Starting HEAD: `b66d3fc8e7582f9e5b058d67c624e41e5ff264f4`.
- Worktree at start: mixed and not clean.
- Closure audit: see `docs/phase3_6d_baseline_closure_report.md`.

## Scope

This phase prepares account semantics before dashboard development. It does not implement a dashboard, account-level AI calls, OCR, cloud vision parsing, screenshot import UI, broker sync, moneyflow, margin financing, backtesting, or phase 4/5 work.

## Product Boundary

The single-stock page remains responsible for one-symbol evidence research: quote, daily K, facts, auxiliary signals, external drivers, missing data, and Single-stock Packet output. It may show current holding relationship as read-only context.

The portfolio/account area is responsible for local holdings, cash/assets structure, user-confirmed official theme exposure, related theme observations, portfolio external drivers, Portfolio Packet output, and future AccountAnalysisContext input.

Account-level review and AI output belong to the future personal investment dashboard.

## Implemented Changes

- Added persisted semantic fields: `semantic_classification_status`, `semantic_classification_source`, and `semantic_classification_confirmed_at`.
- Added account semantic confirmation endpoints and UI.
- Added reviewed system suggestions for selected symbols, including Zijin's resource/gold composite handling.
- Added local `AccountAnalysisContext`.
- Updated Portfolio Packet with `official_theme_exposure`, `related_theme_observations`, `data_gaps`, and `ai_analysis_boundary`.
- Updated Single-stock Packet to show holding semantics read-only and state the account-analysis boundary.
- Renamed visible packet actions to `生成组合证据包 / Generate Portfolio Packet` and `生成单票证据包 / Generate Stock Packet`.

## Portfolio Packet Behavior

Official theme exposure uses only confirmed `primary_theme`. `theme_tags` are retained as non-additive related observations. If a holding lacks confirmed `primary_theme`, it is reported as a semantic data gap rather than a misleading limit breach.

Existing placeholder reminders are not current AI action rules. Packet reminders are system placeholders, user-unconfirmed, and inactive for AI reasoning.

## AccountAnalysisContext

`AccountAnalysisContext` is generated locally from the saved portfolio snapshot and Portfolio Packet without calling an external LLM. It includes meta, account facts, holdings with confirmed semantics, official theme exposure, related theme observations, external driver summary, data gaps, and AI boundaries.

Inactive current AI rules:

- Single-position limit.
- Theme exposure limit.
- Cash floor.
- Repo cash-equivalent policy.

## Cloud Vision / OCR Status

Screenshot/OCR/cloud vision code already exists in historical commits and is retained as `implemented_but_not_active_in_current_product_flow`.

This closure excluded current uncommitted cloud-provider compatibility increments from the account semantics baseline after creating a full local backup.

## Privacy

No token, `.env`, real screenshot, attachment, real account export, or real generated Packet is included in this phase's docs or tests. Automated tests use synthetic fixtures.

## Verification

- `cd backend && python -m pytest -q`: passed, 54 tests.
- `cd backend && python -m compileall app`: passed.
- `cd frontend && npm run build`: passed.
- API smoke: passed with a temporary synthetic portfolio covering portfolio read, semantic suggestions, semantic update, portfolio reread, Portfolio Packet, Single-stock Packet, AccountAnalysisContext, external driver summary, shared driver de-duplication, unclassified semantic gap, and official primary-theme exposure.
- Browser UI smoke on `http://127.0.0.1:5173`: passed for manual portfolio flow, Portfolio Packet naming, semantic confirmation controls, Single-stock Packet naming, dashboard-boundary copy, no misleading OCR/cloud main-flow entry, and no new dashboard AI entry.

## Next Step

After the baseline commit, the next recommended product step is the personal investment dashboard MVP. The user should first confirm real holdings' `primary_theme`, `theme_tags`, and `position_role` in the page and keep any real Portfolio Packet local and out of Git.
