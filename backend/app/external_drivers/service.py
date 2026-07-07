from __future__ import annotations

from datetime import datetime, timezone
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
from app.external_drivers.profiles import DEFAULT_UNMAPPED, MAPPING_BOUNDARY, find_profile
from app.external_drivers.schemas import ExternalDriver, ExternalDriverContext
from app.facts.common import DEFAULT_DAILY_TTL, days_ago_yyyymmdd, parse_yyyymmdd, records_from_df, safe_float, to_ts_code
from app.external_drivers.yahoo_comex_provider import get_comex_fact, YahooComexError
from app.facts.etf_service import get_etf_facts
from app.tushare import TushareConfigError, TushareLowFrequencyClient, TushareRequestError


FACT_LIMIT = (
    "External-driver facts are related background observations only. They do not imply a direct "
    "causal effect, valuation impact, or buy/sell conclusion."
)

SIGNAL_LIMIT = (
    "External-driver changes are derived observations computed from retrieved daily facts. "
    "They are weak context only and must not be interpreted as causality."
)


def _latest_close_record(df: pd.DataFrame) -> dict[str, Any]:
    if df is None or df.empty:
        return {}
    frame = df.copy()
    if "trade_date" in frame.columns:
        frame["trade_date"] = frame["trade_date"].astype(str)
        frame = frame.sort_values("trade_date", ascending=False).reset_index(drop=True)
    return frame.iloc[0].to_dict()


def _close_series(df: pd.DataFrame) -> list[float | None]:
    if df is None or df.empty:
        return []
    close_col = "close" if "close" in df.columns else None
    if close_col is None and {"bid_close", "ask_close"} <= set(df.columns):
        mid = (pd.to_numeric(df["bid_close"], errors="coerce") + pd.to_numeric(df["ask_close"], errors="coerce")) / 2
        return [None if pd.isna(v) else float(v) for v in mid.tolist()]
    if close_col is None:
        return []
    values = pd.to_numeric(df[close_col], errors="coerce")
    return [None if pd.isna(v) else float(v) for v in values.tolist()]


def _pct_change(values: list[float | None], offset: int) -> float | None:
    if len(values) <= offset or values[0] is None or values[offset] in {None, 0}:
        return None
    return round((values[0] / values[offset] - 1) * 100, 4)


def _daily_payload(driver: ExternalDriver, df: pd.DataFrame, meta: dict[str, Any], include_series: bool = False) -> dict[str, Any]:
    if df is not None and not df.empty and "trade_date" in df.columns:
        df = df.copy()
        df["trade_date"] = df["trade_date"].astype(str)
        df = df.sort_values("trade_date", ascending=False).reset_index(drop=True)
    latest = _latest_close_record(df)
    values = _close_series(df)
    close = safe_float(latest.get("close"))
    if close is None and latest.get("bid_close") is not None and latest.get("ask_close") is not None:
        bid = safe_float(latest.get("bid_close"))
        ask = safe_float(latest.get("ask_close"))
        close = round((bid + ask) / 2, 4) if bid is not None and ask is not None else None
    payload: dict[str, Any] = {
        "factor_id": driver.factor_id,
        "display_name": driver.display_name,
        "factor_type": driver.factor_type,
        "provider_symbol": driver.retrieval_config.provider_symbol,
        "trade_date": latest.get("trade_date"),
        "close": close,
        "open": safe_float(latest.get("open")),
        "high": safe_float(latest.get("high")),
        "low": safe_float(latest.get("low")),
        "volume": safe_float(latest.get("vol")) or safe_float(latest.get("volume")),
        "amount": safe_float(latest.get("amount")),
        "returns_pct": {
            "1d": _pct_change(values, 1),
            "5d": _pct_change(values, 5),
            "20d": _pct_change(values, 20),
        },
        "cache": meta,
        "interpretation_limit": driver.interpretation_limit,
    }
    if include_series:
        payload["series"] = records_from_df(df, 75)
    return payload


def _unavailable_evidence(symbol: str, driver: ExternalDriver, reason: str) -> EvidenceItem:
    return EvidenceItem(
        symbol=to_ts_code(symbol),
        evidence_type=EvidenceType.EXTERNAL_DRIVER_FACT,
        category=EvidenceCategory.AUTO_FACT,
        title=f"External driver unavailable: {driver.display_name}",
        payload={
            "factor_id": driver.factor_id,
            "display_name": driver.display_name,
            "factor_type": driver.factor_type,
            "data_status": "unavailable",
            "reason": reason,
            "mapping_boundary": MAPPING_BOUNDARY,
        },
        source=f"{driver.retrieval_config.provider}.{driver.retrieval_config.endpoint}",
        source_endpoint=driver.retrieval_config.endpoint,
        fetched_at=datetime.now(timezone.utc),
        reliability=EvidenceReliability.B,
        llm_usage=LlmUsage.CONTEXT_ONLY,
        interpretation_limit=FACT_LIMIT,
        data_status=DataStatus.UNAVAILABLE,
    )


