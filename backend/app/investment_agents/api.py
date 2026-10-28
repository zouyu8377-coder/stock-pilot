from urllib.parse import urlparse

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app.investment_agents import account_updates, data_agent, service, store as s
from app.investment_agents.schemas import AccountImport, Confirm, SettingsUpdate, Start
from app.data_sync import storage as ds


def local_only(request: Request):
    if request.client and request.client.host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(403, "真实账户与本机模型接口仅限本机使用")
    host = urlparse("//" + request.headers.get("host", "")).hostname
    permitted = {"127.0.0.1", "localhost", "::1"}
    if request.client and request.client.host == "testclient":
        permitted.add("testserver")
    if host not in permitted:
        raise HTTPException(403, "拒绝非本机Host，防止DNS重绑定访问")
    origin = request.headers.get("origin")
    if origin and urlparse(origin).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise HTTPException(403, "拒绝非本机网页发起账户或模型操作")


router = APIRouter(prefix="/api/investment-agents", tags=["investment-agents"], dependencies=[Depends(local_only)])


def call(fn, *args):
    try:
        return {"data": fn(*args)}
    except (ValueError, BlockingIOError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("")
def status():
    return call(lambda: {**service.status(), "account_fingerprint": data_agent.fingerprint()})


@router.post("/runs", status_code=202)
def start(body: Start):
    return call(service.start, body)


@router.get("/assistant-status")
def assistant_status():
    from app.investment_agents import health
    return call(health.status)


@router.get("/runs/{run_id}")
def get(run_id: str):
    return call(lambda: service.summary(s.load(run_id)))


@router.get("/history")
def history():
    return {"data": list(reversed(s.memories()["results"][-20:]))}


@router.post("/runs/{run_id}/cancel")
def cancel(run_id: str):
    return call(service.cancel, run_id)


@router.post("/runs/{run_id}/confirm")
def confirm(run_id: str, body: Confirm):
    return call(service.confirm, run_id, body.digest)


@router.get("/runs/{run_id}/evidence/{ref}")
def evidence(run_id: str, ref: str):
    return call(service.evidence, run_id, ref)


@router.get("/documents/{symbol}/{announcement_id}")
def document(symbol: str, announcement_id: str):
    if not re.fullmatch(r"\d{6}", symbol) or not re.fullmatch(r"\d{1,30}", announcement_id):
        raise HTTPException(422, "文件编号无效")
    target = ds.ROOT / "documents" / f"{symbol}-{announcement_id}.pdf"
    if not target.exists():
        raise HTTPException(404, "本地未保存该公告全文")
    return FileResponse(target, media_type="application/pdf", filename=target.name)


@router.put("/settings")
def settings(body: SettingsUpdate):
    with s.LOCK:
        s.write(s.ROOT / "settings.json", body.model_dump())
    return {"data": s.settings()}


@router.post("/account-import")
def account_import(body: AccountImport):
    return call(account_updates.apply, body)


@router.post("/account-import/{update_id}/undo")
def undo(update_id: str):
    return call(account_updates.undo, update_id)
