# Stock-Pilot Analysis Packet v1 - single_stock

## Privacy and External Sharing Boundary
This packet is generated locally and may contain personal account information, holdings, costs, cash, repo, trade plans, and manually entered evidence. Stock-Pilot does not send it to any external LLM, does not call deep analysis, and does not upload attachments automatically. External sharing happens only if the user actively copies, downloads, or submits the content elsewhere.

Quote-time boundary: Current quote source does not provide a verifiable quote time; portfolio snapshot time is not market quote time.
Default-risk boundary: Concentration or cash reminders may depend on system default placeholder parameters and are unconfirmed by the user.
Repo boundary: Repo amount is displayed separately from cash; cash-equivalent treatment is unconfirmed.

## Packet Metadata
- packet_id: packet_69aca0bd8184431ab3aea78b94116874
- packet_version: analysis_packet.v1
- generated_at: 2026-05-25T02:56:10.085190
- analysis_scope: single_stock
- target_symbol: 000657
- target_name: 中钨高新
- user_question: 验收样例：中钨高新外部驱动
- market_data_as_of: 2026-05-25T02:56:10.079218
- daily_k_as_of: 2026-05-22
- portfolio_as_of: -
- source_snapshot_id: snap_f27a00507a6449e38aa5e72e65c52649

## Basic Information
```json
{
  "symbol": "000657",
  "name": "中钨高新",
  "industry": null,
  "area": null,
  "listing_information": {
    "list_date": null,
    "exchange": null
  },
  "company_profile": {
    "company_name": "中钨高新",
    "main_business": "有色金属采选与深加工",
    "core_products": [
      "数控刀片",
      "硬质合金",
      "钨丝"
    ],
    "industry_chain_position": "上游资源开采 + 中游深加工",
    "core_logic": [
      "高端刀具国产替代",
      "工业母机产业链",
      "战略金属管控",
      "央企资源整合预期",
      "国防装备采购"
    ],
    "concept_tags": [
      "工业母机",
      "军工",
      "央企改革",
      "小金属",
      "硬质合金"
    ],
    "company_type": [
      "军工"
    ],
    "profit_driver": "钨价上涨 + 高端刀具放量",
    "competitive_advantage": "资源储量优势，产业链一体化",
    "risk_points": [
      "钨价下跌",
      "制造业需求回落"
    ]
  },
  "current_holding": {
    "has_holding": false,
    "message": "No local holding for this symbol in the current portfolio snapshot."
  },
  "data_status": "available"
}
```

## Auto Fact
- **Realtime quote snapshot**
  - category: `auto_fact`; type: `realtime_quote`
  - source: easyquotation; endpoint: easyquotation.real
  - as_of: 2026-05-25T02:56:10.079218; fetched/recorded: 2026-05-25T02:56:10.079218
  - reliability: `B`; llm_usage: `fact_with_limit`; data_status: `available`
  - boundary: Quote data may be delayed and should not be interpreted as institutional intent.
  - payload: `{"symbol": "000657", "price": 63.72, "change_pct": 2.15, "name": "中钨高新", "volume": 72599600.0, "provider": "easyquotation", "hot_status": "ready", "market_cap": 1451.93, "float_market_cap": 925.8, "pe": 74.5, "pb": 13.59, "turnover_rate": 5.0, "volume_ratio": 2.57}`
- **Local daily K summary**
  - category: `auto_fact`; type: `daily_k_summary`
  - source: local parquet base_market; endpoint: collector.get_history
  - as_of: 2026-05-22; fetched/recorded: 2026-05-25T02:56:10.079218
  - reliability: `B`; llm_usage: `fact_with_limit`; data_status: `available`
  - boundary: Local daily K is a market fact summary, not a trading conclusion.
  - payload: `{"row_count": 5000, "open": 57.24, "high": 62.38, "low": 57.2, "close": 62.38, "volume": 91808038.0, "amount": 5545023114.29, "pct_chg": 9.9982, "return_5d_pct": 10.49, "return_20d_pct": 7.91, "return_60d_pct": 19.02}`
