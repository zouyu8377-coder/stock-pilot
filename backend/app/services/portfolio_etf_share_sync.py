from __future__ import annotations

import logging
from typing import Any, Iterable

from app.data_sources.akshare_etf_share import compact_fund_code, infer_exchange
from app.services.etf_share_service import EtfShareUpdateResult, etf_share_service


logger = logging.getLogger(__name__)


def _position_items(snapshot_or_payload: Any) -> Iterable[Any]:
    if snapshot_or_payload is None:
        return []
    if isinstance(snapshot_or_payload, dict):
        return snapshot_or_payload.get("positions") or []
    return getattr(snapshot_or_payload, "positions", []) or []


def _position_value(position: Any, key: str, default: Any = None) -> Any:
    if isinstance(position, dict):
        return position.get(key, default)
    return getattr(position, key, default)


def current_etf_symbols(snapshot_or_payload: Any) -> tuple[list[str], dict[str, str]]:
    codes: list[str] = []
    names: dict[str, str] = {}
    for position in _position_items(snapshot_or_payload):
        code = compact_fund_code(str(_position_value(position, "symbol", "")))
        if infer_exchange(code) == "UNKNOWN":
            continue
        codes.append(code)
        name = str(_position_value(position, "name", "") or "").strip()
        if name:
            names[code] = name
    return sorted(set(codes)), names


def new_etf_symbols(previous_snapshot: Any, current_snapshot_or_payload: Any) -> tuple[list[str], dict[str, str]]:
    previous, _ = current_etf_symbols(previous_snapshot)
    current, names = current_etf_symbols(current_snapshot_or_payload)
    previous_set = set(previous)
    return [code for code in current if code not in previous_set], names


def sync_new_etf_share_data(previous_snapshot: Any, current_snapshot_or_payload: Any) -> list[EtfShareUpdateResult]:
    codes, names = new_etf_symbols(previous_snapshot, current_snapshot_or_payload)
    if not codes:
        return []
    try:
        return etf_share_service.update_many(codes, names=names, force=True)
    except Exception as exc:
        logger.warning("Immediate ETF share sync failed: %s", exc)
        return [
            EtfShareUpdateResult(
                fund_code=code,
                fund_name=names.get(code, ""),
                exchange=infer_exchange(code),
                reason=str(exc)[:240],
            )
            for code in codes
        ]
