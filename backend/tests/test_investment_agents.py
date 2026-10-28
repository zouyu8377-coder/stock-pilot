import json
from copy import deepcopy
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data_sync import storage as ds, service as sync, collectors
from app.investment_agents import account_updates, data_agent, providers, service, store as s
from app.investment_agents.api import router
from app.investment_agents.schemas import AccountImport, Start
from app.portfolio.schemas import PortfolioSnapshotInput


def reference_fixture(current):
    from app.data_sync.references import REQUIRED_GROUPS
    return [{"symbol": key, "name": key, "group": key, "market": "overseas", "price": 100,
             "observed_at": current.isoformat(), "status": "available"} for key in REQUIRED_GROUPS]


def test_business_assistant_health_uses_observation_dates_and_provider(env, monkeypatch):
    from app.investment_agents import health
    current = datetime.fromisoformat('2026-10-28T17:00:00+08:00')
    monkeypatch.setattr(ds, 'now', lambda: current)
    for name in health.SOURCE_NAMES:
        facts = {"items": [{"symbol": code, "daily": {"as_of": '2026-10-28', "close": 30, "is_stale": False}}
                            for code in ['601899', '600036']], "documents": [{"symbol": "601899"}], "coverage_count": 4500, "coverage_pct": 95}
        if name == 'references':
            facts['items'] = reference_fixture(current)
        ds.write(ds.ROOT / f'{name}.json', {"status": 'complete', "finished_at": current.isoformat(), "target_date": '2026-10-28', "data": facts})
    result = health.status()
    assert all(row['level'] == 'green' for row in result['assistants'].values())
    market = ds.read(ds.ROOT / 'market.json')
    market['data']['items'][0]['daily']['as_of'] = '2026-10-27'
    ds.write(ds.ROOT / 'market.json', market)
    result = health.status()
    assert result['assistants']['portfolio']['level'] == 'yellow'
    assert any('601899' in reason for reason in result['assistants']['portfolio']['reasons'])
    monkeypatch.setattr(providers, 'availability', lambda: {'codex': {'installed': False}, 'api': {'configured': True, 'enabled': False}})
    result = health.status()
    assert result['assistants']['dashboard']['level'] == 'red'
    assert result['assistants']['discovery']['level'] == 'red'
    assert result['assistants']['portfolio']['level'] == 'yellow'


def test_business_health_expired_source_and_missing_daily_are_not_green(env, monkeypatch):
    from app.investment_agents import health
    current = datetime.fromisoformat('2026-10-28T17:00:00+08:00')
    monkeypatch.setattr(ds, 'now', lambda: current)
    for name in health.SOURCE_NAMES:
        ds.write(ds.ROOT / f'{name}.json', {"status": 'complete', "finished_at": (current - timedelta(days=2)).isoformat(),
                                           "target_date": '2026-10-28', "data": {}})
    result = health.status()
    assert not any(row['ready'] for row in result['sources'])
    assert result['assistants']['portfolio']['level'] == 'red'
    assert result['assistants']['dashboard']['level'] == 'yellow'
    ds.write(ds.ROOT / 'trading_calendar.json', {'sessions': ['2025-01-03'], 'checked_on': '2025-01-03'})
    assert health._target(current) == '2026-10-28'


