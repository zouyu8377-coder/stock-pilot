# Stage 0 Foundation Notes

## Scope

Stage 0 adds a safety and data-foundation layer without changing the existing stock query, K-line, quick analysis, deep analysis, or LLM output contracts.

## Token Safety

Tushare access now reads the backend-only `TUSHARE_TOKEN` setting from environment variables or `backend/.env`.

Do not put Tushare credentials in:

- frontend `.env` files
- `VITE_` variables
- logs
- generated snapshots
- tests

`backend/.env.example` contains placeholders only. Real `.env` files are ignored by Git.

## Evidence Model

Evidence items live in `backend/app/evidence/schemas.py`.

Key fields:

- `category` separates automatic facts, automatic signals, manual account data, manual evidence, and system hypotheses.
- `reliability` uses `A`, `B`, `C`, and `H`.
- `llm_usage` controls whether the LLM may treat the item as fact, bounded fact, weak signal, context, or hypothesis.
- `system_hypothesis` evidence must use `reliability=H` and cannot use fact-level `llm_usage`.

The evidence type enum already reserves future types for ETF share changes, dragon-tiger events, announcements, surveys, margin changes, vendor moneyflow, manual shareholder count, manual unlock events, portfolio data, trade plans, and system market regime.

## Analysis Snapshot

`backend/app/analysis_packet/snapshot_builder.py` can generate a basic single-stock `AnalysisSnapshot`.

Current snapshot inputs:

- realtime quote
- local daily K summary
- technical indicators
- company profile
- data coverage
- current rule-based analysis and market regime as `system_hypothesis`

Snapshots are written under:

```text
backend/data/analysis_snapshots/{symbol}/{snapshot_id}.json
```

This directory is ignored by Git.

## Tushare Low-Frequency Cache

The reusable low-frequency client lives in `backend/app/tushare/client.py`.

Default cache root:

```text
backend/data/tushare/
```

Reserved subdirectories:

```text
etf/
dragon_tiger/
announcements/
surveys/
margin/
moneyflow/
events/
```

Each cached query stores a parquet payload and a `.meta.json` file with endpoint, params, row count, fetch time, and data path. The client supports token validation, sanitized errors, configurable throttling, and TTL-based cache reads.

## Next Reuse Points

- ETF card: reuse `TushareLowFrequencyClient.query(namespace="etf", endpoint="etf_share_size" | "fund_nav" | "fund_daily")`.
- Dragon-tiger card: reuse `namespace="dragon_tiger"` with `top_list` and `top_inst`.
- Announcement and survey timeline: reuse `namespace="announcements"` for `anns_d` and `namespace="surveys"` for `stk_surv`.
- Margin and moneyflow modules: reuse `namespace="margin"` and `namespace="moneyflow"` with daily/background refresh, not page-triggered high-frequency calls.
- Analysis Packet v1: append new facts as `EvidenceItem` records before prompt/export formatting.
