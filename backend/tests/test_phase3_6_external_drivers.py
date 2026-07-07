from datetime import date

import pandas as pd

from app.external_drivers import service
from app.external_drivers.service import build_external_driver_context


class FakeTushareClient:
    def query(self, endpoint, *, namespace, fields=None, ttl=None, force=False, **params):
        return pd.DataFrame([
            {"trade_date": "20260522", "close": 100.0, "open": 99.0, "high": 101.0, "low": 98.0, "vol": 10},
            {"trade_date": "20260521", "close": 95.0, "open": 94.0, "high": 96.0, "low": 93.0, "vol": 9},
            {"trade_date": "20260520", "close": 90.0, "open": 89.0, "high": 91.0, "low": 88.0, "vol": 8},
        ]), {"endpoint": endpoint, "params": params, "cache_hit": False, "row_count": 3}


def test_unmapped_external_driver_context_is_explicit_default():
    context = build_external_driver_context("600000")

    assert context.mapping_status == "not_configured"
    assert context.profile_id == "DEFAULT_UNMAPPED_V1"
    assert context.drivers == []
    assert context.evidence == []
    assert "不自动附加商品、汇率或板块驱动" in context.message


def test_configured_daily_driver_builds_fact_and_weak_signal(monkeypatch):
    monkeypatch.setattr(service, "TushareLowFrequencyClient", FakeTushareClient)
    monkeypatch.setattr(service, "get_etf_facts", lambda symbol: {"evidence": [], "message": "skipped in unit test"})
    monkeypatch.setattr(service, "get_comex_fact", lambda factor_id, range_days="30d", include_series=False, **kw: {
        "factor_id": factor_id,
        "data_status": "unavailable",
        "reason": "Mocked unavailable for unit test",
        "provider": "yahoo_finance",
        "quote_delay_status": "delayed_or_unverified",
    })

    context = build_external_driver_context("601899")

    fact = next(item for item in context.evidence if item["evidence_type"] == "external_driver_fact")
    signal = next(item for item in context.evidence if item["evidence_type"] == "external_driver_signal")
    assert context.mapping_status == "configured"
    assert context.profile_id == "ZIJIN_RESOURCE_METALS_V1"
    assert fact["category"] == "auto_fact"
    assert fact["payload"]["factor_id"] == "copper_futures"
    assert fact["payload"]["returns_pct"]["1d"] == 5.2632
    assert fact["as_of_date"] == date(2026, 5, 22).isoformat()
    assert signal["category"] == "auto_signal"
    assert signal["llm_usage"] == "weak_signal_only"
    assert any(item["key"] == "external_driver:gold_futures" and item["mapping_status"] == "pending_probe" for item in context.missing_data)


def test_unsupported_placeholder_stays_missing_without_fact(monkeypatch):
    monkeypatch.setattr(service, "TushareLowFrequencyClient", FakeTushareClient)
    monkeypatch.setattr(service, "get_etf_facts", lambda symbol: {"evidence": [], "message": "ETF unavailable"})
    monkeypatch.setattr(service, "get_comex_fact", lambda factor_id, range_days="30d", include_series=False, **kw: {
        "factor_id": factor_id,
        "data_status": "unavailable",
        "reason": "Mocked unavailable for unit test",
        "provider": "yahoo_finance",
        "quote_delay_status": "delayed_or_unverified",
    })

    context = build_external_driver_context("000657")

    factor_ids = {item["payload"]["factor_id"] for item in context.evidence if item["evidence_type"] == "external_driver_fact"}
    missing_keys = {item["key"] for item in context.missing_data}
    assert "tungsten_price_placeholder" not in factor_ids
    assert "external_driver:tungsten_price_placeholder" in missing_keys
    assert "external_driver:pcb_sector_index_placeholder" in missing_keys
