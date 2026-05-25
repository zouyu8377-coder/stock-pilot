from __future__ import annotations

import json
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

import baostock as bs
import pandas as pd

from app.core.data_updater import (
    BASE_MARKET_DIR,
    BAOSTOCK_FIELDS,
    REQUEST_INTERVAL_SECONDS,
    _ensure_baostock_login,
    _logout_baostock,
    fetch_increment,
    is_symbol_updated,
    normalize_columns,
)


BASE_DIR = Path(__file__).resolve().parents[2]
METADATA_DIR = BASE_DIR / "data" / "metadata"
ETF_META_FILE = METADATA_DIR / "etf_meta.parquet"
ETF_STATUS_FILE = BASE_DIR / "data" / "etf_update_status.json"

ETF_PREFIXES = (
    "sh.510",
    "sh.511",
    "sh.512",
    "sh.513",
    "sh.515",
    "sh.516",
    "sh.517",
    "sh.518",
    "sh.588",
    "sh.589",
    "sz.159",
)


def _default_etf_status() -> dict[str, Any]:
    return {
        "last_trading_date": None,
        "completed_count": 0,
        "failed_count": 0,
        "total_symbols": 0,
        "updated_at": None,
        "status": "unknown",
        "failed_symbols": [],
        "failure_reasons": {},
        "provider": "baostock",
        "target_date": None,
        "remaining_count": 0,
        "processed_count": 0,
        "baostock_support": "query_stock_basic type=5 and query_history_k_data_plus daily K data",
    }


def _save_status(status: dict[str, Any]) -> None:
    ETF_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ETF_STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def load_etf_update_status() -> dict[str, Any]:
    if not ETF_STATUS_FILE.exists():
        return _default_etf_status()
    try:
        return {**_default_etf_status(), **json.loads(ETF_STATUS_FILE.read_text(encoding="utf-8"))}
    except Exception:
        return _default_etf_status()


def etf_needs_update(target_date: date) -> bool:
    status = load_etf_update_status()
    return not (
        status.get("status") == "complete"
        and status.get("last_trading_date") == target_date.isoformat()
    )


def _baostock_to_ts_code(code: str) -> str:
    exchange, raw = code.split(".", 1)
    return f"{raw}.{exchange.upper()}"


def _baostock_to_area(code: str) -> str:
    return code.split(".", 1)[0].upper()


def _is_etf_code(code: str, security_type: str | None = None) -> bool:
    return security_type == "5" or code.startswith(ETF_PREFIXES)


def bootstrap_etf_metadata(force: bool = False) -> tuple[pd.DataFrame, dict[str, Any]]:
    if ETF_META_FILE.exists() and not force:
        df = pd.read_parquet(ETF_META_FILE)
        return df, {
            "cache_hit": True,
            "row_count": int(len(df)),
            "provider": "baostock",
            "metadata_path": str(ETF_META_FILE),
        }

    _ensure_baostock_login()
    rs = bs.query_stock_basic()
    if rs is None:
        raise RuntimeError("BaoStock query_stock_basic returned None")
    if rs.error_code != "0":
        raise RuntimeError(f"BaoStock query_stock_basic failed: {rs.error_msg}")

    rows: list[dict[str, Any]] = []
    while rs.next():
        raw = dict(zip(rs.fields, rs.get_row_data()))
        code = raw.get("code", "")
        security_type = raw.get("type", "")
        status = raw.get("status", "")
        out_date = raw.get("outDate", "")
        if status != "1" or out_date:
            continue
        if not _is_etf_code(code, security_type):
            continue
        symbol = code.split(".", 1)[1]
        rows.append({
            "ts_code": _baostock_to_ts_code(code),
            "symbol": symbol,
            "name": raw.get("code_name") or symbol,
            "area": _baostock_to_area(code),
            "industry": "ETF",
            "list_date": raw.get("ipoDate", ""),
            "fund_type": "ETF",
            "management": "",
            "asset_type": "etf",
            "baostock_code": code,
            "baostock_type": security_type,
        })

    df = pd.DataFrame(rows).sort_values(["symbol", "area"]).reset_index(drop=True)
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(ETF_META_FILE, index=False)
    return df, {
        "cache_hit": False,
        "row_count": int(len(df)),
        "provider": "baostock",
        "metadata_path": str(ETF_META_FILE),
    }


def load_etf_symbols() -> pd.DataFrame:
    meta, _ = bootstrap_etf_metadata(force=False)
    if not meta.empty:
        return meta

    local_rows = []
    for path in sorted(BASE_MARKET_DIR.glob("*.parquet")):
        code = path.stem
        if _is_etf_code(code):
            symbol = code.split(".", 1)[1]
            local_rows.append({
                "ts_code": _baostock_to_ts_code(code),
                "symbol": symbol,
                "name": symbol,
                "area": _baostock_to_area(code),
                "industry": "ETF",
                "fund_type": "ETF",
                "asset_type": "etf",
                "baostock_code": code,
            })
    return pd.DataFrame(local_rows)


def _download_full_history(code: str) -> tuple[bool, str | None]:
    path = BASE_MARKET_DIR / f"{code}.parquet"
    if path.exists():
        return True, None

    rs = bs.query_history_k_data_plus(
        code=code,
        fields=BAOSTOCK_FIELDS,
        start_date="1990-01-01",
        end_date=datetime.now().strftime("%Y-%m-%d"),
        frequency="d",
        adjustflag="3",
    )
    if rs is None:
        return False, "BaoStock history query returned None"
    if rs.error_code != "0":
        return False, rs.error_msg

    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return False, "empty BaoStock ETF history"

    BASE_MARKET_DIR.mkdir(parents=True, exist_ok=True)
    df = normalize_columns(pd.DataFrame(rows, columns=BAOSTOCK_FIELDS.split(",")))
    df.to_parquet(path, index=False)
    return True, None


