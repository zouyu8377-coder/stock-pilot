import sys

import pytest
from fastapi.testclient import TestClient

from app.agent_demo import service as s, tools
from app.agent_demo.schemas import AnalystReply, Start, ToolRequest
from app.demo_main import create_app


@pytest.fixture(autouse=True)
def isolated_demo(tmp_path, monkeypatch):
    monkeypatch.setattr(s, "ROOT", tmp_path / "demo")


def finish(run):
    for _ in range(25):
        if run["phase"] in {"awaiting_confirmation", "awaiting_external", *s.TERMINAL}:
            return run
        run = s.step(run["run_id"], run["revision"])
    pytest.fail("Demo did not reach a bounded stop")


@pytest.mark.parametrize("scenario", [v["id"] for v in tools.SCENARIOS])
def test_all_scenarios_end_at_human_gate(scenario):
    run = finish(s.start(Start(scenario=scenario)))
    assert run["phase"] == "awaiting_confirmation"
    assert run["confirmed_report"] is None
    assert run["model_calls"] == run["tokens"] == 0
    assert run["tool_calls"] <= s.LIMITS["tool_calls"]
    assert run["analyst_turns"] <= s.LIMITS["analyst_turns"]
    assert run["context"]["fingerprint"] == s.digest(run["context"]["payload"])
    ids = {e["id"] for e in run["context"]["payload"]["evidence"]}
    assert all(set(f["evidence_refs"]) <= ids for f in run["pending_report"]["report"]["findings"])
    assert all(e["data"]["synthetic"] for e in run["context"]["payload"]["evidence"])
    done = s.confirm(run["run_id"], run["revision"], run["preview_digest"])
    assert done["phase"] == "confirmed"
    assert done["confirmed_report"]["digest"] == run["preview_digest"]
    assert {p.parent.name for p in s.ROOT.rglob("*.json")} == {"demo"}


def test_no_manufactured_rework_for_sufficient_context():
    run = s.start(Start(scenario="sufficient"))
    assert run["tool_calls"] == 2
    result = finish(run)
    assert result["tool_calls"] == 2
    assert result["analyst_turns"] == 1
    assert result["repairs"] == 0


def test_version_rejection_is_visible_then_repaired():
    run = finish(s.start(Start(scenario="stale_handoff")))
    rejected = [e for e in run["events"] if e["kind"] == "rejected"]
    assert len(rejected) == 1
    assert "版本" in rejected[0]["detail"]
    assert run["repairs"] == 1
    assert run["pending_report"]["context_version"] == run["context"]["version"]


def test_conflict_gets_extra_evidence_and_changes_conclusion():
    run = finish(s.start(Start(scenario="conflicting_evidence")))
    assert run["tool_calls"] == 3
    assert any(e["kind"] == "hypothesis" for e in run["events"])
    assert "现金流下降" in run["pending_report"]["report"]["summary"]
    assert run["pending_report"]["report"]["findings"][0]["confidence"] == "low"


def test_permanent_failure_never_becomes_fake_market_success():
    run = finish(s.start(Start(scenario="unavailable")))
    assert sum(e["kind"] == "tool_failed" for e in run["events"]) == 2
    assert all(e["data"]["kind"] != "market" for e in run["context"]["payload"]["evidence"])
    assert "证据不足" in run["pending_report"]["report"]["summary"]
    assert all(e.get("tool") == "market" for e in run["events"] if e["kind"] == "tool_exhausted")


def test_unrelated_tool_failure_does_not_suppress_market_collection():
    run = s.start(Start())
    s.event(run, "collector", "analyst", "tool_exhausted", "test", "events unavailable", tool="events")
    reply = s.sample_reply(run)
    assert "market" in {request.tool for request in reply.requests}


def test_manual_prompt_includes_repair_feedback_and_budget():
    run = s.start(Start(mode="manual"))
    reply = s.sample_reply(run).model_dump()
    reply["context_fingerprint"] = "0" * 64
    run = s.submit(run["run_id"], run["revision"], AnalystReply.model_validate(reply))
    prompt = s.prompt(run["run_id"])
    assert "资料版本或指纹不匹配" in prompt
    assert '"repairs": 1' in prompt


@pytest.mark.parametrize("tool_request", [
    {"tool": "place_order", "symbols": ["600519"]},
    {"tool": "market", "symbols": ["603259"]},
    {"tool": "market", "symbols": ["../../private"]},
    {"tool": "market", "symbols": ["600519", "600519"]},
])
def test_permissions(tool_request):
    with pytest.raises(ValueError):
        tools.check(ToolRequest(**tool_request, reason="permission test"))


def test_calculations_are_actual_deterministic_computation():
    run = s.start(Start())
    result = tools.collect(ToolRequest(tool="market", symbols=list(tools.SYMBOLS), reason="test"), run, 1)
    assert result["account_total"] == 332000
    assert result["rows"][0]["market_value"] == 120000
    assert result["rows"][0]["account_weight_pct"] == 36.14
    partial = tools.collect(ToolRequest(tool="market", symbols=["600519"], reason="test"), run, 1)
    assert partial["account_total"] is None
    assert partial["rows"][0]["account_weight_pct"] is None


def manual_reply(run, **changes):
    value = s.sample_reply(run).model_dump()
    value.update(changes)
    return AnalystReply.model_validate(value)


