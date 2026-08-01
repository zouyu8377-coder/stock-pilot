import os
from datetime import datetime

from app.core.data_updater import (
    UPDATE_LOCK_FILE,
    get_last_trading_date,
    load_priority_symbols,
    load_update_status,
    run_sync_update,
)
from app.core.etf_data_updater import load_etf_update_status, run_sync_etf_update
from app.rotation.service import build_rotation_bundle


def main():
    UPDATE_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(UPDATE_LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print("[DataUpdaterWorker] another worker is already running")
        return

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(datetime.now().isoformat())

        target_date = get_last_trading_date()
        priority_symbols = load_priority_symbols()
        stock_status = load_update_status()
        stocks_ready = (
            stock_status.get("status") == "complete"
            and stock_status.get("last_trading_date") == target_date.isoformat()
        )
        core_ready = (
            stock_status.get("core_status") == "complete"
            and stock_status.get("core_last_trading_date") == target_date.isoformat()
            and stock_status.get("status") == "market_deferred"
        )

        if stocks_ready:
            print(f"[DataUpdaterWorker] stock data already updated to {target_date}, skip stock update")
        else:
            if not core_ready:
                run_sync_update(target_date, priority_symbols=priority_symbols, priority_only=True)
            print(f"[DataUpdaterWorker] start low-priority stock market backfill for {target_date}")
            run_sync_update(target_date, priority_symbols=priority_symbols, priority_only=False)

        etf_status = load_etf_update_status()
        etf_ready = (
            etf_status.get("status") == "complete"
            and etf_status.get("last_trading_date") == target_date.isoformat()
        )
        etf_core_ready = (
            etf_status.get("status") == "market_deferred"
            and etf_status.get("core_status") == "complete"
            and etf_status.get("core_last_trading_date") == target_date.isoformat()
        )
        if not etf_ready:
            if not etf_core_ready:
                run_sync_etf_update(target_date, priority_only=True)
            print(f"[DataUpdaterWorker] start low-priority ETF market backfill for {target_date}")
            run_sync_etf_update(target_date, priority_only=False)
        else:
            print(f"[DataUpdaterWorker] ETF data already updated to {target_date}, skip ETF update")
        rotation = build_rotation_bundle()
        print(
            "[DataUpdaterWorker] rotation evidence rebuilt: "
            f"as_of={rotation.get('as_of')}, sectors={len(rotation.get('sectors', []))}"
        )
    finally:
        try:
            UPDATE_LOCK_FILE.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
