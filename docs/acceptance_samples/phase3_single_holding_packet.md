# Stock-Pilot Analysis Packet v1 - single_stock

## Privacy and External Sharing Boundary
This packet is generated locally and may contain personal account information, holdings, costs, cash, repo, trade plans, and manually entered evidence. Stock-Pilot does not send it to any external LLM, does not call deep analysis, and does not upload attachments automatically. External sharing happens only if the user actively copies, downloads, or submits the content elsewhere.

Quote-time boundary: Current quote source does not provide a verifiable quote time; portfolio snapshot time is not market quote time.
Default-risk boundary: Concentration or cash reminders may depend on system default placeholder parameters and are unconfirmed by the user.
Repo boundary: Repo amount is displayed separately from cash; cash-equivalent treatment is unconfirmed.

## Packet Metadata
- packet_id: packet_5e28f5d544ea453b9ec850cd20e4c4fd
- packet_version: analysis_packet.v1
- generated_at: 2026-05-24T21:56:04.046736
- analysis_scope: single_stock
- target_symbol: 000657
- target_name: Demo Composite Resource
- user_question: -
- market_data_as_of: 2026-05-24T21:56:04.039824
- daily_k_as_of: 2026-05-22
- portfolio_as_of: 2026-05-25T09:30:00
- source_snapshot_id: snap_966ab55a2f894eba8f43a0c38561915d

## Basic Information
```json
{
  "symbol": "000657",
  "name": "Demo Composite Resource",
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
    "has_holding": true,
    "quantity": 1000.0,
    "available_quantity": 800.0,
    "avg_cost": 9.0,
    "market_price": 10.0,
    "market_price_as_of": null,
    "market_price_time_status": "unavailable",
    "quote_time_boundary": "Current quote source does not provide a verifiable quote time; portfolio snapshot time is not market quote time.",
    "market_value": 10000.0,
    "unrealized_pnl": 1000.0,
    "unrealized_pnl_pct": 11.11,
    "portfolio_weight_pct": 10.0,
    "position_role": "short_term",
    "primary_theme": "METAL_RESOURCE",
    "theme_tags": [
      "METAL_RESOURCE",
      "TUNGSTEN",
      "HIGH_VOLATILITY",
      "COMPOSITE_EXPOSURE"
    ],
    "user_plan": "Demo plan: composite exposure should be reviewed separately.",
    "invalid_condition": "Demo invalid condition: composite risk becomes unclear.",
    "target_max_weight": 15.0,
    "data_status": "available",
    "missing_data": []
  },
  "data_status": "available"
}
```

## Auto Fact
- **Realtime quote snapshot**
  - category: `auto_fact`; type: `realtime_quote`
  - source: phase3_acceptance_demo_quote; endpoint: easyquotation.real
  - as_of: 2026-05-24T21:56:04.039824; fetched/recorded: 2026-05-24T21:56:04.039824
  - reliability: `B`; llm_usage: `fact_with_limit`; data_status: `available`
  - boundary: Quote data may be delayed and should not be interpreted as institutional intent.
  - payload: `{"symbol": "000657", "name": "Demo Composite Resource", "price": 10.0, "provider": "phase3_acceptance_demo_quote"}`
- **Local daily K summary**
  - category: `auto_fact`; type: `daily_k_summary`
  - source: local parquet base_market; endpoint: collector.get_history
  - as_of: 2026-05-22; fetched/recorded: 2026-05-24T21:56:04.039824
  - reliability: `B`; llm_usage: `fact_with_limit`; data_status: `available`
  - boundary: Local daily K is a market fact summary, not a trading conclusion.
  - payload: `{"row_count": 5000, "open": 57.24, "high": 62.38, "low": 57.2, "close": 62.38, "volume": 91808038.0, "amount": 5545023114.29, "pct_chg": 9.9982, "return_5d_pct": 10.49, "return_20d_pct": 7.91, "return_60d_pct": 19.02}`
