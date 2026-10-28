from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from app.collector.router import collector
from app.portfolio import portfolio_service


BACKEND_DIR = Path(__file__).resolve().parents[2]
OUTCOME_DIR = BACKEND_DIR / "data" / "agent_outcomes"
RECOMMENDATIONS_PATH = OUTCOME_DIR / "recommendations.json"
ACTIONS_PATH = OUTCOME_DIR / "portfolio_actions.json"
SNAPSHOT_CHANGES_PATH = OUTCOME_DIR / "snapshot_changes.json"
TRADE_LEDGER_PATH = BACKEND_DIR / "data" / "trade_ledger" / "transactions.json"
REVIEW_DIR = BACKEND_DIR / "data" / "agent_reviews"
IMPORT_DRAFT_DIR = BACKEND_DIR / "data" / "portfolio" / "imports"
MARKET_BENCHMARK = {"symbol": "510300", "name": "沪深300ETF"}
LOCAL_TZ = ZoneInfo("Asia/Shanghai")


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _write(path: Path, payload: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _latest_review_at(value: Any) -> dict[str, Any] | None:
    action_time = _parse_time(value)
    candidates: list[tuple[datetime, dict[str, Any]]] = []
    if not action_time:
        return None
    for path in REVIEW_DIR.glob("daily-*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        completed = _parse_time(payload.get("completed_at"))
        if completed and completed <= action_time and payload.get("status") == "completed":
            candidates.append((completed, payload))
    if not candidates:
        return None
    payload = max(candidates, key=lambda item: item[0])[1]
    review = payload.get("review", {})
    return {
        "run_id": payload.get("run_id"),
        "completed_at": payload.get("completed_at"),
        "model": payload.get("model"),
        "headline": review.get("headline"),
        "summary": review.get("summary"),
        "decision_focus": deepcopy(review.get("decision_focus", [])),
    }


def _strategy_comparison(symbol: str, action_type: str, value: Any) -> dict[str, Any]:
    action_time = _parse_time(value)
    recommendations = []
    for item in _read(RECOMMENDATIONS_PATH):
        created_at = _parse_time(item.get("created_at"))
        if (
            action_time
            and created_at
            and created_at <= action_time
            and symbol in [str(target).split(".", 1)[0] for target in item.get("target_symbols", [])]
        ):
            recommendations.append((created_at, item))
    recommendations.sort(key=lambda row: row[0], reverse=True)
    matched = recommendations[:5]
    positive_action = action_type in {"opened", "increased"}
    aligned: list[str] = []
    conflicted: list[str] = []
    frozen = []
    for _, item in matched:
        category = str(item.get("category") or "")
        recommendation_id = str(item.get("recommendation_id") or "")
        if (positive_action and category == "opportunity") or (not positive_action and category == "risk"):
            aligned.append(recommendation_id)
        elif (positive_action and category == "risk") or (not positive_action and category == "opportunity"):
            conflicted.append(recommendation_id)
        frozen.append({
            "recommendation_id": recommendation_id,
            "run_id": item.get("run_id"),
            "created_at": item.get("created_at"),
            "category": category,
            "subject": item.get("subject"),
            "conclusion": item.get("conclusion"),
            "confidence": item.get("confidence"),
            "action_semantics": (item.get("decision_snapshot") or {}).get("action_semantics"),
            "invalidation_conditions": deepcopy(
                (item.get("decision_snapshot") or {}).get("invalidation_conditions", [])
            ),
        })
    status = (
        "mixed" if aligned and conflicted
        else "aligned" if aligned
        else "conflicted" if conflicted
        else "no_direct_recommendation"
    )
    return {
        "schema_version": "action_strategy_comparison.v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "action_time": str(value or ""),
        "status": status,
        "aligned_recommendation_ids": aligned,
        "conflicted_recommendation_ids": conflicted,
        "matched_recommendations": frozen,
        "latest_review": _latest_review_at(value),
    }


def _confirmed_holdings_snapshot(snapshot: dict[str, Any]) -> bool:
    draft_id = str(snapshot.get("draft_id") or "")
    if not (
        draft_id
        and snapshot.get("confirmed_at")
        and str(snapshot.get("source_type") or "") in {
            "broker_screenshot_cloud_parsed_user_confirmed",
            "broker_screenshot_confirmed",
        }
    ):
        return False
    path = IMPORT_DRAFT_DIR / f"{draft_id}.json"
    try:
        draft = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(
        draft.get("screenshot_kind") == "current_holdings"
        and str(draft.get("saved_snapshot_id") or "") == str(snapshot.get("snapshot_id") or "")
        and draft.get("confirmed_at")
    )


def _snapshot_change_event(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    def number(payload: dict[str, Any], key: str) -> float:
        return float(payload.get(key) or 0)

    before = {
        str(item.get("symbol") or "").split(".", 1)[0]: item
        for item in previous.get("positions", [])
    }
    after = {
        str(item.get("symbol") or "").split(".", 1)[0]: item
        for item in current.get("positions", [])
    }
    position_changes = []
    for symbol in sorted(set(before) | set(after)):
        old = before.get(symbol, {})
        new = after.get(symbol, {})
        old_qty = number(old, "quantity")
        new_qty = number(new, "quantity")
        old_cost = number(old, "avg_cost")
        new_cost = number(new, "avg_cost")
        old_value = number(old, "broker_screenshot_market_value")
        new_value = number(new, "broker_screenshot_market_value")
        if (
            abs(new_qty - old_qty) < 1e-8
            and abs(new_cost - old_cost) < 1e-8
            and abs(new_value - old_value) < 0.01
        ):
            continue
        position_changes.append({
            "symbol": symbol,
            "name": new.get("name") or old.get("name"),
            "quantity_before": old_qty,
            "quantity_after": new_qty,
            "quantity_delta": round(new_qty - old_qty, 6),
            "avg_cost_before": old.get("avg_cost"),
            "avg_cost_after": new.get("avg_cost"),
            "avg_cost_delta": round(new_cost - old_cost, 6),
            "market_value_before": old.get("broker_screenshot_market_value"),
            "market_value_after": new.get("broker_screenshot_market_value"),
            "market_value_delta": round(new_value - old_value, 2),
        })
    return {
        "event_id": f"snapshot:{previous.get('snapshot_id')}:{current.get('snapshot_id')}",
        "event_type": "confirmed_holdings_screenshot_diff",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_time": current.get("snapshot_time"),
        "previous_snapshot_id": previous.get("snapshot_id"),
        "snapshot_id": current.get("snapshot_id"),
        "source_draft_id": current.get("draft_id"),
        "source_name": current.get("source_name"),
        "account_changes": {
            "total_assets_before": previous.get("total_assets"),
            "total_assets_after": current.get("total_assets"),
            "total_assets_delta": round(number(current, "total_assets") - number(previous, "total_assets"), 2),
            "cash_before": previous.get("cash_available"),
            "cash_after": current.get("cash_available"),
            "cash_delta": round(number(current, "cash_available") - number(previous, "cash_available"), 2),
            "repo_before": previous.get("repo_amount"),
            "repo_after": current.get("repo_amount"),
            "repo_delta": round(number(current, "repo_amount") - number(previous, "repo_amount"), 2),
        },
        "position_changes": position_changes,
        "user_confirmed": True,
    }


def _capture_snapshot_change_events(ordered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = _read(SNAPSHOT_CHANGES_PATH)
    existing = {str(item.get("event_id") or "") for item in records}
    created = []
    for previous, current in zip(ordered, ordered[1:]):
        if not _confirmed_holdings_snapshot(current):
            continue
        event = _snapshot_change_event(previous, current)
        if event["event_id"] in existing:
            continue
        records.append(event)
        created.append(event)
        existing.add(event["event_id"])
    if created:
        _write(SNAPSHOT_CHANGES_PATH, records)
    return created


def _collapse_symbol_format_artifacts(records: list[dict[str, Any]]) -> bool:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        if str(record.get("source") or "") not in {
            "inferred_from_portfolio_snapshots",
            "confirmed_holdings_screenshot_diff",
        }:
            continue
        parts = str(record.get("action_id") or "").split(":")
        if len(parts) != 3:
            continue
        groups.setdefault((parts[0], parts[1], parts[2].split(".", 1)[0]), []).append(record)
    changed = False
    for (_, _, compact_symbol), items in groups.items():
        if len(items) < 2:
            continue
        before = max(float(item.get("quantity_before") or 0) for item in items)
        after = max(float(item.get("quantity_after") or 0) for item in items)
        if abs(after - before) < 1e-8:
            for item in items:
                item.update({
                    "decision_status": "dismissed",
                    "user_confirmed": False,
                    "learning_eligible": False,
                    "record_quality": "symbol_format_artifact",
                    "dismissed_reason": "同一证券代码的交易所后缀格式变化，不构成真实持仓操作",
                })
            changed = True
            continue
        keeper = items[0]
        keeper.update({
            "symbol": compact_symbol,
            "quantity_before": before,
            "quantity_after": after,
            "quantity_delta": after - before,
            "action_type": (
                "opened" if before == 0 and after > 0
                else "closed" if before > 0 and after == 0
                else "increased" if after > before
                else "reduced"
            ),
        })
        keeper["ai_strategy_comparison"] = _strategy_comparison(
            compact_symbol,
            keeper["action_type"],
            keeper.get("snapshot_time"),
        )
        for item in items[1:]:
            item.update({
                "decision_status": "dismissed",
                "user_confirmed": False,
                "learning_eligible": False,
                "record_quality": "symbol_format_artifact",
                "dismissed_reason": "已合并到同一证券代码的规范化持仓变化",
            })
        changed = True
    return changed


def _action_learning_eligible(record: dict[str, Any]) -> bool:
    return bool(
        record.get("user_confirmed")
        and record.get("decision_status") != "dismissed"
    )


def confirmed_actions_on_local_date(value: str) -> list[dict[str, Any]]:
    selected = []
    for record in _read(ACTIONS_PATH):
        if not _action_learning_eligible(record):
            continue
        action_time = _parse_time(record.get("snapshot_time"))
        if action_time and action_time.astimezone(LOCAL_TZ).date().isoformat() == value:
            selected.append(record)
    return selected


def _action_local_date(record: dict[str, Any]) -> str | None:
    action_time = _parse_time(record.get("snapshot_time"))
    return action_time.astimezone(LOCAL_TZ).date().isoformat() if action_time else None


def _aggregate_weekly_actions(
    actions: list[dict[str, Any]],
    trading_dates: list[str],
) -> list[dict[str, Any]]:
    selected_dates = set(trading_dates)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in actions:
        action_date = _action_local_date(record)
        if action_date not in selected_dates or not _action_learning_eligible(record):
            continue
        symbol = str(record.get("symbol") or "").split(".", 1)[0]
        if symbol:
            grouped.setdefault(symbol, []).append(record)

    result: list[dict[str, Any]] = []
    for symbol, records in grouped.items():
        records.sort(key=lambda item: str(item.get("snapshot_time") or ""))
        buy_records = [item for item in records if float(item.get("quantity_delta") or 0) > 0]
        sell_records = [item for item in records if float(item.get("quantity_delta") or 0) < 0]
        buy_quantity = sum(float(item.get("quantity_delta") or 0) for item in buy_records)
        sell_quantity = abs(sum(float(item.get("quantity_delta") or 0) for item in sell_records))
        net_quantity = buy_quantity - sell_quantity
        signs = [
            1 if float(item.get("quantity_delta") or 0) > 0 else -1
            for item in records
            if float(item.get("quantity_delta") or 0) != 0
        ]
        reversal_count = sum(1 for previous, current in zip(signs, signs[1:]) if previous != current)
        if buy_records and sell_records:
            pattern = (
                "two_way_net_buy" if net_quantity > 0
                else "two_way_net_sell" if net_quantity < 0
                else "round_trip_flat"
            )
        else:
            pattern = "accumulation" if buy_records else "distribution"

        strategy_counts: dict[str, int] = {}
        matched_recommendations: dict[str, dict[str, Any]] = {}
        sequence = []
        for item in records:
            comparison = item.get("ai_strategy_comparison") or {}
            status = str(comparison.get("status") or "unavailable")
            strategy_counts[status] = strategy_counts.get(status, 0) + 1
            for recommendation in comparison.get("matched_recommendations", []):
                recommendation_id = str(recommendation.get("recommendation_id") or "")
                if recommendation_id:
                    matched_recommendations[recommendation_id] = recommendation
            sequence.append({
                "action_id": item.get("action_id"),
                "trading_date": _action_local_date(item),
                "action_type": item.get("action_type"),
                "quantity_delta": item.get("quantity_delta"),
                "average_price": item.get("average_price"),
                "amount": item.get("amount"),
                "strategy_status": status,
                "user_reason": item.get("user_reason"),
            })

        baseline = next((item.get("baseline") for item in records if item.get("baseline")), None)
        latest = _latest_market_point(symbol)
        market_return = None
        if baseline and latest and float(baseline.get("close") or 0):
            market_return = round(
                (float(latest["close"]) / float(baseline["close"]) - 1) * 100,
                2,
            )
        benchmark_baseline = _market_point_at(MARKET_BENCHMARK["symbol"], records[0].get("snapshot_time"))
        benchmark_latest = _latest_market_point(MARKET_BENCHMARK["symbol"])
        benchmark_return = None
        if benchmark_baseline and benchmark_latest and float(benchmark_baseline.get("close") or 0):
            benchmark_return = round(
                (float(benchmark_latest["close"]) / float(benchmark_baseline["close"]) - 1) * 100,
                2,
            )
        result.append({
            "evidence_ref": f"operation:weekly:{trading_dates[-1]}:{symbol}",
            "symbol": symbol,
            "name": records[-1].get("name") or symbol,
            "operation_count": len(records),
            "buy_count": len(buy_records),
            "sell_count": len(sell_records),
            "buy_quantity": round(buy_quantity, 4),
            "sell_quantity": round(sell_quantity, 4),
            "net_quantity": round(net_quantity, 4),
            "quantity_before": records[0].get("quantity_before"),
            "quantity_after": records[-1].get("quantity_after"),
            "pattern": pattern,
            "reversal_count": reversal_count,
            "strategy_comparison_counts": strategy_counts,
            "matched_recommendations": list(matched_recommendations.values())[:5],
            "sequence": sequence,
            "provisional_market_result": {
                "status": "provisional_not_matured_outcome",
                "baseline_date": baseline.get("date") if baseline else None,
                "latest_date": latest.get("date") if latest else None,
                "return_pct": market_return,
                "benchmark_return_pct": benchmark_return,
                "excess_return_pct": (
                    round(market_return - benchmark_return, 2)
                    if market_return is not None and benchmark_return is not None
                    else None
                ),
                "notice": "仅用于周内临时反思，不替代20个交易日到期评价。",
            },
        })
    return sorted(result, key=lambda item: (-item["operation_count"], item["symbol"]))


def build_weekly_operation_summary(reference_time: datetime | None = None) -> dict[str, Any]:
    reference = reference_time or datetime.now(LOCAL_TZ)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=LOCAL_TZ)
    reference_date = reference.astimezone(LOCAL_TZ).date().isoformat()
    actions = _read(ACTIONS_PATH)
    _migrate_action_records(actions)
    action_dates = {
        value for item in actions
        if (value := _action_local_date(item)) and value <= reference_date and _action_learning_eligible(item)
    }
    try:
        benchmark = collector.get_history(MARKET_BENCHMARK["symbol"], limit=60).copy()
        market_dates = {
            value.date().isoformat()
            for value in pd.to_datetime(benchmark.get("date"), errors="coerce").dropna()
            if value.date().isoformat() <= reference_date
        }
    except Exception:
        market_dates = set()
    trading_dates = sorted(market_dates | action_dates)[-5:]
    if not trading_dates:
        trading_dates = [value.date().isoformat() for value in pd.bdate_range(end=reference_date, periods=5)]
    items = _aggregate_weekly_actions(actions, trading_dates)
    return {
        "contract_version": "weekly_operation_summary.v1",
        "window_type": "rolling_five_trading_days",
        "window_start": trading_dates[0],
        "window_end": trading_dates[-1],
        "records_checked_through": reference_date,
        "market_history_through": max(market_dates) if market_dates else None,
        "window_is_market_limited": trading_dates[-1] < reference_date,
        "trading_dates": trading_dates,
        "action_count": sum(item["operation_count"] for item in items),
        "symbol_count": len(items),
        "items": items,
        "method": "confirmed_actions_grouped_by_symbol.v1",
        "boundary": "周内收益为临时反馈；操作成败仍以到期评价、执行理由和风险控制共同判断。",
    }


def _migrate_action_records(records: list[dict[str, Any]]) -> bool:
    changed = False
    for record in records:
        confirmed = bool(record.get("user_confirmed"))
        source = str(record.get("source") or "")
        desired_status = (
            "dismissed" if record.get("decision_status") == "dismissed"
            else "confirmed" if confirmed
            else "candidate"
        )
        desired_quality = (
            "symbol_format_artifact" if record.get("record_quality") == "symbol_format_artifact"
            else "confirmed_transaction" if source == "confirmed_trade_ledger"
            else "user_confirmed_snapshot_change" if confirmed
            else "inferred_snapshot_change"
        )
        learning_eligible = confirmed and desired_status != "dismissed"
        if not learning_eligible and record.get("outcome"):
            record["excluded_outcome"] = record["outcome"]
            record["outcome"] = None
            record["evaluated_at"] = None
            changed = True
        for key, value in (
            ("decision_status", desired_status),
            ("record_quality", desired_quality),
            ("learning_eligible", learning_eligible),
        ):
            if record.get(key) != value:
                record[key] = value
                changed = True
    return changed


def _symbols_for_refs(refs: list[str], evidence_catalog: list[dict[str, Any]]) -> list[str]:
    by_ref = {str(item.get("evidence_ref")): item for item in evidence_catalog}
    symbols: list[str] = []
    for ref in refs:
        item = by_ref.get(ref, {})
        facts = item.get("facts", {})
        candidates = [
            facts.get("symbol"),
            facts.get("selected_symbol"),
            facts.get("primary_symbol"),
        ]
        candidates.extend(component.get("symbol") for component in facts.get("proxy_components", []))
        for symbol in candidates:
            clean = str(symbol or "").strip()
            if len(clean) == 6 and clean.isdigit() and clean not in symbols:
                symbols.append(clean)
    return symbols[:5]


def _referenced_evidence(
    refs: list[str],
    evidence_catalog: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    wanted = set(refs)
    return [
        deepcopy(item)
        for item in evidence_catalog
        if str(item.get("evidence_ref")) in wanted
    ]


def _lifecycle_event(state: str, at: str, reason: str) -> dict[str, str]:
    return {"state": state, "at": at, "reason": reason}


def _ensure_lifecycle(record: dict[str, Any]) -> None:
    created_at = str(record.get("created_at") or datetime.now(timezone.utc).isoformat())
    status = str(record.get("status") or "tracking")
    if not record.get("lifecycle"):
        history = [_lifecycle_event("proposed", created_at, "AI 复盘形成结构化建议")]
        history.append(_lifecycle_event(status, created_at, "进入结果观察期"))
        if record.get("outcome"):
            evaluated_at = str(record.get("evaluated_at") or created_at)
            history.append(_lifecycle_event("evaluated", evaluated_at, "达到观察周期并完成规则评价"))
        record["lifecycle"] = {"state": "evaluated" if record.get("outcome") else status, "history": history}


def _ensure_legacy_snapshot(record: dict[str, Any]) -> None:
    if record.get("decision_snapshot"):
        return
    record["decision_snapshot"] = {
        "schema_version": "decision_snapshot.v1",
        "snapshot_status": "unavailable_legacy",
        "captured_at": record.get("created_at"),
        "run_id": record.get("run_id"),
        "provider": None,
        "model": None,
        "contract_version": None,
        "prompt_version": None,
        "action_semantics": None,
        "invalidation_conditions": [],
        "evidence": [],
        "notice": "历史版本未保存证据正文，不能使用当前数据回填当时证据。",
    }


def _transition(record: dict[str, Any], state: str, at: str, reason: str) -> None:
    _ensure_lifecycle(record)
    lifecycle = record["lifecycle"]
    if lifecycle.get("state") == state:
        return
    lifecycle["state"] = state
    lifecycle.setdefault("history", []).append(_lifecycle_event(state, at, reason))


def _latest_market_point(symbol: str) -> dict[str, Any] | None:
    try:
        frame = collector.get_history(symbol, limit=5000).copy()
    except Exception:
        return None
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["date", "close"]).sort_values("date")
    if frame.empty:
        return None
    row = frame.iloc[-1]
    return {"date": row["date"].date().isoformat(), "close": round(float(row["close"]), 4)}


def _market_point_at(symbol: str, value: str | None) -> dict[str, Any] | None:
    if not value:
        return _latest_market_point(symbol)
    try:
        frame = collector.get_history(symbol, limit=5000).copy()
    except Exception:
        return None
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["date", "close"]).sort_values("date")
    target = pd.to_datetime(value, utc=True).tz_convert(None).date()
    rows = frame[frame["date"].dt.date >= target]
    if rows.empty:
        return None
    row = rows.iloc[0]
    return {"date": row["date"].date().isoformat(), "close": round(float(row["close"]), 4)}


def register_review_outcomes(review_run: dict[str, Any], model_input: dict[str, Any]) -> list[dict[str, Any]]:
    records = _read(RECOMMENDATIONS_PATH)
    existing = {record.get("recommendation_id") for record in records}
    run_id = str(review_run.get("run_id") or "")
    created_at = review_run.get("completed_at") or datetime.now(timezone.utc).isoformat()
    evidence_catalog = model_input.get("evidence_catalog", [])
    review = review_run.get("review", {})
    new_records: list[dict[str, Any]] = []
    for category, horizon in (("opportunity", 20), ("risk", 20), ("watch", 10)):
        key = {"opportunity": "opportunities", "risk": "risks", "watch": "watch_items"}[category]
        for item in review.get(key, []):
            recommendation_id = f"{run_id}:{item.get('item_id')}"
            if recommendation_id in existing:
                continue
            symbols = _symbols_for_refs(
                [*item.get("evidence_refs", []), *item.get("counter_evidence_refs", [])],
                evidence_catalog,
            )
            baselines = {
                symbol: point
                for symbol in symbols
                if (point := _latest_market_point(symbol))
            }
            all_refs = [*item.get("evidence_refs", []), *item.get("counter_evidence_refs", [])]
            benchmark_point = _latest_market_point(MARKET_BENCHMARK["symbol"])
            initial_state = "open" if baselines and category != "watch" else "tracking"
            record = {
                "recommendation_id": recommendation_id,
                "run_id": run_id,
                "category": category,
                "subject": item.get("subject"),
                "conclusion": item.get("conclusion"),
                "confidence": item.get("confidence"),
                "evidence_refs": item.get("evidence_refs", []),
                "counter_evidence_refs": item.get("counter_evidence_refs", []),
                "target_symbols": symbols,
                "baselines": baselines,
                "benchmark": {
                    **MARKET_BENCHMARK,
                    "baseline": benchmark_point,
                },
                "horizon_trading_days": horizon,
                "status": initial_state,
                "outcome": None,
                "created_at": created_at,
                "due_after": (
                    datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                    + timedelta(days=round(horizon * 1.6))
                ).isoformat(),
                "evaluated_at": None,
                "decision_snapshot": {
                    "schema_version": "decision_snapshot.v1",
                    "snapshot_status": "frozen",
                    "captured_at": created_at,
                    "run_id": run_id,
                    "provider": review_run.get("provider"),
                    "model": review_run.get("model"),
                    "contract_version": review_run.get("contract_version"),
                    "prompt_version": review_run.get("prompt_version"),
                    "action_semantics": item.get("action_semantics"),
                    "invalidation_conditions": item.get("invalidation_conditions", []),
                    "evidence": _referenced_evidence(all_refs, evidence_catalog),
                },
                "lifecycle": {
                    "state": initial_state,
                    "history": [
                        _lifecycle_event("proposed", created_at, "AI 复盘形成结构化建议"),
                        _lifecycle_event(initial_state, created_at, "进入结果观察期"),
                    ],
                },
            }
            records.append(record)
            new_records.append(record)
    _write(RECOMMENDATIONS_PATH, records)
    return new_records


def _future_return(symbol: str, baseline: dict[str, Any], horizon: int) -> dict[str, Any] | None:
    try:
        frame = collector.get_history(symbol, limit=5000).copy()
    except Exception:
        return None
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    baseline_date = pd.to_datetime(baseline["date"]).date()
    candidates = frame.index[frame["date"].dt.date >= baseline_date].tolist()
    if not candidates:
        return None
    start = candidates[0]
    end = start + horizon
    if end >= len(frame):
        return None
    start_close = float(frame.loc[start, "close"])
    end_close = float(frame.loc[end, "close"])
    period = frame.loc[start:end, "close"]
    relative_path = period / start_close - 1
    peak_index = int(relative_path.idxmax())
    trough_index = int(relative_path.idxmin())
    return {
        "baseline_date": frame.loc[start, "date"].date().isoformat(),
        "evaluation_date": frame.loc[end, "date"].date().isoformat(),
        "baseline_close": round(start_close, 4),
        "evaluation_close": round(end_close, 4),
        "return_pct": round((end_close / start_close - 1) * 100, 2),
        "max_drawdown_pct": round(float((period / period.cummax() - 1).min()) * 100, 2),
        "max_runup_pct": round(float(relative_path.max()) * 100, 2),
        "max_adverse_move_pct": round(float(relative_path.min()) * 100, 2),
        "days_to_peak": peak_index - start,
        "days_to_trough": trough_index - start,
    }


def _reason_categories(
    *,
    verdict: str,
    average_return: float,
    excess_return: float | None,
    worst_drawdown: float,
) -> list[str]:
    categories: list[str] = []
    if excess_return is not None and abs(excess_return) >= 3:
        categories.append("direction_judgment")
    if verdict == "mixed":
        categories.append("timing_or_threshold")
    if verdict == "not_supported" and worst_drawdown <= -7:
        categories.append("risk_omission")
    if abs(average_return) < 3 and (excess_return is None or abs(excess_return) < 3):
        categories.append("signal_not_realized")
    return categories or ["market_follow_through"]


def _decision_quality(
    *,
    category: str,
    verdict: str,
    average_return: float,
    excess_return: float | None,
    worst_drawdown: float,
    max_runup: float,
) -> dict[str, Any]:
    direction_correct = verdict == "supported"
    meaningful_move = max(abs(average_return), abs(excess_return or 0), abs(worst_drawdown), abs(max_runup)) >= 3
    if verdict == "mixed" and meaningful_move:
        assessment = "direction_partly_right_timing_unclear"
    elif verdict == "mixed":
        assessment = "signal_not_realized"
    elif verdict == "supported" and category == "risk":
        assessment = "risk_warning_effective"
    elif verdict == "supported":
        assessment = "direction_and_follow_through_supported"
    elif category == "risk":
        assessment = "risk_warning_not_realized"
    else:
        assessment = "opportunity_thesis_not_supported"
    return {
        "assessment": assessment,
        "direction_accuracy": "supported" if direction_correct else "partial" if verdict == "mixed" else "not_supported",
        "timing_quality": (
            "adverse_path" if category == "opportunity" and worst_drawdown <= -7
            else "late_or_early" if verdict == "mixed" and meaningful_move
            else "acceptable"
        ),
        "risk_control_value": (
            "high" if category == "risk" and worst_drawdown <= -7
            else "medium" if category == "risk" and worst_drawdown <= -3
            else "not_applicable" if category != "risk"
            else "low"
        ),
        "thesis_validity": "unverified",
        "assessment_boundary": "仅评价后续价格路径；收益不能证明或否定基本面逻辑及因果关系。",
    }


def evaluate_recommendations() -> list[dict[str, Any]]:
    records = _read(RECOMMENDATIONS_PATH)
    changed: list[dict[str, Any]] = []
    for record in records:
        _ensure_lifecycle(record)
        if record.get("category") == "watch":
            continue
        current_method = (record.get("outcome") or {}).get("method")
        if record.get("outcome") is not None and current_method == "deterministic_market_outcome.v3":
            continue
        results = {
            symbol: result
            for symbol, baseline in record.get("baselines", {}).items()
            if (result := _future_return(symbol, baseline, int(record.get("horizon_trading_days") or 20)))
        }
        if not results:
            continue
        benchmark = record.get("benchmark") or {
            **MARKET_BENCHMARK,
            "baseline": _market_point_at(MARKET_BENCHMARK["symbol"], record.get("created_at")),
        }
        record["benchmark"] = benchmark
        benchmark_result = (
            _future_return(
                str(benchmark.get("symbol") or MARKET_BENCHMARK["symbol"]),
                benchmark["baseline"],
                int(record.get("horizon_trading_days") or 20),
            )
            if benchmark.get("baseline")
            else None
        )
        returns = [item["return_pct"] for item in results.values()]
        drawdowns = [item["max_drawdown_pct"] for item in results.values()]
        runups = [item["max_runup_pct"] for item in results.values()]
        average_return = round(sum(returns) / len(returns), 2)
        benchmark_return = benchmark_result["return_pct"] if benchmark_result else None
        excess_return = round(average_return - benchmark_return, 2) if benchmark_return is not None else None
        worst_drawdown = min(drawdowns)
        max_runup = max(runups)
        category = record.get("category")
        if category == "opportunity":
            verdict = (
                "supported" if average_return >= 5 or (excess_return is not None and excess_return >= 3)
                else "not_supported" if average_return <= -3 and (excess_return is None or excess_return <= -2)
                else "mixed"
            )
        else:
            verdict = (
                "supported" if worst_drawdown <= -7 or average_return <= -5 or (excess_return is not None and excess_return <= -3)
                else "not_supported" if average_return >= 5 and (excess_return is None or excess_return >= 2)
                else "mixed"
            )
        benchmark_text = f"，相对沪深300超额 {excess_return}%" if excess_return is not None else "，基准数据不足"
        reason = f"观察期平均收益 {average_return}%，最大回撤 {worst_drawdown}%{benchmark_text}。"
        evaluated_at = datetime.now(timezone.utc).isoformat()
        record["status"] = "evaluated"
        record["outcome"] = {
            "verdict": verdict,
            "reason": reason,
            "symbol_results": results,
            "benchmark_result": benchmark_result,
            "average_return_pct": average_return,
            "excess_return_pct": excess_return,
            "reason_categories": _reason_categories(
                verdict=verdict,
                average_return=average_return,
                excess_return=excess_return,
                worst_drawdown=worst_drawdown,
            ),
            "decision_quality": _decision_quality(
                category=str(category),
                verdict=verdict,
                average_return=average_return,
                excess_return=excess_return,
                worst_drawdown=worst_drawdown,
                max_runup=max_runup,
            ),
            "method": "deterministic_market_outcome.v3",
        }
        record["evaluated_at"] = evaluated_at
        _transition(record, "evaluated", evaluated_at, "达到观察周期并完成基准化规则评价")
        changed.append(record)
    _write(RECOMMENDATIONS_PATH, records)
    return changed


def _confirmed_trade_actions(
    *,
    existing_ids: set[str],
    snapshots_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], set[str]]:
    batches = _read(TRADE_LEDGER_PATH)
    created: list[dict[str, Any]] = []
    resulting_snapshot_ids: set[str] = set()
    for batch in batches:
        snapshot_id = str(batch.get("resulting_snapshot_id") or "")
        if snapshot_id:
            resulting_snapshot_ids.add(snapshot_id)
        resulting_snapshot = snapshots_by_id.get(snapshot_id, {})
        after_positions = {
            str(item.get("symbol") or "").split(".", 1)[0]: item
            for item in resulting_snapshot.get("positions", [])
        }
        for transaction in batch.get("transactions", []):
            action_id = str(transaction.get("transaction_id") or "")
            if not action_id or action_id in existing_ids:
                continue
            symbol = str(transaction.get("symbol") or "").split(".", 1)[0]
            quantity = float(transaction.get("quantity") or 0)
            side = str(transaction.get("side") or "")
            after_quantity = (
                float(after_positions.get(symbol, {}).get("quantity") or 0)
                if resulting_snapshot
                else None
            )
            before_quantity = (
                after_quantity - quantity if side == "buy" and after_quantity is not None
                else after_quantity + quantity if side == "sell" and after_quantity is not None
                else None
            )
            occurred_at = transaction.get("occurred_at") or transaction.get("confirmed_at") or batch.get("confirmed_at")
            action_type = (
                "opened" if side == "buy" and before_quantity == 0
                else "closed" if side == "sell" and after_quantity == 0
                else "increased" if side == "buy"
                else "reduced"
            )
            created.append({
                "action_id": action_id,
                "symbol": symbol,
                "name": transaction.get("name"),
                "action_type": action_type,
                "quantity_before": before_quantity,
                "quantity_after": after_quantity,
                "quantity_delta": quantity if side == "buy" else -quantity,
                "average_price": transaction.get("average_price"),
                "amount": transaction.get("amount"),
                "snapshot_time": occurred_at,
                "source": "confirmed_trade_ledger",
                "source_batch_id": batch.get("batch_id"),
                "user_confirmed": True,
                "user_reason": batch.get("user_reason"),
                "decision_status": "confirmed",
                "record_quality": "confirmed_transaction",
                "learning_eligible": True,
                "baseline": _market_point_at(symbol, occurred_at),
                "horizon_trading_days": 20,
                "outcome": None,
                "ai_strategy_comparison": _strategy_comparison(symbol, action_type, occurred_at),
            })
    return created, resulting_snapshot_ids


def capture_portfolio_actions() -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for path in portfolio_service.snapshots_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            snapshots.append(payload)
        except (OSError, json.JSONDecodeError):
            continue
    current = json.loads(portfolio_service.portfolio_path.read_text(encoding="utf-8"))
    snapshots.append(current)
    unique = {item.get("snapshot_id"): item for item in snapshots if item.get("snapshot_id")}
    ordered = sorted(unique.values(), key=lambda item: item.get("snapshot_time") or "")
    snapshots_by_id = {
        str(item.get("snapshot_id")): item
        for item in ordered
        if item.get("snapshot_id")
    }
    records = _read(ACTIONS_PATH)
    _collapse_symbol_format_artifacts(records)
    _migrate_action_records(records)
    existing = {record.get("action_id") for record in records}
    records_by_id = {
        str(record.get("action_id")): record
        for record in records
        if record.get("action_id")
    }
    created: list[dict[str, Any]] = []
    confirmed_trades, trade_snapshot_ids = _confirmed_trade_actions(
        existing_ids={str(value) for value in existing if value},
        snapshots_by_id=snapshots_by_id,
    )
    records.extend(confirmed_trades)
    created.extend(confirmed_trades)
    existing.update(item["action_id"] for item in confirmed_trades)
    _capture_snapshot_change_events(ordered)
    for previous, current in zip(ordered, ordered[1:]):
        if str(current.get("snapshot_id") or "") in trade_snapshot_ids:
            continue
        before = {
            str(item.get("symbol") or "").split(".", 1)[0]: item
            for item in previous.get("positions", [])
        }
        after = {
            str(item.get("symbol") or "").split(".", 1)[0]: item
            for item in current.get("positions", [])
        }
        for symbol in sorted(set(before) | set(after)):
            old_qty = float(before.get(symbol, {}).get("quantity") or 0)
            new_qty = float(after.get(symbol, {}).get("quantity") or 0)
            if abs(new_qty - old_qty) < 1e-8:
                continue
            action_id = f"{previous.get('snapshot_id')}:{current.get('snapshot_id')}:{symbol}"
            confirmed_snapshot = _confirmed_holdings_snapshot(current)
            if action_id in existing:
                existing_record = records_by_id.get(action_id)
                if existing_record and confirmed_snapshot and not existing_record.get("user_confirmed"):
                    existing_record.update({
                        "source": "confirmed_holdings_screenshot_diff",
                        "source_draft_id": current.get("draft_id"),
                        "user_confirmed": True,
                        "decision_status": "confirmed",
                        "record_quality": "user_confirmed_snapshot_change",
                        "learning_eligible": True,
                    })
                    if not existing_record.get("ai_strategy_comparison"):
                        existing_record["ai_strategy_comparison"] = _strategy_comparison(
                            symbol,
                            str(existing_record.get("action_type") or ""),
                            current.get("snapshot_time"),
                        )
                continue
            action_type = (
                "opened" if old_qty == 0 and new_qty > 0
                else "closed" if old_qty > 0 and new_qty == 0
                else "increased" if new_qty > old_qty
                else "reduced"
            )
            point = _market_point_at(symbol, current.get("snapshot_time"))
            record = {
                "action_id": action_id,
                "symbol": symbol,
                "name": after.get(symbol, before.get(symbol, {})).get("name"),
                "action_type": action_type,
                "quantity_before": old_qty,
                "quantity_after": new_qty,
                "quantity_delta": new_qty - old_qty,
                "snapshot_time": current.get("snapshot_time"),
                "source": (
                    "confirmed_holdings_screenshot_diff"
                    if confirmed_snapshot
                    else "inferred_from_portfolio_snapshots"
                ),
                "source_draft_id": current.get("draft_id"),
                "user_confirmed": confirmed_snapshot,
                "user_reason": None,
                "decision_status": "confirmed" if confirmed_snapshot else "candidate",
                "record_quality": (
                    "user_confirmed_snapshot_change"
                    if confirmed_snapshot
                    else "inferred_snapshot_change"
                ),
                "learning_eligible": confirmed_snapshot,
                "baseline": point,
                "horizon_trading_days": 20,
                "outcome": None,
                "ai_strategy_comparison": _strategy_comparison(
                    symbol,
                    action_type,
                    current.get("snapshot_time"),
                ),
            }
            records.append(record)
            created.append(record)
    _write(ACTIONS_PATH, records)
    return created


def _strategy_fit(record: dict[str, Any], verdict: str) -> str:
    comparison = record.get("ai_strategy_comparison") or {}
    status = comparison.get("status")
    successful = verdict == "supported"
    if status == "aligned":
        return "aligned_and_supported" if successful else "aligned_but_not_supported"
    if status == "conflicted":
        return "contrarian_supported" if successful else "conflict_warning_validated"
    if status == "mixed":
        return "mixed_strategy_context"
    return "no_direct_recommendation"


def _action_attribution(
    record: dict[str, Any],
    *,
    result: dict[str, Any],
    excess_return: float | None,
    verdict: str,
) -> dict[str, Any]:
    quantity_delta = float(record.get("quantity_delta") or 0)
    quantity = abs(quantity_delta)
    baseline_price = float(result.get("baseline_close") or (record.get("baseline") or {}).get("close") or 0)
    evaluation_price = float(result.get("evaluation_close") or 0)
    direction = 1 if quantity_delta > 0 else -1
    gross_notional = round(quantity * baseline_price, 2) if quantity and baseline_price else None
    signed_pnl = (
        round(direction * quantity * (evaluation_price - baseline_price), 2)
        if quantity and baseline_price and evaluation_price
        else None
    )
    benchmark_adjusted_pnl = (
        round(direction * gross_notional * excess_return / 100, 2)
        if gross_notional is not None and excess_return is not None
        else None
    )
    before = float(record.get("quantity_before") or 0)
    quantity_change_pct = round(quantity_delta / before * 100, 2) if before else None
    if direction > 0:
        path_interpretation = (
            "added_risk_then_adverse_move"
            if float(result.get("max_adverse_move_pct") or 0) <= -7
            else "added_risk_with_follow_through"
            if float(result.get("max_runup_pct") or 0) >= 5
            else "added_risk_without_clear_follow_through"
        )
    else:
        path_interpretation = (
            "risk_reduction_avoided_decline"
            if float(result.get("return_pct") or 0) <= -3
            else "risk_reduction_missed_subsequent_gain"
            if float(result.get("return_pct") or 0) >= 3
            else "risk_reduction_neutral_afterward"
        )
    return {
        "contract_version": "action_attribution.v1",
        "direction_effect": "positive" if signed_pnl is not None and signed_pnl > 0 else "negative" if signed_pnl is not None and signed_pnl < 0 else "neutral_or_unknown",
        "estimated_position_effect_pnl": signed_pnl,
        "estimated_benchmark_adjusted_pnl": benchmark_adjusted_pnl,
        "gross_notional_at_baseline": gross_notional,
        "quantity_change_pct": quantity_change_pct,
        "path_interpretation": path_interpretation,
        "max_adverse_move_pct": result.get("max_adverse_move_pct"),
        "max_runup_pct": result.get("max_runup_pct"),
        "reason_capture": "recorded" if record.get("user_reason") else "missing",
        "strategy_fit": _strategy_fit(record, verdict),
        "transaction_cost": {
            "status": "unavailable",
            "estimated_fee": None,
            "notice": "未取得可靠佣金、印花税与滑点数据，不计入估算盈亏。",
        },
        "boundary": "仓位贡献按基准日收盘价与评价日收盘价估算，不等同于券商已实现盈亏。",
    }


def evaluate_portfolio_actions() -> list[dict[str, Any]]:
    records = _read(ACTIONS_PATH)
    _migrate_action_records(records)
    changed: list[dict[str, Any]] = []
    for record in records:
        current_method = (record.get("outcome") or {}).get("method")
        if (
            not _action_learning_eligible(record)
            or (record.get("outcome") and current_method == "deterministic_position_action.v4")
            or not record.get("baseline")
        ):
            continue
        result = _future_return(
            record["symbol"],
            record["baseline"],
            int(record.get("horizon_trading_days") or 20),
        )
        if not result:
            continue
        benchmark_baseline = record.get("benchmark_baseline") or _market_point_at(
            MARKET_BENCHMARK["symbol"],
            record.get("snapshot_time"),
        )
        record["benchmark_baseline"] = benchmark_baseline
        benchmark_result = (
            _future_return(MARKET_BENCHMARK["symbol"], benchmark_baseline, int(record.get("horizon_trading_days") or 20))
            if benchmark_baseline
            else None
        )
        positive_action = record.get("action_type") in {"opened", "increased"}
        value = result["return_pct"]
        benchmark_return = benchmark_result["return_pct"] if benchmark_result else None
        excess_return = round(value - benchmark_return, 2) if benchmark_return is not None else None
        verdict = (
            "supported" if (
                value >= 3 or (excess_return is not None and excess_return >= 2)
                if positive_action
                else value <= -3 or (excess_return is not None and excess_return <= -2)
            )
            else "not_supported" if (
                value <= -3 and (excess_return is None or excess_return <= -2)
                if positive_action
                else value >= 3 and (excess_return is None or excess_return >= 2)
            )
            else "mixed"
        )
        benchmark_text = f"，相对沪深300超额 {excess_return}%" if excess_return is not None else "，基准数据不足"
        record["outcome"] = {
            "verdict": verdict,
            "reason": (
                f"调仓后20个交易日收益 {value}%；"
                f"{'开仓/增持' if positive_action else '减持/清仓'}按绝对收益与相对收益共同评价{benchmark_text}。"
            ),
            "market_result": result,
            "benchmark_result": benchmark_result,
            "excess_return_pct": excess_return,
            "reason_categories": _reason_categories(
                verdict=verdict,
                average_return=value,
                excess_return=excess_return,
                worst_drawdown=result["max_drawdown_pct"],
            ),
            "decision_quality": _decision_quality(
                category="opportunity" if positive_action else "risk",
                verdict=verdict,
                average_return=value,
                excess_return=excess_return,
                worst_drawdown=result["max_drawdown_pct"],
                max_runup=result["max_runup_pct"],
            ),
            "method": "deterministic_position_action.v4",
            "strategy_fit": _strategy_fit(record, verdict),
            "attribution": _action_attribution(
                record,
                result=result,
                excess_return=excess_return,
                verdict=verdict,
            ),
        }
        record["evaluated_at"] = datetime.now(timezone.utc).isoformat()
        changed.append(record)
    _write(ACTIONS_PATH, records)
    return changed


def list_outcomes() -> dict[str, Any]:
    recommendation_records = _read(RECOMMENDATIONS_PATH)
    migrated = False
    for record in recommendation_records:
        if not record.get("lifecycle"):
            _ensure_lifecycle(record)
            migrated = True
        if not record.get("decision_snapshot"):
            _ensure_legacy_snapshot(record)
            migrated = True
    if migrated:
        _write(RECOMMENDATIONS_PATH, recommendation_records)
    recommendations = list(reversed(recommendation_records))
    action_records = _read(ACTIONS_PATH)
    if _migrate_action_records(action_records):
        _write(ACTIONS_PATH, action_records)
    actions = list(reversed([
        item for item in action_records
        if item.get("decision_status") != "dismissed"
    ]))
    eligible_actions = [item for item in action_records if _action_learning_eligible(item)]
    snapshot_changes = list(reversed(_read(SNAPSHOT_CHANGES_PATH)))
    comparison_count = sum(
        1 for item in eligible_actions
        if (item.get("ai_strategy_comparison") or {}).get("status")
    )
    direct_comparison_count = sum(
        1 for item in eligible_actions
        if (item.get("ai_strategy_comparison") or {}).get("status")
        not in {None, "no_direct_recommendation"}
    )
    evaluated_action_count = sum(1 for item in eligible_actions if item.get("outcome"))
    return {
        "recommendations": recommendations,
        "portfolio_actions": actions,
        "snapshot_changes": snapshot_changes,
        "weekly_operations": build_weekly_operation_summary(),
        "summary": {
            "recommendation_count": len(recommendations),
            "recommendation_evaluated": sum(1 for item in recommendations if item.get("outcome")),
            "action_count": len(eligible_actions),
            "action_evaluated": evaluated_action_count,
            "action_candidates": sum(1 for item in action_records if item.get("decision_status") == "candidate"),
            "action_dismissed": sum(1 for item in action_records if item.get("decision_status") == "dismissed"),
            "snapshot_change_count": len(snapshot_changes),
            "action_strategy_compared": comparison_count,
            "action_direct_strategy_compared": direct_comparison_count,
        },
        "loop_health": {
            "operation_capture_rate_pct": 100.0 if eligible_actions or snapshot_changes else None,
            "strategy_context_coverage_pct": (
                round(comparison_count / len(eligible_actions) * 100, 1)
                if eligible_actions else None
            ),
            "direct_strategy_match_rate_pct": (
                round(direct_comparison_count / len(eligible_actions) * 100, 1)
                if eligible_actions else None
            ),
            "matured_evaluation_rate_pct": (
                round(evaluated_action_count / len(eligible_actions) * 100, 1)
                if eligible_actions else None
            ),
            "notice": "未到观察周期的操作不计为评价失败。",
        },
    }


def annotate_portfolio_action(
    action_id: str,
    *,
    confirmed: bool,
    reason: str | None,
    dismissed: bool = False,
) -> dict[str, Any]:
    records = _read(ACTIONS_PATH)
    for record in records:
        if record.get("action_id") == action_id:
            record["user_confirmed"] = confirmed and not dismissed
            record["user_reason"] = (reason or "").strip() or None
            record["decision_status"] = "dismissed" if dismissed else "confirmed" if confirmed else "candidate"
            record["learning_eligible"] = confirmed and not dismissed
            if dismissed and record.get("outcome"):
                record["excluded_outcome"] = record["outcome"]
                record["outcome"] = None
                record["evaluated_at"] = None
            _write(ACTIONS_PATH, records)
            return record
    raise KeyError("调仓记录不存在")


def current_account_record_status() -> dict[str, Any]:
    """Read saved structure separately from confirmed fills; never infer execution prices."""
    current = portfolio_service.load_snapshot().model_dump(mode="json")
    current_time = _parse_time(current.get("snapshot_time"))
    previous = []
    for path in portfolio_service.snapshots_dir.glob("*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
            at = _parse_time(row.get("snapshot_time"))
            if row.get("snapshot_id") != current.get("snapshot_id") and at and current_time and at < current_time:
                previous.append((at, row))
        except (OSError, ValueError, TypeError):
            continue
    change = None
    if previous:
        before = max(previous, key=lambda pair: pair[0])[1]
        change = _snapshot_change_event(before, current)
        change.update(event_type="saved_account_snapshot_diff", user_confirmed=False, recorded_at=current.get("snapshot_time"),
                      boundary="仅为两次保存间的净持仓变化，非逐笔成交；实际日期、成交价和原因未确认。")
    return {
        "snapshot_id": current.get("snapshot_id"),
        "holdings_updated_at": current_time.astimezone(LOCAL_TZ).isoformat() if current_time else None,
        "holdings_source": current.get("source_type"),
        "latest_saved_change": change,
        "boundary": "当前持仓以此快照为准。交易台账仅含已登记操作，空记录不代表没有交易；行情截止日不代表持仓或台账更新时间。",
    }


def build_learning_feedback(*, recent_limit: int = 8) -> dict[str, Any]:
    from app.agent_review.learning_policy import learning_policy_snapshot

    recommendations = [
        item for item in _read(RECOMMENDATIONS_PATH)
        if item.get("outcome")
    ]
    action_records = _read(ACTIONS_PATH)
    _migrate_action_records(action_records)
    actions = [
        item for item in action_records
        if _action_learning_eligible(item) and item.get("outcome")
    ]
    confirmed_actions = [
        item for item in action_records
        if _action_learning_eligible(item)
    ]
    evaluated = [*recommendations, *actions]
    verdict_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    for item in evaluated:
        outcome = item.get("outcome") or {}
        verdict = str(outcome.get("verdict") or "unknown")
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
        for reason in outcome.get("reason_categories", []):
            key = str(reason)
            reason_counts[key] = reason_counts.get(key, 0) + 1
    recent_failures = sorted(
        [
            item for item in evaluated
            if (item.get("outcome") or {}).get("verdict") in {"not_supported", "mixed"}
        ],
        key=lambda item: str(item.get("evaluated_at") or ""),
        reverse=True,
    )[:recent_limit]
    recent_successes = sorted(
        [
            item for item in evaluated
            if (item.get("outcome") or {}).get("verdict") == "supported"
        ],
        key=lambda item: str(item.get("evaluated_at") or ""),
        reverse=True,
    )[: max(2, recent_limit // 2)]

    def compact(item: dict[str, Any]) -> dict[str, Any]:
        outcome = item.get("outcome") or {}
        is_action = not item.get("recommendation_id")
        reason_recorded = bool(item.get("user_reason")) if is_action else True
        return {
            "kind": "recommendation" if not is_action else "confirmed_action",
            "subject": item.get("subject") or item.get("name") or item.get("symbol"),
            "category": item.get("category") or item.get("action_type"),
            "original_judgment": item.get("conclusion") or item.get("user_reason"),
            "verdict": outcome.get("verdict"),
            "assessment": (outcome.get("decision_quality") or {}).get("assessment"),
            "reason_categories": outcome.get("reason_categories", []),
            "return_pct": outcome.get("average_return_pct")
            if item.get("recommendation_id")
            else (outcome.get("market_result") or {}).get("return_pct"),
            "excess_return_pct": outcome.get("excess_return_pct"),
            "attribution": outcome.get("attribution"),
            "learning_confidence": "normal" if reason_recorded else "low",
            "learning_confidence_reason": None if reason_recorded else "用户未记录操作理由，无法核验当时意图",
        }

    total = len(evaluated)
    supported = verdict_counts.get("supported", 0)
    strategy_counts: dict[str, int] = {}
    for item in confirmed_actions:
        status = str((item.get("ai_strategy_comparison") or {}).get("status") or "unavailable")
        strategy_counts[status] = strategy_counts.get(status, 0) + 1
    recent_action_comparisons = [
        {
            "symbol": item.get("symbol"),
            "name": item.get("name"),
            "action_type": item.get("action_type"),
            "action_time": item.get("snapshot_time"),
            "strategy_status": (item.get("ai_strategy_comparison") or {}).get("status"),
            "matched_recommendations": (
                item.get("ai_strategy_comparison") or {}
            ).get("matched_recommendations", [])[:3],
            "outcome_verdict": (item.get("outcome") or {}).get("verdict"),
            "strategy_fit": (item.get("outcome") or {}).get("strategy_fit"),
            "learning_confidence": "normal" if item.get("user_reason") else "low",
        }
        for item in sorted(
            confirmed_actions,
            key=lambda row: str(row.get("snapshot_time") or ""),
            reverse=True,
        )[:recent_limit]
    ]
    weekly_operations = build_weekly_operation_summary()
    return {
        "contract_version": "agent_learning_feedback.v4",
        "evaluated_count": total,
        "support_rate_pct": round(supported / total * 100, 1) if total else None,
        "verdict_counts": verdict_counts,
        "top_error_patterns": [
            {"key": key, "count": count}
            for key, count in sorted(reason_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:5]
        ],
        "recent_failures": [compact(item) for item in recent_failures],
        "recent_successes": [compact(item) for item in recent_successes],
        "operation_feedback": {
            "account_record_status": current_account_record_status(),
            "confirmed_action_count": len(confirmed_actions),
            "strategy_comparison_counts": strategy_counts,
            "recent_action_comparisons": recent_action_comparisons,
            "weekly_symbol_operations": weekly_operations,
            "snapshot_change_count": len(_read(SNAPSHOT_CHANGES_PATH)),
        },
        "policy_memory": learning_policy_snapshot(),
        "learning_rule": (
            "历史结果只用于校准与反思，不得替代当前证据；新结论如重复历史失败模式，"
            "必须说明新增证据或降级为观察；用户操作与既有建议冲突时，应核查冲突原因，"
            "不能默认用户或模型任一方正确。"
        ),
    }