def _unsupported_missing(driver: ExternalDriver) -> dict[str, Any]:
    return {
        "key": f"external_driver:{driver.factor_id}",
        "mapping_status": driver.status,
        "reason": driver.interpretation_limit,
        "future_extension": "Add a verified provider endpoint/code before enabling automatic retrieval.",
        "factor_type": driver.factor_type,
    }


def _fetch_daily_driver(symbol: str, driver: ExternalDriver) -> list[EvidenceItem]:
    provider = driver.retrieval_config.provider
    if provider == "yahoo_finance":
        return _fetch_yahoo_comex_driver(symbol, driver)

    client = TushareLowFrequencyClient()
    provider_symbol = driver.retrieval_config.provider_symbol
    if not provider_symbol:
        return [_unavailable_evidence(symbol, driver, "No verified provider symbol is configured.")]
    try:
        df, meta = client.query(
            driver.retrieval_config.endpoint,
            namespace="external_drivers",
            ttl=DEFAULT_DAILY_TTL,
            ts_code=provider_symbol,
            start_date=days_ago_yyyymmdd(140),
            end_date=datetime.now().strftime("%Y%m%d"),
        )
    except (TushareConfigError, TushareRequestError) as exc:
        return [_unavailable_evidence(symbol, driver, str(exc))]

    payload = _daily_payload(driver, df, meta, include_series=False)
    as_of = parse_yyyymmdd(payload.get("trade_date"))
    fact = EvidenceItem(
        symbol=to_ts_code(symbol),
        evidence_type=EvidenceType.EXTERNAL_DRIVER_FACT,
        category=EvidenceCategory.AUTO_FACT,
        title=f"External driver fact: {driver.display_name}",
        payload=payload,
        source=f"{driver.retrieval_config.provider}.{driver.retrieval_config.endpoint}",
        source_endpoint=driver.retrieval_config.endpoint,
        as_of_date=as_of,
        fetched_at=datetime.now(timezone.utc),
        reliability=EvidenceReliability.B,
        llm_usage=LlmUsage.FACT_WITH_LIMIT,
        interpretation_limit=FACT_LIMIT,
        data_status=DataStatus.AVAILABLE if payload.get("close") is not None else DataStatus.UNAVAILABLE,
    )
    signal = EvidenceItem(
        symbol=to_ts_code(symbol),
        evidence_type=EvidenceType.EXTERNAL_DRIVER_SIGNAL,
        category=EvidenceCategory.AUTO_SIGNAL,
        title=f"External driver derived changes: {driver.display_name}",
        payload={
            "factor_id": driver.factor_id,
            "display_name": driver.display_name,
            "returns_pct": payload.get("returns_pct"),
            "calculation": "close-to-close percentage change over 1, 5, and 20 observations when enough data is available",
        },
        source=f"{driver.retrieval_config.provider}.{driver.retrieval_config.endpoint}",
        source_endpoint=driver.retrieval_config.endpoint,
        as_of_date=as_of,
        fetched_at=datetime.now(timezone.utc),
        reliability=EvidenceReliability.C,
        llm_usage=LlmUsage.WEAK_SIGNAL_ONLY,
        interpretation_limit=SIGNAL_LIMIT,
        data_status=fact.data_status,
    )
    return [fact, signal]


def _fetch_yahoo_comex_driver(symbol: str, driver: ExternalDriver) -> list[EvidenceItem]:
    try:
        result = get_comex_fact(driver.factor_id, range_days="30d", include_series=False)
    except YahooComexError as exc:
        return [_unavailable_evidence(symbol, driver, str(exc))]

    if result.get("data_status") != "available":
        return [_unavailable_evidence(symbol, driver, result.get("reason") or "Yahoo COMEX data unavailable.")]

    result["factor_type"] = driver.factor_type
    as_of = parse_yyyymmdd(result.get("trade_date"))
    fact = EvidenceItem(
        symbol=to_ts_code(symbol),
        evidence_type=EvidenceType.EXTERNAL_DRIVER_FACT,
        category=EvidenceCategory.AUTO_FACT,
        title=f"External driver fact: {driver.display_name}",
        payload=result,
        source=f"{driver.retrieval_config.provider}.{driver.retrieval_config.endpoint}",
        source_endpoint=driver.retrieval_config.endpoint,
        as_of_date=as_of,
        fetched_at=datetime.now(timezone.utc),
        reliability=EvidenceReliability.B,
        llm_usage=LlmUsage.CONTEXT_ONLY,
        interpretation_limit=result.get("interpretation_limit") or FACT_LIMIT,
        data_status=DataStatus.AVAILABLE,
    )
    signal = EvidenceItem(
        symbol=to_ts_code(symbol),
        evidence_type=EvidenceType.EXTERNAL_DRIVER_SIGNAL,
        category=EvidenceCategory.AUTO_SIGNAL,
        title=f"External driver derived changes: {driver.display_name}",
        payload={
            "factor_id": driver.factor_id,
            "display_name": driver.display_name,
            "returns_pct": result.get("returns_pct"),
            "calculation": "close-to-close percentage change over 1, 5, and 20 observations from Yahoo COMEX delayed reference",
        },
        source=f"{driver.retrieval_config.provider}.{driver.retrieval_config.endpoint}",
        source_endpoint=driver.retrieval_config.endpoint,
        as_of_date=as_of,
        fetched_at=datetime.now(timezone.utc),
        reliability=EvidenceReliability.C,
        llm_usage=LlmUsage.WEAK_SIGNAL_ONLY,
        interpretation_limit=SIGNAL_LIMIT,
        data_status=DataStatus.AVAILABLE,
    )
    return [fact, signal]


