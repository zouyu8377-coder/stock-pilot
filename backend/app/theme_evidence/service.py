from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.portfolio.schemas import PortfolioPosition, PortfolioState


THEME_EVIDENCE_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "theme_evidence"
    / "theme_evidence_registry.json"
)


def _compact_symbol(symbol: str) -> str:
    return str(symbol or "").split(".", 1)[0].strip().zfill(6)


def _round(value: Any, digits: int = 2) -> float | None:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def load_theme_evidence_registry(
    path: Path = THEME_EVIDENCE_REGISTRY_PATH,
) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "version": "unavailable",
            "themes": [],
            "boundary": "主题证据注册表缺失；当前无法生成主题证据雷达。",
        }
    except json.JSONDecodeError as exc:
        return {
            "version": "invalid",
            "themes": [],
            "boundary": f"主题证据注册表无法解析：{exc}",
        }
    if not isinstance(payload.get("themes"), list):
        payload["themes"] = []
    return payload


def _weight_map(state: PortfolioState, weights: dict[str, float] | None) -> dict[str, float]:
    result = {
        _compact_symbol(item.get("symbol", "")): float(item.get("weight_pct") or 0)
        for item in state.metrics.position_weights
        if item.get("symbol")
    }
    for symbol, value in (weights or {}).items():
        result[_compact_symbol(symbol)] = float(value or 0)
    return result


def _position_tags(position: PortfolioPosition) -> set[str]:
    return {
        str(tag).strip().upper()
        for tag in [
            *(position.directions or []),
            *(position.theme_tags or []),
            position.primary_theme or "",
        ]
        if str(tag).strip()
    }


def _event_channels(market_event_radar: dict[str, Any] | None) -> set[str]:
    channels: set[str] = set()
    for event in (market_event_radar or {}).get("events", []):
        for channel in [
            *(event.get("matched_impact_channels") or []),
            *(event.get("impact_channels") or []),
        ]:
            if isinstance(channel, dict):
                key = channel.get("channel")
            else:
                key = channel
            if key:
                channels.add(str(key).strip().lower())
    return channels


def _relation_label(strength: str) -> str:
    return {
        "high": "高相关",
        "medium": "中相关",
        "weak": "弱关联 / 待核验",
    }.get(strength, "待核验")


def _related_position(
    position: PortfolioPosition,
    mapping: dict[str, Any],
    matched_tags: list[str],
    weight_pct: float,
) -> dict[str, Any]:
    from app.disclosure_verification import load_disclosure_verification

    strength = str(mapping.get("relation_strength") or "medium")
    is_watchlist = float(position.quantity or 0) == 0
    status = mapping.get("thesis_status") or "needs_verification"
    if is_watchlist:
        status = "watchlist_observation"
    verification = load_disclosure_verification(position.symbol)
    return {
        "symbol": position.symbol,
        "name": position.name,
        "position_status": "watchlist" if is_watchlist else "active",
        "position_role": (
            position.position_role.value
            if hasattr(position.position_role, "value")
            else str(position.position_role)
        ),
        "current_position_value": _round(position.market_value or 0),
        "weight_pct": _round(weight_pct) or 0,
        "weight": _round(weight_pct / 100, 4) or 0,
        "matched_tags": matched_tags,
        "relation_strength": strength,
        "relation_label": _relation_label(strength),
        "role_in_theme": mapping.get("role_in_theme") or "主题候选，产业链角色待核验",
        "thesis_status": status,
        "open_questions": list(mapping.get("open_questions") or [])[:3],
        "invalid_condition": mapping.get("invalid_condition") or "主题相关证据无法持续验证。",
        "announcement_verification": verification,
    }


