from types import SimpleNamespace

import pandas as pd

from app.analysis_packet import packet_service
from app.analysis_packet.packet_service import (
    build_account_analysis_context,
    build_portfolio_packet,
    render_compact_markdown,
)
from app.portfolio.schemas import PortfolioPositionInput, PortfolioSnapshotInput
from app.portfolio.service import PortfolioService
from app.theme_evidence import build_theme_evidence_radar, load_theme_evidence_registry


PRICES = {
    "002463": 100,
    "002916": 120,
    "002384": 60,
    "159382": 2,
    "513310": 1.5,
    "159516": 1.2,
    "601899": 25,
    "603993": 12,
    "000657": 50,
    "600549": 40,
    "159934": 7,
}


def _quote(symbol: str):
    code = symbol.split(".", 1)[0].zfill(6)
    return {"symbol": code, "name": code, "price": PRICES[code], "provider": "test"}


def _history(symbol: str, limit: int = 5000):
    base = PRICES[symbol.split(".", 1)[0].zfill(6)]
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=80, freq="B"),
            "open": [base + i * 0.01 for i in range(80)],
            "high": [base + i * 0.01 + 0.1 for i in range(80)],
            "low": [base + i * 0.01 - 0.1 for i in range(80)],
            "close": [base + i * 0.01 for i in range(80)],
            "volume": [100000 + i for i in range(80)],
            "amount": [1000000 + i for i in range(80)],
            "pctChg": [0.1] * 80,
        }
    ).tail(limit)


def _state(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _quote)
    service = PortfolioService(tmp_path)
    state = service.save_snapshot(
        PortfolioSnapshotInput(
            cash_available=100000,
            positions=[
                PortfolioPositionInput(symbol="002463", name="沪电股份", quantity=2000, avg_cost=80, directions=["PCB"], risk_flags=["HIGH_VOLATILITY"]),
                PortfolioPositionInput(symbol="002916", name="深南电路", quantity=800, avg_cost=100, directions=["PCB"]),
                PortfolioPositionInput(symbol="002384", name="东山精密", quantity=500, avg_cost=55, directions=["PCB"]),
                PortfolioPositionInput(symbol="159382", name="创业板人工智能 ETF", quantity=20000, avg_cost=1.8, directions=["AI"]),
                PortfolioPositionInput(symbol="513310", name="中韩半导体 ETF", quantity=10000, avg_cost=1.4, directions=["SEMICONDUCTOR_EQUIPMENT"]),
                PortfolioPositionInput(symbol="601899", name="紫金矿业", quantity=3000, avg_cost=22, directions=["COPPER", "GOLD"]),
                PortfolioPositionInput(symbol="603993", name="洛阳钼业", quantity=3000, avg_cost=10, directions=["COPPER"]),
                PortfolioPositionInput(symbol="000657", name="中钨高新", quantity=0, avg_cost=0, directions=["TUNGSTEN"]),
                PortfolioPositionInput(symbol="600549", name="厦门钨业", quantity=0, avg_cost=0, directions=["TUNGSTEN"]),
                PortfolioPositionInput(symbol="159934", name="黄金 ETF", quantity=5000, avg_cost=6.5, directions=["GOLD"]),
            ],
        )
    )
    return service, state


def _event_radar():
    return {
        "events": [
            {
                "matched_impact_channels": [
                    {"channel": "memory_cycle"},
                    {"channel": "foundry_cycle"},
                    {"channel": "usd_real_yield"},
                ]
            }
        ]
    }


def test_registry_loads_three_seed_themes():
    registry = load_theme_evidence_registry()

    assert registry["version"] == "theme_evidence.v1"
    assert {theme["theme_id"] for theme in registry["themes"]} == {
        "ai_server_pcb",
        "semiconductor_hbm_memory",
        "industrial_metals",
    }


def test_theme_radar_maps_core_beta_and_weak_relations(tmp_path, monkeypatch):
    _, state = _state(tmp_path, monkeypatch)

    radar = build_theme_evidence_radar(
        state,
        load_theme_evidence_registry(),
        market_event_radar=_event_radar(),
    )
    themes = {theme["theme_id"]: theme for theme in radar["themes"]}
    pcb = {item["symbol"]: item for item in themes["ai_server_pcb"]["related_positions"]}
    semiconductor = {item["symbol"]: item for item in themes["semiconductor_hbm_memory"]["related_positions"]}
    metals = {item["symbol"]: item for item in themes["industrial_metals"]["related_positions"]}

    assert pcb["002463"]["relation_strength"] == "high"
    assert pcb["002916"]["relation_strength"] == "high"
    assert pcb["002384"]["relation_strength"] == "medium"
    assert pcb["159382"]["thesis_status"] == "beta_exposure"
    assert pcb["000657"]["relation_label"] == "弱关联 / 待核验"
    assert semiconductor["513310"]["relation_strength"] == "high"
    assert semiconductor["600549"]["relation_label"] == "弱关联 / 待核验"
    assert metals["601899"]["relation_strength"] == "high"
    assert metals["603993"]["role_in_theme"] == "铜 / 钼资源核心观察"
    assert metals["000657"]["position_status"] == "watchlist"
    assert all(theme["evidence_maturity"] == "watching" for theme in themes.values())
    assert all(theme["confirming_events"] for theme in themes.values())
    assert all(theme["invalidating_events"] for theme in themes.values())
    assert "不构成买卖" in radar["boundary"]


def test_portfolio_packet_and_compact_markdown_include_four_theme_tables(tmp_path, monkeypatch):
    service, _ = _state(tmp_path, monkeypatch)
    monkeypatch.setattr(packet_service, "portfolio_service", service)
    monkeypatch.setattr(packet_service.collector, "get_history", _history)
    monkeypatch.setattr(packet_service, "build_market_event_radar", lambda *_args, **_kwargs: _event_radar())
    monkeypatch.setattr(packet_service, "_portfolio_auto_fact_summary", lambda _symbols: [])
    monkeypatch.setattr(packet_service, "_portfolio_etf_share_observations", lambda _positions: {"observations": [], "unavailable": []})
    monkeypatch.setattr(packet_service, "_portfolio_external_driver_summary", lambda _positions: [])

    packet_result = build_portfolio_packet(persist=False)
    context = build_account_analysis_context(mode="compact")
    markdown = render_compact_markdown(context)

    assert packet_result["packet"]["theme_evidence_radar"]["registry_version"] == "theme_evidence.v1"
    assert "## 主题证据雷达" in packet_result["markdown"]
    assert "### 账户相关主题表" in markdown
    assert "### 产业链层级表" in markdown
    assert "### 持仓 Thesis 健康表" in markdown
    assert "### 催化 / 反证事件表" in markdown
    assert "中钨高新" in markdown
    assert "弱关联 / 待核验" in markdown
    assert len(context["theme_evidence_radar"]["themes"]) <= 3
    assert all(len(theme["related_positions"]) <= 5 for theme in context["theme_evidence_radar"]["themes"])
