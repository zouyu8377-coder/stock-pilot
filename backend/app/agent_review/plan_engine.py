"""Deterministic plan collection/monitoring. Never calls an LLM or places orders."""
import math
import operator
import threading
from datetime import datetime, timedelta

from app.agent_review import plans, research

RUN_LOCK = threading.Lock()
OPS = {"gt": operator.gt, "gte": operator.ge, "lt": operator.lt, "lte": operator.le}
WORKER = None
STATUS = {"status": "idle"}


def settings():
    return {"enabled": False, "external_only": True, "interval_minutes": 60,
            **plans.read(plans.ROOT / "engine_settings.json", {})}


def configure(enabled, external_only):
    with plans.LOCK:
        value = {**settings(), "enabled": bool(enabled), "external_only": bool(external_only)}
        plans.write(plans.ROOT / "engine_settings.json", value)
    return value


def board():
    return plans.read(plans.ROOT / "monitor.json", {"revision": 0, "plans": [], "research": [], "checked_at": None})


def status():
    return {**STATUS, "settings": settings(), "board": board()}


def collect(tool, symbols):
    # These adapters fetch data only. Do not use disclosure_snapshot: it invokes an LLM.
    if tool == "market":
        from app.agent_review.tasks import _stock_snapshot
        return _stock_snapshot({"symbols": symbols})
    if tool == "disclosure":
        from app.disclosure_verification.service import _fetch_cninfo_announcements, _download_pdf, _extract_pdf_pages, _select_relevant_text, _symbol_context
        now = datetime.now(research.TZ)
        documents, failures = [], []
        for symbol in symbols:
            rows = _fetch_cninfo_announcements(symbol, (now - timedelta(days=90)).date().isoformat(), now.date().isoformat(), max_pages=2)
            rows.sort(key=lambda r: str(r.get("announced_at") or ""), reverse=True)
            for row in rows[:2]:
                try:
                    pages = _extract_pdf_pages(_download_pdf(row["pdf_url"]))
                    text = _select_relevant_text(pages, _symbol_context(symbol)["keywords"], max_chars=8000)
                    if not text:
                        raise ValueError("PDF没有可提取正文")
                    documents.append({**row, "symbol": symbol, "selected_text": text})
                except Exception as exc:
                    failures.append({"symbol": symbol, "title": row.get("title"), "error": str(exc)[:300]})
        return {"retrieved_at": research.now(), "documents": documents, "failures": failures,
                "boundary": "近90日、最多2页索引及每标的2份PDF选段，不是完整文献覆盖。正文仅提取，尚未由模型判断投资含义。"}
    if tool == "events":
        from app.agent_review.tasks import _event_snapshot
        return _event_snapshot({"symbols": symbols})
    raise ValueError("缺少可执行取证工具，需要外部研究或用户补充")


def condition_result(condition, market, account, default_symbol=""):
    symbol = condition.get("symbol") or default_symbol
    metric = condition["metric"]
    value = None
    as_of = None
    reason = ""
    if metric in {"cash_ratio_pct", "invested_ratio_pct"}:
        value = account.get(metric)
        as_of = account.get("as_of")
        reason = "账户估值所需行情不完整" if account.get("missing") else ""
    elif metric == "weight_pct":
        value = account.get("weights", {}).get(symbol)
        as_of = account.get("as_of")
        reason = "账户估值所需行情不完整" if account.get("missing") else ""
    else:
        rows = (market.get(symbol) or {}).get("snapshots", [])
        history = next((r.get("history", {}) for r in rows if r.get("symbol") == symbol), {})
        value, as_of = history.get(metric), history.get("latest_date")
        if not as_of or as_of != history.get("target_date", datetime.now(research.TZ).date().isoformat()):
            reason = "日K未匹配最近完整交易日（可能陈旧或盘中未完成），不能判断条件"
    if reason or value is None or not math.isfinite(float(value)):
        return {**condition, "symbol": symbol, "state": "unknown", "value": value, "as_of": as_of,
                "reason": reason or "所需字段缺失"}
    hit = OPS[condition["operator"]](float(value), condition["threshold"])
    return {**condition, "symbol": symbol, "state": "met" if hit else "not_met", "value": value, "as_of": as_of}


