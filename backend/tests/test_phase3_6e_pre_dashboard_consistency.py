from types import SimpleNamespace

import pandas as pd

from app.analysis_packet import packet_service
from app.analysis_packet.packet_service import build_account_analysis_context, build_portfolio_packet, render_compact_markdown
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


def _fake_history(symbol: str, limit: int = 5000):
    code = symbol.split(".", 1)[0].zfill(6)
    base = {
        "002463": 30,
        "002916": 24,
        "159382": 1.2,
        "601899": 16,
        "603993": 8,
        "159934": 4.6,
    }.get(code, 10)
    rows = []
    for idx in range(80):
        close = base + idx * 0.08
        rows.append({
            "date": f"2026-03-{(idx % 28) + 1:02d}",
            "open": close - 0.03,
            "high": close + 0.05,
            "low": close - 0.06,
            "close": close,
            "volume": 100000 + idx,
            "amount": 1000000 + idx,
            "pctChg": 0.5,
        })
    return pd.DataFrame(rows).tail(limit)


def _service(tmp_path, monkeypatch) -> PortfolioService:
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    monkeypatch.setattr(packet_service.collector, "get_history", _fake_history)
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
            PortfolioPositionInput(symbol="601899", name="Zijin", quantity=1000, avg_cost=18, primary_theme="METAL_RESOURCE", theme_tags=["METAL_RESOURCE", "GOLD", "COPPER", "COMPOSITE_EXPOSURE"], position_role="observation", semantic_classification_status="user_confirmed"),
            PortfolioPositionInput(symbol="603993", name="CMOC", quantity=1000, avg_cost=9, primary_theme="METAL_RESOURCE", theme_tags=["METAL_RESOURCE", "COPPER"], position_role="observation", semantic_classification_status="user_confirmed"),
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
    assert themes["PCB"]["weight_pct"] == round(themes["PCB"]["market_value"] / expected_total * 100, 2)
    assert "not broker-verified realtime total assets" in estimate["boundary"]


