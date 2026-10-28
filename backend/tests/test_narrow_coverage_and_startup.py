from datetime import datetime, timedelta

import pandas as pd

from app.data_sync import collectors, references, startup, storage as s, service


def test_overseas_observation_respects_session_and_not_china_day():
    now = datetime.fromisoformat('2026-10-28T09:00:00+08:00')
    item = {"market": "overseas", "price": 100, "observed_at": '2026-10-27T20:00:00+00:00',
            "exchange_timezone": "America/New_York", "session_start": '2026-10-27T13:30:00+00:00', "session_end": '2026-10-27T20:00:00+00:00'}
    assert references.observation_fresh(item, now, '2026-10-28')
    assert not references.observation_fresh({**item, 'observed_at': '2026-10-24T20:00:00+00:00'}, now, '2026-10-28')
    live = datetime.fromisoformat('2026-10-27T19:00:00+00:00')
    assert not references.observation_fresh({**item, 'observed_at': '2026-10-27T18:00:00+00:00'}, live, '2026-10-27')
    assert not references.observation_fresh({**item, 'observed_at': '2026-10-29T20:00:00+00:00'}, now, '2026-10-28')


def test_reference_collection_records_failures_and_explicit_proxies(tmp_path, monkeypatch):
    from app.overseas_tech_chain import service as overseas
    from app.collector.history.base_market_provider import BaseMarketProvider
    monkeypatch.setattr(s, 'ROOT', tmp_path)
    monkeypatch.setattr(s, 'now', lambda: datetime.fromisoformat('2026-10-28T09:00:00+08:00'))
    monkeypatch.setattr(BaseMarketProvider, 'get_daily_history', lambda *a, **k: pd.DataFrame({'date': ['2026-10-27'], 'close': [10]}))
    def fetch(symbol):
        if symbol == 'DX-Y.NYB':
            raise TimeoutError('source unavailable')
        stamp = int(datetime.fromisoformat('2026-10-27T20:00:00+00:00').timestamp())
        return {'chart': {'result': [{'timestamp': [stamp - 86400, stamp], 'indicators': {'quote': [{'close': [99, 100]}]},
                                      'meta': {'regularMarketTime': stamp, 'regularMarketPrice': 100}}]}}
    monkeypatch.setattr(overseas, 'fetch_yahoo_chart', fetch)
    result = references.collect({'target_date': '2026-10-27'}, lambda v: None)
    assert result['status'] == 'partial'
    assert len(result['items']) == 8
    assert result['failures'][0]['symbol'] == 'DX-Y.NYB'
    assert next(item for item in result['items'] if item['symbol'] == 'sh.512400')['kind'] == 'etf_proxy'


def test_backfill_has_batch_limit_and_resumes_without_model(tmp_path, monkeypatch):
    from app.core import data_updater as up, etf_data_updater as etf
    monkeypatch.setattr(s, 'ROOT', tmp_path / 'sync')
    stocks = tmp_path / 'stocks.parquet'
    pd.DataFrame({'ts_code': [f'{600000+i}.SH' for i in range(201)]}).to_parquet(stocks)
    monkeypatch.setattr(up, 'METADATA_FILE', stocks)
    monkeypatch.setattr(etf, 'ETF_META_FILE', tmp_path / 'missing.parquet')
    batches = []
    def cold(request, progress):
        batch = request['universe']['cold']
        batches.append(batch)
        value = {'items': [{'symbol': code, 'as_of': request['target_date']} for code in batch], 'failures': [], 'status': 'complete'}
        progress(value)
        return value
    monkeypatch.setattr(collectors, 'cold', cold)
    request = {'target_date': '2026-10-28', 'universe': {}}
    first = collectors.backfill(request, lambda v: None)
    assert first['status'] == 'partial' and first['remaining_count'] == 1
    second = collectors.backfill(request, lambda v: None)
    assert second['status'] == 'complete'
    assert [len(batch) for batch in batches] == [200, 1]
    assert not set(batches[0]) & set(batches[1])


def test_startup_launch_is_model_free_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(s, 'ROOT', tmp_path)
    launches = []
    class Process:
        pid = 12345
    def popen(argv, **kwargs):
        launches.append((argv, kwargs))
        return Process()
    monkeypatch.setattr(startup.subprocess, 'Popen', popen)
    monkeypatch.setattr(s, 'process_alive', lambda pid: True)
    first = startup.launch()
    assert startup.launch() == first
    assert len(launches) == 1
    assert 'sync_data.py' in launches[0][0][-1]
    assert launches[0][1]['env']['STOCK_PILOT_DATA_ONLY'] == '1'
    assert first['model_calls'] == 0


def test_tracked_analysis_skips_full_market_backfill(tmp_path, monkeypatch):
    monkeypatch.setattr(s, 'ROOT', tmp_path)
    monkeypatch.setattr(collectors, 'universe', lambda: {'tracked': ['600000'], 'stocks': ['600000'], 'cold': ['600000'], 'account': {'positions': []}})
    called = []
    def execute(name, request, timeout):
        called.append(name)
        return {'status': 'complete'}
    service.run(scope='tracked', executor=execute)
    assert 'references' in called and 'backfill' not in called
