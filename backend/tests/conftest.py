import pytest


@pytest.fixture(autouse=True)
def isolate_task_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCK_PILOT_AUTO_DATA_SYNC", "0")
    from app.agent_review import runtime
    from app.agent_review import plans
    monkeypatch.setattr(plans, "ROOT", tmp_path / "plans")
    monkeypatch.setattr(runtime, "PATH", tmp_path / "task_runtime.json")
    monkeypatch.setattr(runtime, "_owner", None)
    monkeypatch.setattr(runtime, "_state", None)
