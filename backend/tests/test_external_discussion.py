import pytest
from app.agent_review import discussion as d


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(d, "ROOT", tmp_path / "discussion")
    monkeypatch.setattr(d, "account_fingerprint", lambda: "account-a")
    monkeypatch.setattr(d, "collect", lambda: {"evidence": {"evidence_catalog": [{"evidence_ref": "quote:1"}]}, "records": d.state()})
    d.start(d.Start())
    return monkeypatch


def response(**kwargs):
    m = d.read(d.current("manifest.json"))
    return d.Result.model_validate({"schema_version": "1.0", "discussion_id": m["discussion_id"],
        "context_version": m["context_version"], "context_fingerprint": m["context_fingerprint"],
        "result_id": "r1", "provider": "test", "summary": "Discussion summary", "sources": [],
        "changes": [{"id": "task1", "operation": "add", "kind": "followup", "level": "account",
            "target": "account", "conclusion": "Check evidence", "reasoning": "Evidence is incomplete",
            "confidence": "low", "confidence_reason": "Missing disclosure", "trigger": "New report",
            "invalidation": "Thesis rejected", "evidence_refs": ["quote:1"]}], **kwargs})


def test_local_file_preview_confirm_idempotent(env):
    d.write(d.current("response.json"), response().model_dump())
    preview = d.status()["incoming"]
    assert preview["status"] == "preview"
    assert not d.state()["entities"]
    d.confirm(preview["digest"])
    d.confirm(preview["digest"])
    assert len(d.state()["results"]) == 1
    assert d.state()["entities"]["task1"]["active"]


def test_stale_account_rejects_even_after_preview(env):
    preview = d.stage(response())["incoming"]
    env.setattr(d, "account_fingerprint", lambda: "changed")
    assert d.status()["stale"]
    with pytest.raises(ValueError):
        d.confirm(preview["digest"])
    assert not d.state()["results"]


def test_content_changed_requires_new_preview(env):
    preview = d.stage(response())["incoming"]
    d.write(d.current("response.json"), response(summary="changed").model_dump())
    with pytest.raises(ValueError):
        d.confirm(preview["digest"])
    assert not d.state()["results"]


def test_continue_does_not_collect_or_archive(env):
    env.setattr(d, "collect", lambda: pytest.fail("unnecessary collection"))
    assert d.start(d.Start())["manifest"]["context_version"] == 1
    assert not (d.ROOT / "archive").exists()


def test_new_requires_unfinished_ack_and_archives(env):
    old = d.status()["manifest"]
    with pytest.raises(ValueError):
        d.start(d.Start(mode="new"))
    new = d.start(d.Start(mode="new", archive_unfinished=True))["manifest"]
    assert old["discussion_id"] != new["discussion_id"]
    assert list((d.ROOT / "archive").rglob("prompt.md"))


def test_refresh_invalidates_old_result(env):
    old = response()
    d.start(d.Start(mode="refresh"))
    with pytest.raises(ValueError, match="context_version"):
        d.stage(old)


def test_missing_refs_and_duplicate_ids_rejected(env):
    r = response()
    r.changes[0].evidence_refs = ["invented"]
    with pytest.raises(ValueError):
        d.stage(r)
    r = response()
    r.changes.append(r.changes[0])
    with pytest.raises(ValueError):
        d.stage(r)


def test_other_provider_cannot_overwrite(env):
    d.stage(response())
    with pytest.raises(ValueError, match="其他回传"):
        d.stage(response(result_id="r2", provider="other"))


def test_update_retract_and_empty_do_not_delete(env):
    d.confirm(d.stage(response())["incoming"]["digest"])
    d.start(d.Start(mode="refresh"))
    d.confirm(d.stage(response(result_id="r2", changes=[]))["incoming"]["digest"])
    assert d.state()["entities"]["task1"]["active"]
    d.start(d.Start(mode="refresh"))
    r = response(result_id="r3")
    r.changes[0].operation = "retract"
    d.confirm(d.stage(r)["incoming"]["digest"])
    assert not d.state()["entities"]["task1"]["active"]


def test_bad_json_is_visible_and_no_commit(env):
    d.write(d.current("response.json"), "{partial")
    assert d.status()["incoming"]["status"] == "invalid"
    assert not d.state()["results"]


def test_supplement_whitelist_and_version(env):
    from app.agent_review import plan_engine
    env.setattr(plan_engine, "collect", lambda tool, symbols: {"data": symbols})
    m = d.status()["manifest"]
    d.write(d.current("supplement.json"), {"discussion_id": m["discussion_id"], "context_version": 1, "tool": "market", "symbols": ["603259"]})
    assert d.supplement()["manifest"]["context_version"] == 2
    assert d.read(d.current("context.json"))["supplements"]
    assert not d.current("supplement.json").exists()


def test_file_too_large(env):
    d.write(d.current("response.json"), "x" * (d.MAX_BYTES + 1))
    assert d.status()["incoming"]["status"] == "invalid"


def test_new_install_defaults_to_no_internal_models():
    from app.agent_review.plan_engine import settings
    from app.agent_review import runtime
    assert settings()["external_only"] is True
    with pytest.raises(RuntimeError):
        runtime.model_attempt()
