"""Separate historical disclosure findings from current decision evidence."""
from copy import deepcopy
from datetime import date
import re


def annotate_verification(payload, *, today=None):
    result = deepcopy(payload)
    today = today or date.today()
    current, historical, seen = [], [], set()
    for item in sorted(result.get("items") or [], key=lambda row: str(row.get("announced_at") or ""), reverse=True):
        title = re.sub(r"摘要|全文|\s", "", str(item.get("source_title") or ""))
        key = (item.get("question"), item.get("announced_at"), title, item.get("status"))
        if key in seen:
            continue
        seen.add(key)
        try:
            age = (today - date.fromisoformat(str(item.get("announced_at"))[:10])).days
        except (ValueError, TypeError):
            age = None
        fresh = age is not None and 0 <= age <= 180 and (item.get("quote_verified") is True or item.get("status") == "not_found")
        item["decision_freshness"] = "current" if fresh else "historical_or_unverified"
        item["age_days"] = age
        (current if fresh else historical).append(item)
    result["current_items"] = current
    result["historical_items"] = historical
    result["raw_counts"] = result.get("raw_counts", result.get("counts", {}))
    result["counts"] = {status: sum(i.get("status") == status for i in current)
                        for status in ("supported", "partially_supported", "contradicted", "not_found")}
    result["freshness_policy"] = "180天为当前决策证据窗口；历史事实保留备查，不单独触发当前减持或硬约束。"
    return result
