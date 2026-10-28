from __future__ import annotations

import json
from datetime import datetime, time as clock_time, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd

from app.analysis.indicators import compute_indicators
from app.analysis_packet.snapshot_builder import build_basic_stock_snapshot
from app.collector.router import collector
from app.core.config import settings
from app.evidence.schemas import AnalysisSnapshot, EvidenceCategory, EvidenceItem
from app.evidence.schemas import AnalysisScope, DataStatus, EvidenceReliability, EvidenceType, LlmUsage
from app.external_drivers import build_external_driver_context
from app.facts.common import to_ts_code
from app.facts.disclosure_service import get_disclosure_facts
from app.facts.dragon_tiger_service import get_dragon_tiger_facts
from app.facts.etf_service import SUPPORTED_ETFS, get_etf_facts
from app.overseas_tech_chain import build_overseas_tech_chain
from app.portfolio.dashboard import build_market_event_radar
from app.theme_evidence import build_theme_evidence_radar, load_theme_evidence_registry
from app.services.etf_share_service import ETF_SHARE_LIMIT, etf_share_service
from app.portfolio import portfolio_service
from app.market_breadth import get_market_breadth


PACKET_VERSION = "analysis_packet.v1"
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

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
    "请先识别当前账户的具体机会点，并结合关联方向与风险观察说明：哪些已有持仓或持仓量为 0 的观察标的最值得优先跟踪，对应证据来自持仓角色、账户权重、走势证据、外部驱动或数据缺口中的哪一项。",
    "请再识别当前账户的具体风险点：集中度、趋势转弱、事实缺失、持仓计划不清、账户数据陈旧、外部驱动敏感性等，都必须绑定到具体标的或账户指标。",
    "请对重要标的分别给出短期、中期、长期策略观察；每个周期都要包含需要观察的触发条件、使判断失效的信号，以及哪些新增信息会改变当前看法。",
    "请区分已有持仓与持仓量为 0 的观察标的。观察标的只讨论进入观察池后的跟踪重点、入场准备度和需要等待的证据，不计入当前仓位暴露、成本或盈亏贡献。",
    "避免输出“控制风险、注意波动、关注基本面”这类笼统结论；每条结论都应点名标的或账户指标，并引用本证据包中的相关字段。",
    "不要输出无条件的买入、卖出、加仓、减仓或调仓指令；请使用条件化策略语言，例如继续观察、等待确认、降低置信度、需要补充证据、若条件成立再评估；do not output buy, sell, or position-adjustment instructions。",
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


