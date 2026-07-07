from __future__ import annotations

import sys
from datetime import datetime
from types import SimpleNamespace

import pandas as pd

from app.analysis_packet import packet_service
from app.api import portfolio as portfolio_api
from app.data_sources import akshare_etf_share
from app.portfolio.schemas import PortfolioPositionInput, PortfolioSnapshotInput
from app.portfolio.service import PortfolioService
from app.services.portfolio_etf_share_sync import current_etf_symbols, new_etf_symbols, sync_new_etf_share_data
from app.services import etf_share_service as service_module
from app.services import portfolio_etf_share_sync
from app.services.etf_share_service import EtfShareService, compute_share_metrics


def test_akshare_adapter_normalizes_sse_and_szse_mock_data(monkeypatch):
    fake_ak = SimpleNamespace(
        fund_etf_scale_sse=lambda date: pd.DataFrame([
            {"基金代码": "518880", "基金简称": "黄金ETF", "统计日期": date, "基金份额(亿份)": 10.5},
            {"基金代码": "510300", "基金简称": "沪深300ETF", "统计日期": date, "基金份额(亿份)": 99},
        ]),
        fund_scale_daily_szse=lambda start_date, end_date, symbol: pd.DataFrame([
            {"基金代码": "159819", "基金简称": "创业板人工智能ETF", "交易日期": "2026-05-29", "基金份额": 1_000_000_000},
            {"基金代码": "159819", "基金简称": "创业板人工智能ETF", "交易日期": "2026-05-30", "基金份额": 1_020_000_000},
        ]),
    )
    monkeypatch.setitem(sys.modules, "akshare", fake_ak)

    sse = akshare_etf_share.fetch_sse_etf_share("518880", "20260530")
    szse = akshare_etf_share.fetch_szse_etf_share_history("159819", "20260501", "20260530")

    assert akshare_etf_share.infer_exchange("518880") == "SSE"
    assert akshare_etf_share.infer_exchange("159819") == "SZSE"
    assert sse[0]["fund_share"] == 1_050_000_000
    assert sse[0]["fund_share_100m"] == 10.5
    assert szse[-1]["fund_code"] == "159819"
    assert szse[-1]["trade_date"] == "2026-05-30"


def test_etf_share_cache_write_read_and_metrics(tmp_path, monkeypatch):
    records = [
        {
            "fund_code": "159819",
            "fund_name": "创业板人工智能ETF",
            "exchange": "SZSE",
            "trade_date": f"2026-05-{day:02d}",
            "fund_share": 1_000_000_000 + day * 10_000_000,
            "fund_share_100m": 10 + day * 0.1,
            "nav": None,
            "source": "akshare",
            "fetched_at": datetime.utcnow().isoformat(),
            "raw_fields": {"day": day},
        }
        for day in range(1, 23)
    ]
    monkeypatch.setattr(service_module, "fetch_szse_etf_share_history", lambda *args, **kwargs: records)

    svc = EtfShareService(cache_root=tmp_path)
    result = svc.update_one("159819", start="2026-05-01", end="2026-05-30", force=True)
    cached = svc.read_cache("159819")
    metrics = compute_share_metrics(cached)

    assert result.success is True
    assert result.cache_path
    assert len(cached) == 22
    assert metrics["latest_share_100m"] == 12.2
    assert metrics["share_chg_1d"] is not None
    assert metrics["share_chg_5d"] is not None
    assert metrics["share_chg_20d"] is not None


def test_update_many_records_warning_without_interrupt(tmp_path, monkeypatch):
    def fail_history(*args, **kwargs):
        raise service_module.AkshareEtfShareError("network failed")

    monkeypatch.setattr(service_module, "fetch_szse_etf_share_history", fail_history)
    monkeypatch.setattr(service_module, "fetch_szse_etf_share_latest", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        service_module,
        "fetch_em_etf_share_latest",
        lambda *args, **kwargs: (_ for _ in ()).throw(service_module.AkshareEtfShareError("fallback failed")),
    )

    svc = EtfShareService(cache_root=tmp_path)
    results = svc.update_many(["159819", "000001"], force=True)

    assert len(results) == 2
    assert results[0].success is False
    assert "matched" in results[0].reason
    assert results[0].warnings
    assert results[1].success is False
    assert "Non-ETF" in results[1].reason