- **Company profile**
  - category: `auto_fact`; type: `company_profile`
  - source: stock_meta/Tushare cache/rule inference; endpoint: build_company_profile
  - as_of: -; fetched/recorded: 2026-05-25T02:56:10.079218
  - reliability: `B`; llm_usage: `context_only`; data_status: `available`
  - boundary: Company profile may mix Tushare fields and rule-inferred fields; treat it as bounded context, not formal disclosure or a hard fact.
  - payload: `{"company_name": "中钨高新", "main_business": "有色金属采选与深加工", "core_products": ["数控刀片", "硬质合金", "钨丝"], "industry_chain_position": "上游资源开采 + 中游深加工", "core_logic": ["高端刀具国产替代", "工业母机产业链", "战略金属管控", "央企资源整合预期", "国防装备采购"], "concept_tags": ["工业母机", "军工", "央企改革", "小金属", "硬质合金"], "company_type": ["军工"], "profit_driver": "钨价上涨 + 高端刀具放量", "competitive_advantage": "资源储量优势，产业链一体化", "risk_points": ["钨价下跌", "制造业需求回落"]}`
- **Data coverage**
  - category: `auto_fact`; type: `data_coverage`
  - source: data_coverage.py; endpoint: build_data_coverage
  - as_of: -; fetched/recorded: 2026-05-25T02:56:10.079218
  - reliability: `B`; llm_usage: `context_only`; data_status: `available`
  - boundary: Use this item to identify available and missing data, not as market evidence.
  - payload: `{"provided": [{"key": "company_business", "label": "主营业务及产品结构", "source": "本地公司画像/Tushare缓存/规则推断", "detail": {"main_business": "有色金属采选与深加工", "core_products": ["数控刀片", "硬质合金", "钨丝"], "industry_chain_position": "上游资源开采 + 中游深加工"}}, {"key": "price_overhang", "label": "前高与套牢区分布", "source": "本地日K线近250日", "detail": {"available": true, "previous_high": 71.5, "previous_high_date": "2026-03-03", "latest_close": 62.38, "distance_pct": -12.76, "overhang_volume_pct": 0.6, "source": "本地日K线近250日"}}], "missing": [{"key": "orders_capacity", "label": "最新订单与产能利用率", "reason": "当前未接入公告/调研纪要/互动易等事件文本源", "possible_sources": ["投资者关系活动记录", "互动易", "定期报告", "公司公告"]}, {"key": "northbound_flow", "label": "北向资金实时流向", "reason": "当前未接入陆股通持股或实时资金流数据", "possible_sources": ["深股通持股", "港交所披露", "交易所/行情数据源"]}, {"key": "institution_holding", "label": "机构持仓变动", "reason": "当前未接入基金季报、十大流通股东或机构持仓聚合数据", "possible_sources": ["基金季报", "十大流通股东", "定期报告", "机构持仓数据库"]}], "missing_labels": ["最新订单与产能利用率", "北向资金实时流向", "机构持仓变动"]}`
- **dragon_tiger_event unavailable**
  - category: `auto_fact`; type: `dragon_tiger_event`
  - source: Stock-Pilot fact service; endpoint: top_list,top_inst
  - as_of: -; fetched/recorded: 2026-05-25T02:56:10.085749
  - reliability: `B`; llm_usage: `context_only`; data_status: `unavailable`
  - boundary: Dragon-tiger facts are unavailable. When available, they reflect public abnormal-trading-day seat structure only, not long-term holding intent.
  - payload: `{"coverage": "dragon_tiger_event", "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN."}`
- **disclosure_index unavailable**
  - category: `auto_fact`; type: `disclosure_index`
  - source: Stock-Pilot fact service; endpoint: anns_d,stk_surv
  - as_of: -; fetched/recorded: 2026-05-25T02:56:10.085749
  - reliability: `B`; llm_usage: `context_only`; data_status: `unavailable`
  - boundary: Disclosure indexes are unavailable. When available, the system reads index data only, not announcement or survey full text.
  - payload: `{"coverage": "disclosure_index", "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN."}`
