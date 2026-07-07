from __future__ import annotations

from app.attractiveness import service
from app.portfolio.schemas import PortfolioPositionInput, PortfolioSnapshotInput
from app.portfolio.service import PortfolioService


def _quote(symbol: str):
    return {"symbol": symbol, "name": symbol, "price": 100, "provider": "test"}


def test_attractiveness_scores_available_dimensions_without_neutral_valuation(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _quote)
    monkeypatch.setattr(
        service,
        "get_valuation_reference",
        lambda symbol: {"status": "unavailable", "reason": "test"},
    )
    monkeypatch.setattr(service, "HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(service, "CONSENSUS_PATH", tmp_path / "consensus.json")
    portfolio_service = PortfolioService(tmp_path / "portfolio")
    state = portfolio_service.save_snapshot(PortfolioSnapshotInput(
        cash_available=10000,
        positions=[PortfolioPositionInput(
            symbol="002463",
            name="沪电股份",
            quantity=100,
            avg_cost=80,
            directions=["PCB"],
        )],
    ))
    radar = service.build_attractiveness_radar(
        state,
        trends={
            "002463": {
                "data_status": "available",
                "price_vs_ma20_pct": 6,
                "return_20d_pct": 8,
                "return_60d_pct": 12,
                "rsi14": 61,
                "trend_state": "短期强势排列",
                "latest_pct_chg": 2,
            }
        },
        theme_radar={
            "themes": [{
                "theme_id": "ai_server_pcb",
                "theme_name": "AI服务器 / PCB",
                "confirming_events": ["订单改善"],
                "invalidating_events": [],
                "related_positions": [{
                    "symbol": "002463",
                    "relation_strength": "high",
                    "announcement_verification": {
                        "status": "verified",
                        "counts": {
                            "supported": 2,
                            "partially_supported": 1,
                            "contradicted": 0,
                            "not_found": 0,
                        },
                    },
                }],
            }],
        },
        event_radar={"events": []},
        persist_history=True,
    )

    row = radar["positions"][0]
    valuation = next(item for item in row["dimensions"] if item["key"] == "valuation_consensus")
    assert row["score"] >= 65
    assert row["coverage"] < 100
    assert valuation["score"] is None
    assert valuation["coverage"] == 0
    assert row["execution_constraints"]["t_plus_one_modeled"] is False
    assert row["execution_constraints"]["all_existing_holdings_available"] is True
    assert "account_constraints" in row
    assert 0 <= row["account_readiness_score"] <= 100


def test_local_price_position_fills_valuation_dimension(monkeypatch):
    monkeypatch.setattr(
        service,
        "get_valuation_reference",
        lambda symbol: {
            "status": "available",
            "asset_type": "stock",
            "price_percentile_3y": 25,
            "source": "local_baostock_daily",
        },
    )

    dimension = service._valuation_dimension("002463", 40, {"symbols": {}})

    assert dimension["score"] == 75
    assert dimension["coverage"] == 60
    assert "自身3年价格分位" in dimension["reasons"][0]


def test_etf_share_fact_fills_evidence_without_theme_mapping():
    dimension = service._etf_evidence_dimension(
        {},
        {"share_change_1d_pct": 1.2, "as_of": "2026-06-15"},
    )

    assert dimension["score"] is not None
    assert dimension["coverage"] == 35
    assert "主题尚未映射" in dimension["reasons"][0]


def test_attractiveness_uses_multi_institution_target_price_reference(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _quote)
    monkeypatch.setattr(service, "HISTORY_PATH", tmp_path / "history.json")
    consensus_path = tmp_path / "consensus.json"
    consensus_path.write_text(
        '{"version":"test","symbols":{"002463":{"target_price_median":125,"institution_count":5,"published_at":"2026-06-01"}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(service, "CONSENSUS_PATH", consensus_path)
    portfolio_service = PortfolioService(tmp_path / "portfolio")
    state = portfolio_service.save_snapshot(PortfolioSnapshotInput(
        cash_available=10000,
        positions=[PortfolioPositionInput(symbol="002463", name="沪电股份", quantity=0, avg_cost=0, directions=["PCB"])],
    ))

    radar = service.build_attractiveness_radar(
        state,
        trends={"002463": {"data_status": "unavailable"}},
        theme_radar={"themes": []},
        event_radar={"events": []},
        persist_history=True,
    )

    valuation = next(item for item in radar["positions"][0]["dimensions"] if item["key"] == "valuation_consensus")
    assert valuation["score"] > 50
    assert valuation["coverage"] > 0
    assert valuation["reference"]["implied_upside_pct"] == 25.0


def test_evidence_change_compares_previous_snapshot():
    current = service._evidence_dimension(
        {
            "announcement_verification": {
                "status": "verified",
                "counts": {"supported": 2, "partially_supported": 1, "contradicted": 0, "not_found": 0},
            }
        },
        {"supported": 1, "partially_supported": 0, "contradicted": 0, "not_found": 0},
    )

    assert current["evidence_delta"] == 3
    assert any("较上次证据净变化 +3" in reason for reason in current["reasons"])


def test_stale_market_benchmark_disables_trend_score():
    dimension = service._trend_dimension(
        {
            "data_status": "available",
            "return_20d_pct": 12,
            "return_60d_pct": 20,
        },
        {
            "market": {
                "status": "available",
                "as_of": "2026-05-13",
                "freshness": {"status": "stale", "stale_days": 30},
            }
        },
    )

    assert dimension["score"] is None
    assert dimension["coverage"] == 0
    assert "行情基准已过期 30 天" in dimension["reasons"][0]


def test_account_constraints_block_concentrated_theme(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _quote)
    portfolio_service = PortfolioService(tmp_path / "portfolio")
    state = portfolio_service.save_snapshot(PortfolioSnapshotInput(
        cash_available=1000,
        positions=[
            PortfolioPositionInput(symbol="002463", name="沪电股份", quantity=400, avg_cost=80, directions=["PCB"]),
            PortfolioPositionInput(symbol="002916", name="深南电路", quantity=400, avg_cost=80, directions=["PCB"]),
        ],
    ))
    constraints = service._account_constraints(
        state,
        state.snapshot.positions[0],
        80,
        {"limit_up": False, "limit_down": False},
    )

    assert constraints["theme_headroom_pct"] == 0
    assert constraints["eligible_after_account_constraints"] is False
    assert "主题仓位余量不足" in constraints["blockers"]


def test_catalyst_without_near_term_event_is_observed_not_missing():
    dimension = service._catalyst_dimension(
        {
            "theme_id": "ai_server_pcb",
            "theme_name": "AI服务器 / PCB",
            "confirming_events": [],
        },
        [],
    )

    assert dimension["data_status"] == "available_no_near_term_catalyst"
    assert dimension["coverage"] == 60
    assert "已检查主题事件清单" in dimension["reasons"][0]


def test_opportunity_cost_includes_leader_name(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _quote)
    monkeypatch.setattr(
        service,
        "get_valuation_reference",
        lambda symbol: {"status": "unavailable", "reason": "test"},
    )
    monkeypatch.setattr(service, "HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(service, "CONSENSUS_PATH", tmp_path / "consensus.json")
    portfolio_service = PortfolioService(tmp_path / "portfolio")
    state = portfolio_service.save_snapshot(PortfolioSnapshotInput(
        cash_available=10000,
        positions=[
            PortfolioPositionInput(symbol="002463", name="沪电股份", quantity=100, avg_cost=80, directions=["PCB"]),
            PortfolioPositionInput(symbol="002916", name="深南电路", quantity=100, avg_cost=80, directions=["PCB"]),
        ],
    ))
    radar = service.build_attractiveness_radar(
        state,
        trends={
            "002463": {"data_status": "available", "return_20d_pct": 12, "return_60d_pct": 18, "latest_pct_chg": 1},
            "002916": {"data_status": "available", "return_20d_pct": -3, "return_60d_pct": 2, "latest_pct_chg": 0},
        },
        theme_radar={
            "themes": [{
                "theme_id": "ai_server_pcb",
                "theme_name": "AI服务器 / PCB",
                "confirming_events": ["订单改善"],
                "invalidating_events": [],
                "related_positions": [
                    {"symbol": "002463", "relation_strength": "high"},
                    {"symbol": "002916", "relation_strength": "medium"},
                ],
            }],
        },
        event_radar={"events": []},
        persist_history=False,
    )

    follower = next(row for row in radar["positions"] if row["theme_rank"] == 2)
    leader = next(row for row in radar["positions"] if row["theme_rank"] == 1)
    assert follower["opportunity_cost"]["dominated_by_symbol"] == leader["symbol"]
    assert follower["opportunity_cost"]["dominated_by_name"] == leader["name"]
