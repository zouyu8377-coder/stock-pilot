from app.ai.schemas import ResearchReport


def format_research_report(report: ResearchReport) -> dict:
    return {
        "trading_bias": report.trading_bias,
        "trading_advice": report.trading_advice,
        "win_rate": report.win_rate,
        "profit_loss_ratio": report.profit_loss_ratio,
        "risk_level": report.risk_level,
        "bull_score": report.bull_score,
        "bear_score": report.bear_score,
        "key_drivers": report.key_drivers,
        "sector_capital_flow": report.sector_capital_flow,
        "key_price_levels": report.key_price_levels,
        "short_term": report.short_term,
        "medium_term": report.medium_term,
        "long_term": report.long_term,
        "industry_analysis": report.industry_analysis,
        "risk_factors": report.risk_factors,
        "summary": report.summary,
    }