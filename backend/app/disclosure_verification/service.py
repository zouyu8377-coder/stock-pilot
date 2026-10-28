from __future__ import annotations

import io
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import requests
from pypdf import PdfReader

from app.ai.research_engine import extract_json
from app.agent_review.service import _call_model
from app.core.config import settings
from app.disclosure_verification.freshness import annotate_verification
from app.theme_evidence import load_theme_evidence_registry


ROOT = Path(__file__).resolve().parents[2] / "data" / "disclosure_verification"
CNINFO_QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STATIC_ROOT = "https://static.cninfo.com.cn/"
RELEVANT_TITLE_TERMS = (
    "年度报告", "半年度报告", "季度报告", "业绩预告", "业绩快报",
    "投资者关系", "调研", "日常经营", "订单", "合同", "扩产", "产能",
    "项目投资", "风险提示", "异常波动",
)
GENERIC_EVIDENCE_TERMS = (
    "收入", "营收", "毛利率", "净利润", "订单", "产能", "客户", "认证",
    "产品", "业务", "需求", "价格", "成本", "同比", "环比",
)


def _call_disclosure_model(prompt: str) -> str:
    """Use the review model's non-streaming JSON contract for citation verification."""
    content, _, _ = _call_model([
        {
            "role": "system",
            "content": (
                "你是公告正文核验器。只输出JSON；只能引用用户提供的PDF正文，"
                "每个非not_found结论必须逐字复制一段原文短引。"
            ),
        },
        {"role": "user", "content": prompt},
    ])
    return content


def _compact_symbol(symbol: str) -> str:
    return str(symbol or "").split(".", 1)[0].strip().zfill(6)


def _cache_path(symbol: str) -> Path:
    return ROOT / f"{_compact_symbol(symbol)}.json"


