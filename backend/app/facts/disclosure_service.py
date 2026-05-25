from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

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
        return {
            "success": False,
            "symbol": ts_code,
            "message": str(exc),
            "data_status": "unavailable",
            "data": {"announcements": [], "surveys": []},
            "evidence": [],
        }

    anns_df = _sort(anns_df, "ann_date")
    surveys_df = _sort(surveys_df, "surv_date")
    announcements = [_announcement_payload(row) for row in records_from_df(anns_df, 30)]
    surveys = [_survey_payload(row) for row in records_from_df(surveys_df, 30)]

    evidence: list[dict[str, Any]] = []
    for item in announcements:
        evidence.append(EvidenceItem(
            symbol=ts_code,
            evidence_type=EvidenceType.ANNOUNCEMENT_INDEX,
            category=EvidenceCategory.AUTO_FACT,
            title=f"Announcement index {item['ann_date']}",
            payload=item,
            source="tushare.anns_d",
            source_endpoint="anns_d",
            as_of_date=parse_yyyymmdd(item["ann_date"]),
            fetched_at=datetime.utcnow(),
            reliability=EvidenceReliability.B,
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
        },
        "evidence": evidence,
        "cache": {
            "announcements": anns_meta,
            "surveys": surveys_meta,
        },
    }
