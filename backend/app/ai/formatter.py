from app.ai.schemas import ResearchReport, PriceLevel, TimeframeView


def format_research_report(report: ResearchReport) -> dict:
    """
    将 ResearchReport 序列化为前端可用的字典。
    确保所有字段都有默认值，前端不会因缺失字段报错。
    """
    return {
        "trade_thesis": report.trade_thesis,
        "trading_bias": report.trading_bias,
        "strategy_type": report.strategy_type,
        "trading_advice": report.trading_advice,

        "confidence_score": report.confidence_score,
        "odds_score": report.odds_score,
        "risk_level": report.risk_level,

        "bull_score": report.bull_score,
        "bear_score": report.bear_score,

        "key_drivers": report.key_drivers,

        "key_price_levels": [
            {
                "price": lvl.price,
                "type": lvl.type,
                "meaning": lvl.meaning,
            }
            for lvl in report.key_price_levels
        ],

        "invalid_condition": report.invalid_condition,
        "bullish_triggers": report.bullish_triggers,
        "bearish_triggers": report.bearish_triggers,

        "short_term": {
            "view": report.short_term.view,
            "action": report.short_term.action,
        },
        "medium_term": {
            "view": report.medium_term.view,
            "action": report.medium_term.action,
        },
        "long_term": {
            "view": report.long_term.view,
            "action": report.long_term.action,
        },

        "company_alpha": report.company_alpha,
        "industry_beta": report.industry_beta,
        "industry_analysis": report.industry_analysis,

        "risk_factors": report.risk_factors,
        "missing_data": report.missing_data,

        "market_regime": report.market_regime,
        "selected_models": report.selected_models,

        "summary": report.summary,

        # 兼容旧字段
        "sector_capital_flow": report.sector_capital_flow,
        "market_state": report.market_state,
    }
