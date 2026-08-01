from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.analysis_packet.packet_service import build_single_stock_packet
from app.portfolio.dashboard_cache import get_dashboard_bundle
from app.rotation.service import get_rotation_bundle, load_rotation_status


CONTRACT_VERSION = "agent_context.v1"
LOCAL_EXPORT_BOUNDARY = (
    "上下文在 Stock-Pilot 本地生成，接口本身不会调用外部大模型。"
    "只有用户主动复制、导出或后续显式启用外部 Provider 时，数据才可进入外部分析流程。"
)

DAILY_REVIEW_QUESTIONS = [
    "基于事实与推断分区，概括今日账户风险、潜在机会和最值得核查的三项证据。",
    "哪些结论受到数据陈旧、缺失或代理标的代表性不足的限制？",
    "给出今日复盘清单，只输出核查动作与触发条件，不直接给出买卖指令。",
]
PORTFOLIO_QUESTIONS = [
    "当前账户最主要的集中度、主题暴露和外部驱动风险是什么？",
    "哪些持仓的趋势证据、成本语义或事实覆盖不足，需要优先补证？",
    "形成一份账户风险审计清单，不直接给出买卖或调仓指令。",
]
ROTATION_QUESTIONS = [
    "哪些方向处于潜在机会或早期转强阶段，支持证据与反证分别是什么？",
    "哪些强势方向存在追涨风险，更适合等待什么样的回踩或确认信号？",
    "检查代理 ETF 与龙头股是否足以代表对应行业，并指出代表性缺口。",
]
STOCK_QUESTIONS = [
    "区分事实、系统推断和缺失数据，概括该标的当前研究结论。",
    "哪些关键假设尚未被公告、行情或外部驱动证据验证？",
    "形成下一步事实核查清单，不直接给出买卖指令。",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _meta(
    context_type: str,
    *,
    data_time: dict[str, Any],
    sources: list[dict[str, Any]],
    freshness: dict[str, Any],
    contains_sensitive_account_data: bool,
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "context_type": context_type,
        "generated_at": _now_iso(),
        "data_time": data_time,
        "sources": sources,
        "freshness": freshness,
        "privacy_boundary": {
            "processing": "local_only",
            "external_llm_called": False,
            "contains_sensitive_account_data": contains_sensitive_account_data,
            "export_rule": LOCAL_EXPORT_BOUNDARY,
        },
    }


def _portfolio_payload(bundle: dict[str, Any]) -> dict[str, Any]:
    context = bundle["context"]
    dashboard = bundle["dashboard"]
    context_meta = context.get("meta", {})
    cache = bundle.get("cache", {})
    return {
        "meta": _meta(
            "portfolio_review",
            data_time={
                "portfolio_as_of": context_meta.get("portfolio_as_of"),
                "quote_retrieved_at": context_meta.get("quote_retrieved_at"),
                "valuation_generated_at": context_meta.get("valuation_generated_at"),
            },
            sources=[
                {"name": "portfolio_snapshot", "kind": "local_user_data"},
                {"name": "local_market_cache", "kind": "local_market_data"},
                {"name": "portfolio_dashboard", "kind": "derived_local_context"},
            ],
            freshness={
                "status": "reported_by_sources",
                "dashboard_cache": cache,
                "valuation_consistency_status": context_meta.get("valuation_consistency_status"),
            },
            contains_sensitive_account_data=True,
        ),
        "facts": {
            "account": context.get("account_facts", {}),
            "holdings": context.get("holdings", []),
            "holding_trend_evidence": context.get("holding_trend_evidence", []),
            "market_events": _compact_market_events(context.get("market_event_radar", {})),
            "manual_and_external_evidence": {
                "etf_share_observations": context.get("etf_share_observations", {}),
                "theme_evidence_radar": context.get("theme_evidence_radar", {}),
                "overseas_tech_chain": context.get("overseas_tech_chain", {}),
                "external_driver_summary": context.get("external_driver_summary", {}),
            },
        },
        "inferences": {
            "primary_direction_grouping": context.get("primary_direction_grouping", []),
            "related_theme_observations": context.get("related_theme_observations", {}),
            "risk_observations": context.get("risk_observations", {}),
            "opportunity_queue": dashboard.get("opportunity_queue", []),
            "risk_queue": dashboard.get("risk_queue", []),
            "strategy_matrix": dashboard.get("strategy_matrix", []),
            "attractiveness_radar": _compact_attractiveness(dashboard.get("attractiveness_radar", {})),
        },
        "missing_data": context.get("data_gaps", []),
        "suggested_questions_for_llm": PORTFOLIO_QUESTIONS,
    }


def build_portfolio_agent_context(*, force: bool = False) -> dict[str, Any]:
    return _portfolio_payload(get_dashboard_bundle(force=force))


def _compact_market_events(radar: dict[str, Any]) -> dict[str, Any]:
    event_fields = (
        "event_id",
        "date",
        "time_et",
        "category",
        "title",
        "source",
        "source_url",
        "days_until",
        "status",
        "impact_level",
        "impact_score",
        "matched_impact_channels",
        "related_positions",
        "portfolio_readout",
        "focus_points",
    )
    return {
        "generated_at": radar.get("generated_at"),
        "window_days": radar.get("window_days"),
        "registry_version": radar.get("registry_version"),
        "registry_updated_at": radar.get("registry_updated_at"),
        "high_impact_count": radar.get("high_impact_count"),
        "next_event": radar.get("next_event"),
        "events": [
            {key: event.get(key) for key in event_fields}
            for event in radar.get("events", [])
        ],
        "boundary": radar.get("boundary"),
    }


def _compact_attractiveness(radar: dict[str, Any]) -> dict[str, Any]:
    position_fields = (
        "symbol",
        "name",
        "position_status",
        "score",
        "coverage",
        "confidence",
        "reference_price",
        "top_reasons",
        "execution_constraints",
        "account_constraints",
        "account_readiness_score",
        "data_health",
        "portfolio_priority_score",
        "theme_rank",
        "opportunity_cost",
        "previous_score",
        "score_change",
    )
    return {
        "generated_at": radar.get("generated_at"),
        "model": radar.get("model"),
        "positions": [
            {key: item.get(key) for key in position_fields}
            for item in radar.get("positions", [])
        ],
        "benchmark": radar.get("benchmark", {}),
        "validation": radar.get("validation", {}),
        "data_quality": radar.get("data_quality", {}),
        "boundary": radar.get("boundary"),
    }


def _rotation_missing_data(bundle: dict[str, Any], status: dict[str, Any]) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    for item in [*bundle.get("benchmarks", []), *bundle.get("sectors", [])]:
        fields = item.get("missing_fields") or []
        if item.get("data_quality") in {"unavailable", "stale"} or fields:
            missing.append({
                "sector_id": item.get("sector_id"),
                "name": item.get("name"),
                "data_quality": item.get("data_quality"),
                "missing_fields": fields,
                "stale_days_to_market": item.get("stale_days_to_market"),
            })
    for reason, count in (status.get("failure_reasons") or {}).items():
        missing.append({"source": "rotation_refresh", "reason": reason, "count": count})
    return missing


def _rotation_payload(bundle: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    sectors = bundle.get("sectors", [])
    factor_fields = (
        "sector_id",
        "name",
        "category",
        "proxy_type",
        "primary_symbol",
        "selected_symbol",
        "proxy_components",
        "latest_date",
        "latest_close",
        "returns",
        "moving_averages",
        "benchmark",
        "relative_strength",
        "flow",
        "data_quality",
        "missing_fields",
        "stale_days_to_market",
        "proxy_meta",
    )
    sector_facts = [{key: item.get(key) for key in factor_fields} for item in sectors]
    sector_inferences = [
        {
            "sector_id": item.get("sector_id"),
            "name": item.get("name"),
            "score": item.get("score"),
            "score_delta_1d": item.get("score_delta_1d"),
            "score_delta_5d": item.get("score_delta_5d"),
            "score_delta_10d": item.get("score_delta_10d"),
            "maturity": item.get("maturity"),
            "opportunity_stage": item.get("opportunity_stage"),
            "action_label": item.get("action_label"),
            "chasing_risk": item.get("chasing_risk"),
            "opportunity_reason": item.get("opportunity_reason"),
            "ma20_distance_pct": item.get("ma20_distance_pct"),
        }
        for item in sectors
    ]
    assessments_by_id = {item["sector_id"]: item for item in sector_inferences}

    def stage_items(key: str) -> list[dict[str, Any]]:
        return [
            assessments_by_id[item.get("sector_id")]
            for item in bundle.get(key, [])
            if item.get("sector_id") in assessments_by_id
        ]

    return {
        "meta": _meta(
            "rotation_review",
            data_time={
                "market_as_of": bundle.get("as_of"),
                "rotation_generated_at": bundle.get("generated_at"),
                "universe_version": bundle.get("universe_version"),
            },
            sources=[
                {"name": "local_cold_market_data", "kind": "local_market_data"},
                {"name": "rotation_universe", "kind": "local_configuration"},
                {"name": "proxy_etf_and_leaders", "kind": "derived_proxy_evidence"},
            ],
            freshness={
                "status": status.get("status", "unknown"),
                "updated_at": status.get("updated_at"),
                "last_trading_date": status.get("last_trading_date"),
                "stale_count": status.get("stale_count", 0),
                "failed_count": status.get("failed_count", 0),
            },
            contains_sensitive_account_data=False,
        ),
        "facts": {
            "market_style_reference": bundle.get("market_style", {}),
            "benchmarks": bundle.get("benchmarks", []),
            "sector_evidence": sector_facts,
        },
        "inferences": {
            "summary": bundle.get("summary", {}),
            "sector_opportunity_assessments": sector_inferences,
            "potential_opportunities": stage_items("potential_opportunities"),
            "early_turning": stage_items("early_turning"),
            "wait_pullback": stage_items("wait_pullback"),
            "avoid_now": stage_items("avoid_now"),
        },
        "missing_data": _rotation_missing_data(bundle, status),
        "suggested_questions_for_llm": ROTATION_QUESTIONS,
    }


def build_rotation_agent_context(*, force: bool = False) -> dict[str, Any]:
    return _rotation_payload(get_rotation_bundle(force=force), load_rotation_status())


def build_daily_review_context(*, force: bool = False) -> dict[str, Any]:
    dashboard_bundle = get_dashboard_bundle(force=force)
    rotation_bundle = get_rotation_bundle(force=force)
    rotation_status = load_rotation_status()
    portfolio = _portfolio_payload(dashboard_bundle)
    rotation = _rotation_payload(rotation_bundle, rotation_status)
    portfolio_meta = portfolio["meta"]
    rotation_meta = rotation["meta"]
    return {
        "meta": _meta(
            "daily_review",
            data_time={
                "portfolio": portfolio_meta["data_time"],
                "rotation": rotation_meta["data_time"],
            },
            sources=[*portfolio_meta["sources"], *rotation_meta["sources"]],
            freshness={
                "portfolio": portfolio_meta["freshness"],
                "rotation": rotation_meta["freshness"],
            },
            contains_sensitive_account_data=True,
        ),
        "facts": {
            "portfolio": {
                "account": portfolio["facts"]["account"],
                "holdings": portfolio["facts"]["holdings"],
                "holding_trend_evidence": portfolio["facts"]["holding_trend_evidence"],
                "market_events": portfolio["facts"]["market_events"],
            },
            "rotation": rotation["facts"],
        },
        "inferences": {
            "portfolio": {
                "primary_direction_grouping": portfolio["inferences"]["primary_direction_grouping"],
                "risk_observations": portfolio["inferences"]["risk_observations"],
                "opportunity_queue": portfolio["inferences"]["opportunity_queue"],
                "risk_queue": portfolio["inferences"]["risk_queue"],
            },
            "rotation": rotation["inferences"],
        },
        "missing_data": [
            *[{"scope": "portfolio", "detail": item} for item in portfolio["missing_data"]],
            *[{"scope": "rotation", "detail": item} for item in rotation["missing_data"]],
        ],
        "suggested_questions_for_llm": DAILY_REVIEW_QUESTIONS,
    }


def build_stock_agent_context(symbol: str, *, user_question: str | None = None) -> dict[str, Any]:
    result = build_single_stock_packet(symbol, user_question=user_question, persist=False)
    packet = result["packet"]
    packet_meta = packet.get("meta", {})
    holding = packet.get("stock_profile", {}).get("holding")
    questions = packet.get("suggested_questions_for_external_llm") or STOCK_QUESTIONS
    return {
        "meta": _meta(
            "single_stock_review",
            data_time={
                "daily_k_as_of": packet_meta.get("daily_k_as_of"),
                "quote_retrieved_at": packet_meta.get("quote_retrieved_at"),
                "portfolio_as_of": packet_meta.get("portfolio_as_of"),
            },
            sources=[
                {"name": "single_stock_analysis_packet", "kind": "derived_local_context"},
                {"name": "local_market_and_fact_cache", "kind": "local_market_data"},
                *([{"name": "portfolio_snapshot", "kind": "local_user_data"}] if holding else []),
            ],
            freshness={
                "status": "reported_by_sources",
                "market_data_as_of": packet_meta.get("market_data_as_of"),
                "daily_k_as_of": packet_meta.get("daily_k_as_of"),
            },
            contains_sensitive_account_data=bool(holding),
        ),
        "facts": {
            "basic_information": packet.get("basic_information", {}),
            "stock_profile": packet.get("stock_profile", {}),
            "auto_fact": packet.get("auto_fact", []),
            "manual_account": packet.get("manual_account", {}),
            "manual_evidence": packet.get("manual_evidence", []),
            "external_driver_mapping": packet.get("external_driver_mapping", {}),
        },
        "inferences": {
            "auto_signal": packet.get("auto_signal", []),
            "system_hypothesis": packet.get("system_hypothesis", []),
        },
        "missing_data": packet.get("missing_data", []),
        "suggested_questions_for_llm": questions,
    }


def render_agent_context_markdown(context: dict[str, Any]) -> str:
    meta = context.get("meta", {})
    privacy = meta.get("privacy_boundary", {})
    lines = [
        f"# Stock-Pilot Agent Context: {meta.get('context_type', 'unknown')}",
        "",
        f"- Contract: {meta.get('contract_version', CONTRACT_VERSION)}",
        f"- Generated at: {meta.get('generated_at', '-')}",
        f"- External LLM called: {privacy.get('external_llm_called', False)}",
        f"- Contains sensitive account data: {privacy.get('contains_sensitive_account_data', False)}",
        f"- Export boundary: {privacy.get('export_rule', LOCAL_EXPORT_BOUNDARY)}",
        "",
        "## Data Time And Freshness",
        "",
        "```json",
        json.dumps({
            "data_time": meta.get("data_time", {}),
            "freshness": meta.get("freshness", {}),
            "sources": meta.get("sources", []),
        }, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Facts",
        "",
        "```json",
        json.dumps(context.get("facts", {}), ensure_ascii=False, indent=2),
        "```",
        "",
        "## System Inferences",
        "",
        "```json",
        json.dumps(context.get("inferences", {}), ensure_ascii=False, indent=2),
        "```",
        "",
        "## Missing Data",
        "",
        "```json",
        json.dumps(context.get("missing_data", []), ensure_ascii=False, indent=2),
        "```",
        "",
        "## Suggested Review Questions",
        "",
    ]
    lines.extend(f"- {question}" for question in context.get("suggested_questions_for_llm", []))
    return "\n".join(lines) + "\n"