- **External driver unavailable: Copper futures daily price**
  - category: `auto_fact`; type: `external_driver_fact`
  - source: tushare.fut_daily; endpoint: fut_daily
  - as_of: -; fetched/recorded: 2026-05-25T02:56:10.086797
  - reliability: `B`; llm_usage: `context_only`; data_status: `unavailable`
  - boundary: External-driver facts are related background observations only. They do not imply a direct causal effect, valuation impact, or buy/sell conclusion.
  - payload: `{"factor_id": "copper_futures", "display_name": "Copper futures daily price", "factor_type": "commodity", "data_status": "unavailable", "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN.", "mapping_boundary": "External-driver mapping is a product configuration used to select observation variables. It does not prove these factors dominate the stock price in the current period and must not be used as a system buy/sell conclusion."}`
- **External driver unavailable: AI theme ETF share, NAV, and price**
  - category: `auto_fact`; type: `external_driver_fact`
  - source: tushare.etf_share_size,fund_nav,fund_daily; endpoint: etf_share_size,fund_nav,fund_daily
  - as_of: -; fetched/recorded: 2026-05-25T02:56:10.086797
  - reliability: `B`; llm_usage: `context_only`; data_status: `unavailable`
  - boundary: External-driver facts are related background observations only. They do not imply a direct causal effect, valuation impact, or buy/sell conclusion.
  - payload: `{"factor_id": "ai_theme_etf_159382", "display_name": "AI theme ETF share, NAV, and price", "factor_type": "theme_etf", "data_status": "unavailable", "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN.", "mapping_boundary": "External-driver mapping is a product configuration used to select observation variables. It does not prove these factors dominate the stock price in the current period and must not be used as a system buy/sell conclusion."}`

