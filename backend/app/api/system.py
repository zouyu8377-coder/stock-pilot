from fastapi import APIRouter

from app.core.data_updater import get_last_trading_date, load_update_status

router = APIRouter()


@router.get("/system/cold-data-status")
def cold_data_status():
    status = load_update_status()
    target_date = status.get("target_date") or get_last_trading_date().isoformat()
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
        "target_date": target_date,
        "last_trading_date": status.get("last_trading_date"),
        "completed_count": completed,
        "failed_count": failed,
        "total_symbols": total,
        "remaining_count": remaining or 0,
        "processed_count": int(status.get("processed_count") or 0),
        "current_symbol": status.get("current_symbol"),
        "progress": progress,
        "updated_at": status.get("updated_at"),
        "failure_reasons": status.get("failure_reasons", {}),
    }
