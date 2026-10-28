import json
import os
import subprocess
import sys
import threading
import time
from copy import deepcopy
from datetime import datetime
from uuid import uuid4

from app.data_sync import service as sync, storage as ds
from app.investment_agents import data_agent, providers, store as s
from app.investment_agents.schemas import Analysis, Start


def summary(run):
    value = deepcopy(run)
    value["account_changed"] = value.get("account_fingerprint") != data_agent.fingerprint()
    value["elapsed_seconds"] = max(0, int((s.now() - datetime.fromisoformat(value["created_at"])).total_seconds()))
    return value


def status():
    pointer = s.read(s.ROOT / "current.json", {})
    run = s.load(pointer["run_id"]) if pointer.get("run_id") else None
    if run and run["status"] not in s.TERMINAL and run.get("pid") and not ds.process_alive(run["pid"]):
        with s.LOCK:
            run = s.load(run["run_id"])
            if run["status"] not in s.TERMINAL:
                run.update(status="failed", error="运行进程已退出；已完成资料仍保留，请重新发起。")
                s.event(run, "coordinator", "任务中断", run["error"])
                s.save(run)
    from app.investment_agents.account_updates import history
    return {"run": summary(run) if run else None, "settings": s.settings(), "providers": providers.availability(),
            "collection": sync.load_status(), "confirmed": s.memories()["results"][-1:] or [], "account_updates": history()}


