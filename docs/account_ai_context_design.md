# Account AI Context Design

## Purpose

Account-level analysis belongs to the future personal investment dashboard. Single-stock pages remain focused on one symbol and may only show the current account holding relationship as read-only context.

`AccountAnalysisContext` is a local structured input derived from the saved portfolio snapshot and Portfolio Packet. It does not call an external LLM.

## Valuation Basis

Account facts separate saved snapshot valuation from current quote estimate:

- `snapshot_valuation`: saved local account values at snapshot time.
- `current_quote_estimate`: current system-enriched holding market value plus cash/repo carried from the saved snapshot.

Current portfolio weights, official theme exposure weights, related tag observation weights, cash ratio, and repo ratio use `current_quote_estimate.estimated_total_assets_using_current_quotes` as the denominator. This estimate is not broker-verified realtime total assets.

## Input Structure

- `meta`: generation time, portfolio snapshot id, portfolio time, quote-time boundary, and privacy boundary.
- `account_facts`: account totals and holdings count.
- `holdings`: symbol, name, quantity, average cost, market value, unrealized PnL, weight, confirmed `primary_theme`, confirmed `theme_tags`, confirmed `position_role`, external driver profile id, and data status.
- `official_theme_exposure`: additive exposure using only confirmed `primary_theme`.
- `related_theme_observations`: non-additive observations from `theme_tags`, including composite exposure notes.
- `external_driver_summary`: compact shared driver observations with factor id, display name, associated symbols, data status, reason, and boundary.
- `data_gaps`: unclassified holdings, unconfirmed roles, unavailable quote/fact/driver data, and other missing information.
- `ai_analysis_boundary`: intended use, inactive rules, privacy boundary, and no-execution limits.

## Layering

Hard facts, account facts, external drivers, user-confirmed semantics, and missing information are separate layers. `primary_theme` is the only formal theme attribution used for exposure sums. `theme_tags` are context only and must not be added into asset weights.

System suggestions are not account facts. They become user-confirmed semantics only after the user saves them.

Related tag observations are calculated strictly from user-confirmed `theme_tags`. `AI_THEME_ETF` is not implicitly merged into `AI_PCB`. A broader `AI_RELATED` concept may be offered later only as a suggestion requiring user confirmation.

## Inactive Rules

The following are not current AI decision rules:

- Single-position limit.
- Primary-theme limit.
- Cash floor.
- Repo cash-equivalent policy.

The structured inactive rule ids are `single_position_limit`, `primary_theme_limit`, `cash_floor`, and `repo_cash_equivalent_policy`. Until the user confirms those rules, downstream AI must not treat them as verified discipline or use them to judge concentration, cash sufficiency, repo cash-equivalent treatment, or trade action validity.

Confirmed `position_role = observation` is a valid user role. It means the user marked the holding as observational context; the system must not infer a trade plan, offensive/defensive intent, or missing role from it.

## Privacy Boundary

Account context may contain real holdings, costs, cash, and user plans. It is generated locally. A future dashboard may use it only after explicit user action, and external sharing must remain user-initiated.

## Future Dashboard Output Shape

The future dashboard may present:

- account fact summary;
- theme structure and composite exposure observations;
- holdings that need focused tracking;
- evidence gaps or information to supplement;
- candidate action directions and pre-check conditions;
- items that must not be executed automatically.

It must not issue automatic buy, sell, add, reduce, or unified command conclusions.