def _display_shanghai_time(value: datetime | str | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return "-"
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            value = datetime.fromisoformat(normalized)
        except ValueError:
            return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(SHANGHAI_TZ).isoformat(timespec="seconds")


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
    try:
        context = build_external_driver_context(
            symbol,
            primary_theme=(holding or {}).get("primary_theme"),
            directions=(holding or {}).get("directions"),
        )
    except TypeError:
        context = build_external_driver_context(
            symbol,
            primary_theme=(holding or {}).get("primary_theme"),
        )
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


def _portfolio_etf_share_observations(positions: list[dict[str, Any]]) -> dict[str, Any]:
    codes: list[str] = []
    names: dict[str, str] = {}
    for position in positions:
        symbol = str(position.get("symbol") or "")
        code = symbol.split(".", 1)[0].strip().zfill(6)
        if not code.startswith(("15", "16", "51", "56", "58")):
            continue
        codes.append(code)
        if position.get("name"):
            names[code] = str(position.get("name"))

    observations = etf_share_service.observations_for_codes(sorted(set(codes)), names=names)
    available = [item for item in observations if item.get("data_status") == "available"]
    unavailable = [item for item in observations if item.get("data_status") != "available"]
    return {
        "observations": available,
        "unavailable": unavailable,
        "source": "akshare",
        "boundary": ETF_SHARE_LIMIT,
    }


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


def build_portfolio_packet(
    user_question: str | None = None,
    persist: bool = True,
    state: PortfolioState | None = None,
) -> dict[str, Any]:
    state = state or portfolio_service.get_state()
    snapshot = portfolio_service.build_portfolio_snapshot(user_question=user_question, persist=persist, state=state)
    generated_at = state.metrics.valuation_generated_at or _now()
    positions = []
    weights = {item.get("symbol"): item for item in state.metrics.position_weights}
    for position in state.snapshot.positions:
        data = position.model_dump(mode="json")
        data["portfolio_weight_pct"] = (weights.get(position.symbol) or {}).get("weight_pct")
        data["weight_pct"] = data["portfolio_weight_pct"]
        data["quote_retrieved_at"] = (position.system_quote_retrieved_at or generated_at).isoformat()
        data["quote_market_time"] = None
        data["quote_time_status"] = "unavailable"
        data["quote_time_boundary"] = QUOTE_TIME_BOUNDARY
        data["confirmed_primary_theme"] = data.get("directions", [])[0] if data.get("directions") else data.get("primary_theme")
        data["confirmed_theme_tags"] = data.get("theme_tags", [])
        data["confirmed_directions"] = data.get("directions", [])
        data["confirmed_risk_flags"] = data.get("risk_flags", [])
        data["confirmed_position_role"] = data.get("position_role")
        positions.append(data)
    holding_trend_evidence = _build_holding_trend_evidence(positions, generated_at)
    market_breadth = get_market_breadth()
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
        if not item.get("confirmed_directions") or str(item.get("confirmed_directions", [])[0] if item.get("confirmed_directions") else "").upper() == "UNCLASSIFIED"
    ]
    data_gaps = [
        *state.metrics.missing_data,
        *[
            {
                "key": "holding_semantics",
                "symbol": item.get("symbol"),
                "reason": "Holding directions are not confirmed; account direction analysis is incomplete.",
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
        *[
            {
                "key": "holding_trend_evidence",
                "symbol": item.get("symbol"),
                "reason": item.get("reason") or "Holding daily-K trend evidence is unavailable.",
            }
            for item in holding_trend_evidence
            if item.get("data_status") != "available"
        ],
    ]
    etf_share_observations = _portfolio_etf_share_observations(positions)
    event_weights = {
        str(item.get("symbol", "")).split(".", 1)[0].strip().zfill(6): float(item.get("weight_pct") or 0)
        for item in state.metrics.position_weights
        if item.get("symbol")
    }
    market_event_radar = build_market_event_radar(state, event_weights)
    theme_evidence_radar = build_theme_evidence_radar(
        state,
        load_theme_evidence_registry(),
        event_weights,
        market_event_radar=market_event_radar,
    )
    overseas_tech_chain = build_overseas_tech_chain(state)
    missing_data = _clean_text([
        *data_gaps,
        *[
            {
                "key": "ETF 份额 / 净值事实",
                "symbol": item.get("fund_code"),
                "reason": item.get("reason") or "AKShare 接口失败或未匹配到基金代码",
                "source": "akshare",
            }
            for item in etf_share_observations.get("unavailable", [])
        ],
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
            "account_actual_total_cost": state.metrics.account_actual_total_cost,
            "account_actual_total_cost_source": state.metrics.account_actual_total_cost_source,
            "account_actual_total_cost_confirmed_at": state.metrics.account_actual_total_cost_confirmed_at.isoformat() if state.metrics.account_actual_total_cost_confirmed_at else None,
            "account_total_pnl": state.metrics.account_total_pnl,
            "account_total_pnl_pct": state.metrics.account_total_pnl_pct,
            "account_total_pnl_status": state.metrics.account_total_pnl_status,
            "current_holding_cost_basis": state.metrics.current_holding_cost_basis,
            "current_holding_unrealized_pnl": state.metrics.current_holding_unrealized_pnl,
            "current_holding_unrealized_pnl_pct": state.metrics.current_holding_unrealized_pnl_pct,
            "current_holding_unrealized_pnl_status": state.metrics.current_holding_unrealized_pnl_status,
            "repo_amount": state.metrics.repo_amount,
            "active_position_count": state.metrics.active_position_count,
            "watchlist_position_count": state.metrics.watchlist_position_count,
            "watchlist_symbols": state.metrics.watchlist_symbols,
            "valuation_basis": "current_quote_estimate",
            "valuation_snapshot_id": state.metrics.valuation_snapshot_id,
            "valuation_generated_at": state.metrics.valuation_generated_at.isoformat() if state.metrics.valuation_generated_at else None,
            "quote_retrieved_at": state.metrics.quote_retrieved_at.isoformat() if state.metrics.quote_retrieved_at else generated_at.isoformat(),
            "valuation_consistency_status": state.metrics.valuation_consistency_status,
            "valuation_consistency_checks": state.metrics.valuation_consistency_checks,
            "valuation_consistency_errors": state.metrics.valuation_consistency_errors,
            "valuation_consistency_diffs": state.metrics.valuation_consistency_diffs,
            "snapshot_valuation": {
                "snapshot_as_of": state.snapshot.snapshot_time.isoformat(),
                "snapshot_total_assets": state.snapshot.total_assets,
                "snapshot_cash_available": state.snapshot.cash_available,
                "snapshot_repo_amount": state.snapshot.repo_amount,
                "boundary": "Snapshot values reflect the locally saved account record at snapshot time.",
            },
            "current_quote_estimate": {
                "quote_retrieved_at": state.metrics.quote_retrieved_at.isoformat() if state.metrics.quote_retrieved_at else generated_at.isoformat(),
                "valuation_snapshot_id": state.metrics.valuation_snapshot_id,
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
        "holding_trend_evidence": holding_trend_evidence,
        "market_data_time_semantics": {
            "daily_k": "Trend, returns, moving averages and the latest_daily_k_close always use the same latest landed local daily-K date.",
            "post_close_quote": "A post-close quote is emitted separately only when it is newer than local daily K. It is a source snapshot pending daily-K landing and must not be mixed into trend calculations.",
            "volume_ratio": "Daily-K volume ratios use completed daily bars. Post-close source volume ratio is labelled separately, alongside session volume divided by the prior five completed trading-day average.",
        },
        "market_breadth": market_breadth,
        "primary_theme_exposure": [item.model_dump(mode="json") for item in state.metrics.primary_theme_exposures],
        "primary_direction_grouping": [item.model_dump(mode="json") for item in state.metrics.primary_theme_exposures],
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
        "etf_share_observations": etf_share_observations,
        "market_event_radar": market_event_radar,
        "theme_evidence_radar": theme_evidence_radar,
        "overseas_tech_chain": overseas_tech_chain,
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
    "AI": "AI",
    "CXO": "CXO",
    "INNOVATION_DRUG": "创新药",
    "MEDICAL_ETF": "医药ETF",
    "INSURANCE": "保险",
    "MOLYBDENUM": "钼",
    "METAL_RESOURCE": "金属资源",
    "EV_AUTOMOTIVE": "新能源车 / 整车",
    "GOLD": "黄金",
    "COPPER": "铜",
    "TUNGSTEN": "钨",
    "PCB": "PCB",
    "SEMICONDUCTOR_EQUIPMENT": "半导体设备",
    "HIGH_VOLATILITY": "高波动",
    "OTHER": "其他",
    "UNCLASSIFIED": "待分类",
}

_DIRECTION_TAGS = {"AI", "GOLD", "COPPER", "TUNGSTEN", "PCB", "SEMICONDUCTOR_EQUIPMENT", "CXO", "INNOVATION_DRUG", "MEDICAL_ETF", "INSURANCE", "MOLYBDENUM", "METAL_RESOURCE", "EV_AUTOMOTIVE", "OTHER"}
_RISK_TAGS = {"HIGH_VOLATILITY"}
_EXCLUDED_FROM_COMPACT = {"COMPOSITE_EXPOSURE", "AI_PCB", "AI_THEME_ETF", "METAL_RESOURCE", "CASH_EQUIVALENT"}

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
    "short_term": "短线",
    "unclassified": "待分类",
}

_COMPACT_LLM_QUESTIONS = [
    "请总结当前账户的关联方向与风险观察，并明确主要方向归组按首个关联方向唯一可加总。",
    "请结合持仓近期走势证据，区分哪些持仓仅有结构性观察基础，哪些持仓出现转强、转弱、利润保护或修复观察信号；不得输出交易指令。",
    "请识别全部关联方向中的交叉背景，例如同时关联铜与黄金的持仓；全部方向观察不可重复加总。",
    "请单独整理风险观察，不将高波动等风险标记混同为产业或资源方向。",
    "请识别共享外部驱动背景的持仓，并说明这些关联仅为背景观察，不构成因果结论。",
    "请列出当前缺少的账户记录、持仓计划或外部事实，并按“重点跟踪 / 需补信息 / 暂不足判断”整理观察。",
    "不输出买入、卖出、加仓、减仓或调仓指令。",
]

_COMPACT_BOUNDARIES = [
    "隐私边界：本上下文由本地生成，不会自动发送给外部 AI；仅在用户主动复制、导出或提交时外传。",
    "行情时间边界：当前 A 股行情源不提供可验证市场报价时间；当前估算总资产与持仓市值均基于系统本次冻结取价结果。",
    "账户盈亏边界：账户总盈亏基于用户手动维护的账户实际总成本与当前估算总资产计算；当前持仓浮动盈亏仅反映尚持有证券的浮动结果，两者口径不同。",
    "走势证据边界：持仓近期走势证据来自本地日K与MA5/10/20/30等派生指标，仅作弱信号观察，不构成买卖、加仓、减仓或止盈止损指令。",
    "方向口径边界：每只持仓按首个关联方向进行唯一归组；全部关联方向仅用于非加总观察，不得重复统计为资产暴露。",
    "风险观察边界：高波动等风险标记独立于关联方向，仅作描述性观察，不构成调仓或交易建议。",
    "外部驱动边界：COMEX、汇率、ETF 或其他外部驱动仅作为关联背景，不构成因果结论、估值结论或买卖建议。",
]

_STRATEGY_LLM_QUESTIONS = [
    "请先识别当前账户的具体机会点，并结合关联方向与风险观察说明：哪些已有持仓或持仓量为 0 的观察标的最值得优先跟踪，对应证据来自持仓角色、账户权重、走势证据、外部驱动或数据缺口中的哪一项。",
    "请再识别当前账户的具体风险点：集中度、趋势转弱、事实缺失、持仓计划不清、账户数据陈旧、外部驱动敏感性等，都必须绑定到具体标的或账户指标。",
    "请对重要标的分别给出短期、中期、长期策略观察；每个周期都要包含需要观察的触发条件、使判断失效的信号，以及哪些新增信息会改变当前看法。",
    "请区分已有持仓与持仓量为 0 的观察标的。观察标的只讨论进入观察池后的跟踪重点、入场准备度和需要等待的证据，不计入当前仓位暴露、成本或盈亏贡献。",
    "避免输出“控制风险、注意波动、关注基本面”这类笼统结论；每条结论都应点名标的或账户指标，并引用本证据包中的相关字段。",
    "不要输出无条件的买入、卖出、加仓、减仓或调仓指令；请使用条件化策略语言，例如继续观察、等待确认、降低置信度、需要补充证据、若条件成立再评估；do not output buy, sell, or position-adjustment instructions。",
]


def _theme_label(key: str) -> str:
    return _THEME_LABEL_MAP.get(key, key)


def _is_direction_tag(tag: str | None) -> bool:
    return bool(tag) and tag not in _RISK_TAGS and tag not in _EXCLUDED_FROM_COMPACT


def _driver_label(key: str) -> str:
    return _DRIVER_LABEL_MAP.get(key, key)


def _history_col(df: pd.DataFrame, *names: str) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    return None


def _pct(value: float | None) -> float | None:
    return round(float(value), 2) if value is not None else None


def _interval_return(closes: pd.Series, days: int) -> float | None:
    if len(closes) <= days:
        return None
    base = closes.iloc[-days - 1]
    if not base:
        return None
    return round((closes.iloc[-1] / base - 1) * 100, 2)


def _price_vs_ma(price: float | None, ma: float | None) -> float | None:
    if price is None or ma in (None, 0):
        return None
    return round((float(price) / float(ma) - 1) * 100, 2)


def _trend_state(price: float | None, indicators: dict[str, Any]) -> str:
    ma5 = indicators.get("ma5")
    ma10 = indicators.get("ma10")
    ma20 = indicators.get("ma20")
    ma30 = indicators.get("ma30")
    macd = indicators.get("macd")
    if not all(v is not None for v in [price, ma5, ma10, ma20, ma30]):
        return "数据不足"
    if price > ma5 > ma10 > ma20 > ma30:
        return "短期强势排列"
    if price > ma5 and ma5 >= ma10 >= ma20:
        return "偏强观察"
    if price < ma5 < ma10 < ma20:
        return "短期转弱"
    if price < ma20 and macd is not None and macd < 0:
        return "中期均线下方"
    if price >= ma20:
        return "震荡偏稳"
    return "震荡偏弱"


def _strategy_observation(position: dict[str, Any], price: float | None, indicators: dict[str, Any], trend_state: str) -> str:
    pnl = position.get("unrealized_pnl")
    ma5 = indicators.get("ma5")
    ma20 = indicators.get("ma20")
    rsi = indicators.get("rsi14")
    notes: list[str] = []
    if pnl is not None and pnl > 0:
        if price is not None and ma5 is not None and price < ma5:
            notes.append("盈利持仓已低于MA5，适合进入利润保护观察")
        else:
            notes.append("盈利持仓仍保持短线观察基础")
    elif pnl is not None and pnl < 0:
        if price is not None and ma20 is not None and price < ma20:
            notes.append("亏损持仓仍在MA20下方，修复证据不足")
        else:
            notes.append("亏损持仓出现均线修复观察点")
    if rsi is not None and rsi >= 70:
        notes.append("RSI偏高，后续关注冲高回落风险")
    elif rsi is not None and rsi <= 30:
        notes.append("RSI偏低，后续关注技术修复是否成立")
    notes.append(f"走势状态：{trend_state}")
    return "；".join(notes)


def _shanghai_quote_time(value: Any, fallback: datetime) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        fallback = fallback.replace(tzinfo=timezone.utc) if fallback.tzinfo is None else fallback
        return fallback.astimezone(SHANGHAI_TZ).isoformat()
    if parsed.tzinfo is None:
        parsed = parsed.tz_localize(SHANGHAI_TZ)
    else:
        parsed = parsed.tz_convert(SHANGHAI_TZ)
    return parsed.isoformat()


def _realtime_session_snapshot(
    symbol: str,
    generated_at: datetime,
    *,
    daily_k_as_of: Any = None,
    prior_volume_ma_5: float | None = None,
) -> dict[str, Any]:
    """Return an independently usable real-time snapshot, even without local daily K."""
    quote = collector.get_quote(symbol)
    quote_time = _shanghai_quote_time(quote.get("quote_market_time"), generated_at)
    parsed_quote_time = pd.to_datetime(quote_time, errors="coerce")
    parsed_daily_date = pd.to_datetime(daily_k_as_of, errors="coerce")
    if pd.isna(parsed_daily_date):
        status = "realtime_snapshot_no_daily_k"
    elif not pd.isna(parsed_quote_time) and parsed_quote_time.date() > parsed_daily_date.date():
        status = "post_close_quote_pending_daily_k" if parsed_quote_time.time() >= clock_time(15, 30) else "intraday_quote"
    else:
        status = "realtime_quote_snapshot"
    volume = quote.get("volume")
    return {
        "market_session_as_of": quote_time,
        "market_session_status": status,
        "session_open": quote.get("open"),
        "session_high": quote.get("high"),
        "session_low": quote.get("low"),
        "session_close": quote.get("price"),
        "session_pct_chg": quote.get("change_pct"),
        "session_volume": volume,
        "session_amount": quote.get("amount"),
        "session_turnover_rate": quote.get("turnover_rate"),
        "session_volume_ratio": quote.get("volume_ratio"),
        "session_volume_vs_prev_5d_ratio": (
            round(float(volume) / prior_volume_ma_5, 4)
            if volume is not None and prior_volume_ma_5
            else None
        ),
        "session_source": quote.get("provider"),
    }


def _build_holding_trend_evidence(positions: list[dict[str, Any]], generated_at: datetime) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for position in positions:
        symbol = position.get("symbol")
        if not symbol:
            continue
        try:
            history = collector.get_history(symbol, 160)
            if history is None or history.empty:
                raise ValueError("local daily K history is empty")
            close_col = _history_col(history, "close", "收盘")
            date_col = _history_col(history, "date", "日期")
            pct_col = _history_col(history, "pctChg", "pct_chg", "涨跌幅")
            if not close_col:
                raise ValueError("daily K close column missing")
            indicators, _ma_series = compute_indicators(history)
            closes = pd.to_numeric(history[close_col], errors="coerce").dropna()
            if closes.empty:
                raise ValueError("daily K close values are empty")
            latest = history.iloc[-1]
            latest_close = round(float(closes.iloc[-1]), 4)
            # Trend indicators must use the same completed daily-K close as their
            # date label. A newer realtime quote is emitted separately below.
            current_price = latest_close
            trend_state = _trend_state(current_price, indicators)
            latest_pct = None
            if pct_col:
                pct_value = pd.to_numeric(pd.Series([latest[pct_col]]), errors="coerce").iloc[0]
                latest_pct = None if pd.isna(pct_value) else round(float(pct_value), 2)
            def latest_number(column: str | None) -> float | None:
                if not column:
                    return None
                value = pd.to_numeric(pd.Series([latest[column]]), errors="coerce").iloc[0]
                return None if pd.isna(value) else round(float(value), 4)

            open_col = _history_col(history, "open")
            high_col = _history_col(history, "high")
            low_col = _history_col(history, "low")
            volume_col = _history_col(history, "volume")
            amount_col = _history_col(history, "amount")
            turn_col = _history_col(history, "turn", "turnover")
            volume_values = pd.to_numeric(history[volume_col], errors="coerce").dropna() if volume_col else pd.Series(dtype=float)
            amount_values = pd.to_numeric(history[amount_col], errors="coerce").dropna() if amount_col else pd.Series(dtype=float)

            def rolling_mean(values: pd.Series, window: int) -> float | None:
                return round(float(values.tail(window).mean()), 4) if len(values) >= window else None

            volume_ma = {window: rolling_mean(volume_values, window) for window in (5, 10, 20)}
            amount_ma = {window: rolling_mean(amount_values, window) for window in (5, 10, 20)}
            prior_volume_ma = {
                window: rolling_mean(volume_values.iloc[:-1], window)
                for window in (5, 10, 20)
            }
            latest_volume = latest_number(volume_col)
            session_quote: dict[str, Any] = {}
            try:
                session_quote = _realtime_session_snapshot(
                    symbol,
                    generated_at,
                    daily_k_as_of=latest[date_col] if date_col else None,
                    prior_volume_ma_5=prior_volume_ma[5],
                )
            except Exception:
                pass
            evidence.append({
                "symbol": symbol,
                "name": position.get("name") or symbol,
                "data_status": "available",
                "source": "local_daily_k_and_compute_indicators",
                "source_endpoint": "collector.get_history + compute_indicators",
                "daily_k_as_of": str(latest[date_col])[:10] if date_col else None,
                "daily_k_close_label": "latest_landed_daily_k_close",
                "generated_at": generated_at.isoformat(),
                "current_price": round(float(current_price), 4) if current_price is not None else None,
                "latest_daily_k_close": latest_close,
                "latest_close": latest_close,
                "latest_pct_chg": latest_pct,
                "open": latest_number(open_col),
                "high": latest_number(high_col),
                "low": latest_number(low_col),
                "volume": latest_volume,
                "amount": latest_number(amount_col),
                "turnover_rate": latest_number(turn_col),
                "volume_ma_5": volume_ma[5],
                "volume_ma_10": volume_ma[10],
                "volume_ma_20": volume_ma[20],
                "amount_ma_5": amount_ma[5],
                "amount_ma_10": amount_ma[10],
                "amount_ma_20": amount_ma[20],
                "volume_vs_ma_5_ratio": round(latest_volume / volume_ma[5], 4) if latest_volume is not None and volume_ma[5] else None,
                "volume_vs_ma_10_ratio": round(latest_volume / volume_ma[10], 4) if latest_volume is not None and volume_ma[10] else None,
                "volume_vs_ma_20_ratio": round(latest_volume / volume_ma[20], 4) if latest_volume is not None and volume_ma[20] else None,
                "volume_ma_5_to_20_ratio": round(volume_ma[5] / volume_ma[20], 4) if volume_ma[5] and volume_ma[20] else None,
                "volume_prev_5_avg": prior_volume_ma[5],
                "volume_prev_10_avg": prior_volume_ma[10],
                "volume_prev_20_avg": prior_volume_ma[20],
                **session_quote,
                "return_5d_pct": _interval_return(closes, 5),
                "return_10d_pct": _interval_return(closes, 10),
                "return_20d_pct": _interval_return(closes, 20),
                "return_60d_pct": _interval_return(closes, 60),
                "ma5": indicators.get("ma5"),
                "ma10": indicators.get("ma10"),
                "ma20": indicators.get("ma20"),
                "ma30": indicators.get("ma30"),
                "ma60": indicators.get("ma60"),
                "rsi14": indicators.get("rsi14"),
                "macd": indicators.get("macd"),
                "price_vs_ma5_pct": _price_vs_ma(current_price, indicators.get("ma5")),
                "price_vs_ma20_pct": _price_vs_ma(current_price, indicators.get("ma20")),
                "trend_state": trend_state,
                "strategy_observation": _strategy_observation(position, current_price, indicators, trend_state),
                "interpretation_limit": "近期走势证据来自本地日K和派生技术指标，仅作弱信号观察，不构成买卖、加仓、减仓或止盈止损指令。",
            })
        except Exception as exc:
            session_quote: dict[str, Any] = {}
            try:
                session_quote = _realtime_session_snapshot(symbol, generated_at)
            except Exception:
                pass
            evidence.append({
                "symbol": symbol,
                "name": position.get("name") or symbol,
                "data_status": "daily_k_unavailable_realtime_available" if session_quote else "unavailable",
                "reason": str(exc),
                "generated_at": generated_at.isoformat(),
                **session_quote,
                "interpretation_limit": "近期走势证据不可用；不得据此补造趋势结论。",
            })
    return evidence


def build_account_analysis_context(
    mode: str = "compact",
    snapshot_status_note: str | None = None,
    state: PortfolioState | None = None,
) -> dict[str, Any]:
    result = build_portfolio_packet(user_question=None, persist=False, state=state)
    packet = result["packet"]
    account_overview = packet["account_overview"]

    if mode == "audit":
        return {
            "meta": {
                "generated_at": _iso_z(packet["meta"]["generated_at"]),
                "portfolio_snapshot_id": packet["meta"]["source_snapshot_id"],
                "portfolio_as_of": _iso_z(packet["meta"]["portfolio_as_of"]),
                "valuation_snapshot_id": account_overview.get("valuation_snapshot_id"),
                "valuation_generated_at": _iso_z(account_overview.get("valuation_generated_at")),
                "quote_retrieved_at": _iso_z(account_overview.get("quote_retrieved_at")),
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
                    "position_status": item.get("position_status"),
                    "valuation_scope": item.get("valuation_scope"),
                    "confirmed_primary_theme": item.get("confirmed_primary_theme"),
                    "confirmed_theme_tags": item.get("confirmed_theme_tags", []),
                    "confirmed_directions": item.get("confirmed_directions", []),
                    "confirmed_risk_flags": item.get("confirmed_risk_flags", []),
                    "confirmed_position_role": item.get("confirmed_position_role"),
                    "external_driver_profile_id": None,
                    "data_status": item.get("data_status"),
                }
                for item in packet["holdings"]
            ],
            "holding_trend_evidence": packet.get("holding_trend_evidence", []),
            "etf_share_observations": packet.get("etf_share_observations", {}),
            "market_event_radar": packet.get("market_event_radar", {}),
            "theme_evidence_radar": packet.get("theme_evidence_radar", {}),
            "overseas_tech_chain": packet.get("overseas_tech_chain", {}),
            "primary_direction_grouping": packet.get("primary_direction_grouping", packet.get("primary_theme_exposure", [])),
            "all_direction_observations": packet["related_theme_observations"],
            "risk_observations": packet["related_risk_observations"],
            "official_theme_exposure": packet["official_theme_exposure"],
            "related_theme_observations": packet["related_theme_observations"],
            "external_driver_summary": _compact_external_driver_summary(packet["external_driver_summary"]),
            "data_gaps": packet["data_gaps"],
            "ai_analysis_boundary": packet["ai_analysis_boundary"],
            "suggested_questions_for_external_llm": packet["suggested_questions_for_external_llm"],
        }

    # Compact mode
    has_repo = bool(account_overview.get("repo_amount") and account_overview.get("repo_amount") > 0)

    account_facts: dict[str, Any] = {
        "total_assets": account_overview.get("total_assets"),
        "total_market_value": account_overview.get("total_market_value"),
        "cash_available": account_overview.get("cash_available"),
        "invested_ratio_pct": account_overview.get("invested_ratio_pct"),
        "cash_ratio_pct": account_overview.get("cash_ratio_pct"),
        "active_position_count": account_overview.get("active_position_count"),
        "watchlist_position_count": account_overview.get("watchlist_position_count"),
        "watchlist_symbols": account_overview.get("watchlist_symbols", []),
        "account_actual_total_cost": account_overview.get("account_actual_total_cost"),
        "account_actual_total_cost_source": account_overview.get("account_actual_total_cost_source"),
        "account_actual_total_cost_confirmed_at": account_overview.get("account_actual_total_cost_confirmed_at"),
        "account_total_pnl": account_overview.get("account_total_pnl"),
        "account_total_pnl_pct": account_overview.get("account_total_pnl_pct"),
        "account_total_pnl_status": account_overview.get("account_total_pnl_status"),
        "current_holding_cost_basis": account_overview.get("current_holding_cost_basis"),
        "current_holding_unrealized_pnl": account_overview.get("current_holding_unrealized_pnl"),
        "current_holding_unrealized_pnl_pct": account_overview.get("current_holding_unrealized_pnl_pct"),
        "current_holding_unrealized_pnl_status": account_overview.get("current_holding_unrealized_pnl_status"),
        "total_cost_basis": account_overview.get("current_holding_cost_basis"),
        "total_unrealized_pnl": account_overview.get("current_holding_unrealized_pnl"),
        "total_unrealized_pnl_pct": account_overview.get("current_holding_unrealized_pnl_pct"),
        "total_unrealized_pnl_status": account_overview.get("current_holding_unrealized_pnl_status"),
    }
    if has_repo:
        account_facts["repo_amount"] = account_overview.get("repo_amount")
        account_facts["repo_ratio_pct"] = account_overview.get("repo_ratio_pct")

    # Build name/primary maps and compact holdings
    symbol_name_map: dict[str, str] = {}
    symbol_primary_map: dict[str, str] = {}
    compact_holdings = []
    for item in packet["holdings"]:
        symbol = item.get("symbol", "")
        name = item.get("name") or symbol
        directions = item.get("confirmed_directions", []) or ["UNCLASSIFIED"]
        symbol_name_map[symbol] = name
        symbol_primary_map[symbol] = directions[0] if directions else ""
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
            "position_status": item.get("position_status"),
            "valuation_scope": item.get("valuation_scope"),
            "confirmed_primary_theme": item.get("confirmed_primary_theme"),
            "confirmed_theme_tags": item.get("confirmed_theme_tags", []),
            "confirmed_directions": directions,
            "confirmed_risk_flags": item.get("confirmed_risk_flags", []),
            "confirmed_position_role": item.get("confirmed_position_role"),
        })

    # Build primary direction grouping (additive, by directions[0])
    compact_trend_evidence = [
        {
            "symbol": item.get("symbol"),
            "name": item.get("name"),
            "data_status": item.get("data_status"),
            "daily_k_as_of": item.get("daily_k_as_of"),
            "daily_k_close_label": item.get("daily_k_close_label"),
            "current_price": item.get("current_price"),
            "latest_daily_k_close": item.get("latest_daily_k_close"),
            "latest_close": item.get("latest_close"),
            "latest_pct_chg": item.get("latest_pct_chg"),
            "open": item.get("open"),
            "high": item.get("high"),
            "low": item.get("low"),
            "volume": item.get("volume"),
            "amount": item.get("amount"),
            "turnover_rate": item.get("turnover_rate"),
            "volume_ma_5": item.get("volume_ma_5"),
            "volume_ma_10": item.get("volume_ma_10"),
            "volume_ma_20": item.get("volume_ma_20"),
            "volume_prev_5_avg": item.get("volume_prev_5_avg"),
            "amount_ma_5": item.get("amount_ma_5"),
            "amount_ma_10": item.get("amount_ma_10"),
            "amount_ma_20": item.get("amount_ma_20"),
            "volume_vs_ma_5_ratio": item.get("volume_vs_ma_5_ratio"),
            "volume_vs_ma_10_ratio": item.get("volume_vs_ma_10_ratio"),
            "volume_vs_ma_20_ratio": item.get("volume_vs_ma_20_ratio"),
            "volume_ma_5_to_20_ratio": item.get("volume_ma_5_to_20_ratio"),
            "volume_prev_5_avg": item.get("volume_prev_5_avg"),
            "volume_prev_10_avg": item.get("volume_prev_10_avg"),
            "volume_prev_20_avg": item.get("volume_prev_20_avg"),
            "market_session_as_of": item.get("market_session_as_of"),
            "market_session_status": item.get("market_session_status"),
            "session_open": item.get("session_open"),
            "session_high": item.get("session_high"),
            "session_low": item.get("session_low"),
            "session_close": item.get("session_close"),
            "session_pct_chg": item.get("session_pct_chg"),
            "session_volume": item.get("session_volume"),
            "session_amount": item.get("session_amount"),
            "session_turnover_rate": item.get("session_turnover_rate"),
            "session_volume_ratio": item.get("session_volume_ratio"),
            "session_volume_vs_prev_5d_ratio": item.get("session_volume_vs_prev_5d_ratio"),
            "session_source": item.get("session_source"),
            "return_5d_pct": item.get("return_5d_pct"),
            "return_10d_pct": item.get("return_10d_pct"),
            "return_20d_pct": item.get("return_20d_pct"),
            "return_60d_pct": item.get("return_60d_pct"),
            "ma5": item.get("ma5"),
            "ma10": item.get("ma10"),
            "ma20": item.get("ma20"),
            "ma30": item.get("ma30"),
            "ma60": item.get("ma60"),
            "rsi14": item.get("rsi14"),
            "macd": item.get("macd"),
            "price_vs_ma5_pct": item.get("price_vs_ma5_pct"),
            "price_vs_ma20_pct": item.get("price_vs_ma20_pct"),
            "trend_state": item.get("trend_state"),
            "strategy_observation": item.get("strategy_observation"),
            "interpretation_limit": item.get("interpretation_limit"),
            "reason": item.get("reason"),
        }
        for item in packet.get("holding_trend_evidence", [])
    ]
    primary_direction_aggregates: dict[str, dict[str, Any]] = {}
    all_direction_aggregates: dict[str, dict[str, Any]] = {}
    risk_flag_aggregates: dict[str, dict[str, Any]] = {}
    for item in packet["holdings"]:
        symbol = item.get("symbol", "")
        mv = item.get("market_value") or 0
        directions = item.get("confirmed_directions", []) or ["UNCLASSIFIED"]
        risk_flags = item.get("confirmed_risk_flags", [])
        # Primary grouping by directions[0]
        if directions:
            primary_dir = directions[0]
            if primary_dir and primary_dir not in _EXCLUDED_FROM_COMPACT:
                entry = primary_direction_aggregates.setdefault(primary_dir, {"market_value": 0.0, "symbols": []})
                entry["market_value"] += mv
                entry["symbols"].append(symbol)
        # All directions (non-additive observation)
        for d in directions:
            if d and d not in _EXCLUDED_FROM_COMPACT:
                entry = all_direction_aggregates.setdefault(d, {"market_value": 0.0, "symbols": []})
                entry["market_value"] += mv
                entry["symbols"].append(symbol)
        # Risk flags
        for flag in risk_flags:
            if flag and flag not in _EXCLUDED_FROM_COMPACT:
                entry = risk_flag_aggregates.setdefault(flag, {"market_value": 0.0, "symbols": []})
                entry["market_value"] += mv
                entry["symbols"].append(symbol)

    total_assets_for_wp = account_overview.get("total_assets") or 1
    primary_direction_grouping = []
    for direction, data in sorted(primary_direction_aggregates.items(), key=lambda x: x[1]["market_value"], reverse=True):
        mv = data["market_value"]
        wp = mv / total_assets_for_wp * 100
        primary_direction_grouping.append({
            "direction": direction,
            "market_value": round(mv, 2),
            "weight_pct": round(wp, 2),
            "symbols": sorted(set(data["symbols"])),
        })

    all_direction_observations = []
    for direction, data in sorted(all_direction_aggregates.items(), key=lambda x: x[1]["market_value"], reverse=True):
        mv = data["market_value"]
        wp = mv / total_assets_for_wp * 100
        all_direction_observations.append({
            "theme": direction,
            "direction": direction,
            "market_value": round(mv, 2),
            "weight_pct": round(wp, 2),
            "symbols": sorted(set(data["symbols"])),
        })

    risk_observations = []
    for flag, data in sorted(risk_flag_aggregates.items(), key=lambda x: x[1]["market_value"], reverse=True):
        mv = data["market_value"]
        wp = mv / total_assets_for_wp * 100
        risk_observations.append({
            "theme": flag,
            "risk_flag": flag,
            "market_value": round(mv, 2),
            "weight_pct": round(wp, 2),
            "symbols": sorted(set(data["symbols"])),
        })

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
    if not account_overview.get("account_actual_total_cost") or account_overview.get("account_actual_total_cost", 0) <= 0:
        compact_data_gaps.append({
            "key": "账户实际总成本",
            "reason": "尚未录入；账户整体盈亏暂不可计算，当前仅可展示持仓浮动盈亏。",
        })

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
            "quote_retrieved_at": _iso_z(account_overview.get("quote_retrieved_at") or packet["account_overview"]["current_quote_estimate"]["quote_retrieved_at"]),
                "valuation_snapshot_id": account_overview.get("valuation_snapshot_id"),
                "valuation_generated_at": _iso_z(account_overview.get("valuation_generated_at")),
                "valuation_consistency_status": account_overview.get("valuation_consistency_status"),
                "valuation_consistency_checks": account_overview.get("valuation_consistency_checks"),
                "valuation_consistency_errors": account_overview.get("valuation_consistency_errors"),
                "symbol_name_map": symbol_name_map,
                "symbol_primary_map": symbol_primary_map,
                "analysis_boundaries": _COMPACT_BOUNDARIES,
                "snapshot_status_note": snapshot_status_note,
            },
        "account_facts": account_facts,
        "holdings": compact_holdings,
        "holding_trend_evidence": compact_trend_evidence,
        "market_breadth": packet.get("market_breadth", {}),
        "etf_share_observations": packet.get("etf_share_observations", {}),
        "market_event_radar": packet.get("market_event_radar", {}),
        "theme_evidence_radar": _compact_theme_evidence_radar(packet.get("theme_evidence_radar", {})),
        "overseas_tech_chain": _compact_overseas_tech_chain(packet.get("overseas_tech_chain", {})),
        "primary_direction_grouping": primary_direction_grouping,
        "all_direction_observations": {
            "direction_observations": all_direction_observations,
            "boundary": "全部方向观察允许同一持仓出现在多个方向中，因此不可相互加总，也不可与主要方向归组重复加总。",
        },
        "related_theme_observations": {
            "direction_observations": all_direction_observations,
            "risk_observations": risk_observations,
            "boundary": "全部方向观察允许同一持仓出现在多个方向中，因此不可相互加总，也不可与主要方向归组重复加总。",
        },
        "risk_observations": {
            "risk_observations": risk_observations,
            "boundary": "风险观察独立于关联方向，仅作描述性观察，不构成调仓或交易建议。",
        },
        "external_driver_summary": ext_summary,
        "data_gaps": compact_data_gaps,
        "ai_analysis_boundary": {
            "external_llm_called": packet["ai_analysis_boundary"]["external_llm_called"],
            "inactive_decision_rules": packet["ai_analysis_boundary"]["inactive_decision_rules"],
            "boundary": "当前上下文仅用于账户事实汇总、方向结构观察与数据缺口识别；不输出买卖或调仓指令。",
        },
        "suggested_questions_for_external_llm": _STRATEGY_LLM_QUESTIONS,
    }


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _compact_theme_evidence_radar(radar: dict[str, Any]) -> dict[str, Any]:
    themes = []
    for theme in (radar.get("themes") or [])[:3]:
        themes.append({
            "theme_id": theme.get("theme_id"),
            "theme_name": theme.get("theme_name"),
            "portfolio_relevance_score": theme.get("portfolio_relevance_score"),
            "evidence_maturity": theme.get("evidence_maturity"),
            "related_position_weight_pct": theme.get("related_position_weight_pct"),
            "matched_event_channels": (theme.get("matched_event_channels") or [])[:3],
            "related_positions": [
                {
                    "symbol": item.get("symbol"),
                    "name": item.get("name"),
                    "position_status": item.get("position_status"),
                    "weight_pct": item.get("weight_pct"),
                    "matched_tags": item.get("matched_tags") or [],
                    "relation_strength": item.get("relation_strength"),
                    "relation_label": item.get("relation_label"),
                    "role_in_theme": item.get("role_in_theme"),
                    "thesis_status": item.get("thesis_status"),
                    "open_questions": (item.get("open_questions") or [])[:3],
                    "invalid_condition": item.get("invalid_condition"),
                    "announcement_verification": item.get("announcement_verification"),
                    "ai_direction_classification": item.get("ai_direction_classification"),
                }
                for item in (theme.get("related_positions") or [])[:5]
            ],
            "chain_layers": [
                {
                    "layer_name": layer.get("layer_name"),
                    "physical_constraint": layer.get("physical_constraint"),
                    "evidence_questions": (layer.get("evidence_questions") or [])[:2],
                }
                for layer in (theme.get("chain_layers") or [])[:3]
            ],
            "confirming_events": (theme.get("confirming_events") or [])[:4],
            "invalidating_events": (theme.get("invalidating_events") or [])[:4],
            "portfolio_readout": theme.get("portfolio_readout"),
        })
    return {
        "generated_at": radar.get("generated_at"),
        "registry_version": radar.get("registry_version"),
        "registry_updated_at": radar.get("registry_updated_at"),
        "themes": themes,
        "boundary": radar.get("boundary"),
    }


