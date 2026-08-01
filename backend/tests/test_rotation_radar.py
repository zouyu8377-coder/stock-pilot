from app.rotation.service import get_sector_research, load_universe


def test_rotation_universe_uses_v1_scope_after_pruning():
    universe = load_universe()
    sector_ids = {item["sector_id"] for item in universe["sectors"]}
    benchmark_ids = {item["sector_id"] for item in universe["benchmarks"]}

    assert {"hs300", "csi500", "csi1000", "dividend_low_vol"}.issubset(benchmark_ids)
    assert {"ai", "semiconductor", "pcb", "gold", "securities", "bank", "game"}.issubset(sector_ids)
    assert "copper_resources" not in sector_ids
    assert "home_appliance" not in sector_ids
    assert "power_utility" not in sector_ids
    assert "transportation" not in sector_ids
    assert "building_materials" not in sector_ids
    assert "infrastructure" not in sector_ids


def test_rotation_universe_marks_benchmarks_outside_ranking():
    universe = load_universe()

    assert all(item["ranking_enabled"] is False for item in universe["benchmarks"])
    assert all(item["ranking_enabled"] is True for item in universe["sectors"])


def test_rotation_universe_uses_main_and_weak_relation_rules():
    universe = load_universe()
    by_id = {item["sector_id"]: item for item in universe["sectors"]}

    assert "159382" in by_id["ai"]["main_symbols"]
    assert "159934" in by_id["gold"]["main_symbols"]
    assert by_id["pcb"]["weak_symbols"]
    assert by_id["semiconductor"]["weak_holding_tags"]


def test_rotation_universe_has_research_proxy_pool_for_every_sector():
    universe = load_universe()

    for item in universe["sectors"]:
        research_symbols = item.get("research_symbols") or [
            component["symbol"] for component in item.get("components", [])
        ]
        assert len(research_symbols) >= 4, item["sector_id"]


def test_sector_research_exposes_breadth_risk_and_representatives():
    detail = get_sector_research("bank")

    assert detail is not None
    assert len(detail["securities"]) >= 5
    assert detail["breadth"]["constituent_count"] == 4
    assert detail["breadth"]["available_count"] == 4
    assert detail["objective_metrics"]["data_coverage_pct"] == 100
    assert detail["research_as_of"]
    assert len(detail["trend_series"]) >= 60
    assert detail["evidence_analysis"]["supports"]
    assert detail["evidence_analysis"]["conclusion"]
