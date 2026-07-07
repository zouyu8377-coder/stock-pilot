from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from app.evidence.schemas import (
    DataStatus,
    EvidenceCategory,
    EvidenceItem,
    EvidenceReliability,
    EvidenceType,
    LlmUsage,
)
from app.facts.common import (
    DEFAULT_DAILY_TTL,
    days_ago_yyyymmdd,
    parse_yyyymmdd,
    records_from_df,
    safe_float,
    safe_str,
    today_yyyymmdd,
    to_ts_code,
)
from app.tushare import TushareConfigError, TushareLowFrequencyClient, TushareRequestError


DRAGON_TIGER_LIMIT = (
    "Dragon-tiger list reflects public abnormal-trading-day seat structure only. "
    "It does not represent long-term holding intent and cannot predict the next trading day by itself."
)


def _sort(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "trade_date" not in df.columns:
        return pd.DataFrame()
    frame = df.copy()
    frame["trade_date"] = frame["trade_date"].astype(str)
    return frame.sort_values("trade_date", ascending=False).reset_index(drop=True)


def _seat_flags(seats: pd.DataFrame) -> tuple[bool, bool]:
    if seats is None or seats.empty or "exalter" not in seats.columns:
        return False, False
    names = " ".join(str(x) for x in seats["exalter"].dropna().tolist())
    return "机构专用" in names, ("深股通专用" in names or "沪股通专用" in names)


def _top_seats(seats: pd.DataFrame, field: str) -> list[dict[str, Any]]:
    if seats is None or seats.empty or field not in seats.columns:
        return []
    frame = seats.copy()
    frame[field] = pd.to_numeric(frame[field], errors="coerce").fillna(0)
    frame = frame[frame[field] > 0].sort_values(field, ascending=False)
    rows = []
    for row in records_from_df(frame, 5):
        rows.append({
            "seat": row.get("exalter"),
            "buy": safe_float(row.get("buy")),
            "sell": safe_float(row.get("sell")),
            "net_buy": safe_float(row.get("net_buy")),
            "buy_rate": safe_float(row.get("buy_rate")),
            "sell_rate": safe_float(row.get("sell_rate")),
        })
    return rows


def _event_payload(row: pd.Series, seats: pd.DataFrame) -> dict[str, Any]:
    amount = safe_float(row.get("amount")) or 0
    net_amount = safe_float(row.get("net_amount"))
    net_amount_rate = round(net_amount / amount * 100, 4) if net_amount is not None and amount else safe_float(row.get("net_rate"))
    has_inst, has_connect = _seat_flags(seats)
    return {
        "trade_date": safe_str(row.get("trade_date")),
        "reason": safe_str(row.get("reason")),
        "close": safe_float(row.get("close")),
        "pct_change": safe_float(row.get("pct_change")),
        "amount": amount or None,
        "total_buy": safe_float(row.get("l_buy")),
        "total_sell": safe_float(row.get("l_sell")),
        "net_buy": net_amount,
        "net_buy_amount_rate": net_amount_rate,
        "top_buy_seats": _top_seats(seats, "buy"),
        "top_sell_seats": _top_seats(seats, "sell"),
        "has_institutional_seat": has_inst,
        "has_stock_connect_seat": has_connect,
        "interpretation_limit": DRAGON_TIGER_LIMIT,
    }


def get_dragon_tiger_facts(symbol: str, *, force: bool = False) -> dict[str, Any]:
    ts_code = to_ts_code(symbol)
    client = TushareLowFrequencyClient()
    start_date = days_ago_yyyymmdd(45)
    end_date = today_yyyymmdd()
    try:
        events_df, events_meta = client.query(
            "top_list",
            namespace="dragon_tiger",
            ttl=DEFAULT_DAILY_TTL,
            force=force,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
        seats_df, seats_meta = client.query(
            "top_inst",
            namespace="dragon_tiger",
            ttl=DEFAULT_DAILY_TTL,
            force=force,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
    except (TushareConfigError, TushareRequestError) as exc:
        return {
            "success": False,
            "symbol": ts_code,
            "message": str(exc),
            "data_status": "unavailable",
            "data": {"events": [], "latest_event": None},
            "evidence": [],
        }

    events_df = _sort(events_df)
    seats_df = _sort(seats_df)
    events: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for _, row in events_df.iterrows():
        trade_date = safe_str(row.get("trade_date"))
        reason = safe_str(row.get("reason"))
        seats = seats_df[
            (seats_df.get("trade_date", pd.Series(dtype=str)).astype(str) == trade_date)
            & (seats_df.get("reason", pd.Series(dtype=str)).astype(str) == reason)
        ] if not seats_df.empty else pd.DataFrame()
        if seats.empty and not seats_df.empty:
            seats = seats_df[seats_df.get("trade_date", pd.Series(dtype=str)).astype(str) == trade_date]
        payload = _event_payload(row, seats)
        events.append(payload)
        item = EvidenceItem(
            symbol=ts_code,
            evidence_type=EvidenceType.DRAGON_TIGER_EVENT,
            category=EvidenceCategory.AUTO_FACT,
            title=f"Dragon-tiger event {trade_date}",
            payload=payload,
            source="tushare.top_list / top_inst",
            source_endpoint="top_list,top_inst",
            as_of_date=parse_yyyymmdd(trade_date),
            fetched_at=datetime.utcnow(),
            reliability=EvidenceReliability.B,
            llm_usage=LlmUsage.FACT_WITH_LIMIT,
            interpretation_limit=DRAGON_TIGER_LIMIT,
            data_status=DataStatus.AVAILABLE,
        )
        evidence.append(item.model_dump(mode="json"))

    return {
        "success": True,
        "symbol": ts_code,
        "data_status": "available" if events else "unavailable",
        "data": {
            "latest_event": events[0] if events else None,
            "events": events,
            "empty_message": "" if events else "No public dragon-tiger event found in the recent query window.",
            "interpretation_limit": DRAGON_TIGER_LIMIT,
        },
        "evidence": evidence,
        "cache": {
            "top_list": events_meta,
            "top_inst": seats_meta,
        },
    }
