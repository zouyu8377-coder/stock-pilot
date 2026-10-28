from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.attractiveness import build_attractiveness_radar
from app.portfolio.schemas import PortfolioPosition, PortfolioState
from app.portfolio.task_evidence import completed_market_trend_overrides


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


def _build_account_performance(state: PortfolioState) -> dict[str, Any]:
    """Build deterministic account facts; no model output is used here."""
    metrics = state.metrics
    active_positions = [item for item in state.snapshot.positions if float(item.quantity or 0) > 0]
    total_market_value = float(metrics.total_market_value or 0)
    total_unrealized_pnl = metrics.current_holding_unrealized_pnl
    known_positions = [item for item in active_positions if item.unrealized_pnl is not None]
    covered_market_value = sum(float(item.market_value or 0) for item in known_positions)
    coverage_pct = _round(covered_market_value / total_market_value * 100) if total_market_value else None

    contributors: list[dict[str, Any]] = []
    direction_totals: dict[str, dict[str, Any]] = {}
    for position in known_positions:
        pnl = float(position.unrealized_pnl or 0)
        market_value = float(position.market_value or 0)
        direction = str(position.primary_theme or "UNCLASSIFIED")
        contributors.append({
            "symbol": position.symbol,
            "name": position.name,
            "unrealized_pnl": _round(pnl),
            "unrealized_pnl_pct": _round(position.unrealized_pnl_pct),
            "market_value": _round(market_value),
            "contribution_to_holding_pnl_pct": _round(
                pnl / float(total_unrealized_pnl) * 100,
            ) if total_unrealized_pnl not in (None, 0) else None,
            "data_status": position.data_status,
        })
        grouped = direction_totals.setdefault(direction, {
            "direction": direction,
            "unrealized_pnl": 0.0,
            "market_value": 0.0,
            "position_count": 0,
        })
        grouped["unrealized_pnl"] += pnl
        grouped["market_value"] += market_value
        grouped["position_count"] += 1

    for row in direction_totals.values():
        row["unrealized_pnl"] = _round(row["unrealized_pnl"])
        row["market_value"] = _round(row["market_value"])
        row["contribution_to_holding_pnl_pct"] = _round(
            float(row["unrealized_pnl"] or 0) / float(total_unrealized_pnl) * 100,
        ) if total_unrealized_pnl not in (None, 0) else None

    return {
        "as_of": metrics.quote_retrieved_at.isoformat() if metrics.quote_retrieved_at else None,
        "account_return": {
            "pnl": metrics.account_total_pnl,
            "pnl_pct": metrics.account_total_pnl_pct,
            "status": metrics.account_total_pnl_status,
            "basis": "user_confirmed_total_cost",
            "basis_amount": metrics.account_actual_total_cost,
            "note": "账户总盈亏以用户确认的账户总成本为基准，包含已实现与未实现损益。",
        },
        "holding_return": {
            "pnl": total_unrealized_pnl,
            "pnl_pct": metrics.current_holding_unrealized_pnl_pct,
            "status": metrics.current_holding_unrealized_pnl_status,
            "basis": "current_open_positions_cost_basis",
            "note": "持仓浮盈仅反映当前仍持有标的，不能替代账户总盈亏。",
        },
        "attribution": {
            "status": "available" if coverage_pct is not None and coverage_pct >= 95 else "partial",
            "coverage_pct": coverage_pct,
            "covered_position_count": len(known_positions),
            "active_position_count": len(active_positions),
            "top_contributors": sorted(contributors, key=lambda item: abs(float(item["unrealized_pnl"] or 0)), reverse=True)[:5],
            "direction_contributors": sorted(direction_totals.values(), key=lambda item: abs(float(item["unrealized_pnl"] or 0)), reverse=True)[:5],
            "note": "当前归因按持仓浮盈聚合；交易导致的已实现损益将在交易台账口径完善后纳入。",
        },
        "benchmark": {
            "status": "not_ready",
            "benchmark": "沪深300",
            "note": "组合含资金进出和交易变动，尚未建立现金流调整后的时间加权收益序列，暂不展示可能误导的组合超额收益。",
        },
        "reconciliation": {
            "status": metrics.valuation_consistency_status,
            "checks": metrics.valuation_consistency_checks,
            "errors": metrics.valuation_consistency_errors,
        },
    }


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