def test_update_one_uses_eastmoney_spot_fallback(tmp_path, monkeypatch):
    def fail_history(*args, **kwargs):
        raise service_module.AkshareEtfShareError("network failed")

    fallback_records = [{
        "fund_code": "159819",
        "fund_name": "创业板人工智能ETF",
        "exchange": "SZSE",
        "trade_date": "2026-06-08",
        "fund_share": 1_230_000_000,
        "fund_share_100m": 12.3,
        "nav": None,
        "source": "akshare_eastmoney_spot",
        "fetched_at": datetime.utcnow().isoformat(),
        "raw_fields": {},
    }]
    monkeypatch.setattr(service_module, "fetch_szse_etf_share_history", fail_history)
    monkeypatch.setattr(service_module, "fetch_szse_etf_share_latest", lambda *args, **kwargs: [])
    monkeypatch.setattr(service_module, "fetch_em_etf_share_latest", lambda *args, **kwargs: fallback_records)

    svc = EtfShareService(cache_root=tmp_path)
    result = svc.update_one("159819", force=True)

    assert result.success is True
    assert result.metrics["source"] == "akshare_eastmoney_spot"
    assert result.metrics["latest_share_100m"] == 12.3
    assert result.warnings


def test_account_context_keeps_running_when_etf_share_cache_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("app.portfolio.service.collector.get_quote", lambda symbol: {"symbol": symbol, "name": symbol, "price": 1.0})
    monkeypatch.setattr(packet_service, "get_dragon_tiger_facts", lambda symbol: {"data_status": "unavailable", "evidence": []})
    monkeypatch.setattr(packet_service, "get_disclosure_facts", lambda symbol: {"data_status": "unavailable", "evidence": []})
    monkeypatch.setattr(packet_service, "get_etf_facts", lambda symbol: {"data_status": "unavailable", "evidence": [], "message": "mock unavailable"})
    monkeypatch.setattr(packet_service, "etf_share_service", EtfShareService(cache_root=tmp_path / "etf_share"))

    portfolio = PortfolioService(root=tmp_path / "portfolio")
    portfolio.save_snapshot(PortfolioSnapshotInput(
        cash_available=1000,
        positions=[
            PortfolioPositionInput(
                symbol="159819",
                name="创业板人工智能ETF",
                quantity=100,
                avg_cost=1.0,
                directions=["AI"],
                position_role="observation",
            )
        ],
    ))
    monkeypatch.setattr(packet_service, "portfolio_service", portfolio)

    context = packet_service.build_account_analysis_context(mode="compact")

    assert context["etf_share_observations"]["observations"] == []
    assert context["etf_share_observations"]["unavailable"][0]["fund_code"] == "159819"
    assert any(gap.get("key") == "ETF 份额 / 净值事实" for gap in context["data_gaps"] if isinstance(gap, dict))


def test_new_etf_share_sync_only_requests_new_current_portfolio_etfs(monkeypatch):
    previous = PortfolioSnapshotInput(
        cash_available=1000,
        positions=[
            PortfolioPositionInput(symbol="600000", name="浦发银行", quantity=100, avg_cost=10),
            PortfolioPositionInput(symbol="518880", name="黄金ETF", quantity=100, avg_cost=5),
        ],
    )
    current = PortfolioSnapshotInput(
        cash_available=1000,
        positions=[
            PortfolioPositionInput(symbol="518880", name="黄金ETF", quantity=100, avg_cost=5),
            PortfolioPositionInput(symbol="159819", name="创业板人工智能ETF", quantity=0, avg_cost=0),
        ],
    )
    calls = []

    def fake_update_many(codes, *, names=None, force=False, **kwargs):
        calls.append({"codes": codes, "names": names, "force": force})
        return []

    monkeypatch.setattr(portfolio_etf_share_sync.etf_share_service, "update_many", fake_update_many)

    assert current_etf_symbols(current)[0] == ["159819", "518880"]
    assert new_etf_symbols(previous, current)[0] == ["159819"]
    assert sync_new_etf_share_data(previous, current) == []
    assert calls == [{"codes": ["159819"], "names": {"159819": "创业板人工智能ETF", "518880": "黄金ETF"}, "force": True}]


def test_portfolio_api_save_triggers_immediate_sync_for_added_etf(tmp_path, monkeypatch):
    portfolio = PortfolioService(root=tmp_path / "portfolio")
    portfolio.save_snapshot(PortfolioSnapshotInput(
        cash_available=1000,
        positions=[PortfolioPositionInput(symbol="600000", name="浦发银行", quantity=100, avg_cost=10)],
    ))
    calls = []

    def fake_sync(previous_snapshot, current_snapshot):
        calls.append(new_etf_symbols(previous_snapshot, current_snapshot)[0])
        return []

    monkeypatch.setattr(portfolio_api, "portfolio_service", portfolio)
    monkeypatch.setattr(portfolio_api, "sync_new_etf_share_data", fake_sync)

    payload = PortfolioSnapshotInput(
        cash_available=1000,
        positions=[
            PortfolioPositionInput(symbol="600000", name="浦发银行", quantity=100, avg_cost=10),
            PortfolioPositionInput(symbol="159819", name="创业板人工智能ETF", quantity=0, avg_cost=0),
        ],
    )
    response = portfolio_api.save_portfolio(payload)

    assert response["success"] is True
    assert response["etf_share_update"] == []
    assert calls == [["159819"]]
