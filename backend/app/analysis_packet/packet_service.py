from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.analysis_packet.snapshot_builder import build_basic_stock_snapshot
from app.core.config import settings
from app.evidence.schemas import AnalysisSnapshot, EvidenceCategory, EvidenceItem
from app.evidence.schemas import AnalysisScope, DataStatus, EvidenceReliability, EvidenceType, LlmUsage
from app.external_drivers import build_external_driver_context
from app.facts.common import to_ts_code
from app.facts.disclosure_service import get_disclosure_facts
from app.facts.dragon_tiger_service import get_dragon_tiger_facts
from app.facts.etf_service import SUPPORTED_ETFS, get_etf_facts
from app.portfolio import portfolio_service


PACKET_VERSION = "analysis_packet.v1"

PRIVACY_NOTICE = (
    "This packet is generated locally and may contain personal account information, holdings, costs, cash, repo, "
    "trade plans, and manually entered evidence. Stock-Pilot does not send it to any external LLM, does not call "
    "deep analysis, and does not upload attachments automatically. External sharing happens only if the user "
    "actively copies, downloads, or submits the content elsewhere."
)

GLOBAL_BOUNDARIES = [
    "Automatic shareholder count is not available in this stage.",
    "Automatic unlock event data is not available in this stage.",
    "Announcement full text is not read unless manually entered; do not infer business or profit impact from an index title.",
    "Dragon-tiger list data shows public abnormal trading seat structure only and does not prove long-term capital commitment.",
    "Moneyflow, margin financing, backtesting, and broker sync are not included in this stage.",
    "External commodity, FX, ETF, or sector drivers are attached only when a reviewed symbol mapping exists; unmapped symbols do not receive generic macro factors.",
    "Manual account data uses the user's local snapshot time and may be stale.",
    "Realtime quote data and low-frequency facts may have different timestamps.",
    "Daily K OHLC, volume, amount, and daily change are local daily-K facts; 5/20/60-day returns are derived observations from daily closes, not trend causality or buy/sell conclusions.",
    "The current quote provider does not expose a verifiable quote timestamp for portfolio enrichment; portfolio snapshot time is not market quote time.",
    "Concentration and cash reminders may depend on system default placeholder parameters that have not been confirmed by the user.",
    "Repo amount is shown separately. It is not treated as fully equivalent to cash unless the user confirms that convention.",
]

QUOTE_TIME_BOUNDARY = (
    "Current quote source does not provide a verifiable market quote time; "
    "system retrieval time is not market quote time."
)
DEFAULT_RISK_BOUNDARY = "Concentration or cash reminders may depend on system default placeholder parameters and are unconfirmed by the user."
REPO_BOUNDARY = "Repo amount is displayed separately from cash; cash-equivalent treatment is unconfirmed."

MOJIBAKE_MARKERS = ("�", "鏃", "鐢", "鎴", "涓", "鍏", "榫", "璋", "绱", "浠", "浜", "勫")

SINGLE_LLM_QUESTIONS = [
    "Which items in this packet are hard facts, and which are weak auxiliary signals?",
    "Does the current holding, if any, create excessive theme exposure inside the portfolio?",
    "Which missing information would most materially change the analysis?",
    "Is the user's invalid condition specific enough to falsify the trade plan?",
    "What are the main risks under bullish, neutral, and adverse market scenarios?",
]

PORTFOLIO_LLM_QUESTIONS = [
    "Is the portfolio overly concentrated by single position or primary theme?",
    "Which theme tags indicate overlapping risk, and why should they not be added as asset weights?",
    "Does the cash and repo structure preserve enough optionality?",
    "Are the recorded plans and invalid conditions consistent with the actual portfolio structure?",
    "If a proposed trade is executed, how would concentration, cash ratio, and theme overlap change?",
    "What is the most important missing information before making a decision?",
]


def _now() -> datetime:
    return datetime.utcnow()


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def has_mojibake(text: str) -> bool:
    return any(marker in text for marker in MOJIBAKE_MARKERS)


def _clean_text(value: Any) -> Any:
    if isinstance(value, str):
        if has_mojibake(value):
            return "[text omitted: source string appears incorrectly encoded]"
        return value
    if isinstance(value, list):
        return [_clean_text(item) for item in value]
    if isinstance(value, dict):
        return {key: _clean_text(item) for key, item in value.items()}
    return value


def _evidence_dict(item: EvidenceItem) -> dict[str, Any]:
    data = _clean_text(item.model_dump(mode="json"))
    payload = data.get("payload") or {}
    if isinstance(payload, dict) and len(json.dumps(payload, ensure_ascii=False, default=str)) > 2500:
        data["payload_summary"] = {
            "keys": list(payload.keys()),
            "note": "Payload is large; inspect JSON export for full content.",
        }
    return data


def _filter_evidence(snapshot: AnalysisSnapshot, category: EvidenceCategory) -> list[dict[str, Any]]:
    return [
        _evidence_dict(item)
        for item in snapshot.evidence_items
        if item.category == category and item.evidence_type != EvidenceType.COMPANY_PROFILE
    ]


