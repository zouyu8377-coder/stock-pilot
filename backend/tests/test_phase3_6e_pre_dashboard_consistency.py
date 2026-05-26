from types import SimpleNamespace

from app.analysis_packet import packet_service
from app.analysis_packet.packet_service import build_account_analysis_context, build_portfolio_packet
from app.portfolio.schemas import PortfolioPositionInput, PortfolioSnapshotInput
from app.portfolio.service import PortfolioService


def _fake_quote(symbol: str):
    prices = {
        "002463": 40.0,
        "002916": 30.0,
        "159382": 1.5,
        "601899": 20.0,
        "603993": 10.0,
        "159934": 5.0,
    }
    code = symbol.split(".", 1)[0].zfill(6)
    return {"price": prices[code], "name": code, "provider": "synthetic"}


def _service(tmp_path, monkeypatch) -> PortfolioService:
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    service = PortfolioService(tmp_path)
    monkeypatch.setattr(packet_service, "portfolio_service", service)
    service.save_snapshot(PortfolioSnapshotInput(
        total_assets=999999,
        cash_available=5000,
        repo_amount=1000,
        positions=[
            PortfolioPositionInput(symbol="002463", name="Hudian", quantity=500, avg_cost=35, primary_theme="AI_PCB", theme_tags=["AI_PCB", "HIGH_VOLATILITY"], position_role="observation", semantic_classification_status="user_confirmed"),
            PortfolioPositionInput(symbol="002916", name="Shennan", quantity=500, avg_cost=28, primary_theme="AI_PCB", theme_tags=["AI_PCB", "HIGH_VOLATILITY"], position_role="observation", semantic_classification_status="user_confirmed"),
            PortfolioPositionInput(symbol="159382", name="AI ETF", quantity=10000, avg_cost=1.4, primary_theme="AI_THEME_ETF", theme_tags=["AI_THEME_ETF", "HIGH_VOLATILITY"], position_role="observation", semantic_classification_status="user_confirmed"),
            PortfolioPositionInput(symbol="601899", name="Zijin", quantity=1000, avg_cost=18, primary_theme="METAL_RESOURCE", theme_tags=["METAL_RESOURCE", "GOLD", "COMPOSITE_EXPOSURE"], position_role="observation", semantic_classification_status="user_confirmed"),
            PortfolioPositionInput(symbol="603993", name="CMOC", quantity=1000, avg_cost=9, primary_theme="METAL_RESOURCE", theme_tags=["METAL_RESOURCE"], position_role="observation", semantic_classification_status="user_confirmed"),
            PortfolioPositionInput(symbol="159934", name="Gold ETF", quantity=2000, avg_cost=4.8, primary_theme="GOLD", theme_tags=["GOLD"], position_role="observation", semantic_classification_status="user_confirmed"),
        ],
    ))
    return service


