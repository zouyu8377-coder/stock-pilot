# Account AI Context Design

## Purpose

Account-level analysis belongs to the future personal investment dashboard. Single-stock pages remain focused on one symbol and may only show the current account holding relationship as read-only context.

`AccountAnalysisContext` is a local structured input derived from the saved portfolio snapshot and Portfolio Packet. It does not call an external LLM.

## Input Structure

- `meta`: generation time, portfolio snapshot id, portfolio time, quote-time boundary, and privacy boundary.
- `account_facts`: account totals and holdings count.
- `holdings`: symbol, name, quantity, average cost, market value, unrealized PnL, weight, confirmed `primary_theme`, confirmed `theme_tags`, confirmed `position_role`, external driver profile id, and data status.
- `official_theme_exposure`: additive exposure using only confirmed `primary_theme`.
- `related_theme_observations`: non-additive observations from `theme_tags`, including composite exposure notes.
- `external_driver_summary`: shared external-driver summary and de-duplicated driver facts.
- `data_gaps`: unclassified holdings, unconfirmed roles, unavailable quote/fact/driver data, and other missing information.
- `ai_analysis_boundary`: intended use, inactive rules, privacy boundary, and no-execution limits.

## Layering

Hard facts, account facts, external drivers, user-confirmed semantics, and missing information are separate layers. `primary_theme` is the only formal theme attribution used for exposure sums. `theme_tags` are context only and must not be added into asset weights.

System suggestions are not account facts. They become user-confirmed semantics only after the user saves them.

## Inactive Rules

The following are not current AI decision rules:

- Single-position limit.
- Theme exposure limit.
- Cash floor.
- Repo cash-equivalent policy.

If existing Portfolio Packet placeholder reminders remain, they must be marked as system placeholders, unconfirmed by the user, and inactive for AI reasoning.

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
