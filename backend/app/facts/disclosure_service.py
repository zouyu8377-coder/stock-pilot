from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from app.evidence.schemas import (
    DataStatus,
    EvidenceCategory,
    EvidenceItem,
    EvidenceReliability,
    EvidenceType,
    LlmUsage,
)
from app.facts.common import (
    DEFAULT_DAILY_TTL,
    days_ago_yyyymmdd,
    parse_yyyymmdd,
    records_from_df,
    safe_str,
    today_yyyymmdd,
    to_ts_code,
)
from app.tushare import TushareConfigError, TushareLowFrequencyClient, TushareRequestError


ANNOUNCEMENT_LIMIT = (
    "The system currently fetches announcement index information only and does not read full text. "
    "Do not infer order, capacity, or profit impact from the index title."
)
SURVEY_LIMIT = (
    "The system currently fetches survey index information only and does not read full text. "
    "Do not infer survey conclusions, order status, or earnings impact from the index."
)
CNINFO_QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STATIC_ROOT = "https://static.cninfo.com.cn/"
CNINFO_CACHE_ROOT = Path(__file__).resolve().parents[2] / "data" / "facts" / "cninfo_announcements"


def _cninfo_cache_path(symbol: str) -> Path:
    return CNINFO_CACHE_ROOT / f"{symbol.split('.', 1)[0].zfill(6)}.json"


