"""Validated account records only; never send orders or change trade fills."""
import math
from datetime import datetime, timezone
from uuid import uuid4

from app.investment_agents import store as s
from app.data_sync.service import account_identity
from app.portfolio.schemas import PortfolioPositionInput, PortfolioSnapshotInput
from app.portfolio.storage_lock import portfolio_lock


def history():
    return [{k: value for k, value in row.items() if k != "before"} for row in s.read(s.ROOT / "account_updates.json", [])][-12:]


def apply(body):
    from app.portfolio.service import portfolio_service, _normalize_position_semantics
    if not s.settings()["auto_apply_verified_holdings"]:
        raise ValueError("自动更新账户记录未启用")
    if not body.complete:
        raise ValueError("仅完整账户资料可自动更新；部分截图或缺行资料需人工确认")
    observed = datetime.fromisoformat(body.observed_at.replace("Z", "+00:00"))
    if observed.tzinfo is None:
        raise ValueError("账户资料时间必须带时区")
    age = (s.now() - observed).total_seconds()
    if age < -300 or age > 86400:
        raise ValueError("仅接收24小时内且不在未来的账户资料")
    with s.LOCK, portfolio_lock(portfolio_service.root):
        rows = s.read(s.ROOT / "account_updates.json", [])
        input_digest = s.digest(body.model_dump(exclude={"expected_fingerprint"}))
        existing = next((r for r in rows if r["source_id"] == body.source_id), None)
        if existing:
            if existing["input_digest"] != input_digest:
                raise ValueError("来源编号已被不同账户资料使用")
            return {k: v for k, v in existing.items() if k != "before"}
        before = portfolio_service.load_snapshot().model_dump(mode="json")
        if account_identity(before) != body.expected_fingerprint:
            raise ValueError("账户已变化，未覆盖新的记录")
        prior_time = datetime.fromisoformat(before["snapshot_time"].replace("Z", "+00:00"))
        prior_time = prior_time.replace(tzinfo=timezone.utc) if prior_time.tzinfo is None else prior_time
        if observed < prior_time:
            raise ValueError("上传账户资料早于现有快照，不自动回退")
        previous = {p["symbol"].split(".")[0]: p for p in before["positions"]}
        positions, codes, value = [], set(), 0.0
        allowed = {"symbol", "name", "quantity", "available_quantity", "avg_cost", "broker_screenshot_price", "broker_screenshot_market_value", "asset_type"}
        for raw in body.positions:
            code = str(raw.get("symbol", "")).split(".")[0]
            if len(code) != 6 or not code.isdigit() or code in codes:
                raise ValueError("标的代码缺失、重复或不合法")
            codes.add(code)
            if code not in previous and (raw.get("asset_type") not in {"stock", "etf", "ipo_subscription"} or not str(raw.get("name") or "").strip()):
                raise ValueError("新增标的需明确名称与asset_type；不能自动猜测股票和ETF类型")
            item = {**previous.get(code, {}), **{k: v for k, v in raw.items() if k in allowed}, "symbol": code}
            row = PortfolioPositionInput(**item)
            numbers = [row.quantity, row.avg_cost, row.available_quantity, row.broker_screenshot_price, row.broker_screenshot_market_value]
            if any(n is not None and not math.isfinite(n) for n in numbers) or row.quantity < 0:
                raise ValueError("数量、成本或价格字段无效；负成本允许，但数量不可为负")
            if row.available_quantity is not None and not 0 <= row.available_quantity <= row.quantity:
                raise ValueError("可用数量超出持仓数量")
            if row.quantity:
                if row.broker_screenshot_price is None or row.broker_screenshot_price <= 0 or row.broker_screenshot_market_value is None:
                    raise ValueError("自动入账需要每项持仓的截图价格与市值用于交叉校验")
                calculated = row.quantity * row.broker_screenshot_price
                if abs(calculated - row.broker_screenshot_market_value) > max(2, calculated * 0.0001):
                    raise ValueError("持仓数量×价格与该行市值不符")
                value += calculated
            data = row.model_dump()
            data.update(broker_screenshot_price_time=observed, broker_screenshot_price_source="verified_account_import",
                        source_type="agent1_validated_account_import", source_name="Agent1交叉校验后自动记账，非人工逐行确认", confirmed_by_user=False)
            positions.append(PortfolioPositionInput(**_normalize_position_semantics(data)))
        if abs(value - body.total_market_value) > max(2, value * 0.0001):
            raise ValueError("持仓行市值之和与账户总市值不符，可能是截图缺行；保留原账户")
        repo = float(before.get("repo_amount") or 0)
        if abs(value + body.cash_available + repo - body.total_assets) > max(2, body.total_assets * 0.0001):
            raise ValueError("总资产与现金、持仓市值及逆回购不符；不能自行猜测差额")
        positions.extend(PortfolioPositionInput(**p) for code, p in previous.items() if code not in codes and not p["quantity"])
        payload = PortfolioSnapshotInput(**{**before, "snapshot_id": "portfolio_snapshot_" + uuid4().hex,
            "snapshot_time": observed, "positions": positions, "cash_available": body.cash_available, "total_assets": body.total_assets,
            "source_type": "agent1_validated_account_import", "source_name": "Agent1校验记账；非交易指令", "confirmed_at": None})
        update = {"id": uuid4().hex, "source_id": body.source_id, "input_digest": input_digest, "before": before,
                  "at": s.now().isoformat(), "status": "prepared", "before_fingerprint": account_identity(before),
                  "after_fingerprint": account_identity(payload.model_dump(mode="json")),
                  "changes": [{"symbol": p.symbol, "before_quantity": previous.get(p.symbol, {}).get("quantity", 0),
                               "after_quantity": p.quantity, "avg_cost": p.avg_cost} for p in positions],
                  "removed": [code for code, p in previous.items() if code not in codes and p["quantity"]]}
        rows.append(update)
        s.write(s.ROOT / "account_updates.json", rows)
        portfolio_service._persist_snapshot(payload, preserve_cost_provenance=True)
        update["status"] = "applied"
        s.write(s.ROOT / "account_updates.json", rows)
    from app.portfolio.dashboard_cache import invalidate_dashboard_cache
    invalidate_dashboard_cache()
    return {k: v for k, v in update.items() if k != "before"}


def undo(update_id):
    from app.portfolio.service import portfolio_service
    with s.LOCK, portfolio_lock(portfolio_service.root):
        rows = s.read(s.ROOT / "account_updates.json", [])
        entry = next((r for r in rows if r["id"] == update_id), None)
        if not entry or entry["status"] not in {"applied", "prepared"}:
            raise ValueError("该记录不能撤销")
        current = portfolio_service.load_snapshot().model_dump(mode="json")
        if account_identity(current) != entry["after_fingerprint"]:
            raise ValueError("入账后已有其他账户变更；不能覆盖，请人工核对")
        prior = {**entry["before"], "snapshot_id": "portfolio_snapshot_" + uuid4().hex,
                 "snapshot_time": s.now(), "source_type": "agent1_import_undo", "source_name": "撤销自动账户入账"}
        portfolio_service._persist_snapshot(PortfolioSnapshotInput(**prior), preserve_cost_provenance=True)
        entry.update(status="undone", undone_at=s.now().isoformat())
        s.write(s.ROOT / "account_updates.json", rows)
    from app.portfolio.dashboard_cache import invalidate_dashboard_cache
    invalidate_dashboard_cache()
    return {k: v for k, v in entry.items() if k != "before"}
