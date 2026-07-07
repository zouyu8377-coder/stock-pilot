from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
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
    _migrate_directions_risk_flags,
)
from app.portfolio.ipo_registry import get_ipo_entry, normalize_symbol


SEMANTIC_SUGGESTIONS: dict[str, dict[str, Any]] = {
    "601899": {
        "directions": ["COPPER", "GOLD"],
        "risk_flags": [],
        "note": "Zijin Mining: directions ordered as [COPPER, GOLD].",
    },
    "603993": {"directions": ["COPPER"], "risk_flags": []},
    "002463": {"directions": ["PCB"], "risk_flags": ["HIGH_VOLATILITY"]},
    "002916": {"directions": ["PCB"], "risk_flags": ["HIGH_VOLATILITY"]},
    "159382": {"directions": ["AI"], "risk_flags": ["HIGH_VOLATILITY"]},
    "159934": {"directions": ["GOLD"], "risk_flags": []},
    "159516": {"directions": ["SEMICONDUCTOR_EQUIPMENT"], "risk_flags": []},
    "000657": {"directions": ["TUNGSTEN"], "risk_flags": []},
}

SEMANTIC_SUGGESTIONS.update({
    "001399": {"directions": ["DISPLAY_PANEL", "SEMICONDUCTOR_EQUIPMENT"], "risk_flags": ["HIGH_VOLATILITY"]},
    "001248": {"directions": ["GREEN_POWER"], "risk_flags": ["HIGH_VOLATILITY"]},
})

CANONICAL_SECURITY_NAMES: dict[str, str] = {
    "601899": "紫金矿业",
    "603993": "洛阳钼业",
    "002463": "沪电股份",
    "002916": "深南电路",
    "159382": "创业板人工智能 ETF",
    "159934": "黄金 ETF",
    "159516": "半导体设备 ETF",
    "000657": "中钨高新",
}

CANONICAL_SECURITY_NAMES.update({
    "001399": "惠科股份",
    "001248": "华润新能源",
})


def _round(value: float | None, digits: int = 2) -> float:
    return round(float(value or 0), digits)


def _compact_symbol(symbol: str) -> str:
    return normalize_symbol(symbol)


