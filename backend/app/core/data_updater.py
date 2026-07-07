import asyncio
import json
import os
import random
import socket
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
METADATA_FILE = BASE_DIR / "data" / "metadata" / "stock_meta.parquet"
STATUS_FILE = BASE_DIR / "data" / "update_status.json"
UPDATE_LOCK_FILE = BASE_DIR / "data" / "update_worker.lock"

REQUEST_RETRIES = int(os.getenv("MARKET_UPDATE_RETRIES", "3"))
REQUEST_INTERVAL_SECONDS = float(os.getenv("MARKET_UPDATE_INTERVAL_SECONDS", "0.35"))
MAX_CONSECUTIVE_FAILURES = int(os.getenv("MARKET_UPDATE_MAX_CONSECUTIVE_FAILURES", "20"))
UPDATE_LOCK_STALE_SECONDS = int(os.getenv("MARKET_UPDATE_LOCK_STALE_SECONDS", "21600"))
UPDATE_STATUS_STALE_SECONDS = int(os.getenv("MARKET_UPDATE_STATUS_STALE_SECONDS", "900"))
BAOSTOCK_SOCKET_TIMEOUT_SECONDS = float(os.getenv("BAOSTOCK_SOCKET_TIMEOUT_SECONDS", "20"))
STATUS_UPDATE_INTERVAL = int(os.getenv("MARKET_UPDATE_STATUS_INTERVAL", "20"))
SLOW_SYMBOL_SECONDS = float(os.getenv("MARKET_UPDATE_SLOW_SYMBOL_SECONDS", "5"))
SLOW_PROBE_SYMBOLS = int(os.getenv("MARKET_UPDATE_SLOW_PROBE_SYMBOLS", "3"))
SLOW_DEGRADE_AFTER = int(os.getenv("MARKET_UPDATE_SLOW_DEGRADE_AFTER", "2"))
BAOSTOCK_FIELDS = "date,open,high,low,close,volume,amount,turn,pctChg"
REQUIRED_BENCHMARK_SYMBOLS = {"sh.000300"}

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


def _status_is_stale(status: dict) -> bool:
    if status.get("status") not in {"checking", "running"}:
        return False
    raw = status.get("updated_at")
    if not raw:
        return True
    try:
        updated_at = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return True
    return (datetime.now() - updated_at).total_seconds() > UPDATE_STATUS_STALE_SECONDS


def extract_symbol(path: Path) -> str:
    return path.stem


def _ts_code_to_baostock_symbol(ts_code: str) -> str | None:
    text = str(ts_code).strip()
    if not text or "." not in text:
        return None

    code, exchange = text.split(".", 1)
    exchange = exchange.lower()
    if exchange == "sh":
        return f"sh.{code}"
    if exchange == "sz":
        return f"sz.{code}"
    return None


def _compact_to_baostock_symbol(symbol: str) -> str | None:
    text = str(symbol or "").strip()
    if not text:
        return None
    if "." in text:
        converted = _ts_code_to_baostock_symbol(text)
        if converted:
            return converted
        left, right = text.split(".", 1)
        if left.lower() in {"sh", "sz"}:
            return f"{left.lower()}.{right.zfill(6)}"
    compact = "".join(ch for ch in text if ch.isdigit()).zfill(6)
    if len(compact) != 6:
        return None
    if compact.startswith(("5", "6", "9")):
        return f"sh.{compact}"
    if compact.startswith(("0", "1", "2", "3")):
        return f"sz.{compact}"
    return None


def load_priority_symbols() -> set[str]:
    symbols = set(REQUIRED_BENCHMARK_SYMBOLS)
    try:
        from app.portfolio import portfolio_service

        for position in portfolio_service.get_state().snapshot.positions:
            converted = _compact_to_baostock_symbol(position.symbol)
            if converted:
                symbols.add(converted)
    except Exception as exc:
        print(f"[DataUpdater] Failed to load portfolio priority symbols: {exc}")
    return symbols


def _load_active_symbols() -> set[str]:
    if not METADATA_FILE.exists():
        print(f"[DataUpdater] Metadata file not found, using all local market files: {METADATA_FILE}")
        return set()

    try:
        meta = pd.read_parquet(METADATA_FILE, columns=["ts_code"])
    except Exception as e:
        print(f"[DataUpdater] Failed to load metadata, using all local market files: {e}")
        return set()

    symbols = {
        symbol
        for symbol in (_ts_code_to_baostock_symbol(value) for value in meta["ts_code"].dropna())
        if symbol
    }
    print(f"[DataUpdater] Active symbols from metadata: {len(symbols)}")
    return symbols


def _market_files(active_symbols: set[str] | None = None) -> list[Path]:
    files = sorted(BASE_MARKET_DIR.glob("*.parquet"))
    if active_symbols:
        files = [
            path
            for path in files
            if extract_symbol(path) in active_symbols
            or extract_symbol(path) in REQUIRED_BENCHMARK_SYMBOLS
        ]
    return files


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
    return df
