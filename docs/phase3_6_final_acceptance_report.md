# Phase 3.6A Final Acceptance Report

Last updated: 2026-05-25

## 1. Current Branch and Workspace State

- Branch: `feature/analysis-packet-v1-baseline`
- `git status --short`: modified tracked files and new untracked files from Phase 3.6A
- `git log --oneline -n 5`:
  - `808a604 Record Phase 3.5 baseline closure result`
  - `bb3fa99 Build evidence-based analysis packet and portfolio baseline`
  - `f737215 docs: add workflow demo gif`
  - `59e5af8 迭代更新：AI深度分析增强、数据覆盖检查、前端交互优化`
  - `2256136 feat: upgrade AI deep analysis to model-driven strategy system`

## 2. Phase 3.6A Implementation Summary

This round adds mapped external driver evidence to Analysis Packets:

- `backend/app/external_drivers/` with schemas, profiles, and service.
- Extended `EvidenceType` with `EXTERNAL_DRIVER_FACT` and `EXTERNAL_DRIVER_SIGNAL`.
- Single-stock Packet includes `external_driver_mapping`, facts in `auto_fact`, and derived signals in `auto_signal`.
- Portfolio Packet includes `external_driver_summary` with deduplicated shared drivers and per-symbol mapping.
- Unmapped symbols return `DEFAULT_UNMAPPED_V1` without generic macro factors.
- Unsupported placeholders remain missing-data boundaries.

## 3. Modules Reviewed

- `backend/app/external_drivers/schemas.py`
- `backend/app/external_drivers/profiles.py`
- `backend/app/external_drivers/service.py`
- `backend/app/external_drivers/__init__.py`
- `backend/app/evidence/schemas.py`
- `backend/app/analysis_packet/packet_service.py`
- `backend/app/analysis_packet/snapshot_builder.py`
- `backend/tests/test_phase3_analysis_packet.py`
- `backend/tests/test_phase3_6_external_drivers.py`
- `frontend/src/components/AnalysisPacketPanel.vue`
- `frontend/src/api/client.ts`

## 4. Automation Test and Build Results

- `cd backend; python -m pytest -q`: 33 passed
- `cd backend; python -m compileall app`: passed
- `cd frontend; npm run build`: passed

## 5. API Smoke Summary

Phase 2 and Phase 3 API routes were previously smoke-tested in Phase 3.5 and remain unchanged.

Phase 3.6A new capabilities verified via direct Python invocation (no Token, so data status is `unavailable`):

- `build_external_driver_context("601899")` returns configured profile with mapped drivers.
- `build_external_driver_context("600000")` returns `DEFAULT_UNMAPPED_V1`.
- `_portfolio_external_driver_summary(positions)` returns deduplicated shared drivers.

## 6. Eight Key Symbol Profile Acceptance

| Symbol | Profile | Result |
|---|---|---|
| 601899.SH | ZIJIN_RESOURCE_METALS_V1 | pass |
| 603993.SH | LUOMO_RESOURCE_METALS_V1 | pass (added this round) |
| 000960.SZ | XIYAN_TIN_RESOURCE_V1 | pass (added this round) |
| 159934.SZ | GOLD_ETF_SELF_V1 | pass |
| 002463.SZ | AI_PCB_HARDWARE_V1 | pass |
| 002916.SZ | AI_PCB_HARDWARE_V1 | pass |
| 159382.SZ | AI_THEME_ETF_SELF_V1 | pass |
| 000657.SZ | ZHONGWU_RESOURCE_AI_PCB_V1 | pass |
| 600000.SH | DEFAULT_UNMAPPED_V1 | pass |

## 7. DEFAULT_UNMAPPED_V1 Acceptance

- `mapping_status`: `not_configured`
- `profile_id`: `DEFAULT_UNMAPPED_V1`
- `drivers`: `[]`
- No generic USD, copper, gold, AI ETF, or macro factors attached.
- Verified via `build_single_stock_packet("600000")` output.

## 8. Portfolio Shared Driver Deduplication