- **Company profile**
  - category: `auto_fact`; type: `company_profile`
  - source: stock_meta/Tushare cache/rule inference; endpoint: build_company_profile
  - as_of: -; fetched/recorded: 2026-05-24T21:56:04.039824
  - reliability: `B`; llm_usage: `fact_with_limit`; data_status: `available`
  - boundary: Rule-inferred profile fields should be treated as bounded context, not formal disclosure.
  - payload: `{"company_name": "中钨高新", "main_business": "有色金属采选与深加工", "core_products": ["数控刀片", "硬质合金", "钨丝"], "industry_chain_position": "上游资源开采 + 中游深加工", "core_logic": ["高端刀具国产替代", "工业母机产业链", "战略金属管控", "央企资源整合预期", "国防装备采购"], "concept_tags": ["工业母机", "军工", "央企改革", "小金属", "硬质合金"], "company_type": ["军工"], "profit_driver": "钨价上涨 + 高端刀具放量", "competitive_advantage": "资源储量优势，产业链一体化", "risk_points": ["钨价下跌", "制造业需求回落"]}`
- **Data coverage**
  - category: `auto_fact`; type: `data_coverage`
  - source: data_coverage.py; endpoint: build_data_coverage
  - as_of: -; fetched/recorded: 2026-05-24T21:56:04.039824
  - reliability: `B`; llm_usage: `context_only`; data_status: `available`
  - boundary: Use this item to identify available and missing data, not as market evidence.
  - payload: `{"provided": [{"key": "company_business", "label": "主营业务及产品结构", "source": "本地公司画像/Tushare缓存/规则推断", "detail": {"main_business": "有色金属采选与深加工", "core_products": ["数控刀片", "硬质合金", "钨丝"], "industry_chain_position": "上游资源开采 + 中游深加工"}}, {"key": "price_overhang", "label": "前高与套牢区分布", "source": "本地日K线近250日", "detail": {"available": true, "previous_high": 71.5, "previous_high_date": "2026-03-03", "latest_close": 62.38, "distance_pct": -12.76, "overhang_volume_pct": 0.6, "source": "本地日K线近250日"}}], "missing": [{"key": "orders_capacity", "label": "最新订单与产能利用率", "reason": "当前未接入公告/调研纪要/互动易等事件文本源", "possible_sources": ["投资者关系活动记录", "互动易", "定期报告", "公司公告"]}, {"key": "northbound_flow", "label": "北向资金实时流向", "reason": "当前未接入陆股通持股或实时资金流数据", "possible_sources": ["深股通持股", "港交所披露", "交易所/行情数据源"]}, {"key": "institution_holding", "label": "机构持仓变动", "reason": "当前未接入基金季报、十大流通股东或机构持仓聚合数据", "possible_sources": ["基金季报", "十大流通股东", "定期报告", "机构持仓数据库"]}], "missing_labels": ["最新订单与产能利用率", "北向资金实时流向", "机构持仓变动"]}`
- **dragon_tiger_event unavailable**
  - category: `auto_fact`; type: `dragon_tiger_event`
  - source: Stock-Pilot fact service; endpoint: top_list,top_inst
  - as_of: -; fetched/recorded: 2026-05-24T21:56:04.046736
  - reliability: `B`; llm_usage: `context_only`; data_status: `unavailable`
  - boundary: Dragon-tiger facts are unavailable. When available, they reflect public abnormal-trading-day seat structure only, not long-term holding intent.
  - payload: `{"coverage": "dragon_tiger_event", "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN."}`
- **disclosure_index unavailable**
  - category: `auto_fact`; type: `disclosure_index`
  - source: Stock-Pilot fact service; endpoint: anns_d,stk_surv
  - as_of: -; fetched/recorded: 2026-05-24T21:56:04.047805
  - reliability: `B`; llm_usage: `context_only`; data_status: `unavailable`
  - boundary: Disclosure indexes are unavailable. When available, the system reads index data only, not announcement or survey full text.
  - payload: `{"coverage": "disclosure_index", "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN."}`