def _load_cninfo_cache(symbol: str) -> list[dict[str, Any]] | None:
    try:
        payload = json.loads(_cninfo_cache_path(symbol).read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(str(payload.get("fetched_at")).replace("Z", "+00:00"))
        if datetime.now(timezone.utc) - fetched_at.astimezone(timezone.utc) > DEFAULT_DAILY_TTL:
            return None
        rows = payload.get("rows")
        return rows if isinstance(rows, list) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _write_cninfo_cache(symbol: str, rows: list[dict[str, Any]]) -> None:
    path = _cninfo_cache_path(symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "rows": rows}, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def _fetch_cninfo_announcement_index(symbol: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    """Low-frequency fallback for public announcement indexes when Tushare is absent.

    CNINFO is an official disclosure platform. This reads only the index and PDF URL;
    no announcement body is interpreted here.
    """
    from akshare.stock_feature import stock_disclosure_cninfo as cninfo

    compact = symbol.split(".", 1)[0].zfill(6)
    org_map = getattr(cninfo, "__get_stock_json")("沪深京")
    org_id = org_map.get(compact)
    if not org_id:
        return []
    start = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
    end = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"
    payload = {
        "pageNum": 1,
        "pageSize": 30,
        "column": "szse",
        "tabName": "fulltext",
        "plate": "",
        "stock": f"{compact},{org_id}",
        "searchkey": "",
        "secid": "",
        "category": "",
        "trade": "",
        "seDate": f"{start}~{end}",
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }
    headers = {"User-Agent": "Mozilla/5.0 Stock-Pilot/1.0"}
    response = requests.post(CNINFO_QUERY_URL, data=payload, headers=headers, timeout=25)
    response.raise_for_status()
    rows = response.json().get("announcements") or []
    result: list[dict[str, Any]] = []
    for row in rows:
        title = re.sub(r"<[^>]+>", "", str(row.get("announcementTitle") or "")).strip()
        adjunct = str(row.get("adjunctUrl") or "")
        if not title or not adjunct:
            continue
        timestamp = row.get("announcementTime")
        ann_date = ""
        if timestamp:
            ann_date = datetime.fromtimestamp(float(timestamp) / 1000, timezone.utc).strftime("%Y%m%d")
        result.append({
            "ann_date": ann_date,
            "title": title,
            "url": f"{CNINFO_STATIC_ROOT}{adjunct.lstrip('/')}",
        })
    return result


def classify_announcement_title(title: str) -> str:
    text = title or ""
    if any(key in text for key in ("年度报告", "半年度报告", "季度报告", "定期报告", "annual report", "quarterly report")):
        return "定期报告"
    if any(key in text for key in ("业绩预告", "业绩快报", "earnings forecast")):
        return "业绩预告/业绩快报"
    if any(key in text for key in ("投资者关系", "投资者交流", "调研", "路演", "investor relations")):
        return "投资者关系活动"
    if any(key in text for key in ("项目投资", "扩产", "产能", "募投项目", "建设项目")):
        return "项目投资/扩产"
    if "回购" in text:
        return "回购"
    if any(key in text for key in ("增持", "减持")):
        return "增减持"
    if any(key in text for key in ("异常波动", "风险提示", "严重异常")):
        return "异常波动/风险提示"
    return "其他"


def _sort(df: pd.DataFrame, column: str) -> pd.DataFrame:
    if df is None or df.empty or column not in df.columns:
        return pd.DataFrame()
    frame = df.copy()
    frame[column] = frame[column].astype(str)
    return frame.sort_values(column, ascending=False).reset_index(drop=True)


def _announcement_payload(row: dict[str, Any]) -> dict[str, Any]:
    title = safe_str(row.get("title"))
    return {
        "ann_date": safe_str(row.get("ann_date")),
        "title": title,
        "url": safe_str(row.get("url")),
        "category_label": classify_announcement_title(title),
        "interpretation_limit": ANNOUNCEMENT_LIMIT,
    }


def _survey_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "surv_date": safe_str(row.get("surv_date")),
        "rece_mode": safe_str(row.get("rece_mode")),
        "rece_org": safe_str(row.get("rece_org")),
        "org_type": safe_str(row.get("org_type")),
        "comp_rece": safe_str(row.get("comp_rece")),
        "rece_place": safe_str(row.get("rece_place")),
        "interpretation_limit": SURVEY_LIMIT,
    }


def get_disclosure_facts(symbol: str, *, force: bool = False) -> dict[str, Any]:
    ts_code = to_ts_code(symbol)
    client = TushareLowFrequencyClient()
    end_date = today_yyyymmdd()
    source = "tushare"
    warning = ""
    try:
        anns_df, anns_meta = client.query(
            "anns_d",
            namespace="announcements",
            ttl=DEFAULT_DAILY_TTL,
            force=force,
            ts_code=ts_code,
            start_date=days_ago_yyyymmdd(90),
            end_date=end_date,
        )
        surveys_df, surveys_meta = client.query(
            "stk_surv",
            namespace="surveys",
            ttl=DEFAULT_DAILY_TTL,
            force=force,
            ts_code=ts_code,
            start_date=days_ago_yyyymmdd(90),
            end_date=end_date,
        )
    except (TushareConfigError, TushareRequestError) as exc:
        source = "cninfo_official_fallback"
        warning = f"Tushare 不可用，已改用巨潮官方公告索引；调研索引暂不可用：{exc}"
        try:
            fallback_rows = None if force else _load_cninfo_cache(ts_code)
            if fallback_rows is None:
                fallback_rows = _fetch_cninfo_announcement_index(
                    ts_code,
                    days_ago_yyyymmdd(90),
                    end_date,
                )
                _write_cninfo_cache(ts_code, fallback_rows)
        except Exception as fallback_exc:
            return {
                "success": False,
                "symbol": ts_code,
                "message": f"Tushare 不可用；巨潮官方公告索引也不可用：{fallback_exc}",
                "data_status": "unavailable",
                "data": {"announcements": [], "surveys": []},
                "evidence": [],
            }
        anns_df = pd.DataFrame(fallback_rows)
        surveys_df = pd.DataFrame()
        anns_meta = {"source": "cninfo_official", "cached": False}
        surveys_meta = {"source": "unavailable_without_tushare", "cached": False}

    anns_df = _sort(anns_df, "ann_date")
    surveys_df = _sort(surveys_df, "surv_date")
    announcements = [_announcement_payload(row) for row in records_from_df(anns_df, 30)]
    surveys = [_survey_payload(row) for row in records_from_df(surveys_df, 30)]

    evidence: list[dict[str, Any]] = []
    announcement_source = "cninfo.official" if source == "cninfo_official_fallback" else "tushare.anns_d"
    announcement_reliability = EvidenceReliability.A if source == "cninfo_official_fallback" else EvidenceReliability.B
    for item in announcements:
        evidence.append(EvidenceItem(
            symbol=ts_code,
            evidence_type=EvidenceType.ANNOUNCEMENT_INDEX,
            category=EvidenceCategory.AUTO_FACT,
            title=f"Announcement index {item['ann_date']}",
            payload=item,
            source=announcement_source,
            source_endpoint="cninfo.hisAnnouncement.query" if source == "cninfo_official_fallback" else "anns_d",
            as_of_date=parse_yyyymmdd(item["ann_date"]),
            fetched_at=datetime.utcnow(),
            reliability=announcement_reliability,
            llm_usage=LlmUsage.FACT_WITH_LIMIT,
            interpretation_limit=ANNOUNCEMENT_LIMIT,
            data_status=DataStatus.AVAILABLE,
        ).model_dump(mode="json"))

    for item in surveys:
        evidence.append(EvidenceItem(
            symbol=ts_code,
            evidence_type=EvidenceType.SURVEY_INDEX,
            category=EvidenceCategory.AUTO_FACT,
            title=f"Survey index {item['surv_date']}",
            payload=item,
            source="tushare.stk_surv",
            source_endpoint="stk_surv",
            as_of_date=parse_yyyymmdd(item["surv_date"]),
            fetched_at=datetime.utcnow(),
            reliability=EvidenceReliability.B,
            llm_usage=LlmUsage.FACT_WITH_LIMIT,
            interpretation_limit=SURVEY_LIMIT,
            data_status=DataStatus.AVAILABLE,
        ).model_dump(mode="json"))

    return {
        "success": True,
        "symbol": ts_code,
        "data_status": "available" if announcements or surveys else "unavailable",
        "data": {
            "announcements": announcements,
            "surveys": surveys,
            "announcement_interpretation_limit": ANNOUNCEMENT_LIMIT,
            "survey_interpretation_limit": SURVEY_LIMIT,
            "empty_message": "" if announcements or surveys else "No announcement or survey index found in the recent query window.",
            "announcement_source": announcement_source,
            "survey_source": "tushare.stk_surv" if source == "tushare" else "unavailable_without_tushare",
        },
        "evidence": evidence,
        "cache": {
            "announcements": anns_meta,
            "surveys": surveys_meta,
        },
        "message": warning,
    }
