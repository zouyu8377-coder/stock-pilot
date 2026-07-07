from __future__ import annotations

from typing import Any


IPO_SUBSCRIPTION_REGISTRY: dict[str, dict[str, Any]] = {
    "001399": {
        "symbol": "001399",
        "name": "惠科股份",
        "asset_type": "ipo_subscription",
        "ipo_status": "subscribed",
        "issue_price": 10.12,
        "exchange": "SZSE",
        "industry": "DISPLAY_PANEL",
        "area": "广东",
        "list_date": "2026-06-17",
        "directions": ["DISPLAY_PANEL", "SEMICONDUCTOR_EQUIPMENT"],
        "risk_flags": ["HIGH_VOLATILITY"],
        "note": "IPO subscription registry entry; market quote/history may be unavailable until listing data is populated.",
    },
    "001248": {
        "symbol": "001248",
        "name": "华润新能源",
        "asset_type": "ipo_subscription",
        "ipo_status": "subscribed",
        "issue_price": 10.11,
        "exchange": "SZSE",
        "industry": "GREEN_POWER",
        "area": "香港",
        "list_date": None,
        "directions": ["GREEN_POWER"],
        "risk_flags": ["HIGH_VOLATILITY"],
        "note": "IPO subscription registry entry; market quote/history may be unavailable until listing data is populated.",
    },
}


def normalize_symbol(symbol: str) -> str:
    value = str(symbol or "").split(".", 1)[0].strip().upper()
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits[:6].zfill(6) if digits else value


def get_ipo_entry(symbol: str) -> dict[str, Any] | None:
    return IPO_SUBSCRIPTION_REGISTRY.get(normalize_symbol(symbol))


def search_ipo_entries(query: str, limit: int = 8) -> list[dict[str, Any]]:
    term = str(query or "").strip().upper()
    if not term:
        return []
    result: list[dict[str, Any]] = []
    for entry in IPO_SUBSCRIPTION_REGISTRY.values():
        haystack = f"{entry['symbol']} {entry['name']} {entry.get('industry') or ''}".upper()
        if term in haystack:
            result.append(entry)
        if len(result) >= limit:
            break
    return result
