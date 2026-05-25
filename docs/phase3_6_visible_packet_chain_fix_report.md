# Phase 3.6A Visible Packet Chain Fix Report

## Baseline

- Baseline branch: `feature/analysis-packet-v1-baseline`
- Baseline commit: `0927317` (`Add mapped external driver evidence to analysis packets`)
- Fix branch: `fix/phase3-6a-visible-packet-chain`

## User-Visible Inconsistencies

1. Zijin Mining single-stock Markdown copied from the frontend does not include `Relevant External Drivers`, `ZIJIN_RESOURCE_METALS_V1`, or configured drivers such as `copper_futures`, `usd_cnh`, and `gold_futures`.
2. Markdown still exposes old market time fields such as `market_data_as_of`, `as_of`, and `fetched/recorded` even while saying the quote source has no verifiable quote time.
3. Rule-derived company profile content is still exported as strong `auto_fact` with `llm_usage: fact_with_limit`, including evaluative claims.
4. `Interpretation Boundaries` still says FX and futures are not included, which conflicts with Phase 3.6A external driver design.

## Investigation Plan

| Path | external driver section | quote time new fields | company profile downgraded | boundary updated | conclusion |
|---|---|---|---|---|---|
| Bottom service | Pass: `## Relevant External Drivers`, `ZIJIN_RESOURCE_METALS_V1`, `copper_futures`, `usd_cnh`, `gold_futures` present | Pass: `quote_retrieved_at`, `quote_market_time: null`, `quote_time_status: unavailable`; no `market_data_as_of` | Pass: no `company_profile` in `auto_fact`; exported as `company_profile_context` under system context | Pass: no `FX, futures, backtesting` exclusion | Current code path fixed |
| JSON API | Pass via `TestClient`; `external_driver_mapping` present | Pass | Pass | Pass | Current FastAPI app object fixed |
| Markdown API | Pass: API response `markdown` has `Relevant External Drivers` | Pass | Pass | Pass | Renderer now uses latest packet fields |
| Frontend preview | Pass on `http://127.0.0.1:5173` with API base `http://127.0.0.1:8001` | Pass | Pass | Pass | Preview now comes from `AnalysisPacketPanel` only |
| Frontend copy | Pass: clipboard contains external drivers and new quote fields | Pass: clipboard has no `market_data_as_of` | Pass: clipboard has no `type: company_profile` auto fact and no evaluative `最强` payload | Pass | User-visible copy path fixed |

## Root Cause

There were two separate inconsistencies:

1. The single-stock page still mounted `AnalysisPromptPanel`, which called the old `/api/deep-analyze-prompt/{symbol}` prompt chain. That old panel had its own copy action, so a user could still copy an old prompt/Markdown-style output even after the new Analysis Packet API existed.
2. The Phase 3.6A backend renderer was only partially updated. The JSON packet contained `external_driver_mapping`, but the single-stock Markdown section was still named `External Driver Mapping` and did not provide the user-visible `Relevant External Drivers` driver status section. The same renderer still exposed `market_data_as_of` and realtime quote `as_of/fetched` lines, and it kept rule-derived `company_profile` payloads in `auto_fact`.

During local runtime verification, `127.0.0.1:8000` was also still served by an old uvicorn process/state and returned old Markdown. A fresh backend started on `127.0.0.1:8001` returned the fixed output. This confirms that stale running services can reproduce the user's symptom even when the checked-out code is newer.

## Fix Summary

- `backend/app/analysis_packet/snapshot_builder.py`
  - Realtime quote evidence now uses `quote_retrieved_at`, `quote_market_time: null`, and `quote_time_status: unavailable`.
  - `market_data_as_of` is no longer populated from quote retrieval time.
- `backend/app/analysis_packet/packet_service.py`
  - Single-stock metadata exports quote time fields instead of `market_data_as_of`.
  - Rule-derived company profile content is removed from `auto_fact` and exported as bounded `company_profile_context`.
  - Single-stock Markdown renders `## Relevant External Drivers` with mapping context and per-driver status.
  - Portfolio holding quote fields use `quote_retrieved_at`, `quote_market_time`, and `quote_time_status`.
- `frontend/src/App.vue`
  - Removed the old `AnalysisPromptPanel` from the single-stock page so preview/copy no longer uses `/api/deep-analyze-prompt/{symbol}`.
- `backend/tests/test_phase3_analysis_packet.py`
  - Added API + Markdown export coverage for the visible single-stock chain.
  - Updated quote-time and company-profile assertions to match the user-visible contract.

## Verification

- Bottom service direct call for `601899`: passed.
- FastAPI `TestClient` single-stock API: passed.
- Real HTTP API:
  - `127.0.0.1:8000`: failed before restart/cleanup because it returned old output.
  - `127.0.0.1:8001`: passed with fresh backend.
- Browser UI on `http://127.0.0.1:5173` pointed at `http://127.0.0.1:8001`: passed.
- Clipboard checks after clicking `Copy Markdown`:
  - Contains `## Relevant External Drivers`: yes.
  - Contains `ZIJIN_RESOURCE_METALS_V1`: yes.
  - Contains `copper_futures`, `usd_cnh`, `gold_futures`: yes.
  - Contains `quote_retrieved_at` and `quote_market_time`: yes.
  - Contains `market_data_as_of`: no.
  - Contains `type: company_profile`: no.
  - Contains old `FX, futures, backtesting` exclusion: no.

## Automated Checks

- `python -m pytest`: 34 passed.
- `python -m compileall app`: passed.
- `npm run build`: passed.

## Explicit Non-Goals

- No OCR import work.
- No personal investment dashboard work.
- No Phase 4 or Phase 5 work.
- No new data source integration.
- No attempt to force unavailable external drivers to become available.