- `copper_futures` shared by 601899.SH, 603993.SH, 000657.SZ: single entry with `associated_symbols`.
- `usd_cnh` shared by 601899.SH, 603993.SH: single entry with `associated_symbols`.
- `gold_etf_159934` only 601899.SH.
- `ai_theme_etf_159382` only 000657.SZ.
- Asset exposure by `primary_theme` remains unique; no double counting.

## 9. Capability Probe Result

- No TUSHARE_TOKEN configured in this environment.
- All `configured` factors return `unavailable` due to missing token.
- Placeholder factors remain `unsupported_placeholder`.
- Structure and unavailable paths verified; real data retrieval pending token.

## 10. Real Driver Entering Packet

- No real external driver data has entered a Packet in this environment.
- Reason: TUSHARE_TOKEN not configured.
- Structure verified via unit tests with mock client.
- When token is available, `copper_futures`, `usd_cnh`, and ETF facts should enter Packet as `auto_fact`.

## 11. Boundary Regression Results

| Item | Result |
|---|---|
| Quote time not misused | pass |
| Company profile downgraded to `context_only` | pass |
| Daily K derived observations bounded | pass |
| Privacy notice present | pass |
| No external LLM call | pass |
| No attachment upload | pass |

## 12. Privacy and No Automatic External Transfer

- Packet generation does not call external LLM.
- No deep analysis called.
- No attachment upload.
- No Token written into Packet output (only configuration message when missing).
- Privacy notice retained in Markdown.

## 13. Security Check

- `backend/.env` ignored: pass
- `data/portfolio/`, `data/tushare/`, `data/analysis_snapshots/` ignored: pass
- `account_exports/`, `attachments/`, `uploads/`, `screenshots/` ignored: pass
- No real secret values in source: pass
- All acceptance samples sanitized: pass

## 14. Fixes Applied This Round

1. Added `LUOMO_RESOURCE_METALS_V1` profile for 603993.SH (Luomo Mining).
2. Added `XIYAN_TIN_RESOURCE_V1` profile for 000960.SZ (Xiyan).
3. Added placeholder drivers: `TIN_PLACEHOLDER`, `COBALT_MOLY_PLACEHOLDER`, `RESOURCE_SECTOR_PLACEHOLDER`.
4. Implemented portfolio shared-driver deduplication.
5. Fixed `build_portfolio_packet` to handle deduplicated structure.

## 15. Remaining Limitations

- Real external driver data retrieval requires TUSHARE_TOKEN.
- No real driver data has entered Packet in this environment.
- Browser manual acceptance not yet performed by user.
- User risk limits and repo treatment remain unconfirmed.
- OCR not developed.

## 16. Recommendation: Enter OCR?

**Not yet recommended.**

Before OCR development:
- Frontend build passes and basic structure is stable.
- Mapped/unmapped behavior passes.
- Differential mapping for resource/AI/composite symbols passes.
- Shared driver deduplication passes.
- **However**, real external driver data has not been verified to enter Packet.
- Browser manual acceptance is still pending.

Recommendation: complete at least one browser manual acceptance pass and, if possible, verify one real driver with TUSHARE_TOKEN before starting OCR.

## 17. Recommendation: Sanitized vs Real Portfolio

**Continue with sanitized demo portfolio only.**

- Real external driver data not yet verified.
- Risk limits remain unconfirmed.
- A small real manually entered portfolio should only be tried after:
  - Browser acceptance completed.
  - At least one real driver enters Packet successfully, or user accepts unavailable boundaries.
  - Risk limits confirmed.

## 18. Document Paths

- Acceptance report: `docs/phase3_6_final_acceptance_report.md`
- Checklist: `docs/phase3_6_acceptance_checklist.md`
- Capability report: `docs/external_driver_capability_report.md`
- Capability JSON: `docs/external_driver_capability_report.json`
- Samples: `docs/acceptance_samples/phase3_6/`

## 19. Git Baseline

- To be committed in the next step.
- Commit message: `Add mapped external driver evidence to analysis packets`

## 20. Explicit Declarations

- This round did not develop OCR.
- This round did not enter Phase 4 or Phase 5.
- This round did not automatically call external LLM.
- This round did not submit any Token, real account data, or attachments.