def account_values(snapshot, market):
    values = {}
    missing = False
    for row in snapshot.get("positions", []):
        if float(row.get("quantity") or 0) <= 0:
            continue
        symbol = research.symbol(row["symbol"])
        data = condition_result({"metric": "latest_close", "operator": "gt", "threshold": 0}, market, {}, symbol)
        if data["state"] == "unknown" or not data.get("value") or data["value"] <= 0:
            missing = True
            continue
        values[symbol] = float(row["quantity"]) * data["value"]
    cash = float(snapshot.get("cash_available") or 0)
    assets = sum(values.values()) + cash + float(snapshot.get("repo_amount") or 0)
    return {"missing": missing or assets <= 0, "as_of": research.now(),
            "cash_ratio_pct": cash / assets * 100 if assets else None,
            "invested_ratio_pct": sum(values.values()) / assets * 100 if assets else None,
            "weights": {s: v / assets * 100 for s, v in values.items()} if assets else {}}


def plan_changes(plan, snapshot):
    from app.agent_review import outcomes
    confirmed = []
    for action in outcomes._read(outcomes.ACTIONS_PATH):
        if not outcomes._action_learning_eligible(action) or research.instant(action.get("snapshot_time")) < research.instant(plan["at"]):
            continue
        if plan["level"] == "symbol" and research.symbol(action.get("symbol")) != plan["target"]:
            continue
        if plan["level"] == "direction":
            eligible = set(plan["content"].get("symbols", [])) | {research.symbol(p["symbol"]) for p in [*snapshot.get("positions", []), *plan.get("baseline", {}).get("positions", [])] if plan["target"] in (p.get("directions") or [])}
            if research.symbol(action.get("symbol")) not in eligible:
                continue
        confirmed.append({k: action.get(k) for k in ("action_id", "symbol", "name", "snapshot_time", "action_type", "quantity_delta", "source", "user_reason", "ai_strategy_comparison", "outcome")})
    baseline = plan.get("baseline")
    if not baseline:
        return {"status": "baseline_missing", "items": [], "boundary": "历史计划缺少当时快照，不用当前数据回填。"}
    before = {research.symbol(p["symbol"]): p for p in baseline.get("positions", [])}
    after = {research.symbol(p["symbol"]): p for p in snapshot.get("positions", [])}
    items = []
    for symbol in sorted(before.keys() | after.keys()):
        if plan["level"] == "symbol" and symbol != plan["target"]:
            continue
        if plan["level"] == "direction":
            directions = (before.get(symbol, {}).get("directions") or []) + (after.get(symbol, {}).get("directions") or [])
            if plan["target"] not in directions and symbol not in plan["content"].get("symbols", []):
                continue
        old, new = float(before.get(symbol, {}).get("quantity") or 0), float(after.get(symbol, {}).get("quantity") or 0)
        if old != new:
            stance = plan["content"]["stance"]
            conflict = (new > old and stance in {"reduce", "exit", "wait"}) or (new < old and stance == "increase")
            items.append({"symbol": symbol, "before": old, "after": new, "delta": new - old,
                          "assessment": "需讨论与原计划是否一致" if conflict else "净变化已记录，执行意图待确认"})
    return {"status": "observed", "items": items, "confirmed_operations": confirmed[-30:], "since": plan["at"], "through": snapshot.get("snapshot_time"),
            "boundary": "净变化不是逐笔成交，不推断成交价、操作时间或成功失败；需结合当时理由与后续结果复盘。"}


def performance_review(plan):
    if plan["level"] != "symbol":
        return {"status": "discussion_required", "reason": "账户和行业归因需结合现金流、方向成分与操作记录讨论，不用单票收益替代。"}
    from app.collector.router import collector
    from app.core.data_updater import get_last_trading_date
    import pandas as pd
    def series(symbol):
        frame = collector.get_history(symbol, limit=5000).copy()
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
        return frame.dropna(subset=["date", "close"]).sort_values("date").drop_duplicates("date")
    try:
        frame = series(plan["target"])
        plan_at = datetime.fromisoformat(plan["at"]).astimezone(research.TZ)
        start_date = get_last_trading_date(ref_date=plan_at.date(), ref_time=plan_at.time()).isoformat()
        prior = frame[frame.date <= start_date]
        after = frame[(frame.date > start_date) & (frame.date <= get_last_trading_date().isoformat())]
        if prior.empty or after.empty or float(prior.iloc[-1].close) <= 0:
            return {"status": "waiting", "reason": "尚无可对比的计划后完整交易日"}
        first, last = prior.iloc[-1], after.iloc[-1]
        result = {"status": "provisional" if len(after) < 5 else "ready_for_review", "trading_days": len(after),
                  "baseline_date": first.date, "through": last.date,
                  "price_return_pct": round((float(last.close) / float(first.close) - 1) * 100, 2),
                  "boundary": "以计划当日或此前日K为参照，不是成交成本或账户收益；价格变化不能单独判定决策成败，复权口径也须核对。"}
        benchmark = series("510300")
        b0, b1 = benchmark[benchmark.date == first.date], benchmark[benchmark.date == last.date]
        if not b0.empty and not b1.empty and float(b0.iloc[-1].close) > 0:
            result["benchmark_return_pct"] = round((float(b1.iloc[-1].close) / float(b0.iloc[-1].close) - 1) * 100, 2)
            result["relative_return_pct"] = round(result["price_return_pct"] - result["benchmark_return_pct"], 2)
        return result
    except Exception as exc:
        return {"status": "unavailable", "reason": str(exc)[:200]}


