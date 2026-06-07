from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.portfolio.schemas import PortfolioPosition, PortfolioState


def _compact_symbol(symbol: str) -> str:
    return symbol.split(".", 1)[0].strip().zfill(6)


def _round(value: Any, digits: int = 2) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _trend_by_symbol(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        _compact_symbol(item.get("symbol", "")): item
        for item in context.get("holding_trend_evidence", [])
        if item.get("symbol")
    }


def _weight_by_symbol(state: PortfolioState, context: dict[str, Any]) -> dict[str, float]:
    weights: dict[str, float] = {}
    for item in state.metrics.position_weights:
        symbol = item.get("symbol")
        if symbol:
            weights[_compact_symbol(symbol)] = float(item.get("weight_pct") or 0)
    for item in context.get("holdings", []):
        symbol = item.get("symbol")
        weight = item.get("portfolio_weight_pct")
        if symbol and weight is not None:
            weights[_compact_symbol(symbol)] = float(weight or 0)
    return weights


def _status(position: PortfolioPosition) -> str:
    return "watchlist" if float(position.quantity or 0) == 0 else "active"


def _risk_evidence(position: PortfolioPosition, trend: dict[str, Any], weight: float) -> list[str]:
    evidence: list[str] = []
    if weight >= 10:
        evidence.append(f"account_weight_pct={weight:.2f}")
    if (position.unrealized_pnl or 0) < 0:
        evidence.append(f"unrealized_pnl={position.unrealized_pnl}")
    if (trend.get("price_vs_ma20_pct") or 0) < 0:
        evidence.append(f"price_vs_ma20_pct={trend.get('price_vs_ma20_pct')}")
    if "HIGH_VOLATILITY" in (position.risk_flags or []):
        evidence.append("risk_flag=HIGH_VOLATILITY")
    if position.data_status == "missing_data" or trend.get("data_status") == "unavailable":
        evidence.append("data_status=missing_or_unavailable")
    return evidence


def _opportunity_evidence(position: PortfolioPosition, trend: dict[str, Any], weight: float) -> list[str]:
    evidence: list[str] = []
    if _status(position) == "watchlist":
        evidence.append("position_status=watchlist")
    if (trend.get("return_20d_pct") or 0) > 0:
        evidence.append(f"return_20d_pct={trend.get('return_20d_pct')}")
    if "强" in str(trend.get("trend_state") or ""):
        evidence.append(f"trend_state={trend.get('trend_state')}")
    if (position.unrealized_pnl_pct or 0) > 0:
        evidence.append(f"unrealized_pnl_pct={position.unrealized_pnl_pct}")
    if weight >= 10:
        evidence.append(f"account_weight_pct={weight:.2f}")
    return evidence


def _opportunity_score(position: PortfolioPosition, trend: dict[str, Any], weight: float) -> int:
    score = 0
    if _status(position) == "watchlist":
        score += 3
    if "强" in str(trend.get("trend_state") or ""):
        score += 3
    if (trend.get("return_20d_pct") or 0) > 0:
        score += 2
    if (position.unrealized_pnl_pct or 0) > 0:
        score += 1
    if weight >= 10:
        score += 1
    return score


def _risk_score(position: PortfolioPosition, trend: dict[str, Any], weight: float) -> int:
    score = 0
    if (position.unrealized_pnl or 0) < 0:
        score += 3
    if (trend.get("price_vs_ma20_pct") or 0) < 0:
        score += 3
    if weight >= 10:
        score += 2
    if "HIGH_VOLATILITY" in (position.risk_flags or []):
        score += 1
    if position.data_status == "missing_data" or trend.get("data_status") == "unavailable":
        score += 1
    return score


def _strategy_note(position: PortfolioPosition, trend: dict[str, Any], horizon: str) -> str:
    status = _status(position)
    trend_state = trend.get("trend_state") or "走势证据不足"
    price_vs_ma20 = trend.get("price_vs_ma20_pct")
    return_20d = trend.get("return_20d_pct")
    pnl = position.unrealized_pnl or 0

    if status == "watchlist":
        if horizon == "short":
            return "观察池标的：先确认短线走势触发和成交活跃度，不计入当前仓位。"
        if horizon == "medium":
            return "观察池标的：等待方向归属、外部驱动和 20 日趋势证据进一步清晰。"
        return "观察池标的：只作为潜在投资对象跟踪，长期观点需补齐基本事实和失效条件。"

    if horizon == "short":
        if pnl > 0 and (trend.get("price_vs_ma5_pct") or 0) < 0:
            return "盈利持仓短线转弱：进入利润保护观察，重点看 MA5 附近能否修复。"
        if "强" in str(trend_state):
            return "短线走势偏强：继续观察强势延续与放量质量。"
        return f"短线以走势状态为主：{trend_state}。"

    if horizon == "medium":
        if pnl < 0 and price_vs_ma20 is not None and price_vs_ma20 < 0:
            return "中期仍弱于 MA20：修复证据不足，降低策略置信度。"
        if return_20d is not None and return_20d > 0:
            return "中期 20 日收益为正：观察趋势是否能被方向逻辑或外部驱动继续支持。"
        return "中期需要结合 MA20、账户权重和持仓角色继续确认。"

    if position.position_role in ("core", "trend"):
        return "长期需验证持仓角色是否仍成立，并补充基本面、外部驱动与失效条件。"
    return "长期暂以观察性结论处理，等待用户计划和核心事实补齐。"


