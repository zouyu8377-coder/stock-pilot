from fastapi import APIRouter, HTTPException, Query

from app.rotation.service import (
    build_rotation_bundle,
    get_rotation_bundle,
    get_sector_history,
    get_sector_research,
    load_rotation_status,
    load_universe,
)

router = APIRouter()


@router.get("/rotation/summary")
def rotation_summary(force: bool = Query(False)):
    return {"success": True, "data": get_rotation_bundle(force=force)}


@router.get("/rotation/sectors")
def rotation_sectors(force: bool = Query(False), category: str | None = Query(None)):
    bundle = get_rotation_bundle(force=force)
    sectors = bundle.get("sectors", [])
    if category:
        sectors = [item for item in sectors if item.get("category") == category]
    return {"success": True, "items": sectors}


@router.get("/rotation/sectors/{sector_id}")
def rotation_sector_detail(sector_id: str):
    detail = get_sector_research(sector_id)
    if not detail:
        raise HTTPException(status_code=404, detail="sector not found")
    return {"success": True, "data": detail}


@router.get("/rotation/history/{sector_id}")
def rotation_sector_history(sector_id: str):
    return {"success": True, "items": get_sector_history(sector_id)}


@router.get("/rotation/universe")
def rotation_universe():
    return {"success": True, "data": load_universe()}


@router.get("/rotation/status")
def rotation_status():
    return {"success": True, "data": load_rotation_status()}


@router.post("/rotation/refresh")
def rotation_refresh():
    return {"success": True, "data": build_rotation_bundle()}
