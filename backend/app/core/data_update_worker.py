import os
from datetime import datetime

from app.core.data_updater import UPDATE_LOCK_FILE, get_last_trading_date, run_sync_update


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
        run_sync_update(target_date)
    finally:
        try:
            UPDATE_LOCK_FILE.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
