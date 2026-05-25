# Phase 3.6A Acceptance Checklist

Last updated: 2026-05-25

## 1. Automation Verification

| Item | Method | Result | Blocking Git | Blocking OCR | Blocking Real Portfolio |
|---|---|---|---|---|---|
| Backend pytest | `cd backend; python -m pytest -q` | 33 passed | no | no | no |
| Backend compileall | `cd backend; python -m compileall app` | passed | no | no | no |
| Frontend build | `cd frontend; npm run build` | passed | no | no | no |

## 2. Profile Mapping for Key Symbols

| Symbol | Profile | Result | Notes |
|---|---|---|---|
| 601899.SH | ZIJIN_RESOURCE_METALS_V1 | pass | copper, gold(pending), usd_cnh, gold_etf |
| 603993.SH | LUOMO_RESOURCE_METALS_V1 | pass | added in this round; copper, usd_cnh, cobalt_moly_placeholder, resource_sector_placeholder |
| 000960.SZ | XIYAN_TIN_RESOURCE_V1 | pass | added in this round; tin_placeholder, usd_cnh, resource_sector_placeholder |
| 159934.SZ | GOLD_ETF_SELF_V1 | pass | gold_etf |
| 002463.SZ | AI_PCB_HARDWARE_V1 | pass | ai_etf, pcb_placeholder |
| 002916.SZ | AI_PCB_HARDWARE_V1 | pass | ai_etf, pcb_placeholder |
| 159382.SZ | AI_THEME_ETF_SELF_V1 | pass | ai_etf |
| 000657.SZ | ZHONGWU_RESOURCE_AI_PCB_V1 | pass | tungsten_placeholder, copper, ai_etf, pcb_placeholder |
| 600000.SH | DEFAULT_UNMAPPED_V1 | pass | no generic macro factors attached |

## 3. Portfolio Shared Driver Deduplication

| Item | Result | Notes |
|---|---|---|
| copper_futures shared by 601899+603993+000657 | pass | aggregated associated_symbols |
| usd_cnh shared by 601899+603993 | pass | aggregated associated_symbols |
| gold_etf only 601899 | pass | correct single association |
| ai_etf only 000657 | pass | correct single association |
| Asset exposure not duplicated | pass | primary_theme still unique |

## 4. Capability Probe

| Factor | Status | Packet Verified |
|---|---|---|
| copper_futures | UNAVAILABLE (no token) | structure yes |
| gold_futures | PENDING_PROBE | no |
| usd_cnh | UNAVAILABLE (no token) | structure yes |
| ai_theme_etf_159382 | UNAVAILABLE (no token) | structure yes |
| gold_etf_159934 | UNAVAILABLE (no token) | structure yes |
| pcb_sector_index_placeholder | UNSUPPORTED_PLACEHOLDER | N/A |
| tungsten_price_placeholder | UNSUPPORTED_PLACEHOLDER | N/A |
| tin_price_placeholder | UNSUPPORTED_PLACEHOLDER | N/A |
| cobalt_moly_price_placeholder | UNSUPPORTED_PLACEHOLDER | N/A |
| resource_sector_index_placeholder | UNSUPPORTED_PLACEHOLDER | N/A |

## 5. Boundary Regression

| Item | Result | Notes |
|---|---|---|
| Quote time not misused | pass | market_price_as_of=null, status=unavailable |
| Company profile downgraded | pass | llm_usage=context_only |
| No auto buy/sell conclusion | pass | no trading recommendation in packet |
| Privacy notice present | pass | in markdown and json |
| No external LLM call | pass | no call to LLM in packet paths |
| No attachment upload | pass | no upload logic |

## 6. Security Check

| Item | Result |
|---|---|
| backend/.env ignored | pass |
| data/portfolio ignored | pass |
| data/tushare ignored | pass |
| data/analysis_snapshots ignored | pass |
| account_exports ignored | pass |
| attachments/uploads/screenshots ignored | pass |
| No real token in source | pass |
| Samples sanitized | pass |

## 7. Fixes Applied in This Round

1. Added `LUOMO_RESOURCE_METALS_V1` profile for 603993.SH.
2. Added `XIYAN_TIN_RESOURCE_V1` profile for 000960.SZ.
3. Added placeholders: `TIN_PLACEHOLDER`, `COBALT_MOLY_PLACEHOLDER`, `RESOURCE_SECTOR_PLACEHOLDER`.
4. Implemented portfolio shared-driver deduplication in `_portfolio_external_driver_summary`.
5. Fixed `build_portfolio_packet` to handle new deduplication structure.

## 8. Remaining Limitations

- Real external driver data retrieval pending TUSHARE_TOKEN configuration.
- No real available driver has entered a packet in this environment yet.
- Browser manual acceptance remains `pending_user_verification`.
- Risk limits and repo treatment remain unconfirmed by user.
