from __future__ import annotations

import json
from datetime import datetime, timezone
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
    "Please summarize the official exposure structure under confirmed primary_theme and state that theme_tags are non-additive related observations only.",
    "Please identify holdings that share the same or related external-driver context, and state that these links are contextual observations rather than causal conclusions.",
    "Please list missing account records, holding plans, role notes, or external facts that would materially affect further review.",
    "Please organize observations into focus areas, information to supplement, and items without enough basis for judgment; do not output buy, sell, or position-adjustment instructions.",
    "Please state which conclusions are contextual assumptions rather than verified facts.",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_z(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        if value.endswith("Z"):
            return value
        if value.endswith("+00:00"):
            return value.replace("+00:00", "Z")
        return value + "Z"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


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


def _compact_external_driver_summary(summary: list[dict[str, Any]]) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    for item in summary:
        if item.get("type") != "shared_driver":
            continue
        evidence = item.get("evidence") or {}
        payload = evidence.get("payload") or {}
        factor_type = payload.get("factor_type") or item.get("factor_type", "unknown")
        # 10. Hide pure unsupported placeholders from compact
        if factor_type == "unsupported_placeholder":
            continue
        data_status = payload.get("data_status") or evidence.get("data_status") or "unavailable"
        if data_status == "available":
            observations.append({
                "factor_id": item.get("factor_id"),
                "display_name": _driver_label(item.get("factor_id", "")),
                "associated_symbols": item.get("associated_symbols", []),
                "close": payload.get("close"),
                "currency": payload.get("currency"),
                "quote_unit": payload.get("quote_unit"),
                "returns_pct": payload.get("returns_pct"),
            })
        else:
            unavailable.append({
                "factor_id": item.get("factor_id"),
                "display_name": _driver_label(item.get("factor_id", "")),
                "associated_symbols": item.get("associated_symbols", []),
                "data_status": data_status,
                "reason": payload.get("reason"),
            })

    # Also collect missing_data from symbol_mappings
    for item in summary:
        if item.get("type") != "symbol_mapping":
            continue
        for md in item.get("missing_data", []):
            factor_id = str(md.get("key", "")).replace("external_driver:", "")
            if not factor_id:
                continue
            factor_type = md.get("factor_type", "unknown")
            if factor_type == "unsupported_placeholder":
                continue
            existing = next((d for d in unavailable if d.get("factor_id") == factor_id), None)
            if existing:
                sym = item.get("symbol")
                if sym and sym not in existing["associated_symbols"]:
                    existing["associated_symbols"].append(sym)
            else:
                unavailable.append({
                    "factor_id": factor_id,
                    "display_name": _driver_label(factor_id),
                    "associated_symbols": [item.get("symbol")] if item.get("symbol") else [],
                    "data_status": md.get("mapping_status", "unavailable"),
                    "reason": md.get("reason"),
                })

    return {
        "shared_external_driver_observations": observations,
        "unavailable_drivers": unavailable,
        "boundary": "External-driver observations are contextual only and do not establish causal effects or trading conclusions.",
    }


def _is_user_confirmed_role(item: dict[str, Any]) -> bool:
    return item.get("semantic_classification_status") == "user_confirmed" or bool(item.get("semantic_classification_confirmed_at"))


def _is_missing_position_role(item: dict[str, Any]) -> bool:
    role = str(item.get("confirmed_position_role") or "").strip().lower()
    if role in ("", "unclassified"):
        return True
    if role == "observation" and not _is_user_confirmed_role(item):
        return True
    return False


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
        "confirmed_position_role": holding.get("position_role"),
        "confirmed_primary_theme": holding.get("primary_theme"),
        "confirmed_theme_tags": holding.get("theme_tags", []),
        "semantic_classification_status": holding.get("semantic_classification_status"),
        "semantic_classification_source": holding.get("semantic_classification_source"),
        "account_analysis_boundary": "Single-stock packet may show this holding relationship read-only; account-level position and portfolio analysis belongs in the future personal investment dashboard.",
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
        data["confirmed_primary_theme"] = data.get("primary_theme")
        data["confirmed_theme_tags"] = data.get("theme_tags", [])
        data["confirmed_position_role"] = data.get("position_role")
        positions.append(data)
    rule_reminders = [_evidence_dict(item) for item in snapshot.system_hypotheses]
    high_volatility = [
        item for item in state.metrics.risk_tag_exposures
        if item.theme == "HIGH_VOLATILITY" and item.weight_pct > 0
    ]
    for exposure in high_volatility:
        rule_reminders.append({
            "category": "system_hypothesis",
            "title": "High-volatility tag observation",
            "source": "Stock-Pilot portfolio rules",
            "source_endpoint": "portfolio.compute_metrics",
            "as_of_time": state.snapshot.snapshot_time.isoformat(),
            "fetched_at": generated_at.isoformat(),
            "reliability": "H",
            "llm_usage": "hypothesis_only",
            "data_status": "available",
            "payload": exposure.model_dump(mode="json"),
            "risk_parameter_source": "user_confirmed_theme_tags",
            "unconfirmed_by_user": False,
            "interpretation_limit": "High-volatility tag observation only. It summarizes holdings with the user-confirmed HIGH_VOLATILITY tag, does not use a threshold, and is not a buy/sell or position-adjustment conclusion.",
        })
    for reminder in rule_reminders:
        reminder.setdefault("risk_parameter_source", "system_default_placeholder")
        reminder.setdefault("unconfirmed_by_user", True)
        reminder.setdefault("inactive_for_ai_reasoning", True)
        current_limit = reminder.get("interpretation_limit") or "System-generated hypothesis only."
        if reminder.get("risk_parameter_source") == "user_confirmed_theme_tags":
            reminder["interpretation_limit"] = current_limit
        else:
            reminder["interpretation_limit"] = current_limit if DEFAULT_RISK_BOUNDARY in current_limit else f"{current_limit} {DEFAULT_RISK_BOUNDARY}"
    unclassified_holdings = [
        item for item in positions
        if not item.get("confirmed_primary_theme") or str(item.get("confirmed_primary_theme")).upper() == "UNCLASSIFIED"
    ]
    data_gaps = [
        *state.metrics.missing_data,
        *[
            {
                "key": "holding_semantics",
                "symbol": item.get("symbol"),
                "reason": "Holding primary_theme is not confirmed; account theme analysis is incomplete.",
            }
            for item in unclassified_holdings
        ],
        *[
            {
                "key": "holding_position_role",
                "symbol": item.get("symbol"),
                "reason": "Holding position_role is missing, unclassified, or observation without user confirmation.",
            }
            for item in positions
            if _is_missing_position_role(item)
        ],
    ]
    missing_data = _clean_text([
        *data_gaps,
        {"key": "broker_sync", "reason": "Broker account sync is not implemented."},
        {"key": "quote_time", "reason": QUOTE_TIME_BOUNDARY},
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
            "valuation_basis": "current_quote_estimate",
            "snapshot_valuation": {
                "snapshot_as_of": state.snapshot.snapshot_time.isoformat(),
                "snapshot_total_assets": state.snapshot.total_assets,
                "snapshot_cash_available": state.snapshot.cash_available,
                "snapshot_repo_amount": state.snapshot.repo_amount,
                "boundary": "Snapshot values reflect the locally saved account record at snapshot time.",
            },
            "current_quote_estimate": {
                "quote_retrieved_at": generated_at.isoformat(),
                "current_enriched_market_value": state.metrics.total_market_value,
                "cash_carried_from_snapshot": state.metrics.cash_available,
                "repo_carried_from_snapshot": state.metrics.repo_amount,
                "estimated_total_assets_using_current_quotes": state.metrics.estimated_total_assets_using_current_quotes,
                "estimated_position_weight_pct": state.metrics.estimated_position_weight_pct,
                "estimated_cash_weight_pct": state.metrics.estimated_cash_weight_pct,
                "estimated_repo_weight_pct": state.metrics.estimated_repo_weight_pct,
                "boundary": "Estimated total assets use system-retrieved holding prices plus cash/repo values carried from the saved snapshot; this is not broker-verified realtime total assets.",
            },
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
        "official_theme_exposure": [item.model_dump(mode="json") for item in state.metrics.primary_theme_exposures],
        "related_risk_observations": {
            "risk_tag_exposure": [item.model_dump(mode="json") for item in state.metrics.risk_tag_exposures],
            "composite_exposure_notes": [
                {
                    "symbol": position.symbol,
                    "theme_tags": position.theme_tags,
                    "message": "Composite exposure: this holding has multiple risk tags. It is counted once in primary_theme exposure and must not be double counted through tags.",
                }
                for position in state.snapshot.positions
                if "COMPOSITE_EXPOSURE" in set(position.theme_tags)
            ],
            "boundary": "Primary theme exposure is unique attribution. Theme tag observations are non-additive and must not be summed as asset weights.",
        },
        "related_theme_observations": {
            "theme_tag_exposure": [item.model_dump(mode="json") for item in state.metrics.risk_tag_exposures],
            "composite_exposure_notes": [
                {
                    "symbol": position.symbol,
                    "theme_tags": position.theme_tags,
                    "message": "theme_tags are related observations only and are not added into official asset exposure.",
                }
                for position in state.snapshot.positions
                if "COMPOSITE_EXPOSURE" in set(position.theme_tags)
            ],
            "boundary": "primary_theme is the single official attribution; theme_tags are non-additive observations.",
        },
        "system_hypothesis": rule_reminders,
        "rule_reminders": rule_reminders,
        "manual_evidence": _manual_evidence_for_symbol(None),
        "auto_fact_summary": _portfolio_auto_fact_summary([p.symbol for p in state.snapshot.positions]),
        "external_driver_summary": external_driver_summary,
        "data_gaps": missing_data,
        "ai_analysis_boundary": {
            "intended_use": "Future dashboard account-level review and candidate watch items.",
            "not_trade_execution": True,
            "external_llm_called": False,
            "inactive_rules_for_ai_reasoning": [
                "single_position_limit",
                "primary_theme_limit",
                "cash_floor",
                "repo_cash_equivalent_policy",
            ],
            "inactive_decision_rules": [
                "single_position_limit",
                "primary_theme_limit",
                "cash_floor",
                "repo_cash_equivalent_policy",
            ],
            "boundary": "Current context is only for account fact summary, theme-structure observation, shared external-driver organization, and data-gap identification. Disabled position, cash, and repo rules must not be used as AI action or discipline-violation grounds. theme_tags do not participate in official exposure sums.",
        },
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


_THEME_LABEL_MAP = {
    "AI_PCB": "AI / PCB",
    "AI_THEME_ETF": "AI 主题 ETF",
    "METAL_RESOURCE": "金属资源",
    "GOLD": "黄金",
    "COPPER": "铜",
    "TUNGSTEN": "钨",
    "CASH_EQUIVALENT": "现金等价",
    "HIGH_VOLATILITY": "高波动关联",
    "COMPOSITE_EXPOSURE": "多重逻辑关联",
    "OTHER": "其他",
    "UNCLASSIFIED": "待分类",
}

_DIRECTION_TAGS = {"AI_PCB", "AI_THEME_ETF", "METAL_RESOURCE", "GOLD", "COPPER", "TUNGSTEN", "CASH_EQUIVALENT", "OTHER"}
_RISK_TAGS = {"HIGH_VOLATILITY"}
_EXCLUDED_FROM_COMPACT = {"COMPOSITE_EXPOSURE", "UNCLASSIFIED"}

_DRIVER_LABEL_MAP = {
    "comex_copper_yahoo": "COMEX 铜参考",
    "comex_gold_yahoo": "COMEX 黄金参考",
    "comex_silver_yahoo": "COMEX 白银参考",
    "copper_futures": "国内铜参考",
    "gold_futures": "国内黄金参考",
    "usd_cnh": "USD/CNH",
    "gold_etf_159934": "黄金 ETF 背景",
    "ai_theme_etf_159382": "AI 主题 ETF 背景",
    "pcb_sector_index_placeholder": "PCB 板块指数",
    "tungsten_price_placeholder": "钨价格",
    "tin_price_placeholder": "锡价格",
    "cobalt_moly_price_placeholder": "钴/钼价格",
    "resource_sector_index_placeholder": "资源板块指数",
}

_ROLE_LABEL_MAP = {
    "observation": "观察",
    "core": "核心",
    "trend": "趋势",
    "defensive": "防御",
    "unclassified": "待分类",
}

_COMPACT_LLM_QUESTIONS = [
    "请总结当前持仓在已确认 primary_theme 下的正式暴露结构，并说明 theme_tags 仅是非加总的关联观察。",
    "请识别共享相同或相关外部驱动上下文的持仓，并说明这些关联仅为背景观察而非因果结论。",
    "请列出缺失的账户记录、持仓计划、角色备注或外部事实，这些因素可能显著影响后续复核。",
    "请将观察整理为关注区域、待补充信息，以及尚无足够依据做出判断的条目；不输出买入、卖出或调仓指令。",
    "请说明哪些结论是情境假设而非已验证事实。",
]

_COMPACT_BOUNDARIES = [
    "隐私边界：本上下文由本地生成，不会自动发送给外部 AI；仅在用户主动复制、导出或提交时外传。",
    "行情时间边界：当前 A 股行情源不提供可验证市场报价时间；总资产与浮动盈亏均为系统当前取价估算。",
    "主题口径边界：正式主题按主主题唯一加总；关联方向仅用于补充观察，不得重复统计为资产暴露。",
    "外部驱动边界：COMEX、汇率、ETF 或其他外部驱动仅作为关联背景，不构成因果结论、估值结论或买卖建议。",
]


def _theme_label(key: str) -> str:
    return _THEME_LABEL_MAP.get(key, key)


def _driver_label(key: str) -> str:
    return _DRIVER_LABEL_MAP.get(key, key)


def build_account_analysis_context(mode: str = "compact") -> dict[str, Any]:
    result = build_portfolio_packet(user_question=None, persist=False)
    packet = result["packet"]

    if mode == "audit":
        return {
            "meta": {
                "generated_at": _iso_z(packet["meta"]["generated_at"]),
                "portfolio_snapshot_id": packet["meta"]["source_snapshot_id"],
                "portfolio_as_of": _iso_z(packet["meta"]["portfolio_as_of"]),
                "quote_time_boundary": QUOTE_TIME_BOUNDARY,
                "privacy_boundary": PRIVACY_NOTICE,
            },
            "account_facts": {
                **packet["account_overview"],
                "holdings_count": len(packet["holdings"]),
            },
            "holdings": [
                {
                    "symbol": item.get("symbol"),
                    "name": item.get("name"),
                    "quantity": item.get("quantity"),
                    "avg_cost": item.get("avg_cost"),
                    "market_value": item.get("market_value"),
                    "unrealized_pnl": item.get("unrealized_pnl"),
                    "unrealized_pnl_pct": item.get("unrealized_pnl_pct"),
                    "portfolio_weight_pct": item.get("portfolio_weight_pct"),
                    "confirmed_primary_theme": item.get("confirmed_primary_theme"),
                    "confirmed_theme_tags": item.get("confirmed_theme_tags", []),
                    "confirmed_position_role": item.get("confirmed_position_role"),
                    "external_driver_profile_id": None,
                    "data_status": item.get("data_status"),
                }
                for item in packet["holdings"]
            ],
            "official_theme_exposure": packet["official_theme_exposure"],
            "related_theme_observations": packet["related_theme_observations"],
            "external_driver_summary": _compact_external_driver_summary(packet["external_driver_summary"]),
            "data_gaps": packet["data_gaps"],
            "ai_analysis_boundary": packet["ai_analysis_boundary"],
            "suggested_questions_for_external_llm": packet["suggested_questions_for_external_llm"],
        }

    # Compact mode
    state = portfolio_service.get_state()
    metrics = state.metrics
    has_repo = bool(metrics.repo_amount and metrics.repo_amount > 0)

    account_facts: dict[str, Any] = {
        "total_assets": metrics.total_assets,
        "total_market_value": metrics.total_market_value,
        "cash_available": metrics.cash_available,
        "invested_ratio_pct": metrics.invested_ratio_pct,
        "cash_ratio_pct": metrics.cash_ratio_pct,
        "total_cost_basis": metrics.total_cost_basis,
        "total_unrealized_pnl": metrics.total_unrealized_pnl,
        "total_unrealized_pnl_pct": metrics.total_unrealized_pnl_pct,
        "total_unrealized_pnl_status": metrics.total_unrealized_pnl_status,
    }
    if has_repo:
        account_facts["repo_amount"] = metrics.repo_amount
        account_facts["repo_ratio_pct"] = metrics.repo_ratio_pct

    # Build name/primary maps and compact holdings
    symbol_name_map: dict[str, str] = {}
    symbol_primary_map: dict[str, str] = {}
    compact_holdings = []
    for item in packet["holdings"]:
        symbol = item.get("symbol", "")
        name = item.get("name") or symbol
        symbol_name_map[symbol] = name
        symbol_primary_map[symbol] = item.get("confirmed_primary_theme") or ""
        compact_holdings.append({
            "symbol": symbol,
            "name": name,
            "quantity": item.get("quantity"),
            "avg_cost": item.get("avg_cost"),
            "market_price": item.get("market_price") or item.get("system_quote_price"),
            "market_value": item.get("market_value"),
            "unrealized_pnl": item.get("unrealized_pnl"),
            "unrealized_pnl_pct": item.get("unrealized_pnl_pct"),
            "portfolio_weight_pct": item.get("portfolio_weight_pct"),
            "confirmed_primary_theme": item.get("confirmed_primary_theme"),
            "confirmed_theme_tags": item.get("confirmed_theme_tags", []),
            "confirmed_position_role": item.get("confirmed_position_role"),
        })

    # 1. Tag exposure split into direction_observations and risk_observations
    # Keep a tag only if at least one holding with that tag has primary_theme != tag.
    tag_aggregates: dict[str, dict[str, Any]] = {}
    for item in packet["holdings"]:
        symbol = item.get("symbol", "")
        primary = item.get("confirmed_primary_theme", "")
        mv = item.get("market_value") or 0
        for tag in item.get("confirmed_theme_tags", []):
            if not tag or tag in _EXCLUDED_FROM_COMPACT:
                continue
            entry = tag_aggregates.setdefault(tag, {"market_value": 0.0, "symbols": [], "all_same_as_primary": True})
            entry["market_value"] += mv
            entry["symbols"].append(symbol)
            if tag != primary:
                entry["all_same_as_primary"] = False

    total_assets_for_wp = metrics.total_assets or 1
    direction_observations = []
    risk_observations = []
    for tag, data in sorted(tag_aggregates.items(), key=lambda x: x[1]["market_value"], reverse=True):
        if data["all_same_as_primary"]:
            continue
        mv = data["market_value"]
        wp = mv / total_assets_for_wp * 100
        obs = {
            "theme": tag,
            "market_value": round(mv, 2),
            "weight_pct": round(wp, 2),
            "symbols": sorted(set(data["symbols"])),
        }
        if tag in _DIRECTION_TAGS:
            direction_observations.append(obs)
        elif tag in _RISK_TAGS:
            risk_observations.append(obs)

    # Data gaps: remove broker_sync and quote_time; keep real data gaps; add fact coverage gaps
    compact_data_gaps: list[dict[str, Any]] = []
    for gap in packet["data_gaps"]:
        if isinstance(gap, dict):
            key = gap.get("key", "")
            if key in ("broker_sync", "quote_time"):
                continue
            compact_data_gaps.append(gap)
        else:
            compact_data_gaps.append(gap)

    # 3. Restore fact coverage gaps in compact with grouped keys
    gap_reasons: dict[str, str] = {}
    for summary_item in packet.get("auto_fact_summary", []):
        if summary_item.get("data_status") != "available" and summary_item.get("missing_reason"):
            coverage = summary_item.get("coverage", "")
            symbol = summary_item.get("symbol", "")
            reason = summary_item.get("missing_reason", "")
            if coverage == "etf_facts":
                compact_data_gaps.append({
                    "key": "ETF 份额 / 净值事实",
                    "symbol": symbol,
                    "reason": "Tushare 未配置",
                    "raw_reason": reason,
                })
            elif coverage == "dragon_tiger_and_disclosure_index":
                compact_data_gaps.append({
                    "key": "龙虎榜 / 公告索引",
                    "symbol": symbol,
                    "reason": "Tushare 未配置",
                    "raw_reason": reason,
                })

    # External driver summary (2. groups available/unavailable without duplication; 10. hides unsupported placeholders)
    ext_summary = _compact_external_driver_summary(packet["external_driver_summary"])

    return {
        "meta": {
            "generated_at": _iso_z(packet["meta"]["generated_at"]),
            "portfolio_snapshot_id": packet["meta"]["source_snapshot_id"],
            "portfolio_as_of": _iso_z(packet["meta"]["portfolio_as_of"]),
            "quote_retrieved_at": _iso_z(packet["account_overview"]["current_quote_estimate"]["quote_retrieved_at"]),
            "symbol_name_map": symbol_name_map,
            "symbol_primary_map": symbol_primary_map,
            "analysis_boundaries": _COMPACT_BOUNDARIES,
        },
        "account_facts": account_facts,
        "holdings": compact_holdings,
        "official_theme_exposure": packet["official_theme_exposure"],
        "related_theme_observations": {
            "direction_observations": direction_observations,
            "risk_observations": risk_observations,
            "boundary": "关联方向与风险观察均不得重复计入正式主题资产暴露。",
        },
        "external_driver_summary": ext_summary,
        "data_gaps": compact_data_gaps,
        "ai_analysis_boundary": {
            "external_llm_called": packet["ai_analysis_boundary"]["external_llm_called"],
            "inactive_decision_rules": packet["ai_analysis_boundary"]["inactive_decision_rules"],
            "boundary": "当前上下文仅用于账户事实汇总、主题结构观察与数据缺口识别；不输出买卖或调仓指令。",
        },
        "suggested_questions_for_external_llm": _COMPACT_LLM_QUESTIONS,
    }


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


def _render_portfolio_external_drivers_markdown(summary: list[dict[str, Any]], mode: str = "audit") -> str:
    shared = [item for item in summary if item.get("type") == "shared_driver"]
    mappings = [item for item in summary if item.get("type") == "symbol_mapping"]

    lines = ["## External Driver Summary", ""]

    if shared:
        lines.append("### Shared Drivers")
        lines.append("")
        for item in shared:
            evidence = item.get("evidence") or {}
            payload = evidence.get("payload") or {}
            display_name = _driver_label(item.get("factor_id", "")) if mode == "compact" else item.get("display_name", item.get("factor_id"))
            lines.append(f"- **{display_name}** (`{item.get('factor_id')}`)")
            lines.append(f"  - factor_type: `{item.get('factor_type', 'unknown')}`")
            lines.append(f"  - associated_symbols: {', '.join(item.get('associated_symbols', []))}")
            if payload.get("trade_date"):
                lines.append(f"  - trade_date: {payload['trade_date']}")
            if payload.get("close") is not None:
                currency = payload.get("currency", "")
                quote_unit = payload.get("quote_unit", "")
                if quote_unit:
                    unit_str = f" {quote_unit}" if quote_unit.startswith(currency) else f" {currency}/{quote_unit}"
                else:
                    unit_str = f" {currency}"
                lines.append(f"  - close: {payload['close']}{unit_str}")
            returns = payload.get("returns_pct") or {}
            if returns:
                ret_parts = []
                for k in ["1d", "5d", "20d"]:
                    v = returns.get(k)
                    if v is not None:
                        ret_parts.append(f"{k}: {v:+.4f}%")
                if ret_parts:
                    lines.append(f"  - returns_pct: {' | '.join(ret_parts)}")
            if evidence.get("interpretation_limit"):
                lines.append(f"  - boundary: {evidence['interpretation_limit']}")
            lines.append("")
    else:
        lines.append("- No shared external drivers in current portfolio.")
        lines.append("")

    if mode == "audit" and mappings:
        lines.append("### Per-Symbol Mapping Status")
        lines.append("")
        for item in mappings:
            mapping = item.get("mapping") or {}
            lines.append(
                f"- {item.get('symbol')} → profile_id: `{mapping.get('profile_id', '-')}` | "
                f"status: `{mapping.get('mapping_status', '-')}`"
            )
        lines.append("")

    lines.append("External-driver observations are contextual only and do not establish causal effects or trading conclusions.")
    return "\n".join(lines)


def _localize_driver_status(status: str | None, reason: str | None) -> tuple[str, str]:
    status_map = {
        "available": "可用",
        "unavailable": "暂无数据",
        "not_configured": "未配置",
        "pending_probe": "待验证接入",
        "unsupported_placeholder": "尚未支持",
    }
    localized_status = status_map.get(str(status).lower() if status else "", "暂无数据")
    reason_str = str(reason) if reason else ""
    if "Tushare token is not configured" in reason_str:
        localized_reason = "Tushare 未配置"
    elif "No verified provider symbol" in reason_str:
        localized_reason = "Provider 符号未配置"
    elif "No verified ETF symbol" in reason_str:
        localized_reason = "ETF 符号未配置"
    elif "Yahoo returned HTTP 403" in reason_str:
        localized_reason = "Yahoo Finance 请求失败（HTTP 403）"
    elif "Yahoo" in reason_str and ("unavailable" in reason_str or "failed" in reason_str):
        localized_reason = "Yahoo 数据暂不可用"
    else:
        localized_reason = reason_str
    return localized_status, localized_reason


def render_compact_markdown(context: dict[str, Any]) -> str:
    """Render a compact, AI-friendly account analysis markdown."""
    meta = context["meta"]
    account = context["account_facts"]
    holdings = context["holdings"]
    official_themes = context["official_theme_exposure"]
    related = context["related_theme_observations"]
    ext_summary = context["external_driver_summary"]
    data_gaps = context["data_gaps"]
    questions = context["suggested_questions_for_external_llm"]

    symbol_name_map = meta.get("symbol_name_map") or {}
    symbol_primary_map = meta.get("symbol_primary_map") or {}

    def _names(symbols: list[str]) -> str:
        return ", ".join(symbol_name_map.get(s, s) for s in symbols)

    def _fmt_amount(value: Any) -> str:
        if value is None:
            return "-"
        try:
            return f"{float(value):,.2f}"
        except (TypeError, ValueError):
            return str(value)

    lines = [
        "# Stock-Pilot 账户分析上下文",
        "",
        f"生成时间：{meta['generated_at']}",
        f"持仓快照时间：{meta.get('portfolio_as_of', '-')}",
        f"行情取数时间：{meta.get('quote_retrieved_at', '-')}",
        "",
        "> 注意：系统取数时间不是可验证市场报价时间。",
        "",
        "## 分析边界",
    ]
    for b in meta.get("analysis_boundaries", []):
        lines.append(f"- {b}")
    lines.append("")

    # Account summary table
    lines.extend([
        "## 账户摘要",
        "",
        "| 指标 | 当前估算值 |",
        "|---|---:|",
    ])
    lines.append(f"| 总资产 | {_fmt_amount(account.get('total_assets'))} |")
    lines.append(f"| 持仓市值 | {_fmt_amount(account.get('total_market_value'))} |")
    lines.append(f"| 可用现金 | {_fmt_amount(account.get('cash_available'))} |")
    ir = account.get("invested_ratio_pct")
    lines.append(f"| 当前仓位 | {ir:.2f}% |" if ir is not None else "| 当前仓位 | - |")
    if account.get("total_cost_basis") is not None:
        lines.append(f"| 持仓总成本 | {_fmt_amount(account['total_cost_basis'])} |")
        pnl = account.get("total_unrealized_pnl")
        pnl_pct = account.get("total_unrealized_pnl_pct")
        pnl_str = _fmt_amount(pnl)
        pnl_pct_str = f" ({pnl_pct:+.2f}%)" if pnl_pct is not None else ""
        lines.append(f"| 持仓累计浮动盈亏 | {pnl_str}{pnl_pct_str} |")
    if account.get("repo_amount") is not None:
        lines.append(f"| 逆回购余额 | {_fmt_amount(account['repo_amount'])} |")
    lines.append("")

    # Holdings table
    lines.extend([
        "## 当前持仓",
        "",
        "| 标的 | 持仓数量 | 成本价 | 当前价 | 当前市值 | 浮动盈亏 | 权重 | 主主题 | 关联方向 | 角色 |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|---|",
    ])
    for h in holdings:
        name = h.get("name") or h.get("symbol", "")
        qty = h.get("quantity")
        cost = h.get("avg_cost")
        price = h.get("market_price")
        mv = h.get("market_value")
        pnl = h.get("unrealized_pnl")
        pnl_pct = h.get("unrealized_pnl_pct")
        weight = h.get("portfolio_weight_pct")
        theme = _theme_label(h.get("confirmed_primary_theme") or "UNCLASSIFIED")
        tags = [_theme_label(t) for t in (h.get("confirmed_theme_tags") or []) if t != h.get("confirmed_primary_theme") and t in _DIRECTION_TAGS]
        role = _ROLE_LABEL_MAP.get(str(h.get("confirmed_position_role", "")).lower(), h.get("confirmed_position_role", ""))

        qty_str = f"{qty:,.0f}" if qty is not None else "-"
        cost_str = f"{cost:,.3f}" if cost is not None else "-"
        price_str = f"{price:,.3f}" if price is not None else "-"
        mv_str = _fmt_amount(mv)
        if pnl is not None and pnl_pct is not None:
            pnl_str = f"{pnl:+.2f} ({pnl_pct:+.2f}%)"
        elif pnl is not None:
            pnl_str = f"{pnl:+.2f}"
        else:
            pnl_str = "-"
        weight_str = f"{weight:.2f}%" if weight is not None else "-"
        tags_str = ", ".join(tags) if tags else "-"
        lines.append(f"| {name} | {qty_str} | {cost_str} | {price_str} | {mv_str} | {pnl_str} | {weight_str} | {theme} | {tags_str} | {role} |")
    lines.append("")

    # Official theme exposure
    lines.extend([
        "## 正式主题暴露",
        "",
        "| 正式主题 | 当前市值 | 占总资产比例 | 组成标的 |",
        "|---|---:|---:|---|",
    ])
    for item in official_themes:
        theme = _theme_label(item.get("theme", ""))
        mv = item.get("market_value", 0)
        wp = item.get("weight_pct", 0)
        syms = _names(item.get("symbols", []))
        lines.append(f"| {theme} | {mv:,.2f} | {wp:.2f}% | {syms} |")
    lines.append("")
    lines.append("正式主题为唯一资产归属口径，可加总；关联方向不得再次并入正式主题合计。")
    lines.append("")

    # Direction observations
    directions = related.get("direction_observations", [])
    if directions:
        lines.extend([
            "## 关联方向观察",
            "",
            "| 关联方向 | 当前市值 | 占总资产比例 | 关联标的 | 说明 |",
            "|---|---:|---:|---|---|",
        ])
        for item in directions:
            tag = _theme_label(item.get("theme", ""))
            mv = item.get("market_value", 0)
            wp = item.get("weight_pct", 0)
            syms = _names(item.get("symbols", []))
            note = "关联方向仅作背景观察，不得重复计入正式主题资产暴露"
            if item.get("theme") == "GOLD":
                non_gold_syms = [s for s in item.get("symbols", []) if symbol_primary_map.get(s) != "GOLD"]
                if non_gold_syms:
                    note = f"其中 {_names(non_gold_syms)} 的正式主题仍归属其他类别"
            elif item.get("theme") == "COPPER":
                note = "与铜价背景相关；仅为关联观察，不构成因果或交易结论"
            lines.append(f"| {tag} | {mv:,.2f} | {wp:.2f}% | {syms} | {note} |")
        lines.append("")
        lines.append("关联方向不可与正式主题加总；仅为非加总观察。")
        lines.append("")

    # Risk observations
    risks = related.get("risk_observations", [])
    if risks:
        lines.extend([
            "## 风险观察",
            "",
            "| 观察项 | 当前市值 | 占总资产比例 | 关联标的 | 说明 |",
            "|---|---:|---:|---|---|",
        ])
        for item in risks:
            tag = _theme_label(item.get("theme", ""))
            mv = item.get("market_value", 0)
            wp = item.get("weight_pct", 0)
            syms = _names(item.get("symbols", []))
            note = "描述性观察，不代表阈值触发或调仓建议"
            lines.append(f"| {tag} | {mv:,.2f} | {wp:.2f}% | {syms} | {note} |")
        lines.append("")
        lines.append("风险观察不可与正式主题或关联方向加总。")
        lines.append("")

    # External driver summary
    observations = ext_summary.get("shared_external_driver_observations", [])
    unavailable = ext_summary.get("unavailable_drivers", [])
    lines.extend([
        "## 外部驱动摘要",
        "",
    ])
    if observations:
        lines.extend([
            "### 可用参考数据",
            "",
            "| 驱动 | 当前值 | 1日变化 | 5日变化 | 20日变化 | 关联标的 |",
            "|---|---:|---:|---:|---:|---|",
        ])
        for obs in observations:
            name = _driver_label(obs.get("factor_id", ""))
            close = obs.get("close")
            currency = obs.get("currency", "")
            quote_unit = obs.get("quote_unit", "")
            if quote_unit:
                unit_str = f" {quote_unit}" if quote_unit.startswith(currency) else f" {currency}/{quote_unit}"
            else:
                unit_str = f" {currency}"
            close_str = f"{close:,.4f}{unit_str}" if close is not None else "-"
            ret = obs.get("returns_pct") or {}
            ret_1d = f"{ret.get('1d'):+.2f}%" if ret.get("1d") is not None else "-"
            ret_5d = f"{ret.get('5d'):+.2f}%" if ret.get("5d") is not None else "-"
            ret_20d = f"{ret.get('20d'):+.2f}%" if ret.get("20d") is not None else "-"
            syms = _names(obs.get("associated_symbols", []))
            lines.append(f"| {name} | {close_str} | {ret_1d} | {ret_5d} | {ret_20d} | {syms} |")
        lines.append("")
        lines.append("来源边界：Yahoo Finance / COMEX 数据仅作为延迟参考行情；不是 CME 官方结算数据，不保证实时性，不替代国内对应品种，不构成交易建议。")
        lines.append("")

    if unavailable:
        lines.extend([
            "### 已映射但当前暂无数据的驱动",
            "",
            "| 驱动 | 关联标的 | 状态 | 原因 |",
            "|---|---|---|---|",
        ])
        for drv in unavailable:
            name = _driver_label(drv.get("factor_id", ""))
            syms = _names(drv.get("associated_symbols", []))
            status, reason = _localize_driver_status(drv.get("data_status"), drv.get("reason"))
            lines.append(f"| {name} | {syms} | {status} | {reason} |")
        lines.append("")

    # Data gaps: group by key and merge symbols
    if data_gaps:
        lines.extend([
            "## 数据缺口",
            "",
        ])
        gap_groups: dict[str, dict[str, Any]] = {}
        non_dict_gaps: list[str] = []
        for gap in data_gaps:
            if isinstance(gap, dict):
                key = gap.get("key", "")
                reason = gap.get("reason", "")
                symbol = gap.get("symbol", "")
                if key not in gap_groups:
                    gap_groups[key] = {"reason": reason, "symbols": []}
                if symbol:
                    gap_groups[key]["symbols"].append(symbol)
            else:
                non_dict_gaps.append(str(gap))

        key_label_map = {
            "龙虎榜与公告索引": "龙虎榜 / 公告索引",
            "ETF份额净值事实": "ETF 份额 / 净值事实",
        }
        for key, info in gap_groups.items():
            label = key_label_map.get(key, key)
            reason = info["reason"]
            syms = _names(info["symbols"]) if info["symbols"] else ""
            if syms:
                lines.append(f"- {label}：当前暂无数据；原因：{reason}；涉及标的：{syms}。")
            else:
                lines.append(f"- {label}：当前暂无数据；原因：{reason}。")
        for gap_str in non_dict_gaps:
            lines.append(f"- {gap_str}")
        lines.append("")

    # AI questions
    lines.extend([
        "## 给外部 AI 的任务",
        "",
    ])
    for q in questions:
        lines.append(f"- {q}")
    lines.append("")

    return "\n".join(lines)


def render_packet_markdown(packet: dict[str, Any], mode: str = "audit") -> str:
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
            _render_portfolio_external_drivers_markdown(packet["external_driver_summary"], mode=mode),
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
