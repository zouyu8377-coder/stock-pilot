from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agent_review.service import _call_model, _extract_json, _model_name
from app.facts.disclosure_service import get_disclosure_facts
from app.portfolio import portfolio_service
from app.portfolio.schemas import PortfolioPositionInput, PortfolioSnapshotInput
from app.portfolio.service import _sync_legacy_fields
from app.theme_evidence.service import load_theme_evidence_registry


DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "ai_direction_classification" / "latest.json"
MAX_ANNOUNCEMENTS = 8
MAX_POSITIONS = 24
BUILTIN_DIRECTIONS = {"EV_AUTOMOTIVE"}


def _compact_symbol(symbol: str) -> str:
    return str(symbol or "").split(".", 1)[0].strip().zfill(6)


def _read() -> dict[str, Any]:
    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"items": [], "generated_at": None, "status": "not_run"}


def _write(payload: dict[str, Any]) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = DATA_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(DATA_PATH)


def get_direction_classifications() -> dict[str, Any]:
    payload = _read()
    return {
        **payload,
        "by_symbol": {
            _compact_symbol(item.get("symbol", "")): item
            for item in payload.get("items", [])
            if item.get("symbol")
        },
    }


def sync_cached_direction_classifications() -> dict[str, Any]:
    """Reapply the latest validated AI classifications after a screenshot refresh."""
    payload = _read()
    if payload.get("status") != "completed" or not payload.get("items"):
        return {"updated_symbols": [], "updated_count": 0, "status": payload.get("status", "not_run")}
    result = _apply_to_portfolio(payload["items"], str(payload.get("model") or _model_name()))
    return {**result, "status": "completed"}


def _apply_to_portfolio(items: list[dict[str, Any]], model: str) -> dict[str, Any]:
    by_symbol = {_compact_symbol(item.get("symbol", "")): item for item in items}
    snapshot = portfolio_service.load_snapshot()
    now = datetime.now(timezone.utc)
    updated: list[str] = []
    positions: list[PortfolioPositionInput] = []
    for position in snapshot.positions:
        data = position.model_dump()
        result = by_symbol.get(_compact_symbol(position.symbol)) or {}
        directions = [str(value).strip().upper() for value in result.get("directions", []) if str(value).strip()]
        if float(result.get("confidence") or 0) >= 0.6 and directions:
            data["directions"] = directions
            _sync_legacy_fields(data)
            data["semantic_classification_status"] = "ai_classified"
            data["semantic_classification_source"] = f"ai_direction_classification:{model}"
            data["semantic_classification_confirmed_at"] = now
            updated.append(_compact_symbol(position.symbol))
        positions.append(PortfolioPositionInput(**data))
    if not updated:
        return {"updated_symbols": [], "updated_count": 0}
    snapshot.positions = positions
    snapshot.snapshot_id = f"portfolio_snapshot_{now.strftime('%Y%m%d%H%M%S%f')}"
    snapshot.snapshot_time = now
    portfolio_service.save_snapshot(PortfolioSnapshotInput(**snapshot.model_dump()))
    return {"updated_symbols": updated, "updated_count": len(updated)}


def _taxonomy() -> tuple[list[str], dict[str, list[str]]]:
    registry = load_theme_evidence_registry()
    directions: set[str] = set()
    themes: dict[str, list[str]] = {}
    for theme in registry.get("themes", []):
        theme_id = str(theme.get("theme_id") or "").strip()
        tags = [str(tag).strip().upper() for tag in [*(theme.get("theme_tags") or []), *(theme.get("candidate_tags") or [])] if str(tag).strip()]
        if theme_id:
            themes[theme_id] = tags
            directions.update(tags)
    directions.update(BUILTIN_DIRECTIONS)
    return sorted(directions), themes


def _public_profile(position: Any) -> dict[str, Any]:
    facts = get_disclosure_facts(position.symbol)
    data = facts.get("data") or {}
    announcements = [
        {"date": item.get("ann_date"), "title": item.get("title")}
        for item in (data.get("announcements") or [])[:MAX_ANNOUNCEMENTS]
        if item.get("title")
    ]
    return {
        "symbol": _compact_symbol(position.symbol),
        "name": position.name,
        "asset_type": position.asset_type,
        "official_announcement_index": announcements,
        "announcement_source": (facts.get("evidence") or [{}])[0].get("source") if facts.get("evidence") else None,
    }


def _validated_item(raw: dict[str, Any], profile: dict[str, Any], valid_directions: set[str], valid_theme_ids: set[str]) -> dict[str, Any]:
    directions = [str(value).strip().upper() for value in raw.get("directions", []) if str(value).strip().upper() in valid_directions][:4]
    theme_ids = [str(value).strip() for value in raw.get("theme_ids", []) if str(value).strip() in valid_theme_ids][:3]
    confidence = raw.get("confidence", 0)
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "symbol": profile["symbol"],
        "name": profile["name"],
        "directions": directions,
        "theme_ids": theme_ids,
        "role": str(raw.get("role") or "unclassified")[:40],
        "confidence": round(confidence, 2),
        "reason": str(raw.get("reason") or "模型未给出可审计的分类依据。").strip()[:160],
        "evidence_basis": [str(value).strip() for value in raw.get("evidence_basis", []) if str(value).strip()][:4],
        "needs_review": bool(raw.get("needs_review", not directions)),
        "source_scope": "仅发送证券代码、名称与公开公告索引；不发送数量、成本、盈亏或现金。",
    }


def classify_portfolio_directions() -> dict[str, Any]:
    state = portfolio_service.get_state()
    directions, themes = _taxonomy()
    profiles = [_public_profile(position) for position in state.snapshot.positions[:MAX_POSITIONS]]
    prompt = {
        "task": "对A股或ETF进行关联方向分类，供主题研究和证据索引使用，不输出投资建议。只能基于提供的公开公告索引与证券名称；不确定时标记needs_review。",
        "allowed_directions": directions,
        "allowed_theme_ids": list(themes),
        "profiles": profiles,
        "output": {
            "items": [{
                "symbol": "6位代码", "directions": ["仅可用allowed_directions"],
                "theme_ids": ["仅可用allowed_theme_ids"], "role": "产业链或ETF角色/不确定",
                "confidence": "0到1", "reason": "不超过80字", "evidence_basis": ["证券名称", "公告索引"], "needs_review": False,
            }],
        },
    }
    try:
        content, usage, _ = _call_model([
            {"role": "system", "content": "你是审计友好的证券关联方向分类器。只输出JSON；不推断未提供的主营、收入或订单事实，不提供买卖建议。"},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ])
        parsed = _extract_json(content)
        raw_by_symbol = {_compact_symbol(item.get("symbol", "")): item for item in parsed.get("items", []) if isinstance(item, dict)}
        items = [_validated_item(raw_by_symbol.get(profile["symbol"], {}), profile, set(directions), set(themes)) for profile in profiles]
        status = "completed"
        error = None
    except Exception as exc:
        # Preserve existing AI results on transient provider failure; dashboard can still use manual fallback.
        previous = _read()
        items = previous.get("items", [])
        usage = {}
        status = "failed"
        error = str(exc)[:240]
    apply_result = _apply_to_portfolio(items, _model_name()) if status == "completed" else {"updated_symbols": [], "updated_count": 0}
    payload = {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": _model_name(),
        "items": items,
        "usage": usage,
        "error": error,
        "portfolio_sync": apply_result,
        "boundary": "AI分类用于方向关联和研究优先级；公告索引不等于公告正文核验，不可单独证明经营Thesis。",
    }
    _write(payload)
    return get_direction_classifications()
