from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd


DEFAULT_DAILY_TTL = timedelta(hours=20)


def to_ts_code(symbol: str) -> str:
    value = symbol.strip().upper()
    if "." in value:
        code, suffix = value.split(".", 1)
        if suffix in {"SH", "SZ"}:
            return f"{code.zfill(6)}.{suffix}"
        return value
    code = value.zfill(6)
    if code.startswith(("6", "5")):
        return f"{code}.SH"
    return f"{code}.SZ"


def compact_symbol(symbol: str) -> str:
    return symbol.split(".", 1)[0].zfill(6)


def today_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")


def days_ago_yyyymmdd(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")


def parse_yyyymmdd(value: Any) -> date | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:8], "%Y%m%d").date()
    except ValueError:
        try:
            return pd.to_datetime(text, errors="coerce").date()
        except Exception:
            return None


def safe_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return round(float(value), 4)
    except Exception:
        return None


def safe_str(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value)


def records_from_df(df: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    frame = df.head(limit) if limit else df
    records = []
    for row in frame.to_dict(orient="records"):
        clean = {}
        for key, value in row.items():
            if value is None or pd.isna(value):
                clean[key] = None
            elif hasattr(value, "item"):
                clean[key] = value.item()
            else:
                clean[key] = value
        records.append(clean)
    return records
