from datetime import date, datetime

import pytest

from app.analysis_packet import packet_service
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
from app.portfolio.schemas import ManualEvidenceCreate, PortfolioSnapshotInput, PortfolioPositionInput
from app.portfolio.service import PortfolioService


def _fake_quote(symbol: str):
    prices = {"600000": 10.0, "159382": 1.2}
    return {"symbol": symbol, "name": f"Name{symbol}", "price": prices.get(symbol, 10.0), "provider": "test"}


def _fake_stock_snapshot(symbol: str, user_question=None, persist=True):
    fetched_at = datetime(2026, 5, 24, 10, 0, 0)
    return AnalysisSnapshot(
        snapshot_id=f"snap_{symbol}",
        created_at=fetched_at,
        analysis_scope=AnalysisScope.SINGLE_STOCK,
        target_symbols=[symbol],
        user_question=user_question,
        market_data_as_of=fetched_at,
        daily_k_as_of=date(2026, 5, 22),
        evidence_items=[
            EvidenceItem(
                symbol=symbol,
                evidence_type=EvidenceType.REALTIME_QUOTE,
                category=EvidenceCategory.AUTO_FACT,
                title="Realtime quote snapshot",
                payload={"symbol": symbol, "name": f"Name{symbol}", "price": 10.0, "provider": "test"},
                source="test quote",
                source_endpoint="collector.get_quote",
                as_of_time=fetched_at,
                fetched_at=fetched_at,
                reliability=EvidenceReliability.B,
                llm_usage=LlmUsage.FACT_WITH_LIMIT,
                interpretation_limit="Quote is delayed and bounded.",
            ),
            EvidenceItem(
                symbol=symbol,
                evidence_type=EvidenceType.TECHNICAL_INDICATOR,
                category=EvidenceCategory.AUTO_SIGNAL,
                title="Technical indicators",
                payload={"ma20": 9.5, "rsi14": 55, "macd": 0.1},
                source="test indicators",
                as_of_date=date(2026, 5, 22),
                fetched_at=fetched_at,
                reliability=EvidenceReliability.C,
                llm_usage=LlmUsage.WEAK_SIGNAL_ONLY,
                interpretation_limit="Auxiliary signal only.",
            ),
        ],
        missing_data=[{"key": "announcement_full_text", "reason": "index only"}],
        system_hypotheses=[
            EvidenceItem(
                symbol=symbol,
                evidence_type=EvidenceType.SYSTEM_MARKET_REGIME,
                category=EvidenceCategory.SYSTEM_HYPOTHESIS,
                title="Rule hypothesis",
                payload={"trend": "watch"},
                source="rules",
                fetched_at=fetched_at,
                reliability=EvidenceReliability.H,
                llm_usage=LlmUsage.HYPOTHESIS_ONLY,
                interpretation_limit="Question and verify.",
            )
        ],
    )


def test_single_stock_packet_without_holding_has_manual_account_boundary(tmp_path, monkeypatch):
    service = PortfolioService(root=tmp_path / "portfolio")
    service.save_snapshot(PortfolioSnapshotInput(cash_available=1000, positions=[]))
    monkeypatch.setattr(packet_service, "portfolio_service", service)
    monkeypatch.setattr(packet_service, "build_basic_stock_snapshot", _fake_stock_snapshot)
    monkeypatch.setattr(packet_service.settings, "ANALYSIS_SNAPSHOT_DIR", str(tmp_path / "snapshots"))

    result = packet_service.build_single_stock_packet("600000", persist=True)

    required = {
        "meta",
        "basic_information",
        "auto_fact",
        "auto_signal",
        "manual_account",
        "manual_evidence",
        "system_hypothesis",
        "missing_data",
        "interpretation_boundaries",
        "privacy_notice",
        "suggested_questions_for_external_llm",
    }
    assert required.issubset(result["packet"].keys())
    assert result["packet"]["manual_account"]["has_holding"] is False
    assert result["packet"]["auto_signal"][0]["llm_usage"] == "weak_signal_only"
    assert "No local holding" in result["packet"]["manual_account"]["message"]
    assert (tmp_path / "snapshots").glob("analysis_packets/single_stock/600000/*.json")
    assert "No buy/sell recommendation" in result["markdown"]
    assert "personal account information" in result["markdown"]


