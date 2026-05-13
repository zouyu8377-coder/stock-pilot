import asyncio
import json
import os
import random
import subprocess
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import baostock as bs
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
BASE_MARKET_DIR = BASE_DIR / "data" / "base_market"
STATUS_FILE = BASE_DIR / "data" / "update_status.json"
UPDATE_LOCK_FILE = BASE_DIR / "data" / "update_worker.lock"

REQUEST_RETRIES = int(os.getenv("MARKET_UPDATE_RETRIES", "3"))
REQUEST_INTERVAL_SECONDS = float(os.getenv("MARKET_UPDATE_INTERVAL_SECONDS", "0.35"))
MAX_CONSECUTIVE_FAILURES = int(os.getenv("MARKET_UPDATE_MAX_CONSECUTIVE_FAILURES", "20"))
UPDATE_LOCK_STALE_SECONDS = int(os.getenv("MARKET_UPDATE_LOCK_STALE_SECONDS", "21600"))
BAOSTOCK_FIELDS = "date,open,high,low,close,volume,amount,turn,pctChg"

_BAOSTOCK_LOGGED_IN = False


def get_last_trading_date(ref_date: Optional[date] = None) -> date:
    d = ref_date or date.today()
    weekday = d.weekday()

    if weekday == 5:
        return d - timedelta(days=1)
    if weekday == 6:
        return d - timedelta(days=2)
    if weekday == 0:
        return d - timedelta(days=3)
    return d - timedelta(days=1)


def load_update_status() -> dict:
    if not STATUS_FILE.exists():
        return _default_status()
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return _default_status()


def save_update_status(status: dict) -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def _default_status() -> dict:
    return {
        "last_trading_date": None,
        "completed_count": 0,
        "failed_count": 0,
        "total_symbols": 0,
        "updated_at": None,
        "status": "unknown",
        "failed_symbols": [],
        "failure_reasons": {},
    }


def _lock_started_at() -> datetime | None:
    try:
        content = UPDATE_LOCK_FILE.read_text(encoding="utf-8").strip()
        if content:
            return datetime.fromisoformat(content)
    except Exception:
        pass

    try:
        return datetime.fromtimestamp(UPDATE_LOCK_FILE.stat().st_mtime)
    except Exception:
        return None


def _clear_stale_update_lock() -> bool:
    started_at = _lock_started_at()
    if started_at is None:
        is_stale = True
        age_seconds = None
    else:
        age_seconds = (datetime.now() - started_at).total_seconds()
        is_stale = age_seconds > UPDATE_LOCK_STALE_SECONDS

    if not is_stale:
        return False

    try:
        UPDATE_LOCK_FILE.unlink()
        age_text = "unknown age" if age_seconds is None else f"{int(age_seconds)}s old"
        print(f"[DataUpdater] Removed stale update lock ({age_text})")
        return True
    except FileNotFoundError:
        return True
    except Exception as e:
        print(f"[DataUpdater] Failed to remove stale update lock: {e}")
        return False


def extract_symbol(path: Path) -> str:
    return path.stem


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    col_map = {
        "日期": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
        "换手率": "turn",
        "涨跌幅": "pct_chg",
        "涨跌额": "change",
        "振幅": "amplitude",
        "股票代码": "symbol",
    }
    rename_map = {cn: en for cn, en in col_map.items() if cn in df.columns}
    if rename_map:
        df = df.rename(columns=rename_map)

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    return df


def _ensure_baostock_login() -> None:
    global _BAOSTOCK_LOGGED_IN
    if _BAOSTOCK_LOGGED_IN:
        return

    result = bs.login()
    if result.error_code != "0":
        raise RuntimeError(f"BaoStock login failed: {result.error_msg}")
    _BAOSTOCK_LOGGED_IN = True


def _logout_baostock() -> None:
    global _BAOSTOCK_LOGGED_IN
    if not _BAOSTOCK_LOGGED_IN:
        return
    bs.logout()
    _BAOSTOCK_LOGGED_IN = False


