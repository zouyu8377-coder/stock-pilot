from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[2]
TASKS_PATH = BACKEND_DIR / "data" / "agent_tasks" / "tasks.json"
MAX_EVIDENCE_AGE = timedelta(days=7)


def _compact_symbol(value: Any) -> str:
    return str(value or "").split(".", 1)[0].strip().zfill(6)


def _read_tasks() -> list[dict[str, Any]]:
    try:
        payload = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _as_utc(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def completed_market_trend_overrides(*, now: datetime | None = None) -> dict[str, dict[str, Any]]:
    """Expose recent completed stock-snapshot evidence as auditable trend fallbacks."""
    reference_time = now or datetime.now(timezone.utc)
    selected: dict[str, tuple[datetime, dict[str, Any]]] = {}
    for task in _read_tasks():
        if task.get("planning_origin") != "coverage_gap_auto":
            continue
        if task.get("tool", {}).get("name") != "stock_snapshot":
            continue
        if task.get("status") not in {"completed", "partial"}:
            continue
        result = task.get("result") or {}
        payload = result.get("payload") or {}
        retrieved_at = _as_utc(payload.get("retrieved_at") or result.get("completed_at"))
        if not retrieved_at or reference_time - retrieved_at > MAX_EVIDENCE_AGE:
            continue
        for snapshot in payload.get("snapshots") or []:
            history = snapshot.get("history") or {}
            if not history.get("latest_date") or history.get("return_20d_pct") is None:
                continue
            symbol = _compact_symbol(snapshot.get("symbol"))
            if not symbol:
                continue
            quote = snapshot.get("quote") or {}
            latest_price = history.get("latest_close") or quote.get("price")
            ma20 = history.get("ma20")
            override = {
                "data_status": "available",
                "daily_k_as_of": history.get("latest_date"),
                "latest_price": latest_price,
                "latest_pct_chg": quote.get("change_pct"),
                "return_5d_pct": history.get("return_5d_pct"),
                "return_20d_pct": history.get("return_20d_pct"),
                "return_60d_pct": history.get("return_60d_pct"),
                "ma20": ma20,
                "price_vs_ma20_pct": history.get("price_vs_ma20_pct"),
                "trend_state": "站上MA20" if latest_price is not None and ma20 is not None and float(latest_price) >= float(ma20) else "跌破MA20",
                "data_source": "agent_task_stock_snapshot",
                "evidence_task_id": task.get("task_id"),
                "evidence_retrieved_at": retrieved_at.isoformat(),
            }
            current = selected.get(symbol)
            if current is None or retrieved_at > current[0]:
                selected[symbol] = (retrieved_at, override)
    return {symbol: data for symbol, (_, data) in selected.items()}


def coverage_source_blocks() -> dict[str, str]:
    """Latest concrete source blockers from completed or partial coverage tasks."""
    result: dict[str, str] = {}
    for task in _read_tasks():
        if task.get("planning_origin") != "coverage_gap_auto":
            continue
        if task.get("status") not in {"partial", "failed"}:
            continue
        payload = (task.get("result") or {}).get("payload") or {}
        blockers = payload.get("remaining_gaps") or []
        if not blockers:
            continue
        message = str(blockers[0])[:240]
        # Tushare is no longer the only disclosure source. Historical task
        # failures caused solely by a missing token must remain retryable.
        if "Tushare token is not configured" in message:
            continue
        for symbol in task.get("target_symbols") or []:
            result[_compact_symbol(symbol)] = message
    return result
