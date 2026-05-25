# Phase 3.5 Hardening Report

Last updated: 2026-05-25

## Audit Conclusions

1. The two Packet JSON examples shown after Phase 3 were abbreviated summaries, not complete exports.
2. The complete single-stock Packet now has stable sections: `meta`, `basic_information`, `auto_fact`, `auto_signal`, `manual_account`, `manual_evidence`, `system_hypothesis`, `missing_data`, `interpretation_boundaries`, `privacy_notice`, and `suggested_questions_for_external_llm`.
3. The complete portfolio Packet now has stable sections: `meta`, `account_overview`, `holdings`, `primary_theme_exposure`, `related_risk_observations`, `auto_fact_summary`, `manual_evidence`, `system_hypothesis`, `missing_data`, `interpretation_boundaries`, `privacy_notice`, and `suggested_questions_for_external_llm`.
4. Stage 1 facts are aggregated into Packet output. ETF, dragon-tiger, and disclosure/survey coverage either export `auto_fact` evidence or explicit `unavailable` boundary records.
5. `include_in_analysis_packet` controls manual evidence export. Include=true records are exported; include=false records are excluded.
6. Markdown includes privacy notice, source, endpoint, as-of/fetched time, reliability, LLM usage, data status, and interpretation boundary for evidence items.
7. Packet generation does not call external LLM code or the deep-analysis API. Code inspection found no call to `call_llm`, `/deep-analyze`, or attachment upload in packet paths.
8. Default risk reminders are now marked with `risk_parameter_source = system_default_placeholder` and `unconfirmed_by_user = true`.
9. Portfolio snapshot time is no longer exported as quote time. `market_price_as_of` is `null`, with `market_price_time_status = unavailable` and an explicit quote-time boundary.
10. Packet Markdown and generated acceptance samples were checked for common mojibake markers. Historical mojibake remains in unrelated Phase 0-2 UI/service strings and is deferred.

## Blocking Fixes Completed

- Removed the misleading `price_as_of = portfolio snapshot time` mapping from portfolio Packet holdings.
- Added explicit quote-time boundary: portfolio snapshot time is not market quote time.
- Added fixed Packet structures even when data is unavailable.
- Added Stage 1 unavailable coverage records so missing Tushare/token data is visible and verifiable.
- Changed ETF evidence category to `auto_fact`; ETF share changes remain bounded facts, not predictions.
- Cleaned Stage 1 fact interpretation strings used in Packet output.
- Forced exported manual evidence to remain `manual_evidence`, including trade-plan-style manual records.
- Added default-risk placeholder disclosure and repo cash-equivalent boundary.
- Generated real code-output acceptance samples under `docs/acceptance_samples/`.

## Allowed Remaining Issues

- Real low-frequency facts depend on `TUSHARE_TOKEN`; without it, samples correctly show unavailable coverage.
- Existing Phase 0-2 UI has mojibake outside Packet-specific controls.
- Frontend remains minimal and is not a Phase 4 redesign.
- Browser automation was blocked from opening localhost during final UI check, but frontend build passed and API paths were smoke-tested.
- The API smoke test created one non-sensitive local manual evidence record titled `smoke include toggle` and set include=false; local data directories must not be committed.

## Single-Stock Packet Structure

Required sections are present:

- `meta`
- `basic_information`
- `auto_fact`
- `auto_signal`
- `manual_account`
- `manual_evidence`
- `system_hypothesis`
- `missing_data`
- `interpretation_boundaries`
- `privacy_notice`
- `suggested_questions_for_external_llm`

ETF sample: `docs/acceptance_samples/phase3_single_etf_packet.*`

Holding sample: `docs/acceptance_samples/phase3_single_holding_packet.*`

## Portfolio Packet Structure

Required sections are present:

- `meta`
- `account_overview`
- `holdings`
- `primary_theme_exposure`
- `related_risk_observations`
- `auto_fact_summary`
- `manual_evidence`
- `system_hypothesis`
- `missing_data`
- `interpretation_boundaries`
- `privacy_notice`
- `suggested_questions_for_external_llm`

Demo portfolio sample: `docs/acceptance_samples/phase3_portfolio_packet.*`

## Stage 1 Fact Verification

- ETF sample for `159382.SZ` generated through Packet code. Current environment lacks usable Tushare access for this call, so Packet exports `etf_share_change` as `auto_fact` with `data_status = unavailable` and the token/config reason.
- Holding sample for `000657` includes dragon-tiger and disclosure/survey coverage. In this environment they are unavailable or empty, and the Packet exports explicit unavailable `auto_fact` boundaries.
- Fact evidence fields preserve category/source/endpoint/as-of/fetched/reliability/llm_usage/interpretation_limit/data_status.

## Manual Evidence Verification

Demo portfolio creates three non-sensitive manual records:

- `shareholder_count_manual`, include=true: exported.
- `manual_market_observation`, include=true: exported.
- `manual_market_observation`, include=false: excluded.

Exported records remain `category = manual_evidence`.

## Quote-Time Fix

Portfolio holdings now export:

- `market_price_as_of: null`
- `market_price_time_status: unavailable`
- `quote_time_boundary: Current quote source does not provide a verifiable quote time; portfolio snapshot time is not market quote time.`

Automated tests verify snapshot time is not mapped into `market_price_as_of`.

## Default Risk and Repo Disclosure

System hypotheses include:

- `risk_parameter_source = system_default_placeholder`
- `unconfirmed_by_user = true`

Markdown includes the warning that concentration/cash reminders may rely on unconfirmed defaults.

Repo is shown separately as `repo_amount` and `repo_weight`; `repo_policy.cash_equivalent_treatment = unconfirmed`.

## Privacy and No External Transfer

Packet API paths build local JSON/Markdown only. They do not call external LLM code, do not call deep-analysis routes, and do not upload attachments. Frontend entry text states local preview and user-initiated copy/export.

## Test and Build Results

- `cd backend; python -m pytest`: passed, 28 tests.
- `cd backend; python -m pytest tests/test_phase3_analysis_packet.py -q`: passed, 6 tests.
- `cd backend; python -m compileall app`: passed.
- `cd frontend; npm run build`: passed.
- FastAPI smoke: Phase 2 four routes and Phase 3 packet/evidence include routes returned 200, except no 422 occurred in the supplied valid simulation payload.

## Trial Recommendation

Use a脱敏 demo portfolio first, then a small manually entered real portfolio only after confirming risk limits and repo treatment. Do not use full real account data until the user has reviewed sample exports and `.gitignore` protection.