def test_current_quote_estimate_is_separate_and_self_consistent(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    packet = build_portfolio_packet(persist=False)["packet"]
    overview = packet["account_overview"]
    estimate = overview["current_quote_estimate"]

    expected_total = (
        estimate["current_enriched_market_value"]
        + estimate["cash_carried_from_snapshot"]
        + estimate["repo_carried_from_snapshot"]
    )
    assert overview["snapshot_valuation"]["snapshot_total_assets"] == 999999
    assert estimate["estimated_total_assets_using_current_quotes"] == expected_total
    assert overview["total_assets"] == expected_total
    assert abs(
        estimate["estimated_position_weight_pct"]
        + estimate["estimated_cash_weight_pct"]
        + estimate["estimated_repo_weight_pct"]
        - 100
    ) <= 0.02
    themes = {item["theme"]: item for item in packet["official_theme_exposure"]}
    assert themes["AI_PCB"]["weight_pct"] == round(themes["AI_PCB"]["market_value"] / expected_total * 100, 2)
    assert "not broker-verified realtime total assets" in estimate["boundary"]


def test_related_tag_exposure_is_strictly_confirmed_tags(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    packet = build_portfolio_packet(persist=False)["packet"]
    official = {item["theme"]: set(item["symbols"]) for item in packet["official_theme_exposure"]}
    related = {item["theme"]: set(item["symbols"]) for item in packet["related_theme_observations"]["theme_tag_exposure"]}

    assert official["AI_PCB"] == {"002463", "002916"}
    assert official["AI_THEME_ETF"] == {"159382"}
    assert related["AI_PCB"] == {"002463", "002916"}
    assert "159382" not in related["AI_PCB"]
    assert related["AI_THEME_ETF"] == {"159382"}
    assert related["HIGH_VOLATILITY"] == {"002463", "002916", "159382"}
    assert related["METAL_RESOURCE"] == {"601899", "603993"}
    assert related["GOLD"] == {"601899", "159934"}
    assert "AI_RELATED" not in related


def test_user_confirmed_observation_is_not_missing_data(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    packet = build_portfolio_packet(persist=False)["packet"]
    context = build_account_analysis_context()

    role_gaps = [item for item in packet["data_gaps"] if isinstance(item, dict) and item.get("key") == "holding_position_role"]
    assert role_gaps == []
    assert {item["confirmed_position_role"] for item in context["holdings"]} == {"observation"}

    service = packet_service.portfolio_service
    saved = service.load_snapshot()
    saved.positions[0].semantic_classification_status = "unconfirmed"
    service.save_snapshot(PortfolioSnapshotInput(**saved.model_dump()))
    packet = build_portfolio_packet(persist=False)["packet"]
    role_gaps = [item for item in packet["data_gaps"] if isinstance(item, dict) and item.get("key") == "holding_position_role"]
    assert role_gaps and role_gaps[0]["symbol"] == "002463"


def test_ai_boundary_questions_are_descriptive_and_rules_inactive(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    packet = build_portfolio_packet(persist=False)["packet"]
    context = build_account_analysis_context()
    questions = "\n".join(packet["suggested_questions_for_external_llm"])

    assert "overly concentrated" not in questions
    assert "preserve enough optionality" not in questions
    assert "proposed trade is executed" not in questions
    assert "do not output buy, sell, or position-adjustment instructions" in questions
    assert context["ai_analysis_boundary"]["external_llm_called"] is False
    assert context["ai_analysis_boundary"]["inactive_decision_rules"] == [
        "single_position_limit",
        "primary_theme_limit",
        "cash_floor",
        "repo_cash_equivalent_policy",
    ]


def test_account_context_external_driver_summary_is_compact(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)

    def fake_external_context(symbol: str, primary_theme=None):
        return SimpleNamespace(
            mapping_status="configured",
            profile_id="TEST",
            symbol=symbol,
            message="test",
            future_extension="test",
            drivers=[],
            boundary="External-driver mapping boundary.",
            evidence=[
                {
                    "category": "auto_fact",
                    "evidence_type": "external_driver_fact",
                    "data_status": "unavailable",
                    "payload": {
                        "factor_id": "ai_theme_etf_159382",
                        "display_name": "AI theme ETF share, NAV, and price",
                        "factor_type": "theme_etf",
                        "data_status": "unavailable",
                        "reason": "Tushare token is not configured.",
                    },
                }
            ] if symbol in {"002463", "002916", "159382"} else [],
            missing_data=[],
        )

    monkeypatch.setattr(packet_service, "build_external_driver_context", fake_external_context)
    context = build_account_analysis_context()
    summary = context["external_driver_summary"]

    assert set(summary.keys()) == {"shared_external_driver_observations", "boundary"}
    observation = summary["shared_external_driver_observations"][0]
    assert observation["factor_id"] == "ai_theme_etf_159382"
    assert set(observation["associated_symbols"]) == {"002463", "002916", "159382"}
    assert "evidence" not in observation
    assert "mapping" not in observation
