from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from app.collector.router import collector
from app.core.config import settings
from app.evidence.schemas import (
    AnalysisScope,
    AnalysisSnapshot,
    DataStatus,
    EvidenceCategory,
    EvidenceItem,
    EvidenceReliability,
    EvidenceType,
    LlmUsage,
)
from app.portfolio.schemas import (
    DEFAULT_PORTFOLIO_ID,
    DEFAULT_THEME_TAGS,
    HoldingSemanticBatchUpdate,
    HoldingSemanticSuggestion,
    ManualEvidenceCreate,
    ManualEvidenceRecord,
    PortfolioMetrics,
    PortfolioPosition,
    PortfolioPositionInput,
    PortfolioSnapshot,
    PortfolioSnapshotInput,
    PortfolioState,
    ThemeExposure,
    TradeSide,
    TradeSimulationRequest,
    TradeSimulationResult,
)


SEMANTIC_SUGGESTIONS: dict[str, dict[str, Any]] = {
    "601899": {
        "primary_theme": "METAL_RESOURCE",
        "theme_tags": ["METAL_RESOURCE", "GOLD", "COMPOSITE_EXPOSURE"],
        "note": (
            "Zijin Mining is associated with both resource metals and gold. primary_theme is used only for "
            "one official account attribution; keep the other association in theme_tags."
        ),
    },
    "603993": {"primary_theme": "METAL_RESOURCE", "theme_tags": ["METAL_RESOURCE"]},
    "002463": {"primary_theme": "AI_PCB", "theme_tags": ["AI_PCB", "HIGH_VOLATILITY"]},
    "002916": {"primary_theme": "AI_PCB", "theme_tags": ["AI_PCB", "HIGH_VOLATILITY"]},
    "159382": {"primary_theme": "AI_THEME_ETF", "theme_tags": ["AI_THEME_ETF", "HIGH_VOLATILITY"]},
    "159934": {"primary_theme": "GOLD", "theme_tags": ["GOLD"]},
    "000657": {
        "primary_theme": "TUNGSTEN",
        "theme_tags": ["TUNGSTEN", "METAL_RESOURCE", "AI_PCB", "COMPOSITE_EXPOSURE"],
    },
}


def _round(value: float | None, digits: int = 2) -> float:
    return round(float(value or 0), digits)


def _compact_symbol(symbol: str) -> str:
    return symbol.split(".", 1)[0].strip().zfill(6)