## Auto Signal
Auxiliary observations only; these are not factual conclusions or buy/sell instructions.
- **Technical indicators**
  - category: `auto_signal`; type: `technical_indicator`
  - source: indicators.py; endpoint: compute_indicators
  - as_of: 2026-05-22; fetched/recorded: 2026-05-25T02:56:10.079218
  - reliability: `C`; llm_usage: `weak_signal_only`; data_status: `available`
  - boundary: Technical indicators are auxiliary signals and must not be the sole basis for conclusions.
  - payload: `{"ma5": 57.04, "ma10": 58.35, "ma20": 58.02, "ma30": 55.93, "ma60": 55.88, "rsi14": 58.34, "macd": 1.17}`

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
  "profile_id": "ZHONGWU_RESOURCE_AI_PCB_V1",
  "symbol": "000657.SZ",
  "message": "已为该标的配置专属外部驱动观察因子；这些因子仅用于筛选背景变量。",
  "future_extension": "可继续增加经用户确认且接口代码已验证的行业、商品或主题映射。",
  "drivers": [
    {
      "factor_id": "tungsten_price_placeholder",
      "display_name": "Tungsten price placeholder",
      "factor_type": "unsupported_placeholder",
      "importance": "conditional",
      "retrieval_config": {
        "provider": "stock-pilot",
        "endpoint": "not_configured",
        "provider_symbol": null,
        "code": null
      },
      "inclusion_reason": "No verified tungsten daily series is configured in this round.",
      "interpretation_limit": "Placeholder only; no market fact is retrieved and no conclusion should be drawn.",
      "status": "unsupported"
    },
    {
      "factor_id": "copper_futures",
      "display_name": "Copper futures daily price",
      "factor_type": "commodity",
      "importance": "core_if_available",
      "retrieval_config": {
        "provider": "tushare",
        "endpoint": "fut_daily",
        "provider_symbol": "CU.SHF",
        "code": "CU.SHF"
      },
      "inclusion_reason": "Resource producers may have earnings or sentiment sensitivity to copper price observations.",
      "interpretation_limit": "Copper futures are background facts only; no causality or profit impact is inferred.",
      "status": "configured"
    },
    {
      "factor_id": "ai_theme_etf_159382",
      "display_name": "AI theme ETF share, NAV, and price",
      "factor_type": "theme_etf",
      "importance": "context",
      "retrieval_config": {
        "provider": "tushare",
        "endpoint": "etf_share_size,fund_nav,fund_daily",
        "provider_symbol": "159382.SZ",
        "code": "159382.SZ"
      },
      "inclusion_reason": "AI/PCB hardware names can be observed alongside a liquid AI-theme ETF proxy.",
      "interpretation_limit": "ETF facts are background observations only and do not prove theme inflow into a specific stock.",
      "status": "configured"
    },
    {
      "factor_id": "pcb_sector_index_placeholder",
      "display_name": "PCB sector index placeholder",
      "factor_type": "unsupported_placeholder",
      "importance": "conditional",
      "retrieval_config": {
        "provider": "stock-pilot",
        "endpoint": "not_configured",
        "provider_symbol": null,
        "code": null
      },
      "inclusion_reason": "PCB-specific sector-index mapping needs a verified provider code before automatic retrieval.",
      "interpretation_limit": "Placeholder only; no market fact is retrieved and no conclusion should be drawn.",
      "status": "unsupported"
    }
  ],
  "boundary": "External-driver mapping is a product configuration used to select observation variables. It does not prove these factors dominate the stock price in the current period and must not be used as a system buy/sell conclusion.",
  "llm_usage": "context_only",
  "interpretation_limit": "This mapping selects observation variables only and is not market evidence by itself."
}
```
## System Hypothesis and Risk Reminders
System-generated, must be questioned and manually verified.
- **Rule-based analysis and market regime**
  - category: `system_hypothesis`; type: `system_market_regime`
  - source: Stock-Pilot rule engine; endpoint: analyze_stock/detect_market_regime/select_models
  - as_of: 2026-05-22; fetched/recorded: 2026-05-25T02:56:10.079218
  - reliability: `H`; llm_usage: `hypothesis_only`; data_status: `available`
  - boundary: System-generated hypothesis only. Do not cite it as a fact.
  - payload: `{"analysis": {"trend": "震荡", "signal": "金叉", "support": "62/61", "resistance": "65/67", "summary": "当前RSI=58.3，位于中性区间。MACD维持多头结构，短线相对强势。短期均线呈下行态势。综合来看，短线处于震荡整理阶段"}, "market_regime": "事件驱动", "selected_models": ["催化剂模型", "预期差模型", "公司Alpha/行业Beta拆分模型"]}`


## Missing Data
- {"key": "orders_capacity", "label": "最新订单与产能利用率", "reason": "当前未接入公告/调研纪要/互动易等事件文本源", "possible_sources": ["投资者关系活动记录", "互动易", "定期报告", "公司公告"]}
- {"key": "northbound_flow", "label": "北向资金实时流向", "reason": "当前未接入陆股通持股或实时资金流数据", "possible_sources": ["深股通持股", "港交所披露", "交易所/行情数据源"]}
- {"key": "institution_holding", "label": "机构持仓变动", "reason": "当前未接入基金季报、十大流通股东或机构持仓聚合数据", "possible_sources": ["基金季报", "十大流通股东", "定期报告", "机构持仓数据库"]}
- {"key": "announcement_full_text", "label": "公告正文", "reason": "The system currently fetches announcement index information only and does not read full text. Do not infer order, capacity, or profit impact from the index title.", "possible_sources": ["公告URL", "PDF正文解析"]}
- {"key": "survey_full_text", "label": "调研正文", "reason": "The system currently fetches survey index information only and does not read full text. Do not infer survey conclusions, order status, or earnings impact from the index.", "possible_sources": ["公告URL", "调研纪要正文解析"]}
- {"key": "external_driver:tungsten_price_placeholder", "mapping_status": "unsupported", "reason": "Placeholder only; no market fact is retrieved and no conclusion should be drawn.", "future_extension": "Add a verified provider endpoint/code before enabling automatic retrieval."}
- {"key": "external_driver:pcb_sector_index_placeholder", "mapping_status": "unsupported", "reason": "Placeholder only; no market fact is retrieved and no conclusion should be drawn.", "future_extension": "Add a verified provider endpoint/code before enabling automatic retrieval."}

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