def _fetch_etf_driver(symbol: str, driver: ExternalDriver) -> list[EvidenceItem]:
    provider_symbol = driver.retrieval_config.provider_symbol
    if not provider_symbol:
        return [_unavailable_evidence(symbol, driver, "No verified ETF symbol is configured.")]
    result = get_etf_facts(provider_symbol)
    if not result.get("evidence"):
        return [_unavailable_evidence(symbol, driver, result.get("message") or "ETF fact service returned no evidence.")]
    evidence: list[EvidenceItem] = []
    for item in result.get("evidence") or []:
        payload = item.get("payload") or {}
        evidence.append(EvidenceItem(
            symbol=to_ts_code(symbol),
            evidence_type=EvidenceType.EXTERNAL_DRIVER_FACT,
            category=EvidenceCategory.AUTO_FACT,
            title=f"External driver ETF fact: {driver.display_name}",
            payload={
                "factor_id": driver.factor_id,
                "display_name": driver.display_name,
                "factor_type": driver.factor_type,
                "provider_symbol": provider_symbol,
                "etf_fact": payload,
                "mapping_boundary": MAPPING_BOUNDARY,
            },
            source=item.get("source") or "tushare.etf_fact_service",
            source_endpoint=item.get("source_endpoint") or driver.retrieval_config.endpoint,
            as_of_date=parse_yyyymmdd((payload.get("as_of_date") or "").replace("-", "")),
            fetched_at=datetime.now(timezone.utc),
            reliability=EvidenceReliability.B,
            llm_usage=LlmUsage.FACT_WITH_LIMIT,
            interpretation_limit=FACT_LIMIT,
            data_status=DataStatus(item.get("data_status", "available")),
        ))
        evidence.append(EvidenceItem(
            symbol=to_ts_code(symbol),
            evidence_type=EvidenceType.EXTERNAL_DRIVER_SIGNAL,
            category=EvidenceCategory.AUTO_SIGNAL,
            title=f"External driver ETF derived changes: {driver.display_name}",
            payload={
                "factor_id": driver.factor_id,
                "display_name": driver.display_name,
                "share_change": payload.get("share_change"),
                "price_change": payload.get("price_change"),
                "calculation": "ETF service derived 1d/5d/20d share and price changes when enough daily data is available",
            },
            source=item.get("source") or "tushare.etf_fact_service",
            source_endpoint=item.get("source_endpoint") or driver.retrieval_config.endpoint,
            as_of_date=parse_yyyymmdd((payload.get("as_of_date") or "").replace("-", "")),
            fetched_at=datetime.now(timezone.utc),
            reliability=EvidenceReliability.C,
            llm_usage=LlmUsage.WEAK_SIGNAL_ONLY,
            interpretation_limit=SIGNAL_LIMIT,
            data_status=DataStatus(item.get("data_status", "available")),
        ))
    return evidence


def build_external_driver_context(symbol: str, primary_theme: str | None = None, directions: list[str] | None = None) -> ExternalDriverContext:
    profile = find_profile(symbol, primary_theme=primary_theme, directions=directions)
    ts_code = to_ts_code(symbol)
    if profile is None:
        return ExternalDriverContext(symbol=ts_code, **DEFAULT_UNMAPPED)

    evidence: list[EvidenceItem] = []
    missing_data: list[dict[str, Any]] = []
    for driver in profile.drivers:
        if driver.status != "configured" or driver.factor_type == "unsupported_placeholder":
            missing_data.append(_unsupported_missing(driver))
            continue
        if driver.factor_type == "theme_etf":
            evidence.extend(_fetch_etf_driver(ts_code, driver))
        elif driver.factor_type in {"commodity", "fx", "sector_index"}:
            evidence.extend(_fetch_daily_driver(ts_code, driver))
        else:
            missing_data.append(_unsupported_missing(driver))

    return ExternalDriverContext(
        mapping_status="configured",
        profile_id=profile.profile_id,
        symbol=ts_code,
        message="已为该标的配置专属外部驱动观察因子；这些因子仅用于筛选背景变量。",
        future_extension="可继续增加经用户确认且接口代码已验证的行业、商品或主题映射。",
        drivers=[driver.model_dump(mode="json") for driver in profile.drivers],
        boundary=profile.boundary,
        evidence=[item.model_dump(mode="json") for item in evidence],
        missing_data=missing_data,
    )