def test_related_tag_exposure_is_strictly_confirmed_tags(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    packet = build_portfolio_packet(persist=False)["packet"]
    official = {item["theme"]: set(item["symbols"]) for item in packet["official_theme_exposure"]}
    directions = {item["theme"]: set(item["symbols"]) for item in build_account_analysis_context()["related_theme_observations"]["direction_observations"]}
    risks = {item["theme"]: set(item["symbols"]) for item in build_account_analysis_context()["related_theme_observations"]["risk_observations"]}

    assert official["PCB"] == {"002463", "002916"}
    assert official["AI"] == {"159382"}
    assert directions["PCB"] == {"002463", "002916"}
    assert "159382" not in directions["PCB"]
    assert directions["AI"] == {"159382"}
    assert risks["HIGH_VOLATILITY"] == {"002463", "002916", "159382"}
    assert directions["COPPER"] == {"601899", "603993"}
    assert directions["GOLD"] == {"601899", "159934"}
    assert "AI_RELATED" not in directions


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

    assert "shared_external_driver_observations" in summary
    assert "boundary" in summary
    assert "unavailable_drivers" in summary
    # Unavailable drivers go to unavailable_drivers, not observations
    unavailable = summary["unavailable_drivers"]
    assert unavailable
    observation = unavailable[0]
    assert observation["factor_id"] == "ai_theme_etf_159382"
    assert set(observation["associated_symbols"]) == {"002463", "002916", "159382"}
    assert "evidence" not in observation
    assert "mapping" not in observation


def test_total_cost_basis_and_unrealized_pnl(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    packet = build_portfolio_packet(persist=False)["packet"]
    metrics = packet_service.portfolio_service.get_state().metrics

    # Expected calculations based on _fake_quote:
    # 002463: qty=500, cost=35, price=40 -> cost=17500, pnl=2500
    # 002916: qty=500, cost=28, price=30 -> cost=14000, pnl=1000
    # 159382: qty=10000, cost=1.4, price=1.5 -> cost=14000, pnl=1000
    # 601899: qty=1000, cost=18, price=20 -> cost=18000, pnl=2000
    # 603993: qty=1000, cost=9, price=10 -> cost=9000, pnl=1000
    # 159934: qty=2000, cost=4.8, price=5 -> cost=9600, pnl=400
    expected_cost = 17500 + 14000 + 14000 + 18000 + 9000 + 9600
    expected_pnl = 2500 + 1000 + 1000 + 2000 + 1000 + 400
    expected_pnl_pct = expected_pnl / expected_cost * 100

    assert metrics.total_cost_basis == expected_cost
    assert metrics.total_unrealized_pnl == expected_pnl
    assert abs(metrics.total_unrealized_pnl_pct - expected_pnl_pct) < 0.1
    assert metrics.total_unrealized_pnl_status == "available"
    assert metrics.excluded_symbols == []


def test_account_actual_total_cost_drives_account_total_pnl(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    saved = service.load_snapshot()
    payload = saved.model_dump()
    payload["account_actual_total_cost"] = 110000
    service.save_snapshot(PortfolioSnapshotInput(**payload))

    context = build_account_analysis_context(mode="compact")
    facts = context["account_facts"]
    expected_assets = facts["total_market_value"] + facts["cash_available"] + facts.get("repo_amount", 0)

    assert facts["account_actual_total_cost"] == 110000
    assert facts["account_actual_total_cost_source"] == "user_manual_entry"
    assert facts["account_total_pnl"] == round(expected_assets - 110000, 2)
    assert facts["current_holding_unrealized_pnl"] == 7900

    md = render_compact_markdown(context)
    assert "账户总盈亏" in md
    assert "当前持仓浮动盈亏" in md
    assert "持仓累计浮动盈亏" not in md


def test_missing_account_actual_total_cost_does_not_fake_account_pnl(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    context = build_account_analysis_context(mode="compact")

    assert context["account_facts"]["account_actual_total_cost"] is None
    assert context["account_facts"]["account_total_pnl"] is None
    assert any(gap.get("key") == "账户实际总成本" for gap in context["data_gaps"] if isinstance(gap, dict))
    assert "账户总盈亏 | 暂不可计算" in render_compact_markdown(context)


def test_compact_context_uses_one_valuation_snapshot(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    context = build_account_analysis_context(mode="compact")
    facts = context["account_facts"]

    holdings_market_value = round(sum(item["market_value"] or 0 for item in context["holdings"]), 2)
    primary_market_value = round(sum(item["market_value"] or 0 for item in context["primary_direction_grouping"]), 2)
    holdings_pnl = round(sum(item["unrealized_pnl"] or 0 for item in context["holdings"]), 2)

    assert context["meta"]["valuation_snapshot_id"].startswith("valuation_")
    assert context["meta"]["valuation_consistency_status"] == "passed"
    assert holdings_market_value == facts["total_market_value"]
    assert primary_market_value == facts["total_market_value"]
    assert holdings_pnl == facts["current_holding_unrealized_pnl"]


def test_compact_context_includes_holding_trend_evidence(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    context = build_account_analysis_context(mode="compact")
    trend = {item["symbol"]: item for item in context["holding_trend_evidence"]}

    assert trend["002463"]["data_status"] == "available"
    assert trend["002463"]["ma5"] is not None
    assert trend["002463"]["ma10"] is not None
    assert trend["002463"]["ma20"] is not None
    assert trend["002463"]["ma30"] is not None
    assert trend["002463"]["return_5d_pct"] is not None
    assert trend["002463"]["trend_state"] in {"短期强势排列", "偏强观察", "震荡偏稳"}

    md = render_compact_markdown(context)
    assert "持仓近期走势证据" in md
    assert "MA5" in md
    assert "MA30" in md
    assert "不构成买卖、加仓、减仓或止盈止损指令" in md


def test_compact_context_excludes_audit_fields(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    context = build_account_analysis_context(mode="compact")

    assert "broker_screenshot_price" not in context["holdings"][0]
    assert "import_draft_id" not in context["holdings"][0]
    assert "semantic_classification_source" not in context["holdings"][0]
    assert "user_plan" not in context["holdings"][0]
    assert "quote_time_boundary" not in context["holdings"][0]
    assert "interpretation_boundaries" not in context
    assert "system_hypothesis" not in context
    assert "auto_fact_summary" not in context
    assert "broker_sync" not in str(context.get("data_gaps", []))
    assert "quote_time" not in str(context.get("data_gaps", []))


def test_compact_repo_hidden_when_zero(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", _fake_quote)
    service = PortfolioService(tmp_path)
    monkeypatch.setattr(packet_service, "portfolio_service", service)
    service.save_snapshot(PortfolioSnapshotInput(
        total_assets=100000,
        cash_available=50000,
        repo_amount=0,
        positions=[
            PortfolioPositionInput(symbol="601899", name="Zijin", quantity=1000, avg_cost=18, primary_theme="METAL_RESOURCE", theme_tags=["METAL_RESOURCE"], position_role="observation", semantic_classification_status="user_confirmed"),
        ],
    ))
    context = build_account_analysis_context(mode="compact")

    assert "repo_amount" not in context["account_facts"]
    assert "repo_ratio_pct" not in context["account_facts"]


def test_time_format_is_utc_z(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    context = build_account_analysis_context(mode="compact")

    generated = context["meta"]["generated_at"]
    assert generated.endswith("Z")


def test_composite_exposure_only_from_tag_not_length(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    packet = build_portfolio_packet(persist=False)["packet"]

    # Only 601899 has COMPOSITE_EXPOSURE tag
    composite_notes = packet["related_risk_observations"]["composite_exposure_notes"]
    symbols_with_composite = {n["symbol"] for n in composite_notes}
    assert symbols_with_composite == {"601899"}

    # 002463 and 002916 have multiple tags (AI_PCB + HIGH_VOLATILITY) but no COMPOSITE_EXPOSURE
    # They should NOT appear in composite_exposure_notes


def test_compact_gold_cross_theme_restored(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    context = build_account_analysis_context(mode="compact")
    directions = {item["theme"]: item for item in context["related_theme_observations"]["direction_observations"]}
    assert "GOLD" in directions, "GOLD cross-theme linkage should be restored"
    assert set(directions["GOLD"]["symbols"]) == {"601899", "159934"}

    md = render_compact_markdown(context)
    assert "黄金" in md
    assert "主要方向归组仍归属其他类别" in md or "黄金" in md


def test_compact_external_driver_groups_no_duplication(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)

    def fake_mixed_drivers(symbol: str, primary_theme=None):
        evidence = []
        if symbol == "601899":
            evidence.append({
                "category": "auto_fact",
                "evidence_type": "external_driver_fact",
                "data_status": "available",
                "payload": {
                    "factor_id": "comex_gold_yahoo",
                    "display_name": "COMEX Gold Futures Reference",
                    "factor_type": "commodity",
                    "data_status": "available",
                    "close": 2345.6,
                    "currency": "USD",
                    "quote_unit": "USD/troy oz",
                    "returns_pct": {"1d": 0.5, "5d": 1.2, "20d": 3.4},
                },
            })
        return SimpleNamespace(
            mapping_status="configured",
            profile_id="TEST",
            symbol=symbol,
            message="test",
            future_extension="test",
            drivers=[],
            boundary="External-driver mapping boundary.",
            evidence=evidence,
            missing_data=[],
        )

    monkeypatch.setattr(packet_service, "build_external_driver_context", fake_mixed_drivers)
    context = build_account_analysis_context(mode="compact")
    summary = context["external_driver_summary"]
    observations = summary["shared_external_driver_observations"]
    unavailable = summary["unavailable_drivers"]

    obs_ids = {o["factor_id"] for o in observations}
    unav_ids = {u["factor_id"] for u in unavailable}
    assert not (obs_ids & unav_ids), "Available and unavailable driver sets must not overlap"
    assert "comex_gold_yahoo" in obs_ids
    assert "comex_gold_yahoo" not in unav_ids

    md = render_compact_markdown(context)
    assert "2,345.6000 USD/troy oz" in md


def test_compact_data_gaps_restored(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    context = build_account_analysis_context(mode="compact")
    assert context["data_gaps"], "Compact data_gaps should be restored"
    gap_keys = {g["key"] for g in context["data_gaps"] if isinstance(g, dict)}
    assert "ETF 份额 / 净值事实" in gap_keys or "龙虎榜 / 公告索引" in gap_keys

    md = render_compact_markdown(context)
    assert "## 数据缺口" in md


def test_compact_role_chinese_names_and_format(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    context = build_account_analysis_context(mode="compact")
    md = render_compact_markdown(context)

    # Role mapped to Chinese
    assert "观察" in md

    # Chinese names used in tables
    assert "紫金矿业" in md or "沪电股份" in md

    # Amount format with 2 decimals
    import re
    assert re.search(r"\d{1,3}(?:,\d{3})+\.\d{2}", md), "Amount should use thousands separator and 2 decimals"


def test_compact_time_info_and_ai_questions(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    context = build_account_analysis_context(mode="compact")
    md = render_compact_markdown(context)

    assert "持仓快照时间" in md
    assert "行情取数时间" in md
    assert "系统取数时间不是可验证市场报价时间" in md

    assert "给外部 AI 的任务" in md
    questions = context["suggested_questions_for_external_llm"]
    assert all(any("一" <= ch <= "鿿" for ch in q) for q in questions), "AI questions should be in Chinese"


def test_unsupported_placeholder_hidden_in_compact(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)

    def fake_with_placeholder(symbol: str, primary_theme=None):
        return SimpleNamespace(
            mapping_status="configured",
            profile_id="TEST",
            symbol=symbol,
            message="test",
            future_extension="test",
            drivers=[],
            boundary="External-driver mapping boundary.",
            evidence=[],
            missing_data=[{
                "key": "external_driver:cobalt_moly_price_placeholder",
                "mapping_status": "unsupported",
                "reason": "Placeholder driver.",
                "factor_type": "unsupported_placeholder",
            }],
        )

    monkeypatch.setattr(packet_service, "build_external_driver_context", fake_with_placeholder)
    context = build_account_analysis_context(mode="compact")
    summary = context["external_driver_summary"]
    all_factor_ids = {
        o["factor_id"] for o in summary.get("shared_external_driver_observations", [])
    } | {
        u["factor_id"] for u in summary.get("unavailable_drivers", [])
    }
    assert "cobalt_moly_price_placeholder" not in all_factor_ids


def test_compact_direction_and_risk_separated(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    context = build_account_analysis_context(mode="compact")
    related = context["related_theme_observations"]

    directions = {item["theme"]: item for item in related["direction_observations"]}
    risks = {item["theme"]: item for item in related["risk_observations"]}

    assert "HIGH_VOLATILITY" not in directions, "HIGH_VOLATILITY must not appear in direction_observations"
    assert "HIGH_VOLATILITY" in risks, "HIGH_VOLATILITY must appear in risk_observations"
    assert set(risks["HIGH_VOLATILITY"]["symbols"]) == {"002463", "002916", "159382"}

    md = render_compact_markdown(context)
    assert "## 全部方向观察" in md
    assert "## 风险观察" in md
    assert "高波动" in md


def test_compact_copper_direction_present(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    context = build_account_analysis_context(mode="compact")
    directions = {item["theme"]: item for item in context["related_theme_observations"]["direction_observations"]}

    assert "COPPER" in directions, "COPPER direction should be present"
    assert set(directions["COPPER"]["symbols"]) == {"601899", "603993"}

    md = render_compact_markdown(context)
    assert "铜" in md


def test_compact_composite_exposure_hidden(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    context = build_account_analysis_context(mode="compact")
    directions = {item["theme"]: item for item in context["related_theme_observations"]["direction_observations"]}
    risks = {item["theme"]: item for item in context["related_theme_observations"]["risk_observations"]}

    assert "COMPOSITE_EXPOSURE" not in directions, "COMPOSITE_EXPOSURE must not appear in direction_observations"
    assert "COMPOSITE_EXPOSURE" not in risks, "COMPOSITE_EXPOSURE must not appear in risk_observations"

    md = render_compact_markdown(context)
    assert "多重逻辑关联" not in md, "COMPOSITE_EXPOSURE should not be rendered in compact markdown"


def test_compact_data_gaps_grouped(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    context = build_account_analysis_context(mode="compact")
    md = render_compact_markdown(context)

    # Gaps should be grouped by key, not repeated per symbol
    assert "当前暂无数据" in md
    assert "涉及标的" in md
    # Per-symbol repetition pattern like "（601899）" should not appear
    assert "（601899）" not in md
    assert "（603993）" not in md


def test_compact_holdings_direction_excludes_primary_theme(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    context = build_account_analysis_context(mode="compact")
    md = render_compact_markdown(context)

    # 601899 legacy METAL_RESOURCE should normalize to concrete directions.
    lines = md.split("\n")
    zijin_line = [line for line in lines if "紫金矿业" in line]
    assert zijin_line, "Zijin holding row should exist in markdown"
    assert "铜, 黄金" in zijin_line[0], "Zijin direction should show 铜 and 黄金"
    assert "金属资源" not in zijin_line[0]


def test_compact_ai_question_wording(tmp_path, monkeypatch):
    _service(tmp_path, monkeypatch)
    context = build_account_analysis_context(mode="compact")
    questions = context["suggested_questions_for_external_llm"]

    first_question = questions[0]
    assert "关联方向与风险观察" in first_question, "AI question should distinguish direction and risk"
    assert "theme_tags 仅是非加总的关联观察" not in first_question, "AI question should not use old theme_tags wording"


def test_localize_driver_pending_probe():
    from app.analysis_packet.packet_service import _localize_driver_status
    status, reason = _localize_driver_status(
        "pending_probe",
        "Gold futures provider code still requires a successful probe before automatic retrieval.",
    )
    assert status == "待验证接入"
    assert reason == "数据源尚未完成成功探测"