def build_theme_evidence_radar(
    state: PortfolioState,
    theme_registry: dict[str, Any] | None = None,
    weights: dict[str, float] | None = None,
    *,
    market_event_radar: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = theme_registry or load_theme_evidence_registry()
    weight_by_symbol = _weight_map(state, weights)
    active_event_channels = _event_channels(market_event_radar)
    themes: list[dict[str, Any]] = []

    for seed in registry.get("themes", []):
        theme_tags = {str(tag).upper() for tag in seed.get("theme_tags", [])}
        candidate_tags = {str(tag).upper() for tag in seed.get("candidate_tags", [])}
        mappings = seed.get("symbol_mappings") or {}
        related: list[dict[str, Any]] = []
        direct_theme_hit = False
        candidate_hit = False
        high_volatility = False

        for position in state.snapshot.positions:
            symbol = _compact_symbol(position.symbol)
            tags = _position_tags(position)
            mapping = mappings.get(symbol)
            matched_theme = sorted(tags & theme_tags)
            matched_candidate = sorted(tags & candidate_tags)
            if not mapping and not matched_theme and not matched_candidate:
                continue

            direct_theme_hit = direct_theme_hit or bool(matched_theme)
            candidate_hit = candidate_hit or bool(matched_candidate)
            high_volatility = high_volatility or "HIGH_VOLATILITY" in set(position.risk_flags or [])
            fallback_mapping = {
                "role_in_theme": "标签命中的主题候选，产业链角色待核验",
                "relation_strength": "weak",
                "thesis_status": "weak_relation_needs_verification",
                "open_questions": ["标签关联是否能够由收入、订单或利润证据验证？"],
                "invalid_condition": "仅有标签关联，缺少业务或利润证据。",
            }
            related.append(
                _related_position(
                    position,
                    mapping or fallback_mapping,
                    sorted(set([*matched_theme, *matched_candidate])),
                    weight_by_symbol.get(symbol, 0.0),
                )
            )

        related.sort(
            key=lambda item: (
                {"high": 3, "medium": 2, "weak": 1}.get(item["relation_strength"], 0),
                item["weight_pct"],
            ),
            reverse=True,
        )
        active_related = [item for item in related if item["position_status"] == "active"]
        total_weight_pct = sum(float(item["weight_pct"] or 0) for item in active_related)
        matched_channels = sorted(
            active_event_channels
            & {str(channel).strip().lower() for channel in seed.get("impact_channels", [])}
        )

        score = 0
        score_reasons: list[str] = []
        if direct_theme_hit:
            score += 30
            score_reasons.append("账户方向命中主题标签 +30")
        if candidate_hit:
            score += 20
            score_reasons.append("账户方向命中候选标签 +20")
        if any(float(item["weight_pct"] or 0) >= 10 for item in active_related):
            score += 15
            score_reasons.append("单一相关持仓权重不低于10% +15")
        if total_weight_pct >= 20:
            score += 15
            score_reasons.append("主题相关持仓总权重不低于20% +15")
        if high_volatility:
            score += 5
            score_reasons.append("相关标的含高波动标签 +5")
        if matched_channels:
            score += 5
            score_reasons.append("近期事件命中主题影响路径 +5")
        score = min(score, 100)

        maturity = "seed_only" if not related else "watching"

        if not related:
            readout = "当前账户暂无明确相关标的，保留主题种子和待核验问题。"
        elif any(item["relation_strength"] == "weak" for item in related) and not active_related:
            readout = "当前仅有弱关联观察标的，需要先补充业务、订单或利润证据。"
        else:
            names = "、".join(item["name"] or item["symbol"] for item in related[:3])
            readout = (
                f"账户与该主题相关的主要标的包括{names}；当前用于跟踪证据兑现、反证条件和研究优先级，"
                "不得直接转化为交易指令。"
            )

        themes.append(
            {
                "theme_id": seed.get("theme_id"),
                "theme_name": seed.get("theme_name"),
                "description": seed.get("description"),
                "portfolio_relevance_score": score,
                "score_reasons": score_reasons,
                "evidence_maturity": maturity,
                "related_position_weight_pct": round(total_weight_pct, 2),
                "matched_event_channels": matched_channels,
                "related_positions": related,
                "chain_layers": seed.get("chain_layers", []),
                "confirming_events": list(seed.get("confirming_events", [])),
                "invalidating_events": list(seed.get("invalidating_events", [])),
                "portfolio_readout": readout,
            }
        )

    themes.sort(
        key=lambda item: (
            item["portfolio_relevance_score"],
            item["related_position_weight_pct"],
        ),
        reverse=True,
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry_version": registry.get("version"),
        "registry_updated_at": registry.get("updated_at"),
        "themes": themes,
        "boundary": registry.get("boundary")
        or "主题证据雷达仅用于研究观察，不构成交易建议。",
    }
