from app.portfolio.dashboard import _build_account_performance
from app.portfolio.schemas import PortfolioPositionInput, PortfolioSnapshotInput
from app.portfolio.service import PortfolioService


def test_account_performance_keeps_total_and_holding_pnl_separate(tmp_path, monkeypatch):
    prices = {"002463": 12.0, "601899": 9.0}

    def quote(symbol: str):
        code = symbol.split(".", 1)[0].zfill(6)
        return {"price": prices[code], "name": code}

    monkeypatch.setattr("app.portfolio.service.collector.get_quote", quote)
    service = PortfolioService(tmp_path)
    service.save_snapshot(PortfolioSnapshotInput(
        total_assets=300,
        cash_available=100,
        account_actual_total_cost=300,
        positions=[
            PortfolioPositionInput(
                symbol="002463",
                name="Hudian",
                quantity=10,
                avg_cost=10,
                primary_theme="PCB",
                directions=["PCB"],
            ),
            PortfolioPositionInput(
                symbol="601899",
                name="Zijin",
                quantity=10,
                avg_cost=10,
                primary_theme="COPPER",
                directions=["COPPER"],
            ),
        ],
    ))

    performance = _build_account_performance(service.get_state())

    assert performance["account_return"]["pnl"] == 10.0
    assert performance["holding_return"]["pnl"] == 10.0
    assert performance["attribution"]["coverage_pct"] == 100.0
    assert performance["attribution"]["top_contributors"][0]["symbol"] == "002463"
    assert performance["attribution"]["direction_contributors"][0]["direction"] == "PCB"
    assert performance["benchmark"]["status"] == "not_ready"