def _compact_overseas_tech_chain(chain: dict[str, Any]) -> dict[str, Any]:
    indicators = []
    for item in chain.get("indicators", []):
        if item.get("data_status") == "available" or item.get("related_holdings"):
            indicators.append({
                "name": item.get("name"),
                "symbol": item.get("symbol"),
                "market": item.get("market"),
                "category": item.get("category"),
                "latest_price": item.get("latest_price"),
                "change_1d_pct": item.get("change_1d_pct"),
                "change_5d_pct": item.get("change_5d_pct"),
                "change_20d_pct": item.get("change_20d_pct"),
                "ma5": item.get("ma5"),
                "ma20": item.get("ma20"),
                "relative_ma20_pct": item.get("relative_ma20_pct"),
                "trend_state": item.get("trend_state"),
                "data_time": item.get("data_time"),
                "data_status": item.get("data_status"),
                "related_holdings": (item.get("related_holdings") or [])[:5],
                "mapping_reason": item.get("mapping_reason"),
                "risk_note": item.get("risk_note"),
            })
    return {
        "generated_at": chain.get("generated_at"),
        "provider": chain.get("provider"),
        "data_status": chain.get("data_status"),
        "indicator_count": chain.get("indicator_count"),
        "available_indicator_count": chain.get("available_indicator_count"),
        "risk_level": chain.get("risk_level", {}),
        "account_sensitivity_summary": chain.get("account_sensitivity_summary", {}),
        "open_sentiment_observation": chain.get("open_sentiment_observation"),
        "sentiment_path": chain.get("sentiment_path", []),
        "leading_signals": chain.get("leading_signals", []),
        "event_watchlist": chain.get("event_watchlist", []),
        "indicators": indicators[:18],
        "boundary": chain.get("boundary"),
    }


