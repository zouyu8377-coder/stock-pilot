from __future__ import annotations

from app.portfolio import dashboard_cache


def test_dashboard_cache_reuses_payload_and_force_refreshes(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_cache, "CACHE_PATH", tmp_path / "dashboard.json")
    monkeypatch.setattr(dashboard_cache, "_source_paths", lambda: [])
    monkeypatch.setattr(dashboard_cache.settings, "DASHBOARD_CACHE_SECONDS", 300)

    calls = {"state": 0, "context": 0, "dashboard": 0}

    def state():
        calls["state"] += 1
        return {"state": calls["state"]}

    def context(*, mode, state):
        calls["context"] += 1
        return {"context": state["state"]}

    def dashboard(state, context, **kwargs):
        calls["dashboard"] += 1
        return {"value": state["state"], "context": context["context"]}

    monkeypatch.setattr(dashboard_cache.portfolio_service, "get_state", state)
    monkeypatch.setattr(dashboard_cache, "build_account_analysis_context", context)
    monkeypatch.setattr(dashboard_cache, "build_dashboard", dashboard)

    first = dashboard_cache.get_dashboard_bundle()
    second = dashboard_cache.get_dashboard_bundle()
    refreshed = dashboard_cache.get_dashboard_bundle(force=True)

    assert first["dashboard"]["value"] == 1
    assert second["cache"]["status"] == "hit"
    assert refreshed["dashboard"]["value"] == 2
    assert calls == {"state": 2, "context": 2, "dashboard": 2}
