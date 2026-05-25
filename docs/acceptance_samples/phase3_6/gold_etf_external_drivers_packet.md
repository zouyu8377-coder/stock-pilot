# Stock-Pilot Analysis Packet v1 - single_stock

## Privacy and External Sharing Boundary
This packet is generated locally and may contain personal account information, holdings, costs, cash, repo, trade plans, and manually entered evidence. Stock-Pilot does not send it to any external LLM, does not call deep analysis, and does not upload attachments automatically. External sharing happens only if the user actively copies, downloads, or submits the content elsewhere.

Quote-time boundary: Current quote source does not provide a verifiable quote time; portfolio snapshot time is not market quote time.
Default-risk boundary: Concentration or cash reminders may depend on system default placeholder parameters and are unconfirmed by the user.
Repo boundary: Repo amount is displayed separately from cash; cash-equivalent treatment is unconfirmed.

## Packet Metadata
- packet_id: packet_f740040e77064aa7b306f31f29d14ec5
- packet_version: analysis_packet.v1
- generated_at: 2026-05-25T02:56:09.766804
- analysis_scope: single_stock
- target_symbol: 159934
- target_name: -
- user_question: 验收样例：黄金ETF外部驱动
- market_data_as_of: -
- daily_k_as_of: -
- portfolio_as_of: -
- source_snapshot_id: snap_981ee4eb396242bba66116d426da24e6

## Basic Information
```json
{
  "symbol": "159934",
  "name": "",
  "industry": null,
  "area": null,
  "listing_information": {
    "list_date": null,
    "exchange": null
  },
  "company_profile": {},
  "current_holding": {
    "has_holding": false,
    "message": "No local holding for this symbol in the current portfolio snapshot."
  },
  "data_status": "unavailable"
}
```

## Auto Fact
- **Base market snapshot unavailable**
  - category: `auto_fact`; type: `data_coverage`
  - source: Stock-Pilot snapshot builder; endpoint: build_basic_stock_snapshot
  - as_of: -; fetched/recorded: 2026-05-25T02:56:09.766102
  - reliability: `B`; llm_usage: `context_only`; data_status: `unavailable`
  - boundary: Base quote/history snapshot is unavailable; use this as a data boundary only.
  - payload: `{"reason": "Unknown symbol prefix: 159934"}`
- **etf_share_change unavailable**
  - category: `auto_fact`; type: `etf_share_change`
  - source: Stock-Pilot fact service; endpoint: etf_share_size,fund_nav,fund_daily
  - as_of: -; fetched/recorded: 2026-05-25T02:56:09.766804
  - reliability: `B`; llm_usage: `context_only`; data_status: `unavailable`
  - boundary: ETF share/NAV/price facts are unavailable. When available, share changes still do not imply future price direction.
  - payload: `{"coverage": "etf_share_change", "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN."}`
- **External driver unavailable: Gold ETF share, NAV, and price**
  - category: `auto_fact`; type: `external_driver_fact`
  - source: tushare.etf_share_size,fund_nav,fund_daily; endpoint: etf_share_size,fund_nav,fund_daily
  - as_of: -; fetched/recorded: 2026-05-25T02:56:09.766804
  - reliability: `B`; llm_usage: `context_only`; data_status: `unavailable`
  - boundary: External-driver facts are related background observations only. They do not imply a direct causal effect, valuation impact, or buy/sell conclusion.
  - payload: `{"factor_id": "gold_etf_159934", "display_name": "Gold ETF share, NAV, and price", "factor_type": "theme_etf", "data_status": "unavailable", "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN.", "mapping_boundary": "External-driver mapping is a product configuration used to select observation variables. It does not prove these factors dominate the stock price in the current period and must not be used as a system buy/sell conclusion."}`

## Auto Signal
Auxiliary observations only; these are not factual conclusions or buy/sell instructions.
- No available evidence in this section.

## Manual Account
```json
{
  "has_holding": false,
  "message": "No local holding for this symbol in the current portfolio snapshot."
}
```

## Manual Evidence
- No available evidence in this section.

## External Driver Mapping
```json
{
  "mapping_status": "configured",
  "profile_id": "GOLD_ETF_SELF_V1",
  "symbol": "159934.SZ",
  "message": "已为该标的配置专属外部驱动观察因子；这些因子仅用于筛选背景变量。",
  "future_extension": "可继续增加经用户确认且接口代码已验证的行业、商品或主题映射。",
  "drivers": [
    {
      "factor_id": "gold_etf_159934",
      "display_name": "Gold ETF share, NAV, and price",
      "factor_type": "theme_etf",
      "importance": "context",
      "retrieval_config": {
        "provider": "tushare",
        "endpoint": "etf_share_size,fund_nav,fund_daily",
        "provider_symbol": "159934.SZ",
        "code": "159934.SZ"
      },
      "inclusion_reason": "Gold ETF facts can provide a listed gold-theme context observation.",
      "interpretation_limit": "ETF facts are background observations only and do not prove fund flow into miners.",
      "status": "configured"
    }
  ],
  "boundary": "External-driver mapping is a product configuration used to select observation variables. It does not prove these factors dominate the stock price in the current period and must not be used as a system buy/sell conclusion.",
  "llm_usage": "context_only",
  "interpretation_limit": "This mapping selects observation variables only and is not market evidence by itself."
}
```
## System Hypothesis and Risk Reminders
System-generated, must be questioned and manually verified.
- No available evidence in this section.


## Missing Data
- {"key": "base_market_snapshot", "reason": "Unknown symbol prefix: 159934"}

## Interpretation Boundaries
- Automatic shareholder count is not available in this stage.
- Automatic unlock event data is not available in this stage.
- Announcement full text is not read unless manually entered; do not infer business or profit impact from an index title.
- Dragon-tiger list data shows public abnormal trading seat structure only and does not prove long-term capital commitment.
- Moneyflow, margin financing, backtesting, and broker sync are not included in this stage.
- External commodity, FX, ETF, or sector drivers are attached only when a reviewed symbol mapping exists; unmapped symbols do not receive generic macro factors.
- Manual account data uses the user's local snapshot time and may be stale.
- Realtime quote data and low-frequency facts may have different timestamps.
- The current quote provider does not expose a verifiable quote timestamp for portfolio enrichment; portfolio snapshot time is not market quote time.
- Concentration and cash reminders may depend on system default placeholder parameters that have not been confirmed by the user.
- Repo amount is shown separately. It is not treated as fully equivalent to cash unless the user confirms that convention.
- External-driver mapping is a product configuration used to select observation variables. It does not prove these factors dominate the stock price in the current period and must not be used as a system buy/sell conclusion.

## Neutral Questions for an External LLM
- Which items in this packet are hard facts, and which are weak auxiliary signals?
- Does the current holding, if any, create excessive theme exposure inside the portfolio?
- Which missing information would most materially change the analysis?
- Is the user's invalid condition specific enough to falsify the trade plan?
- What are the main risks under bullish, neutral, and adverse market scenarios?

No buy/sell recommendation is generated by this packet.