def test_single_stock_packet_includes_holding_and_only_selected_manual_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    service = PortfolioService(root=tmp_path / "portfolio")
    service.save_snapshot(PortfolioSnapshotInput(
        cash_available=1000,
        positions=[
            PortfolioPositionInput(
                symbol="600000",
                name="Name600000",
                quantity=100,
                available_quantity=80,
                avg_cost=8,
                position_role="core",
                primary_theme="BANK",
                theme_tags=["BANK"],
                user_plan="hold while thesis valid",
                invalid_condition="breaks risk limit",
                target_max_weight=30,
            )
        ],
    ))
    included = service.add_manual_evidence(ManualEvidenceCreate(
        symbol="600000",
        evidence_type="manual_market_observation",
        title="Included observation",
        text="manual note",
        include_in_analysis_packet=True,
    ))
    service.add_manual_evidence(ManualEvidenceCreate(
        symbol="600000",
        evidence_type="manual_market_observation",
        title="Excluded observation",
        text="hidden note",
        include_in_analysis_packet=False,
    ))
    monkeypatch.setattr(packet_service, "portfolio_service", service)
    monkeypatch.setattr(packet_service, "build_basic_stock_snapshot", _fake_stock_snapshot)

    result = packet_service.build_single_stock_packet("600000", persist=False)

    account = result["packet"]["manual_account"]
    assert account["has_holding"] is True
    assert account["quantity"] == 100
    assert account["portfolio_weight_pct"] is not None
    assert [item["evidence_id"] for item in result["packet"]["manual_evidence"]] == [included.evidence_id]
    assert all(item["category"] == "manual_evidence" for item in result["packet"]["manual_evidence"])
    assert all(item["category"] != "auto_fact" for item in result["packet"]["manual_evidence"])
    assert "Excluded observation" not in result["markdown"]


