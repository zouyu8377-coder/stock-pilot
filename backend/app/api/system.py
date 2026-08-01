from fastapi import APIRouter

from app.core.data_updater import get_last_trading_date, load_update_status
from app.core.etf_data_updater import load_etf_update_status
from app.rotation.service import load_rotation_status

router = APIRouter()


def _shape_status(status: dict, target_date: str) -> dict:
    total = int(status.get("total_symbols") or 0)
    completed = int(status.get("completed_count") or 0)
    failed = int(status.get("failed_count") or 0)
    remaining = status.get("remaining_count")
    if remaining is None and total:
        remaining = max(total - completed, 0)
    progress = round(completed / total * 100, 2) if total else 0
    return {
        "status": status.get("status", "unknown"),
        "provider": status.get("provider", "unknown"),
        "target_date": status.get("target_date") or target_date,
        "last_trading_date": status.get("last_trading_date"),
        "completed_count": completed,
        "failed_count": failed,
        "stale_count": int(status.get("stale_count") or 0),
        "total_symbols": total,
        "remaining_count": remaining or 0,
        "processed_count": int(status.get("processed_count") or 0),
        "current_symbol": status.get("current_symbol"),
        "progress": progress,
        "updated_at": status.get("updated_at"),
        "failure_reasons": status.get("failure_reasons", {}),
        "phase": status.get("phase"),
        "core_total": int(status.get("core_total") or 0),
        "core_completed": int(status.get("core_completed") or 0),
        "core_failed": int(status.get("core_failed") or 0),
        "core_status": status.get("core_status"),
        "core_last_trading_date": status.get("core_last_trading_date"),
        "market_total": int(status.get("market_total") or 0),
        "market_processed": int(status.get("market_processed") or 0),
        "deferred_reason": status.get("deferred_reason"),
        "average_symbol_seconds": status.get("average_symbol_seconds"),
    }


@router.get("/system/cold-data-status")
def cold_data_status():
    status = load_update_status()
    etf_status = load_etf_update_status()
    rotation_status = load_rotation_status()
    target_date = status.get("target_date") or get_last_trading_date().isoformat()
    shaped = _shape_status(status, target_date)
    etf_shaped = _shape_status(etf_status, target_date)
    rotation_shaped = _shape_status(rotation_status, rotation_status.get("target_date") or target_date)

    return {
        **shaped,
        "components": {
            "stock": shaped,
            "etf": etf_shaped,
            "rotation": rotation_shaped,
        },
    }
