import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4

from app.data_sync.storage import ProcessRLock, now, read, write

ROOT = Path(__file__).resolve().parents[2] / "data" / "investment_agents"
LOCK = ProcessRLock(lambda: ROOT / "workspace.lock")
TERMINAL = {"awaiting_confirmation", "confirmed", "failed", "cancelled", "stale"}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def path(run_id):
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("无效任务编号")
    return ROOT / "runs" / run_id / "run.json"


def load(run_id):
    value = read(path(run_id))
    if not value:
        raise ValueError("分析任务不存在")
    return value


def save(run):
    run["updated_at"] = now().isoformat()
    write(path(run["run_id"]), run)
    return run


def event(run, actor, title, detail=""):
    run["events"].append({"id": uuid4().hex, "actor": actor, "title": title, "detail": detail[:2000], "at": now().isoformat()})
    run["events"] = run["events"][-100:]
    run["activity"] = title


def settings():
    return {"api_enabled": False, "codex_model": "", "web_search": True, "auto_apply_verified_holdings": True,
            **read(ROOT / "settings.json", {})}


def memories():
    return read(ROOT / "memory.json", {"revision": 0, "results": []})