def start(body: Start, launch=True):
    if not body.consent:
        raise ValueError("需要允许将本次分析资料发送给所选模型；不会执行交易")
    available = providers.availability()
    if body.provider == "codex" and not available["codex"]["installed"]:
        raise ValueError("本机未找到 Codex CLI")
    if body.provider == "api" and not (available["api"]["enabled"] and available["api"]["configured"]):
        raise ValueError("API 未配置或未启用；不会隐式调用旧服务")
    with s.LOCK:
        pointer = s.read(s.ROOT / "current.json", {})
        if pointer.get("run_id"):
            old = s.load(pointer["run_id"])
            if old["status"] not in s.TERMINAL and (not old.get("pid") or ds.process_alive(old["pid"])):
                raise ValueError("已有任务运行中，可查看进度或停止；不会重复发起模型调用")
            if old["status"] == "awaiting_confirmation":
                raise ValueError("上一份分析尚待确认，请确认或放弃后再运行")
        run_id = uuid4().hex
        run = {"run_id": run_id, "status": "queued", "created_at": s.now().isoformat(), "updated_at": s.now().isoformat(),
               "question": body.question, "provider": body.provider, "refresh": body.refresh, "max_model_calls": body.max_model_calls,
               "config": s.settings(),
               "model_calls": 0, "tool_requests": 0, "max_tool_requests": 4, "tokens": {}, "model_usage": [], "events": [],
               "account_fingerprint": data_agent.fingerprint(), "memory_revision": s.memories()["revision"], "consent_at": s.now().isoformat(),
               "context_version": 0, "context_fingerprint": None, "report": None, "report_digest": None,
               "data_summary": None, "error": None, "cancel_requested": False, "pid": None}
        s.event(run, "coordinator", "真实投资分析任务已建立", "Agent1负责资料，Agent2负责推理；不会执行交易。")
        s.save(run)
        s.write(s.ROOT / "current.json", {"run_id": run_id})
        if launch:
            directory = s.path(run_id).parent
            try:
                with (directory / "worker.log").open("w", encoding="utf-8") as log:
                    child = subprocess.Popen([sys.executable, "-u", "-m", "app.investment_agents.worker", run_id],
                        cwd=ds.BACKEND, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            except OSError as exc:
                run.update(status="failed", error="无法启动分析工作进程：" + str(exc)[:500])
                s.save(run)
                raise ValueError(run["error"]) from exc
            run["pid"] = child.pid
            s.save(run)
        return summary(run)


def update(run_id, **fields):
    with s.LOCK:
        run = s.load(run_id)
        if run["cancel_requested"]:
            raise InterruptedError("用户已停止任务")
        run.update(fields)
        return s.save(run)


def progress(run_id, actor, title, detail="", **fields):
    with s.LOCK:
        run = s.load(run_id)
        if run["cancel_requested"]:
            raise InterruptedError("用户已停止任务")
        if run.get("activity") != title:
            s.event(run, actor, title, detail)
        run.update(fields)
        return s.save(run)


def cancelled(run_id):
    return s.load(run_id).get("cancel_requested", False)


def publish(run_id, context):
    with s.LOCK:
        run = s.load(run_id)
        if run["cancel_requested"]:
            raise InterruptedError("用户已停止任务")
        run["context_version"] += 1
        run["context_fingerprint"] = s.digest(context)
        s.write(s.path(run_id).parent / f"context-v{run['context_version']}.json", context)
        run["data_summary"] = {"prepared_at": context["prepared_at"], "target_date": context["target_date"],
            "collection_account_matches": context["collection_account_matches"], "metrics": context["metrics"],
            "source_status": context["source_status"], "account_snapshot_at": context["account"].get("snapshot_time"),
            "positions": [{"symbol": p["symbol"], "name": p.get("name"), "watchlist": not p["quantity"]} for p in context["account"]["positions"]],
            "evidence": [{k: item.get(k) for k in ("id", "kind", "symbol", "source", "title", "published_at", "retrieved_at", "warning")} for item in context["evidence"]]}
        s.event(run, "agent1", f"资料 v{run['context_version']} 已交接", f"{len(context['evidence'])}项证据；逐项保留日期与失败信息，不将整体完成视为来源全部最新。")
        return s.save(run)


def compact(context):
    value = deepcopy(context)
    account = value["account"]
    fields = {"symbol", "name", "quantity", "avg_cost", "asset_type", "ipo_status", "issue_price", "expected_list_date",
              "directions", "position_role", "invalid_condition", "target_max_weight", "user_plan", "risk_flags"}
    value["account"] = {k: v for k, v in account.items() if k in {"snapshot_id", "snapshot_time", "cash_available", "repo_amount", "account_actual_total_cost", "risk_limits", "notes"}}
    value["account"]["positions"] = [{k: v for k, v in p.items() if k in fields} for p in account["positions"]]
    for evidence in value["evidence"]:
        if evidence["kind"] == "rotation":
            facts = evidence["facts"]
            facts["items"] = [{k: item.get(k) for k in ("sector_id", "name", "selected_symbol", "latest_date", "returns", "relative_strength", "missing_fields")}
                              for item in facts.get("items", [])]
    for limit in (1800, 900, 400):
        if len(json.dumps(value, ensure_ascii=False, default=str)) <= 80000:
            return value
        for evidence in value["evidence"]:
            facts = evidence.get("facts", {})
            if evidence.get("priority") != "requested" and "selected_text" in facts and len(facts["selected_text"]) > limit:
                facts["selected_text"] = facts["selected_text"][:limit]
                evidence["warning"] = "输入预算缩减的原文选段；需要更多上下文可请求Agent1补证，不代表全文完整。"
    if len(json.dumps(value, ensure_ascii=False, default=str)) > 80000:
        raise ValueError("资料包超过本轮80,000字符输入预算；请减少观察标的或历史记录范围后重试")
    return value


def validate(value, run, context):
    report = Analysis.model_validate(value)
    if (report.context_version, report.context_fingerprint) != (run["context_version"], run["context_fingerprint"]):
        raise ValueError("模型使用了旧资料版本或错误指纹")
    if report.action == "request_evidence":
        if not report.requests or report.findings:
            raise ValueError("补证请求必须包含requests，且不能夹带最终结论")
        tracked = {p["symbol"].split(".")[0] for p in context["account"]["positions"]}
        if any(not set(request.symbols) <= tracked for request in report.requests):
            raise ValueError("补证越权：只允许已有持仓或观察标的")
        return report
    if report.requests or not report.findings or not any(item.level == "account" for item in report.findings):
        raise ValueError("最终分析需包含账户层判断与建议，且requests应为空")
    if any(p["quantity"] > 0 for p in context["account"]["positions"]) and not any(item.level == "symbol" for item in report.findings):
        raise ValueError("最终分析缺少重点持仓标的的具体计划，不能只返回账户概述")
    ids = [source.id for source in report.external_sources]
    if len(set(ids)) != len(ids):
        raise ValueError("外部来源编号重复")
    catalog = {e["id"] for e in context["evidence"]}
    if set(ids) & catalog:
        raise ValueError("外部来源编号不能覆盖本地证据")
    refs = set(ids) | catalog | {"account:snapshot"}
    for item in report.findings:
        if not set(item.evidence_refs) <= refs:
            raise ValueError("模型引用了未提供的证据编号")
        if item.level == "symbol" and item.target not in {p["symbol"].split(".")[0] for p in context["account"]["positions"]}:
            raise ValueError("标的建议target必须是本次持仓/观察池的六位代码")
        if item.confidence == "high" and not context["collection_account_matches"]:
            raise ValueError("采集账户与当前账户不一致，不接受高信心判断")
    return report


def work(run_id, caller=None):
    heartbeat_stop = threading.Event()
    def heartbeat():
        while not heartbeat_stop.wait(2):
            try:
                with s.LOCK:
                    run = s.load(run_id)
                    if run["status"] in s.TERMINAL or run["cancel_requested"]:
                        return
                    run["heartbeat_at"] = s.now().isoformat()
                    if run["status"] == "collecting":
                        run["source_progress"] = sync.load_status().get("progress", {})
                    s.save(run)
            except (OSError, ValueError, BlockingIOError):
                pass
    threading.Thread(target=heartbeat, daemon=True).start()
    try:
        run = update(run_id, status="collecting")
        progress(run_id, "agent1", "检查账户、持仓与观察池资料", "按来源缓存、采集、存储；不调用模型解释数据。")
        cached_context = None
        if run["refresh"]:
            deadline = time.monotonic() + 90
            while True:
                if cancelled(run_id):
                    raise InterruptedError("用户已停止任务")
                try:
                    sync.run(scope="tracked")
                    break
                except BlockingIOError:
                    if sync.load_status().get("stage") == "backfill":
                        from app.investment_agents.health import status as coverage_status
                        candidate = data_agent.build_context(run["question"])
                        if candidate["collection_account_matches"] and coverage_status()["coverage"]["narrow"]["healthy"]:
                            cached_context = candidate
                            progress(run_id, "agent1", "重点资料已就绪", "全市场正在后台续传，本轮复用已验证时效的重点资料；其他来源的日期和缺口仍保留。")
                            break
                    if time.monotonic() > deadline:
                        raise ValueError("后台采集仍占用来源锁，请稍后重试；不会重复启动采集")
                    progress(run_id, "agent1", "等待已运行的后台采集", "复用同一份真实数据缓存，不并发争抢来源。")
                    time.sleep(2)
        context = compact(cached_context or data_agent.build_context(run["question"]))
        if not context["collection_account_matches"]:
            raise ValueError("资料对应的账户与当前记录不一致，请更新资料；未发起模型分析")
        if data_agent.fingerprint() != run["account_fingerprint"]:
            raise ValueError("取数期间账户已变化，请重新发起")
        run = publish(run_id, context)
        seen, last_error = set(), ""
        for turn in range(run["max_model_calls"]):
            if cancelled(run_id):
                raise InterruptedError("用户已停止任务")
            if data_agent.fingerprint() != run["account_fingerprint"]:
                raise ValueError("账户发生变化，已停止旧版本分析")
            remaining = run["max_model_calls"] - turn - 1
            context["execution_budget"] = {"model_calls_remaining_after_this": remaining,
                                          "tool_requests_remaining": run["max_tool_requests"] - run["tool_requests"],
                                          "must_finalize": remaining == 0}
            run = publish(run_id, context)
            run = update(run_id, status="analyzing", model_calls=turn + 1)
            progress(run_id, "agent2", f"Agent2 分析第 {turn + 1} 轮", f"模型来源：{run['provider']}；本轮后剩余{remaining}次调用。")
            text = providers.prompt(context, run["context_version"], run["context_fingerprint"], last_error)
            s.write(s.path(run_id).parent / f"prompt-{turn + 1}.md", text)
            invoke = caller or providers.CALLERS[run["provider"]]
            value, usage = invoke(text, s.path(run_id).parent, run.get("config") or s.settings(),
                lambda title, detail: progress(run_id, "agent2", title, json.dumps(detail, ensure_ascii=False)),
                lambda: cancelled(run_id), turn + 1)
            totals = dict(run["tokens"])
            for key, count in usage.items():
                if isinstance(count, (int, float)):
                    totals[key] = totals.get(key, 0) + count
            run = update(run_id, tokens=totals, model_usage=[*run.get("model_usage", []), {"call": turn + 1, "usage": usage}])
            try:
                report = validate(value, run, context)
            except ValueError as exc:
                last_error = str(exc)[:1600]
                progress(run_id, "coordinator", "分析结果未通过校验", last_error)
                if not remaining:
                    raise
                continue
            if report.action == "final":
                if data_agent.fingerprint() != run["account_fingerprint"]:
                    raise ValueError("分析完成时账户已变化，旧结论不能入库")
                result = report.model_dump()
                update(run_id, status="awaiting_confirmation", report=result, report_digest=s.digest(result))
                progress(run_id, "coordinator", "分析完成，等待确认记录", "观点与事实分开；确认只保存判断、建议和教训，不执行交易。")
                return
            if not remaining:
                raise ValueError("模型在最后一轮仍请求补证，未产生完整结论。可提高单次任务轮次后重新运行。")
            for request in report.requests:
                signature = s.digest(request.model_dump(exclude={"reason"}))
                if signature in seen or run["tool_requests"] >= run["max_tool_requests"]:
                    last_error = "相同补证请求已执行或取证预算耗尽；必须基于已有资料形成有限结论并列出缺口。"
                    progress(run_id, "coordinator", "补证请求停止扩展", last_error)
                    continue
                seen.add(signature)
                run = update(run_id, status="supplementing", tool_requests=run["tool_requests"] + 1)
                progress(run_id, "agent2", "向 Agent1 请求补证", request.reason)
                name, result, target = data_agent.collect_requested(request, lambda name, state: progress(run_id, "agent1", "补证返回", name + " · " + state))
                context = compact(data_agent.add_supplement(context, name, result, target, run["tool_requests"]))
                run = publish(run_id, context)
        raise ValueError("本次分析预算已耗尽，未获得通过校验的结论")
    except Exception as exc:
        with s.LOCK:
            run = s.load(run_id)
            stopped = run["cancel_requested"] or isinstance(exc, InterruptedError)
            run.update(status="cancelled" if stopped else "failed", error=str(exc)[:1600])
            s.event(run, "coordinator", "任务已停止" if stopped else "任务未完成", run["error"])
            s.save(run)
    finally:
        heartbeat_stop.set()


def cancel(run_id):
    with s.LOCK:
        run = s.load(run_id)
        if run["status"] != "confirmed":
            run.update(cancel_requested=True, status="cancelled")
            s.event(run, "human", "用户停止或放弃本次分析", "已完成资料保留；迟到结果不会覆盖此状态。")
            s.save(run)
        return summary(run)


def confirm(run_id, checksum):
    with s.LOCK:
        run = s.load(run_id)
        if run["status"] == "confirmed" and run["report_digest"] == checksum:
            return summary(run)
        if run["status"] != "awaiting_confirmation" or checksum != run["report_digest"]:
            raise ValueError("分析预览已变化或尚未完成")
        if data_agent.fingerprint() != run["account_fingerprint"]:
            raise ValueError("账户已变化，请重新分析，不接受旧账户结论")
        memory = s.memories()
        existing = next((item for item in memory["results"] if item["run_id"] == run_id), None)
        if existing:
            if s.digest(existing["report"]) != checksum:
                raise ValueError("已有同编号的不同结果，不会覆盖")
            run["status"] = "confirmed"
            return summary(s.save(run))
        if memory["revision"] != run["memory_revision"]:
            raise ValueError("分析记忆已更新，请重新分析")
        record = {"run_id": run_id, "provider": run["provider"], "confirmed_at": s.now().isoformat(),
                  "account_fingerprint": run["account_fingerprint"], "context_version": run["context_version"], "report": run["report"], "digest": checksum}
        memory["results"].append(record)
        memory["revision"] += 1
        s.write(s.ROOT / "memory.json", memory)
        run["status"] = "confirmed"
        s.event(run, "human", "判断、建议与教训已记录", "后续分析读取这些记忆，并重新核对当前证据。未改动持仓。")
        return summary(s.save(run))


def evidence(run_id, ref):
    run = s.load(run_id)
    context = s.read(s.path(run_id).parent / f"context-v{run['context_version']}.json", {})
    if ref == "account:snapshot":
        return {"id": ref, "facts": context.get("account")}
    found = next((e for e in context.get("evidence", []) if e["id"] == ref), None)
    if not found:
        raise ValueError("证据不存在")
    return found
