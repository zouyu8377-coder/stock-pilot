from __future__ import annotations

from typing import Any

from app.portfolio.dashboard_cache import get_dashboard_bundle
from app.portfolio.task_evidence import coverage_source_blocks


def _symbol(value: str | None) -> str:
    return str(value or "").split(".", 1)[0].zfill(6)


def _clamp(value: float, low: float = 0, high: float = 100) -> int:
    return max(int(low), min(int(high), round(value)))


def _coverage_gain_pp(*, position_weight: float, total_weight: float, gap: dict[str, Any]) -> float:
    """Maximum account-level coverage gain if this one dimension reaches its target."""
    if total_weight <= 0:
        return 0.0
    missing = max(float(gap.get("target") or 0) - float(gap.get("coverage") or 0), 0.0)
    dimension_weight = max(float(gap.get("weight") or 0), 0.0) / 100
    return round(position_weight / total_weight * missing * dimension_weight, 2)


def _theme_positions(theme_radar: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rank = {"high": 3, "medium": 2, "weak": 1}
    result: dict[str, dict[str, Any]] = {}
    for theme in theme_radar.get("themes", []):
        for item in theme.get("related_positions", []):
            key = _symbol(item.get("symbol"))
            previous = result.get(key)
            if previous and rank.get(str(previous.get("relation_strength")), 0) >= rank.get(str(item.get("relation_strength")), 0):
                continue
            result[key] = {**item, "theme_id": theme.get("theme_id"), "theme_name": theme.get("theme_name")}
    return result


def _health_coverage(position: dict[str, Any], mapping: dict[str, Any], events: list[dict[str, Any]]) -> tuple[int, dict[str, int]]:
    verification = mapping.get("announcement_verification") or {}
    thesis = 15
    if mapping.get("theme_id"):
        thesis += 20
    if mapping.get("role_in_theme"):
        thesis += 10
    if mapping.get("invalid_condition"):
        thesis += 10
    if mapping.get("open_questions"):
        thesis += 10
    if verification.get("status") == "verified":
        items = verification.get("items") or []
        verified = sum(1 for item in items if item.get("status") in {"supported", "partially_supported", "contradicted"})
        thesis += min(30, verified * 10)
    else:
        thesis = min(thesis, 65)

    trend = 100 if (position.get("trend") or {}).get("data_status") == "available" else 0
    compact = _symbol(position.get("symbol"))
    related = [
        event for event in events
        if int(event.get("days_until") or -1) >= 0
        and any(_symbol(item.get("symbol")) == compact for item in event.get("related_positions", []))
    ]
    macro = [
        event for event in events
        if int(event.get("days_until") or -1) >= 0 and str(event.get("category") or "").startswith("macro_")
    ]
    event = 70 if related or macro else 45
    details = {"thesis": _clamp(thesis), "trend": trend, "position": 100, "event": event}
    raw = details["thesis"] * 0.35 + trend * 0.25 + 100 * 0.25 + event * 0.15
    return _clamp(raw if verification.get("status") == "verified" else min(raw, 70)), details


def _attractiveness_gaps(position: dict[str, Any]) -> list[dict[str, Any]]:
    dimensions = (position.get("attractiveness") or {}).get("dimensions") or []
    result = []
    for dimension in dimensions:
        coverage = int(dimension.get("coverage") or 0)
        if coverage >= 70:
            continue
        key = str(dimension.get("key") or "")
        if key == "trend_strength":
            tool, evidence_type, label = "stock_snapshot", "market_snapshot", "趋势与相对强度"
        elif key in {"evidence_change", "catalyst"}:
            tool, evidence_type, label = "disclosure_snapshot", "announcement", "证据变化与催化"
        else:
            continue
        result.append({
            "dimension": f"attractiveness.{key}",
            "label": label,
            "coverage": coverage,
            "target": 70,
            "tool": tool,
            "evidence_type": evidence_type,
            "weight": int(dimension.get("weight") or 0),
        })
    return result


def _refreshability(candidate: dict[str, Any], source_blocks: dict[str, str]) -> dict[str, Any]:
    symbol = _symbol((candidate.get("target_symbols") or [""])[0])
    evidence_type = str(candidate.get("evidence_type") or "")
    if evidence_type == "manual_review":
        return {
            "state": "manual_required",
            "label": "需人工补充",
            "can_improve_on_refresh": False,
            "reason": "当前未配置稳定、可审计的免费估值来源；再次刷新不会补齐该项。",
        }
    blocker = None
    if evidence_type == "announcement":
        blocker = source_blocks.get(symbol) or source_blocks.get("__announcement__")
    if blocker:
        return {
            "state": "source_blocked",
            "label": "数据源受阻",
            "can_improve_on_refresh": False,
            "reason": blocker,
        }
    return {
        "state": "retryable",
        "label": "可再次自动取证",
        "can_improve_on_refresh": True,
        "reason": "下次刷新会在每日额度内重新取证；取得新的有效事实后才会提高覆盖率。",
    }


def build_coverage_plan(*, max_candidates: int = 12, force: bool = False) -> dict[str, Any]:
    """Return deterministic, budget-ready evidence tasks from dashboard coverage gaps."""
    dashboard = get_dashboard_bundle(force=force)["dashboard"]
    positions = [item for item in dashboard.get("positions", []) if float(item.get("quantity") or 0) > 0]
    mappings = _theme_positions(dashboard.get("theme_evidence_radar") or {})
    events = (dashboard.get("market_event_radar") or {}).get("events") or []
    risk_scores = {_symbol(item.get("symbol")): int(item.get("score") or 0) for item in dashboard.get("risk_queue", [])}
    opportunity_scores = {_symbol(item.get("symbol")): int(item.get("score") or 0) for item in dashboard.get("opportunity_queue", [])}

    total_weight = sum(float(item.get("portfolio_weight_pct") or 0) for item in positions)
    weighted_health = 0.0
    weighted_attractiveness = 0.0
    candidates: list[dict[str, Any]] = []

    for position in positions:
        symbol = _symbol(position.get("symbol"))
        weight = float(position.get("portfolio_weight_pct") or 0)
        mapping = mappings.get(symbol, {})
        health, health_dimensions = _health_coverage(position, mapping, events)
        attractiveness = int((position.get("attractiveness") or {}).get("coverage") or 0)
        weighted_health += health * weight
        weighted_attractiveness += attractiveness * weight

        risk = risk_scores.get(symbol, 0)
        opportunity = opportunity_scores.get(symbol, 0)
        decision_impact = 85 if risk >= 5 else 70 if opportunity >= 4 else 45
        related_event = any(
            any(_symbol(item.get("symbol")) == symbol for item in event.get("related_positions", []))
            and 0 <= int(event.get("days_until") or -1) <= 7
            for event in events
        )
        urgency = 85 if related_event else 70 if health_dimensions["trend"] == 0 else 40

        gaps: list[dict[str, Any]] = []
        if health_dimensions["trend"] == 0:
            gaps.append({"dimension": "health.trend", "label": "趋势与波动", "coverage": 0, "target": 100, "tool": "stock_snapshot", "evidence_type": "market_snapshot", "weight": 25})
        if health_dimensions["thesis"] < 65:
            gaps.append({"dimension": "health.thesis", "label": "持仓逻辑与公告验证", "coverage": health_dimensions["thesis"], "target": 65, "tool": "disclosure_snapshot", "evidence_type": "announcement", "weight": 35})
        if health_dimensions["event"] < 70 and related_event:
            gaps.append({"dimension": "health.event", "label": "临近事件影响", "coverage": health_dimensions["event"], "target": 70, "tool": "event_snapshot", "evidence_type": "event_outcome", "weight": 15})
        gaps.extend(_attractiveness_gaps(position))

        for gap in gaps:
            auto = gap["tool"] != "manual_review"
            metric = "health" if str(gap["dimension"]).startswith("health.") else "attractiveness"
            gain_pp = _coverage_gain_pp(
                position_weight=weight,
                total_weight=total_weight,
                gap=gap,
            )
            freshness = 80 if gap["dimension"] in {"health.trend", "attractiveness.trend_strength"} else 55
            priority_score = _clamp(weight * 3 + decision_impact * 0.25 + urgency * 0.2 + freshness * 0.15 + (100 if auto else 20) * 0.1)
            priority = "high" if priority_score >= 70 else "medium" if priority_score >= 50 else "low"
            candidates.append({
                "priority": priority,
                "priority_score": priority_score,
                "subject": position.get("name") or position.get("symbol"),
                "task": f"补齐{gap['label']}证据并重新评估覆盖率",
                "reason": f"{gap['label']}覆盖 {gap['coverage']}%，当前持仓权重 {weight:.2f}%，可能影响持仓结论。",
                "target_symbols": [symbol],
                "evidence_type": gap["evidence_type"],
                "missing_evidence": [f"{gap['label']}：覆盖 {gap['coverage']}% → 目标 {gap['target']}%"],
                "success_criteria": "取得可追溯的新事实后重新计算覆盖率；无新增事实时保持原置信度。",
                "planning_origin": "coverage_gap_auto",
                "coverage_gap": {
                    "dimension": gap["dimension"],
                    "label": gap["label"],
                    "coverage_before_pct": gap["coverage"],
                    "target_coverage_pct": gap["target"],
                    "account_weight_pct": round(weight, 2),
                    "dimension_impacts": [{
                        "dimension": gap["dimension"],
                        "label": gap["label"],
                        "coverage_before_pct": gap["coverage"],
                        "target_coverage_pct": gap["target"],
                        "metric": metric,
                        "max_account_coverage_gain_pp": gain_pp,
                    }],
                    "projected_health_gain_pp": gain_pp if metric == "health" else 0.0,
                    "projected_attractiveness_gain_pp": gain_pp if metric == "attractiveness" else 0.0,
                    "decision_impact": decision_impact,
                    # A large position with a material evidence gap can change the
                    # decision even before it has been labelled as an explicit risk.
                    "decision_sensitive": decision_impact >= 70 or (
                        weight >= 10 and gap["coverage"] < gap["target"]
                    ),
                    "priority_score": priority_score,
                },
            })

    candidates.sort(key=lambda item: (-int(item["priority_score"]), -float(item["coverage_gap"]["account_weight_pct"])))
    # One source call can often close several dimensions for the same holding.
    # Merge these before applying the daily budget so a single high-weight name
    # cannot consume the whole morning queue with duplicate requests.
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for candidate in candidates:
        key = (str((candidate.get("target_symbols") or [""])[0]), str(candidate.get("evidence_type") or ""))
        current = merged.get(key)
        if not current:
            candidate["coverage_gap"]["related_dimensions"] = [candidate["coverage_gap"].get("dimension")]
            merged[key] = candidate
            continue
        current["missing_evidence"] = list(dict.fromkeys([
            *(current.get("missing_evidence") or []),
            *(candidate.get("missing_evidence") or []),
        ]))
        current["coverage_gap"]["related_dimensions"] = list(dict.fromkeys([
            *(current["coverage_gap"].get("related_dimensions") or []),
            candidate["coverage_gap"].get("dimension"),
        ]))
        impacts = current["coverage_gap"].setdefault("dimension_impacts", [])
        incoming_impacts = candidate["coverage_gap"].get("dimension_impacts") or []
        known_dimensions = {item.get("dimension") for item in impacts}
        impacts.extend(item for item in incoming_impacts if item.get("dimension") not in known_dimensions)
        current["coverage_gap"]["projected_health_gain_pp"] = round(sum(
            float(item.get("max_account_coverage_gain_pp") or 0)
            for item in impacts if item.get("metric") == "health"
        ), 2)
        current["coverage_gap"]["projected_attractiveness_gain_pp"] = round(sum(
            float(item.get("max_account_coverage_gain_pp") or 0)
            for item in impacts if item.get("metric") == "attractiveness"
        ), 2)
        current["coverage_gap"]["decision_sensitive"] = bool(
            current["coverage_gap"].get("decision_sensitive") or candidate["coverage_gap"].get("decision_sensitive")
        )
        current["priority_score"] = max(int(current["priority_score"]), int(candidate["priority_score"]))
        current["coverage_gap"]["priority_score"] = current["priority_score"]
        labels = [str(item).split("：", 1)[0] for item in current["missing_evidence"]]
        current["task"] = f"补齐{'、'.join(dict.fromkeys(labels))}证据并重新评估覆盖率"

    candidates = sorted(
        merged.values(),
        key=lambda item: (-int(item["priority_score"]), -float(item["coverage_gap"]["account_weight_pct"])),
    )
    source_blocks = coverage_source_blocks()
    for candidate in candidates:
        candidate["refreshability"] = _refreshability(candidate, source_blocks)
    health_coverage = _clamp(weighted_health / total_weight) if total_weight else 0
    attractiveness_coverage = _clamp(weighted_attractiveness / total_weight) if total_weight else 0
    automatic_candidate_count = sum(
        1 for item in candidates if item["evidence_type"] != "manual_review"
    )
    retryable_candidate_count = sum(
        1 for item in candidates if item["refreshability"]["state"] == "retryable"
    )
    source_blocked_count = sum(
        1 for item in candidates if item["refreshability"]["state"] == "source_blocked"
    )
    return {
        "summary": {
            "health_coverage_pct": health_coverage,
            "attractiveness_coverage_pct": attractiveness_coverage,
            "joint_coverage_pct": min(health_coverage, attractiveness_coverage),
            "active_position_count": len(positions),
            "candidate_count": len(candidates),
            "automatic_candidate_count": automatic_candidate_count,
            "manual_review_count": len(candidates) - automatic_candidate_count,
            "retryable_candidate_count": retryable_candidate_count,
            "source_blocked_count": source_blocked_count,
        },
        "candidates": candidates[:max(0, max_candidates)],
    }
