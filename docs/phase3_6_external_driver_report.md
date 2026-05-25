# Phase 3.6A External Driver Report

Last updated: 2026-05-25

## Baseline State

- Branch at start: `feature/analysis-packet-v1-baseline`.
- `git status --short`: clean.
- Latest commits:
  - `808a604 Record Phase 3.5 baseline closure result`
  - `bb3fa99 Build evidence-based analysis packet and portfolio baseline`
  - `f737215 docs: add workflow demo gif`
  - `59e5af8 迭代更新：AI深度分析增强、数据覆盖检查、前端交互优化`
  - `2256136 feat: upgrade AI deep analysis to model-driven strategy system`
- `git diff --stat`: empty.
- `git ls-files --others --exclude-standard`: empty.

Phase 3.5 is treated as the stable baseline. Analysis Packet v1 already exports layered `auto_fact`, `auto_signal`, manual account/evidence, system hypotheses, unavailable coverage, privacy boundaries, and explicit quote-time boundaries.

## Implementation Scope

This round adds only Phase 3.6A external-driver support:

- Configurable `symbol/theme -> external driver` profiles.
- Minimal external-driver data retrieval through already probed Tushare endpoints.
- `available`, `unavailable`, and `not_configured` mapping/data states.
- External-driver raw facts and derived observations as existing `EvidenceItem` records.
- Single-stock and portfolio Analysis Packet integration.
- Tests for configured, unavailable, and unmapped symbols.

## Explicitly Out Of Scope

- OCR holding screenshot import.
- Broker sync or automated trading.
- Moneyflow, margin financing, shareholder count, unlock, buyback, block trade, pledge, and broader event expansion.
- Full-market automatic industry-factor matching.
- Correlation learning, regression, causality, macro scoring, or buy/sell conclusions.
- Intraday commodity/FX refresh.
- Phase 4 layout redesign or Phase 5 expansion.
- Any automatic external LLM call.

## Initial Focus Profiles

- `601899.SH` Zijin Mining: copper futures, gold futures, USD/CNH, and gold ETF context.
- `002916.SZ` Shennan Circuits: AI theme ETF plus PCB/AI observation placeholders where no verified sector-index code is configured.
- `000657.SZ` Zhongwu High-Tech: resource-side placeholders plus AI theme ETF context; no tungsten contract is treated as verified in this round.
- `002463.SZ` Hudian: AI theme ETF plus PCB/AI observation placeholders.
- `159382.SZ` AI theme ETF: ETF share/NAV/price facts through the existing ETF fact service.
- `159934.SZ` gold ETF: ETF share/NAV/price facts through the existing ETF fact service.

Unmapped symbols use `DEFAULT_UNMAPPED_V1` and do not receive generic USD, copper, gold, or sector drivers.

## Data Interfaces To Probe Or Use

Already probed in `docs/tushare_capability_report.md`:

- `fut_daily`, sample `CU.SHF`, commodity future daily data.
- Gold futures are kept as `pending_probe` until a provider code is successfully verified; no unverified gold-futures code is written into the active retrieval config.
- `fx_daily`, sample `USDCNH.FXCM`, FX daily data.
- `etf_share_size`, `fund_nav`, `fund_daily`, samples `159382.SZ` and `159934.SZ`, ETF facts through existing service.
- `ths_daily`, sample `885800.TI`, reserved for future sector-index mapping after user review.

Runtime token or permission failures must produce `unavailable` evidence, not inferred conclusions.

## Implementation Result

- Added `backend/app/external_drivers/` with reviewed profile schemas, static first-batch mappings, default unmapped state, and retrieval service.
- Added `external_driver_fact` and `external_driver_signal` to the existing `EvidenceType` enum.
- Single-stock Packet now includes `external_driver_mapping`, external-driver facts in `auto_fact`, derived changes in `auto_signal`, and mapping/missing boundaries.
- Portfolio Packet now includes `external_driver_summary` per holding; each symbol keeps its own mapping status and evidence.
- Unmapped symbols explicitly return `DEFAULT_UNMAPPED_V1` and do not receive generic commodity, FX, gold, or sector drivers.
- Unsupported placeholders, such as tungsten price or PCB sector index without a verified provider code, remain missing-data boundaries and do not produce facts.
- Company profile evidence was minimally downgraded to `llm_usage = context_only` because it may mix Tushare fields with rule-inferred fields.
- No external LLM call, OCR import, broker sync, trading action, moneyflow, margin, or event expansion was added.

## Acceptance Sample

- Sanitized review sample: `docs/acceptance_samples/phase3_6_external_driver_sample.json`.
- The sample shows both an unmapped symbol and a configured symbol with separated mapping, raw fact, and weak derived observation layers.

## Verification

- `cd backend; python -m pytest tests/test_phase3_analysis_packet.py -q`: passed, 8 tests.
- `cd backend; python -m pytest tests/test_phase3_6_external_drivers.py -q`: passed, 3 tests.
- `cd backend; python -m pytest -q`: passed, 33 tests.
- `cd backend; python -m compileall app`: passed.

Known warnings are existing Pydantic class-config and `datetime.utcnow()` deprecation warnings; they are not introduced as functional blockers for Phase 3.6A.
