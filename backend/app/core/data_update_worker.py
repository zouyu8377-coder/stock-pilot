import os
from datetime import datetime

from app.core.data_updater import UPDATE_LOCK_FILE, get_last_trading_date, load_update_status, run_sync_update
from app.core.etf_data_updater import etf_needs_update, run_sync_etf_update


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
        stock_status = load_update_status()
        stocks_ready = (
            stock_status.get("status") == "complete"
            and stock_status.get("last_trading_date") == target_date.isoformat()
        )

        if stocks_ready:
            print(f"[DataUpdaterWorker] stock data already updated to {target_date}, skip stock update")
        else:
            run_sync_update(target_date)

        if etf_needs_update(target_date):
            run_sync_etf_update(target_date)
        else:
            print(f"[DataUpdaterWorker] ETF data already updated to {target_date}, skip ETF update")
    finally:
        try:
            UPDATE_LOCK_FILE.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