def _ensure_baostock_login() -> None:
    global _BAOSTOCK_LOGGED_IN
    if _BAOSTOCK_LOGGED_IN:
        return

    socket.setdefaulttimeout(BAOSTOCK_SOCKET_TIMEOUT_SECONDS)
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


def _reset_baostock_session() -> None:
    """Drop a broken BaoStock socket so the next retry performs a fresh login."""
    global _BAOSTOCK_LOGGED_IN
    try:
        if _BAOSTOCK_LOGGED_IN:
            bs.logout()
    except Exception:
        pass
    finally:
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
            _reset_baostock_session()
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

    active_symbols = _load_active_symbols()
    files = _market_files(active_symbols)
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
        combined["date"] = pd.to_datetime(combined["date"], errors="coerce")
        combined = combined.dropna(subset=["date"])
        combined = combined.drop_duplicates(subset=["date"], keep="last")
        combined = combined.sort_values("date")
        combined.to_parquet(path, index=False)
        return True, None
    except Exception as e:
        reason = str(e)
        print(f"[DataUpdater] FAILED {symbol}: {reason}")
        return False, reason


def _market_files_for_symbols(symbols: set[str]) -> list[Path]:
    return [
        path
        for path in _market_files()
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


def run_sync_update(target_date: date, priority_symbols: set[str] | None = None, *, priority_only: bool = False) -> dict:
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
        "phase": "checking",
    })

    priority_symbols = priority_symbols if priority_symbols is not None else load_priority_symbols()
    if priority_only and priority_symbols:
        active_symbols = _load_active_symbols()
        total = len(_market_files(active_symbols))
        priority_paths_for_check = _market_files_for_symbols(priority_symbols)
        priority_outdated_for_check = [
            extract_symbol(path)
            for path in priority_paths_for_check
            if not is_symbol_updated(path, target_date)
        ]
        all_updated = not priority_outdated_for_check
        outdated = priority_outdated_for_check
        if all_updated:
            status = {
                **_default_status(),
                "last_trading_date": None,
                "completed_count": len(priority_paths_for_check),
                "failed_count": 0,
                "total_symbols": total,
                "updated_at": datetime.now().isoformat(),
                "status": "market_deferred",
                "provider": "baostock",
                "target_date": target_date.isoformat(),
                "phase": "market_deferred",
                "remaining_count": max(total - len(priority_paths_for_check), 0),
                "core_total": len(priority_paths_for_check),
                "core_completed": len(priority_paths_for_check),
                "core_failed": 0,
                "core_status": "complete",
                "core_last_trading_date": target_date.isoformat(),
                "market_total": max(total - len(priority_paths_for_check), 0),
                "market_processed": 0,
                "deferred_reason": "启动阶段仅更新核心标的，全市场冷数据延后补全。",
            }
            save_update_status(status)
            return {"action": "core_ready", "total": total, "updated": 0, "failed": 0, "deferred": True}
    else:
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
            "phase": "complete",
        }
        save_update_status(status)
        return {"action": "none", "total": total, "updated": 0, "failed": 0}

    print(f"[DataUpdater] Need to update {len(outdated)}/{total} symbols via BaoStock")
    priority_outdated = set(outdated) & priority_symbols
    priority_paths = _market_files_for_symbols(priority_outdated)
    priority_path_symbols = {extract_symbol(path) for path in priority_paths}
    market_paths = _market_files_for_symbols(set(outdated) - priority_path_symbols)
    ordered_paths = priority_paths + market_paths
    print(
        "[DataUpdater] Priority update set: "
        f"{len(priority_paths)} symbols, market backlog: {len(market_paths)}"
    )
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
        "phase": "core_running" if priority_paths else "market_backfill",
        "core_total": len(priority_paths),
        "core_completed": 0,
        "core_failed": 0,
        "market_total": len(market_paths) if not priority_only else max(total - len(priority_paths), 0),
        "market_processed": 0,
    })

    updated_count = 0
    processed_count = 0
    core_completed = 0
    core_failed = 0
    market_processed = 0
    failed_symbols: list[str] = []
    failure_reasons: Counter[str] = Counter()
    consecutive_failures = 0
    slow_samples: list[float] = []
    slow_count = 0
    deferred_reason: str | None = None

    def write_running_status(*, phase: str, current_symbol: str | None = None) -> None:
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
            "remaining_count": max(len(outdated) - processed_count, 0),
            "processed_count": processed_count,
            "current_symbol": current_symbol,
            "provider": "baostock",
            "phase": phase,
            "core_total": len(priority_paths),
            "core_completed": core_completed,
            "core_failed": core_failed,
            "market_total": len(market_paths),
            "market_processed": market_processed,
            "slow_symbol_seconds": SLOW_SYMBOL_SECONDS,
            "average_symbol_seconds": round(sum(slow_samples) / len(slow_samples), 2) if slow_samples else None,
        })

    try:
        _ensure_baostock_login()
        for path in ordered_paths:
            symbol = extract_symbol(path)
            is_core = symbol in priority_path_symbols
            phase = "core_running" if is_core else "market_backfill"
            started_at = time.perf_counter()
            success, reason = update_single_symbol(path, target_date)
            elapsed = time.perf_counter() - started_at
            processed_count += 1
            if success:
                updated_count += 1
                consecutive_failures = 0
            else:
                failed_symbols.append(symbol)
                consecutive_failures += 1
                failure_reasons[_summarize_reason(reason or "unknown")] += 1

            if is_core:
                if success:
                    core_completed += 1
                else:
                    core_failed += 1
            else:
                market_processed += 1
                slow_samples.append(elapsed)
                if elapsed >= SLOW_SYMBOL_SECONDS:
                    slow_count += 1

            if is_core or processed_count % STATUS_UPDATE_INTERVAL == 0:
                print(
                    "[DataUpdater] Progress: "
                    f"{processed_count}/{len(outdated)}, core={core_completed}/{len(priority_paths)}, "
                    f"market={market_processed}/{len(market_paths)}, failed={len(failed_symbols)}"
                )
                write_running_status(phase=phase, current_symbol=symbol)

            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print(
                    "[DataUpdater] Stop update: "
                    f"{consecutive_failures} consecutive failures, likely BaoStock/network issue"
                )
                break

            if (
                not is_core
                and market_processed >= SLOW_PROBE_SYMBOLS
                and slow_count >= SLOW_DEGRADE_AFTER
            ):
                average = sum(slow_samples) / len(slow_samples)
                deferred_reason = (
                    f"BaoStock 单标的请求偏慢，最近 {len(slow_samples)} 次平均 {average:.1f}s，"
                    "已优先完成核心标的，延后全市场补全。"
                )
                print(f"[DataUpdater] Defer market backfill: {deferred_reason}")
                break

            if REQUEST_INTERVAL_SECONDS > 0:
                time.sleep(REQUEST_INTERVAL_SECONDS + random.uniform(0, 0.15))
    finally:
        _logout_baostock()

    if priority_only:
        remaining = []
        all_updated_after = False
        if deferred_reason is None:
            deferred_reason = "启动阶段仅更新核心标的，全市场冷数据延后补全。"
    else:
        all_updated_after, remaining, _ = check_update_status(target_date)
    is_deferred = deferred_reason is not None
    is_complete = all_updated_after and not failed_symbols
    status = {
        **_default_status(),
        "last_trading_date": target_date.isoformat() if is_complete else None,
        "completed_count": total - len(remaining) if not priority_only else core_completed,
        "failed_count": len(failed_symbols),
        "total_symbols": total,
        "updated_at": datetime.now().isoformat(),
        "status": "complete" if is_complete else "market_deferred" if is_deferred else "partial_failed",
        "failed_symbols": failed_symbols[:200],
        "failure_reasons": dict(failure_reasons),
        "target_date": target_date.isoformat(),
        "remaining_count": len(remaining) if not priority_only else max(total - len(priority_paths), 0),
        "provider": "baostock",
        "phase": "complete" if is_complete else "market_deferred" if is_deferred else "partial_failed",
        "core_total": len(priority_paths),
        "core_completed": core_completed,
        "core_failed": core_failed,
        "core_status": "complete" if core_completed == len(priority_paths) and core_failed == 0 else "partial_failed",
        "core_last_trading_date": target_date.isoformat() if core_completed == len(priority_paths) and core_failed == 0 else None,
        "market_total": len(market_paths) if not priority_only else max(total - len(priority_paths), 0),
        "market_processed": market_processed,
        "deferred_reason": deferred_reason,
        "slow_symbol_seconds": SLOW_SYMBOL_SECONDS,
        "average_symbol_seconds": round(sum(slow_samples) / len(slow_samples), 2) if slow_samples else None,
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
        "deferred": is_deferred,
        "failure_reasons": dict(failure_reasons),
        "provider": "baostock",
    }


async def check_and_update() -> None:
    from app.core.etf_data_updater import etf_needs_update

    target_date = get_last_trading_date()
    status = load_update_status()
    stocks_ready = (
        status.get("status") == "complete"
        and status.get("last_trading_date") == target_date.isoformat()
    )
    etf_ready = not etf_needs_update(target_date)

    if stocks_ready and etf_ready:
        total = status.get("total_symbols", 0)
        print(f"[DataUpdater] Stock and ETF data already updated to {target_date}, stock total {total}")
        return

    if UPDATE_LOCK_FILE.exists() and (_status_is_stale(status) or not status):
        try:
            UPDATE_LOCK_FILE.unlink()
            print("[DataUpdater] Removed update lock because status heartbeat is stale")
        except OSError as exc:
            print(f"[DataUpdater] Failed to remove stale heartbeat lock: {exc}")

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