## Auto Signal
Auxiliary observations only; these are not factual conclusions or buy/sell instructions.
- **Technical indicators**
  - category: `auto_signal`; type: `technical_indicator`
  - source: indicators.py; endpoint: compute_indicators
  - as_of: 2026-05-22; fetched/recorded: 2026-05-24T21:56:04.039824
  - reliability: `C`; llm_usage: `weak_signal_only`; data_status: `available`
  - boundary: Technical indicators are auxiliary signals and must not be the sole basis for conclusions.
  - payload: `{"ma5": 57.04, "ma10": 58.35, "ma20": 58.02, "ma30": 55.93, "ma60": 55.88, "rsi14": 58.34, "macd": 1.17}`

## Manual Account
```json
{
  "has_holding": true,
  "quantity": 1000.0,
  "available_quantity": 800.0,
  "avg_cost": 9.0,
  "market_price": 10.0,
  "market_price_as_of": null,
  "market_price_time_status": "unavailable",
  "quote_time_boundary": "Current quote source does not provide a verifiable quote time; portfolio snapshot time is not market quote time.",
  "market_value": 10000.0,
  "unrealized_pnl": 1000.0,
  "unrealized_pnl_pct": 11.11,
  "portfolio_weight_pct": 10.0,
  "position_role": "short_term",
  "primary_theme": "METAL_RESOURCE",
  "theme_tags": [
    "METAL_RESOURCE",
    "TUNGSTEN",
    "HIGH_VOLATILITY",
    "COMPOSITE_EXPOSURE"
  ],
  "user_plan": "Demo plan: composite exposure should be reviewed separately.",
  "invalid_condition": "Demo invalid condition: composite risk becomes unclear.",
  "target_max_weight": 15.0,
  "data_status": "available",
  "missing_data": []
}
```

## Manual Evidence
- **Demo included shareholder-count note**
  - category: `manual_evidence`; type: `shareholder_count_manual`
  - source: phase3_acceptance_demo; endpoint: -
  - as_of: 2026-05-20; fetched/recorded: 2026-05-24T21:56:03.983841
  - reliability: `B_manual_structured`; llm_usage: `fact_with_limit`; data_status: `available`
  - boundary: 手动录入证据，仅在用户选择纳入分析包时使用；需保留来源与日期边界。
  - payload: `{"symbol": "000657", "evidence_type": "shareholder_count_manual", "title": "Demo included shareholder-count note", "value": null, "text": "Non-sensitive demo evidence: shareholder count manually entered for packet inclusion test.", "as_of_time": null, "as_of_date": "2026-05-20", "source": "phase3_acceptance_demo", "reliability": "B_manual_structured", "llm_usage": "fact_with_limit", "attachment_path": null, "image_reference": null, "notes": null, "include_in_analysis_packet": true, "holder_num": 12345, "end_date": null, "announcement_date": null, "change_from_previous": null, "screenshot": null, "evidence_id": "manual_1713ca701f11410881da246e831e5cca", "recorded_at": "2026-05-24T21:56:03.983841"}`
- **Demo included observation**
  - category: `manual_evidence`; type: `manual_market_observation`
  - source: phase3_acceptance_demo; endpoint: -
  - as_of: 2026-05-21; fetched/recorded: 2026-05-24T21:56:03.991681
  - reliability: `B_manual_structured`; llm_usage: `fact_with_limit`; data_status: `available`
  - boundary: 手动录入证据，仅在用户选择纳入分析包时使用；需保留来源与日期边界。
  - payload: `{"symbol": "000657", "evidence_type": "manual_market_observation", "title": "Demo included observation", "value": null, "text": "Non-sensitive demo observation used to verify manual evidence export.", "as_of_time": null, "as_of_date": "2026-05-21", "source": "phase3_acceptance_demo", "reliability": "B_manual_structured", "llm_usage": "fact_with_limit", "attachment_path": null, "image_reference": null, "notes": null, "include_in_analysis_packet": true, "holder_num": null, "end_date": null, "announcement_date": null, "change_from_previous": null, "screenshot": null, "evidence_id": "manual_e195015d0ec949a39c4738e3964d6170", "recorded_at": "2026-05-24T21:56:03.991681"}`