def run():
    global STATUS
    if not RUN_LOCK.acquire(blocking=False):
        return status()
    STATUS = {"status": "running", "started_at": research.now(), "completed": 0, "total": 0, "detail": "准备计划监控"}
    try:
        with plans.LOCK:
            saved = plans.state()
            fingerprint = research.account_fingerprint()
            snapshot = research.portfolio_service.load_snapshot().model_dump(mode="json")
        prior = board()
        prior_research = {r["id"]: r for r in prior.get("research", [])}
        needs_account_prices = any(c["metric"] in {"weight_pct", "cash_ratio_pct", "invested_ratio_pct"}
                                   for p in saved["plans"].values() for c in p["content"].get("conditions", []))
        needs_account_prices = needs_account_prices or any((n.get("answer_condition") or {}).get("metric") in {"weight_pct", "cash_ratio_pct", "invested_ratio_pct"} for n in saved["needs"] if n["status"] == "open")
        codes = {research.symbol(p["symbol"]) for p in snapshot.get("positions", []) if p.get("quantity", 0) > 0} if needs_account_prices else set()
        for plan in saved["plans"].values():
            for c in plan["content"].get("conditions", []):
                code = c.get("symbol") or (plan["target"] if plan["level"] == "symbol" else "")
                if code:
                    codes.add(code)
        market, results = {}, []
        active = [n for n in saved["needs"] if n["owner"] == "platform" and n["status"] == "open"]
        eligible = [n for n in active if research.instant(prior_research.get(n["id"], {}).get("next_attempt_at")) <= datetime.now(research.TZ).timestamp()]
        eligible.sort(key=lambda n: (research.instant(prior_research.get(n["id"], {}).get("checked_at")), {"high": 0, "medium": 1, "low": 2}.get(n.get("priority"), 1)))
        actionable = eligible[:5]
        scheduled_ids = {n["id"] for n in actionable}
        results = [prior_research[n["id"]] for n in active if n["id"] not in scheduled_ids and n["id"] in prior_research]
        STATUS["total"] = len(codes) + len(actionable)
        for code in sorted(codes):
            STATUS["detail"] = f"读取 {code} 日K证据"
            try:
                market[code] = collect("market", [code])
            except Exception as exc:
                market[code] = {"error": str(exc)[:500]}
            STATUS["completed"] += 1
        for need in actionable:
            STATUS["detail"] = f"取证：{need['question']}"
            old = prior_research.get(need["id"], {})
            if old.get("next_attempt_at") and research.instant(old["next_attempt_at"]) > datetime.now(research.TZ).timestamp():
                results.append(old)
                STATUS["completed"] += 1
                continue
            row = {"id": need["id"], "question": need["question"], "level": need["level"], "target": need["target"],
                   "evidence_ref": f"plan:need:{need['id']}", "checked_at": research.now()}
            tool = need.get("tool", "none")
            symbols = need.get("symbols") or ([need["target"]] if need["level"] == "symbol" else [])
            account_question = tool == "market" and (need.get("answer_condition") or {}).get("metric") in {"cash_ratio_pct", "invested_ratio_pct"}
            if account_question:
                symbols = sorted(codes)
            try:
                if tool != "events" and not symbols and not account_question:
                    raise ValueError("需要明确证券代码，不能猜测行业代表标的")
                if tool == "market":
                    payload = {"snapshots": []}
                    for code in symbols:
                        if code not in market:
                            market[code] = collect("market", [code])
                        payload["snapshots"].extend(market[code].get("snapshots", []))
                    if not payload["snapshots"] and not account_question:
                        raise ValueError("未取得行情数据")
                else:
                    payload = collect(tool, symbols)
                row.update(state="material_ready", data=payload,
                           answer="已取得材料，尚需核验其能否回答经营问题；不是方向性结论")
                if tool == "disclosure" and (not payload.get("documents") or payload.get("failures")):
                    row.update(state="incomplete", answer="部分公告来源未成功返回，不能视为材料完整")
                if tool == "market" and need.get("answer_condition"):
                    answer = condition_result(need["answer_condition"], market, account_values(snapshot, market), symbols[0] if symbols else "")
                    row.update(state="answered" if answer["state"] != "unknown" else "incomplete", answer=answer)
                row["next_attempt_at"] = (datetime.now(research.TZ) + timedelta(hours=6)).isoformat()
            except Exception as exc:
                failures = int(old.get("failures", 0)) + 1
                row.update(state="blocked", error=str(exc)[:500], failures=failures,
                           next_attempt_at=(datetime.now(research.TZ) + timedelta(minutes=min(360, 30 * 2 ** min(failures, 4)))).isoformat())
            results.append(row)
            STATUS["completed"] += 1
        account = account_values(snapshot, market)
        summaries = []
        for scope, plan in saved["plans"].items():
            conditions = [condition_result(c, market, account, plan["target"] if plan["level"] == "symbol" else "") for c in plan["content"].get("conditions", [])]
            states = [c["state"] for c in conditions]
            mode = plan["content"].get("condition_mode", "all")
            met = bool(states) and (all(s == "met" for s in states) if mode == "all" else any(s == "met" for s in states))
            unknown = not met and "unknown" in states and (mode == "any" or "not_met" not in states)
            due = plan["content"]["review_on"] <= datetime.now(research.TZ).date().isoformat()
            changed = plan["account_fingerprint"] != fingerprint
            reason = "计划条件成立，需要重新讨论" if met else "证据不足，无法判定计划条件" if unknown else "已到复查日期" if due else "账户变化，需复核计划" if changed else "未发现已登记条件触发"
            summaries.append({"scope": scope, "target": plan["target"], "level": plan["level"], "version": plan["version"],
                "state": "discussion_required" if met or due or changed else "evidence_missing" if unknown else "monitoring",
                "reason": reason, "conditions": conditions, "mode": mode,
                "next_action": plan["content"]["next_check"], "triggered_actions": [c["action"] for c in conditions if c["state"] == "met"] if met else [],
                "operation_review": plan_changes(plan, snapshot), "performance_review": performance_review(plan)})
        def stable(value):
            if isinstance(value, dict):
                return {k: stable(v) for k, v in value.items() if k not in {"checked_at", "next_attempt_at", "retrieved_at", "recorded_at", "generated_at", "fetched_at"} and not (k == "as_of" and isinstance(v, str) and "T" in v)}
            if isinstance(value, list):
                return [stable(v) for v in value]
            return value
        evidence_signature = research.digest(stable({"plans": summaries, "research": results}))
        revision = prior.get("revision", 0) + int(evidence_signature != prior.get("signature"))
        summaries.sort(key=lambda p: ({"discussion_required": 0, "evidence_missing": 1, "monitoring": 2}[p["state"]], {"account": 0, "direction": 1, "symbol": 2}[p["level"]]))
        value = {"revision": revision, "signature": evidence_signature, "checked_at": research.now(), "plans": summaries,
                 "plan_revision": saved["revision"],
                 "queued_research_count": max(0, len(eligible) - len(actionable)),
                 "research": results, "model_calls": 0, "account_fingerprint": fingerprint,
                 "boundary": "仅检查已登记条件；未触发不代表账户安全。计划与经验修改须用户确认。"}
        with plans.LOCK:
            if saved["revision"] != plans.state()["revision"] or fingerprint != research.account_fingerprint():
                raise ValueError("取证期间账户或计划变化，结果未发布，请重新检查")
            plans.write(plans.ROOT / "monitor.json", value)
            if revision != prior.get("revision", 0):
                history = plans.read(plans.ROOT / "monitor_history.json", [])
                plans.write(plans.ROOT / "monitor_history.json", [*history, value][-100:])
        STATUS.update(status="completed", detail="本地检查完成，需要判断的事项可导出给外部模型", completed_at=research.now())
    except Exception as exc:
        STATUS.update(status="failed", error=str(exc)[:1000], completed_at=research.now())
    finally:
        RUN_LOCK.release()
    return status()


def start():
    global WORKER
    with plans.LOCK:
        if WORKER and WORKER.is_alive():
            return status()
        WORKER = threading.Thread(target=run, daemon=True, name="plan-local-monitor")
        WORKER.start()
    return status()


def tick():
    config = settings()
    if not config["enabled"] or datetime.now(research.TZ).weekday() >= 5:
        return
    last = STATUS.get("completed_at") or board().get("checked_at")
    if STATUS.get("status") == "failed" and last and datetime.now(research.TZ).timestamp() - research.instant(last) < 600:
        return
    changed = board().get("plan_revision") != plans.state()["revision"] or board().get("account_fingerprint") != research.account_fingerprint()
    if changed or not last or datetime.now(research.TZ).timestamp() - research.instant(last) >= config["interval_minutes"] * 60:
        start()