def _queue_item(position: PortfolioPosition, trend: dict[str, Any], weight: float, score: int, evidence: list[str]) -> dict[str, Any]:
    return {
        "symbol": position.symbol,
        "name": position.name,
        "position_status": _status(position),
        "position_role": position.position_role,
        "primary_direction": position.directions[0] if position.directions else None,
        "quantity": position.quantity,
        "market_value": position.market_value,
        "portfolio_weight_pct": _round(weight),
        "unrealized_pnl": position.unrealized_pnl,
        "unrealized_pnl_pct": position.unrealized_pnl_pct,
        "trend_state": trend.get("trend_state"),
        "return_20d_pct": trend.get("return_20d_pct"),
        "price_vs_ma20_pct": trend.get("price_vs_ma20_pct"),
        "score": score,
        "evidence_refs": evidence,
    }


_MARKET_EVENT_SEEDS: list[dict[str, Any]] = [
    {
        "event_id": "us_cpi_2026_06_10",
        "date": "2026-06-10",
        "time_et": "08:30",
        "category": "macro_inflation",
        "title": "美国 5 月 CPI",
        "impact_base": 92,
        "source": "BLS CPI Release Calendar",
        "source_url": "https://www.bls.gov/schedule/news_release/cpi.htm",
        "focus_points": ["核心 CPI 环比", "服务通胀", "市场对降息路径的重定价"],
    },
    {
        "event_id": "fomc_2026_06_16_17",
        "date": "2026-06-17",
        "time_et": "14:00",
        "category": "macro_fed",
        "title": "FOMC 利率决议与经济预测",
        "impact_base": 96,
        "source": "Federal Reserve FOMC Calendar",
        "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        "focus_points": ["利率决定", "点阵图", "鲍威尔发布会措辞"],
    },
    {
        "event_id": "us_pce_2026_06_25",
        "date": "2026-06-25",
        "time_et": "08:30",
        "category": "macro_inflation",
        "title": "美国 PCE / 个人收入支出",
        "impact_base": 84,
        "source": "BEA Release Calendar",
        "source_url": "https://www.bea.gov/news/schedule",
        "focus_points": ["核心 PCE", "个人消费支出", "通胀与增长组合"],
    },
    {
        "event_id": "us_jobs_2026_07_02",
        "date": "2026-07-02",
        "time_et": "08:30",
        "category": "macro_jobs",
        "title": "美国 6 月非农就业",
        "impact_base": 90,
        "source": "BLS Employment Situation Calendar",
        "source_url": "https://www.bls.gov/schedule/news_release/empsit.htm",
        "focus_points": ["新增非农就业", "失业率", "平均时薪"],
    },
    {
        "event_id": "us_cpi_2026_07_14",
        "date": "2026-07-14",
        "time_et": "08:30",
        "category": "macro_inflation",
        "title": "美国 6 月 CPI",
        "impact_base": 88,
        "source": "BLS July 2026 Release Schedule",
        "source_url": "https://www.bls.gov/schedule/2026/07_sched_list.htm",
        "focus_points": ["核心 CPI 环比", "住房与服务价格", "下一次 FOMC 前的通胀验证"],
    },
]


def _event_relevance(position: PortfolioPosition, event: dict[str, Any], weight: float) -> tuple[int, str]:
    directions = set(position.directions or [])
    risks = set(position.risk_flags or [])
    tags = directions | set(position.theme_tags or []) | risks
    category = event["category"]
    score = 0
    reasons: list[str] = []

    if float(position.quantity or 0) > 0:
        score += 2
    if weight >= 10:
        score += 2
        reasons.append(f"账户权重 {weight:.2f}%")
    if "HIGH_VOLATILITY" in risks:
        score += 2
        reasons.append("高波动标签")
    if category in {"macro_fed", "macro_inflation", "macro_jobs"}:
        score += 1
        if tags & {"AI", "PCB", "SEMICONDUCTOR_EQUIPMENT", "AI_THEME_ETF"}:
            score += 2
            reasons.append("成长/科技方向对利率预期敏感")
        if tags & {"GOLD"}:
            score += 2
            reasons.append("黄金方向受实际利率与美元影响")
        if tags & {"COPPER", "TUNGSTEN", "METAL_RESOURCE"}:
            score += 1
            reasons.append("资源品方向受增长预期影响")
    return score, "；".join(reasons[:2]) or "组合内标的可能受全市场风险偏好变化影响"