def _overseas_tech_chain_markdown(chain: dict[str, Any]) -> str:
    if not chain:
        return "## 海外风险偏好与全球科技链映射\n\n- 当前没有生成海外科技链数据。\n"
    risk = chain.get("risk_level") or {}
    sensitivity = chain.get("account_sensitivity_summary") or {}
    indicators = chain.get("indicators") or []

    def cell(value: Any) -> str:
        if value is None or value == "":
            return "-"
        if isinstance(value, float):
            return f"{value:.2f}"
        if isinstance(value, list):
            return "、".join(str(item) for item in value) or "-"
        return str(value).replace("|", "/").replace("\n", " ")

    def pct(value: Any) -> str:
        if value is None:
            return "-"
        try:
            return f"{float(value):+.2f}%"
        except (TypeError, ValueError):
            return cell(value)

    lines = [
        "## 海外风险偏好与全球科技链映射",
        "",
        f"- 风险等级：{cell(risk.get('level'))}。{cell(risk.get('judgment'))}",
        f"- 科技成长相关暴露：{pct(sensitivity.get('tech_growth_exposure_pct'))}",
        f"- 开盘观察：{cell(chain.get('open_sentiment_observation'))}",
        "",
        "### 海外科技链映射表",
        "",
        "| 指标 | 市场 | 分类 | 最新涨跌 | 5日 | 20日 | 相对MA20 | 状态 | 映射持仓 | 观察 |",
        "|---|---|---|---:|---:|---:|---:|---|---|---|",
    ]
    for item in indicators[:12]:
        holdings = "、".join(
            holding.get("name") or holding.get("symbol") or "-"
            for holding in (item.get("related_holdings") or [])[:4]
        ) or "-"
        if item.get("data_status") != "available":
            latest = "不可用"
        else:
            latest = pct(item.get("change_1d_pct"))
        lines.append(
            f"| {cell(item.get('name') or item.get('symbol'))} | {cell(item.get('market'))} | {cell(item.get('category'))} | "
            f"{latest} | {pct(item.get('change_5d_pct'))} | {pct(item.get('change_20d_pct'))} | "
            f"{pct(item.get('relative_ma20_pct'))} | {cell(item.get('trend_state') or item.get('data_status'))} | "
            f"{cell(holdings)} | {cell(item.get('risk_note') or item.get('missing_reason'))} |"
        )
    watchlist = chain.get("event_watchlist") or []
    if watchlist:
        lines.extend([
            "",
            "### 海外科技链事件观察清单",
            "",
            "| 分组 | 观察对象 | 观察重点 | 日程状态 |",
            "|---|---|---|---|",
        ])
        for item in watchlist:
            lines.append(
                f"| {cell(item.get('group'))} | {cell(item.get('items') or [])} | "
                f"{cell(item.get('observation'))} | {cell(item.get('schedule_status'))} |"
            )
    lines.extend([
        "",
        chain.get("boundary") or "海外指标仅作为外部风险偏好观察，不构成买卖、加仓、减仓或择时指令。",
        "",
    ])
    return "\n".join(lines)


