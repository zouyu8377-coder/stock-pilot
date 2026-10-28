import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from uuid import uuid4

from app.data_sync import storage as s

# Independent cadences; a failed source does not stop other collections.
POLICY = {"cold": (3600, 360), "market": (900, 150), "references": (1800, 120), "disclosures": (21600, 420),
          "rotation": (3600, 90), "public": (3600, 180), "backfill": (1800, 300), "breadth": (21600, 180)}


def signature(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def account_identity(snapshot):
    fields = ["symbol", "quantity", "avg_cost", "asset_type", "ipo_status", "issue_price", "expected_list_date",
              "directions", "position_role", "invalid_condition", "target_max_weight", "user_plan", "risk_flags"]
    return signature({"positions": sorted([{k: p.get(k) for k in fields} for p in snapshot.get("positions", [])], key=lambda p: p["symbol"]),
                      **{k: snapshot.get(k) for k in ["cash_available", "repo_amount", "account_actual_total_cost", "risk_limits"]}})


def load_status():
    status = s.read(s.ROOT / "status.json", {"status": "never_run", "steps": {}})
    if status.get("status") == "running":
        try:
            with s.exclusive(s.ROOT / "sync.lock"):
                status = {**status, "status": "interrupted", "reason": "Previous process exited; next run resumes from stage caches"}
        except BlockingIOError:
            pass
    return status


def due(name, previous, inputs, target, force=False):
    if force or previous.get("inputs") != inputs or previous.get("target_date") != target:
        return True
    raw = previous.get("finished_at")
    if not raw:
        return True
    try:
        elapsed = (s.now() - datetime.fromisoformat(raw)).total_seconds()
    except (ValueError, TypeError):
        return True
    ttl = POLICY[name][0] if previous.get("status") == "complete" else 900
    if name == "market" and previous.get("status") == "complete":
        at = s.now()
        if at.weekday() >= 5 or not 9 <= at.hour < 16:
            ttl = 21600
    return elapsed >= ttl


def run_stage(name, request, timeout):
    request_path = s.ROOT / "worker_request.json"
    result_path = s.ROOT / "worker_result.json"
    partial_path = s.ROOT / "worker_progress.json"
    request = {**request, "request_id": uuid4().hex}
    s.write(request_path, request)
    result_path.unlink(missing_ok=True)
    partial_path.unlink(missing_ok=True)
    log_path = s.ROOT / "worker.log"
    if log_path.exists() and log_path.stat().st_size > 2_000_000:
        log_path.replace(s.ROOT / "worker.previous.log")
    env = {**os.environ, "PYTHONUTF8": "1", "STOCK_PILOT_DATA_ONLY": "1"}
    started = time.monotonic()
    with log_path.open("a", encoding="utf-8") as log:
        child = subprocess.Popen([sys.executable, "-u", str(s.BACKEND / "scripts" / "sync_data.py"),
                                  "--worker", name], cwd=s.BACKEND, env=env, stdout=log, stderr=log)
        try:
            while child.poll() is None:
                if time.monotonic() - started > timeout:
                    child.kill()
                    child.wait()
                    data = s.read(partial_path, {})
                    return {**data, "status": "timed_out", "reason": f"Stage exceeded {timeout}s; completed partial results retained"}
                status = load_status()
                status["heartbeat_at"] = s.now().isoformat()
                partial = s.read(partial_path, {})
                status["progress"] = {"stage": name, "items": len(partial.get("items", [])),
                                      "documents": len(partial.get("documents", [])),
                                      "failures": len(partial.get("failures", [])), "timeout_seconds": timeout,
                                      **{key: partial[key] for key in ("completed_count", "total_symbols", "remaining_count") if key in partial}}
                s.write(s.ROOT / "status.json", status)
                time.sleep(1)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
            if name in {"cold", "backfill"}:
                from app.core.data_updater import UPDATE_LOCK_FILE
                owner = s.read(UPDATE_LOCK_FILE, {})
                if isinstance(owner, dict) and owner.get("owner") == request["request_id"]:
                    UPDATE_LOCK_FILE.unlink(missing_ok=True)
    return s.read(result_path, {"status": "failed", "reason": f"Worker exited {child.returncode}; see worker.log"})


def worker(name):
    # Enforce the boundary even if a future adapter accidentally imports an LLM call.
    from openai.resources.chat.completions import Completions, AsyncCompletions
    def blocked(*args, **kwargs):
        raise RuntimeError("LLM calls are prohibited in the data-only worker")
    classes = [Completions, AsyncCompletions]
    try:
        from openai.resources.responses import Responses, AsyncResponses
        classes.extend([Responses, AsyncResponses])
    except ImportError:
        pass
    for cls in classes:
        cls.create = blocked
    from app.data_sync.collectors import STAGES
    try:
        data = STAGES[name](s.read(s.ROOT / "worker_request.json"), lambda value: s.write(s.ROOT / "worker_progress.json", value))
    except Exception as exc:
        data = {**s.read(s.ROOT / "worker_progress.json", {}), "status": "failed", "reason": str(exc)[:500]}
    s.write(s.ROOT / "worker_result.json", data)


def run(force=False, stages=None, executor=run_stage, scope="full"):
    from app.data_sync.collectors import universe
    from app.core.data_updater import get_last_trading_date
    with s.exclusive(s.ROOT / "sync.lock"):
        deadline = time.monotonic() + 1200
        selection = [name for name in POLICY if scope != "tracked" or name != "backfill"] if stages is None else stages
        if any(name not in POLICY for name in selection):
            raise ValueError("Unknown data stage")
        sources = universe()
        if scope not in {"full", "tracked"}:
            raise ValueError("Unknown collection scope")
        if scope == "tracked":
            sources["cold"] = list(sources["tracked"])
        inputs = signature({**{k: sources[k] for k in ["tracked", "stocks", "cold"]}, "collector_revision": "coverage-v1-financial-v3"})
        account_fingerprint = account_identity(sources["account"])
        target = get_last_trading_date().isoformat()
        calendar = s.read(s.ROOT / "trading_calendar.json", {})
        if calendar.get("checked_on") == s.now().date().isoformat():
            target = max((d for d in calendar["sessions"] if d <= target), default=target)
        status = {"status": "running", "started_at": s.now().isoformat(), "steps": {},
                  "model_calls": 0, "holdings_modified": False, "target_date": target, "scope": scope}
        s.write(s.ROOT / "status.json", status)
        for name in selection:
            path = s.ROOT / f"{name}.json"
            previous = s.read(path, {})
            if not due(name, previous, inputs, target, force):
                status["steps"][name] = {"status": "cached", "source_status": previous.get("status"), "finished_at": previous.get("finished_at")}
                continue
            remaining = int(deadline - time.monotonic())
            if remaining <= 5:
                status["steps"][name] = {"status": "deferred", "reason": "本轮20分钟预算已用完，下一次启动或定时任务继续"}
                continue
            status["stage"] = name
            s.write(s.ROOT / "status.json", status)
            started = s.now().isoformat()
            try:
                data = executor(name, {"universe": sources, "target_date": target}, min(POLICY[name][1], remaining))
            except Exception as exc:
                data = {"status": "failed", "reason": str(exc)[:500]}
            if name == "cold" and data.get("target_date"):
                target = data["target_date"]
            envelope = {"status": data.get("status", "failed"), "started_at": started,
                        "finished_at": s.now().isoformat(), "target_date": target, "inputs": inputs, "data": data}
            s.write(path, envelope)
            if envelope["status"] == "complete":
                s.write(s.ROOT / f"{name}.last_success.json", envelope)
            status["steps"][name] = {k: envelope[k] for k in ["status", "started_at", "finished_at"]}
        latest_account = universe()["account"]
        changed = account_identity(latest_account) != account_fingerprint
        bundle = {"schema_version": "1.0", "generated_at": s.now().isoformat(), "account": sources["account"] if changed else latest_account,
                  "account_changed_during_collection": changed, "target_date": target,
                  "calendar_verified": s.read(s.ROOT / "trading_calendar.json", {}).get("checked_on") == s.now().date().isoformat(),
                  "sources": {name: s.read(s.ROOT / f"{name}.json", {"status": "not_collected"}) for name in POLICY},
                  "model_calls": 0, "holdings_modified": False, "scope": scope,
                  "boundaries": ["No brokerage sync, screenshot OCR, order execution or investment inference",
                                 "Uncollected/failed/stale sources are not bearish evidence",
                                 "Full-market breadth is local covered-stock aggregation, not official exchange totals",
                                 "No automatic future event-calendar or comprehensive industry/geopolitical news refresh"]}
        s.write(s.ROOT / "latest.json", bundle)
        deferred = any(step.get("status") == "deferred" for step in status["steps"].values())
        status.update(status="partial" if changed or deferred or any(v.get("status") != "complete" for v in bundle["sources"].values()) else "complete",
                      finished_at=s.now().isoformat(), target_date=target, account_changed_during_collection=changed)
        s.write(s.ROOT / "status.json", status)
        return status


def prepare_discussion():
    """Explicit handoff only; periodic updates never invalidate an in-progress discussion."""
    from app.agent_review import discussion as d
    from app.agent_review import plans
    from app.portfolio.service import portfolio_service
    with d.LOCK:
        before = d.account_fingerprint()
        bundle = s.read(s.ROOT / "latest.json")
        if not bundle:
            raise ValueError("Run data sync before preparing a discussion")
        snapshot = portfolio_service.load_snapshot().model_dump(mode="json")
        if account_identity(snapshot) != account_identity(bundle["account"]):
            raise ValueError("Account has changed; run data sync again")
        pending_result = d.current("response.json").exists() and d.inspect().get("status") != "confirmed"
        if pending_result or d.current("supplement.json").exists():
            raise ValueError("Pending response/supplement exists; resolve it before refreshing the discussion")
        old = d.read(d.current("manifest.json"))
        prior = d.read(d.current("context.json"), {})
        catalog = []
        for name, envelope in bundle["sources"].items():
            catalog.append({"evidence_ref": f"objective:{name}", "scope": "objective_data",
                            "facts": envelope, "boundary": "Check collection status and observation dates; no model verification"})
        context = {"account": snapshot, "evidence": {"evidence_catalog": catalog},
                   "objective_data": {k: bundle[k] for k in ["generated_at", "target_date", "calendar_verified", "boundaries"]},
                   "records": d.state(), "legacy_memory": plans.view(),
                   "supplements": prior.get("supplements", []),
                   "retained_context_note": "Previous supplements retained with their ORIGINAL dates; not refreshed automatically"}
        if before != d.account_fingerprint():
            raise ValueError("Account changed while preparing context; retry after syncing")
        return d.publish(context, (old or {}).get("question") or "Review current holdings, changes and prior plans using dated objective evidence.",
                         before, old, "refresh" if old else "new")