def test_portfolio_packet_keeps_primary_theme_unique_and_risk_tags_non_additive(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    monkeypatch.setattr(packet_service, "get_dragon_tiger_facts", lambda symbol: {"data_status": "unavailable", "evidence": []})
    monkeypatch.setattr(packet_service, "get_disclosure_facts", lambda symbol: {"data_status": "unavailable", "evidence": []})
    monkeypatch.setattr(packet_service, "get_etf_facts", lambda symbol: {"data_status": "unavailable", "evidence": []})
    service = PortfolioService(root=tmp_path / "portfolio")
    service.save_snapshot(PortfolioSnapshotInput(
        cash_available=500,
        repo_amount=200,
        positions=[
            PortfolioPositionInput(
                symbol="600000",
                name="Name600000",
                quantity=100,
                avg_cost=8,
                primary_theme="AI_PCB",
                theme_tags=["AI_PCB", "HIGH_VOLATILITY", "COMPOSITE_EXPOSURE"],
                user_plan="plan",
            ),
            PortfolioPositionInput(
                symbol="159382",
                name="ETF",
                quantity=100,
                avg_cost=1,
                primary_theme="AI_THEME_ETF",
                theme_tags=["AI_THEME_ETF", "COMPOSITE_EXPOSURE"],
            ),
        ],
    ))
    service.add_manual_evidence(ManualEvidenceCreate(
        symbol=None,
        evidence_type="macro_observation_manual",
        title="Portfolio level evidence",
        text="portfolio note",
        include_in_analysis_packet=True,
    ))
    monkeypatch.setattr(packet_service, "portfolio_service", service)
    monkeypatch.setattr(packet_service.settings, "ANALYSIS_SNAPSHOT_DIR", str(tmp_path / "snapshots"))

    first = packet_service.build_portfolio_packet(persist=True)
    second = packet_service.build_portfolio_packet(persist=True)

    assert first["packet"]["account_overview"]["cash_available"] == 500
    assert first["packet"]["account_overview"]["repo_amount"] == 200
    assert "holdings" in first["packet"]
    assert "system_hypothesis" in first["packet"]
    assert first["packet"]["holdings"][0]["market_price_as_of"] is None
    assert first["packet"]["holdings"][0]["market_price_time_status"] == "unavailable"
    assert "portfolio snapshot time is not market quote time" in first["markdown"]
    assert first["packet"]["account_overview"]["repo_policy"]["cash_equivalent_treatment"] == "unconfirmed"
    themes = {item["theme"] for item in first["packet"]["primary_theme_exposure"]}
    assert themes == {"AI_PCB", "AI_THEME_ETF"}
    assert "non-additive" in first["packet"]["related_risk_observations"]["boundary"]
    assert all(item.get("unconfirmed_by_user") is True for item in first["packet"]["system_hypothesis"])
    assert first["packet"]["manual_evidence"][0]["title"] == "Portfolio level evidence"
    assert first["packet"]["meta"]["packet_id"] != second["packet"]["meta"]["packet_id"]
    saved = list((tmp_path / "snapshots" / "analysis_packets" / "portfolio" / "local_default").glob("*.json"))
    assert len(saved) == 2


def test_manual_evidence_include_update_controls_packet_export(tmp_path, monkeypatch):
    service = PortfolioService(root=tmp_path / "portfolio")
    record = service.add_manual_evidence(ManualEvidenceCreate(
        symbol="600000",
        evidence_type="manual_market_observation",
        title="Toggle me",
        text="note",
        include_in_analysis_packet=True,
    ))
    updated = service.update_manual_evidence_include(record.evidence_id, False)
    monkeypatch.setattr(packet_service, "portfolio_service", service)
    monkeypatch.setattr(packet_service, "build_basic_stock_snapshot", _fake_stock_snapshot)

    result = packet_service.build_single_stock_packet("600000", persist=False)

    assert updated is not None
    assert updated.include_in_analysis_packet is False
    assert result["packet"]["manual_evidence"] == []


def test_etf_unavailable_status_enters_single_packet_when_no_token(tmp_path, monkeypatch):
    service = PortfolioService(root=tmp_path / "portfolio")
    service.save_snapshot(PortfolioSnapshotInput(cash_available=1000, positions=[]))
    monkeypatch.setattr(packet_service, "portfolio_service", service)
    monkeypatch.setattr(packet_service, "build_basic_stock_snapshot", _fake_stock_snapshot)
    monkeypatch.setattr(packet_service, "get_etf_facts", lambda symbol: {
        "success": False,
        "symbol": symbol,
        "message": "Tushare token is not configured.",
        "data_status": "unavailable",
        "data": None,
        "evidence": [],
    })

    result = packet_service.build_single_stock_packet("159382.SZ", persist=False)

    matches = [item for item in result["packet"]["auto_fact"] if item.get("evidence_type") == "etf_share_change"]
    assert matches
    assert matches[0]["category"] == "auto_fact"
    assert matches[0]["data_status"] == "unavailable"


def test_packet_markdown_has_no_mojibake_markers(tmp_path, monkeypatch):
    service = PortfolioService(root=tmp_path / "portfolio")
    service.save_snapshot(PortfolioSnapshotInput(cash_available=1000, positions=[]))
    monkeypatch.setattr(packet_service, "portfolio_service", service)
    monkeypatch.setattr(packet_service, "build_basic_stock_snapshot", _fake_stock_snapshot)

    result = packet_service.build_single_stock_packet("600000", persist=False)

    assert not packet_service.has_mojibake(result["markdown"])