def _theme_evidence_markdown(radar: dict[str, Any], *, compact: bool) -> str:
    themes = (radar.get("themes") or [])[:3] if compact else (radar.get("themes") or [])
    if not themes:
        return "## 主题证据雷达\n\n- 当前无可用主题证据注册表。\n"

    def cell(value: Any) -> str:
        if isinstance(value, list):
            value = "；".join(str(item) for item in value)
        return str(value or "-").replace("|", "/").replace("\n", " ")

    lines = [
        "## 主题证据雷达",
        "",
        "### 账户相关主题表",
        "",
        "| 主题 | 账户相关分 | 相关持仓 | 主题状态 | 组合提示 |",
        "|---|---:|---|---|---|",
    ]
    for theme in themes:
        positions = theme.get("related_positions") or []
        related = "、".join(
            f"{item.get('name') or item.get('symbol')}({item.get('relation_label') or '待核验'})"
            for item in positions[:5]
        ) or "-"
        lines.append(
            f"| {cell(theme.get('theme_name'))} | {theme.get('portfolio_relevance_score', 0)} | "
            f"{cell(related)} | {cell(theme.get('evidence_maturity'))} | {cell(theme.get('portfolio_readout'))} |"
        )

    lines.extend([
        "",
        "### 产业链层级表",
        "",
        "| 主题 | 层级 | 物理约束 | 待核验问题 |",
        "|---|---|---|---|",
    ])
    for theme in themes:
        for layer in (theme.get("chain_layers") or [])[:3 if compact else None]:
            lines.append(
                f"| {cell(theme.get('theme_name'))} | {cell(layer.get('layer_name'))} | "
                f"{cell(layer.get('physical_constraint'))} | {cell((layer.get('evidence_questions') or [])[:3])} |"
            )

    lines.extend([
        "",
        "### 持仓 Thesis 健康表",
        "",
        "| 标的 | 相关主题 | 产业链角色 | 当前状态 | 待核验问题 | 失效条件 |",
        "|---|---|---|---|---|---|",
    ])
    for theme in themes:
        for item in (theme.get("related_positions") or [])[:5 if compact else None]:
            lines.append(
                f"| {cell(item.get('name') or item.get('symbol'))} | {cell(theme.get('theme_name'))} | "
                f"{cell(item.get('role_in_theme'))} | {cell(item.get('thesis_status'))} / {cell(item.get('relation_label'))} | "
                f"{cell((item.get('open_questions') or [])[:3])} | {cell(item.get('invalid_condition'))} |"
            )

    lines.extend([
        "",
        "### 催化 / 反证事件表",
        "",
        "| 主题 | 确认信号 | 反证信号 | 关联持仓 |",
        "|---|---|---|---|",
    ])
    for theme in themes:
        positions = "、".join(
            item.get("name") or item.get("symbol")
            for item in (theme.get("related_positions") or [])[:5]
        ) or "-"
        lines.append(
            f"| {cell(theme.get('theme_name'))} | {cell((theme.get('confirming_events') or [])[:4])} | "
            f"{cell((theme.get('invalidating_events') or [])[:4])} | {cell(positions)} |"
        )
    lines.extend([
        "",
        radar.get("boundary") or "主题证据雷达仅用于研究观察，不构成交易建议。",
        "",
    ])
    return "\n".join(lines)


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
    elif "requires a successful probe before automatic retrieval" in reason_str:
        localized_reason = "数据源尚未完成成功探测"
    else:
        localized_reason = reason_str
    return localized_status, localized_reason


