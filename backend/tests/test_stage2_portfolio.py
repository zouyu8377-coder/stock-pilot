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
    assert primary["AI_PCB"] == 45.45
    assert primary["METAL_RESOURCE"] == 18.18
    assert sum(primary.values()) <= 100
    assert any("000657" in note for note in state.metrics.composite_exposure_notes)


def test_unconfirmed_theme_tags_do_not_become_official_exposure(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    service = PortfolioService(tmp_path)
    state = service.save_snapshot(PortfolioSnapshotInput(
        cash_available=10000,
        positions=[
            PortfolioPositionInput(symbol="002463", name="HD", quantity=100, avg_cost=80, theme_tags=["AI_PCB"]),
        ],
    ))

    primary = {item.theme: item.weight_pct for item in state.metrics.primary_theme_exposures}

    assert "AI_PCB" not in primary
    assert "UNCLASSIFIED" in primary
    assert any("without confirmed primary_theme" in warning for warning in state.metrics.warnings)


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
            primary_theme=suggestion.suggested_primary_theme,
            theme_tags=suggestion.suggested_theme_tags,
            position_role="trend",
        )
    ])).snapshot.positions[0]

    assert suggestion.requires_user_confirmation is True
    assert before.primary_theme is None
    assert after.primary_theme == "AI_PCB"
    assert after.theme_tags == ["AI_PCB", "HIGH_VOLATILITY"]
    assert after.position_role == "trend"
    assert after.semantic_classification_status == "user_confirmed"
    assert service.load_snapshot().positions[0].primary_theme == "AI_PCB"


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