MARKET_EVENT_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "market_events" / "event_registry.json"


def _load_market_event_registry(path: Path = MARKET_EVENT_REGISTRY_PATH) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"events": [], "boundary": "事件注册表缺失；当前无法生成事件日历。"}
    except json.JSONDecodeError as exc:
        return {"events": [], "boundary": f"事件注册表 JSON 无法解析：{exc}"}
    if not isinstance(payload.get("events"), list):
        payload["events"] = []
    return payload


def _position_tags(position: PortfolioPosition) -> set[str]:
    return set(position.directions or []) | set(position.theme_tags or []) | set(position.risk_flags or [])


def _portfolio_tags(state: PortfolioState) -> set[str]:
    tags: set[str] = set()
    for position in state.snapshot.positions:
        tags.update(_position_tags(position))
    return tags


def _event_channels(event: dict[str, Any]) -> list[dict[str, Any]]:
    channels = event.get("impact_channels")
    if isinstance(channels, list) and channels:
        return [item for item in channels if isinstance(item, dict)]
    required_tags = event.get("required_tags") or []
    if required_tags:
        return [{
            "channel": "legacy_required_tags",
            "label": "账户标签匹配",
            "related_tags": required_tags,
            "reason": "事件与账户标签存在配置关联",
        }]
    return []


def _event_required_tags(event: dict[str, Any]) -> set[str]:
    tags = set(event.get("required_tags") or [])
    for channel in _event_channels(event):
        tags.update(channel.get("related_tags") or [])
    return tags


def _event_relevance(
    position: PortfolioPosition,
    event: dict[str, Any],
    weight: float,
    extra_tags: set[str] | None = None,
) -> dict[str, Any]:
    risks = set(position.risk_flags or [])
    tags = _position_tags(position) | set(extra_tags or [])
    category = event["category"]
    tech_tags = {"AI", "AI_THEME_ETF", "PCB", "SEMICONDUCTOR_EQUIPMENT", "HBM", "STORAGE"}
    if category in {"ai_supply_chain", "semiconductor_earnings"} and not (tags & tech_tags):
        return {
            "score": 0,
            "reason": "仅存在广义风险偏好间接影响，不计为产业链直接关联。",
            "matched_channels": [],
            "relation_type": "indirect_risk_appetite",
        }
    score = 0
    reasons: list[str] = []
    matched_channels: list[dict[str, Any]] = []

    if float(position.quantity or 0) > 0:
        score += 2
    if weight >= 10:
        score += 2
        reasons.append(f"账户权重 {weight:.2f}%")
    if "HIGH_VOLATILITY" in risks:
        score += 2
        reasons.append("高波动标签")
    for channel in _event_channels(event):
        related_tags = set(channel.get("related_tags") or [])
        if related_tags and not (tags & related_tags):
            continue
        if not related_tags and category.startswith("macro_"):
            pass
        elif not related_tags:
            continue
        score += 3
        matched_channels.append({
            "channel": channel.get("channel") or "unknown",
            "label": channel.get("label") or channel.get("channel") or "影响路径",
            "reason": channel.get("reason") or "事件与账户暴露存在配置关联",
            "matched_tags": sorted(tags & related_tags) if related_tags else [],
        })
    if matched_channels:
        reasons = [item["reason"] for item in matched_channels[:2]] + reasons
    if category in {"macro_fed", "macro_inflation", "macro_jobs", "macro_growth"}:
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
    if category in {"ai_supply_chain", "semiconductor_earnings"}:
        theme_reasons: list[str] = []
        if tags & {"AI", "AI_THEME_ETF"}:
            score += 3
            theme_reasons.append("AI 算力链风向标")
        if tags & {"PCB"}:
            score += 3
            theme_reasons.append("PCB 订单与 AI 服务器链条相关")
        if tags & {"SEMICONDUCTOR_EQUIPMENT"}:
            score += 2
            theme_reasons.append("半导体景气与资本开支敏感")
        reasons = [*theme_reasons, *reasons]
    relation_type = "direct_driver"
    if category in {"macro_fed", "macro_inflation", "macro_jobs", "macro_growth"}:
        direct_macro = (
            category in {"macro_fed", "macro_inflation"} and bool(tags & {"GOLD"})
        ) or (
            category == "macro_growth" and bool(tags & {"COPPER", "TUNGSTEN", "MOLYBDENUM", "METAL_RESOURCE"})
        )
        if not direct_macro:
            relation_type = "indirect_risk_appetite"
            score = min(score, 4)
            reasons.insert(0, "广义风险偏好间接影响，不视为标的经营或产业链直接驱动")
    return {
        "score": score,
        "reason": "；".join(dict.fromkeys(reasons).keys()) or "组合内标的可能受全市场风险偏好变化影响",
        "matched_channels": matched_channels,
        "relation_type": relation_type,
    }


