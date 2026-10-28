"""Read-only business readiness, separate from investment risk or model confidence."""
from datetime import datetime, timedelta

from app.data_sync import service as sync, storage as ds
from app.investment_agents import data_agent, providers, store as s


SOURCE_NAMES = {"market": "持仓与关注标的行情", "references": "重要参考指数与代理", "disclosures": "财报与公告", "rotation": "行业代理走势",
                "breadth": "广义广度（全市场）", "public": "宏观与商品参考"}


def _target(now):
    day = now.date()
    if now.hour * 60 + now.minute < 930:
        day -= timedelta(days=1)
    calendar = ds.read(ds.ROOT / "trading_calendar.json", {})
    sessions = [d for d in calendar.get("sessions", []) if d <= day.isoformat()]
    if sessions and (calendar.get("checked_on") == now.date().isoformat() or max(calendar.get("sessions", [])) >= day.isoformat()):
        return max(sessions)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day.isoformat()


def narrow_coverage(snapshot, target, market, references, now):
    from app.data_sync.references import REQUIRED_GROUPS, observation_fresh
    by_symbol = {item.get("symbol"): item for item in market.get("items", [])}
    calendar = ds.read(ds.ROOT / "trading_calendar.json", {})
    trading_day = now.date().isoformat() in calendar.get("sessions", []) if calendar.get("checked_on") == now.date().isoformat() else now.weekday() < 5
    minute = now.hour * 60 + now.minute
    needs_live_quote = trading_day and (570 <= minute <= 690 or 780 <= minute <= 900)
    rows = []
    for position in snapshot.get("positions", []):
        code = position["symbol"].split(".")[0]
        daily = by_symbol.get(code, {}).get("daily", {})
        quote = by_symbol.get(code, {}).get("quote", {})
        exempt = position.get("asset_type") == "ipo_subscription" and position.get("ipo_status") != "listed"
        ready = bool(daily.get("close") is not None and (daily.get("as_of") or "") >= target)
        quote_time = quote.get("market_time_local") or quote.get("quote_market_time")
        if needs_live_quote and not exempt:
            try:
                observed = datetime.fromisoformat(quote_time)
                if observed.tzinfo is None:
                    observed = observed.replace(tzinfo=ds.TZ)
                lag = (now - observed).total_seconds()
                quote_fresh = quote.get("price") is not None and -300 <= lag <= 900
            except (ValueError, TypeError):
                quote_fresh = False
            ready = ready and quote_fresh
        rows.append({"symbol": code, "name": position.get("name") or code, "kind": "holding" if position.get("quantity", 0) > 0 else "watchlist",
                     "fresh": ready, "exempt": exempt, "observed_at": daily.get("as_of"),
                     "quote_observed_at": quote_time, "reason": "未上市新股无交易日K，不纳入缺失分母" if exempt else "" if ready else "日K未到目标日，或盘中报价超过15分钟/缺失"})
    reference_rows = [{**item, "fresh": item.get("status") == "available" and observation_fresh(item, now, target)}
                      for item in references.get("items", [])]
    groups = [{"group": key, "name": name, "fresh": any(item.get("group") == key and item["fresh"] for item in reference_rows)}
              for key, name in REQUIRED_GROUPS.items()]
    required = [row for row in rows if not row["exempt"]]
    held_missing = [row for row in required if row["kind"] == "holding" and not row["fresh"]]
    missing = [row for row in required if not row["fresh"]]
    ratio = sum(row["fresh"] for row in required) / len(required) if required else 1
    missing_groups = [row["name"] for row in groups if not row["fresh"]]
    major = bool(held_missing or ratio < 0.8 or missing_groups or not rows)
    return {"name": "狭义广度（重点资料覆盖）", "healthy": not major, "tracked_count": len(required),
            "covered_count": sum(row["fresh"] for row in required), "coverage_pct": round(ratio * 100, 2),
            "missing_symbols": [row["symbol"] for row in missing], "missing_groups": missing_groups,
            "items": rows, "references": reference_rows, "reference_groups": groups,
            "boundary": "这是重点资料的时效覆盖，不是市场涨跌家数。全部已上市持仓日K须有效，关注池覆盖至少80%，境内大盘/纳指/美元/黄金/有色参考组均至少有一个有效来源；全市场覆盖低不影响该健康判定。"}


