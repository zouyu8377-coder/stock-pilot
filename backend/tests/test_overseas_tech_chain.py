from __future__ import annotations

from app.analysis_packet import packet_service
from app.overseas_tech_chain.service import build_overseas_tech_chain
from app.portfolio.schemas import PortfolioPositionInput, PortfolioSnapshotInput
from app.portfolio.service import PortfolioService


def _fake_quote(symbol: str):
    prices = {
        "002463": {"price": 100.0, "name": "HD"},
        "159819": {"price": 1.2, "name": "AI ETF"},
    }
    return {**prices.get(symbol, {"price": 10.0, "name": symbol}), "provider": "test"}


def _chart_payload(symbol: str) -> dict:
    base = 100.0
    if symbol == "^SOX":
        closes = [100 + i for i in range(25)]
    elif symbol in {"^NDX", "MU", "000660.KS"}:
        closes = [100 + i for i in range(22)] + [120, 112, 108]
    else:
        closes = [base + i * 0.5 for i in range(25)]
    timestamps = [1_700_000_000 + i * 86_400 for i in range(len(closes))]
    return {
        "chart": {
            "result": [{
                "timestamp": timestamps,
                "indicators": {"quote": [{"close": closes}]},
                "meta": {
                    "regularMarketPrice": closes[-1],
                    "regularMarketTime": timestamps[-1],
                    "currency": "USD",
                },
            }],
            "error": None,
        }
    }


def _state(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    service = PortfolioService(tmp_path)
    return service.save_snapshot(PortfolioSnapshotInput(
        cash_available=10000,
        positions=[
            PortfolioPositionInput(
                symbol="002463",
                name="沪电股份",
                quantity=1000,
                avg_cost=80,
                directions=["PCB"],
                theme_tags=["AI", "PCB"],
            ),
            PortfolioPositionInput(
                symbol="159819",
                name="AI ETF",
                quantity=10000,
                avg_cost=1,
                directions=["AI_THEME_ETF"],
                theme_tags=["AI_THEME_ETF"],
            ),
        ],
    ))


def test_overseas_tech_chain_maps_holdings_and_risk_level(tmp_path, monkeypatch):
    state = _state(tmp_path, monkeypatch)
    chain = build_overseas_tech_chain(state, fetcher=_chart_payload, max_workers=2)

    assert chain["available_indicator_count"] == chain["indicator_count"]
    assert chain["risk_level"]["level"] == "High"
    assert chain["account_sensitivity_summary"]["tech_growth_exposure_pct"] > 70
    sox = next(item for item in chain["indicators"] if item["symbol"] == "^SOX")
    assert sox["data_status"] == "available"
    assert {item["symbol"] for item in sox["related_holdings"]} == {"002463", "159819"}
    assert "A 股开盘" in chain["open_sentiment_observation"]


def test_packet_context_and_markdown_include_overseas_chain(tmp_path, monkeypatch):
    state = _state(tmp_path, monkeypatch)
    monkeypatch.setattr(packet_service, "build_overseas_tech_chain", lambda *_args, **_kwargs: {
        "generated_at": "2026-07-13T00:00:00+00:00",
        "provider": "test",
        "data_status": "available",
        "indicator_count": 1,
        "available_indicator_count": 1,
        "risk_level": {"level": "Low", "judgment": "test"},
        "account_sensitivity_summary": {"tech_growth_exposure_pct": 80.0, "summary": "test"},
        "open_sentiment_observation": "A 股开盘观察前 30-60 分钟。",
        "sentiment_path": [],
        "leading_signals": [],
        "indicators": [{
            "name": "PHLX Semiconductor Index",
            "symbol": "^SOX",
            "market": "US",
            "category": "Semiconductor chain",
            "latest_price": 100,
            "change_1d_pct": 1,
            "change_5d_pct": 2,
            "change_20d_pct": 3,
            "relative_ma20_pct": 4,
            "trend_state": "MA20上方 / 短期偏强",
            "data_status": "available",
            "related_holdings": [{"symbol": "002463", "name": "沪电股份"}],
            "risk_note": "test note",
        }],
        "boundary": "test boundary",
    })

    result = packet_service.build_portfolio_packet(persist=False, state=state)
    assert result["packet"]["overseas_tech_chain"]["risk_level"]["level"] == "Low"

    context = packet_service.build_account_analysis_context(mode="compact", state=state)
    assert context["overseas_tech_chain"]["available_indicator_count"] == 1
    markdown = packet_service.render_compact_markdown(context)
    assert "海外科技链映射表" in markdown
    assert "PHLX Semiconductor Index" in markdown
