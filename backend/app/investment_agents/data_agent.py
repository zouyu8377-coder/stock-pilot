"""Real source adapters and evidence packaging. No model calls or account writes."""
from copy import deepcopy

from app.data_sync import collectors, service as sync, storage as data_store
from app.investment_agents import store as s


def account():
    from app.portfolio.service import portfolio_service
    return portfolio_service.load_snapshot().model_dump(mode="json")


def fingerprint():
    return sync.account_identity(account())


def _market_evidence(item, target):
    quote, daily = item.get("quote", {}), item.get("daily", {})
    return {"id": "market:" + item["symbol"], "kind": "market", "symbol": item["symbol"],
            "source": "Tencent quote / local daily-K source", "retrieved_at": item.get("retrieved_at"),
            "target_date": target, "facts": {"quote": quote, "daily": daily},
            "warning": "实时行情与已落库日K分别标注日期；报价成交量单位可能与日K不同，不可直接相除。"}


def build_context(question):
    bundle = data_store.read(data_store.ROOT / "latest.json", {})
    snapshot = account()
    sources = bundle.get("sources", {})
    evidence, quality = [], []
    tracked = {p["symbol"].split(".")[0] for p in snapshot["positions"]}
    for name, envelope in sources.items():
        data = envelope.get("data", {})
        quality.append({"source": name, "status": envelope.get("status"), "finished_at": envelope.get("finished_at"),
                        "target_date": envelope.get("target_date"), "failures": data.get("failures", [])[:20],
                        "boundary": data.get("boundary"), "coverage": data.get("checked_symbols", [])})
        if name == "market":
            evidence.extend(_market_evidence(item, envelope.get("target_date")) for item in data.get("items", []) if item.get("symbol") in tracked)
        elif name == "disclosures":
            for doc in data.get("documents", []):
                if doc.get("symbol") not in tracked:
                    continue
                evidence.append({"id": "disclosure:" + str(doc["announcement_id"]), "kind": "disclosure", "symbol": doc["symbol"],
                                 "source": doc.get("pdf_url"), "title": doc.get("title"), "published_at": doc.get("announced_at"),
                                 "retrieved_at": doc.get("retrieved_at"), "document_type": doc.get("document_type", "announcement"),
                                 "local_pdf": doc.get("local_pdf"),
                                 "facts": {"selected_text": doc.get("selected_text", "")[:2800]},
                                 "warning": "原文选段，非全文核验；不能把未选中的章节视为不存在。"})
        elif name in {"public", "breadth", "rotation", "references"}:
            facts = deepcopy(data)
            if name == "rotation":
                facts["items"] = facts.get("items", [])[:35]
            evidence.append({"id": "objective:" + name, "kind": name, "source": "objective_data_sync", "facts": facts,
                             "retrieved_at": envelope.get("finished_at"), "status": envelope.get("status"),
                             "warning": "广义全市场样本覆盖不足95%，不能据此推断两市普涨/普跌或称样本成交额为两市总额。" if name == "breadth" and (facts.get("coverage_pct") or 0) < 95 else ""})
    values, missing = [], []
    for position in snapshot["positions"]:
        code = position["symbol"].split(".")[0]
        item = next((e for e in evidence if e["id"] == "market:" + code), None)
        facts = item["facts"] if item else {}
        quote, daily = facts.get("quote", {}), facts.get("daily", {})
        price = quote.get("price") if not quote.get("is_stale", True) else daily.get("close")
        if price is None and position["quantity"] > 0:
            missing.append(code)
        values.append({"symbol": code, "name": position.get("name"), "market_value": float(position["quantity"]) * float(price or 0)})
    total = float(snapshot.get("cash_available") or 0) + float(snapshot.get("repo_amount") or 0) + sum(v["market_value"] for v in values)
    metrics = {"total_assets": total if not missing else None, "unpriced_holdings": missing,
               "account_pnl": total - float(snapshot["account_actual_total_cost"]) if not missing and snapshot.get("account_actual_total_cost") else None,
               "cash_pct": round(float(snapshot.get("cash_available") or 0) / total * 100, 2) if total and not missing else None,
               "positions": [{**v, "weight_pct": round(v["market_value"] / total * 100, 2) if total and not missing else None} for v in values]}
    from app.agent_review import discussion
    from app.portfolio.service import portfolio_service
    from app.portfolio.trade_ledger import PortfolioTradeLedger
    batches = PortfolioTradeLedger(portfolio_service.root / "trade_ledger").list_batches(limit=5)
    if batches:
        evidence.append({"id": "account:transactions", "kind": "account_records", "source": "local confirmed trade ledger",
                         "facts": [{"confirmed_at": b.get("confirmed_at"), "user_reason": b.get("user_reason"),
                                    "transactions": [{k: t.get(k) for k in ("symbol", "side", "quantity", "average_price", "amount", "occurred_at", "action_time_source", "applied_to_portfolio")}
                                                     for t in b.get("transactions", [])]} for b in batches],
                         "warning": "只包含最近5批已确认记录，不代表完整资金流水；日期来源需分辨成交时间与录入时间。"})
    changes = s.read(s.ROOT / "account_updates.json", [])[-8:]
    if changes:
        evidence.append({"id": "account:record_changes", "kind": "account_records", "source": "Agent1 account import audit",
                         "facts": [{k: row.get(k) for k in ("at", "status", "changes", "removed")} for row in changes],
                         "warning": "账户快照变化而非成交证据，不得据此编造逐笔交易。"})
    legacy = list(discussion.state().get("entities", {}).values())
    memory = s.memories()
    return {"question": question, "account": snapshot, "account_fingerprint": sync.account_identity(snapshot),
            "metrics": metrics, "evidence": evidence, "source_status": quality,
            "collection_account_matches": bool(bundle) and sync.account_identity(bundle.get("account", {})) == sync.account_identity(snapshot),
            "target_date": bundle.get("target_date"), "prepared_at": s.now().isoformat(),
            "memory_revision": memory["revision"], "previous_results": [
                {"confirmed_at": r["confirmed_at"], "summary": r["report"]["summary"], "lessons": r["report"]["lessons"],
                 "findings": [{k: f.get(k) for k in ("level", "target", "action", "conclusion", "trigger", "invalidation")} for f in r["report"]["findings"]]}
                for r in memory["results"][-3:]],
            "legacy_memories": [e for e in legacy if e.get("active")][-15:],
            "boundaries": bundle.get("boundaries", []) + ["账户集中或回撤本身只是参数；风险判断需结合趋势、经营、事件等独立证据。",
                "无实时券商同步；账户来自用户已有记录。数据缺失不等于利空。截图净变化不等于已确认成交。",
                "历史已确认判断是记忆而非当前事实，须注明沿用、修订或失效；观点信心不是收益概率。"]}


