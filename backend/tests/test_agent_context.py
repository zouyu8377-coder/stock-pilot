from fastapi.testclient import TestClient

from app.agent_context import service
from app.main import app


def _dashboard_bundle():
    return {
        "context": {
            "meta": {
                "portfolio_as_of": "2026-07-29T08:00:00Z",
                "quote_retrieved_at": "2026-07-29T08:01:00Z",
                "valuation_generated_at": "2026-07-29T08:01:00Z",
                "valuation_consistency_status": "consistent",
            },
            "account_facts": {"total_assets": 100000},
            "holdings": [{"symbol": "000001", "name": "测试标的"}],
            "holding_trend_evidence": [{"symbol": "000001", "return_20d_pct": 3.2}],
            "market_event_radar": {"events": []},
            "etf_share_observations": {},
            "theme_evidence_radar": {},
            "overseas_tech_chain": {},
            "external_driver_summary": {},
            "primary_direction_grouping": [],
            "related_theme_observations": {},
            "risk_observations": {},
            "data_gaps": [{"key": "test_gap", "reason": "not available"}],
        },
        "dashboard": {
            "opportunity_queue": [],
            "risk_queue": [],
            "strategy_matrix": [],
            "attractiveness_radar": {},
        },
        "cache": {"status": "hit", "cached_at": "2026-07-29T08:01:00Z"},
    }


def _rotation_bundle():
    sector = {
        "sector_id": "semiconductor",
        "name": "半导体",
        "category": "industry",
        "proxy_type": "etf",
        "primary_symbol": "512480",
        "selected_symbol": "512480",
        "proxy_components": [{"symbol": "512480", "name": "半导体ETF"}],
        "latest_date": "2026-07-29",
        "latest_close": 1.23,
        "returns": {"return_20d_pct": 5.0},
        "moving_averages": {"ma20": 1.2},
        "benchmark": {},
        "relative_strength": {},
        "flow": {},
        "data_quality": "available",
        "missing_fields": [],
        "stale_days_to_market": 0,
        "proxy_meta": {},
        "score": 72,
        "score_delta_1d": 2,
        "score_delta_5d": 8,
        "score_delta_10d": 10,
        "maturity": "emerging",
        "opportunity_stage": "early_turning",
        "action_label": "早期转强",
        "chasing_risk": "low",
        "opportunity_reason": ["相对强度改善"],
        "ma20_distance_pct": 2.5,
    }
    return {
        "generated_at": "2026-07-29T08:02:00",
        "as_of": "2026-07-29",
        "universe_version": "rotation.v1",
        "market_style": {},
        "summary": {"sector_count": 1},
        "benchmarks": [],
        "sectors": [sector],
        "potential_opportunities": [],
        "early_turning": [sector],
        "wait_pullback": [],
        "avoid_now": [],
    }


def _rotation_status():
    return {
        "status": "complete",
        "updated_at": "2026-07-29T08:02:00",
        "last_trading_date": "2026-07-29",
        "stale_count": 0,
        "failed_count": 0,
        "failure_reasons": {},
    }


def test_portfolio_context_contract_is_local_and_separates_inferences(monkeypatch):
    monkeypatch.setattr(service, "get_dashboard_bundle", lambda force=False: _dashboard_bundle())

    result = service.build_portfolio_agent_context()

    assert result["meta"]["contract_version"] == "agent_context.v1"
    assert result["meta"]["privacy_boundary"]["external_llm_called"] is False
    assert result["meta"]["privacy_boundary"]["contains_sensitive_account_data"] is True
    assert result["facts"]["account"]["total_assets"] == 100000
    assert "opportunity_queue" in result["inferences"]
    assert result["missing_data"][0]["key"] == "test_gap"


def test_rotation_context_exposes_proxy_facts_and_stage_as_inference(monkeypatch):
    monkeypatch.setattr(service, "get_rotation_bundle", lambda force=False: _rotation_bundle())
    monkeypatch.setattr(service, "load_rotation_status", _rotation_status)

    result = service.build_rotation_agent_context()

    evidence = result["facts"]["sector_evidence"][0]
    assessment = result["inferences"]["sector_opportunity_assessments"][0]
    assert evidence["proxy_components"][0]["symbol"] == "512480"
    assert "opportunity_stage" not in evidence
    assert assessment["opportunity_stage"] == "early_turning"
    assert result["meta"]["privacy_boundary"]["contains_sensitive_account_data"] is False


def test_daily_review_combines_portfolio_and_rotation(monkeypatch):
    monkeypatch.setattr(service, "get_dashboard_bundle", lambda force=False: _dashboard_bundle())
    monkeypatch.setattr(service, "get_rotation_bundle", lambda force=False: _rotation_bundle())
    monkeypatch.setattr(service, "load_rotation_status", _rotation_status)

    result = service.build_daily_review_context()

    assert result["meta"]["context_type"] == "daily_review"
    assert result["facts"]["portfolio"]["account"]["total_assets"] == 100000
    assert result["facts"]["rotation"]["sector_evidence"][0]["sector_id"] == "semiconductor"
    assert result["missing_data"][0]["scope"] == "portfolio"


def test_stock_context_uses_non_persistent_packet_and_preserves_boundaries(monkeypatch):
    calls = {}

    def packet(symbol, user_question=None, persist=True):
        calls.update(symbol=symbol, user_question=user_question, persist=persist)
        return {
            "packet": {
                "meta": {
                    "daily_k_as_of": "2026-07-29",
                    "quote_retrieved_at": "2026-07-29T08:03:00Z",
                    "portfolio_as_of": None,
                },
                "basic_information": {"symbol": symbol},
                "stock_profile": {"holding": None},
                "auto_fact": [{"fact": "test"}],
                "auto_signal": [{"signal": "test"}],
                "missing_data": [],
            }
        }

    monkeypatch.setattr(service, "build_single_stock_packet", packet)
    result = service.build_stock_agent_context("000001", user_question="测试问题")

    assert calls == {"symbol": "000001", "user_question": "测试问题", "persist": False}
    assert result["facts"]["auto_fact"] == [{"fact": "test"}]
    assert result["inferences"]["auto_signal"] == [{"signal": "test"}]


def test_agent_context_routes_return_json_and_markdown(monkeypatch):
    from app.api import agent_context

    payload = {
        "meta": {
            "contract_version": "agent_context.v1",
            "context_type": "daily_review",
            "generated_at": "2026-07-29T08:00:00Z",
            "privacy_boundary": {
                "external_llm_called": False,
                "contains_sensitive_account_data": True,
            },
        },
        "facts": {},
        "inferences": {},
        "missing_data": [],
        "suggested_questions_for_llm": [],
    }
    monkeypatch.setattr(agent_context, "build_daily_review_context", lambda force=False: payload)
    client = TestClient(app)

    json_response = client.get("/api/agent/context/daily-review")
    markdown_response = client.get("/api/agent/context/daily-review/markdown")

    assert json_response.status_code == 200
    assert json_response.json()["data"]["meta"]["context_type"] == "daily_review"
    assert markdown_response.status_code == 200
    assert markdown_response.headers["content-type"].startswith("text/plain")
    assert "# Stock-Pilot Agent Context: daily_review" in markdown_response.text