def build_market_event_radar(state: PortfolioState, weights: dict[str, float], today: date | None = None) -> dict[str, Any]:
    today = today or datetime.now(timezone.utc).date()
    registry = _load_market_event_registry()
    from app.direction_classification import get_direction_classifications
    ai_by_symbol = get_direction_classifications().get("by_symbol", {})
    portfolio_tags = _portfolio_tags(state)
    registry_events: list[dict[str, Any]] = []
    high_impact_count = 0

    for seed in registry.get("events", []):
        required_tags = _event_required_tags(seed)
        category = str(seed.get("category") or "")
        if required_tags and not (portfolio_tags & required_tags) and not category.startswith("macro_"):
            continue
        try:
            event_date = date.fromisoformat(seed["date"])
        except (KeyError, TypeError, ValueError):
            continue
        days_until = (event_date - today).days
        if days_until < 0 or days_until > 45:
            continue

        related: list[dict[str, Any]] = []
        relevance_points = 0
        matched_event_channels: dict[str, dict[str, Any]] = {}
        for position in state.snapshot.positions:
            compact = _compact_symbol(position.symbol)
            weight = weights.get(compact, 0.0)
            ai_tags = {
                str(tag).upper()
                for tag in (ai_by_symbol.get(compact) or {}).get("directions", [])
            }
            relevance = _event_relevance(position, seed, weight, ai_tags)
            score = int(relevance["score"])
            if score <= 1:
                continue
            relevance_points = max(relevance_points, score)
            for channel in relevance.get("matched_channels", []):
                key = str(channel.get("channel") or "")
                if key and key not in matched_event_channels:
                    matched_event_channels[key] = channel
            related.append({
                "symbol": position.symbol,
                "name": position.name,
                "portfolio_weight_pct": _round(weight),
                "reason": relevance["reason"],
                "matched_channels": relevance.get("matched_channels", []),
                "relation_type": relevance.get("relation_type", "indirect_risk_appetite"),
            })

        related.sort(key=lambda item: item.get("portfolio_weight_pct") or 0, reverse=True)
        market_impact_score = min(100, int(seed.get("impact_base") or 0))
        account_relevance_score = min(100, relevance_points * 10)
        portfolio_risk_score = min(100, round(market_impact_score * 0.6 + account_relevance_score * 0.4))
        if portfolio_risk_score >= 90:
            high_impact_count += 1
        status = "released" if days_until < 0 else "today" if days_until == 0 else "upcoming"

        channel_list = list(matched_event_channels.values())
        registry_events.append({
            **seed,
            "days_until": days_until,
            "status": status,
            "market_impact_score": market_impact_score,
            "account_relevance_score": account_relevance_score,
            "portfolio_risk_score": portfolio_risk_score,
            "impact_score": portfolio_risk_score,
            "impact_level": "high" if portfolio_risk_score >= 85 else "medium" if portfolio_risk_score >= 65 else "low",
            "matched_impact_channels": channel_list,
            "related_positions": related[:6],
            "portfolio_readout": related[0]["reason"] if related else "组合层面风险偏好事件，暂未匹配到明确方向暴露。",
        })

    registry_events.sort(key=lambda item: (item["date"], item["time_et"]))
    dynamic_alerts: list[dict[str, Any]] = []
    manual_events: list[dict[str, Any]] = []
    events = [*registry_events, *dynamic_alerts, *manual_events]
    next_event = events[0] if events else None
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": 45,
        "registry_version": registry.get("version"),
        "registry_updated_at": registry.get("updated_at"),
        "high_impact_count": high_impact_count,
        "next_event": next_event,
        "registry_events": registry_events,
        "dynamic_alerts": dynamic_alerts,
        "manual_events": manual_events,
        "events": events,
        "boundary": registry.get("boundary") or "事件日历仅作波动风险提示，不构成买卖、加仓、减仓或择时指令。",
    }


