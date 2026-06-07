from datetime import date

import pytest

from app.portfolio.schemas import (
    HoldingSemanticBatchUpdate,
    HoldingSemanticUpdate,
    ManualEvidenceCreate,
    ManualEvidenceType,
    PortfolioPositionInput,
    PortfolioSnapshotInput,
    RiskLimits,
    TradeSide,
    TradeSimulationRequest,
)
from app.portfolio.service import PortfolioService
from app.portfolio.dashboard import build_dashboard, build_market_event_radar


def _fake_quote(symbol: str):
    prices = {
        "002463": {"price": 100.0, "name": "HD"},
        "000657": {"price": 20.0, "name": "ZW"},
        "159934": {"price": 6.0, "name": "Gold ETF"},
    }
    return {**prices.get(symbol, {"price": 10.0, "name": symbol}), "provider": "test"}


def _missing_quote(symbol: str):
    raise RuntimeError("quote unavailable in test")


def test_empty_portfolio_with_cash_is_valid(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    service = PortfolioService(tmp_path)
    state = service.save_snapshot(PortfolioSnapshotInput(cash_available=100000, positions=[]))

    assert state.metrics.total_assets == 100000
    assert state.metrics.total_market_value == 0
    assert state.metrics.invested_ratio_pct == 0
    assert state.metrics.cash_ratio_pct == 100


def test_portfolio_snapshot_valuation_and_exposures(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    service = PortfolioService(tmp_path)
    state = service.save_snapshot(PortfolioSnapshotInput(
        cash_available=30000,
        repo_amount=20000,
        positions=[
            PortfolioPositionInput(symbol="002463", name="HD", quantity=1000, avg_cost=80, theme_tags=["AI_PCB"], primary_theme="AI_PCB", target_max_weight=60),
            PortfolioPositionInput(symbol="000657", name="ZW", quantity=2000, avg_cost=15, theme_tags=["AI_PCB", "METAL_RESOURCE", "TUNGSTEN", "COMPOSITE_EXPOSURE"], primary_theme="METAL_RESOURCE"),
            PortfolioPositionInput(symbol="159934", name="Gold ETF", quantity=5000, avg_cost=5, theme_tags=["GOLD"], primary_theme="GOLD"),
        ],
    ))

    assert state.metrics.total_market_value == 170000
    assert state.metrics.total_assets == 220000
    assert state.metrics.cash_ratio_pct == 13.64
    primary = {item.theme: item.weight_pct for item in state.metrics.primary_theme_exposures}
    assert primary["PCB"] == 45.45
    assert primary["TUNGSTEN"] == 18.18
    assert sum(primary.values()) <= 100
    assert any("000657" in note for note in state.metrics.composite_exposure_notes)


def test_unconfirmed_directions_do_not_become_official_exposure(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    service = PortfolioService(tmp_path)
    state = service.save_snapshot(PortfolioSnapshotInput(
        cash_available=10000,
        positions=[
            PortfolioPositionInput(symbol="002463", name="HD", quantity=100, avg_cost=80),
        ],
    ))

    primary = {item.theme: item.weight_pct for item in state.metrics.primary_theme_exposures}

    assert "AI_PCB" not in primary
    assert "UNCLASSIFIED" in primary
    assert any("without confirmed directions" in warning for warning in state.metrics.warnings)


def test_zero_quantity_symbol_is_saved_as_watchlist_without_asset_exposure(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    service = PortfolioService(tmp_path)
    state = service.save_snapshot(PortfolioSnapshotInput(
        cash_available=10000,
        positions=[
            PortfolioPositionInput(symbol="002463", name="HD", quantity=100, avg_cost=80),
            PortfolioPositionInput(
                symbol="000657",
                name="ZW",
                quantity=0,
                available_quantity=0,
                avg_cost=0,
                position_role="observation",
                directions=["TUNGSTEN"],
            ),
        ],
    ))

    active = next(p for p in state.snapshot.positions if p.symbol == "002463")
    watch = next(p for p in state.snapshot.positions if p.symbol == "000657")
    snapshot = service.build_portfolio_snapshot(persist=False)
    position_payloads = [
        item.payload
        for item in snapshot.evidence_items
        if item.evidence_type == "portfolio_position"
    ]

    assert active.position_status == "active"
    assert watch.position_status == "watchlist"
    assert watch.valuation_scope == "asset_metric_excluded"
    assert watch.market_value == 0
    assert "avg_cost_invalid" not in watch.missing_data
    assert state.metrics.total_market_value == 10000
    assert state.metrics.active_position_count == 1
    assert state.metrics.watchlist_position_count == 1
    assert state.metrics.watchlist_symbols == ["000657"]
    assert {item["symbol"] for item in position_payloads} == {"002463", "000657"}
    assert {item["symbol"] for item in state.metrics.position_weights} == {"002463"}


def test_dashboard_separates_watchlist_from_active_exposure(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    service = PortfolioService(tmp_path)
    state = service.save_snapshot(PortfolioSnapshotInput(
        cash_available=10000,
        positions=[
            PortfolioPositionInput(symbol="002463", name="HD", quantity=100, avg_cost=80, directions=["PCB"]),
            PortfolioPositionInput(symbol="000657", name="ZW", quantity=0, available_quantity=0, avg_cost=0, directions=["TUNGSTEN"]),
        ],
    ))
    context = {
        "account_facts": state.metrics.model_dump(mode="json"),
        "holdings": [
            {"symbol": "002463", "portfolio_weight_pct": state.metrics.position_weights[0]["weight_pct"]},
            {"symbol": "000657", "portfolio_weight_pct": None},
        ],
        "holding_trend_evidence": [
            {"symbol": "002463", "trend_state": "短期强势排列", "return_20d_pct": 8, "price_vs_ma20_pct": 5},
            {"symbol": "000657", "trend_state": "震荡偏稳", "return_20d_pct": 3, "price_vs_ma20_pct": 1},
        ],
        "primary_direction_grouping": [],
        "risk_observations": {},
        "data_gaps": [],
        "suggested_questions_for_external_llm": ["test task"],
        "ai_analysis_boundary": {},
    }

    dashboard = build_dashboard(state, context)
    watch = next(item for item in dashboard["positions"] if item["symbol"] == "000657")
    watch_strategy = next(item for item in dashboard["strategy_matrix"] if item["symbol"] == "000657")

    assert watch["position_status"] == "watchlist"
    assert watch["portfolio_weight_pct"] == 0
    assert any(item["symbol"] == "000657" and item["position_status"] == "watchlist" for item in dashboard["opportunity_queue"])
    assert "观察池标的" in watch_strategy["short_term"]
    assert dashboard["external_ai_tasks"] == ["test task"]


def test_market_event_radar_surfaces_confirmed_macro_events(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    service = PortfolioService(tmp_path)
    state = service.save_snapshot(PortfolioSnapshotInput(
        cash_available=10000,
        positions=[
            PortfolioPositionInput(
                symbol="002463",
                name="HD",
                quantity=1000,
                avg_cost=80,
                directions=["PCB"],
                risk_flags=["HIGH_VOLATILITY"],
                theme_tags=["PCB", "HIGH_VOLATILITY"],
            ),
            PortfolioPositionInput(
                symbol="159934",
                name="Gold ETF",
                quantity=5000,
                avg_cost=5,
                directions=["GOLD"],
                theme_tags=["GOLD"],
            ),
        ],
    ))
    weights = {item["symbol"]: item["weight_pct"] for item in state.metrics.position_weights}

    radar = build_market_event_radar(state, weights, today=date(2026, 6, 7))
    titles = [event["title"] for event in radar["events"]]
    fomc = next(event for event in radar["events"] if event["event_id"] == "fomc_2026_06_16_17")

    assert "美国 5 月 CPI" in titles
    assert "FOMC 利率决议与经济预测" in titles
    assert radar["high_impact_count"] >= 2
    assert fomc["impact_level"] == "high"
    assert any(item["symbol"] == "002463" for item in fomc["related_positions"])
    assert any("黄金" in item["reason"] for item in fomc["related_positions"])


def test_holding_semantic_suggestions_require_user_confirmation_and_persist(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    service = PortfolioService(tmp_path)
    service.save_snapshot(PortfolioSnapshotInput(
        cash_available=10000,
        positions=[
            PortfolioPositionInput(symbol="002463.SZ", name="HD", quantity=100, avg_cost=80),
        ],
    ))

    suggestion = service.holding_semantic_suggestions()[0]
    before = service.get_state().snapshot.positions[0]
    after = service.update_holding_semantics(HoldingSemanticBatchUpdate(updates=[
        HoldingSemanticUpdate(
            symbol="002463.SZ",
            directions=suggestion.suggested_directions,
            risk_flags=suggestion.suggested_risk_flags,
            position_role="trend",
        )
    ])).snapshot.positions[0]

    assert suggestion.requires_user_confirmation is True
    assert before.directions == []
    assert after.directions == ["PCB"]
    assert after.risk_flags == ["HIGH_VOLATILITY"]
    assert after.primary_theme == "PCB"
    assert after.theme_tags == ["PCB", "HIGH_VOLATILITY"]
    assert after.position_role == "trend"
    assert after.semantic_classification_status == "user_confirmed"
    assert service.load_snapshot().positions[0].directions == ["PCB"]


def test_missing_price_does_not_fabricate_market_value_or_pnl(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _missing_quote)
    service = PortfolioService(tmp_path)
    state = service.save_snapshot(PortfolioSnapshotInput(
        cash_available=50000,
        positions=[
            PortfolioPositionInput(symbol="002463", name="HD", quantity=1000, avg_cost=80, theme_tags=["AI_PCB"], primary_theme="AI_PCB"),
        ],
    ))

    position = state.snapshot.positions[0]
    assert position.market_price is None
    assert position.market_value is None
    assert position.unrealized_pnl is None
    assert position.data_status == "missing_data"
    assert "market_price" in position.missing_data
    assert state.metrics.total_market_value == 0
    assert state.metrics.missing_data[0]["symbol"] == "002463"


def test_position_limit_placeholder_does_not_become_system_hypothesis(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    service = PortfolioService(tmp_path)
    service.save_snapshot(PortfolioSnapshotInput(
        cash_available=10000,
        risk_limits=RiskLimits(max_position_weight=20, max_theme_weight=90, min_cash_ratio=1),
        positions=[
            PortfolioPositionInput(symbol="002463", name="HD", quantity=1000, avg_cost=80, theme_tags=["AI_PCB"], primary_theme="AI_PCB"),
        ],
    ))

    snapshot = service.build_portfolio_snapshot(persist=False)

    assert snapshot.system_hypotheses == []


def test_manual_evidence_enters_portfolio_snapshot(tmp_path):
    service = PortfolioService(tmp_path)
    shareholder = service.add_manual_evidence(ManualEvidenceCreate(
        symbol="000657",
        evidence_type=ManualEvidenceType.SHAREHOLDER_COUNT_MANUAL,
        title="Manual shareholder count",
        holder_num=50000,
        end_date=date(2026, 3, 31),
        source="manual screenshot",
        notes="entered by user",
    ))
    observation = service.add_manual_evidence(ManualEvidenceCreate(
        symbol="002463",
        evidence_type=ManualEvidenceType.MANUAL_MARKET_OBSERVATION,
        title="Intraday observation",
        text="Observed volatility during the session.",
        source="manual note",
        reliability="C_manual_observation",
        llm_usage="context_only",
    ))

    snapshot = service.build_portfolio_snapshot(persist=False)
    matched = [item for item in snapshot.evidence_items if item.evidence_id in {shareholder.evidence_id, observation.evidence_id}]
    assert len(matched) == 2
    assert {item.evidence_type for item in matched} == {"shareholder_count_manual", "manual_market_observation"}
    assert all(item.category == "manual_evidence" for item in matched)


def test_trade_simulation_reports_structure_change(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    service = PortfolioService(tmp_path)
    service.save_snapshot(PortfolioSnapshotInput(
        cash_available=100000,
        positions=[
            PortfolioPositionInput(symbol="002463", name="HD", quantity=1000, avg_cost=80, theme_tags=["AI_PCB"], primary_theme="AI_PCB"),
        ],
    ))

    result = service.simulate_trade(TradeSimulationRequest(
        side=TradeSide.BUY,
        symbol="000657",
        name="ZW",
        amount=70000,
        estimated_price=20,
        theme_tags=["AI_PCB", "METAL_RESOURCE", "TUNGSTEN", "COMPOSITE_EXPOSURE"],
        primary_theme="METAL_RESOURCE",
        reason="planned test",
    ))

    assert result.after.cash_ratio_pct < result.before.cash_ratio_pct
    assert result.after.invested_ratio_pct > result.before.invested_ratio_pct
    assert result.after.primary_theme_exposures
    assert result.risk_notes
    assert service.get_state().snapshot.cash_available == 100000


def test_trade_simulation_accepts_requested_aliases_and_cash_warning(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    service = PortfolioService(tmp_path)
    service.save_snapshot(PortfolioSnapshotInput(cash_available=1000, positions=[]))

    request = TradeSimulationRequest.model_validate({
        "action": "buy",
        "symbol": "000657",
        "amount": 5000,
        "estimated_price": 20,
        "trading_reason": "planned context test",
        "is_planned_trade": True,
        "theme_tags": ["METAL_RESOURCE"],
        "primary_theme": "METAL_RESOURCE",
    })
    result = service.simulate_trade(request)

    assert result.trade["side"] == "buy"
    assert any("cash_available" in note for note in result.risk_notes)
    assert service.get_state().snapshot.cash_available == 1000


def test_sell_simulation_rejects_quantity_above_available(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    service = PortfolioService(tmp_path)
    service.save_snapshot(PortfolioSnapshotInput(
        cash_available=10000,
        positions=[
            PortfolioPositionInput(symbol="002463", name="HD", quantity=1000, available_quantity=300, avg_cost=80),
        ],
    ))

    with pytest.raises(ValueError, match="available_quantity"):
        service.simulate_trade(TradeSimulationRequest(
            side=TradeSide.SELL,
            symbol="002463",
            quantity=500,
            estimated_price=100,
        ))
