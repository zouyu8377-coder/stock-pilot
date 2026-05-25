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


SUPPORTED_ETFS = {
    "159382.SZ": {"name": "创业板人工智能ETF南方"},
    "159934.SZ": {"name": "黄金ETF易方达"},
}

ETF_INTERPRETATION_LIMIT = (
    "ETF shares, size, NAV, and price are factual observations only. Share changes do not imply "
    "future price direction and must not be interpreted as confirmed fund intent."
)


def _sort_by_date(df: pd.DataFrame, column: str) -> pd.DataFrame:
    if df is None or df.empty or column not in df.columns:
        return pd.DataFrame()
    frame = df.copy()
    frame[column] = frame[column].astype(str)
    return frame.sort_values(column, ascending=False).reset_index(drop=True)


def _change(series: list[float | None], offset: int) -> tuple[float | None, float | None]:
    if len(series) <= offset or series[0] is None or series[offset] in {None, 0}:
        return None, None
    delta = round(series[0] - series[offset], 4)
    pct = round(delta / series[offset] * 100, 4)
    return delta, pct


def _streak(values: list[float | None]) -> int:
    if len(values) < 2 or values[0] is None or values[1] is None:
        return 0
    direction = 1 if values[0] > values[1] else -1 if values[0] < values[1] else 0
    if direction == 0:
        return 0
    count = 0
    for idx in range(len(values) - 1):
        current, previous = values[idx], values[idx + 1]
        if current is None or previous is None:
            break
        if direction == 1 and current > previous:
            count += 1
            continue
        if direction == -1 and current < previous:
            count -= 1
            continue
        break
    return count


def _quadrant(price_delta: float | None, share_delta: float | None) -> str:
    if price_delta is None or share_delta is None:
        return "insufficient_data"
    if price_delta >= 0 and share_delta >= 0:
        return "price_up_share_up"
    if price_delta >= 0 and share_delta < 0:
        return "price_up_share_down"
    if price_delta < 0 and share_delta >= 0:
        return "price_down_share_up"
    return "price_down_share_down"


def _build_payload(ts_code: str, basic: pd.DataFrame, share: pd.DataFrame, nav: pd.DataFrame, daily: pd.DataFrame) -> dict[str, Any]:
    latest_share = share.iloc[0] if not share.empty else {}
    latest_nav = nav.iloc[0] if not nav.empty else {}
    latest_daily = daily.iloc[0] if not daily.empty else {}
    share_values = [safe_float(v) for v in share.get("total_share", pd.Series(dtype=float)).tolist()]
    price_values = [safe_float(v) for v in daily.get("close", pd.Series(dtype=float)).tolist()]
    share_1d, share_1d_pct = _change(share_values, 1)
    share_5d, share_5d_pct = _change(share_values, 5)
    share_20d, share_20d_pct = _change(share_values, 20)
    price_1d, price_1d_pct = _change(price_values, 1)
    price_5d, price_5d_pct = _change(price_values, 5)
    price_20d, price_20d_pct = _change(price_values, 20)

    basic_row = basic.iloc[0] if not basic.empty else {}
    as_of = parse_yyyymmdd(latest_share.get("trade_date")) or parse_yyyymmdd(latest_daily.get("trade_date"))
    return {
        "symbol": ts_code,
        "name": safe_str(basic_row.get("csname")) or safe_str(latest_share.get("etf_name")) or SUPPORTED_ETFS.get(ts_code, {}).get("name", ""),
        "full_name": safe_str(basic_row.get("cname")) or safe_str(basic_row.get("extname")),
        "index_name": safe_str(basic_row.get("index_name")),
        "manager": safe_str(basic_row.get("mgr_name")) or safe_str(basic_row.get("management")),
        "as_of_date": as_of.isoformat() if as_of else None,
        "latest_share": safe_float(latest_share.get("total_share")),
        "latest_size": safe_float(latest_share.get("total_size")),
        "nav": safe_float(latest_nav.get("unit_nav")) or safe_float(latest_nav.get("adj_nav")),
        "close": safe_float(latest_daily.get("close")),
        "share_change": {
            "1d": share_1d,
            "1d_pct": share_1d_pct,
            "5d": share_5d,
            "5d_pct": share_5d_pct,
            "20d": share_20d,
            "20d_pct": share_20d_pct,
        },
        "price_change": {
            "1d": price_1d,
            "1d_pct": price_1d_pct,
            "5d": price_5d,
            "5d_pct": price_5d_pct,
            "20d": price_20d,
            "20d_pct": price_20d_pct,
        },
        "share_streak_days": _streak(share_values),
        "quadrant_label": _quadrant(price_1d, share_1d),
        "series": {
            "share_size": records_from_df(share, 75),
            "nav": records_from_df(nav, 75),
            "daily": records_from_df(daily, 75),
        },
        "interpretation_limit": ETF_INTERPRETATION_LIMIT,
    }


def get_etf_facts(symbol: str, *, force: bool = False) -> dict[str, Any]:
    ts_code = to_ts_code(symbol)
    client = TushareLowFrequencyClient()
    start_date = days_ago_yyyymmdd(140)
    end_date = today_yyyymmdd()
    try:
        basic, basic_meta = client.query("etf_basic", namespace="etf", ttl=DEFAULT_DAILY_TTL, force=force, ts_code=ts_code)
        share, share_meta = client.query(
            "etf_share_size",
            namespace="etf",
            ttl=DEFAULT_DAILY_TTL,
            force=force,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
        nav, nav_meta = client.query(
            "fund_nav",
            namespace="etf",
            ttl=DEFAULT_DAILY_TTL,
            force=force,
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
        daily, daily_meta = client.query(
            "fund_daily",
            namespace="etf",
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
            "data": None,
            "evidence": [],
        }

    share = _sort_by_date(share, "trade_date")
    nav = _sort_by_date(nav, "nav_date")
    daily = _sort_by_date(daily, "trade_date")
    payload = _build_payload(ts_code, basic, share, nav, daily)
    as_of = parse_yyyymmdd((payload.get("as_of_date") or "").replace("-", ""))
    evidence = EvidenceItem(
        symbol=ts_code,
        evidence_type=EvidenceType.ETF_SHARE_CHANGE,
        category=EvidenceCategory.AUTO_FACT,
        title="ETF share, NAV, and price facts",
        payload=payload,
        source="tushare.etf_share_size / fund_nav / fund_daily",
        source_endpoint="etf_share_size,fund_nav,fund_daily",
        as_of_date=as_of,
        fetched_at=datetime.utcnow(),
        reliability=EvidenceReliability.B,
        llm_usage=LlmUsage.FACT_WITH_LIMIT,
        interpretation_limit=ETF_INTERPRETATION_LIMIT,
        data_status=DataStatus.AVAILABLE if payload.get("latest_share") is not None else DataStatus.UNAVAILABLE,
    )
    return {
        "success": True,
        "symbol": ts_code,
        "data_status": evidence.data_status.value,
        "data": payload,
        "evidence": [evidence.model_dump(mode="json")],
        "cache": {
            "basic": basic_meta,
            "share_size": share_meta,
            "nav": nav_meta,
            "daily": daily_meta,
        },
    }
