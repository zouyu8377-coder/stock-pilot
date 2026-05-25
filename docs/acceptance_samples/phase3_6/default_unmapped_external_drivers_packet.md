# Stock-Pilot Analysis Packet v1 - single_stock

## Privacy and External Sharing Boundary
This packet is generated locally and may contain personal account information, holdings, costs, cash, repo, trade plans, and manually entered evidence. Stock-Pilot does not send it to any external LLM, does not call deep analysis, and does not upload attachments automatically. External sharing happens only if the user actively copies, downloads, or submits the content elsewhere.

Quote-time boundary: Current quote source does not provide a verifiable quote time; portfolio snapshot time is not market quote time.
Default-risk boundary: Concentration or cash reminders may depend on system default placeholder parameters and are unconfirmed by the user.
Repo boundary: Repo amount is displayed separately from cash; cash-equivalent treatment is unconfirmed.

## Packet Metadata
- packet_id: packet_6a6f17dc16ee40e198b46cfbcc907af5
- packet_version: analysis_packet.v1
- generated_at: 2026-05-25T02:56:10.244657
- analysis_scope: single_stock
- target_symbol: 600000
- target_name: 浦发银行
- user_question: 验收样例：未映射普通股外部驱动
- market_data_as_of: 2026-05-25T02:56:10.239342
- daily_k_as_of: 2026-05-22
- portfolio_as_of: -
- source_snapshot_id: snap_77c3fc3dadd846bab33483b3d71739ec