## System Hypothesis and Risk Reminders
System-generated, must be questioned and manually verified.
- **Rule-based analysis and market regime**
  - category: `system_hypothesis`; type: `system_market_regime`
  - source: Stock-Pilot rule engine; endpoint: analyze_stock/detect_market_regime/select_models
  - as_of: 2026-05-22; fetched/recorded: 2026-05-24T21:56:04.039824
  - reliability: `H`; llm_usage: `hypothesis_only`; data_status: `available`
  - boundary: System-generated hypothesis only. Do not cite it as a fact.
  - payload: `{"analysis": {"trend": "震荡", "signal": "金叉", "support": "10/10", "resistance": "10/10", "summary": "当前RSI=58.3，位于中性区间。MACD维持多头结构，短线相对强势。短期均线呈下行态势。综合来看，短线处于震荡整理阶段"}, "market_regime": "事件驱动", "selected_models": ["催化剂模型", "预期差模型", "公司Alpha/行业Beta拆分模型"]}`
- **Portfolio concentration reminder**
  - category: `system_hypothesis`; type: `-`
  - source: Stock-Pilot packet builder; endpoint: -
  - as_of: -; fetched/recorded: -
  - reliability: `H`; llm_usage: `hypothesis_only`; data_status: `available`
  - boundary: System-generated reminder only; manually question and verify it. Concentration or cash reminders may depend on system default placeholder parameters and are unconfirmed by the user.
  - payload: `{"symbol": "000657", "portfolio_weight_pct": 10.0, "primary_theme": "METAL_RESOURCE", "theme_tags": ["METAL_RESOURCE", "TUNGSTEN", "HIGH_VOLATILITY", "COMPOSITE_EXPOSURE"], "risk_parameter_source": "system_default_placeholder", "unconfirmed_by_user": true}`


## Missing Data
- {"key": "orders_capacity", "label": "最新订单与产能利用率", "reason": "当前未接入公告/调研纪要/互动易等事件文本源", "possible_sources": ["投资者关系活动记录", "互动易", "定期报告", "公司公告"]}
- {"key": "northbound_flow", "label": "北向资金实时流向", "reason": "当前未接入陆股通持股或实时资金流数据", "possible_sources": ["深股通持股", "港交所披露", "交易所/行情数据源"]}
- {"key": "institution_holding", "label": "机构持仓变动", "reason": "当前未接入基金季报、十大流通股东或机构持仓聚合数据", "possible_sources": ["基金季报", "十大流通股东", "定期报告", "机构持仓数据库"]}
- {"key": "announcement_full_text", "label": "公告正文", "reason": "The system currently fetches announcement index information only and does not read full text. Do not infer order, capacity, or profit impact from the index title.", "possible_sources": ["公告URL", "PDF正文解析"]}
- {"key": "survey_full_text", "label": "调研正文", "reason": "The system currently fetches survey index information only and does not read full text. Do not infer survey conclusions, order status, or earnings impact from the index.", "possible_sources": ["公告URL", "调研纪要正文解析"]}

## Interpretation Boundaries
- Automatic shareholder count is not available in this stage.
- Automatic unlock event data is not available in this stage.
- Announcement full text is not read unless manually entered; do not infer business or profit impact from an index title.
- Dragon-tiger list data shows public abnormal trading seat structure only and does not prove long-term capital commitment.
- Moneyflow, margin financing, sector baskets, FX, futures, backtesting, and broker sync are not included in this stage.
- Manual account data uses the user's local snapshot time and may be stale.
- Realtime quote data and low-frequency facts may have different timestamps.
- The current quote provider does not expose a verifiable quote timestamp for portfolio enrichment; portfolio snapshot time is not market quote time.
- Concentration and cash reminders may depend on system default placeholder parameters that have not been confirmed by the user.
- Repo amount is shown separately. It is not treated as fully equivalent to cash unless the user confirms that convention.

## Neutral Questions for an External LLM
- Which items in this packet are hard facts, and which are weak auxiliary signals?
- Does the current holding, if any, create excessive theme exposure inside the portfolio?
- Which missing information would most materially change the analysis?
- Is the user's invalid condition specific enough to falsify the trade plan?
- What are the main risks under bullish, neutral, and adverse market scenarios?

No buy/sell recommendation is generated by this packet.