def build_dashboard(
    state: PortfolioState,
    context: dict[str, Any],
    *,
    persist_attractiveness_history: bool = False,
) -> dict[str, Any]:
    trends = _trend_by_symbol(context)
    # A completed agent snapshot can close a missing local trend gap, but never
    # overrides an already available account-context data series.
    for symbol, override in completed_market_trend_overrides().items():
        current = trends.get(symbol) or {}
        if current.get("data_status") != "available":
            trends[symbol] = {**current, **override}
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

    market_event_radar = build_market_event_radar(state, weights)
    theme_evidence_radar = context.get("theme_evidence_radar", {})
    overseas_tech_chain = context.get("overseas_tech_chain", {
        "data_status": "not_built",
        "boundary": "Dashboard consumes overseas_tech_chain from the account-analysis context when available.",
    })
    attractiveness_radar = build_attractiveness_radar(
        state,
        trends=trends,
        theme_radar=theme_evidence_radar,
        event_radar=market_event_radar,
        persist_history=persist_attractiveness_history,
    )
    from app.direction_classification import get_direction_classifications
    ai_classifications = get_direction_classifications()
    attractiveness_by_symbol = {
        _compact_symbol(item.get("symbol", "")): item
        for item in attractiveness_radar.get("positions", [])
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "account_facts": context.get("account_facts", {}),
        "account_performance": _build_account_performance(state),
        "positions": [
            {
                **position.model_dump(mode="json"),
                "portfolio_weight_pct": _round(weights.get(_compact_symbol(position.symbol), 0.0)),
                "position_status": _status(position),
                "trend": trends.get(_compact_symbol(position.symbol), {}),
                "attractiveness": attractiveness_by_symbol.get(_compact_symbol(position.symbol), {}),
                "ai_direction_classification": ai_classifications.get("by_symbol", {}).get(_compact_symbol(position.symbol)),
            }
            for position in state.snapshot.positions
        ],
        "opportunity_queue": opportunity_queue[:8],
        "risk_queue": risk_queue[:8],
        "strategy_matrix": strategy_matrix,
        "primary_direction_grouping": context.get("primary_direction_grouping", []),
        "risk_observations": context.get("risk_observations", {}),
        "data_gaps": context.get("data_gaps", []),
        "market_event_radar": market_event_radar,
        "theme_evidence_radar": theme_evidence_radar,
        "overseas_tech_chain": overseas_tech_chain,
        "attractiveness_radar": attractiveness_radar,
        "ai_direction_classification": {key: value for key, value in ai_classifications.items() if key != "by_symbol"},
        "external_ai_tasks": context.get("suggested_questions_for_external_llm", []),
        "boundaries": context.get("ai_analysis_boundary", {}),
    }