def status():
    now = ds.now()
    snapshot = data_agent.account()
    tracked = {p["symbol"].split(".")[0] for p in snapshot.get("positions", [])}
    held_stocks = {p["symbol"].split(".")[0] for p in snapshot.get("positions", [])
                   if p.get("quantity", 0) > 0 and p.get("asset_type", "stock") == "stock"}
    target = _target(now)
    sources = []
    market = {}
    references = {}
    broad = {}
    for name, label in SOURCE_NAMES.items():
        envelope = ds.read(ds.ROOT / f"{name}.json", {})
        facts = envelope.get("data", {})
        if name == "market":
            market = facts
        elif name == "references":
            references = facts
        elif name == "breadth":
            broad = facts
        try:
            finished = datetime.fromisoformat(envelope["finished_at"])
            age = (now - finished).total_seconds()
            ttl = sync.POLICY[name][0]
            if name == "market" and (now.weekday() >= 5 or not 9 <= now.hour < 16):
                ttl = 21600
            fresh = 0 <= age < ttl
        except (ValueError, TypeError, KeyError):
            fresh = False
            age = None
        failures = facts.get("failures", [])
        complete = envelope.get("status") == "complete"
        major_gap = not facts or age is None or age < 0 or age > 86400 or envelope.get("status") in {"failed", "timed_out", "not_collected"}
        if name == "disclosures":
            covered = {doc.get("symbol") for doc in facts.get("documents", [])}
            major_gap = major_gap or not covered or bool(held_stocks and len(held_stocks & covered) / len(held_stocks) < 0.5)
        elif name == "breadth":
            major_gap = major_gap or not facts.get("coverage_count") or float(facts.get("coverage_pct") or 0) < 50
        sources.append({"source": name, "name": label, "status": envelope.get("status", "not_collected"),
                        "finished_at": envelope.get("finished_at"), "target_date": envelope.get("target_date"),
                        "fresh": fresh, "ready": complete and fresh and not failures and (envelope.get("target_date") or "") >= target,
                        "major_gap": major_gap,
                        "failures": failures[:20], "boundary": facts.get("boundary"),
                        "coverage": facts.get("checked_symbols", [])})
    items = {i.get("symbol"): i for i in market.get("items", [])}
    gaps = []
    for symbol in sorted(tracked):
        daily = items.get(symbol, {}).get("daily", {})
        observed = daily.get("as_of")
        if not observed or observed < target or daily.get("close") is None or daily.get("is_stale", True):
            gaps.append(symbol)
    pointer = s.read(s.ROOT / "current.json", {})
    run = s.load(pointer["run_id"]) if pointer.get("run_id") else None
    active = bool(run and run["status"] not in s.TERMINAL)
    collection = sync.load_status()
    if active and run.get("pid") and not ds.process_alive(run["pid"]):
        active = False
    available = providers.availability()
    model_ready = available["codex"]["installed"] or (available["api"]["configured"] and available["api"]["enabled"])
    changed = bool(run and run.get("account_fingerprint") != sync.account_identity(snapshot))
    by_name = {row["source"]: row for row in sources}
    narrow = narrow_coverage(snapshot, target, market, references, now)
    account_reason = f"账户记录：{snapshot.get('snapshot_time') or '尚无记录时间'}；跟踪{len(tracked)}个标的"
    model_reason = ("已检测本机Codex；登录与可用额度需在运行时确认" if available["codex"]["installed"] else
                    "已启用模型API；服务权限需在运行时确认" if model_ready else "无可用分析入口：未检测到Codex且模型API未启用")

    def indicator(label, required, needs_model=False, supplementary=()):
        reasons = [account_reason] if label != "发现与研究助手" else []
        missing = [by_name[name]["name"] for name in required if not by_name[name]["ready"]]
        if "market" in required and gaps:
            reasons.append(f"{len(gaps)}个标的缺少截至{target}的有效日K：{'、'.join(gaps)}")
        if missing:
            reasons.append("未采集、待更新或部分可用：" + "、".join(missing))
        major = [by_name[name]["name"] for name in supplementary if by_name[name]["major_gap"]]
        minor = [by_name[name]["name"] for name in supplementary if not by_name[name]["ready"] and not by_name[name]["major_gap"]]
        if major:
            reasons.append("补充资料存在重大缺失：" + "、".join(major))
        if minor:
            reasons.append("补充资料部分可用，不影响主要采集就绪：" + "、".join(minor))
        if label == "资料采集助手":
            reasons = [account_reason, f"狭义覆盖：{narrow['covered_count']}/{narrow['tracked_count']}个持仓与关注标的日K有效"]
            if narrow["missing_symbols"]:
                reasons.append("日K待补：" + "、".join(narrow["missing_symbols"]))
            if narrow["missing_groups"]:
                reasons.append("重要参考缺失或过期：" + "、".join(narrow["missing_groups"]))
            reasons.append(f"广义覆盖 {broad.get('coverage_pct', 0)}%，单独展示，不参与狭义健康判定")
        if needs_model:
            reasons.append(model_reason)
        level, text = "green", "就绪"
        if missing or major or ("market" in required and gaps) or not tracked:
            level, text = "yellow", "待完善"
        if label == "资料采集助手":
            level, text = ("green", "重点资料就绪") if narrow["healthy"] else ("yellow", "重点资料待补")
        if changed and needs_model:
            reasons.append("账户已更新，现有分析基于旧账户，需重新分析")
            level, text = "yellow", "待更新"
        broad_running = collection.get("stage") in {"backfill", "breadth"}
        if (collection.get("status") == "running" and not (label == "资料采集助手" and broad_running)) or (active and needs_model):
            level, text = "yellow", "运行中"
            reasons.append("正在更新资料或分析，可在工作台查看进度")
        if needs_model and run and run["status"] == "failed":
            level, text = "red", "任务失败"
            reasons.append(run.get("error") or "最近分析未完成")
        if needs_model and not model_ready:
            level, text = "red", "模型不可用"
        if label == "资料采集助手" and tracked and not any(items.get(code, {}).get("daily", {}).get("close") for code in tracked):
            level, text = "red", "数据不可用"
        return {"label": label, "level": level, "text": text, "reasons": reasons,
                "required_sources": required}

    return {"checked_at": now.isoformat(), "target_date": target, "account_snapshot_at": snapshot.get("snapshot_time"),
            "sources": sources, "coverage": {"narrow": narrow, "broad": {"name": "广义广度（全市场）", "as_of": broad.get("as_of"),
                "covered_count": broad.get("coverage_count", 0), "universe_count": broad.get("universe_count", 0),
                "coverage_pct": broad.get("coverage_pct", 0), "source": broad.get("source"), "boundary": broad.get("boundary")}},
            "startup": ds.read(ds.ROOT / "startup.json", {}), "backfill": {
                **ds.read(ds.ROOT / "backfill.json", {}).get("data", {}),
                **(collection.get("progress", {}) if collection.get("status") == "running" and collection.get("stage") == "backfill" else {})}, "assistants": {
                "portfolio": indicator("资料采集助手", ["market", "references"]),
                "dashboard": indicator("驾驶舱助手", ["market", "disclosures", "public"], True),
                "discovery": indicator("发现与研究助手", ["market", "rotation", "references", "public"], True)},
            "boundary": "状态灯仅表示数据与分析入口的工作状态，不是投资风险评级；采集完成不代表消息全面或模型结论正确。"}
