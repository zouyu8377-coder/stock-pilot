from copy import deepcopy
from datetime import date, timedelta

import pandas as pd
import pytest

from app.data_sync import collectors as c, service as svc, storage as s


@pytest.fixture
def env(tmp_path, monkeypatch):
    from app.agent_review import discussion as d
    monkeypatch.setattr(s, "ROOT", tmp_path / "sync")
    monkeypatch.setattr(d, "ROOT", tmp_path / "discussion")
    monkeypatch.setattr(d, "account_fingerprint", lambda: "test-account")
    account = {"snapshot_id": "a", "snapshot_time": s.now().isoformat(), "cash_available": 10,
               "positions": [{"symbol": "603259", "quantity": 100, "avg_cost": -1}]}
    sources = {"account": account, "tracked": ["603259"], "stocks": ["603259"], "cold": ["603259"]}
    monkeypatch.setattr(c, "universe", lambda: deepcopy(sources))
    return sources


def complete(name, request, timeout):
    return {"status": "complete", "target_date": request["target_date"], "items": []}


def test_no_server_required_and_repeat_is_cached(env):
    called = []
    def execute(*args):
        called.append(args[0])
        return complete(*args)
    assert svc.run(executor=execute)["status"] == "complete"
    assert called == list(svc.POLICY)
    called.clear()
    assert svc.run(executor=execute)["status"] == "complete"
    assert called == []
    bundle = s.read(s.ROOT / "latest.json")
    assert bundle["model_calls"] == 0 and not bundle["holdings_modified"]
    assert bundle["account"]["positions"][0]["avg_cost"] == -1