def load_disclosure_verification(symbol: str) -> dict[str, Any] | None:
    path = _cache_path(symbol)
    if not path.exists():
        return None
    try:
        return annotate_verification(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None


def _cache_is_fresh(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    try:
        checked = datetime.fromisoformat(str(payload["index_checked_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return False
    return datetime.now(timezone.utc) - checked <= timedelta(minutes=settings.DISCLOSURE_INDEX_CHECK_MINUTES)


def _write_cache(symbol: str, payload: dict[str, Any]) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    path = _cache_path(symbol)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _announcement_ids(payload: dict[str, Any] | None) -> set[str]:
    if not payload:
        return set()
    if "processed_announcement_ids" in payload:
        return {str(value) for value in payload["processed_announcement_ids"] if value}
    # Legacy seen IDs included unread documents; only verified batches are processed.
    explicit = payload.get("processed_announcement_ids") or []
    documents = payload.get("documents") or []
    return {
        str(item)
        for item in [
            *explicit,
            *(document.get("announcement_id") for document in documents if isinstance(document, dict)),
        ]
        if item
    }


def _symbol_context(symbol: str) -> dict[str, Any]:
    compact = _compact_symbol(symbol)
    from app.direction_classification import get_direction_classifications

    ai_classification = get_direction_classifications().get("by_symbol", {}).get(compact) or {}
    ai_theme_ids = set(ai_classification.get("theme_ids") or [])
    from app.disclosure_verification.topics import business_questions
    from app.portfolio.service import portfolio_service
    position = next((p for p in portfolio_service.load_snapshot().positions if _compact_symbol(p.symbol) == compact), None)
    directions = (position.directions if position and position.directions else ai_classification.get("directions") or [])
    ai_questions = business_questions(directions)
    themes: list[dict[str, Any]] = []
    questions: list[str] = []
    invalid_conditions: list[str] = []
    keywords: set[str] = set(GENERIC_EVIDENCE_TERMS)
    for theme in load_theme_evidence_registry().get("themes", []):
        mapping = (theme.get("symbol_mappings") or {}).get(compact)
        is_ai_theme = str(theme.get("theme_id") or "") in ai_theme_ids
        if not mapping and not is_ai_theme:
            continue
        role = (mapping or {}).get("role_in_theme") or ai_classification.get("role") or "AI方向关联待核验"
        themes.append({
            "theme_id": theme.get("theme_id"),
            "theme_name": theme.get("theme_name"),
            "role_in_theme": role,
        })
        questions.extend((mapping or {}).get("open_questions") or [])
        if is_ai_theme and not mapping and not ai_questions:
            direction_text = " / ".join(ai_classification.get("directions") or []) or str(theme.get("theme_name") or "该方向")
            questions.extend([
                f"公告正文是否支持其主营、产品或服务与{direction_text}方向相关？",
                "最新定期报告是否披露收入、利润、订单、研发或商业化等可追溯经营事实？",
            ])
        if (mapping or {}).get("invalid_condition"):
            invalid_conditions.append(mapping["invalid_condition"])
        elif is_ai_theme:
            invalid_conditions.append("AI方向分类与公告正文或主营披露不一致，或缺少可引用的经营事实。")
        for text in [
            theme.get("theme_name"),
            role,
            *(mapping or {}).get("open_questions", []),
            *(ai_classification.get("directions") or []),
        ]:
            keywords.update(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,12}", str(text or "")))
    questions = [*ai_questions, *questions]
    if not questions:
        questions = ["最新经营披露是否支持收入、利润及主营业务的持续性？", "是否存在影响持有逻辑的重大风险或政策变化？"]
    return {
        "symbol": compact,
        "themes": themes,
        "questions": list(dict.fromkeys(questions))[:6],
        "invalid_conditions": list(dict.fromkeys(invalid_conditions))[:3],
        "keywords": sorted(keywords, key=len, reverse=True)[:40],
        "ai_classification": ai_classification or None,
    }


def _fetch_cninfo_announcements(symbol: str, start_date: str, end_date: str, *, max_pages: int = 20, category: str = "") -> list[dict[str, Any]]:
    from akshare.stock_feature import stock_disclosure_cninfo as cninfo

    compact = _compact_symbol(symbol)
    org_map = getattr(cninfo, "__get_stock_json")("沪深京")
    org_id = org_map.get(compact)
    if not org_id:
        return []
    payload = {
        "pageNum": 1,
        "pageSize": 30,
        "column": "szse",
        "tabName": "fulltext",
        "plate": "",
        "stock": f"{compact},{org_id}",
        "searchkey": "",
        "secid": "",
        "category": category,
        "trade": "",
        "seDate": f"{start_date}~{end_date}",
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }
    response = requests.post(CNINFO_QUERY_URL, params=payload, timeout=25)
    response.raise_for_status()
    initial = response.json()
    total = int(initial.get("totalAnnouncement") or 0)
    page_count = max(1, min(max_pages, (total + int(payload["pageSize"]) - 1) // int(payload["pageSize"])))
    rows: list[dict[str, Any]] = []
    for page in range(1, page_count + 1):
        page_payload = {**payload, "pageNum": page}
        page_response = requests.post(CNINFO_QUERY_URL, data=page_payload, timeout=25)
        page_response.raise_for_status()
        rows.extend(page_response.json().get("announcements") or [])
    result = []
    for row in rows:
        title = re.sub(r"<[^>]+>", "", str(row.get("announcementTitle") or ""))
        adjunct = str(row.get("adjunctUrl") or "")
        if not adjunct or not any(term in title for term in RELEVANT_TITLE_TERMS):
            continue
        timestamp = row.get("announcementTime")
        announced_at = datetime.fromtimestamp(float(timestamp) / 1000, timezone.utc).astimezone().date().isoformat() if timestamp else None
        result.append({
            "announcement_id": str(row.get("announcementId") or ""),
            "title": title,
            "announced_at": announced_at,
            "pdf_url": f"{CNINFO_STATIC_ROOT}{adjunct.lstrip('/')}",
            "source": "cninfo",
        })
    return result


def _download_pdf(url: str) -> bytes:
    response = requests.get(
        url,
        timeout=40,
        headers={"User-Agent": "Mozilla/5.0 Stock-Pilot/1.0"},
    )
    response.raise_for_status()
    content = response.content
    if not content.startswith(b"%PDF"):
        raise ValueError("announcement response is not a PDF")
    if len(content) > 30 * 1024 * 1024:
        raise ValueError("announcement PDF exceeds 30 MB")
    return content


def _extract_pdf_pages(content: bytes) -> list[str]:
    reader = PdfReader(io.BytesIO(content))
    pages = []
    for index, page in enumerate(reader.pages):
        text = re.sub(r"[ \t]+", " ", page.extract_text() or "")
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if text:
            pages.append(f"[第{index + 1}页]\n{text}")
    return pages


def _select_relevant_text(pages: list[str], keywords: list[str], max_chars: int = 24000) -> str:
    ranked: list[tuple[int, str]] = []
    for page in pages:
        score = sum(1 for keyword in keywords if keyword and keyword.lower() in page.lower())
        if score:
            ranked.append((score, page))
    ranked.sort(key=lambda item: item[0], reverse=True)
    selected = ranked[:8] or [(0, page) for page in pages[:4]]
    text = "\n\n".join(page for _, page in selected)
    return text[:max_chars]


def _build_prompt(context: dict[str, Any], documents: list[dict[str, Any]]) -> str:
    document_text = "\n\n".join(
        f"=== 文件ID：{item['announcement_id']} | 公告：{item['title']} | 日期：{item['announced_at']} ===\n{item['selected_text']}"
        for item in documents
    )
    return f"""
你正在验证上市公司公告正文是否支持某些持仓 Thesis。只允许依据下方公告原文，不得使用外部知识。

标的：{context['symbol']}
主题与角色：{json.dumps(context['themes'], ensure_ascii=False)}
待验证问题：{json.dumps(context['questions'], ensure_ascii=False)}
失效条件：{json.dumps(context['invalid_conditions'], ensure_ascii=False)}

对每个待验证问题输出：
- status: supported / partially_supported / contradicted / not_found
- conclusion: 一句话结论
- quote: 公告中的短原文，最多 120 字；not_found 时为空
- page: quote 所在页码，无法定位则 null
- announcement_id
- confidence: 0 到 1

严格输出 JSON：
{{
  "items": [{{"question":"","status":"","conclusion":"","quote":"","page":null,"announcement_id":"","confidence":0.0}}],
  "overall_summary": "",
  "model_limit": "模型只负责原文匹配与归类，公告原文才是事实来源"
}}

强制要求：announcement_id 只能填写上方“文件ID”的纯数字，绝不能填写 URL、标题或文件名。
quote 必须从下方原文逐字复制连续的一句话或短句，不得改写、概括或拼接；无法复制原文时必须使用 not_found。

公告原文：
{document_text}
""".strip()


def _validate_model_items(payload: dict[str, Any], documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {item["announcement_id"]: item for item in documents}
    by_url = {str(item.get("pdf_url") or ""): item for item in documents}

    def normalize_quote(value: Any) -> str:
        return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", str(value or ""))

    valid: list[dict[str, Any]] = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "")
        if status not in {"supported", "partially_supported", "contradicted", "not_found"}:
            continue
        provided_id = str(item.get("announcement_id") or "")
        announcement = by_id.get(provided_id) or by_url.get(provided_id)
        quote = normalize_quote(item.get("quote"))
        quote_verified = status == "not_found"
        if announcement and quote:
            source_text = normalize_quote(announcement["selected_text"])
            quote_verified = len(quote) >= 12 and quote[: min(40, len(quote))] in source_text
        if status != "not_found" and not quote_verified:
            status = "not_found"
        valid.append({
            "question": str(item.get("question") or "")[:300],
            "status": status,
            "conclusion": str(item.get("conclusion") or "")[:500],
            "quote": str(item.get("quote") or "")[:160] if quote_verified else "",
            "quote_verified": quote_verified,
            "page": item.get("page"),
            "announcement_id": str(item.get("announcement_id") or ""),
            "confidence": max(0.0, min(float(item.get("confidence") or 0), 1.0)),
            "source_url": announcement.get("pdf_url") if announcement else None,
            "source_title": announcement.get("title") if announcement else None,
            "announced_at": announcement.get("announced_at") if announcement else None,
        })
    return valid


def verify_symbol_disclosures(
    symbol: str,
    *,
    force: bool = False,
    announcement_fetcher: Callable[[str, str, str], list[dict[str, Any]]] = _fetch_cninfo_announcements,
    pdf_fetcher: Callable[[str], bytes] = _download_pdf,
    model_caller: Callable[[str], str] = _call_disclosure_model,
) -> dict[str, Any]:
    cached = load_disclosure_verification(symbol)
    context = _symbol_context(symbol)
    question_signature = json.dumps(context["questions"], ensure_ascii=False, sort_keys=True)
    if cached and cached.get("question_signature") != question_signature:
        force = True
    if not force and _cache_is_fresh(cached):
        return cached
    if not context["questions"]:
        return {
            "symbol": _compact_symbol(symbol),
            "status": "not_applicable",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "items": [],
            "reason": "No registered thesis questions for this symbol.",
        }
    today = datetime.now().date()
    start = (today - timedelta(days=550)).isoformat()
    announcements = announcement_fetcher(symbol, start, today.isoformat())
    now = datetime.now(timezone.utc)
    seen_ids = _announcement_ids(cached)
    current_ids = {
        str(item.get("announcement_id"))
        for item in announcements
        if item.get("announcement_id")
    }
    if cached and not force:
        new_announcements = [
            item for item in announcements
            if item.get("announcement_id") and str(item["announcement_id"]) not in seen_ids
        ]
        if not new_announcements:
            cached["index_checked_at"] = now.isoformat()
            cached["discovered_announcement_ids"] = sorted(current_ids)
            cached["trigger"] = "announcement_index_no_change"
            _write_cache(symbol, cached)
            return cached
        announcements = new_announcements

    failed_ids = {str(item.get("announcement_id")) for item in (cached or {}).get("failures", [])}

    def announcement_relevance(item: dict[str, Any]) -> tuple[str, bool, int]:
        title = str(item.get("title") or "").lower()
        matches = sum(1 for keyword in context["keywords"] if keyword.lower() in title)
        return str(item.get("announced_at") or ""), str(item.get("announcement_id")) not in failed_ids, matches

    announcements.sort(key=announcement_relevance, reverse=True)
    documents: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for announcement in announcements[: settings.DISCLOSURE_VERIFICATION_MAX_DOCUMENTS]:
        try:
            pages = _extract_pdf_pages(pdf_fetcher(announcement["pdf_url"]))
            selected = _select_relevant_text(pages, context["keywords"])
            if not selected:
                raise ValueError("PDF has no extractable relevant text")
            documents.append({**announcement, "selected_text": selected, "page_count": len(pages)})
        except Exception as exc:
            failures.append({"announcement_id": str(announcement.get("announcement_id") or ""), "title": announcement.get("title", ""), "reason": str(exc)[:240]})
    if not documents:
        result = {
            "symbol": _compact_symbol(symbol),
            "status": "unavailable",
            "generated_at": now.isoformat(),
            "index_checked_at": now.isoformat(),
            "items": [],
            "documents": [],
            "failures": failures,
            "reason": "No announcement full text could be extracted.",
            "trigger": "new_announcement" if cached and not force else "initial_or_forced",
        }
    else:
        raw = model_caller(_build_prompt(context, documents))
        parsed = extract_json(raw)
        items = _validate_model_items(parsed, documents)
        counts = {status: sum(1 for item in items if item["status"] == status) for status in ("supported", "partially_supported", "contradicted", "not_found")}
        result = {
            "symbol": _compact_symbol(symbol),
            "status": "verified" if items else "model_unavailable",
            "generated_at": now.isoformat(),
            "index_checked_at": now.isoformat(),
            "items": items,
            "counts": counts,
            "documents": [
                {key: item.get(key) for key in ("announcement_id", "title", "announced_at", "pdf_url", "page_count")}
                for item in documents
            ],
            "failures": failures,
            "overall_summary": str(parsed.get("overall_summary") or "")[:800],
            "boundary": "公告原文是事实来源；模型仅负责匹配和归类，未通过原文校验的引用按 not_found 处理。",
            "trigger": "new_announcement" if cached and not force else "initial_or_forced",
        }
    if cached and not force:
        result["items"] = [*(cached.get("items") or []), *(result.get("items") or [])][-100:]
        result["documents"] = [*(cached.get("documents") or []), *(result.get("documents") or [])][-50:]
        result["failures"] = [*(cached.get("failures") or []), *(result.get("failures") or [])][-50:]
        result["counts"] = {
            status: sum(1 for item in result["items"] if item.get("status") == status)
            for status in ("supported", "partially_supported", "contradicted", "not_found")
        }
    processed_ids = seen_ids | {
        str(document["announcement_id"]) for document in documents
        if document.get("announcement_id") and result.get("status") == "verified"
    }
    result["processed_announcement_ids"] = sorted(processed_ids)
    result["discovered_announcement_ids"] = sorted(current_ids)
    result["pending_announcement_ids"] = sorted(current_ids - processed_ids)
    result["seen_announcement_ids"] = sorted(processed_ids)
    result["question_signature"] = question_signature
    _write_cache(symbol, result)
    try:
        from app.portfolio.dashboard_cache import invalidate_dashboard_cache
        invalidate_dashboard_cache()
    except ImportError:
        pass
    return annotate_verification(result)


def refresh_portfolio_disclosure_verifications(*, force: bool = False) -> dict[str, Any]:
    if not settings.DISCLOSURE_VERIFICATION_ENABLED:
        return {"status": "disabled", "results": []}
    from app.portfolio import portfolio_service

    positions = [
        item for item in portfolio_service.get_state().snapshot.positions
        if not _compact_symbol(item.symbol).startswith(("15", "16", "51", "56", "58"))
    ][: settings.DISCLOSURE_VERIFICATION_MAX_SYMBOLS]
    results = []
    for position in positions:
        try:
            result = verify_symbol_disclosures(position.symbol, force=force)
            results.append({"symbol": position.symbol, "status": result.get("status")})
        except Exception as exc:
            results.append({"symbol": position.symbol, "status": "failed", "reason": str(exc)[:240]})
    return {
        "status": "complete",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
