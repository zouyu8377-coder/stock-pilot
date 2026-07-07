# External Driver Capability Report

Last updated: 2026-05-25

## Environment

- TUSHARE_TOKEN: not configured in current environment.
- Backend: FastAPI with local parquet base market.
- External driver module: `backend/app/external_drivers/`.

## Status Legend

- `AVAILABLE_WITH_DATA`: endpoint accessible and returned data in probe.
- `AVAILABLE_NO_DATA`: endpoint accessible but returned empty for probe symbol.
- `PERMISSION_DENIED`: endpoint exists but account lacks permission.
- `PENDING_PROBE`: endpoint name known but provider code not yet verified in this environment.
- `UNSUPPORTED_PLACEHOLDER`: intentionally not configured in this round; no automatic retrieval attempted.
- `UNAVAILABLE`: token/config missing or runtime error.

## Factor Interface Matrix

| factor_id | endpoint | provider_code | status | packet_verified | limitation |
|---|---|---|---|---|---|
| copper_futures | fut_daily | CU.SHF | UNAVAILABLE (no token) | yes (structure) | Token not configured; structure verified via unit test |
| gold_futures | fut_daily | pending_probe | PENDING_PROBE | no | Provider code for gold futures not yet verified |
| usd_cnh | fx_daily | USDCNH.FXCM | UNAVAILABLE (no token) | yes (structure) | Token not configured; structure verified via unit test |
| ai_theme_etf_159382 | etf_share_size,fund_nav,fund_daily | 159382.SZ | UNAVAILABLE (no token) | yes (structure) | Token not configured; structure verified via unit test |
| gold_etf_159934 | etf_share_size,fund_nav,fund_daily | 159934.SZ | UNAVAILABLE (no token) | yes (structure) | Token not configured; structure verified via unit test |
| pcb_sector_index_placeholder | not_configured | N/A | UNSUPPORTED_PLACEHOLDER | N/A | No verified sector-index provider code configured |
| tungsten_price_placeholder | not_configured | N/A | UNSUPPORTED_PLACEHOLDER | N/A | No verified tungsten price provider code configured |
| tin_price_placeholder | not_configured | N/A | UNSUPPORTED_PLACEHOLDER | N/A | No verified tin price provider code configured |
| cobalt_moly_price_placeholder | not_configured | N/A | UNSUPPORTED_PLACEHOLDER | N/A | No verified cobalt/molybdenum provider code configured |
| resource_sector_index_placeholder | not_configured | N/A | UNSUPPORTED_PLACEHOLDER | N/A | No verified resource sector index provider code configured |

## Profile Coverage

| symbol | profile_id | configured_factors | pending/unsupported |
|---|---|---|---|
| 601899.SH | ZIJIN_RESOURCE_METALS_V1 | copper_futures, usd_cnh, gold_etf_159934 | gold_futures |
| 603993.SH | LUOMO_RESOURCE_METALS_V1 | copper_futures, usd_cnh | cobalt_moly_price_placeholder, resource_sector_index_placeholder |
| 000960.SZ | XIYAN_TIN_RESOURCE_V1 | usd_cnh | tin_price_placeholder, resource_sector_index_placeholder |
| 159934.SZ | GOLD_ETF_SELF_V1 | gold_etf_159934 | — |
| 002463.SZ | AI_PCB_HARDWARE_V1 | ai_theme_etf_159382 | pcb_sector_index_placeholder |
| 002916.SZ | AI_PCB_HARDWARE_V1 | ai_theme_etf_159382 | pcb_sector_index_placeholder |
| 159382.SZ | AI_THEME_ETF_SELF_V1 | ai_theme_etf_159382 | — |
| 000657.SZ | ZHONGWU_RESOURCE_AI_PCB_V1 | copper_futures, ai_theme_etf_159382 | tungsten_price_placeholder, pcb_sector_index_placeholder |
| 600000.SH | DEFAULT_UNMAPPED_V1 | — | — |

## Conclusion

- Structure and mapping logic verified: 33 backend tests pass.
- Portfolio shared-driver deduplication implemented and verified.
- No real Token, account data, or attachment entered samples or reports.
- Real external driver data retrieval remains pending TUSHARE_TOKEN configuration.
