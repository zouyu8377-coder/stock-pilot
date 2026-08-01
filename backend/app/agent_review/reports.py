from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from app.agent_review.outcomes import (
    ACTIONS_PATH,
    RECOMMENDATIONS_PATH,
    _action_learning_eligible,
    _migrate_action_records,
    _read,
)


REASON_LABELS = {
    "direction_judgment": "方向判断",
    "timing_or_threshold": "时点或阈值",
    "risk_omission": "风险遗漏",
    "signal_not_realized": "信号未兑现",
    "market_follow_through": "市场跟随",
}


def _month_of(record: dict[str, Any]) -> str | None:
    value = record.get("evaluated_at")
    if not value:
        value = (record.get("outcome") or {}).get("market_result", {}).get("evaluation_date")
    if not value:
        results = (record.get("outcome") or {}).get("symbol_results", {})
        value = next((item.get("evaluation_date") for item in results.values()), None)
    return str(value)[:7] if value else None


def _scorecard(records: list[dict[str, Any]]) -> dict[str, Any]:
    verdicts = Counter((item.get("outcome") or {}).get("verdict") for item in records)
    evaluated = sum(verdicts.values())
    supported = verdicts["supported"]
    excess_values = [
        float(item["outcome"]["excess_return_pct"])
        for item in records
        if (item.get("outcome") or {}).get("excess_return_pct") is not None
    ]
    return {
        "evaluated": evaluated,
        "supported": supported,
        "not_supported": verdicts["not_supported"],
        "mixed": verdicts["mixed"],
        "support_rate_pct": round(supported / evaluated * 100, 1) if evaluated else None,
        "average_excess_return_pct": round(sum(excess_values) / len(excess_values), 2) if excess_values else None,
    }


def build_monthly_report(month: str | None = None) -> dict[str, Any]:
    selected_month = month or datetime.now().strftime("%Y-%m")
    recommendations = [
        item for item in _read(RECOMMENDATIONS_PATH)
        if item.get("outcome") and _month_of(item) == selected_month
    ]
    all_actions = _read(ACTIONS_PATH)
    _migrate_action_records(all_actions)
    actions = [
        item for item in all_actions
        if item.get("outcome") and _month_of(item) == selected_month
    ]
    confirmed_actions = [item for item in actions if _action_learning_eligible(item)]
    reason_counts: Counter[str] = Counter()
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in [*recommendations, *confirmed_actions]:
        outcome = item.get("outcome") or {}
        reason_counts.update(outcome.get("reason_categories", []))
        by_category[str(item.get("category") or item.get("action_type") or "other")].append(item)

    recommendation_score = _scorecard(recommendations)
    action_score = _scorecard(confirmed_actions)
    top_reasons = [
        {"key": key, "label": REASON_LABELS.get(key, key), "count": count}
        for key, count in reason_counts.most_common(5)
    ]
    category_stats = [
        {"category": category, **_scorecard(items)}
        for category, items in sorted(by_category.items())
    ]
    if not recommendations and not confirmed_actions:
        summary = "本月尚无到期建议或已确认调仓可供评价。"
    else:
        parts = [
            f"本月完成 {recommendation_score['evaluated']} 条建议评价",
            f"{len(confirmed_actions)} 条已确认调仓评价",
        ]
        if recommendation_score["support_rate_pct"] is not None:
            parts.append(f"建议支持率 {recommendation_score['support_rate_pct']}%")
        if recommendation_score["average_excess_return_pct"] is not None:
            parts.append(f"建议平均超额 {recommendation_score['average_excess_return_pct']}%")
        summary = "，".join(parts) + "。"
    return {
        "contract_version": "agent_monthly_report.v1",
        "month": selected_month,
        "generated_at": datetime.now().astimezone().isoformat(),
        "summary": summary,
        "recommendations": recommendation_score,
        "confirmed_actions": action_score,
        "unconfirmed_action_count": sum(
            1 for item in all_actions
            if item.get("decision_status") == "candidate"
        ),
        "reason_categories": top_reasons,
        "category_stats": category_stats,
        "method": "deterministic_monthly_scorecard.v1",
    }