def test_manual_handoff_can_request_collect_and_return_without_model_call():
    run = s.start(Start(mode="manual"))
    assert run["phase"] == "awaiting_external"
    assert run["run_id"] in s.prompt(run["run_id"])
    reply = manual_reply(run)
    run = s.submit(run["run_id"], run["revision"], reply)
    while run["phase"] != "awaiting_external":
        run = s.step(run["run_id"], run["revision"])
    result = manual_reply(run, provider="external-human-assisted-test")
    run = s.submit(run["run_id"], run["revision"], result)
    run = s.step(run["run_id"], run["revision"])
    assert run["phase"] == "awaiting_confirmation"
    assert run["pending_report"]["provider"] == "external-human-assisted-test"
    assert run["model_calls"] == 0


@pytest.mark.parametrize("fault", ["version", "fingerprint", "reference", "high_confidence"])
def test_invalid_manual_reports_are_not_accepted(fault):
    run = s.start(Start(mode="manual", scenario="sufficient"))
    reply = manual_reply(run).model_dump()
    if fault == "version":
        reply["context_version"] = 1
    elif fault == "fingerprint":
        reply["context_fingerprint"] = "0" * 64
    elif fault == "reference":
        reply["report"]["findings"][0]["evidence_refs"] = ["MADE_UP"]
    else:
        reply["report"]["findings"][0]["confidence"] = "high"
    run = s.submit(run["run_id"], run["revision"], AnalystReply.model_validate(reply))
    if run["phase"] == "validating":
        run = s.step(run["run_id"], run["revision"])
    assert run["phase"] == "awaiting_external"
    assert run["pending_report"] is None
    assert run["events"][-1]["kind"] == "rejected"


def test_repair_loop_is_bounded():
    run = s.start(Start(mode="manual"))
    for _ in range(3):
        reply = manual_reply(run, context_fingerprint="0" * 64)
        run = s.submit(run["run_id"], run["revision"], reply)
    assert run["phase"] == "failed"


def test_duplicate_reply_does_not_repeat_tools():
    run = s.start(Start(mode="manual"))
    reply = manual_reply(run)
    run = s.submit(run["run_id"], run["revision"], reply)
    again = s.submit(run["run_id"], run["revision"], reply)
    assert again["analyst_turns"] == 1
    assert again["queue"] == run["queue"]
    value = reply.model_dump(); value["provider"] = "changed"
    with pytest.raises(ValueError, match="编号"):
        s.submit(again["run_id"], again["revision"], AnalystReply.model_validate(value))


def test_stale_revision_cannot_execute_twice():
    run = s.start(Start())
    s.step(run["run_id"], run["revision"])
    with pytest.raises(ValueError, match="会话已变化"):
        s.step(run["run_id"], run["revision"])


def test_confirmation_is_bound_to_preview_digest():
    run = finish(s.start(Start()))
    with pytest.raises(ValueError, match="确认内容"):
        s.confirm(run["run_id"], run["revision"], "0" * 64)
    assert s.load(run["run_id"])["confirmed_report"] is None


def test_cancel_discards_in_flight_tool_result(monkeypatch):
    run = s.start(Start())
    run = s.step(run["run_id"], run["revision"])
    original = tools.collect

    def cancelled(*args):
        current = s.load(run["run_id"])
        s.cancel(current["run_id"], current["revision"])
        return original(*args)

    monkeypatch.setattr(tools, "collect", cancelled)
    done = s.step(run["run_id"], run["revision"])
    assert done["phase"] == "cancelled"
    assert not done["context"]["payload"]["evidence"]


def test_interrupted_read_only_tool_can_resume():
    run = s.start(Start())
    run = s.step(run["run_id"], run["revision"])
    run.update(phase="collecting", lease_started=0)
    with s.LOCK:
        run = s.save(run)
    done = s.step(run["run_id"], run["revision"])
    assert any(e["kind"] == "recovered" for e in done["events"])
    assert len(done["context"]["payload"]["evidence"]) == 1


def test_public_quote_missing_or_redirect_does_not_fallback(monkeypatch):
    class Response:
        status_code = 302
        content = b""
        def raise_for_status(self):
            pass
    monkeypatch.setattr(tools.requests, "get", lambda *a, **k: Response())
    with pytest.raises(ValueError):
        tools.public_quotes(["600519"])


def test_demo_server_does_not_expose_private_routes_or_paths():
    client = TestClient(create_app())
    paths = client.get("/openapi.json").json()["paths"]
    assert not any("portfolio" in p or "review/discussion" in p for p in paths)
    assert client.get("/api/portfolio").status_code == 404
    assert client.get("/data/external_discussion/current/context.json").status_code == 404
    assert client.get("/api/demo/collaboration/runs/not-a-run").status_code == 409
    result = client.post("/api/demo/collaboration/runs", json={}).json()["data"]
    assert result["context"]["payload"]["account"]["synthetic"] is True
    assert client.post("/api/demo/collaboration/runs", json={"public_market": False, "secret_path": "x"}).status_code == 422


def test_isolated_entrypoint_does_not_import_private_or_llm_modules():
    # A fresh interpreter is necessary: pytest conftest imports legacy modules.
    import subprocess
    result = subprocess.run([sys.executable, "-c", "import app.demo_main,sys; assert not any(k in sys.modules for k in ['app.portfolio.service','app.ai.llm_client','app.agent_review.discussion','app.core.config'])"], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_session_persists_and_real_account_is_never_referenced(tmp_path):
    marker = tmp_path / "private-account.json"
    marker.write_text('{"cash": 1234567}', encoding="utf-8")
    run = finish(s.start(Start()))
    restored = s.load(run["run_id"])
    assert restored["context"] == run["context"]
    assert restored["context"]["payload"]["account"]["cash"] == 100000
    assert marker.read_text(encoding="utf-8") == '{"cash": 1234567}'