def fetch_increment(symbol: str, start_date: str) -> Optional[pd.DataFrame]:
    start = datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=1)
    start_str = start.strftime("%Y-%m-%d")
    end_str = datetime.now().strftime("%Y-%m-%d")
    last_error: Exception | None = None

    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            _ensure_baostock_login()
            result = bs.query_history_k_data_plus(
                code=symbol,
                fields=BAOSTOCK_FIELDS,
                start_date=start_str,
                end_date=end_str,
                frequency="d",
                adjustflag="3",
            )

            if result is None:
                raise RuntimeError("BaoStock query returned None")
            if result.error_code != "0":
                raise RuntimeError(result.error_msg)

            rows = []
            while result.next():
                rows.append(result.get_row_data())

            if not rows:
                return None

            df = pd.DataFrame(rows, columns=BAOSTOCK_FIELDS.split(","))
            return normalize_columns(df)
        except Exception as e:
            last_error = e
            if attempt < REQUEST_RETRIES:
                delay = min(8.0, 0.8 * attempt) + random.uniform(0, 0.4)
                time.sleep(delay)

    assert last_error is not None
    raise last_error


def is_symbol_updated(path: Path, target_date: date) -> bool:
    try:
        df = normalize_columns(pd.read_parquet(path))
        if "date" not in df.columns:
            return False
        last_date = pd.to_datetime(df["date"], errors="coerce").max().date()
        return last_date >= target_date
    except Exception:
        return False


def check_update_status(target_date: date) -> tuple[bool, list[str], int]:
    if not BASE_MARKET_DIR.exists():
        return False, [], 0

    files = sorted(BASE_MARKET_DIR.glob("*.parquet"))
    total = len(files)
    outdated = [
        extract_symbol(path)
        for path in files
        if not is_symbol_updated(path, target_date)
    ]

    return len(outdated) == 0, outdated, total


def update_single_symbol(path: Path, target_date: date) -> tuple[bool, str | None]:
    symbol = extract_symbol(path)
    try:
        old_df = normalize_columns(pd.read_parquet(path))
        if "date" not in old_df.columns:
            return False, "missing date column"

        old_df["date"] = pd.to_datetime(old_df["date"], errors="coerce")
        last_date = old_df["date"].max().strftime("%Y-%m-%d")
        if pd.to_datetime(last_date).date() >= target_date:
            return True, None

        new_df = fetch_increment(symbol, last_date)
        if new_df is None or new_df.empty:
            return True, None

        combined = pd.concat([old_df, new_df], ignore_index=True)
        combined = normalize_columns(combined)
        combined = combined.dropna(subset=["date"])
        combined = combined.drop_duplicates(subset=["date"], keep="last")
        combined = combined.sort_values("date")
        combined.to_parquet(path)
        return True, None
    except Exception as e:
        reason = str(e)
        print(f"[DataUpdater] FAILED {symbol}: {reason}")
        return False, reason


def _market_files_for_symbols(symbols: set[str]) -> list[Path]:
    return [
        path
        for path in sorted(BASE_MARKET_DIR.glob("*.parquet"))
        if extract_symbol(path) in symbols
    ]


def _summarize_reason(reason: str) -> str:
    text = reason.lower()
    if "login" in text:
        return "baostock_login_error"
    if "timeout" in text:
        return "timeout"
    if "connection" in text:
        return "connection_error"
    if "missing date column" in text:
        return "bad_local_schema"
    return reason[:120]