def test_full_sync_defers_remaining_stages_at_total_time_budget(env, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(svc.time, 'monotonic', lambda: clock[0])
    called = []
    def execute(name, request, timeout):
        called.append(name)
        clock[0] = 1201
        return complete(name, request, timeout)
    status = svc.run(executor=execute)
    assert called == ['cold']
    assert status['status'] == 'partial'
    assert status['steps']['backfill']['status'] == 'deferred'


def test_failure_does_not_block_following_stages_or_erase_last_success(env):
    svc.run(executor=complete)
    good = s.read(s.ROOT / "market.last_success.json")
    def execute(name, *args):
        if name == "market":
            raise TimeoutError("source unavailable")
        return complete(name, *args)
    status = svc.run(force=True, executor=execute)
    assert status["status"] == "partial"
    assert status["steps"]["public"]["status"] == "complete"
    assert s.read(s.ROOT / "market.last_success.json") == good
    assert s.read(s.ROOT / "latest.json")["sources"]["market"]["status"] == "failed"


def test_new_symbols_invalidate_cache(env):
    svc.run(executor=complete)
    env["tracked"].append("601899")
    called = []
    def execute(*args):
        called.append(args[0])
        return complete(*args)
    svc.run(executor=execute)
    assert called == list(svc.POLICY)


def test_lock_releases_and_reentrant_discussion_lock(env):
    path = s.ROOT / "sync.lock"
    with s.exclusive(path):
        with pytest.raises(BlockingIOError):
            with s.exclusive(path):
                pass
    with s.exclusive(path):
        pass
    lock = s.ProcessRLock(lambda: s.ROOT / "discussion.lock")
    with lock:
        with lock:
            with pytest.raises(BlockingIOError):
                with s.exclusive(s.ROOT / "discussion.lock"):
                    pass


def test_daily_fields_exclude_today_from_volume_baseline(monkeypatch):
    from app.collector.history.base_market_provider import BaseMarketProvider
    frame = pd.DataFrame({"date": pd.date_range("2026-10-01", periods=22), "close": range(1, 23),
                          "volume": [100] * 20 + [300, 9999], "amount": [1000] * 22})
    monkeypatch.setattr(BaseMarketProvider, "get_daily_history", lambda *a: frame)
    data = c.history("603259", "2026-10-21")
    assert data["as_of"] == "2026-10-21"
    assert data["volume_vs_previous_5_complete_days"] == 3
    assert data["volume_ma5"] == 140
    assert data["ma20"] is not None


def test_market_retains_daily_when_live_source_fails(env, monkeypatch):
    from app.collector.realtime.easyquotation_provider import EasyQuotationProvider
    monkeypatch.setattr(EasyQuotationProvider, "get_quote", lambda *a: (_ for _ in ()).throw(TimeoutError("offline")))
    monkeypatch.setattr(c, "history", lambda *a: {"as_of": "2026-10-19", "is_stale": False})
    result = c.market({"universe": env, "target_date": "2026-10-19"}, lambda v: None)
    assert result["status"] == "partial"
    assert result["items"][0]["daily"]["as_of"] == "2026-10-19"
    assert result["items"][0]["quote"]["data_status"] == "unavailable"


def test_production_router_does_not_invent_random_quotes():
    from app.collector.router import CollectorRouter
    from app.collector.realtime.mock_provider import MockRealtimeProvider
    assert not any(isinstance(p, MockRealtimeProvider) for p in CollectorRouter().providers)
    assert isinstance(CollectorRouter(allow_mock=True).providers[-1], MockRealtimeProvider)


def test_cold_verifies_written_dates_not_success_flag(env, monkeypatch, tmp_path):
    from app.data_sync import references
    monkeypatch.setattr(references, "DOMESTIC", (("sh.000300", "benchmark", "mainland", "index"),))
    from app.core import data_updater as up
    target = date(2026, 10, 19)
    monkeypatch.setattr(up, "UPDATE_LOCK_FILE", tmp_path / "cold.lock")
    monkeypatch.setattr(up, "BASE_MARKET_DIR", tmp_path / "market")
    monkeypatch.setattr(up, "get_last_trading_date", lambda: target)
    monkeypatch.setattr(up, "load_update_status", lambda: {})
    monkeypatch.setattr(up, "save_update_status", lambda value: None)
    monkeypatch.setattr(up, "_logout_baostock", lambda: None)
    s.write(up.UPDATE_LOCK_FILE, {"pid": 12345, "owner": "dead-process"})
    monkeypatch.setattr(s, "process_alive", lambda pid: False)
    s.write(s.ROOT / "trading_calendar.json", {"checked_on": s.now().date().isoformat(), "sessions": [target.isoformat()]})
    up.BASE_MARKET_DIR.mkdir()
    for code in ["sh.000300", "sh.603259"]:
        (up.BASE_MARKET_DIR / f"{code}.parquet").touch()
    monkeypatch.setattr(up, "is_symbol_updated", lambda *a: False)
    monkeypatch.setattr(up, "update_single_symbol", lambda *a: (True, None))
    result = c.cold({"universe": env, "request_id": "test"}, lambda v: None)
    assert result["status"] == "partial"
    assert len(result["failures"]) == 2
    assert not up.UPDATE_LOCK_FILE.exists()


def test_cold_never_deletes_a_live_worker_lock(env, monkeypatch, tmp_path):
    from app.core import data_updater as up
    monkeypatch.setattr(up, "UPDATE_LOCK_FILE", tmp_path / "cold.lock")
    s.write(up.UPDATE_LOCK_FILE, {"pid": 12345, "owner": "active"})
    monkeypatch.setattr(s, "process_alive", lambda pid: True)
    assert c.cold({"universe": env}, lambda v: None)["status"] == "deferred"
    assert s.read(up.UPDATE_LOCK_FILE)["owner"] == "active"


def test_disclosure_cache_avoids_reextracting_pdf(env, monkeypatch):
    from app.disclosure_verification import service as ds
    monkeypatch.setattr(ds, "_fetch_cninfo_announcements", lambda *a, **k: [{"announcement_id": "123", "title": "Report", "pdf_url": "https://example.com/a.pdf"}])
    downloads = []
    monkeypatch.setattr(ds, "_download_pdf", lambda url: downloads.append(url) or b"pdf")
    monkeypatch.setattr(ds, "_extract_pdf_pages", lambda b: ["Text"])
    monkeypatch.setattr(ds, "_symbol_context", lambda symbol: {"keywords": []})
    first = c.disclosures({"universe": env}, lambda v: None)
    second = c.disclosures({"universe": env}, lambda v: None)
    assert first["status"] == second["status"] == "complete"
    assert len(downloads) == 1


def test_prepare_preserves_supplements_and_refuses_pending_result(env, monkeypatch, tmp_path):
    from app.agent_review import discussion as d, plans
    from app.portfolio.service import portfolio_service
    monkeypatch.setattr(d, "ROOT", tmp_path / "discussion")
    monkeypatch.setattr(d, "account_fingerprint", lambda: "fp")
    class Snapshot:
        def model_dump(self, **kwargs):
            return env["account"]
    monkeypatch.setattr(portfolio_service, "load_snapshot", lambda: Snapshot())
    monkeypatch.setattr(plans, "view", lambda: {})
    svc.run(executor=complete)
    svc.prepare_discussion()
    original = d.read(d.current("manifest.json"))
    context = d.read(d.current("context.json"))
    context["supplements"] = [{"retrieved_at": "old", "data": "original evidence"}]
    d.write(d.current("context.json"), context)
    svc.prepare_discussion()
    assert d.read(d.current("context.json"))["supplements"] == context["supplements"]
    assert d.read(d.current("manifest.json"))["context_version"] == original["context_version"] + 1
    d.write(d.current("response.json"), {"pending": True})
    with pytest.raises(ValueError, match="Pending"):
        svc.prepare_discussion()


def test_prepare_refuses_account_changes(env, monkeypatch):
    from app.portfolio.service import portfolio_service
    class Snapshot:
        def model_dump(self, **kwargs):
            return {"changed": True}
    svc.run(executor=complete)
    monkeypatch.setattr(portfolio_service, "load_snapshot", lambda: Snapshot())
    with pytest.raises(ValueError, match="Account has changed"):
        svc.prepare_discussion()


def test_due_backoff_and_dates(env):
    previous = {"status": "partial", "inputs": "a", "target_date": "2026-10-19", "finished_at": s.now().isoformat()}
    assert not svc.due("market", previous, "a", "2026-10-19")
    assert svc.due("market", previous, "a", "2026-10-20")
    previous["finished_at"] = (s.now() - timedelta(minutes=16)).isoformat()
    assert svc.due("market", previous, "a", "2026-10-19")


def test_atomic_write_retries_windows_sharing_violation(env, monkeypatch):
    real = s.os.replace
    calls = []
    def replace(source, target):
        calls.append(source)
        if len(calls) == 1:
            raise PermissionError("Temporary sharing violation")
        real(source, target)
    monkeypatch.setattr(s.os, "replace", replace)
    s.write(s.ROOT / "sample.json", {"value": 1})
    assert s.read(s.ROOT / "sample.json") == {"value": 1}
    assert len(calls) == 2


def test_worker_rejects_accidental_model_calls(env, monkeypatch):
    from openai.resources.chat.completions import Completions, AsyncCompletions
    from openai.resources.responses import Responses, AsyncResponses
    for cls in [Completions, AsyncCompletions, Responses, AsyncResponses]:
        monkeypatch.setattr(cls, "create", lambda *a, **k: pytest.fail("Model request escaped guard"))
    monkeypatch.setitem(c.STAGES, "market", lambda *args: Completions.create(None))
    s.write(s.ROOT / "worker_request.json", {})
    svc.worker("market")
    result = s.read(s.ROOT / "worker_result.json")
    assert result["status"] == "failed"
    assert "prohibited" in result["reason"]


def test_account_identity_ignores_save_metadata_not_financial_changes(env):
    old = env["account"]
    new = deepcopy(old)
    new["snapshot_id"] = "resaved"
    new["snapshot_time"] = "later"
    new["positions"][0]["semantic_classification_confirmed_at"] = "later"
    assert svc.account_identity(old) == svc.account_identity(new)
    new["positions"][0]["quantity"] += 100
    assert svc.account_identity(old) != svc.account_identity(new)


def test_data_collectors_import_without_llm_key(monkeypatch):
    from app.ai import llm_client
    monkeypatch.setattr(llm_client, "client", None)
    monkeypatch.setattr(llm_client, "API_KEY", "")
    monkeypatch.delenv("STOCK_PILOT_DATA_ONLY", raising=False)
    with pytest.raises(RuntimeError, match="not configured"):
        llm_client._get_client()
    monkeypatch.setenv("STOCK_PILOT_DATA_ONLY", "1")
    with pytest.raises(RuntimeError, match="prohibited"):
        llm_client._get_client()


def test_atomic_parquet_keeps_previous_data_on_write_error(tmp_path, monkeypatch):
    from app.core import data_updater as up
    path = tmp_path / "sh.603259.parquet"
    old = pd.DataFrame({"date": ["2026-10-19"], "close": [100]})
    up.write_market_history(old, path)
    def failed(*args, **kwargs):
        raise OSError("Disk full")
    monkeypatch.setattr(pd.DataFrame, "to_parquet", failed)
    with pytest.raises(OSError):
        up.write_market_history(pd.DataFrame({"close": [200]}), path)
    assert pd.read_parquet(path)["close"].iloc[0] == 100
    assert not list(tmp_path.glob("*.tmp-*"))
