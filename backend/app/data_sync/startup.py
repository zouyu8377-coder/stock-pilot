"""Launch deterministic data maintenance independently of legacy model automation."""
import os
import subprocess
import sys

from app.data_sync import storage as s


def launch():
    try:
        with s.exclusive(s.ROOT / "startup.lock"):
            previous = s.read(s.ROOT / "startup.json", {})
            if previous.get("pid") and s.process_alive(previous["pid"]):
                return previous
            log = s.ROOT / "startup.log"
            if log.exists() and log.stat().st_size > 2_000_000:
                log.replace(s.ROOT / "startup.previous.log")
            with log.open("a", encoding="utf-8") as stream:
                process = subprocess.Popen([sys.executable, "-u", str(s.BACKEND / "scripts" / "sync_data.py")],
                    cwd=s.BACKEND, stdout=stream, stderr=stream, env={**os.environ, "STOCK_PILOT_DATA_ONLY": "1", "PYTHONUTF8": "1"},
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            value = {"pid": process.pid, "launched_at": s.now().isoformat(), "model_calls": 0,
                     "scope": "重点资料优先，随后全市场分批补齐；共用同步锁，不并发重复下载"}
            s.write(s.ROOT / "startup.json", value)
            return value
    except BlockingIOError:
        return {"status": "already_launching"}