def collect_requested(request, progress):
    universe = collectors.universe()
    symbols = set(request.symbols)
    if not symbols <= set(universe["tracked"]):
        raise ValueError("仅允许持仓与观察池标的；新标的请先加入观察池")
    if request.tool == "events":
        name = "public"
    else:
        name = "disclosures" if request.tool == "disclosure" else "market"
    # The existing worker owns source timeouts, read-only mode and source provenance.
    with data_store.exclusive(data_store.ROOT / "sync.lock"):
        universe["tracked"] = sorted(symbols)
        universe["stocks"] = [code for code in universe["stocks"] if code in symbols]
        target = data_store.read(data_store.ROOT / "latest.json", {}).get("target_date") or s.now().date().isoformat()
        result = sync.run_stage(name, {"universe": universe, "target_date": target}, min(sync.POLICY[name][1], 240))
    progress(name, result.get("status", "failed"))
    return name, result, target


def add_supplement(context, name, result, target, index):
    if name == "market":
        additions = [_market_evidence(item, target) for item in result.get("items", [])]
    elif name == "disclosures":
        additions = [{"id": "disclosure:" + str(doc["announcement_id"]), "kind": "disclosure", "symbol": doc["symbol"],
                      "source": doc.get("pdf_url"), "title": doc.get("title"), "published_at": doc.get("announced_at"),
                      "local_pdf": doc.get("local_pdf"), "priority": "requested",
                      "facts": {"selected_text": doc.get("selected_text", "")[:8000]}, "warning": "补充原文选段，非全文核验"}
                     for doc in result.get("documents", [])]
    else:
        additions = [{"id": "objective:public", "kind": "public", "source": "official feeds / reference quote", "facts": result}]
    if not additions:
        additions = [{"id": f"gap:{index}", "kind": "source_gap", "source": name, "facts": result,
                      "warning": "未获得新资料，不可伪造取证成功"}]
    by_id = {e["id"]: e for e in context["evidence"]}
    by_id.update({e["id"]: e for e in additions})
    context["evidence"] = list(by_id.values())
    context["source_status"].append({"source": name, "status": result.get("status"), "failures": result.get("failures", []), "supplement": True})
    # Supplemented prices must also update account metrics, without changing holdings.
    if name == "market":
        prices = {item["symbol"]: item for item in result.get("items", [])}
        by_symbol = {entry["symbol"]: entry for entry in context["metrics"]["positions"]}
        missing = set(context["metrics"]["unpriced_holdings"])
        for position in context["account"]["positions"]:
            code = position["symbol"].split(".")[0]
            item = prices.get(code)
            if not item:
                continue
            quote, daily = item.get("quote", {}), item.get("daily", {})
            price = quote.get("price") if not quote.get("is_stale", True) else daily.get("close")
            if price is not None:
                by_symbol[code]["market_value"] = float(position["quantity"]) * float(price)
                missing.discard(code)
            elif position["quantity"]:
                missing.add(code)
        metrics, account = context["metrics"], context["account"]
        total = sum(item["market_value"] for item in by_symbol.values()) + float(account.get("cash_available") or 0) + float(account.get("repo_amount") or 0)
        metrics.update(total_assets=total if not missing else None, unpriced_holdings=sorted(missing),
                       account_pnl=total - float(account["account_actual_total_cost"]) if not missing and account.get("account_actual_total_cost") else None,
                       cash_pct=round(float(account.get("cash_available") or 0) / total * 100, 2) if total and not missing else None)
        for entry in metrics["positions"]:
            entry["weight_pct"] = round(entry["market_value"] / total * 100, 2) if total and not missing else None
    return context
