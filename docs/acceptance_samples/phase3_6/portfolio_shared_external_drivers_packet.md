# Stock-Pilot Analysis Packet v1 - portfolio

## Privacy and External Sharing Boundary
This packet is generated locally and may contain personal account information, holdings, costs, cash, repo, trade plans, and manually entered evidence. Stock-Pilot does not send it to any external LLM, does not call deep analysis, and does not upload attachments automatically. External sharing happens only if the user actively copies, downloads, or submits the content elsewhere.

Quote-time boundary: Current quote source does not provide a verifiable quote time; portfolio snapshot time is not market quote time.
Default-risk boundary: Concentration or cash reminders may depend on system default placeholder parameters and are unconfirmed by the user.
Repo boundary: Repo amount is displayed separately from cash; cash-equivalent treatment is unconfirmed.

## Packet Metadata
- packet_id: packet_d7331ee6adb249ff9aedde0a414ab16b
- packet_version: analysis_packet.v1
- generated_at: 2026-05-25T02:57:32.348421
- analysis_scope: portfolio
- portfolio_id: local_default
- portfolio_as_of: 2026-05-25T02:57:19.719742
- source_snapshot_id: snap_1e8b10f5f2e04f279492a540e63d5a96
- user_question: 验收样例：组合共享外部驱动

## Account Overview
```json
{
  "total_assets": 81282.5,
  "total_market_value": 31282.5,
  "cash_available": 30000.0,
  "repo_amount": 20000.0,
  "repo_available_date": null,
  "total_position_weight": 38.49,
  "cash_weight": 36.91,
  "repo_weight": 24.61,
  "invested_ratio_pct": 38.49,
  "cash_ratio_pct": 36.91,
  "repo_ratio_pct": 24.61,
  "repo_policy": {
    "cash_equivalent_treatment": "unconfirmed",
    "boundary": "Repo amount is displayed separately from cash; cash-equivalent treatment is unconfirmed."
  },
  "notes": null
}
```

## Current Holdings
```json
[
  {
    "symbol": "601899.SH",
    "name": "紫金矿业",
    "quantity": 100.0,
    "available_quantity": null,
    "avg_cost": 15.0,
    "position_role": "core",
    "theme_tags": [
      "METAL_RESOURCE"
    ],
    "primary_theme": "METAL_RESOURCE",
    "user_plan": "",
    "invalid_condition": null,
    "target_max_weight": null,
    "notes": null,
    "market_price": 31.27,
    "market_value": 3127.0,
    "unrealized_pnl": 1627.0,
    "unrealized_pnl_pct": 108.47,
    "price_source": "easyquotation",
    "data_status": "available",
    "missing_data": [],
    "portfolio_weight_pct": 3.85,
    "weight_pct": 3.85,
    "market_price_as_of": null,
    "market_price_time_status": "unavailable",
    "quote_time_boundary": "Current quote source does not provide a verifiable quote time; portfolio snapshot time is not market quote time."
  },
  {
    "symbol": "603993.SH",
    "name": "洛阳钼业",
    "quantity": 100.0,
    "available_quantity": null,
    "avg_cost": 8.0,
    "position_role": "core",
    "theme_tags": [
      "METAL_RESOURCE"
    ],
    "primary_theme": "METAL_RESOURCE",
    "user_plan": "",
    "invalid_condition": null,
    "target_max_weight": null,
    "notes": null,
    "market_price": 19.24,
    "market_value": 1924.0,
    "unrealized_pnl": 1124.0,
    "unrealized_pnl_pct": 140.5,
    "price_source": "easyquotation",
    "data_status": "available",
    "missing_data": [],
    "portfolio_weight_pct": 2.37,
    "weight_pct": 2.37,
    "market_price_as_of": null,
    "market_price_time_status": "unavailable",
    "quote_time_boundary": "Current quote source does not provide a verifiable quote time; portfolio snapshot time is not market quote time."
  },
  {
    "symbol": "000657.SZ",
    "name": "中钨高新",
    "quantity": 100.0,
    "available_quantity": null,
    "avg_cost": 10.0,
    "position_role": "trend",
    "theme_tags": [
      "METAL_RESOURCE",
      "AI_PCB",
      "COMPOSITE_EXPOSURE"
    ],
    "primary_theme": "METAL_RESOURCE",
    "user_plan": "",
    "invalid_condition": null,
    "target_max_weight": null,
    "notes": null,
    "market_price": 63.78,
    "market_value": 6378.0,
    "unrealized_pnl": 5378.0,
    "unrealized_pnl_pct": 537.8,
    "price_source": "easyquotation",
    "data_status": "available",
    "missing_data": [],
    "portfolio_weight_pct": 7.85,
    "weight_pct": 7.85,
    "market_price_as_of": null,
    "market_price_time_status": "unavailable",
    "quote_time_boundary": "Current quote source does not provide a verifiable quote time; portfolio snapshot time is not market quote time."
  },
  {
    "symbol": "002916.SZ",
    "name": "深南电路",
    "quantity": 50.0,
    "available_quantity": null,
    "avg_cost": 80.0,
    "position_role": "core",
    "theme_tags": [
      "AI_PCB"
    ],
    "primary_theme": "AI_PCB",
    "user_plan": "",
    "invalid_condition": null,
    "target_max_weight": null,
    "notes": null,
    "market_price": 397.07,
    "market_value": 19853.5,
    "unrealized_pnl": 15853.5,
    "unrealized_pnl_pct": 396.34,
    "price_source": "easyquotation",
    "data_status": "available",
    "missing_data": [],
    "portfolio_weight_pct": 24.43,
    "weight_pct": 24.43,
    "market_price_as_of": null,
    "market_price_time_status": "unavailable",
    "quote_time_boundary": "Current quote source does not provide a verifiable quote time; portfolio snapshot time is not market quote time."
  }
]
```