def update_single_etf(code: str, target_date: date) -> tuple[bool, str | None]:
    path = BASE_MARKET_DIR / f"{code}.parquet"
    try:
        if not path.exists():
            return _download_full_history(code)
        if is_symbol_updated(path, target_date):
            return True, None
        old_df = normalize_columns(pd.read_parquet(path))
        if "date" not in old_df.columns:
            return False, "missing date column"
        old_df["date"] = pd.to_datetime(old_df["date"], errors="coerce")
        last_date = old_df["date"].max().strftime("%Y-%m-%d")
        new_df = fetch_increment(code, last_date)
        if new_df is None or new_df.empty:
            return True, None
        combined = pd.concat([old_df, new_df], ignore_index=True)
        combined = normalize_columns(combined).dropna(subset=["date"])
        combined = combined.drop_duplicates(subset=["date"], keep="last").sort_values("date")
        combined.to_parquet(path, index=False)
        return True, None
    except Exception as exc:
        return False, str(exc)[:240]


def _summarize_reason(reason: str) -> str:
    text = reason.lower()
    if "login" in text:
        return "baostock_login_error"
    if "empty" in text:
        return "empty_history"
    if "timeout" in text:
        return "timeout"
    if "connection" in text:
        return "connection_error"
    if "missing date column" in text:
        return "bad_local_schema"
    return reason[:120]


def run_sync_etf_update(target_date: date) -> dict[str, Any]:
    print(f"[ETFDataUpdater] Start BaoStock ETF update, target date: {target_date}")
    _save_status({
        **_default_etf_status(),
        "status": "checking",
        "target_date": target_date.isoformat(),
        "updated_at": datetime.now().isoformat(),
    })

    try:
        _ensure_baostock_login()
        rows = load_etf_symbols()
        if rows.empty:
            status = {
                **_default_etf_status(),
                "status": "unavailable",
                "target_date": target_date.isoformat(),
                "updated_at": datetime.now().isoformat(),
                "failure_reasons": {"no_etf_symbols": 1},
            }
            _save_status(status)
            return {"action": "none", "total": 0, "provider": "baostock"}

        symbols = rows["baostock_code"].astype(str).dropna().unique().tolist()
        total = len(symbols)
        outdated = [code for code in symbols if not is_symbol_updated(BASE_MARKET_DIR / f"{code}.parquet", target_date)]
        already_updated = total - len(outdated)

        if not outdated:
            status = {
                **_default_etf_status(),
                "status": "complete",
                "last_trading_date": target_date.isoformat(),
                "target_date": target_date.isoformat(),
                "completed_count": total,
                "total_symbols": total,
                "updated_at": datetime.now().isoformat(),
            }
            _save_status(status)
            return {"action": "none", "total": total, "updated": 0, "failed": 0, "provider": "baostock"}

        _save_status({
            **_default_etf_status(),
            "status": "running",
            "target_date": target_date.isoformat(),
            "completed_count": already_updated,
            "total_symbols": total,
            "remaining_count": len(outdated),
            "updated_at": datetime.now().isoformat(),
        })

        updated = 0
        failed_symbols: list[str] = []
        failure_reasons: Counter[str] = Counter()

        for idx, code in enumerate(outdated, start=1):
            ok, reason = update_single_etf(code, target_date)
            if ok:
                updated += 1
            else:
                failed_symbols.append(code)
                failure_reasons[_summarize_reason(reason or "unknown")] += 1

            _save_status({
                **_default_etf_status(),
                "status": "running",
                "target_date": target_date.isoformat(),
                "completed_count": already_updated + updated,
                "failed_count": len(failed_symbols),
                "total_symbols": total,
                "remaining_count": max(len(outdated) - idx, 0),
                "processed_count": idx,
                "current_symbol": code,
                "updated_at": datetime.now().isoformat(),
                "failed_symbols": failed_symbols[-200:],
                "failure_reasons": dict(failure_reasons),
            })
            if REQUEST_INTERVAL_SECONDS > 0:
                time.sleep(REQUEST_INTERVAL_SECONDS)

        completed = already_updated + updated
        is_complete = not failed_symbols
        status = {
            **_default_etf_status(),
            "status": "complete" if is_complete else "partial_failed",
            "last_trading_date": target_date.isoformat() if is_complete else None,
            "target_date": target_date.isoformat(),
            "completed_count": completed,
            "failed_count": len(failed_symbols),
            "total_symbols": total,
            "remaining_count": max(total - completed, 0),
            "updated_at": datetime.now().isoformat(),
            "failed_symbols": failed_symbols[:200],
            "failure_reasons": dict(failure_reasons),
        }
        _save_status(status)
        return {
            "action": "updated",
            "total": total,
            "updated": updated,
            "failed": len(failed_symbols),
            "complete": is_complete,
            "provider": "baostock",
            "failure_reasons": dict(failure_reasons),
        }
    except Exception as exc:
        status = {
            **_default_etf_status(),
            "status": "unavailable",
            "target_date": target_date.isoformat(),
            "updated_at": datetime.now().isoformat(),
            "failure_reasons": {_summarize_reason(str(exc)): 1},
        }
        _save_status(status)
        return {"action": "unavailable", "reason": str(exc), "provider": "baostock"}
    finally:
        _logout_baostock()
