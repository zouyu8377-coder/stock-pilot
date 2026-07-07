from types import SimpleNamespace

from app.core import data_updater


class _Rows:
    error_code = "0"
    error_msg = ""

    def __init__(self):
        self._done = False

    def next(self):
        if self._done:
            return False
        self._done = True
        return True

    def get_row_data(self):
        return [
            "2026-06-11",
            "10",
            "10.5",
            "9.8",
            "10.2",
            "1000",
            "10200",
            "1.2",
            "2.0",
        ]


def test_fetch_increment_reconnects_after_broken_session(monkeypatch):
    calls = {"login": 0, "query": 0, "logout": 0}

    def login():
        calls["login"] += 1
        return SimpleNamespace(error_code="0", error_msg="")

    def query(**_kwargs):
        calls["query"] += 1
        if calls["query"] == 1:
            raise ConnectionResetError(10054, "connection reset")
        return _Rows()

    def logout():
        calls["logout"] += 1

    monkeypatch.setattr(data_updater.bs, "login", login)
    monkeypatch.setattr(data_updater.bs, "query_history_k_data_plus", query)
    monkeypatch.setattr(data_updater.bs, "logout", logout)
    monkeypatch.setattr(data_updater.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(data_updater.socket, "setdefaulttimeout", lambda _seconds: None)
    monkeypatch.setattr(data_updater, "_BAOSTOCK_LOGGED_IN", False)

    result = data_updater.fetch_increment("sh.600000", "2026-06-10")

    assert result is not None
    assert len(result) == 1
    assert calls["query"] == 2
    assert calls["login"] == 2
    assert calls["logout"] == 1


def test_market_files_keep_required_benchmark_when_filtering(tmp_path, monkeypatch):
    for name in ("sh.000300.parquet", "sh.600000.parquet", "sh.600001.parquet"):
        (tmp_path / name).touch()
    monkeypatch.setattr(data_updater, "BASE_MARKET_DIR", tmp_path)

    files = data_updater._market_files({"sh.600000"})

    assert [path.name for path in files] == ["sh.000300.parquet", "sh.600000.parquet"]