## Primary Theme Exposure
Unique attribution by `primary_theme`; this is the additive theme exposure view.
```json
[
  {
    "theme": "AI_PCB",
    "market_value": 19853.5,
    "weight_pct": 24.43,
    "symbols": [
      "002916.SZ"
    ]
  },
  {
    "theme": "METAL_RESOURCE",
    "market_value": 11429.0,
    "weight_pct": 14.06,
    "symbols": [
      "601899.SH",
      "603993.SH",
      "000657.SZ"
    ]
  }
]
```

## Related Risk Observations
Primary theme exposure is unique attribution. Theme tag observations are non-additive and must not be summed as asset weights.
```json
{
  "risk_tag_exposure": [
    {
      "theme": "AI_PCB",
      "market_value": 26231.5,
      "weight_pct": 32.27,
      "symbols": [
        "000657.SZ",
        "002916.SZ"
      ]
    },
    {
      "theme": "METAL_RESOURCE",
      "market_value": 11429.0,
      "weight_pct": 14.06,
      "symbols": [
        "000657.SZ",
        "601899.SH",
        "603993.SH"
      ]
    }
  ],
  "composite_exposure_notes": [
    {
      "symbol": "000657.SZ",
      "theme_tags": [
        "METAL_RESOURCE",
        "AI_PCB",
        "COMPOSITE_EXPOSURE"
      ],
      "message": "Composite exposure: this holding has multiple risk tags. It is counted once in primary_theme exposure and must not be double counted through tags."
    }
  ],
  "boundary": "Primary theme exposure is unique attribution. Theme tag observations are non-additive and must not be summed as asset weights."
}
```

## System Hypothesis and Risk Reminders
System-generated hypotheses only; not facts and not trading advice.
- No available evidence in this section.

## Manual Evidence
- No available evidence in this section.