def _external_driver_sections(symbol: str, holding: dict[str, Any] | None = None) -> dict[str, Any]:
    context = build_external_driver_context(symbol, primary_theme=(holding or {}).get("primary_theme"))
    evidence = [_clean_text(item) for item in context.evidence]
    return {
        "mapping": {
            "mapping_status": context.mapping_status,
            "profile_id": context.profile_id,
            "symbol": context.symbol,
            "message": context.message,
            "future_extension": context.future_extension,
            "drivers": context.drivers,
            "boundary": context.boundary,
            "llm_usage": "context_only",
            "interpretation_limit": "This mapping selects observation variables only and is not market evidence by itself.",
        },
        "auto_fact": [item for item in evidence if item.get("category") == "auto_fact"],
        "auto_signal": [item for item in evidence if item.get("category") == "auto_signal"],
        "missing_data": context.missing_data,
        "boundary": context.boundary,
    }


def _portfolio_external_driver_summary(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    symbol_sections: dict[str, dict[str, Any]] = {}
    for position in positions:
        symbol = position.get("symbol", "")
        symbol_sections[symbol] = _external_driver_sections(symbol, position)

    # Deduplicate by factor_id and aggregate associated_symbols
    driver_map: dict[str, dict[str, Any]] = {}
    for symbol, sections in symbol_sections.items():
        for ev in sections.get("auto_fact") or []:
            payload = ev.get("payload") or {}
            factor_id = payload.get("factor_id")
            if not factor_id:
                continue
            if factor_id not in driver_map:
                driver_map[factor_id] = {
                    "factor_id": factor_id,
                    "display_name": payload.get("display_name", factor_id),
                    "factor_type": payload.get("factor_type", "unknown"),
                    "associated_symbols": [],
                    "evidence": ev,
                }
            if symbol not in driver_map[factor_id]["associated_symbols"]:
                driver_map[factor_id]["associated_symbols"].append(symbol)

    result: list[dict[str, Any]] = []
    # Shared driver view (deduplicated)
    for driver in driver_map.values():
        result.append({
            "type": "shared_driver",
            "factor_id": driver["factor_id"],
            "display_name": driver["display_name"],
            "factor_type": driver["factor_type"],
            "associated_symbols": driver["associated_symbols"],
            "evidence": driver["evidence"],
        })

    # Per-symbol mapping view
    for position in positions:
        symbol = position.get("symbol", "")
        sections = symbol_sections.get(symbol, {})
        mapping = sections.get("mapping") or {}
        auto_fact = sections.get("auto_fact") or []
        result.append({
            "type": "symbol_mapping",
            "symbol": symbol,
            "primary_theme": position.get("primary_theme"),
            "mapping": mapping,
            "data_status": "available" if auto_fact else (
                "not_configured" if mapping.get("mapping_status") == "not_configured" else "unavailable"
            ),
            "evidence": auto_fact,
            "derived_observations": sections.get("auto_signal") or [],
            "missing_data": sections.get("missing_data") or [],
        })

    return result


def _unavailable_fact(symbol: str, coverage: str, reason: str, endpoint: str | None = None) -> dict[str, Any]:
    interpretation_limit = "Unavailable fact coverage is a data boundary, not evidence for or against the symbol."
    if coverage == "etf_share_change":
        interpretation_limit = "ETF share/NAV/price facts are unavailable. When available, share changes still do not imply future price direction."
    if coverage == "dragon_tiger_event":
        interpretation_limit = "Dragon-tiger facts are unavailable. When available, they reflect public abnormal-trading-day seat structure only, not long-term holding intent."
    if coverage == "disclosure_index":
        interpretation_limit = "Disclosure indexes are unavailable. When available, the system reads index data only, not announcement or survey full text."
    return {
        "evidence_id": f"unavailable_{coverage}_{symbol}",
        "symbol": symbol,
        "evidence_type": coverage,
        "category": "auto_fact",
        "title": f"{coverage} unavailable",
        "payload": {"coverage": coverage, "reason": reason},
        "source": "Stock-Pilot fact service",
        "source_endpoint": endpoint,
        "as_of_time": None,
        "as_of_date": None,
        "fetched_at": _now().isoformat(),
        "reliability": "B",
        "llm_usage": "context_only",
        "interpretation_limit": interpretation_limit,
        "freshness_days": None,
        "data_status": "unavailable",
        "notes": None,
    }


def _stage1_coverage_items(symbol: str, existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ts_code = to_ts_code(symbol)
    evidence_types = {item.get("evidence_type") for item in existing}
    additions: list[dict[str, Any]] = []
    if ts_code in SUPPORTED_ETFS:
        if "etf_share_change" not in evidence_types:
            try:
                result = get_etf_facts(ts_code)
                additions.extend(result.get("evidence") or [])
                if not result.get("evidence"):
                    additions.append(_unavailable_fact(ts_code, "etf_share_change", result.get("message") or "ETF fact service returned no evidence.", "etf_share_size,fund_nav,fund_daily"))
            except Exception as exc:
                additions.append(_unavailable_fact(ts_code, "etf_share_change", str(exc)[:200], "etf_share_size,fund_nav,fund_daily"))
        return [_clean_text(item) for item in additions]

    if "dragon_tiger_event" not in evidence_types:
        try:
            result = get_dragon_tiger_facts(ts_code)
            additions.extend(result.get("evidence") or [])
            if not result.get("evidence"):
                additions.append(_unavailable_fact(ts_code, "dragon_tiger_event", result.get("message") or "No recent event or data unavailable.", "top_list,top_inst"))
        except Exception as exc:
            additions.append(_unavailable_fact(ts_code, "dragon_tiger_event", str(exc)[:200], "top_list,top_inst"))
    if not ({"announcement_index", "survey_index"} & evidence_types):
        try:
            result = get_disclosure_facts(ts_code)
            additions.extend(result.get("evidence") or [])
            if not result.get("evidence"):
                additions.append(_unavailable_fact(ts_code, "disclosure_index", result.get("message") or "No recent disclosure index or data unavailable.", "anns_d,stk_surv"))
        except Exception as exc:
            additions.append(_unavailable_fact(ts_code, "disclosure_index", str(exc)[:200], "anns_d,stk_surv"))
    return [_clean_text(item) for item in additions]


def _target_name(snapshot: AnalysisSnapshot) -> str:
    for item in snapshot.evidence_items:
        payload = item.payload or {}
        if item.evidence_type.value == "realtime_quote" and payload.get("name"):
            return str(payload.get("name"))
        if item.evidence_type.value == "company_profile":
            for key in ("company_name", "name", "short_name"):
                if payload.get(key):
                    return str(payload.get(key))
    return ""


def _company_profile(snapshot: AnalysisSnapshot) -> dict[str, Any]:
    for item in snapshot.evidence_items:
        if item.evidence_type.value == "company_profile":
            return item.payload or {}
    return {}


def _company_profile_context(snapshot: AnalysisSnapshot) -> dict[str, Any]:
    profile = _company_profile(snapshot)
    if not profile:
        return {}
    company_name = profile.get("company_name") or profile.get("name") or profile.get("short_name")
    return {
        "company_name": company_name,
        "structured_fields": {
            "company_name": company_name,
            "list_date": profile.get("list_date"),
            "exchange": profile.get("exchange"),
            "industry": profile.get("industry") or profile.get("sw_industry"),
            "area": profile.get("area") or profile.get("city"),
        },
        "rule_inferred_context": {
            "concept_tags": profile.get("concept_tags") or [],
            "company_type": profile.get("company_type") or [],
        },
        "omitted_unverified_fields": [
            "main_business",
            "core_products",
            "industry_chain_position",
            "core_logic",
            "profit_driver",
            "competitive_advantage",
            "risk_points",
        ],
        "data_status": "context_only",
        "boundary": (
            "Only explicit structured identity fields are treated as basic facts. Rule-inferred profile, "
            "business logic, advantage, and risk summaries are context only and are not exported as hard facts."
        ),
    }


def _company_profile_context_item(snapshot: AnalysisSnapshot) -> dict[str, Any] | None:
    payload = _company_profile_context(snapshot)
    if not payload:
        return None
    return {
        "category": "system_hypothesis",
        "evidence_type": "company_profile_context",
        "title": "Company profile context",
        "source": "stock_meta/Tushare cache/rule inference",
        "source_endpoint": "build_company_profile",
        "reliability": "H",
        "llm_usage": "hypothesis_only",
        "data_status": "context_only",
        "payload": payload,
        "interpretation_limit": payload["boundary"],
    }


def _quote_time_meta(snapshot: AnalysisSnapshot, generated_at: datetime) -> dict[str, Any]:
    for item in snapshot.evidence_items:
        if item.evidence_type == EvidenceType.REALTIME_QUOTE:
            payload = item.payload or {}
            return {
                "quote_retrieved_at": payload.get("quote_retrieved_at") or item.fetched_at.isoformat(),
                "quote_market_time": payload.get("quote_market_time"),
                "quote_time_status": payload.get("quote_time_status") or "unavailable",
            }
    return {
        "quote_retrieved_at": generated_at.isoformat(),
        "quote_market_time": None,
        "quote_time_status": "unavailable",
    }


def _basic_information(symbol: str, snapshot: AnalysisSnapshot, holding: dict[str, Any] | None) -> dict[str, Any]:
    profile = _company_profile(snapshot)
    profile_context = _company_profile_context(snapshot)
    return {
        "symbol": symbol,
        "name": _target_name(snapshot),
        "industry": profile.get("industry") or profile.get("sw_industry"),
        "area": profile.get("area") or profile.get("city"),
        "listing_information": {
            "list_date": profile.get("list_date"),
            "exchange": profile.get("exchange"),
        },
        "company_profile": profile_context,
        "current_holding": _manual_account_section(holding),
        "data_status": "available" if profile else "unavailable",
    }


def _find_holding(symbol: str) -> dict[str, Any] | None:
    compact = symbol.split(".", 1)[0].zfill(6)
    state = portfolio_service.get_state()
    for position in state.snapshot.positions:
        if position.symbol.split(".", 1)[0].zfill(6) == compact:
            data = position.model_dump(mode="json")
            for weight in state.metrics.position_weights:
                if str(weight.get("symbol", "")).split(".", 1)[0].zfill(6) == compact:
                    data["portfolio_weight_pct"] = weight.get("weight_pct")
            return data
    return None


def _manual_evidence_for_symbol(symbol: str | None = None) -> list[dict[str, Any]]:
    compact = symbol.split(".", 1)[0].zfill(6) if symbol else None
    records = []
    for record in portfolio_service.list_manual_evidence():
        if not record.include_in_analysis_packet:
            continue
        if compact and record.symbol and record.symbol.split(".", 1)[0].zfill(6) != compact:
            continue
        if compact and record.symbol is None:
            continue
        records.append(_evidence_dict(portfolio_service._manual_record_to_evidence(record)))
    return records


def _manual_account_section(holding: dict[str, Any] | None) -> dict[str, Any]:
    if not holding:
        return {
            "has_holding": False,
            "message": "No local holding for this symbol in the current portfolio snapshot.",
        }
    return {
        "has_holding": True,
        "quantity": holding.get("quantity"),
        "available_quantity": holding.get("available_quantity"),
        "avg_cost": holding.get("avg_cost"),
        "broker_screenshot_price": holding.get("broker_screenshot_price"),
        "broker_screenshot_price_source": holding.get("broker_screenshot_price_source"),
        "broker_screenshot_price_time": holding.get("broker_screenshot_price_time"),
        "broker_screenshot_market_value": holding.get("broker_screenshot_market_value"),
        "broker_screenshot_unrealized_pnl": holding.get("broker_screenshot_unrealized_pnl"),
        "broker_screenshot_unrealized_pnl_pct": holding.get("broker_screenshot_unrealized_pnl_pct"),
        "system_quote_price": holding.get("system_quote_price") or holding.get("market_price"),
        "system_quote_retrieved_at": holding.get("system_quote_retrieved_at") or holding.get("quote_retrieved_at"),
        "system_quote_market_time": holding.get("system_quote_market_time"),
        "market_price": holding.get("market_price"),
        "quote_retrieved_at": holding.get("quote_retrieved_at"),
        "quote_market_time": None,
        "quote_time_status": "unavailable",
        "quote_time_boundary": QUOTE_TIME_BOUNDARY,
        "market_value": holding.get("market_value"),
        "unrealized_pnl": holding.get("unrealized_pnl"),
        "unrealized_pnl_pct": holding.get("unrealized_pnl_pct"),
        "portfolio_weight_pct": holding.get("portfolio_weight_pct"),
        "position_role": holding.get("position_role"),
        "primary_theme": holding.get("primary_theme"),
        "theme_tags": holding.get("theme_tags", []),
        "user_plan": holding.get("user_plan"),
        "invalid_condition": holding.get("invalid_condition"),
        "target_max_weight": holding.get("target_max_weight"),
        "data_status": holding.get("data_status"),
        "missing_data": holding.get("missing_data", []),
    }


def _single_hypotheses(snapshot: AnalysisSnapshot, holding: dict[str, Any] | None) -> list[dict[str, Any]]:
    items = [_evidence_dict(item) for item in snapshot.system_hypotheses]
    profile_context = _company_profile_context_item(snapshot)
    if profile_context:
        items.append(profile_context)
    if holding and holding.get("portfolio_weight_pct") is not None:
        items.append({
            "category": "system_hypothesis",
            "title": "Portfolio concentration reminder",
            "source": "Stock-Pilot packet builder",
            "reliability": "H",
            "llm_usage": "hypothesis_only",
            "data_status": "available",
            "payload": {
                "symbol": holding.get("symbol"),
                "portfolio_weight_pct": holding.get("portfolio_weight_pct"),
                "primary_theme": holding.get("primary_theme"),
                "theme_tags": holding.get("theme_tags", []),
                "risk_parameter_source": "system_default_placeholder",
                "unconfirmed_by_user": True,
            },
            "interpretation_limit": f"System-generated reminder only; manually question and verify it. {DEFAULT_RISK_BOUNDARY}",
        })
    return items


def _portfolio_auto_fact_summary(symbols: list[str]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for symbol in symbols:
        ts_code = to_ts_code(symbol)
        try:
            if ts_code in SUPPORTED_ETFS:
                result = get_etf_facts(ts_code)
                summaries.append({
                    "symbol": symbol,
                    "coverage": "etf_facts",
                    "data_status": result.get("data_status"),
                    "evidence": _clean_text(result.get("evidence", [])),
                    "boundary": "ETF share and NAV facts are observations only, not future return conclusions.",
                    "missing_reason": result.get("message") if not result.get("evidence") else None,
                })
            else:
                dragon = get_dragon_tiger_facts(ts_code)
                disclosure = get_disclosure_facts(ts_code)
                evidence = [*dragon.get("evidence", []), *disclosure.get("evidence", [])]
                summaries.append({
                    "symbol": symbol,
                    "coverage": "dragon_tiger_and_disclosure_index",
                    "data_status": "available" if evidence else "unavailable",
                    "evidence": _clean_text(evidence),
                    "boundary": "Indexes and public event facts are bounded context only; no announcement body or long-term fund intent is inferred.",
                    "missing_reason": (dragon.get("message") or disclosure.get("message")) if not evidence else None,
                })
        except Exception as exc:
            summaries.append({
                "symbol": symbol,
                "coverage": "not_covered",
                "data_status": "unavailable",
                "evidence": [],
                "missing_reason": str(exc)[:200],
            })
    return summaries


def _save_packet(packet: dict[str, Any], markdown: str) -> dict[str, str]:
    scope = packet["meta"]["analysis_scope"]
    leaf = packet["meta"].get("target_symbol") or packet["meta"].get("portfolio_id") or "default"
    out_dir = Path(settings.ANALYSIS_SNAPSHOT_DIR) / "analysis_packets" / scope / str(leaf)
    out_dir.mkdir(parents=True, exist_ok=True)
    packet_id = packet["meta"]["packet_id"]
    json_path = out_dir / f"{packet_id}.json"
    md_path = out_dir / f"{packet_id}.md"
    json_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    return {"json_path": str(json_path), "markdown_path": str(md_path)}


def _fallback_single_snapshot(symbol: str, reason: str, user_question: str | None = None) -> AnalysisSnapshot:
    now = _now()
    return AnalysisSnapshot(
        analysis_scope=AnalysisScope.SINGLE_STOCK,
        target_symbols=[symbol],
        user_question=user_question,
        market_data_as_of=None,
        daily_k_as_of=None,
        evidence_items=[
            EvidenceItem(
                symbol=symbol,
                evidence_type=EvidenceType.DATA_COVERAGE,
                category=EvidenceCategory.AUTO_FACT,
                title="Base market snapshot unavailable",
                payload={"reason": reason},
                source="Stock-Pilot snapshot builder",
                source_endpoint="build_basic_stock_snapshot",
                fetched_at=now,
                reliability=EvidenceReliability.B,
                llm_usage=LlmUsage.CONTEXT_ONLY,
                interpretation_limit="Base quote/history snapshot is unavailable; use this as a data boundary only.",
                data_status=DataStatus.UNAVAILABLE,
            )
        ],
        missing_data=[{"key": "base_market_snapshot", "reason": reason}],
        system_hypotheses=[],
    )


def build_single_stock_packet(symbol: str, user_question: str | None = None, persist: bool = True) -> dict[str, Any]:
    try:
        snapshot = build_basic_stock_snapshot(symbol, user_question=user_question, persist=True)
    except Exception as exc:
        snapshot = _fallback_single_snapshot(symbol, str(exc)[:240], user_question=user_question)
    holding = _find_holding(symbol)
    generated_at = _now()
    auto_fact = _filter_evidence(snapshot, EvidenceCategory.AUTO_FACT)
    auto_fact.extend(_stage1_coverage_items(symbol, auto_fact))
    auto_signal = _filter_evidence(snapshot, EvidenceCategory.AUTO_SIGNAL)
    external_driver = _external_driver_sections(symbol, holding)
    auto_fact.extend(external_driver["auto_fact"])
    auto_signal.extend(external_driver["auto_signal"])
    missing_data = _clean_text([_jsonable(item) for item in snapshot.missing_data])
    missing_data.extend(_clean_text(external_driver["missing_data"]))
    interpretation_boundaries = GLOBAL_BOUNDARIES.copy()
    if external_driver["boundary"] not in interpretation_boundaries:
        interpretation_boundaries.append(external_driver["boundary"])
    quote_time = _quote_time_meta(snapshot, generated_at)
    packet = {
        "meta": {
            "packet_id": f"packet_{uuid4().hex}",
            "packet_version": PACKET_VERSION,
            "generated_at": generated_at.isoformat(),
            "analysis_scope": "single_stock",
            "target_symbol": symbol,
            "target_name": _target_name(snapshot),
            "user_question": user_question,
            **quote_time,
            "daily_k_as_of": snapshot.daily_k_as_of.isoformat() if snapshot.daily_k_as_of else None,
            "portfolio_as_of": portfolio_service.get_state().snapshot.snapshot_time.isoformat() if holding else None,
            "source_snapshot_id": snapshot.snapshot_id,
        },
        "privacy_notice": PRIVACY_NOTICE,
        "basic_information": _basic_information(symbol, snapshot, holding),
        "stock_profile": {
            "symbol": symbol,
            "name": _target_name(snapshot),
            "profile": _company_profile_context(snapshot),
            "holding": holding,
        },
        "external_driver_mapping": external_driver["mapping"],
        "auto_fact": auto_fact,
        "auto_signal": auto_signal,
        "manual_account": _manual_account_section(holding),
        "manual_evidence": _manual_evidence_for_symbol(symbol),
        "system_hypothesis": _single_hypotheses(snapshot, holding),
        "missing_data": missing_data,
        "interpretation_boundaries": interpretation_boundaries,
        "missing_data_and_boundaries": [*interpretation_boundaries, *missing_data],
        "suggested_questions_for_external_llm": SINGLE_LLM_QUESTIONS,
        "llm_questions": SINGLE_LLM_QUESTIONS,
    }
    markdown = render_packet_markdown(packet)
    result = {"packet": packet, "markdown": markdown}
    if persist:
        result["saved_paths"] = _save_packet(packet, markdown)
    return result


def build_portfolio_packet(user_question: str | None = None, persist: bool = True) -> dict[str, Any]:
    state = portfolio_service.get_state()
    snapshot = portfolio_service.build_portfolio_snapshot(user_question=user_question, persist=True)
    generated_at = _now()
    positions = []
    weights = {item.get("symbol"): item for item in state.metrics.position_weights}
    for position in state.snapshot.positions:
        data = position.model_dump(mode="json")
        data["portfolio_weight_pct"] = (weights.get(position.symbol) or {}).get("weight_pct")
        data["weight_pct"] = data["portfolio_weight_pct"]
        data["quote_retrieved_at"] = generated_at.isoformat()
        data["quote_market_time"] = None
        data["quote_time_status"] = "unavailable"
        data["quote_time_boundary"] = QUOTE_TIME_BOUNDARY
        positions.append(data)
    rule_reminders = [_evidence_dict(item) for item in snapshot.system_hypotheses]
    high_volatility = [
        item for item in state.metrics.risk_tag_exposures
        if item.theme == "HIGH_VOLATILITY" and item.weight_pct > 0
    ]
    for exposure in high_volatility:
        rule_reminders.append({
            "category": "system_hypothesis",
            "title": "High volatility asset exposure reminder",
            "source": "Stock-Pilot portfolio rules",
            "source_endpoint": "portfolio.compute_metrics",
            "as_of_time": state.snapshot.snapshot_time.isoformat(),
            "fetched_at": generated_at.isoformat(),
            "reliability": "H",
            "llm_usage": "hypothesis_only",
            "data_status": "available",
            "payload": exposure.model_dump(mode="json"),
            "risk_parameter_source": "system_default_placeholder",
            "unconfirmed_by_user": True,
            "interpretation_limit": f"System-generated risk reminder based on user tags only; verify whether the tag is appropriate before using it. {DEFAULT_RISK_BOUNDARY}",
        })
    for reminder in rule_reminders:
        reminder.setdefault("risk_parameter_source", "system_default_placeholder")
        reminder.setdefault("unconfirmed_by_user", True)
        current_limit = reminder.get("interpretation_limit") or "System-generated hypothesis only."
        reminder["interpretation_limit"] = current_limit if DEFAULT_RISK_BOUNDARY in current_limit else f"{current_limit} {DEFAULT_RISK_BOUNDARY}"
    missing_data = _clean_text([
        *state.metrics.missing_data,
        {"key": "broker_sync", "reason": "Broker account sync is not implemented."},
        {"key": "quote_time", "reason": QUOTE_TIME_BOUNDARY},
        {"key": "repo_cash_equivalent_policy", "reason": REPO_BOUNDARY},
    ])
    interpretation_boundaries = GLOBAL_BOUNDARIES.copy()
    external_driver_summary = _portfolio_external_driver_summary(positions)
    if any(
        item.get("type") == "symbol_mapping" and item.get("mapping", {}).get("mapping_status") == "configured"
        for item in external_driver_summary
    ):
        interpretation_boundaries.append("Portfolio external-driver sections are symbol-level context only and must not be aggregated into macro conclusions.")
    packet = {
        "meta": {
            "packet_id": f"packet_{uuid4().hex}",
            "packet_version": PACKET_VERSION,
            "generated_at": generated_at.isoformat(),
            "analysis_scope": "portfolio",
            "portfolio_id": state.snapshot.portfolio_id,
            "portfolio_as_of": state.snapshot.snapshot_time.isoformat(),
            "source_snapshot_id": snapshot.snapshot_id,
            "user_question": user_question,
        },
        "privacy_notice": PRIVACY_NOTICE,
        "account_overview": {
            "total_assets": state.metrics.total_assets,
            "total_market_value": state.metrics.total_market_value,
            "cash_available": state.metrics.cash_available,
            "repo_amount": state.metrics.repo_amount,
            "repo_available_date": state.snapshot.repo_available_date.isoformat() if state.snapshot.repo_available_date else None,
            "total_position_weight": state.metrics.invested_ratio_pct,
            "cash_weight": state.metrics.cash_ratio_pct,
            "repo_weight": state.metrics.repo_ratio_pct,
            "invested_ratio_pct": state.metrics.invested_ratio_pct,
            "cash_ratio_pct": state.metrics.cash_ratio_pct,
            "repo_ratio_pct": state.metrics.repo_ratio_pct,
            "repo_policy": {
                "cash_equivalent_treatment": "unconfirmed",
                "boundary": REPO_BOUNDARY,
            },
            "notes": state.snapshot.notes,
        },
        "holdings": positions,
        "positions": positions,
        "primary_theme_exposure": [item.model_dump(mode="json") for item in state.metrics.primary_theme_exposures],
        "related_risk_observations": {
            "risk_tag_exposure": [item.model_dump(mode="json") for item in state.metrics.risk_tag_exposures],
            "composite_exposure_notes": [
                {
                    "symbol": position.symbol,
                    "theme_tags": position.theme_tags,
                    "message": "Composite exposure: this holding has multiple risk tags. It is counted once in primary_theme exposure and must not be double counted through tags.",
                }
                for position in state.snapshot.positions
                if len(set(position.theme_tags)) > 1 or "COMPOSITE_EXPOSURE" in set(position.theme_tags)
            ],
            "boundary": "Primary theme exposure is unique attribution. Theme tag observations are non-additive and must not be summed as asset weights.",
        },
        "system_hypothesis": rule_reminders,
        "rule_reminders": rule_reminders,
        "manual_evidence": _manual_evidence_for_symbol(None),
        "auto_fact_summary": _portfolio_auto_fact_summary([p.symbol for p in state.snapshot.positions]),
        "external_driver_summary": external_driver_summary,
        "missing_data": missing_data,
        "interpretation_boundaries": interpretation_boundaries,
        "missing_data_and_boundaries": [*interpretation_boundaries, *missing_data],
        "suggested_questions_for_external_llm": PORTFOLIO_LLM_QUESTIONS,
        "llm_questions": PORTFOLIO_LLM_QUESTIONS,
    }
    markdown = render_packet_markdown(packet)
    result = {"packet": packet, "markdown": markdown}
    if persist:
        result["saved_paths"] = _save_packet(packet, markdown)
    return result


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _render_single_external_drivers(packet: dict[str, Any]) -> str:
    mapping = packet.get("external_driver_mapping") or {}
    lines = [
        "## Relevant External Drivers",
        "",
        "### Mapping Context",
        f"- profile_id: {_fmt(mapping.get('profile_id'))}",
        f"- mapping_status: {_fmt(mapping.get('mapping_status'))}",
        f"- boundary: {_fmt(mapping.get('boundary'))}",
        "",
        "### Driver Status",
    ]
    evidence_by_factor = {
        (item.get("payload") or {}).get("factor_id"): item
        for item in [*packet.get("auto_fact", []), *packet.get("auto_signal", [])]
        if (item.get("payload") or {}).get("factor_id")
    }
    missing_by_factor = {
        str(item.get("key", "")).split("external_driver:", 1)[-1]: item
        for item in packet.get("missing_data", [])
        if isinstance(item, dict) and str(item.get("key", "")).startswith("external_driver:")
    }
    for driver in mapping.get("drivers") or []:
        factor_id = driver.get("factor_id")
        evidence = evidence_by_factor.get(factor_id)
        payload = (evidence or {}).get("payload") or {}
        missing = missing_by_factor.get(factor_id) or {}
        data_status = payload.get("data_status") or (evidence or {}).get("data_status")
        if not data_status:
            data_status = "pending_probe" if driver.get("status") == "pending_probe" else "unavailable"
        reason = payload.get("reason") or missing.get("reason")
        lines.extend([
            f"- {factor_id}",
            f"  - data_status: {_fmt(data_status)}",
        ])
        if reason:
            lines.append(f"  - reason: {_fmt(reason)}")
        if payload.get("trade_date"):
            lines.append(f"  - trade_date: {_fmt(payload.get('trade_date'))}")
        if payload.get("close") is not None:
            lines.append(f"  - close: {_fmt(payload.get('close'))}")
        lines.append(
            f"  - interpretation_limit: "
            f"{_fmt(driver.get('interpretation_limit') or (evidence or {}).get('interpretation_limit'))}"
        )
    return "\n".join(lines) + "\n"


def _evidence_markdown(items: list[dict[str, Any]]) -> str:
    if not items:
        return "- No available evidence in this section.\n"
    lines = []
    for item in items:
        lines.append(f"- **{_fmt(item.get('title'))}**")
        lines.append(f"  - category: `{_fmt(item.get('category'))}`; type: `{_fmt(item.get('evidence_type'))}`")
        lines.append(f"  - source: {_fmt(item.get('source'))}; endpoint: {_fmt(item.get('source_endpoint'))}")
        if item.get("evidence_type") == "realtime_quote":
            payload = item.get("payload") or {}
            lines.append(f"  - quote_retrieved_at: {_fmt(payload.get('quote_retrieved_at') or item.get('fetched_at') or item.get('recorded_at'))}")
            lines.append(f"  - quote_market_time: {_fmt(payload.get('quote_market_time'))}; quote_time_status: `{_fmt(payload.get('quote_time_status') or 'unavailable')}`")
        else:
            lines.append(f"  - as_of: {_fmt(item.get('as_of_time') or item.get('as_of_date'))}; fetched/recorded: {_fmt(item.get('fetched_at') or item.get('recorded_at'))}")
        lines.append(f"  - reliability: `{_fmt(item.get('reliability'))}`; llm_usage: `{_fmt(item.get('llm_usage'))}`; data_status: `{_fmt(item.get('data_status'))}`")
        if item.get("interpretation_limit"):
            lines.append(f"  - boundary: {_fmt(item.get('interpretation_limit'))}")
        payload = item.get("payload") or item.get("payload_summary") or item.get("text") or item.get("value")
        if payload:
            lines.append(f"  - payload: `{_fmt(payload)}`")
    return "\n".join(lines) + "\n"


def render_packet_markdown(packet: dict[str, Any]) -> str:
    meta = packet["meta"]
    lines = [
        f"# Stock-Pilot Analysis Packet v1 - {meta['analysis_scope']}",
        "",
        "## Privacy and External Sharing Boundary",
        PRIVACY_NOTICE,
        "",
        f"Quote-time boundary: {QUOTE_TIME_BOUNDARY}",
        f"Default-risk boundary: {DEFAULT_RISK_BOUNDARY}",
        f"Repo boundary: {REPO_BOUNDARY}",
        "",
        "## Packet Metadata",
    ]
    for key, value in meta.items():
        lines.append(f"- {key}: {_fmt(value)}")

    if meta["analysis_scope"] == "single_stock":
        account = packet["manual_account"]
        lines.extend([
            "",
            "## Basic Information",
            f"```json\n{json.dumps(packet['basic_information'], ensure_ascii=False, indent=2, default=str)}\n```",
            "",
            "## Auto Fact",
            _evidence_markdown(packet["auto_fact"]),
            "## Auto Signal",
            "Auxiliary observations only; these are not factual conclusions or buy/sell instructions.",
            _evidence_markdown(packet["auto_signal"]),
            "## Manual Account",
            f"```json\n{json.dumps(account, ensure_ascii=False, indent=2, default=str)}\n```",
            "",
            "## Manual Evidence",
            _evidence_markdown(packet["manual_evidence"]),
            _render_single_external_drivers(packet),
            "## System Hypothesis and Risk Reminders",
            "System-generated, must be questioned and manually verified.",
            _evidence_markdown(packet["system_hypothesis"]),
        ])
    else:
        lines.extend([
            "",
            "## Account Overview",
            f"```json\n{json.dumps(packet['account_overview'], ensure_ascii=False, indent=2, default=str)}\n```",
            "",
            "## Current Holdings",
            f"```json\n{json.dumps(packet['holdings'], ensure_ascii=False, indent=2, default=str)}\n```",
            "",
            "## Primary Theme Exposure",
            "Unique attribution by `primary_theme`; this is the additive theme exposure view.",
            f"```json\n{json.dumps(packet['primary_theme_exposure'], ensure_ascii=False, indent=2, default=str)}\n```",
            "",
            "## Related Risk Observations",
            packet["related_risk_observations"]["boundary"],
            f"```json\n{json.dumps(packet['related_risk_observations'], ensure_ascii=False, indent=2, default=str)}\n```",
            "",
            "## System Hypothesis and Risk Reminders",
            "System-generated hypotheses only; not facts and not trading advice.",
            _evidence_markdown(packet["system_hypothesis"]),
            "## Manual Evidence",
            _evidence_markdown(packet["manual_evidence"]),
            "## Auto Fact Summary",
            f"```json\n{json.dumps(packet['auto_fact_summary'], ensure_ascii=False, indent=2, default=str)}\n```",
            "",
            "## External Driver Summary",
            "Symbol-level external-driver observations only; not macro scoring or trading advice.",
            f"```json\n{json.dumps(packet['external_driver_summary'], ensure_ascii=False, indent=2, default=str)}\n```",
        ])

    lines.extend([
        "",
        "## Missing Data",
        *[f"- {_fmt(item)}" for item in packet["missing_data"]],
        "",
        "## Interpretation Boundaries",
        *[f"- {_fmt(item)}" for item in packet["interpretation_boundaries"]],
        "",
        "## Neutral Questions for an External LLM",
        *[f"- {question}" for question in packet["suggested_questions_for_external_llm"]],
        "",
        "No buy/sell recommendation is generated by this packet.",
    ])
    return "\n".join(lines)
