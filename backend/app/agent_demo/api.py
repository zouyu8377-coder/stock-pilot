from fastapi import APIRouter, HTTPException

from app.agent_demo import service, tools
from app.agent_demo.schemas import Confirmation, Revision, Start, Submission

router = APIRouter(prefix="/api/demo/collaboration", tags=["isolated-collaboration-demo"])


def call(fn, *args):
    try:
        return {"success": True, "data": fn(*args)}
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except BlockingIOError as exc:
        raise HTTPException(409, "演示存储正在使用，请重试") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/scenarios")
def scenarios():
    return {"success": True, "data": {"scenarios": tools.SCENARIOS, "limits": service.LIMITS,
                                      "model_calls": 0, "symbols": tools.SYMBOLS}}


@router.post("/runs")
def create(body: Start):
    return call(service.start, body)


@router.get("/runs/{run_id}")
def get(run_id: str):
    return call(service.load, run_id)


@router.post("/runs/{run_id}/step")
def step(run_id: str, body: Revision):
    return call(service.step, run_id, body.revision)


@router.post("/runs/{run_id}/reply")
def reply(run_id: str, body: Submission):
    return call(service.submit, run_id, body.revision, body.reply)


@router.post("/runs/{run_id}/confirm")
def confirm(run_id: str, body: Confirmation):
    return call(service.confirm, run_id, body.revision, body.preview_digest)


@router.post("/runs/{run_id}/cancel")
def cancel(run_id: str, body: Revision):
    return call(service.cancel, run_id, body.revision)


@router.get("/runs/{run_id}/prompt")
def prompt(run_id: str):
    return call(lambda: {"prompt": service.prompt(run_id)})