## Auto Fact Summary
```json
[
  {
    "symbol": "601899.SH",
    "coverage": "dragon_tiger_and_disclosure_index",
    "data_status": "unavailable",
    "evidence": [],
    "boundary": "Indexes and public event facts are bounded context only; no announcement body or long-term fund intent is inferred.",
    "missing_reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN."
  },
  {
    "symbol": "603993.SH",
    "coverage": "dragon_tiger_and_disclosure_index",
    "data_status": "unavailable",
    "evidence": [],
    "boundary": "Indexes and public event facts are bounded context only; no announcement body or long-term fund intent is inferred.",
    "missing_reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN."
  },
  {
    "symbol": "000657.SZ",
    "coverage": "dragon_tiger_and_disclosure_index",
    "data_status": "unavailable",
    "evidence": [],
    "boundary": "Indexes and public event facts are bounded context only; no announcement body or long-term fund intent is inferred.",
    "missing_reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN."
  },
  {
    "symbol": "002916.SZ",
    "coverage": "dragon_tiger_and_disclosure_index",
    "data_status": "unavailable",
    "evidence": [],
    "boundary": "Indexes and public event facts are bounded context only; no announcement body or long-term fund intent is inferred.",
    "missing_reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN."
  }
]
```

## External Driver Summary
Symbol-level external-driver observations only; not macro scoring or trading advice.
```json
[
  {
    "type": "shared_driver",
    "factor_id": "copper_futures",
    "display_name": "Copper futures daily price",
    "factor_type": "commodity",
    "associated_symbols": [
      "601899.SH",
      "603993.SH",
      "000657.SZ"
    ],
    "evidence": {
      "evidence_id": "ev_5d669a6510fb48e19892548c7f8955e0",
      "symbol": "601899.SH",
      "evidence_type": "external_driver_fact",
      "category": "auto_fact",
      "title": "External driver unavailable: Copper futures daily price",
      "value": null,
      "payload": {
        "factor_id": "copper_futures",
        "display_name": "Copper futures daily price",
        "factor_type": "commodity",
        "data_status": "unavailable",
        "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN.",
        "mapping_boundary": "External-driver mapping is a product configuration used to select observation variables. It does not prove these factors dominate the stock price in the current period and must not be used as a system buy/sell conclusion."
      },
      "source": "tushare.fut_daily",
      "source_endpoint": "fut_daily",
      "as_of_time": null,
      "as_of_date": null,
      "fetched_at": "2026-05-25T02:57:32.349414",
      "reliability": "B",
      "llm_usage": "context_only",
      "interpretation_limit": "External-driver facts are related background observations only. They do not imply a direct causal effect, valuation impact, or buy/sell conclusion.",
      "freshness_days": null,
      "data_status": "unavailable",
      "notes": null
    }
  },
  {
    "type": "shared_driver",
    "factor_id": "usd_cnh",
    "display_name": "USD/CNH daily FX",
    "factor_type": "fx",
    "associated_symbols": [
      "601899.SH",
      "603993.SH"
    ],
    "evidence": {
      "evidence_id": "ev_fd46413f3cec41bf972c2a603cf4ee73",
      "symbol": "601899.SH",
      "evidence_type": "external_driver_fact",
      "category": "auto_fact",
      "title": "External driver unavailable: USD/CNH daily FX",
      "value": null,
      "payload": {
        "factor_id": "usd_cnh",
        "display_name": "USD/CNH daily FX",
        "factor_type": "fx",
        "data_status": "unavailable",
        "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN.",
        "mapping_boundary": "External-driver mapping is a product configuration used to select observation variables. It does not prove these factors dominate the stock price in the current period and must not be used as a system buy/sell conclusion."
      },
      "source": "tushare.fx_daily",
      "source_endpoint": "fx_daily",
      "as_of_time": null,
      "as_of_date": null,
      "fetched_at": "2026-05-25T02:57:32.350427",
      "reliability": "B",
      "llm_usage": "context_only",
      "interpretation_limit": "External-driver facts are related background observations only. They do not imply a direct causal effect, valuation impact, or buy/sell conclusion.",
      "freshness_days": null,
      "data_status": "unavailable",
      "notes": null
    }
  },
  {
    "type": "shared_driver",
    "factor_id": "gold_etf_159934",
    "display_name": "Gold ETF share, NAV, and price",
    "factor_type": "theme_etf",
    "associated_symbols": [
      "601899.SH"
    ],
    "evidence": {
      "evidence_id": "ev_9a2df977486747649fa54d5a6aa7d884",
      "symbol": "601899.SH",
      "evidence_type": "external_driver_fact",
      "category": "auto_fact",
      "title": "External driver unavailable: Gold ETF share, NAV, and price",
      "value": null,
      "payload": {
        "factor_id": "gold_etf_159934",
        "display_name": "Gold ETF share, NAV, and price",
        "factor_type": "theme_etf",
        "data_status": "unavailable",
        "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN.",
        "mapping_boundary": "External-driver mapping is a product configuration used to select observation variables. It does not prove these factors dominate the stock price in the current period and must not be used as a system buy/sell conclusion."
      },
      "source": "tushare.etf_share_size,fund_nav,fund_daily",
      "source_endpoint": "etf_share_size,fund_nav,fund_daily",
      "as_of_time": null,
      "as_of_date": null,
      "fetched_at": "2026-05-25T02:57:32.350427",
      "reliability": "B",
      "llm_usage": "context_only",
      "interpretation_limit": "External-driver facts are related background observations only. They do not imply a direct causal effect, valuation impact, or buy/sell conclusion.",
      "freshness_days": null,
      "data_status": "unavailable",
      "notes": null
    }
  },
  {
    "type": "shared_driver",
    "factor_id": "ai_theme_etf_159382",
    "display_name": "AI theme ETF share, NAV, and price",
    "factor_type": "theme_etf",
    "associated_symbols": [
      "000657.SZ",
      "002916.SZ"
    ],
    "evidence": {
      "evidence_id": "ev_bbb3f21b9d434cb5aa1209d7d72c49e6",
      "symbol": "000657.SZ",
      "evidence_type": "external_driver_fact",
      "category": "auto_fact",
      "title": "External driver unavailable: AI theme ETF share, NAV, and price",
      "value": null,
      "payload": {
        "factor_id": "ai_theme_etf_159382",
        "display_name": "AI theme ETF share, NAV, and price",
        "factor_type": "theme_etf",
        "data_status": "unavailable",
        "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN.",
        "mapping_boundary": "External-driver mapping is a product configuration used to select observation variables. It does not prove these factors dominate the stock price in the current period and must not be used as a system buy/sell conclusion."
      },
      "source": "tushare.etf_share_size,fund_nav,fund_daily",
      "source_endpoint": "etf_share_size,fund_nav,fund_daily",
      "as_of_time": null,
      "as_of_date": null,
      "fetched_at": "2026-05-25T02:57:32.352429",
      "reliability": "B",
      "llm_usage": "context_only",
      "interpretation_limit": "External-driver facts are related background observations only. They do not imply a direct causal effect, valuation impact, or buy/sell conclusion.",
      "freshness_days": null,
      "data_status": "unavailable",
      "notes": null
    }
  },
  {
    "type": "symbol_mapping",
    "symbol": "601899.SH",
    "primary_theme": "METAL_RESOURCE",
    "mapping": {
      "mapping_status": "configured",
      "profile_id": "ZIJIN_RESOURCE_METALS_V1",
      "symbol": "601899.SH",
      "message": "已为该标的配置专属外部驱动观察因子；这些因子仅用于筛选背景变量。",
      "future_extension": "可继续增加经用户确认且接口代码已验证的行业、商品或主题映射。",
      "drivers": [
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
          "factor_id": "gold_futures",
          "display_name": "Gold futures daily price",
          "factor_type": "commodity",
          "importance": "conditional",
          "retrieval_config": {
            "provider": "tushare",
            "endpoint": "fut_daily",
            "provider_symbol": null,
            "code": null
          },
          "inclusion_reason": "Gold exposure can be relevant for precious-metal miners and gold-themed instruments.",
          "interpretation_limit": "Gold futures provider code still requires a successful probe before automatic retrieval.",
          "status": "pending_probe"
        },
        {
          "factor_id": "usd_cnh",
          "display_name": "USD/CNH daily FX",
          "factor_type": "fx",
          "importance": "context",
          "retrieval_config": {
            "provider": "tushare",
            "endpoint": "fx_daily",
            "provider_symbol": "USDCNH.FXCM",
            "code": "USDCNH.FXCM"
          },
          "inclusion_reason": "FX can affect globally priced commodities and overseas revenue/cost translation.",
          "interpretation_limit": "FX is context only and must not be treated as a direct driver without separate evidence.",
          "status": "configured"
        },
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
    },
    "data_status": "available",
    "evidence": [
      {
        "evidence_id": "ev_5d669a6510fb48e19892548c7f8955e0",
        "symbol": "601899.SH",
        "evidence_type": "external_driver_fact",
        "category": "auto_fact",
        "title": "External driver unavailable: Copper futures daily price",
        "value": null,
        "payload": {
          "factor_id": "copper_futures",
          "display_name": "Copper futures daily price",
          "factor_type": "commodity",
          "data_status": "unavailable",
          "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN.",
          "mapping_boundary": "External-driver mapping is a product configuration used to select observation variables. It does not prove these factors dominate the stock price in the current period and must not be used as a system buy/sell conclusion."
        },
        "source": "tushare.fut_daily",
        "source_endpoint": "fut_daily",
        "as_of_time": null,
        "as_of_date": null,
        "fetched_at": "2026-05-25T02:57:32.349414",
        "reliability": "B",
        "llm_usage": "context_only",
        "interpretation_limit": "External-driver facts are related background observations only. They do not imply a direct causal effect, valuation impact, or buy/sell conclusion.",
        "freshness_days": null,
        "data_status": "unavailable",
        "notes": null
      },
      {
        "evidence_id": "ev_fd46413f3cec41bf972c2a603cf4ee73",
        "symbol": "601899.SH",
        "evidence_type": "external_driver_fact",
        "category": "auto_fact",
        "title": "External driver unavailable: USD/CNH daily FX",
        "value": null,
        "payload": {
          "factor_id": "usd_cnh",
          "display_name": "USD/CNH daily FX",
          "factor_type": "fx",
          "data_status": "unavailable",
          "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN.",
          "mapping_boundary": "External-driver mapping is a product configuration used to select observation variables. It does not prove these factors dominate the stock price in the current period and must not be used as a system buy/sell conclusion."
        },
        "source": "tushare.fx_daily",
        "source_endpoint": "fx_daily",
        "as_of_time": null,
        "as_of_date": null,
        "fetched_at": "2026-05-25T02:57:32.350427",
        "reliability": "B",
        "llm_usage": "context_only",
        "interpretation_limit": "External-driver facts are related background observations only. They do not imply a direct causal effect, valuation impact, or buy/sell conclusion.",
        "freshness_days": null,
        "data_status": "unavailable",
        "notes": null
      },
      {
        "evidence_id": "ev_9a2df977486747649fa54d5a6aa7d884",
        "symbol": "601899.SH",
        "evidence_type": "external_driver_fact",
        "category": "auto_fact",
        "title": "External driver unavailable: Gold ETF share, NAV, and price",
        "value": null,
        "payload": {
          "factor_id": "gold_etf_159934",
          "display_name": "Gold ETF share, NAV, and price",
          "factor_type": "theme_etf",
          "data_status": "unavailable",
          "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN.",
          "mapping_boundary": "External-driver mapping is a product configuration used to select observation variables. It does not prove these factors dominate the stock price in the current period and must not be used as a system buy/sell conclusion."
        },
        "source": "tushare.etf_share_size,fund_nav,fund_daily",
        "source_endpoint": "etf_share_size,fund_nav,fund_daily",
        "as_of_time": null,
        "as_of_date": null,
        "fetched_at": "2026-05-25T02:57:32.350427",
        "reliability": "B",
        "llm_usage": "context_only",
        "interpretation_limit": "External-driver facts are related background observations only. They do not imply a direct causal effect, valuation impact, or buy/sell conclusion.",
        "freshness_days": null,
        "data_status": "unavailable",
        "notes": null
      }
    ],
    "derived_observations": [],
    "missing_data": [
      {
        "key": "external_driver:gold_futures",
        "mapping_status": "pending_probe",
        "reason": "Gold futures provider code still requires a successful probe before automatic retrieval.",
        "future_extension": "Add a verified provider endpoint/code before enabling automatic retrieval."
      }
    ]
  },
  {
    "type": "symbol_mapping",
    "symbol": "603993.SH",
    "primary_theme": "METAL_RESOURCE",
    "mapping": {
      "mapping_status": "configured",
      "profile_id": "LUOMO_RESOURCE_METALS_V1",
      "symbol": "603993.SH",
      "message": "已为该标的配置专属外部驱动观察因子；这些因子仅用于筛选背景变量。",
      "future_extension": "可继续增加经用户确认且接口代码已验证的行业、商品或主题映射。",
      "drivers": [
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
          "factor_id": "usd_cnh",
          "display_name": "USD/CNH daily FX",
          "factor_type": "fx",
          "importance": "context",
          "retrieval_config": {
            "provider": "tushare",
            "endpoint": "fx_daily",
            "provider_symbol": "USDCNH.FXCM",
            "code": "USDCNH.FXCM"
          },
          "inclusion_reason": "FX can affect globally priced commodities and overseas revenue/cost translation.",
          "interpretation_limit": "FX is context only and must not be treated as a direct driver without separate evidence.",
          "status": "configured"
        },
        {
          "factor_id": "cobalt_moly_price_placeholder",
          "display_name": "Cobalt/Molybdenum price placeholder",
          "factor_type": "unsupported_placeholder",
          "importance": "conditional",
          "retrieval_config": {
            "provider": "stock-pilot",
            "endpoint": "not_configured",
            "provider_symbol": null,
            "code": null
          },
          "inclusion_reason": "No verified cobalt or molybdenum daily series is configured in this round.",
          "interpretation_limit": "Placeholder only; no market fact is retrieved and no conclusion should be drawn.",
          "status": "unsupported"
        },
        {
          "factor_id": "resource_sector_index_placeholder",
          "display_name": "Resource sector index placeholder",
          "factor_type": "unsupported_placeholder",
          "importance": "conditional",
          "retrieval_config": {
            "provider": "stock-pilot",
            "endpoint": "not_configured",
            "provider_symbol": null,
            "code": null
          },
          "inclusion_reason": "Resource sector index mapping needs a verified provider code before automatic retrieval.",
          "interpretation_limit": "Placeholder only; no market fact is retrieved and no conclusion should be drawn.",
          "status": "unsupported"
        }
      ],
      "boundary": "External-driver mapping is a product configuration used to select observation variables. It does not prove these factors dominate the stock price in the current period and must not be used as a system buy/sell conclusion.",
      "llm_usage": "context_only",
      "interpretation_limit": "This mapping selects observation variables only and is not market evidence by itself."
    },
    "data_status": "available",
    "evidence": [
      {
        "evidence_id": "ev_a09de08f71d445878adbc63069632917",
        "symbol": "603993.SH",
        "evidence_type": "external_driver_fact",
        "category": "auto_fact",
        "title": "External driver unavailable: Copper futures daily price",
        "value": null,
        "payload": {
          "factor_id": "copper_futures",
          "display_name": "Copper futures daily price",
          "factor_type": "commodity",
          "data_status": "unavailable",
          "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN.",
          "mapping_boundary": "External-driver mapping is a product configuration used to select observation variables. It does not prove these factors dominate the stock price in the current period and must not be used as a system buy/sell conclusion."
        },
        "source": "tushare.fut_daily",
        "source_endpoint": "fut_daily",
        "as_of_time": null,
        "as_of_date": null,
        "fetched_at": "2026-05-25T02:57:32.351424",
        "reliability": "B",
        "llm_usage": "context_only",
        "interpretation_limit": "External-driver facts are related background observations only. They do not imply a direct causal effect, valuation impact, or buy/sell conclusion.",
        "freshness_days": null,
        "data_status": "unavailable",
        "notes": null
      },
      {
        "evidence_id": "ev_e26e9993bf2a4342b8273ef88d2ff596",
        "symbol": "603993.SH",
        "evidence_type": "external_driver_fact",
        "category": "auto_fact",
        "title": "External driver unavailable: USD/CNH daily FX",
        "value": null,
        "payload": {
          "factor_id": "usd_cnh",
          "display_name": "USD/CNH daily FX",
          "factor_type": "fx",
          "data_status": "unavailable",
          "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN.",
          "mapping_boundary": "External-driver mapping is a product configuration used to select observation variables. It does not prove these factors dominate the stock price in the current period and must not be used as a system buy/sell conclusion."
        },
        "source": "tushare.fx_daily",
        "source_endpoint": "fx_daily",
        "as_of_time": null,
        "as_of_date": null,
        "fetched_at": "2026-05-25T02:57:32.351424",
        "reliability": "B",
        "llm_usage": "context_only",
        "interpretation_limit": "External-driver facts are related background observations only. They do not imply a direct causal effect, valuation impact, or buy/sell conclusion.",
        "freshness_days": null,
        "data_status": "unavailable",
        "notes": null
      }
    ],
    "derived_observations": [],
    "missing_data": [
      {
        "key": "external_driver:cobalt_moly_price_placeholder",
        "mapping_status": "unsupported",
        "reason": "Placeholder only; no market fact is retrieved and no conclusion should be drawn.",
        "future_extension": "Add a verified provider endpoint/code before enabling automatic retrieval."
      },
      {
        "key": "external_driver:resource_sector_index_placeholder",
        "mapping_status": "unsupported",
        "reason": "Placeholder only; no market fact is retrieved and no conclusion should be drawn.",
        "future_extension": "Add a verified provider endpoint/code before enabling automatic retrieval."
      }
    ]
  },
  {
    "type": "symbol_mapping",
    "symbol": "000657.SZ",
    "primary_theme": "METAL_RESOURCE",
    "mapping": {
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
    },
    "data_status": "available",
    "evidence": [
      {
        "evidence_id": "ev_2b39eeb3c56a4c40a8d8a1e5ce9c1770",
        "symbol": "000657.SZ",
        "evidence_type": "external_driver_fact",
        "category": "auto_fact",
        "title": "External driver unavailable: Copper futures daily price",
        "value": null,
        "payload": {
          "factor_id": "copper_futures",
          "display_name": "Copper futures daily price",
          "factor_type": "commodity",
          "data_status": "unavailable",
          "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN.",
          "mapping_boundary": "External-driver mapping is a product configuration used to select observation variables. It does not prove these factors dominate the stock price in the current period and must not be used as a system buy/sell conclusion."
        },
        "source": "tushare.fut_daily",
        "source_endpoint": "fut_daily",
        "as_of_time": null,
        "as_of_date": null,
        "fetched_at": "2026-05-25T02:57:32.351424",
        "reliability": "B",
        "llm_usage": "context_only",
        "interpretation_limit": "External-driver facts are related background observations only. They do not imply a direct causal effect, valuation impact, or buy/sell conclusion.",
        "freshness_days": null,
        "data_status": "unavailable",
        "notes": null
      },
      {
        "evidence_id": "ev_bbb3f21b9d434cb5aa1209d7d72c49e6",
        "symbol": "000657.SZ",
        "evidence_type": "external_driver_fact",
        "category": "auto_fact",
        "title": "External driver unavailable: AI theme ETF share, NAV, and price",
        "value": null,
        "payload": {
          "factor_id": "ai_theme_etf_159382",
          "display_name": "AI theme ETF share, NAV, and price",
          "factor_type": "theme_etf",
          "data_status": "unavailable",
          "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN.",
          "mapping_boundary": "External-driver mapping is a product configuration used to select observation variables. It does not prove these factors dominate the stock price in the current period and must not be used as a system buy/sell conclusion."
        },
        "source": "tushare.etf_share_size,fund_nav,fund_daily",
        "source_endpoint": "etf_share_size,fund_nav,fund_daily",
        "as_of_time": null,
        "as_of_date": null,
        "fetched_at": "2026-05-25T02:57:32.352429",
        "reliability": "B",
        "llm_usage": "context_only",
        "interpretation_limit": "External-driver facts are related background observations only. They do not imply a direct causal effect, valuation impact, or buy/sell conclusion.",
        "freshness_days": null,
        "data_status": "unavailable",
        "notes": null
      }
    ],
    "derived_observations": [],
    "missing_data": [
      {
        "key": "external_driver:tungsten_price_placeholder",
        "mapping_status": "unsupported",
        "reason": "Placeholder only; no market fact is retrieved and no conclusion should be drawn.",
        "future_extension": "Add a verified provider endpoint/code before enabling automatic retrieval."
      },
      {
        "key": "external_driver:pcb_sector_index_placeholder",
        "mapping_status": "unsupported",
        "reason": "Placeholder only; no market fact is retrieved and no conclusion should be drawn.",
        "future_extension": "Add a verified provider endpoint/code before enabling automatic retrieval."
      }
    ]
  },
  {
    "type": "symbol_mapping",
    "symbol": "002916.SZ",
    "primary_theme": "AI_PCB",
    "mapping": {
      "mapping_status": "configured",
      "profile_id": "AI_PCB_HARDWARE_V1",
      "symbol": "002916.SZ",
      "message": "已为该标的配置专属外部驱动观察因子；这些因子仅用于筛选背景变量。",
      "future_extension": "可继续增加经用户确认且接口代码已验证的行业、商品或主题映射。",
      "drivers": [
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
    },
    "data_status": "available",
    "evidence": [
      {
        "evidence_id": "ev_aedb2ed2db654b78ad4d55b549af1814",
        "symbol": "002916.SZ",
        "evidence_type": "external_driver_fact",
        "category": "auto_fact",
        "title": "External driver unavailable: AI theme ETF share, NAV, and price",
        "value": null,
        "payload": {
          "factor_id": "ai_theme_etf_159382",
          "display_name": "AI theme ETF share, NAV, and price",
          "factor_type": "theme_etf",
          "data_status": "unavailable",
          "reason": "Tushare token is not configured. Set backend env var TUSHARE_TOKEN.",
          "mapping_boundary": "External-driver mapping is a product configuration used to select observation variables. It does not prove these factors dominate the stock price in the current period and must not be used as a system buy/sell conclusion."
        },
        "source": "tushare.etf_share_size,fund_nav,fund_daily",
        "source_endpoint": "etf_share_size,fund_nav,fund_daily",
        "as_of_time": null,
        "as_of_date": null,
        "fetched_at": "2026-05-25T02:57:32.352773",
        "reliability": "B",
        "llm_usage": "context_only",
        "interpretation_limit": "External-driver facts are related background observations only. They do not imply a direct causal effect, valuation impact, or buy/sell conclusion.",
        "freshness_days": null,
        "data_status": "unavailable",
        "notes": null
      }
    ],
    "derived_observations": [],
    "missing_data": [
      {
        "key": "external_driver:pcb_sector_index_placeholder",
        "mapping_status": "unsupported",
        "reason": "Placeholder only; no market fact is retrieved and no conclusion should be drawn.",
        "future_extension": "Add a verified provider endpoint/code before enabling automatic retrieval."
      }
    ]
  }
]
```

## Missing Data
- {"key": "broker_sync", "reason": "Broker account sync is not implemented."}
- {"key": "quote_time", "reason": "Current quote source does not provide a verifiable quote time; portfolio snapshot time is not market quote time."}
- {"key": "repo_cash_equivalent_policy", "reason": "Repo amount is displayed separately from cash; cash-equivalent treatment is unconfirmed."}

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
- Portfolio external-driver sections are symbol-level context only and must not be aggregated into macro conclusions.

## Neutral Questions for an External LLM
- Is the portfolio overly concentrated by single position or primary theme?
- Which theme tags indicate overlapping risk, and why should they not be added as asset weights?
- Does the cash and repo structure preserve enough optionality?
- Are the recorded plans and invalid conditions consistent with the actual portfolio structure?
- If a proposed trade is executed, how would concentration, cash ratio, and theme overlap change?
- What is the most important missing information before making a decision?

No buy/sell recommendation is generated by this packet.