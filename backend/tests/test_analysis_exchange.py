from copy import deepcopy
from datetime import timedelta

import pytest

from app.agent_review import exchange, service, outcomes
from test_agent_review import _context, _review


@pytest.fixture
def request_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(exchange, "EXCHANGE_DIR", tmp_path / "exchange")
    monkeypatch.setattr(exchange, "_account_fingerprint", lambda: "account-v1")
    monkeypatch.setattr(service, "REVIEW_DIR", tmp_path / "reviews")
    monkeypatch.setattr(service, "LATEST_PATH", tmp_path / "latest.json")
    monkeypatch.setattr(service, "build_daily_review_context", lambda force=False: _context())
    monkeypatch.setattr(service, "_operation_review_period", lambda: "daily")
    monkeypatch.setattr(outcomes, "build_learning_feedback", lambda: {})
    calls = []
    monkeypatch.setattr(service, "_sync_tasks", lambda payload: calls.append("tasks"))
    monkeypatch.setattr(service, "_register_outcomes", lambda *args: calls.append("outcomes"))
    from app.portfolio import dashboard_cache
    monkeypatch.setattr(dashboard_cache, "invalidate_dashboard_cache", lambda: None)
    exported = exchange.export_request()
    review = _review().model_dump(mode="json")
    review["headline"] = "账户处于亏损状态，先复核风险"
    result = {"request_id": exported["request_id"], "snapshot_fingerprint": exported["snapshot_fingerprint"], "review": review}
    return result, calls


def test_preview_confirmation_and_idempotence(request_bundle):
    result, calls = request_bundle
    with pytest.raises(ValueError, match="预览"):
        exchange.import_result(result, confirm=True)
    preview = exchange.import_result(result)
    assert preview["status"] == "preview"
    assert not service.LATEST_PATH.exists()
    assert calls == []
    saved = exchange.import_result(result, confirm=True)
    assert saved["status"] == "imported"
    assert calls == ["tasks", "outcomes"]
    assert exchange.import_result(result, confirm=True)["status"] == "already_imported"
    assert calls == ["tasks", "outcomes"]


@pytest.mark.parametrize("failure", ["fingerprint", "account", "expiry", "new_review", "unknown_evidence", "changed_preview", "path"])
def test_rejects_unsafe_or_stale_result(request_bundle, monkeypatch, failure):
    result, calls = request_bundle
    exchange.import_result(result)
    modified = deepcopy(result)
    if failure == "fingerprint": modified["snapshot_fingerprint"] = "wrong"
    if failure == "account": monkeypatch.setattr(exchange, "_account_fingerprint", lambda: "account-v2")
    if failure == "expiry":
        now = service._now()
        monkeypatch.setattr(service, "_now", lambda: now + timedelta(hours=5))
    if failure == "new_review": monkeypatch.setattr(exchange, "_latest_id", lambda: "new-analysis")
    if failure == "unknown_evidence": modified["review"]["opportunities"][0]["evidence_refs"] = ["invented:source"]
    if failure == "changed_preview": modified["review"]["summary"] = "edited"
    if failure == "path": modified["request_id"] = "../../outside"
    with pytest.raises(ValueError): exchange.import_result(modified, confirm=True)
    assert not service.LATEST_PATH.exists()
    assert calls == []
