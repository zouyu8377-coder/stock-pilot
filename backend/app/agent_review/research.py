"""Read-only research dossiers plus user decision annotations, never trade execution."""
import hashlib
import json
import re
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.portfolio.service import portfolio_service
from app.disclosure_verification.service import load_disclosure_verification, _symbol_context

ROOT = Path(__file__).resolve().parents[2] / "data" / "agent_workbench"
_lock = threading.RLock()
TZ = ZoneInfo("Asia/Shanghai")


def now():
    return datetime.now(TZ).isoformat()


def instant(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=TZ)).timestamp()
    except (ValueError, TypeError):
        return 0


def symbol(value):
    match = re.search(r"\d{6}", str(value or ""))
    return match.group() if match else ""


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def account_fingerprint():
    snapshot = portfolio_service.load_snapshot().model_dump(mode="json")
    fields = ("symbol", "quantity", "avg_cost", "directions", "position_role", "invalid_condition", "target_max_weight", "user_plan")
    return digest({"positions": sorted([{k: p.get(k) for k in fields} for p in snapshot["positions"]], key=lambda p: p["symbol"]),
                   **{k: snapshot.get(k) for k in ("cash_available", "repo_amount", "account_actual_total_cost", "risk_limits")}})


def _read_annotations():
    try:
        return json.loads((ROOT / "decisions.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _question_state(question, verification, task=None):
    normal = lambda text: re.sub(r"\s+", "", str(text or ""))
    matches = [i for i in verification.get("current_items", []) if normal(i.get("question")) == normal(question)]
    verified = [i for i in matches if i.get("quote_verified") is True and i.get("status") != "not_found"]
    checked = verification.get("index_checked_at") or verification.get("generated_at")
    failed = task and task.get("status") in {"failed", "retry_wait", "manual_required"}
    status = "body_verified" if verified else "material_found" if verification.get("documents") else "not_checked"
    # A completed index scan says nothing about whether the business question was answered.
    if not verified and verification.get("trigger") == "announcement_index_no_change":
        status = "checked_no_new"
    if verification.get("status") in {"unavailable", "model_unavailable"} or (failed and instant(task.get("updated_at")) >= instant(checked)):
        status = "source_blocked"
    try:
        stale = not checked or (datetime.now(TZ) - datetime.fromisoformat(checked.replace("Z", "+00:00")).astimezone(TZ)).total_seconds() > 86400
    except ValueError:
        stale = True
    return {"question": question, "status": status, "checked_at": checked, "check_stale": stale,
            "answer": "；".join(str(i.get("conclusion") or "") for i in verified),
            "sources": [{k: i.get(k) for k in ("source_title", "source_url", "announced_at", "quote", "page", "status")} for i in verified],
            "blocker": (task.get("error") if failed else verification.get("reason")) or "",
            "next_step": "检查新增披露及反证" if verified else "补取与该问题直接相关的原文；未回答不等于利空"}


def build_workbench():
    from app.agent_review.service import load_latest_review
    from app.agent_review.tasks import list_tasks
    snapshot = portfolio_service.load_snapshot()
    latest = load_latest_review() or {}
    tasks = list_tasks(limit=500)
    annotations = _read_annotations()
    dossiers, actions = [], []
    groups = latest.get("review") or {}
    candidates = [*groups.get("risks", []), *groups.get("watch_items", []), *groups.get("opportunities", [])]
    current_fingerprint = account_fingerprint()
    stale = latest.get("account_fingerprint") != current_fingerprint
    try:
        analysis_stale = datetime.fromisoformat(latest["completed_at"].replace("Z", "+00:00")).astimezone(TZ).date() != datetime.now(TZ).date()
    except (KeyError, ValueError, TypeError):
        analysis_stale = True
    for position in snapshot.positions:
        if position.quantity <= 0:
            continue
        code = symbol(position.symbol)
        findings = load_disclosure_verification(code) or {}
        related = [t for t in tasks if code in [symbol(s) for s in t.get("target_symbols", [])]]
        related.sort(key=lambda t: instant(t.get("updated_at")), reverse=True)
        disclosure_task = next((t for t in related if (t.get("tool") or {}).get("name") == "disclosure_snapshot"), None)
        questions = [_question_state(q, findings, disclosure_task) for q in _symbol_context(code)["questions"]]
        dossier = {"symbol": code, "name": position.name, "directions": position.directions,
                   "questions": questions, "documents": findings.get("documents", [])[-8:],
                   "historical_findings": findings.get("historical_items", [])[-5:],
                   "tasks": [{k: t.get(k) for k in ("task_id", "task", "status", "error", "next_retry_at")} for t in related[:5]]}
        dossiers.append(dossier)
        matched = [i for i in candidates if code in [symbol(s) for s in i.get("target_symbols", [])]
                   or position.name and position.name in i.get("subject", "")]
        if not matched:
            continue
        ranking = {"reduce": 0, "watch": 1, "wait": 2, "hold": 3, "increase": 4}
        matched.sort(key=lambda i: ranking.get(i.get("suggested_action"), 1))
        primary = matched[0]
        version = digest([{k: i.get(k) for k in ("conclusion", "action_semantics", "trigger_condition", "confidence")} for i in matched])
        saved = annotations.get(code, {})
        changed = bool(saved and saved.get("version") != version)
        actions.append({"id": code, "symbol": code, "name": position.name, "version": version,
                        "primary": primary, "related": matched[1:], "run_id": latest.get("run_id"),
                        "analyzed_at": latest.get("completed_at"), "account_changed": stale,
                        "needs_refresh": stale or analysis_stale,
                        "state": "pending" if changed else saved.get("state", "pending"),
                        "note": saved.get("note", ""), "changed_since_response": changed,
                        "history": saved.get("history", [])[-5:],
                        "unanswered": sum(q["status"] != "body_verified" for q in questions)})
    from app.agent_review import automation
    queued = automation._read_json(automation.AUTOMATION_DIR / "account_update_queue.json", {})
    return {"checked_at": now(), "account_fingerprint": current_fingerprint, "actions": actions, "dossiers": dossiers,
            "account_update": queued,
            "run_id": latest.get("run_id"), "analyzed_at": latest.get("completed_at"), "account_changed": stale,
            "needs_refresh": stale or analysis_stale,
            "boundary": "已核验表示引用可追溯，不代表投资判断正确；未发现材料不代表不存在风险。"}


def respond_to_action(action_id, version, state, note):
    if state not in {"pending", "monitoring", "dismissed"}:
        raise ValueError("仅支持待处理、设为监控或暂不采纳；不直接记录成交")
    if state == "dismissed" and not note.strip():
        raise ValueError("请填写暂不采纳的原因")
    with _lock:
        workbench = build_workbench()
        action = next((a for a in workbench["actions"] if a["id"] == action_id), None)
        if not action or action["version"] != version or action["needs_refresh"]:
            raise ValueError("账户或建议已变化，请更新分析后重新确认")
        payload = _read_annotations()
        history = payload.get(action_id, {}).get("history", [])
        entry = {"version": version, "state": state, "note": note.strip(), "at": now(), "run_id": action["run_id"]}
        payload[action_id] = {**entry, "history": [*history, entry][-50:]}
        ROOT.mkdir(parents=True, exist_ok=True)
        temp = ROOT / "decisions.tmp"
        temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temp.replace(ROOT / "decisions.json")
        return entry


def plan_research_tasks(origin_run_id, max_tasks):
    from app.agent_review.tasks import sync_review_tasks
    workbench = build_workbench()
    candidates = []
    for dossier in workbench["dossiers"]:
        gaps = [q for q in dossier["questions"] if q["status"] != "body_verified" or q["check_stale"]]
        if not gaps:
            continue
        candidates.append({"priority": "high", "subject": dossier["name"],
            "task": f"核验{dossier['symbol']}行情与资金证据" if dossier["symbol"].startswith(("15", "16", "51", "56", "58")) else f"核验{dossier['symbol']}经营问题与新增披露正文",
            "reason": "补充可能改变持仓立场的经营事实，不以提高评分为目标",
            "target_symbols": [dossier["symbol"]], "evidence_type": "market_snapshot" if dossier["symbol"].startswith(("15", "16", "51", "56", "58")) else "announcement",
            "missing_evidence": [q["question"] for q in gaps[:4]],
            "success_criteria": "回答登记问题，提供来源、日期与可在原文找到的引文；无法回答时保留缺口"})
    if candidates:
        return sync_review_tasks({"run_id": origin_run_id, "review": {"verification_tasks": candidates[:max_tasks]}})
    return []