def run_sync_update(target_date: date) -> dict:
    print(f"[DataUpdater] Start BaoStock incremental update, target date: {target_date}")
    save_update_status({
        **_default_status(),
        "last_trading_date": None,
        "completed_count": 0,
        "total_symbols": 0,
        "updated_at": datetime.now().isoformat(),
        "status": "checking",
        "target_date": target_date.isoformat(),
        "provider": "baostock",
    })

    all_updated, outdated, total = check_update_status(target_date)
    if all_updated:
        print(f"[DataUpdater] All {total} symbols are already updated to {target_date}")
        status = {
            **_default_status(),
            "last_trading_date": target_date.isoformat(),
            "completed_count": total,
            "total_symbols": total,
            "updated_at": datetime.now().isoformat(),
            "status": "complete",
            "provider": "baostock",
        }
        save_update_status(status)
        return {"action": "none", "total": total, "updated": 0, "failed": 0}

    print(f"[DataUpdater] Need to update {len(outdated)}/{total} symbols via BaoStock")
    already_updated_count = total - len(outdated)
    save_update_status({
        **_default_status(),
        "last_trading_date": None,
        "completed_count": already_updated_count,
        "failed_count": 0,
        "total_symbols": total,
        "updated_at": datetime.now().isoformat(),
        "status": "running",
        "target_date": target_date.isoformat(),
        "remaining_count": len(outdated),
        "processed_count": 0,
        "provider": "baostock",
    })

    updated_count = 0
    failed_symbols: list[str] = []
    failure_reasons: Counter[str] = Counter()
    consecutive_failures = 0

    try:
        _ensure_baostock_login()
        for idx, path in enumerate(_market_files_for_symbols(set(outdated)), start=1):
            symbol = extract_symbol(path)
            success, reason = update_single_symbol(path, target_date)
            if success:
                updated_count += 1
                consecutive_failures = 0
            else:
                failed_symbols.append(symbol)
                consecutive_failures += 1
                failure_reasons[_summarize_reason(reason or "unknown")] += 1

            if idx % 100 == 0:
                print(f"[DataUpdater] Progress: {idx}/{len(outdated)}, failed: {len(failed_symbols)}")
                save_update_status({
                    **_default_status(),
                    "last_trading_date": None,
                    "completed_count": already_updated_count + updated_count,
                    "failed_count": len(failed_symbols),
                    "total_symbols": total,
                    "updated_at": datetime.now().isoformat(),
                    "status": "running",
                    "failed_symbols": failed_symbols[-200:],
                    "failure_reasons": dict(failure_reasons),
                    "target_date": target_date.isoformat(),
                    "remaining_count": max(len(outdated) - idx, 0),
                    "processed_count": idx,
                    "current_symbol": symbol,
                    "provider": "baostock",
                })

            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print(
                    "[DataUpdater] Stop update: "
                    f"{consecutive_failures} consecutive failures, likely BaoStock/network issue"
                )
                break

            if REQUEST_INTERVAL_SECONDS > 0:
                time.sleep(REQUEST_INTERVAL_SECONDS + random.uniform(0, 0.15))
    finally:
        _logout_baostock()

    all_updated_after, remaining, _ = check_update_status(target_date)
    is_complete = all_updated_after and not failed_symbols
    status = {
        **_default_status(),
        "last_trading_date": target_date.isoformat() if is_complete else None,
        "completed_count": total - len(remaining),
        "failed_count": len(failed_symbols),
        "total_symbols": total,
        "updated_at": datetime.now().isoformat(),
        "status": "complete" if is_complete else "partial_failed",
        "failed_symbols": failed_symbols[:200],
        "failure_reasons": dict(failure_reasons),
        "target_date": target_date.isoformat(),
        "remaining_count": len(remaining),
        "provider": "baostock",
    }
    save_update_status(status)

    print(
        "[DataUpdater] BaoStock update finished: "
        f"updated={updated_count}, failed={len(failed_symbols)}, remaining={len(remaining)}"
    )
    return {
        "action": "updated",
        "total": total,
        "updated": updated_count,
        "failed": len(failed_symbols),
        "remaining": len(remaining),
        "target_date": target_date.isoformat(),
        "complete": is_complete,
        "failure_reasons": dict(failure_reasons),
        "provider": "baostock",
    }


async def check_and_update() -> None:
    target_date = get_last_trading_date()
    status = load_update_status()

    if (
        status.get("status") == "complete"
        and status.get("last_trading_date") == target_date.isoformat()
    ):
        total = status.get("total_symbols", 0)
        print(f"[DataUpdater] Data already updated to {target_date}, total {total} symbols")
        return

    if UPDATE_LOCK_FILE.exists() and not _clear_stale_update_lock():
        print(f"[DataUpdater] Update worker already running for {target_date}")
        return

    log_dir = BASE_DIR.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "cold_data_update.out.log"
    stderr_path = log_dir / "cold_data_update.err.log"

    print(f"[DataUpdater] Spawning BaoStock cold data worker for {target_date}")
    with open(stdout_path, "a", encoding="utf-8") as stdout, open(stderr_path, "a", encoding="utf-8") as stderr:
        subprocess.Popen(
            [sys.executable, "-u", "-m", "app.core.data_update_worker"],
            cwd=BASE_DIR,
            stdout=stdout,
            stderr=stderr,
            close_fds=True,
        )