def render_compact_markdown(context: dict[str, Any]) -> str:
    """Render a compact, AI-friendly account analysis markdown."""
    meta = context["meta"]
    account = context["account_facts"]
    holdings = context["holdings"]
    holding_trend_evidence = context.get("holding_trend_evidence", [])
    etf_share_obs = context.get("etf_share_observations", {})
    market_event_radar = context.get("market_event_radar", {})
    theme_evidence_radar = context.get("theme_evidence_radar", {})
    overseas_tech_chain = context.get("overseas_tech_chain", {})
    primary_direction_grouping = context.get("primary_direction_grouping", [])
    all_directions = context.get("all_direction_observations", {})
    risk_obs = context.get("risk_observations", {})
    ext_summary = context["external_driver_summary"]
    data_gaps = context["data_gaps"]

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

    def _fmt_signed_amount(value: Any) -> str:
        if value is None:
            return "-"
        try:
            return f"{float(value):+,.2f}"
        except (TypeError, ValueError):
            return str(value)

    lines = [
        "# Stock-Pilot 账户分析上下文",
        "",
        f"生成时间（北京时间）：{_display_shanghai_time(meta.get('generated_at'))}",
        f"持仓快照时间（北京时间）：{_display_shanghai_time(meta.get('portfolio_as_of'))}",
        f"行情取数时间（北京时间）：{_display_shanghai_time(meta.get('quote_retrieved_at'))}",
    ]
    if meta.get("valuation_snapshot_id"):
        lines.append(f"估值快照：{meta.get('valuation_snapshot_id')}")
    if meta.get("snapshot_status_note"):
        lines.append(f"快照状态：{meta['snapshot_status_note']}")
    lines.extend([
        "",
        "> 注意：系统取数时间不是可验证市场报价时间；本次上下文所有金额来自同一冻结估值快照。",
        "",
        "## 分析边界",
    ])
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
    lines.append(f"| 当前估算总资产 | {_fmt_amount(account.get('total_assets'))} |")
    lines.append(f"| 当前行情持仓市值 | {_fmt_amount(account.get('total_market_value'))} |")
    lines.append(f"| 可用现金 | {_fmt_amount(account.get('cash_available'))} |")
    ir = account.get("invested_ratio_pct")
    lines.append(f"| 当前仓位 | {ir:.2f}% |" if ir is not None else "| 当前仓位 | - |")
    if account.get("account_actual_total_cost") is not None:
        lines.append(f"| 账户实际总成本 | {_fmt_amount(account.get('account_actual_total_cost'))} |")
        pnl = account.get("account_total_pnl")
        pnl_pct = account.get("account_total_pnl_pct")
        pnl_str = _fmt_signed_amount(pnl)
        pnl_pct_str = f" ({pnl_pct:+.2f}%)" if pnl_pct is not None else ""
        lines.append(f"| 账户总盈亏 | {pnl_str}{pnl_pct_str} |")
    else:
        lines.append("| 账户实际总成本 | 待录入 |")
        lines.append("| 账户总盈亏 | 暂不可计算 |")
    if account.get("current_holding_cost_basis") is not None:
        lines.append(f"| 当前持仓成本 | {_fmt_amount(account['current_holding_cost_basis'])} |")
        pnl = account.get("current_holding_unrealized_pnl")
        pnl_pct = account.get("current_holding_unrealized_pnl_pct")
        pnl_str = _fmt_signed_amount(pnl)
        pnl_pct_str = f" ({pnl_pct:+.2f}%)" if pnl_pct is not None else ""
        lines.append(f"| 当前持仓浮动盈亏 | {pnl_str}{pnl_pct_str} |")
    if account.get("repo_amount") is not None:
        lines.append(f"| 逆回购余额 | {_fmt_amount(account['repo_amount'])} |")
    lines.append("")

    # Holdings table
    lines.extend([
        "## 当前持仓",
        "",
        "| 标的 | 持仓数量 | 成本价 | 当前价 | 当前市值 | 当前持仓浮动盈亏 | 权重 | 关联方向 | 角色 |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|",
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
        directions = h.get("confirmed_directions", [])
        dir_labels = [_theme_label(d) for d in directions if d and d not in _EXCLUDED_FROM_COMPACT]
        role = _ROLE_LABEL_MAP.get(str(h.get("confirmed_position_role", "")).lower(), h.get("confirmed_position_role", ""))

        qty_str = f"{qty:,.0f}" if qty is not None else "-"
        cost_str = f"{cost:,.3f}" if cost is not None else "-"
        price_str = f"{price:,.3f}" if price is not None else "-"
        mv_str = _fmt_amount(mv)
        if pnl is not None and pnl_pct is not None:
            pnl_str = f"{pnl:+,.2f} ({pnl_pct:+.2f}%)"
        elif pnl is not None:
            pnl_str = f"{pnl:+,.2f}"
        else:
            pnl_str = "-"
        weight_str = f"{weight:.2f}%" if weight is not None else "-"
        dir_str = ", ".join(dir_labels) if dir_labels else "-"
        lines.append(f"| {name} | {qty_str} | {cost_str} | {price_str} | {mv_str} | {pnl_str} | {weight_str} | {dir_str} | {role} |")
    lines.append("")

    if holding_trend_evidence:
        lines.extend([
            "## 持仓近期走势证据",
            "",
            "| 标的 | 日K日期 | 当前价 | 5日 | 20日 | MA5 | MA10 | MA20 | MA30 | 相对MA20 | 走势状态 | 策略观察 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
        ])
        for item in holding_trend_evidence:
            if item.get("data_status") != "available":
                lines.append(
                    f"| {item.get('name') or item.get('symbol')} | - | - | - | - | - | - | - | - | - | 不可用 | {item.get('reason', '-')} |"
                )
                continue
            name = item.get("name") or item.get("symbol", "")
            lines.append(
                f"| {name} | {item.get('daily_k_as_of') or '-'} | {_fmt_amount(item.get('current_price'))} | "
                f"{_fmt_amount(item.get('return_5d_pct'))}% | {_fmt_amount(item.get('return_20d_pct'))}% | "
                f"{_fmt_amount(item.get('ma5'))} | {_fmt_amount(item.get('ma10'))} | {_fmt_amount(item.get('ma20'))} | {_fmt_amount(item.get('ma30'))} | "
                f"{_fmt_amount(item.get('price_vs_ma20_pct'))}% | {item.get('trend_state') or '-'} | {item.get('strategy_observation') or '-'} |"
            )
        lines.append("")
        lines.append("近期走势证据来自本地日K和派生技术指标，仅作弱信号观察，不构成买卖、加仓、减仓或止盈止损指令。")
        lines.append("")

    if holding_trend_evidence:
        lines.extend([
            "## 持仓量价快照（本地日K）",
            "",
            "| 标的 | 日K日期 | 开/高/低/收 | 成交量 | 5/10/20日均量 | 当日/20日均量 | 成交额 | 换手率 |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ])
        for item in holding_trend_evidence:
            if item.get("data_status") != "available":
                continue
            ohlc = "/".join(_fmt_amount(item.get(key)) for key in ("open", "high", "low", "latest_close"))
            volume_ma = "/".join(_fmt_amount(item.get(f"volume_ma_{window}")) for window in (5, 10, 20))
            lines.append(
                f"| {item.get('name') or item.get('symbol')} | {item.get('daily_k_as_of') or '-'} | {ohlc} | "
                f"{_fmt_amount(item.get('volume'))} | {volume_ma} | {_fmt_amount(item.get('volume_vs_ma_20_ratio'))}x | "
                f"{_fmt_amount(item.get('amount'))} | {_fmt_amount(item.get('turnover_rate'))}% |"
            )
        lines.extend([
            "",
            "日K量比口径：当日成交量 / 20日平均成交量；5/10/20日均量均按完整交易日计算。收盘后行情源量比在下表单列。",
            "",
        ])

    market_breadth = context.get("market_breadth", {})
    session_rows = [item for item in holding_trend_evidence if item.get("market_session_as_of")]
    if session_rows:
        lines.extend([
            "## 收盘后实时行情快照（待日K落库确认）",
            "",
            "| 标的 | 行情时间 | 开/高/低/现价 | 涨跌幅 | 成交量 | 成交额 | 换手率 | 行情源量比 | 当日/前5完整日均量 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for item in session_rows:
            ohlc = "/".join(_fmt_amount(item.get(key)) for key in ("session_open", "session_high", "session_low", "session_close"))
            lines.append(
                f"| {item.get('name') or item.get('symbol')} | {item.get('market_session_as_of')} | {ohlc} | "
                f"{_fmt_amount(item.get('session_pct_chg'))}% | {_fmt_amount(item.get('session_volume'))} | "
                f"{_fmt_amount(item.get('session_amount'))} | {_fmt_amount(item.get('session_turnover_rate'))}% | "
                f"{_fmt_amount(item.get('session_volume_ratio'))} | {_fmt_amount(item.get('session_volume_vs_prev_5d_ratio'))}x |"
            )
        lines.extend([
            "",
            "该快照来自收盘后实时行情源，待 BaoStock 日K落库后将由正式日K替代；两者不应混为同一数据时间点。",
            "",
        ])
    if market_breadth.get("data_status") == "available":
        total = market_breadth.get("total", {})
        shanghai = market_breadth.get("shanghai", {})
        shenzhen = market_breadth.get("shenzhen", {})
        lines.extend([
            "## 沪深市场广度（本地日K聚合）",
            "",
            "| 日K日期 | 覆盖股票数 | 两市成交额 | 较前日 | 5日均额 | 上涨/下跌/平盘 | 涨停/跌停（近似） | 沪市成交额 | 深市成交额 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            f"| {market_breadth.get('as_of') or '-'} | {market_breadth.get('coverage_count', 0)}/{market_breadth.get('universe_count', 0)} | "
            f"{_fmt_amount(total.get('turnover_100m_yuan'))}亿元 | {_fmt_amount(total.get('turnover_change_pct'))}% | "
            f"{_fmt_amount(total.get('turnover_ma_5_100m_yuan'))}亿元 | {total.get('advance_count', 0)}/{total.get('decline_count', 0)}/{total.get('flat_count', 0)} | "
            f"{total.get('limit_up_count', 0)}/{total.get('limit_down_count', 0)} | "
            f"{_fmt_amount(shanghai.get('turnover_100m_yuan'))}亿元 | {_fmt_amount(shenzhen.get('turnover_100m_yuan'))}亿元 |",
            "",
            (
                f"数据新鲜度：最近可用日K为 {market_breadth.get('as_of')}，目标日K {market_breadth.get('target_date')} 尚在刷新。"
                if market_breadth.get("is_stale")
                else "数据新鲜度：已覆盖当前目标日K。"
            ),
            "",
            market_breadth.get("boundary") or "",
            "",
        ])
    elif market_breadth:
        lines.extend([
            "## 沪深市场广度（待刷新）",
            "",
            f"目标日K：{market_breadth.get('target_date') or '-'}；{market_breadth.get('reason') or '暂无可用聚合。'}",
            "",
        ])

    observations = etf_share_obs.get("observations", []) if isinstance(etf_share_obs, dict) else []
    if observations:
        def _fmt_pct(value: Any) -> str:
            if value is None:
                return "暂无"
            try:
                return f"{float(value) * 100:+.2f}%"
            except (TypeError, ValueError):
                return "暂无"

        lines.extend([
            "## ETF 份额观察",
            "",
            "| ETF | 最新日期 | 最新份额 | 1日变化 | 5日变化 | 20日变化 | 数据源 |",
            "|---|---:|---:|---:|---:|---:|---|",
        ])
        for item in observations:
            name = item.get("fund_name") or item.get("fund_code")
            latest_share = item.get("latest_share_100m")
            latest_share_str = f"{float(latest_share):.2f} 亿份" if latest_share is not None else "暂无"
            lines.append(
                f"| {name} | {item.get('latest_trade_date') or '暂无'} | {latest_share_str} | "
                f"{_fmt_pct(item.get('share_chg_1d'))} | {_fmt_pct(item.get('share_chg_5d'))} | "
                f"{_fmt_pct(item.get('share_chg_20d'))} | {item.get('source') or 'akshare'} |"
            )
        lines.append("")
        lines.append("ETF 份额变化仅作为资金变化观察证据，不构成买卖、加减仓或价格方向判断。")
        lines.append("")

    lines.append(_overseas_tech_chain_markdown(overseas_tech_chain))

    event_items = market_event_radar.get("events", []) if isinstance(market_event_radar, dict) else []
    if event_items:
        lines.extend([
            "## 近期风险事件日历",
            "",
            "| 日期 | 事件 | 市场影响 | 账户相关 | 组合风险 | 影响路径 | 关联持仓 | 组合提示 |",
            "|---|---|---:|---:|---:|---|---|---|",
        ])
        for event in event_items[:8]:
            related = event.get("related_positions") or []
            related_text = ", ".join(
                f"{item.get('name') or item.get('symbol')}"
                f"[{'直接驱动' if item.get('relation_type') == 'direct_driver' else '广义风险偏好间接影响'}]"
                f"({item.get('portfolio_weight_pct', '-') }%)"
                for item in related[:4]
            ) or "-"
            channels = ", ".join(
                item.get("label") or item.get("channel") or "-"
                for item in (event.get("matched_impact_channels") or [])[:3]
            ) or "-"
            event_time = f"{event.get('date') or '-'} {event.get('time_et') or ''} ET".strip()
            lines.append(
                f"| {event_time} | {event.get('title') or '-'} | {event.get('market_impact_score', event.get('impact_score', '-'))} | "
                f"{event.get('account_relevance_score', '-')} | {event.get('portfolio_risk_score', event.get('impact_score', '-'))} | {channels} | "
                f"{related_text} | {event.get('portfolio_readout') or '-'} |"
            )
        lines.append("")
        lines.append(market_event_radar.get("boundary") or "事件日历仅作波动风险提示，不构成买卖、加仓、减仓或择时指令。")
        lines.append("")

    lines.append(_theme_evidence_markdown(theme_evidence_radar, compact=True))

    # Primary direction grouping
    lines.extend([
        "## 主要方向归组",
        "",
        "| 主要方向 | 当前市值 | 占总资产比例 | 组成标的 |",
        "|---|---:|---:|---|",
    ])
    for item in primary_direction_grouping:
        direction = _theme_label(item.get("direction", ""))
        mv = item.get("market_value", 0)
        wp = item.get("weight_pct", 0)
        syms = _names(item.get("symbols", []))
        lines.append(f"| {direction} | {mv:,.2f} | {wp:.2f}% | {syms} |")
    lines.append("")
    lines.append("每只持仓仅按首个关联方向进行唯一归组，因此本表可加总；其他方向仅作为关联观察。")
    lines.append("")

    # All direction observations
    direction_obs = all_directions.get("direction_observations", [])
    if direction_obs:
        lines.extend([
            "## 全部方向观察",
            "",
            "| 方向 | 当前市值 | 占总资产比例 | 关联标的 | 说明 |",
            "|---|---:|---:|---|---|",
        ])
        for item in direction_obs:
            direction = _theme_label(item.get("direction", ""))
            mv = item.get("market_value", 0)
            wp = item.get("weight_pct", 0)
            syms = _names(item.get("symbols", []))
            note = "与方向背景相关；仅为关联观察，不构成因果或交易结论"
            if item.get("direction") == "GOLD":
                non_gold_syms = [s for s in item.get("symbols", []) if symbol_primary_map.get(s) != "GOLD"]
                if non_gold_syms:
                    note = f"其中 {_names(non_gold_syms)} 的主要方向归组仍归属其他类别"
            elif item.get("direction") == "COPPER":
                note = "与铜价背景相关；仅为关联观察，不构成因果或交易结论"
            lines.append(f"| {direction} | {mv:,.2f} | {wp:.2f}% | {syms} | {note} |")
        lines.append("")
        lines.append("全部方向观察允许同一持仓出现在多个方向中，因此不可相互加总，也不可与主要方向归组重复加总。")
        lines.append("")

    # Risk observations
    risks = risk_obs.get("risk_observations", [])
    if risks:
        lines.extend([
            "## 风险观察",
            "",
            "| 观察项 | 当前市值 | 占总资产比例 | 关联标的 | 说明 |",
            "|---|---:|---:|---|---|",
        ])
        for item in risks:
            flag = _theme_label(item.get("risk_flag", ""))
            mv = item.get("market_value", 0)
            wp = item.get("weight_pct", 0)
            syms = _names(item.get("symbols", []))
            note = "描述性观察，不代表阈值触发或调仓建议"
            lines.append(f"| {flag} | {mv:,.2f} | {wp:.2f}% | {syms} | {note} |")
        lines.append("")
        lines.append("风险观察不可与主要方向归组或全部方向观察加总。")
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

    # Structured data_gaps and suggested questions remain in the JSON context,
    # but the default markdown stays focused on reusable evidence. The user's
    # actual AI task can change each time.

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
            "## Holding Recent Trend Evidence",
            "Daily-K trend evidence and technical indicators are weak auxiliary signals only.",
            f"```json\n{json.dumps(packet.get('holding_trend_evidence', []), ensure_ascii=False, indent=2, default=str)}\n```",
            "",
            "## ETF Share Observations",
            "ETF share changes are fund-size observations only, not trading signals.",
            f"```json\n{json.dumps(packet.get('etf_share_observations', {}), ensure_ascii=False, indent=2, default=str)}\n```",
            "",
            "## Market Event Radar",
            "Known upcoming events are volatility-risk context only, not timing instructions.",
            f"```json\n{json.dumps(packet.get('market_event_radar', {}), ensure_ascii=False, indent=2, default=str)}\n```",
            "",
            "## Overseas Tech Chain Mapping",
            "Overseas indicators are delayed external risk-appetite observations only.",
            f"```json\n{json.dumps(packet.get('overseas_tech_chain', {}), ensure_ascii=False, indent=2, default=str)}\n```",
            "",
            _theme_evidence_markdown(packet.get("theme_evidence_radar", {}), compact=False),
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
        "## Interpretation Boundaries",
        *[f"- {_fmt(item)}" for item in packet["interpretation_boundaries"]],
        "",
    ])
    if meta["analysis_scope"] == "single_stock":
        lines.extend([
            "## Missing Data",
            *[f"- {_fmt(item)}" for item in packet["missing_data"]],
            "",
            "## Neutral Questions for an External LLM",
            *[f"- {question}" for question in packet["suggested_questions_for_external_llm"]],
            "",
        ])
    lines.append("No buy/sell recommendation is generated by this packet.")
    return "\n".join(lines)
