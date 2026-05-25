from __future__ import annotations

from app.collector.metadata_provider import metadata_provider
from app.external_drivers import build_external_driver_context
from app.facts.common import compact_symbol, to_ts_code
from app.portfolio.import_schemas import SymbolCandidate


KNOWN_SYMBOLS = {
    "601899": "紫金矿业",
    "002916": "深南电路",
    "002463": "沪电股份",
    "000657": "中钨高新",
    "159934": "黄金ETF",
    "159382": "创业板ETF",
}


def _with_driver(candidate: SymbolCandidate) -> SymbolCandidate:
    context = build_external_driver_context(candidate.symbol)
    candidate.external_driver_profile_id = context.profile_id
    candidate.external_driver_mapping_status = context.mapping_status
    return candidate


def resolve_symbol_or_name(symbol_text: str = "", name_text: str = "") -> tuple[str | None, str | None, str, list[SymbolCandidate], list[str]]:
    warnings: list[str] = []
    raw_symbol = (symbol_text or "").strip().upper()
    raw_name = (name_text or "").strip()
    candidates: list[SymbolCandidate] = []

    code = "".join(ch for ch in raw_symbol if ch.isdigit())
    if len(code) >= 6:
        code = code[:6]
        ts_code = to_ts_code(raw_symbol if "." in raw_symbol else code)
        meta = metadata_provider.get(compact_symbol(ts_code))
        name = (meta or {}).get("name") or KNOWN_SYMBOLS.get(compact_symbol(ts_code)) or raw_name
        candidate = _with_driver(SymbolCandidate(
            symbol=ts_code,
            name=name,
            industry=(meta or {}).get("industry"),
            area=(meta or {}).get("area"),
        ))
        candidates.append(candidate)
        if raw_name and name and raw_name not in name and name not in raw_name:
            warnings.append(f"识别代码 {raw_symbol} 对应 {name}，但截图名称为 {raw_name}，需要人工确认。")
            return ts_code, name, "conflict_requires_confirmation", candidates, warnings
        return ts_code, name, "exact_code_match", candidates, warnings

    if raw_name:
        for item in metadata_provider.search(raw_name, limit=8):
            candidate = _with_driver(SymbolCandidate(
                symbol=to_ts_code(item["symbol"]),
                name=item.get("name") or item["symbol"],
                industry=item.get("industry"),
                area=item.get("area"),
            ))
            candidates.append(candidate)
        if not candidates:
            for code_value, known_name in KNOWN_SYMBOLS.items():
                if raw_name in known_name or known_name in raw_name:
                    candidates.append(_with_driver(SymbolCandidate(symbol=to_ts_code(code_value), name=known_name)))
        if len(candidates) == 1:
            first = candidates[0]
            return first.symbol, first.name, "name_candidate_match", candidates, warnings
        if len(candidates) > 1:
            return None, raw_name, "name_candidate_match", candidates, ["名称匹配到多个候选标的，请选择标准代码。"]

    return None, raw_name or None, "unresolved", candidates, ["未能根据代码或名称匹配标准标的，请人工选择。"]

