from pathlib import Path

from app.analysis_packet import packet_service
from app.analysis_packet.packet_service import build_account_analysis_context, build_portfolio_packet
from app.portfolio.schemas import PortfolioPositionInput, PortfolioSnapshotInput
from app.portfolio.service import PortfolioService


def _synthetic_closure_service(tmp_path, monkeypatch) -> PortfolioService:
    prices = {
        "601899": 20.0,
        "603993": 10.0,
        "002463": 40.0,
        "002916": 30.0,
        "159382": 1.5,
        "159934": 5.0,
    }

    def fake_quote(symbol: str):
        code = symbol.split(".", 1)[0].zfill(6)
        return {"price": prices[code], "name": code, "provider": "synthetic"}

    monkeypatch.setattr("app.portfolio.service.collector.get_quote", fake_quote)
    service = PortfolioService(tmp_path)
    monkeypatch.setattr(packet_service, "portfolio_service", service)
    service.save_snapshot(PortfolioSnapshotInput(
        total_assets=88000,
        cash_available=5000,
        repo_amount=0,
        positions=[
            PortfolioPositionInput(symbol="601899", name="Zijin", quantity=1000, avg_cost=18, primary_theme="METAL_RESOURCE", theme_tags=["METAL_RESOURCE", "GOLD", "COMPOSITE_EXPOSURE"], position_role="core"),
            PortfolioPositionInput(symbol="603993", name="CMOC", quantity=1000, avg_cost=9, primary_theme="METAL_RESOURCE", theme_tags=["METAL_RESOURCE"], position_role="core"),
            PortfolioPositionInput(symbol="002463", name="Hudian", quantity=500, avg_cost=35, primary_theme="AI_PCB", theme_tags=["AI_PCB"], position_role="trend"),
            PortfolioPositionInput(symbol="002916", name="Shennan", quantity=500, avg_cost=28, primary_theme="AI_PCB", theme_tags=["AI_PCB"], position_role="trend"),
            PortfolioPositionInput(symbol="159382", name="AI ETF", quantity=10000, avg_cost=1.4, primary_theme="AI_THEME_ETF", theme_tags=["AI_THEME_ETF"], position_role="observation"),
            PortfolioPositionInput(symbol="159934", name="Gold ETF", quantity=2000, avg_cost=4.8, primary_theme="GOLD", theme_tags=["GOLD"], position_role="defensive"),
        ],
    ))
    return service


def test_closure_frontend_exposes_manual_flow_without_cloud_vision_entry():
    root = Path(__file__).resolve().parents[2]
    portfolio_panel = (root / "frontend" / "src" / "components" / "PortfolioPanel.vue").read_text(encoding="utf-8")
    single_panel = (root / "frontend" / "src" / "components" / "AnalysisPacketPanel.vue").read_text(encoding="utf-8")

    assert "Generate Portfolio Packet" in portfolio_panel
    assert "Generate Stock Packet" in single_panel
    assert "uploadPortfolioScreenshot" not in portfolio_panel
    assert "volcengine_ark_vision" not in portfolio_panel
    assert "Generate Portfolio Packet" not in single_panel


def test_closure_synthetic_primary_theme_exposure_is_unique(tmp_path, monkeypatch):
    _synthetic_closure_service(tmp_path, monkeypatch)
    packet = build_portfolio_packet(persist=False)["packet"]
    exposure = {item["theme"]: set(item["symbols"]) for item in packet["official_theme_exposure"]}

    assert exposure["METAL_RESOURCE"] == {"601899", "603993"}
    assert exposure["AI_PCB"] == {"002463", "002916"}
    assert exposure["AI_THEME_ETF"] == {"159382"}
    assert exposure["GOLD"] == {"159934"}
    assert "601899" not in exposure["GOLD"]
    assert packet["related_theme_observations"]["theme_tag_exposure"]


def test_closure_account_analysis_context_is_local_and_rule_limited(tmp_path, monkeypatch):
    _synthetic_closure_service(tmp_path, monkeypatch)
    context = build_account_analysis_context(mode="audit")

    assert context["ai_analysis_boundary"]["external_llm_called"] is False
    assert set(context["ai_analysis_boundary"]["inactive_rules_for_ai_reasoning"]) == {
        "single_position_limit",
        "primary_theme_limit",
        "cash_floor",
        "repo_cash_equivalent_policy",
    }
    assert context["official_theme_exposure"]
    assert all(item["confirmed_primary_theme"] for item in context["holdings"])