## Basic Information
```json
{
  "symbol": "600000",
  "name": "浦发银行",
  "industry": null,
  "area": null,
  "listing_information": {
    "list_date": null,
    "exchange": null
  },
  "company_profile": {
    "company_name": "浦发银行",
    "main_business": "存贷款、理财、投行等金融服务",
    "core_products": [
      "贷款",
      "理财",
      "投行服务"
    ],
    "industry_chain_position": "金融服务端",
    "core_logic": [
      "息差修复",
      "资产质量改善",
      "高股息防御"
    ],
    "concept_tags": [],
    "company_type": [
      "金融股"
    ],
    "profit_driver": "净息差 + 资产规模扩张",
    "competitive_advantage": "网点覆盖广，客户基础稳",
    "risk_points": [
      "息差收窄",
      "地产不良暴露",
      "宏观经济下行"
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
  - as_of: 2026-05-25T02:56:10.239342; fetched/recorded: 2026-05-25T02:56:10.239342
  - reliability: `B`; llm_usage: `fact_with_limit`; data_status: `available`
  - boundary: Quote data may be delayed and should not be interpreted as institutional intent.
  - payload: `{"symbol": "600000", "price": 9.09, "change_pct": 1.45, "name": "浦发银行", "volume": 59945900.0, "provider": "easyquotation", "hot_status": "ready", "market_cap": 3027.5, "float_market_cap": 3027.5, "pe": 6.02, "pb": 0.4, "turnover_rate": 0.18, "volume_ratio": 1.57}`
- **Local daily K summary**
  - category: `auto_fact`; type: `daily_k_summary`
  - source: local parquet base_market; endpoint: collector.get_history
  - as_of: 2026-05-22; fetched/recorded: 2026-05-25T02:56:10.239342
  - reliability: `B`; llm_usage: `fact_with_limit`; data_status: `available`
  - boundary: Local daily K is a market fact summary, not a trading conclusion.
  - payload: `{"row_count": 5000, "open": 8.88, "high": 9.03, "low": 8.75, "close": 8.96, "volume": 99003358.0, "amount": 883300246.96, "pct_chg": 1.1287, "return_5d_pct": -1.21, "return_20d_pct": -7.82, "return_60d_pct": -9.4}`
- **Company profile**
  - category: `auto_fact`; type: `company_profile`
  - source: stock_meta/Tushare cache/rule inference; endpoint: build_company_profile
  - as_of: -; fetched/recorded: 2026-05-25T02:56:10.239342
  - reliability: `B`; llm_usage: `context_only`; data_status: `available`
  - boundary: Company profile may mix Tushare fields and rule-inferred fields; treat it as bounded context, not formal disclosure or a hard fact.
  - payload: `{"company_name": "浦发银行", "main_business": "存贷款、理财、投行等金融服务", "core_products": ["贷款", "理财", "投行服务"], "industry_chain_position": "金融服务端", "core_logic": ["息差修复", "资产质量改善", "高股息防御"], "concept_tags": [], "company_type": ["金融股"], "profit_driver": "净息差 + 资产规模扩张", "competitive_advantage": "网点覆盖广，客户基础稳", "risk_points": ["息差收窄", "地产不良暴露", "宏观经济下行"]}`
- **Data coverage**
  - category: `auto_fact`; type: `data_coverage`
  - source: data_coverage.py; endpoint: build_data_coverage
  - as_of: -; fetched/recorded: 2026-05-25T02:56:10.239342
  - reliability: `B`; llm_usage: `context_only`; data_status: `available`
  - boundary: Use this item to identify available and missing data, not as market evidence.
  - payload: `{"provided": [{"key": "company_business", "label": "主营业务及产品结构", "source": "本地公司画像/Tushare缓存/规则推断", "detail": {"main_business": "存贷款、理财、投行等金融服务", "core_products": ["贷款", "理财", "投行服务"], "industry_chain_position": "金融服务端"}}, {"key": "price_overhang", "label": "前高与套牢区分布", "source": "本地日K线近250日", "detail": {"available": true, "previous_high": 14.8, "previous_high_date": "2025-07-07", "latest_close": 8.96, "distance_pct": -39.46, "overhang_volume_pct": 4.59, "source": "本地日K线近250日"}}], "missing": [{"key": "orders_capacity", "label": "最新订单与产能利用率", "reason": "当前未接入公告/调研纪要/互动易等事件文本源", "possible_sources": ["投资者关系活动记录", "互动易", "定期报告", "公司公告"]}, {"key": "northbound_flow", "label": "北向资金实时流向", "reason": "当前未接入陆股通持股或实时资金流数据", "possible_sources": ["深股通持股", "港交所披露", "交易所/行情数据源"]}, {"key": "institution_holding", "label": "机构持仓变动", "reason": "当前未接入基金季报、十大流通股东或机构持仓聚合数据", "possible_sources": ["基金季报", "十大流通股东", "定期报告", "机构持仓数据库"]}], "missing_labels": ["最新订单与产能利用率", "北向资金实时流向", "机构持仓变动"]}`
- **dragon_tiger_event unavailable**
  - category: `auto_fact`; type: `dragon_tiger_event`
  - source: Stock-Pilot fact service; endpoint: top_list,top_inst
  - as_of: -; fetched/recorded: 2026-05-25T02:56:10.244657
  - reliability: `B`; llm_usage: `context_only`; data_status: `unavailable`
  - boundary: Dragon-tiger facts are unavailable. When available, they reflect public abnormal-trading-day seat structure only, not long-term holding intent.
  - payload: `{"coverage": "dragon_tiger_event", "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN."}`
- **disclosure_index unavailable**
  - category: `auto_fact`; type: `disclosure_index`
  - source: Stock-Pilot fact service; endpoint: anns_d,stk_surv
  - as_of: -; fetched/recorded: 2026-05-25T02:56:10.245566
  - reliability: `B`; llm_usage: `context_only`; data_status: `unavailable`
  - boundary: Disclosure indexes are unavailable. When available, the system reads index data only, not announcement or survey full text.
  - payload: `{"coverage": "disclosure_index", "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN."}`

## Auto Signal
Auxiliary observations only; these are not factual conclusions or buy/sell instructions.
- **Technical indicators**
  - category: `auto_signal`; type: `technical_indicator`
  - source: indicators.py; endpoint: compute_indicators
  - as_of: 2026-05-22; fetched/recorded: 2026-05-25T02:56:10.239342
  - reliability: `C`; llm_usage: `weak_signal_only`; data_status: `available`
  - boundary: Technical indicators are auxiliary signals and must not be the sole basis for conclusions.
  - payload: `{"ma5": 8.96, "ma10": 9.0, "ma20": 9.17, "ma30": 9.42, "ma60": 9.72, "rsi14": 23.08, "macd": -0.23}`

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
  "mapping_status": "not_configured",
  "profile_id": "DEFAULT_UNMAPPED_V1",
  "symbol": "600000.SH",
  "message": "当前未为该标的配置专属外部驱动因子。系统仅保留个股自身证据，不自动附加商品、汇率或板块驱动。",
  "future_extension": "可在后续根据行业、主题或用户观察需求新增映射。",
  "drivers": [],
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
  - as_of: 2026-05-22; fetched/recorded: 2026-05-25T02:56:10.239342
  - reliability: `H`; llm_usage: `hypothesis_only`; data_status: `available`
  - boundary: System-generated hypothesis only. Do not cite it as a fact.
  - payload: `{"analysis": {"trend": "震荡", "signal": "超卖", "support": "9/9", "resistance": "9/10", "summary": "当前RSI=23.1，短线进入超卖区域，存在技术性反弹需求。MACD仍处于空头区间，趋势偏弱。短期均线呈下行态势。综合来看，短线处于震荡整理阶段"}, "market_regime": "震荡观察", "selected_models": ["风险收益比模型", "公司Alpha/行业Beta拆分模型", "预期差模型"]}`


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