def build_market_event_radar(state: PortfolioState, weights: dict[str, float], today: date | None = None) -> dict[str, Any]:
    today = today or datetime.now(timezone.utc).date()
    events: list[dict[str, Any]] = []
    high_impact_count = 0

    for seed in _MARKET_EVENT_SEEDS:
        event_date = date.fromisoformat(seed["date"])
        days_until = (event_date - today).days
        if days_until < -5 or days_until > 45:
            continue

        related: list[dict[str, Any]] = []
        relevance_bonus = 0
        for position in state.snapshot.positions:
            compact = _compact_symbol(position.symbol)
            weight = weights.get(compact, 0.0)
            relevance, reason = _event_relevance(position, seed, weight)
            if relevance <= 1:
                continue
            relevance_bonus = max(relevance_bonus, relevance)
            related.append({
                "symbol": position.symbol,
                "name": position.name,
                "portfolio_weight_pct": _round(weight),
                "reason": reason,
            })

        related.sort(key=lambda item: item.get("portfolio_weight_pct") or 0, reverse=True)
        impact_score = min(100, int(seed["impact_base"]) + relevance_bonus)
        if impact_score >= 90:
            high_impact_count += 1
        status = "released" if days_until < 0 else "today" if days_until == 0 else "upcoming"

        events.append({
            **seed,
            "days_until": days_until,
            "status": status,
            "impact_score": impact_score,
            "impact_level": "high" if impact_score >= 85 else "medium" if impact_score >= 65 else "low",
            "related_positions": related[:6],
            "portfolio_readout": related[0]["reason"] if related else "组合层面风险偏好事件，暂未匹配到明确方向暴露。",
        })

    events.sort(key=lambda item: (item["date"], item["time_et"]))
    next_event = events[0] if events else None
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": 45,
        "high_impact_count": high_impact_count,
        "next_event": next_event,
        "events": events,
        "boundary": "第一版仅覆盖已人工核对的美国宏观事件种子；不包含自动抓取的公司财报、监管节点或实时一致预期。",
    }


def build_dashboard(state: PortfolioState, context: dict[str, Any]) -> dict[str, Any]:
    trends = _trend_by_symbol(context)
    weights = _weight_by_symbol(state, context)
    opportunity_queue: list[dict[str, Any]] = []
    risk_queue: list[dict[str, Any]] = []
    strategy_matrix: list[dict[str, Any]] = []

    for position in state.snapshot.positions:
        compact = _compact_symbol(position.symbol)
        trend = trends.get(compact, {})
        weight = weights.get(compact, 0.0)
        opp_score = _opportunity_score(position, trend, weight)
        risk_score = _risk_score(position, trend, weight)
        if opp_score > 0:
            opportunity_queue.append(_queue_item(position, trend, weight, opp_score, _opportunity_evidence(position, trend, weight)))
        if risk_score > 0:
            risk_queue.append(_queue_item(position, trend, weight, risk_score, _risk_evidence(position, trend, weight)))
        strategy_matrix.append({
            "symbol": position.symbol,
            "name": position.name,
            "position_status": _status(position),
            "short_term": _strategy_note(position, trend, "short"),
            "medium_term": _strategy_note(position, trend, "medium"),
            "long_term": _strategy_note(position, trend, "long"),
            "monitor_triggers": [
                "MA5/MA20 相对位置变化",
                "20 日收益和趋势状态变化",
                "用户持仓计划、失效条件或补充事实更新",
            ],
            "invalidation_signals": [
                "走势证据与持仓角色持续背离",
                "关键外部驱动或事实证据无法验证",
                "账户权重或风险标签超过用户可接受范围",
            ],
        })

    opportunity_queue.sort(key=lambda item: item["score"], reverse=True)
    risk_queue.sort(key=lambda item: item["score"], reverse=True)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "account_facts": context.get("account_facts", {}),
        "positions": [
            {
                **position.model_dump(mode="json"),
                "portfolio_weight_pct": _round(weights.get(_compact_symbol(position.symbol), 0.0)),
                "position_status": _status(position),
                "trend": trends.get(_compact_symbol(position.symbol), {}),
            }
            for position in state.snapshot.positions
        ],
        "opportunity_queue": opportunity_queue[:8],
        "risk_queue": risk_queue[:8],
        "strategy_matrix": strategy_matrix,
        "primary_direction_grouping": context.get("primary_direction_grouping", []),
        "risk_observations": context.get("risk_observations", {}),
        "data_gaps": context.get("data_gaps", []),
        "market_event_radar": build_market_event_radar(state, weights),
        "external_ai_tasks": context.get("suggested_questions_for_external_llm", []),
        "boundaries": context.get("ai_analysis_boundary", {}),
    }