def test_business_health_endpoint_never_collects_or_calls_model(env, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Status must be read-only')
    monkeypatch.setattr(sync, 'run', forbidden)
    monkeypatch.setattr(providers, 'codex_call', forbidden)
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get('/api/investment-agents/assistant-status')
    assert response.status_code == 200
    assert set(response.json()['data']['assistants']) == {'dashboard', 'portfolio', 'discovery'}


def test_narrow_green_independent_of_incomplete_broad_coverage(env, monkeypatch):
    from app.investment_agents import health
    current = datetime.fromisoformat('2026-10-28T17:00:00+08:00')
    monkeypatch.setattr(ds, 'now', lambda: current)
    for name in health.SOURCE_NAMES:
        facts = {"items": [{"symbol": code, "daily": {"as_of": '2026-10-28', "close": 30, "is_stale": False}}
                            for code in ['601899', '600036']], "documents": [{"symbol": "601899"}], "coverage_count": 4500, "coverage_pct": 95}
        optional = name in {'disclosures', 'breadth'}
        if name == 'references':
            facts['items'] = reference_fixture(current)
        if optional:
            facts['failures'] = [{"reason": "one nonessential document unavailable"}]
        ds.write(ds.ROOT / f'{name}.json', {"status": 'partial' if optional else 'complete', "finished_at": current.isoformat(),
                                          "target_date": '2026-10-28', "data": facts})
    result = health.status()
    assert result['assistants']['portfolio']['label'] == '资料采集助手'
    assert result['assistants']['portfolio']['level'] == 'green'
    assert result['coverage']['narrow']['healthy']
    assert result['assistants']['dashboard']['level'] == 'yellow'
    breadth = ds.read(ds.ROOT / 'breadth.json')
    breadth['data'].update(coverage_count=18, coverage_pct=0.38)
    ds.write(ds.ROOT / 'breadth.json', breadth)
    result = health.status()
    assert result['assistants']['portfolio']['level'] == 'green'
    assert result['coverage']['broad']['coverage_pct'] == 0.38
    references = ds.read(ds.ROOT / 'references.json')
    references['data']['items'] = [item for item in references['data']['items'] if item['group'] != 'usd']
    ds.write(ds.ROOT / 'references.json', references)
    result = health.status()
    assert result['assistants']['portfolio']['level'] == 'yellow'
    assert result['coverage']['narrow']['missing_groups'] == ['美元指数']


def test_codex_desktop_discovery_without_path(tmp_path, monkeypatch):
    monkeypatch.setattr(providers.shutil, "which", lambda name: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    executable = tmp_path / "Programs" / "Codex" / "resources" / "codex.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    if providers.os.name == "nt":
        assert providers.codex_executable() == str(executable)
        executable.unlink()
    assert providers.codex_executable() is None


@pytest.fixture
def env(tmp_path, monkeypatch):
    from app.agent_review import discussion
    import app.portfolio.service as portfolio_module
    from app.portfolio.service import PortfolioService
    monkeypatch.setattr(s, "ROOT", tmp_path / "agents")
    monkeypatch.setattr(ds, "ROOT", tmp_path / "data_sync")
    monkeypatch.setattr(discussion, "ROOT", tmp_path / "discussion")
    portfolio = PortfolioService(tmp_path / "portfolio")
    monkeypatch.setattr(portfolio, "get_state", lambda: None)
    monkeypatch.setattr(portfolio_module, "portfolio_service", portfolio)
    portfolio.save_snapshot(PortfolioSnapshotInput(snapshot_time=s.now(), cash_available=10000, account_actual_total_cost=20000,
        positions=[{"symbol": "601899", "quantity": 100, "avg_cost": -2, "name": "test"},
                   {"symbol": "600036", "quantity": 0, "avg_cost": 0, "name": "watch"}]))
    def collected(**kwargs):
        bundle = {"account": data_agent.account(), "target_date": s.now().date().isoformat(), "boundaries": [], "sources": {
            "market": {"status": "complete", "finished_at": s.now().isoformat(), "target_date": s.now().date().isoformat(), "data": {"items": [
                {"symbol": "601899", "retrieved_at": s.now().isoformat(), "quote": {"price": 30, "is_stale": False}, "daily": {"close": 29, "is_stale": False}},
                {"symbol": "600036", "quote": {"price": 40, "is_stale": False}, "daily": {"close": 39, "is_stale": False}}]}},
            "disclosures": {"status": "partial", "data": {"documents": [{"symbol": "601899", "announcement_id": "123", "title": "年度报告",
                "pdf_url": "https://static.cninfo.com.cn/test.pdf", "selected_text": "现金流选段", "document_type": "annual_report"}], "failures": [{"reason": "missing quarterly report"}]}}}}
        s.write(ds.ROOT / "latest.json", bundle)
        return {"status": "partial"}
    collected()
    monkeypatch.setattr(sync, "run", collected)
    monkeypatch.setattr(providers, "availability", lambda: {"codex": {"installed": True}, "api": {"enabled": False, "configured": True}})
    return portfolio


def final(run, **kwargs):
    item = {"level": "account", "target": "账户", "action": "hold", "conclusion": "条件建议", "reasoning": "有来源的判断而非固定评分",
            "confidence": "medium", "confidence_reason": "资料不全", "trigger": "确认趋势", "invalidation": "经营恶化", "horizon": "一周", "evidence_refs": ["market:601899"]}
    return {"context_version": run["context_version"], "context_fingerprint": run["context_fingerprint"], "action": "final", "summary": "真实管道测试，模型响应为mock",
            "account_state": "attention", "requests": [], "findings": [item, {**item, "level": "symbol", "target": "601899"}], "unresolved": ["季报尚缺"], "lessons": ["避免依据单一参数行动"], "external_sources": [], **kwargs}


def caller(run_id, callback=None):
    def call(*args):
        if callback:
            callback()
        return final(s.load(run_id)), {"input_tokens": 10, "output_tokens": 100}
    return call


def test_real_pipeline_uses_account_sources_and_human_gate(env):
    run = service.start(Start(consent=True), launch=False)
    service.work(run["run_id"], caller(run["run_id"]))
    result = s.load(run["run_id"])
    assert result["status"] == "awaiting_confirmation", result.get("error")
    assert result["model_calls"] == 1
    assert result["data_summary"]["metrics"]["total_assets"] == 13000
    assert result["data_summary"]["metrics"]["account_pnl"] == -7000
    assert result["data_summary"]["positions"][1]["watchlist"]
    assert s.memories()["results"] == []
    before = data_agent.fingerprint()
    service.confirm(run["run_id"], result["report_digest"])
    service.confirm(run["run_id"], result["report_digest"])
    assert len(s.memories()["results"]) == 1
    assert data_agent.fingerprint() == before
    assert data_agent.build_context("next")["previous_results"][0]["lessons"]


def test_analysis_reuses_ready_narrow_context_while_broad_backfill_runs(env, monkeypatch):
    from app.investment_agents import health
    monkeypatch.setattr(sync, 'run', lambda **kwargs: (_ for _ in ()).throw(BlockingIOError('backfill')))
    monkeypatch.setattr(sync, 'load_status', lambda: {'status': 'running', 'stage': 'backfill'})
    monkeypatch.setattr(health, 'status', lambda: {'coverage': {'narrow': {'healthy': True}}})
    run = service.start(Start(consent=True), launch=False)
    service.work(run['run_id'], caller(run['run_id']))
    result = s.load(run['run_id'])
    assert result['status'] == 'awaiting_confirmation', result.get('error')
    assert any('重点资料已就绪' == row['title'] for row in result['events'])


def test_consent_and_expired_api_are_not_bypassed(env):
    with pytest.raises(ValueError, match="允许"):
        service.start(Start(), launch=False)
    with pytest.raises(ValueError, match="未配置或未启用"):
        service.start(Start(consent=True, provider="api"), launch=False)
    assert not s.read(s.ROOT / "current.json")


def test_budget_and_wrong_references_cannot_create_fake_success(env):
    run = service.start(Start(consent=True, max_model_calls=1), launch=False)
    def wrong(*args):
        value = final(s.load(run["run_id"]))
        value["findings"][0]["evidence_refs"] = ["invented"]
        return value, {}
    service.work(run["run_id"], wrong)
    result = s.load(run["run_id"])
    assert result["status"] == "failed"
    assert result["model_calls"] == 1
    assert result["report"] is None


def test_old_account_or_late_cancelled_result_never_reaches_preview(env):
    run = service.start(Start(consent=True), launch=False)
    service.work(run["run_id"], caller(run["run_id"], lambda: service.cancel(run["run_id"])))
    assert s.load(run["run_id"])["status"] == "cancelled"
    run = service.start(Start(consent=True), launch=False)
    def change():
        value = env.load_snapshot().model_dump()
        value["cash_available"] += 1
        env.save_snapshot(PortfolioSnapshotInput(**value))
    service.work(run["run_id"], caller(run["run_id"], change))
    assert s.load(run["run_id"])["status"] == "failed"
    assert s.load(run["run_id"])["report"] is None


def test_confirm_cannot_accept_changed_account(env):
    run = service.start(Start(consent=True), launch=False)
    service.work(run["run_id"], caller(run["run_id"]))
    value = env.load_snapshot().model_dump(); value["cash_available"] += 1
    env.save_snapshot(PortfolioSnapshotInput(**value))
    with pytest.raises(ValueError, match="账户已变化"):
        service.confirm(run["run_id"], s.load(run["run_id"])["report_digest"])


def test_agent2_can_request_agent1_then_reanalyze_new_evidence(env, monkeypatch):
    run = service.start(Start(consent=True), launch=False)
    calls = []
    def model(*args):
        current = s.load(run["run_id"])
        calls.append(current["context_version"])
        if len(calls) == 1:
            return final(current, action="request_evidence", findings=[], requests=[{"tool": "market", "symbols": ["601899"], "reason": "需更新价格"}]), {}
        return final(current), {}
    monkeypatch.setattr(data_agent, "collect_requested", lambda *a: ("market", {"status": "complete", "items": [
        {"symbol": "601899", "quote": {"price": 35, "is_stale": False}}]}, s.now().date().isoformat()))
    service.work(run["run_id"], model)
    result = s.load(run["run_id"])
    assert result["status"] == "awaiting_confirmation", result.get("error")
    assert result["tool_requests"] == 1
    assert calls[1] > calls[0]
    assert result["data_summary"]["metrics"]["total_assets"] == 13500


def import_body():
    return AccountImport(source_id="sample-source", observed_at=s.now().isoformat(), complete=True, expected_fingerprint=data_agent.fingerprint(),
        cash_available=9000, total_market_value=6000, total_assets=15000, positions=[{"symbol": "601899", "quantity": 200,
            "available_quantity": 100, "avg_cost": -3, "broker_screenshot_price": 30, "broker_screenshot_market_value": 6000}])


def test_verified_account_import_is_idempotent_audited_and_reversible(env):
    before = data_agent.fingerprint()
    cost_provenance = env.load_snapshot().account_actual_total_cost_confirmed_at
    body = import_body()
    applied = account_updates.apply(body)
    assert env.load_snapshot().positions[0].avg_cost == -3
    assert account_updates.apply(body)["id"] == applied["id"]
    assert len(account_updates.history()) == 1
    assert env.load_snapshot().positions[1].quantity == 0
    assert not env.load_snapshot().positions[0].confirmed_by_user
    assert env.load_snapshot().account_actual_total_cost_confirmed_at == cost_provenance
    account_updates.undo(applied["id"])
    assert data_agent.fingerprint() == before
    assert account_updates.history()[0]["status"] == "undone"


@pytest.mark.parametrize("fault", ["partial", "total", "row", "duplicate", "future", "stale", "fingerprint", "nan"])
def test_invalid_account_data_never_writes_holdings(env, fault):
    value = import_body().model_dump()
    if fault == "partial": value["complete"] = False
    if fault == "total": value["total_assets"] += 100
    if fault == "row": value["positions"][0]["quantity"] += 1
    if fault == "duplicate": value["positions"].append(deepcopy(value["positions"][0]))
    if fault == "future": value["observed_at"] = (s.now() + timedelta(days=1)).isoformat()
    if fault == "stale": value["observed_at"] = (s.now() - timedelta(days=2)).isoformat()
    if fault == "fingerprint": value["expected_fingerprint"] = "old"
    if fault == "nan": value["positions"][0]["avg_cost"] = float("nan")
    before = data_agent.fingerprint()
    with pytest.raises(ValueError): account_updates.apply(AccountImport(**value))
    assert data_agent.fingerprint() == before
    assert account_updates.history() == []


def test_undo_does_not_clobber_a_later_manual_edit(env):
    applied = account_updates.apply(import_body())
    value = env.load_snapshot().model_dump(); value["cash_available"] += 1
    env.save_snapshot(PortfolioSnapshotInput(**value))
    with pytest.raises(ValueError, match="其他账户变更"):
        account_updates.undo(applied["id"])


def test_complete_all_cash_account_is_supported(env):
    value = import_body().model_dump()
    value.update(positions=[], cash_available=15000, total_market_value=0, total_assets=15000)
    account_updates.apply(AccountImport(**value))
    assert all(p.quantity == 0 for p in env.load_snapshot().positions)


def test_source_document_selection_keeps_annual_and_periodic_reports():
    rows = [{"title": "普通公告"}, {"title": "2026年第三季度报告"}, {"title": "2025年年度报告摘要"},
            {"title": "2025年年度报告"}, {"title": "2026年半年度报告"}, {"title": "2024年年度报告"}]
    selected = collectors.select_documents(rows)
    assert len(selected) == 4
    assert any(row["title"] == "2025年年度报告" for row in selected)
    assert not any(row["title"] == "2024年年度报告" for row in selected)
    assert collectors.document_type("关于召开2025年年度报告业绩说明会的公告") == "announcement"
    assert collectors.document_type("2026年第三季度报告") == "periodic_report"


def test_financial_excerpt_prefers_key_figures_not_ir_and_accounting_footnotes():
    pages = ["[第1页]报告目录..................合并现金流量表", "[第10页]投资者关系活动与行业关键词",
             "[第5页]主要会计数据和财务指标 营业收入 经营活动产生的现金流量净额", "[第70页]合并现金流量表 经营现金流",
             "[第68页]合并利润表 营业成本"]
    text = collectors.financial_excerpt(pages)
    assert text.startswith("[第5页]")
    assert "第70页" in text
    assert "第68页" in text
    assert "投资者关系" not in text


def test_large_annual_pdf_failure_does_not_discard_quarterly_report(env, monkeypatch):
    from app.disclosure_verification import service as disclosure
    rows = [{"title": "2025年年度报告", "announcement_id": "1", "announced_at": "2026-04-01"},
            {"title": "2026年第三季度报告", "announcement_id": "2", "announced_at": "2026-10-25"}]
    monkeypatch.setattr(disclosure, "_fetch_cninfo_announcements", lambda *a, **kw: rows)
    def load(row, symbol):
        if row["announcement_id"] == "1": raise ValueError("PDF too large")
        return {**row, "symbol": symbol, "document_type": "periodic_report"}
    monkeypatch.setattr(collectors, "load_document", load)
    value = collectors.disclosures({"universe": {"stocks": ["601899"]}}, lambda *a: None)
    assert value["status"] == "partial"
    assert value["documents"][0]["announcement_id"] == "2"
    assert value["checked_symbols"][0]["annual_report_found"] is False
    assert value["checked_symbols"][0]["annual_index_candidate"] is True


def test_codex_output_contract_requires_every_field_and_disallows_extras():
    schema = providers.strict_schema()
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False


def test_api_rejects_remote_origins_and_unconsented_runs(env):
    app = FastAPI(); app.include_router(router)
    client = TestClient(app)
    assert client.get('/api/investment-agents', headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get('/api/investment-agents', headers={"Host": "evil.example"}).status_code == 403
    assert client.post('/api/investment-agents/runs', json={}).status_code == 409
    response = client.get('/api/investment-agents').json()["data"]
    assert "api_key" not in json.dumps(response)
    assert response["account_fingerprint"] == data_agent.fingerprint()


def test_worker_launch_failure_is_not_left_as_permanently_running(env, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("test process launch failure")
    monkeypatch.setattr(service.subprocess, "Popen", fail)
    with pytest.raises(ValueError, match="无法启动"):
        service.start(Start(consent=True))
    assert s.load(s.read(s.ROOT / "current.json")["run_id"])["status"] == "failed"


def test_confirmation_recovers_if_memory_committed_before_run_state(env):
    run = service.start(Start(consent=True), launch=False)
    service.work(run["run_id"], caller(run["run_id"]))
    preview = deepcopy(s.load(run["run_id"]))
    service.confirm(run["run_id"], preview["report_digest"])
    s.save(preview)
    assert service.confirm(run["run_id"], preview["report_digest"])["status"] == "confirmed"
    assert len(s.memories()["results"]) == 1


def test_provider_launch_uses_restricted_cli_and_no_api_key(env, monkeypatch, tmp_path):
    import io
    captured = {}
    def popen(argv, **kwargs):
        captured.update(argv=argv, env=kwargs["env"])
        output = argv[argv.index("--output-last-message") + 1]
        s.write(__import__("pathlib").Path(output), {"provider_test": True})
        class Process:
            stdin = io.StringIO()
            stdout = io.StringIO('{"type":"turn.completed","usage":{"input_tokens":4}}\n')
            returncode = 0
            def poll(self): return 0
            def wait(self, **kwargs): return 0
        return Process()
    monkeypatch.setattr(providers.shutil, "which", lambda name: "codex.exe")
    monkeypatch.setattr(providers.subprocess, "Popen", popen)
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-propagate")
    result, usage = providers.codex_call("test", tmp_path, s.settings(), lambda *a: None, lambda: False, 1)
    assert result == {"provider_test": True}
    assert usage["input_tokens"] == 4
    assert "OPENAI_API_KEY" not in captured["env"]
    assert captured["argv"][captured["argv"].index("--sandbox") + 1] == "read-only"
    assert "features.shell_tool=false" in captured["argv"]
    assert "features.multi_agent=false" in captured["argv"]
    assert "--dangerously-bypass-approvals-and-sandbox" not in captured["argv"]