def _dedupe_tags(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        clean = str(tag or "").strip().upper()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


class PortfolioService:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or settings.PORTFOLIO_DATA_DIR)
        self.root.mkdir(parents=True, exist_ok=True)
        self.portfolio_path = self.root / "default_portfolio.json"
        self.snapshots_dir = self.root / "snapshots"
        self.evidence_path = self.root / "manual_evidence.json"

    def _read_json(self, path: Path, default):
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    def load_snapshot(self) -> PortfolioSnapshot:
        data = self._read_json(self.portfolio_path, None)
        if not data:
            return PortfolioSnapshot(portfolio_id=DEFAULT_PORTFOLIO_ID, cash_available=0, positions=[])
        return PortfolioSnapshot(**data)

    def save_snapshot(self, payload: PortfolioSnapshotInput) -> PortfolioState:
        snapshot = PortfolioSnapshot(**payload.model_dump())
        self._write_json(self.portfolio_path, snapshot.model_dump(mode="json"))
        self._write_json(self.snapshots_dir / f"{snapshot.snapshot_id}.json", snapshot.model_dump(mode="json"))
        return self.get_state()

    def get_state(self) -> PortfolioState:
        snapshot = self.enrich_snapshot(self.load_snapshot())
        return PortfolioState(snapshot=snapshot, metrics=self.compute_metrics(snapshot))

    def semantic_suggestion_for_symbol(self, symbol: str) -> HoldingSemanticSuggestion:
        compact = _compact_symbol(symbol)
        suggestion = SEMANTIC_SUGGESTIONS.get(compact)
        if not suggestion:
            return HoldingSemanticSuggestion(
                symbol=symbol,
                suggested_primary_theme=None,
                suggested_theme_tags=[],
                source_detail="No reviewed account semantic mapping for this symbol.",
                note="Please classify this holding manually before relying on account-level theme exposure.",
            )
        return HoldingSemanticSuggestion(
            symbol=symbol,
            suggested_primary_theme=suggestion["primary_theme"],
            suggested_theme_tags=suggestion["theme_tags"],
            source_detail=f"Reviewed static mapping for {compact}.",
            note=suggestion.get("note"),
        )

    def holding_semantic_suggestions(self) -> list[HoldingSemanticSuggestion]:
        return [
            self.semantic_suggestion_for_symbol(position.symbol)
            for position in self.load_snapshot().positions
        ]

    def update_holding_semantics(self, payload: HoldingSemanticBatchUpdate) -> PortfolioState:
        snapshot = self.load_snapshot()
        updates = {_compact_symbol(item.symbol): item for item in payload.updates}
        now = datetime.utcnow()
        positions: list[PortfolioPositionInput] = []
        for position in snapshot.positions:
            data = position.model_dump()
            update = updates.get(_compact_symbol(position.symbol))
            if update:
                data["primary_theme"] = (update.primary_theme or "UNCLASSIFIED").strip().upper()
                data["theme_tags"] = _dedupe_tags(update.theme_tags)
                data["position_role"] = update.position_role
                data["semantic_classification_status"] = "user_confirmed"
                data["semantic_classification_source"] = "manual_confirmed_from_system_suggestion"
                data["semantic_classification_confirmed_at"] = now
            positions.append(PortfolioPositionInput(**data))
        snapshot.positions = positions
        snapshot.snapshot_id = f"portfolio_snapshot_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
        snapshot.snapshot_time = now
        return self.save_snapshot(PortfolioSnapshotInput(**snapshot.model_dump()))

    def _quote_price(self, symbol: str) -> tuple[float | None, str, str]:
        try:
            quote = collector.get_quote(_compact_symbol(symbol))
            price = quote.get("price")
            name = quote.get("name") or ""
            if price is not None and float(price) > 0:
                return float(price), "easyquotation", name
        except Exception:
            pass
        return None, "missing_quote", ""

    def enrich_snapshot(self, snapshot: PortfolioSnapshot) -> PortfolioSnapshot:
        positions: list[PortfolioPosition] = []
        for item in snapshot.positions:
            base = PortfolioPositionInput(**item.model_dump(exclude={
                "market_price",
                "market_value",
                "unrealized_pnl",
                "unrealized_pnl_pct",
                "price_source",
                "system_quote_price",
                "system_quote_retrieved_at",
                "system_quote_market_time",
                "quote_time_status",
                "data_status",
                "missing_data",
            }))
            price, source, quote_name = self._quote_price(base.symbol)
            retrieved_at = datetime.utcnow() if price is not None else None
            missing_data: list[str] = []
            if price is None:
                missing_data.append("market_price")
            if base.quantity < 0:
                missing_data.append("quantity_invalid")
            if base.avg_cost <= 0:
                missing_data.append("avg_cost_invalid")
            can_value = price is not None and base.quantity >= 0
            can_pnl = can_value and base.avg_cost > 0
            market_value = price * base.quantity if can_value else None
            pnl = (price - base.avg_cost) * base.quantity if can_pnl else None
            pnl_pct = ((price / base.avg_cost - 1) * 100) if can_pnl else None
            data = base.model_dump()
            data["name"] = base.name or quote_name
            positions.append(PortfolioPosition(
                **data,
                market_price=_round(price, 4) if price is not None else None,
                market_value=_round(market_value) if market_value is not None else None,
                unrealized_pnl=_round(pnl) if pnl is not None else None,
                unrealized_pnl_pct=_round(pnl_pct) if pnl_pct is not None else None,
                price_source=source,
                system_quote_price=_round(price, 4) if price is not None else None,
                system_quote_retrieved_at=retrieved_at,
                system_quote_market_time=None,
                quote_time_status="unavailable",
                data_status="available" if not missing_data else "missing_data",
                missing_data=missing_data,
            ))
        snapshot.positions = positions
        return snapshot

    def compute_metrics(self, snapshot: PortfolioSnapshot) -> PortfolioMetrics:
        total_market_value = sum(p.market_value or 0 for p in snapshot.positions)
        current_quote_total_assets = total_market_value + snapshot.cash_available + snapshot.repo_amount
        total_assets = current_quote_total_assets
        total_assets = max(total_assets, 0.01)
        position_weights = []
        pnl_contributors = []
        primary: dict[str, dict[str, Any]] = {}
        risk_tags: dict[str, dict[str, Any]] = {}
        composite_notes = []
        missing_data = []

        for p in snapshot.positions:
            if p.missing_data:
                missing_data.append({"symbol": p.symbol, "fields": p.missing_data, "data_status": p.data_status})
            market_value = p.market_value or 0
            weight = market_value / total_assets * 100
            position_weights.append({"symbol": p.symbol, "name": p.name, "weight_pct": _round(weight), "market_value": p.market_value, "data_status": p.data_status})
            pnl_contributors.append({"symbol": p.symbol, "name": p.name, "unrealized_pnl": p.unrealized_pnl, "unrealized_pnl_pct": p.unrealized_pnl_pct, "data_status": p.data_status})
            primary_theme = (p.primary_theme or "UNCLASSIFIED").strip().upper()
            entry = primary.setdefault(primary_theme, {"market_value": 0.0, "symbols": []})
            entry["market_value"] += market_value
            entry["symbols"].append(p.symbol)
            for tag in _dedupe_tags(p.theme_tags):
                if tag == "UNCLASSIFIED":
                    continue
                risk_entry = risk_tags.setdefault(tag, {"market_value": 0.0, "symbols": []})
                risk_entry["market_value"] += market_value
                risk_entry["symbols"].append(p.symbol)
            if len(set(p.theme_tags)) > 1:
                composite_notes.append(
                    f"{p.symbol} 同时暴露于 {', '.join(p.theme_tags)}，主题占比不可简单相加。"
                )

        primary_exposures = [
            ThemeExposure(theme=k, market_value=_round(v["market_value"]), weight_pct=_round(v["market_value"] / total_assets * 100), symbols=v["symbols"])
            for k, v in primary.items()
        ]
        risk_exposures = [
            ThemeExposure(theme=k, market_value=_round(v["market_value"]), weight_pct=_round(v["market_value"] / total_assets * 100), symbols=sorted(set(v["symbols"])))
            for k, v in risk_tags.items()
        ]

        warnings = []
        for p in snapshot.positions:
            limit = p.target_max_weight or snapshot.risk_limits.max_position_weight
            weight = (p.market_value or 0) / total_assets * 100
            if weight > limit:
                warnings.append(f"{p.symbol} 单票占比 {weight:.2f}% 超过上限 {limit:.2f}%。")
        for exposure in primary_exposures:
            if exposure.weight_pct > snapshot.risk_limits.max_theme_weight:
                warnings.append(f"{exposure.theme} 唯一归属占比 {exposure.weight_pct:.2f}% 超过主题上限 {snapshot.risk_limits.max_theme_weight:.2f}%。")
        cash_ratio = snapshot.cash_available / total_assets * 100
        if cash_ratio < snapshot.risk_limits.min_cash_ratio:
            warnings.append(f"现金比例 {cash_ratio:.2f}% 低于底线 {snapshot.risk_limits.min_cash_ratio:.2f}%。")

        unclassified = [
            p.symbol for p in snapshot.positions
            if not p.primary_theme or str(p.primary_theme).strip().upper() == "UNCLASSIFIED"
        ]
        warnings = []
        if unclassified:
            warnings.append(
                "There are holdings without confirmed primary_theme; account theme exposure is incomplete. "
                f"Please confirm holding semantics first: {', '.join(unclassified)}."
            )

        return PortfolioMetrics(
            total_assets=_round(total_assets),
            total_market_value=_round(total_market_value),
            cash_available=_round(snapshot.cash_available),
            repo_amount=_round(snapshot.repo_amount),
            snapshot_total_assets=_round(snapshot.total_assets) if snapshot.total_assets is not None else None,
            snapshot_cash_available=_round(snapshot.cash_available),
            snapshot_repo_amount=_round(snapshot.repo_amount),
            estimated_total_assets_using_current_quotes=_round(total_assets),
            estimated_position_weight_pct=_round(total_market_value / total_assets * 100),
            estimated_cash_weight_pct=_round(cash_ratio),
            estimated_repo_weight_pct=_round(snapshot.repo_amount / total_assets * 100),
            cash_ratio_pct=_round(cash_ratio),
            repo_ratio_pct=_round(snapshot.repo_amount / total_assets * 100),
            invested_ratio_pct=_round(total_market_value / total_assets * 100),
            position_weights=sorted(position_weights, key=lambda x: x["weight_pct"], reverse=True),
            pnl_contributors=sorted(pnl_contributors, key=lambda x: x["unrealized_pnl"] or 0, reverse=True),
            primary_theme_exposures=sorted(primary_exposures, key=lambda x: x.weight_pct, reverse=True),
            risk_tag_exposures=sorted(risk_exposures, key=lambda x: x.weight_pct, reverse=True),
            warnings=warnings,
            composite_exposure_notes=composite_notes,
            missing_data=missing_data,
        )

    def list_manual_evidence(self) -> list[ManualEvidenceRecord]:
        return [ManualEvidenceRecord(**item) for item in self._read_json(self.evidence_path, [])]

    def add_manual_evidence(self, payload: ManualEvidenceCreate) -> ManualEvidenceRecord:
        items = self.list_manual_evidence()
        record = ManualEvidenceRecord(**payload.model_dump())
        items.append(record)
        self._write_json(self.evidence_path, [item.model_dump(mode="json") for item in items])
        return record

    def delete_manual_evidence(self, evidence_id: str) -> bool:
        items = self.list_manual_evidence()
        kept = [item for item in items if item.evidence_id != evidence_id]
        if len(kept) == len(items):
            return False
        self._write_json(self.evidence_path, [item.model_dump(mode="json") for item in kept])
        return True

    def update_manual_evidence_include(self, evidence_id: str, include: bool) -> ManualEvidenceRecord | None:
        items = self.list_manual_evidence()
        updated: ManualEvidenceRecord | None = None
        for item in items:
            if item.evidence_id == evidence_id:
                item.include_in_analysis_packet = include
                updated = item
                break
        if updated is None:
            return None
        self._write_json(self.evidence_path, [item.model_dump(mode="json") for item in items])
        return updated

    def simulate_trade(self, request: TradeSimulationRequest) -> TradeSimulationResult:
        if request.estimated_price <= 0:
            raise ValueError("estimated_price must be greater than 0 for read-only simulation.")
        state = self.get_state()
        snapshot = deepcopy(state.snapshot)
        quantity = request.quantity
        if quantity is None:
            quantity = (request.amount or 0) / request.estimated_price if request.estimated_price else 0
        trade_value = quantity * request.estimated_price
        signed_qty = quantity if request.side == TradeSide.BUY else -quantity
        cash_delta = -trade_value if request.side == TradeSide.BUY else trade_value
        snapshot.cash_available += cash_delta

        found = False
        new_positions: list[PortfolioPosition] = []
        for p in snapshot.positions:
            if _compact_symbol(p.symbol) == _compact_symbol(request.symbol):
                found = True
                if request.side == TradeSide.SELL and quantity > (p.available_quantity if p.available_quantity is not None else p.quantity):
                    raise ValueError("sell quantity exceeds available_quantity; original portfolio was not modified.")
                new_qty = p.quantity + signed_qty
                if new_qty > 0:
                    avg_cost = p.avg_cost
                    if request.side == TradeSide.BUY:
                        avg_cost = ((p.avg_cost * p.quantity) + trade_value) / new_qty
                    new_positions.append(PortfolioPositionInput(
                        symbol=p.symbol,
                        name=p.name or request.name,
                        quantity=new_qty,
                        available_quantity=p.available_quantity,
                        avg_cost=avg_cost,
                        position_role=p.position_role,
                        theme_tags=request.theme_tags or p.theme_tags,
                        primary_theme=request.primary_theme or p.primary_theme,
                        user_plan=p.user_plan,
                        invalid_condition=p.invalid_condition,
                        target_max_weight=p.target_max_weight,
                        notes=p.notes,
                    ))
                continue
            new_positions.append(PortfolioPositionInput(**p.model_dump(exclude={"market_price", "market_value", "unrealized_pnl", "unrealized_pnl_pct", "price_source", "data_status", "missing_data"})))

        if not found and request.side == TradeSide.BUY and quantity > 0:
            new_positions.append(PortfolioPositionInput(
                symbol=request.symbol,
                name=request.name,
                quantity=quantity,
                avg_cost=request.estimated_price,
                position_role=request.position_role,
                theme_tags=request.theme_tags,
                primary_theme=request.primary_theme,
                user_plan=request.reason,
            ))
        if not found and request.side == TradeSide.SELL:
            raise ValueError("cannot sell a symbol that is not in current holdings.")

        snapshot.positions = new_positions
        after_snapshot = self.enrich_snapshot(snapshot)
        after = self.compute_metrics(after_snapshot)
        risk_notes = []
        matching = [p for p in after_snapshot.positions if _compact_symbol(p.symbol) == _compact_symbol(request.symbol)]
        if matching and len(set(matching[0].theme_tags)) > 1:
            risk_notes.append(f"{request.symbol} 同时具有 {', '.join(matching[0].theme_tags)} 相关性，该操作不是分散风险，而是在已有主题交叉处增加弹性。")
        if request.side == TradeSide.BUY and trade_value > state.snapshot.cash_available:
            risk_notes.append("Buy simulation amount exceeds current cash_available; this is a risk reminder only and does not change the saved portfolio.")
        if request.planned:
            risk_notes.append("该交易被标记为计划内动作；仍需检查是否增强已有主题集中度。")
        return TradeSimulationResult(
            before=state.metrics,
            after=after,
            trade={
                "side": request.side.value,
                "symbol": request.symbol,
                "quantity": _round(quantity, 4),
                "estimated_price": request.estimated_price,
                "trade_value": _round(trade_value),
                "reason": request.reason,
                "planned": request.planned,
            },
            deltas={
                "cash_ratio_pct": _round(after.cash_ratio_pct - state.metrics.cash_ratio_pct),
                "invested_ratio_pct": _round(after.invested_ratio_pct - state.metrics.invested_ratio_pct),
            },
            warnings=after.warnings,
            risk_notes=risk_notes,
        )

    def _manual_record_to_evidence(self, record: ManualEvidenceRecord) -> EvidenceItem:
        payload = record.model_dump(mode="json")
        evidence_type = EvidenceType(record.evidence_type.value)
        reliability = EvidenceReliability(record.reliability.value)
        usage = LlmUsage(record.llm_usage)
        category = EvidenceCategory.MANUAL_EVIDENCE
        return EvidenceItem(
            evidence_id=record.evidence_id,
            symbol=record.symbol,
            evidence_type=evidence_type,
            category=category,
            title=record.title,
            value=record.value,
            payload=payload,
            source=record.source,
            as_of_time=record.as_of_time,
            as_of_date=record.as_of_date or record.end_date,
            fetched_at=record.recorded_at,
            reliability=reliability,
            llm_usage=usage,
            interpretation_limit="手动录入证据，仅在用户选择纳入分析包时使用；需保留来源与日期边界。",
            data_status=DataStatus.AVAILABLE,
            notes=record.notes,
        )

    def build_portfolio_snapshot(self, user_question: str | None = None, persist: bool = True) -> AnalysisSnapshot:
        state = self.get_state()
        evidence_items: list[EvidenceItem] = []
        now = datetime.utcnow()
        for position in state.snapshot.positions:
            evidence_items.append(EvidenceItem(
                symbol=position.symbol,
                evidence_type=EvidenceType.PORTFOLIO_POSITION,
                category=EvidenceCategory.MANUAL_ACCOUNT,
                title=f"持仓 {position.symbol}",
                payload=position.model_dump(mode="json"),
                source="用户本地持仓快照",
                as_of_time=state.snapshot.snapshot_time,
                fetched_at=now,
                reliability=EvidenceReliability.A_MANUAL_VERIFIED,
                llm_usage=LlmUsage.CONTEXT_ONLY,
                interpretation_limit="本地账户上下文，不自动发送给外部LLM，仅用于用户主动生成的Analysis Packet。",
            ))
        evidence_items.append(EvidenceItem(
            evidence_type=EvidenceType.PORTFOLIO_CASH,
            category=EvidenceCategory.MANUAL_ACCOUNT,
            title="现金与逆回购",
            payload={
                "cash_available": state.snapshot.cash_available,
                "repo_amount": state.snapshot.repo_amount,
                "repo_available_date": state.snapshot.repo_available_date.isoformat() if state.snapshot.repo_available_date else None,
                "metrics": state.metrics.model_dump(mode="json"),
            },
            source="用户本地持仓快照",
            as_of_time=state.snapshot.snapshot_time,
            fetched_at=now,
            reliability=EvidenceReliability.A_MANUAL_VERIFIED,
            llm_usage=LlmUsage.CONTEXT_ONLY,
            interpretation_limit="账户现金上下文，不自动发送给外部LLM。",
        ))
        for record in self.list_manual_evidence():
            if record.include_in_analysis_packet:
                evidence_items.append(self._manual_record_to_evidence(record))
        system_hypotheses = [
            EvidenceItem(
                evidence_type=EvidenceType.SYSTEM_MARKET_REGIME,
                category=EvidenceCategory.SYSTEM_HYPOTHESIS,
                title="Portfolio rule reminder",
                payload={"warning": warning, "metrics_scope": "portfolio"},
                source="Stock-Pilot portfolio rules",
                source_endpoint="portfolio.compute_metrics",
                as_of_time=state.snapshot.snapshot_time,
                fetched_at=now,
                reliability=EvidenceReliability.H,
                llm_usage=LlmUsage.HYPOTHESIS_ONLY,
                interpretation_limit="System-generated portfolio reminder only. It is not a buy/sell instruction or verified market fact.",
            )
            for warning in state.metrics.warnings
        ]

        snapshot = AnalysisSnapshot(
            analysis_scope=AnalysisScope.PORTFOLIO,
            target_symbols=[p.symbol for p in state.snapshot.positions],
            user_question=user_question,
            portfolio_as_of=state.snapshot.snapshot_time,
            evidence_items=evidence_items,
            missing_data=[
                *state.metrics.missing_data,
                "券商账户未自动同步",
                "历史交易流水、分红、手续费与严格T+0/T+1账务未建模",
            ],
            system_hypotheses=system_hypotheses,
            version="analysis_snapshot.portfolio.v0",
        )
        if persist:
            out_dir = Path(settings.ANALYSIS_SNAPSHOT_DIR) / "portfolio"
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{snapshot.snapshot_id}.json"
            path.write_text(json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        return snapshot


portfolio_service = PortfolioService()
