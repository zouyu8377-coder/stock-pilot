from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd


class AkshareEtfShareError(RuntimeError):
    """Raised when AKShare ETF share data cannot be fetched or normalized."""


def compact_fund_code(code: str) -> str:
    return str(code or "").split(".", 1)[0].strip().zfill(6)


def infer_exchange(code: str) -> str:
    compact = compact_fund_code(code)
    if compact.startswith(("51", "56", "58")):
        return "SSE"
    if compact.startswith(("15", "16")):
        return "SZSE"
    return "UNKNOWN"


def _import_akshare():
    try:
        import akshare as ak  # type: ignore
    except ImportError as exc:
        raise AkshareEtfShareError("AKShare is not installed. Please install backend requirements first.") from exc
    return ak


def _pick_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    normalized = {str(col).strip().lower(): col for col in columns}
    for candidate in candidates:
        exact = normalized.get(candidate.strip().lower())
        if exact is not None:
            return exact
    for col in columns:
        text = str(col).strip().lower()
        if any(candidate.strip().lower() in text for candidate in candidates):
            return col
    return None


def _parse_trade_date(value: Any, fallback: str | None = None) -> str | None:
    if value is None or pd.isna(value):
        value = fallback
    if value is None or pd.isna(value):
        return None
    parsed = pd.to_datetime(str(value), errors="coerce")
    if pd.isna(parsed):
        text = str(value).strip()
        if len(text) >= 8 and text[:8].isdigit():
            return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
        return None
    return parsed.strftime("%Y-%m-%d")


def _as_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).replace(",", "").replace("，", "").strip()
    if text in {"", "-", "--", "None", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _share_to_raw_units(value: Any, column_name: str | None = None) -> float | None:
    raw = _as_float(value)
    if raw is None:
        return None
    name = str(column_name or "")
    if "亿" in name:
        return raw * 100_000_000
    if "万" in name:
        return raw * 10_000
    return raw


def _normalize_records(
    df: pd.DataFrame,
    code: str,
    exchange: str,
    fallback_date: str | None = None,
    source: str = "akshare",
) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    frame = df.copy()
    columns = list(frame.columns)
    code_col = _pick_column(columns, ("基金代码", "基金编码", "证券代码", "代码", "fund_code", "ts_code"))
    name_col = _pick_column(columns, ("基金简称", "基金名称", "证券简称", "简称", "名称", "fund_name"))
    date_col = _pick_column(columns, ("统计日期", "业务日期", "交易日期", "日期", "trade_date", "end_date"))
    share_col = _pick_column(columns, ("最新份额", "基金份额", "份额", "总份额", "基金规模", "规模", "fund_share", "total_share"))
    nav_col = _pick_column(columns, ("单位净值", "基金净值", "净值", "nav", "unit_nav"))
    if code_col is None or share_col is None:
        return []

    compact = compact_fund_code(code)
    frame["_fund_code"] = frame[code_col].map(compact_fund_code)
    frame = frame[frame["_fund_code"] == compact]
    records: list[dict[str, Any]] = []
    fetched_at = datetime.utcnow().isoformat()
    for _, row in frame.iterrows():
        fund_share = _share_to_raw_units(row.get(share_col), str(share_col))
        trade_date = _parse_trade_date(row.get(date_col) if date_col else None, fallback=fallback_date)
        if fund_share is None or trade_date is None:
            continue
        raw_fields = {}
        for key, value in row.to_dict().items():
            if key == "_fund_code":
                continue
            raw_fields[str(key)] = None if value is None or pd.isna(value) else value
        records.append({
            "fund_code": compact,
            "fund_name": str(row.get(name_col) or "").strip() if name_col else "",
            "exchange": exchange,
            "trade_date": trade_date,
            "fund_share": fund_share,
            "fund_share_100m": round(fund_share / 100_000_000, 4),
            "nav": _as_float(row.get(nav_col)) if nav_col else None,
            "source": source,
            "fetched_at": fetched_at,
            "raw_fields": raw_fields,
        })
    return records


def fetch_sse_etf_share(code: str, date: str) -> list[dict[str, Any]]:
    ak = _import_akshare()
    yyyymmdd = date.replace("-", "")
    try:
        df = ak.fund_etf_scale_sse(date=yyyymmdd)
    except Exception as exc:
        raise AkshareEtfShareError(f"AKShare SSE ETF share request failed: {exc}") from exc
    return _normalize_records(df, code, "SSE", fallback_date=yyyymmdd)


def fetch_szse_etf_share_history(code: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    ak = _import_akshare()
    start = start_date.replace("-", "")
    end = end_date.replace("-", "")
    try:
        df = ak.fund_scale_daily_szse(start_date=start, end_date=end, symbol="ETF")
    except Exception as exc:
        raise AkshareEtfShareError(f"AKShare SZSE daily ETF share request failed: {exc}") from exc
    return _normalize_records(df, code, "SZSE")


def fetch_szse_etf_share_latest(code: str) -> list[dict[str, Any]]:
    ak = _import_akshare()
    try:
        df = ak.fund_etf_scale_szse()
    except Exception as exc:
        raise AkshareEtfShareError(f"AKShare SZSE latest ETF share request failed: {exc}") from exc
    return _normalize_records(df, code, "SZSE")


def fetch_em_etf_share_latest(code: str) -> list[dict[str, Any]]:
    ak = _import_akshare()
    compact = compact_fund_code(code)
    try:
        df = ak.fund_etf_spot_em()
    except Exception as exc:
        raise AkshareEtfShareError(f"AKShare Eastmoney ETF spot request failed: {exc}") from exc
    records = _normalize_records(
        df,
        compact,
        infer_exchange(compact),
        source="akshare_eastmoney_spot",
    )
    for record in records:
        if not record.get("trade_date"):
            record["trade_date"] = datetime.now().strftime("%Y-%m-%d")
    return records