def _dedupe_tags(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        clean = str(tag or "").strip().upper()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _sync_legacy_fields(data: dict) -> dict:
    """Populate legacy primary_theme/theme_tags from directions/risk_flags."""
    directions = data.get("directions", [])
    risk_flags = data.get("risk_flags", [])
    deprecated_tags = [
        tag for tag in data.get("theme_tags", [])
        if str(tag).strip().upper() == "COMPOSITE_EXPOSURE"
    ]
    data["primary_theme"] = directions[0] if directions else None
    data["theme_tags"] = [*directions, *risk_flags, *deprecated_tags]
    return data


def _canonical_name(symbol: str, current: str = "") -> str:
    compact = _compact_symbol(symbol)
    ipo = get_ipo_entry(compact)
    return CANONICAL_SECURITY_NAMES.get(compact) or (ipo or {}).get("name") or current or ""


def _normalize_position_semantics(data: dict) -> dict:
    legacy_primary = str(data.get("primary_theme") or "").strip().upper()
    legacy_tags = {str(tag).strip().upper() for tag in data.get("theme_tags", [])}
    had_new_directions = bool(data.get("directions"))
    _migrate_directions_risk_flags(data)
    compact = _compact_symbol(data.get("symbol", ""))
    suggestion = SEMANTIC_SUGGESTIONS.get(compact)
    if suggestion and (
        not had_new_directions
        and (legacy_primary in {"AI_PCB", "AI_THEME_ETF", "METAL_RESOURCE"} or legacy_tags & {"AI_PCB", "AI_THEME_ETF", "METAL_RESOURCE", "COMPOSITE_EXPOSURE"})
    ):
        data["directions"] = suggestion.get("directions", [])
        data["risk_flags"] = suggestion.get("risk_flags", data.get("risk_flags", []))
    data["name"] = _canonical_name(data.get("symbol", ""), data.get("name", ""))
    ipo = get_ipo_entry(compact)
    if ipo:
        if data.get("asset_type") in {None, "", "stock"}:
            data["asset_type"] = "ipo_subscription"
        data["ipo_status"] = data.get("ipo_status") or ipo.get("ipo_status")
        data["issue_price"] = data.get("issue_price") or ipo.get("issue_price")
        if not data.get("directions"):
            data["directions"] = ipo.get("directions", [])
        if not data.get("risk_flags"):
            data["risk_flags"] = ipo.get("risk_flags", [])
        _sync_legacy_fields(data)
    _sync_legacy_fields(data)
    return data


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
        for p in data.get("positions", []):
            _normalize_position_semantics(p)
        return PortfolioSnapshot(**data)

    def save_snapshot(self, payload: PortfolioSnapshotInput) -> PortfolioState:
        dumped = payload.model_dump()
        actual_cost = dumped.get("account_actual_total_cost")
        if actual_cost is not None and float(actual_cost or 0) > 0:
            dumped["account_actual_total_cost"] = _round(actual_cost)
            dumped["account_actual_total_cost_source"] = "user_manual_entry"
            dumped["account_actual_total_cost_confirmed_at"] = datetime.now(timezone.utc)
        else:
            dumped["account_actual_total_cost"] = None
            dumped["account_actual_total_cost_source"] = None
            dumped["account_actual_total_cost_confirmed_at"] = None
        for p in dumped.get("positions", []):
            _normalize_position_semantics(p)
        snapshot = PortfolioSnapshot(**dumped)
        self._write_json(self.portfolio_path, snapshot.model_dump(mode="json"))
        self._write_json(self.snapshots_dir / f"{snapshot.snapshot_id}.json", snapshot.model_dump(mode="json"))
        return self.get_state()

    def get_state(self) -> PortfolioState:
        valuation_generated_at = datetime.now(timezone.utc)
        snapshot = self.enrich_snapshot(self.load_snapshot(), valuation_generated_at=valuation_generated_at)
        return PortfolioState(
            snapshot=snapshot,
            metrics=self.compute_metrics(snapshot, valuation_generated_at=valuation_generated_at),
        )

    def semantic_suggestion_for_symbol(self, symbol: str) -> HoldingSemanticSuggestion:
        compact = _compact_symbol(symbol)
        suggestion = SEMANTIC_SUGGESTIONS.get(compact)
        if not suggestion:
            return HoldingSemanticSuggestion(
                symbol=symbol,
                suggested_primary_theme=None,
                suggested_theme_tags=[],
                suggested_directions=[],
                suggested_risk_flags=[],
                source_detail="No reviewed account semantic mapping for this symbol.",
                note="Please classify this holding manually before relying on account-level theme exposure.",
            )
        return HoldingSemanticSuggestion(
            symbol=symbol,
            suggested_primary_theme=suggestion.get("primary_theme"),
            suggested_theme_tags=suggestion.get("theme_tags", []),
            suggested_directions=suggestion.get("directions", []),
            suggested_risk_flags=suggestion.get("risk_flags", []),
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
        now = datetime.now(timezone.utc)
        positions: list[PortfolioPositionInput] = []
        for position in snapshot.positions:
            data = position.model_dump()
            update = updates.get(_compact_symbol(position.symbol))
            if update:
                data["directions"] = _dedupe_tags(update.directions)
                data["risk_flags"] = _dedupe_tags(update.risk_flags)
                _sync_legacy_fields(data)
                data["position_role"] = update.position_role
                data["semantic_classification_status"] = "user_confirmed"
                data["semantic_classification_source"] = "manual_confirmed_from_system_suggestion"
                data["semantic_classification_confirmed_at"] = now
            positions.append(PortfolioPositionInput(**data))
        snapshot.positions = positions
        snapshot.snapshot_id = f"portfolio_snapshot_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
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

    def _manual_ipo_price(self, position: PortfolioPositionInput) -> tuple[float | None, str]:
        if position.asset_type != "ipo_subscription":
            return None, ""
        for value, source in (
            (position.broker_screenshot_price, "broker_screenshot_price"),
            (position.issue_price, "ipo_issue_price"),
            (position.avg_cost, "ipo_avg_cost"),
        ):
            if value is not None and float(value or 0) > 0:
                return float(value), source
        return None, ""

    def enrich_snapshot(self, snapshot: PortfolioSnapshot, valuation_generated_at: datetime | None = None) -> PortfolioSnapshot:
        quote_retrieved_at = valuation_generated_at or datetime.now(timezone.utc)
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
            manual_ipo_price, manual_ipo_source = self._manual_ipo_price(base)
            if price is None and manual_ipo_price is not None:
                price = manual_ipo_price
                source = manual_ipo_source
            retrieved_at = quote_retrieved_at if price is not None else None
            missing_data: list[str] = []
            if price is None:
                missing_data.append("market_price")
            if base.asset_type == "ipo_subscription" and source != "easyquotation":
                missing_data.extend(["realtime_quote", "daily_k_history"])
            if base.quantity < 0:
                missing_data.append("quantity_invalid")
            is_watchlist = base.quantity == 0
            if base.avg_cost <= 0 and not is_watchlist:
                missing_data.append("avg_cost_invalid")
            can_value = price is not None and base.quantity >= 0
            can_pnl = can_value and base.avg_cost > 0
            market_value = price * base.quantity if can_value else None
            pnl = (price - base.avg_cost) * base.quantity if can_pnl else None
            pnl_pct = ((price / base.avg_cost - 1) * 100) if can_pnl else None
            data = base.model_dump()
            data["name"] = _canonical_name(base.symbol, base.name or quote_name)
            positions.append(PortfolioPosition(
                **data,
                position_status="watchlist" if is_watchlist else "active",
                valuation_scope="asset_metric_excluded" if is_watchlist else ("manual_ipo_valuation" if base.asset_type == "ipo_subscription" and source != "easyquotation" else "asset_metric_included"),
                market_price=_round(price, 4) if price is not None else None,
                market_value=_round(market_value) if market_value is not None else None,
                unrealized_pnl=_round(pnl) if pnl is not None else None,
                unrealized_pnl_pct=_round(pnl_pct) if pnl_pct is not None else None,
                price_source=source,
                system_quote_price=_round(price, 4) if price is not None else None,
                system_quote_retrieved_at=retrieved_at,
                system_quote_market_time=None,
                quote_time_status="unavailable" if source == "easyquotation" else "manual_ipo_price" if base.asset_type == "ipo_subscription" and price is not None else "unavailable",
                data_status="available" if not missing_data else "manual_ipo_valuation" if base.asset_type == "ipo_subscription" and price is not None else "missing_data",
                missing_data=sorted(set(missing_data)),
            ))
        snapshot.positions = positions
        return snapshot

    def compute_metrics(self, snapshot: PortfolioSnapshot, valuation_generated_at: datetime | None = None) -> PortfolioMetrics:
        valuation_generated_at = valuation_generated_at or datetime.now(timezone.utc)
        valuation_snapshot_id = f"valuation_{valuation_generated_at.strftime('%Y%m%d%H%M%S%f')}"
        # Filter positions with positive quantity for asset-metric aggregations
        active_positions = [p for p in snapshot.positions if p.quantity is not None and p.quantity > 0]
        watchlist_positions = [p for p in snapshot.positions if p.quantity == 0]

        total_market_value = sum(p.market_value or 0 for p in active_positions)
        current_quote_total_assets = total_market_value + snapshot.cash_available + snapshot.repo_amount
        total_assets = current_quote_total_assets
        total_assets = max(total_assets, 0.01)
        position_weights = []
        pnl_contributors = []
        primary: dict[str, dict[str, Any]] = {}
        risk_tags: dict[str, dict[str, Any]] = {}
        composite_notes = []
        missing_data = []

        total_cost_basis = 0.0
        total_unrealized_pnl = 0.0
        excluded_symbols: list[str] = []

        for p in snapshot.positions:
            if p.missing_data:
                missing_data.append({"symbol": p.symbol, "fields": p.missing_data, "data_status": p.data_status})
            # Only active positions participate in weight/exposure/cost aggregations
            if p.quantity is None or p.quantity <= 0:
                continue
            market_value = p.market_value or 0
            weight = market_value / total_assets * 100
            position_weights.append({"symbol": p.symbol, "name": p.name, "weight_pct": _round(weight), "market_value": p.market_value, "data_status": p.data_status})
            pnl_contributors.append({"symbol": p.symbol, "name": p.name, "unrealized_pnl": p.unrealized_pnl, "unrealized_pnl_pct": p.unrealized_pnl_pct, "data_status": p.data_status})
            primary_direction = (p.directions[0] if p.directions else "UNCLASSIFIED").strip().upper()
            entry = primary.setdefault(primary_direction, {"market_value": 0.0, "symbols": []})
            entry["market_value"] += market_value
            entry["symbols"].append(p.symbol)
            for flag in _dedupe_tags(p.risk_flags):
                if flag == "UNCLASSIFIED":
                    continue
                risk_entry = risk_tags.setdefault(flag, {"market_value": 0.0, "symbols": []})
                risk_entry["market_value"] += market_value
                risk_entry["symbols"].append(p.symbol)
            if "COMPOSITE_EXPOSURE" in set(p.theme_tags):
                composite_notes.append(
                    f"{p.symbol} 同时暴露于 {', '.join(p.theme_tags)}，主题占比不可简单相加。"
                )

            # Cost basis and unrealized PnL aggregation
            if p.avg_cost is not None and p.avg_cost > 0 and p.quantity is not None and p.quantity >= 0:
                total_cost_basis += p.avg_cost * p.quantity
                if p.market_price is not None and p.market_price > 0:
                    total_unrealized_pnl += (p.market_price - p.avg_cost) * p.quantity
                else:
                    excluded_symbols.append(p.symbol)
            else:
                excluded_symbols.append(p.symbol)

        primary_exposures = [
            ThemeExposure(theme=k, market_value=_round(v["market_value"]), weight_pct=_round(v["market_value"] / total_assets * 100), symbols=v["symbols"])
            for k, v in primary.items()
        ]
        risk_exposures = [
            ThemeExposure(theme=k, market_value=_round(v["market_value"]), weight_pct=_round(v["market_value"] / total_assets * 100), symbols=sorted(set(v["symbols"])))
            for k, v in risk_tags.items()
        ]

        warnings = []
        for p in active_positions:
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
            if not p.directions or str(p.directions[0]).strip().upper() == "UNCLASSIFIED"
        ]
        warnings = []
        if unclassified:
            warnings.append(
                "There are holdings without confirmed directions; account direction exposure is incomplete. "
                f"Please confirm holding semantics first: {', '.join(unclassified)}."
            )

        pnl_status = "available"
        if excluded_symbols:
            pnl_status = "partial" if total_cost_basis > 0 else "unavailable"

        actual_cost = snapshot.account_actual_total_cost if snapshot.account_actual_total_cost and snapshot.account_actual_total_cost > 0 else None
        account_total_pnl = (total_assets - actual_cost) if actual_cost else None
        account_total_pnl_pct = (account_total_pnl / actual_cost * 100) if actual_cost and account_total_pnl is not None else None
        account_pnl_status = "available" if actual_cost else "unavailable"

        primary_sum = sum(exposure.market_value for exposure in primary_exposures)
        holding_pnl_sum = sum(p.unrealized_pnl or 0 for p in active_positions)
        total_assets_components = total_market_value + snapshot.cash_available + snapshot.repo_amount
        checks = {
            "holdings_market_value_matches_summary": abs(total_market_value - sum(p.market_value or 0 for p in active_positions)) <= 0.01,
            "primary_direction_groups_match_summary": abs(total_market_value - primary_sum) <= 0.01,
            "holding_pnl_matches_summary": abs(total_unrealized_pnl - holding_pnl_sum) <= 0.01,
            "total_assets_matches_components": abs(total_assets - total_assets_components) <= 0.01,
            "account_total_pnl_matches_actual_cost_basis": True if not actual_cost else abs((total_assets - actual_cost) - (account_total_pnl or 0)) <= 0.01,
        }
        diffs = {
            "holdings_market_value_delta": _round(total_market_value - sum(p.market_value or 0 for p in active_positions)),
            "primary_direction_market_value_delta": _round(total_market_value - primary_sum),
            "holding_unrealized_pnl_delta": _round(total_unrealized_pnl - holding_pnl_sum),
            "total_assets_components_delta": _round(total_assets - total_assets_components),
        }
        errors = [key for key, passed in checks.items() if not passed]

        return PortfolioMetrics(
            total_assets=_round(total_assets),
            total_market_value=_round(total_market_value),
            cash_available=_round(snapshot.cash_available),
            account_actual_total_cost=_round(actual_cost) if actual_cost else None,
            account_actual_total_cost_source=snapshot.account_actual_total_cost_source,
            account_actual_total_cost_confirmed_at=snapshot.account_actual_total_cost_confirmed_at,
            account_total_pnl=_round(account_total_pnl) if account_total_pnl is not None else None,
            account_total_pnl_pct=_round(account_total_pnl_pct) if account_total_pnl_pct is not None else None,
            account_total_pnl_status=account_pnl_status,
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
            total_cost_basis=_round(total_cost_basis) if total_cost_basis > 0 else None,
            total_unrealized_pnl=_round(total_unrealized_pnl) if total_cost_basis > 0 else None,
            total_unrealized_pnl_pct=_round(total_unrealized_pnl / total_cost_basis * 100) if total_cost_basis > 0 else None,
            total_unrealized_pnl_status=pnl_status,
            current_holding_cost_basis=_round(total_cost_basis) if total_cost_basis > 0 else None,
            current_holding_unrealized_pnl=_round(total_unrealized_pnl) if total_cost_basis > 0 else None,
            current_holding_unrealized_pnl_pct=_round(total_unrealized_pnl / total_cost_basis * 100) if total_cost_basis > 0 else None,
            current_holding_unrealized_pnl_status=pnl_status,
            valuation_snapshot_id=valuation_snapshot_id,
            valuation_generated_at=valuation_generated_at,
            quote_retrieved_at=valuation_generated_at,
            valuation_consistency_status="failed" if errors else "passed",
            valuation_consistency_checks=checks,
            valuation_consistency_errors=errors,
            valuation_consistency_diffs=diffs,
            excluded_symbols=sorted(set(excluded_symbols)),
            position_weights=sorted(position_weights, key=lambda x: x["weight_pct"], reverse=True),
            pnl_contributors=sorted(pnl_contributors, key=lambda x: x["unrealized_pnl"] or 0, reverse=True),
            primary_theme_exposures=sorted(primary_exposures, key=lambda x: x.weight_pct, reverse=True),
            risk_tag_exposures=sorted(risk_exposures, key=lambda x: x.weight_pct, reverse=True),
            warnings=warnings,
            composite_exposure_notes=composite_notes,
            missing_data=missing_data,
            active_position_count=len(active_positions),
            watchlist_position_count=len(watchlist_positions),
            watchlist_symbols=[p.symbol for p in watchlist_positions],
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
                        directions=request.directions or p.directions,
                        risk_flags=request.risk_flags or p.risk_flags,
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
                directions=request.directions,
                risk_flags=request.risk_flags,
                user_plan=request.reason,
            ))
        if not found and request.side == TradeSide.SELL:
            raise ValueError("cannot sell a symbol that is not in current holdings.")

        snapshot.positions = new_positions
        after_snapshot = self.enrich_snapshot(snapshot)
        after = self.compute_metrics(after_snapshot)
        risk_notes = []
        matching = [p for p in after_snapshot.positions if _compact_symbol(p.symbol) == _compact_symbol(request.symbol)]
        if matching and len(set(matching[0].directions)) > 1:
            risk_notes.append(f"{request.symbol} 同时具有 {', '.join(matching[0].directions)} 相关性，该操作不是分散风险，而是在已有主题交叉处增加弹性。")
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

    def build_portfolio_snapshot(
        self,
        user_question: str | None = None,
        persist: bool = True,
        state: PortfolioState | None = None,
    ) -> AnalysisSnapshot:
        state = state or self.get_state()
        evidence_items: list[EvidenceItem] = []
        now = datetime.now(timezone.utc)
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
