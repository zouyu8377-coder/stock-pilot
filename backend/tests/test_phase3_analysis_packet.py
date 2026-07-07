from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
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
        market_data_as_of=None,
        daily_k_as_of=date(2026, 5, 22),
        evidence_items=[
            EvidenceItem(
                symbol=symbol,
                evidence_type=EvidenceType.REALTIME_QUOTE,
                category=EvidenceCategory.AUTO_FACT,
                title="Realtime quote snapshot",
                payload={
                    "symbol": symbol,
                    "name": f"Name{symbol}",
                    "price": 10.0,
                    "provider": "test",
                    "quote_retrieved_at": fetched_at.isoformat(),
                    "quote_market_time": None,
                    "quote_time_status": "unavailable",
                },
                source="test quote",
                source_endpoint="collector.get_quote",
                as_of_time=None,
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
            EvidenceItem(
                symbol=symbol,
                evidence_type=EvidenceType.COMPANY_PROFILE,
                category=EvidenceCategory.AUTO_FACT,
                title="Company profile",
                payload={
                    "company_name": f"Name{symbol}",
                    "industry_chain_position": "中游制造/服务",
                    "core_logic": ["rule inferred logic"],
                    "concept_tags": ["TEST_TAG"],
                    "competitive_advantage": "评价性最强表述",
                },
                source="stock_meta/Tushare cache/rule inference",
                source_endpoint="build_company_profile",
                fetched_at=fetched_at,
                reliability=EvidenceReliability.B,
                llm_usage=LlmUsage.CONTEXT_ONLY,
                interpretation_limit="Context only.",
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


def _unmapped_external_context(symbol: str, primary_theme=None, directions=None):
    return SimpleNamespace(
        mapping_status="not_configured",
        profile_id="DEFAULT_UNMAPPED_V1",
        symbol=symbol,
        message="当前未为该标的配置专属外部驱动因子。系统仅保留个股自身证据，不自动附加商品、汇率或板块驱动。",
        future_extension="可在后续根据行业、主题或用户观察需求新增映射。",
        drivers=[],
        boundary="External-driver mapping is a product configuration used to select observation variables.",
        evidence=[],
        missing_data=[],
    )


def test_single_stock_packet_without_holding_has_manual_account_boundary(tmp_path, monkeypatch):
    service = PortfolioService(root=tmp_path / "portfolio")
    service.save_snapshot(PortfolioSnapshotInput(cash_available=1000, positions=[]))
    monkeypatch.setattr(packet_service, "portfolio_service", service)
    monkeypatch.setattr(packet_service, "build_basic_stock_snapshot", _fake_stock_snapshot)
    monkeypatch.setattr(packet_service, "build_external_driver_context", _unmapped_external_context)
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
    assert "market_data_as_of" not in result["packet"]["meta"]
    assert result["packet"]["meta"]["quote_market_time"] is None
    assert result["packet"]["meta"]["quote_time_status"] == "unavailable"
    assert not any(item.get("evidence_type") == "company_profile" for item in result["packet"]["auto_fact"])
    assert any(item.get("evidence_type") == "company_profile_context" for item in result["packet"]["system_hypothesis"])
    assert "评价性最强表述" not in result["markdown"]
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
    monkeypatch.setattr(packet_service, "build_external_driver_context", _unmapped_external_context)

    result = packet_service.build_single_stock_packet("600000", persist=False)

    account = result["packet"]["manual_account"]
    assert account["has_holding"] is True
    assert account["quantity"] == 100
    assert account["portfolio_weight_pct"] is not None
    assert account["confirmed_primary_theme"] == "BANK"
    assert account["confirmed_theme_tags"] == ["BANK"]
    assert "account-level position and portfolio analysis belongs" in account["account_analysis_boundary"]
    assert [item["evidence_id"] for item in result["packet"]["manual_evidence"]] == [included.evidence_id]
    assert all(item["category"] == "manual_evidence" for item in result["packet"]["manual_evidence"])
    assert all(item["category"] != "auto_fact" for item in result["packet"]["manual_evidence"])
    assert "Excluded observation" not in result["markdown"]


def test_portfolio_packet_keeps_primary_theme_unique_and_risk_tags_non_additive(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    monkeypatch.setattr(packet_service, "get_dragon_tiger_facts", lambda symbol: {"data_status": "unavailable", "evidence": []})
    monkeypatch.setattr(packet_service, "get_disclosure_facts", lambda symbol: {"data_status": "unavailable", "evidence": []})
    monkeypatch.setattr(packet_service, "get_etf_facts", lambda symbol: {"data_status": "unavailable", "evidence": []})
    monkeypatch.setattr(packet_service, "build_external_driver_context", _unmapped_external_context)
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
    assert first["packet"]["holdings"][0]["quote_market_time"] is None
    assert first["packet"]["holdings"][0]["quote_time_status"] == "unavailable"
    assert "system retrieval time is not market quote time" in first["markdown"]
    assert first["packet"]["account_overview"]["repo_policy"]["cash_equivalent_treatment"] == "unconfirmed"
    themes = {item["theme"] for item in first["packet"]["primary_theme_exposure"]}
    assert themes == {"PCB", "AI"}
    assert "non-additive" in first["packet"]["related_risk_observations"]["boundary"]
    assert first["packet"]["official_theme_exposure"] == first["packet"]["primary_theme_exposure"]
    assert "related_theme_observations" in first["packet"]
    assert first["packet"]["ai_analysis_boundary"]["external_llm_called"] is False
    assert "single_position_limit" in first["packet"]["ai_analysis_boundary"]["inactive_rules_for_ai_reasoning"]
    assert "primary_theme_limit" in first["packet"]["ai_analysis_boundary"]["inactive_rules_for_ai_reasoning"]
    assert any(item.get("risk_parameter_source") == "user_confirmed_theme_tags" for item in first["packet"]["system_hypothesis"])
    assert all(item.get("inactive_for_ai_reasoning") is True for item in first["packet"]["system_hypothesis"])
    assert first["packet"]["manual_evidence"][0]["title"] == "Portfolio level evidence"
    assert first["packet"]["meta"]["packet_id"] != second["packet"]["meta"]["packet_id"]
    saved = list((tmp_path / "snapshots" / "analysis_packets" / "portfolio" / "local_default").glob("*.json"))
    assert len(saved) == 2


def test_account_analysis_context_uses_confirmed_semantics_without_ai_call(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    monkeypatch.setattr(packet_service, "get_dragon_tiger_facts", lambda symbol: {"data_status": "unavailable", "evidence": []})
    monkeypatch.setattr(packet_service, "get_disclosure_facts", lambda symbol: {"data_status": "unavailable", "evidence": []})
    monkeypatch.setattr(packet_service, "get_etf_facts", lambda symbol: {"data_status": "unavailable", "evidence": []})
    monkeypatch.setattr(packet_service, "build_external_driver_context", _unmapped_external_context)
    service = PortfolioService(root=tmp_path / "portfolio")
    service.save_snapshot(PortfolioSnapshotInput(
        cash_available=500,
        positions=[
            PortfolioPositionInput(
                symbol="600000",
                name="Name600000",
                quantity=100,
                avg_cost=8,
                primary_theme="AI_PCB",
                theme_tags=["AI_PCB", "HIGH_VOLATILITY"],
                position_role="core",
            ),
            PortfolioPositionInput(
                symbol="159382",
                name="ETF",
                quantity=100,
                avg_cost=1,
                primary_theme="AI_THEME_ETF",
                theme_tags=["AI_THEME_ETF", "HIGH_VOLATILITY"],
                position_role="trend",
            ),
        ],
    ))
    monkeypatch.setattr(packet_service, "portfolio_service", service)

    context = packet_service.build_account_analysis_context(mode="audit")

    assert context["account_facts"]["holdings_count"] == 2
    assert {item["confirmed_primary_theme"] for item in context["holdings"]} == {"PCB", "AI"}
    assert context["official_theme_exposure"]
    assert "non-additive" in context["related_theme_observations"]["boundary"]
    assert context["ai_analysis_boundary"]["external_llm_called"] is False
    assert "cash_floor" in context["ai_analysis_boundary"]["inactive_rules_for_ai_reasoning"]
    assert "shared_external_driver_observations" in context["external_driver_summary"]


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
    monkeypatch.setattr(packet_service, "build_external_driver_context", _unmapped_external_context)

    result = packet_service.build_single_stock_packet("600000", persist=False)

    assert updated is not None
    assert updated.include_in_analysis_packet is False
    assert result["packet"]["manual_evidence"] == []


def test_etf_unavailable_status_enters_single_packet_when_no_token(tmp_path, monkeypatch):
    service = PortfolioService(root=tmp_path / "portfolio")
    service.save_snapshot(PortfolioSnapshotInput(cash_available=1000, positions=[]))
    monkeypatch.setattr(packet_service, "portfolio_service", service)
    monkeypatch.setattr(packet_service, "build_basic_stock_snapshot", _fake_stock_snapshot)
    monkeypatch.setattr(packet_service, "build_external_driver_context", _unmapped_external_context)
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
    monkeypatch.setattr(packet_service, "build_external_driver_context", _unmapped_external_context)

    result = packet_service.build_single_stock_packet("600000", persist=False)

    assert not packet_service.has_mojibake(result["markdown"])


def test_unmapped_symbol_gets_explicit_external_driver_default(tmp_path, monkeypatch):
    service = PortfolioService(root=tmp_path / "portfolio")
    service.save_snapshot(PortfolioSnapshotInput(cash_available=1000, positions=[]))
    monkeypatch.setattr(packet_service, "portfolio_service", service)
    monkeypatch.setattr(packet_service, "build_basic_stock_snapshot", _fake_stock_snapshot)

    result = packet_service.build_single_stock_packet("600000", persist=False)

    mapping = result["packet"]["external_driver_mapping"]
    assert mapping["mapping_status"] == "not_configured"
    assert mapping["profile_id"] == "DEFAULT_UNMAPPED_V1"
    assert mapping["drivers"] == []
    assert "不自动附加商品、汇率或板块驱动" in mapping["message"]
    assert not [item for item in result["packet"]["auto_fact"] if item.get("evidence_type") == "external_driver_fact"]


def test_configured_external_driver_enters_fact_and_signal_layers(tmp_path, monkeypatch):
    fetched_at = datetime(2026, 5, 24, 11, 0, 0).isoformat()

    def configured_context(symbol: str, primary_theme=None, directions=None):
        return SimpleNamespace(
            mapping_status="configured",
            profile_id="ZIJIN_RESOURCE_METALS_V1",
            symbol="601899.SH",
            message="configured",
            future_extension="extend later",
            drivers=[{"factor_id": "copper_futures", "factor_type": "commodity"}],
            boundary="Mapping selects observation variables only.",
            evidence=[
                {
                    "evidence_id": "ev_ext_fact",
                    "symbol": "601899.SH",
                    "evidence_type": "external_driver_fact",
                    "category": "auto_fact",
                    "title": "External driver fact: Copper futures daily price",
                    "payload": {"factor_id": "copper_futures", "close": 80000, "returns_pct": {"1d": 1.2}},
                    "source": "tushare.fut_daily",
                    "source_endpoint": "fut_daily",
                    "as_of_date": "2026-05-22",
                    "fetched_at": fetched_at,
                    "reliability": "B",
                    "llm_usage": "fact_with_limit",
                    "interpretation_limit": "background only",
                    "freshness_days": 2,
                    "data_status": "available",
                },
                {
                    "evidence_id": "ev_ext_signal",
                    "symbol": "601899.SH",
                    "evidence_type": "external_driver_signal",
                    "category": "auto_signal",
                    "title": "External driver derived changes: Copper futures daily price",
                    "payload": {"factor_id": "copper_futures", "returns_pct": {"1d": 1.2}},
                    "source": "tushare.fut_daily",
                    "source_endpoint": "fut_daily",
                    "as_of_date": "2026-05-22",
                    "fetched_at": fetched_at,
                    "reliability": "C",
                    "llm_usage": "weak_signal_only",
                    "interpretation_limit": "weak context only",
                    "freshness_days": 2,
                    "data_status": "available",
                },
            ],
            missing_data=[],
        )

    service = PortfolioService(root=tmp_path / "portfolio")
    service.save_snapshot(PortfolioSnapshotInput(cash_available=1000, positions=[]))
    monkeypatch.setattr(packet_service, "portfolio_service", service)
    monkeypatch.setattr(packet_service, "build_basic_stock_snapshot", _fake_stock_snapshot)
    monkeypatch.setattr(packet_service, "build_external_driver_context", configured_context)

    result = packet_service.build_single_stock_packet("601899", persist=False)

    assert result["packet"]["external_driver_mapping"]["profile_id"] == "ZIJIN_RESOURCE_METALS_V1"
    assert any(item.get("evidence_type") == "external_driver_fact" for item in result["packet"]["auto_fact"])
    signals = [item for item in result["packet"]["auto_signal"] if item.get("evidence_type") == "external_driver_signal"]
    assert signals
    assert signals[0]["llm_usage"] == "weak_signal_only"
    assert "## Relevant External Drivers" in result["markdown"]
    assert "copper_futures" in result["markdown"]


def test_single_packet_api_and_markdown_export_use_visible_fixed_chain(tmp_path, monkeypatch):
    service = PortfolioService(root=tmp_path / "portfolio")
    service.save_snapshot(PortfolioSnapshotInput(cash_available=1000, positions=[]))
    monkeypatch.setattr(packet_service, "portfolio_service", service)
    monkeypatch.setattr(packet_service, "build_basic_stock_snapshot", _fake_stock_snapshot)

    response = TestClient(app).post("/api/analysis-packet/single/601899")

    assert response.status_code == 200
    data = response.json()
    packet = data["packet"]
    markdown = data["markdown"]
    assert "## Relevant External Drivers" in markdown
    assert packet["external_driver_mapping"]["profile_id"] == "ZIJIN_RESOURCE_METALS_V1"
    assert "quote_retrieved_at" in markdown
    assert "quote_market_time" in markdown
    assert "market_data_as_of" not in markdown
    assert not any(item.get("evidence_type") == "company_profile" for item in packet["auto_fact"])
    assert any(item.get("evidence_type") == "company_profile_context" for item in packet["system_hypothesis"])
    assert "FX, futures, backtesting" not in markdown
