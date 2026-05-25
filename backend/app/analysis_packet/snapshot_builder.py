from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.ai.analyzer import analyze_stock
from app.analysis.data_coverage import build_data_coverage
from app.analysis.indicators import compute_indicators
from app.collector.metadata_provider import metadata_provider
from app.collector.router import collector
from app.company_profile.profile_engine import build_company_profile
from app.company_profile.schemas import CompanyProfile
from app.core.config import settings
from app.evidence.schemas import (
    AnalysisScope,
    AnalysisSnapshot,
    DataStatus,
    EvidenceCategory,
    EvidenceItem,
    EvidenceReliability,
    EvidenceType,
    LlmUsage,
)
from app.facts.common import to_ts_code
from app.facts.disclosure_service import ANNOUNCEMENT_LIMIT, SURVEY_LIMIT, get_disclosure_facts
from app.facts.dragon_tiger_service import get_dragon_tiger_facts
from app.facts.etf_service import SUPPORTED_ETFS, get_etf_facts
from app.strategy.model_selector import select_models
from app.strategy.regime_engine import detect_market_regime


def _date_col(df: pd.DataFrame) -> str | None:
    for col in ("date", "日期"):
        if col in df.columns:
            return col
    return None


def _column(df: pd.DataFrame, *names: str) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    return None


def _latest_daily_date(history: pd.DataFrame) -> date | None:
    col = _date_col(history)
    if not col or history.empty:
        return None
    parsed = pd.to_datetime(history[col], errors="coerce").dropna()
    if parsed.empty:
        return None
    return parsed.iloc[-1].date()


def _daily_k_summary(history: pd.DataFrame) -> dict[str, Any]:
    if history is None or history.empty:
        return {}
    close_col = _column(history, "close", "收盘")
    open_col = _column(history, "open", "开盘")
    high_col = _column(history, "high", "最高")
    low_col = _column(history, "low", "最低")
    volume_col = _column(history, "volume", "成交量")
    amount_col = _column(history, "amount", "成交额")
    pct_col = _column(history, "pctChg", "pct_chg", "涨跌幅")
    latest = history.iloc[-1]
    summary: dict[str, Any] = {"row_count": int(len(history))}
    for output_key, col in {
        "open": open_col,
        "high": high_col,
        "low": low_col,
        "close": close_col,
        "volume": volume_col,
        "amount": amount_col,
        "pct_chg": pct_col,
    }.items():
        if col:
            value = pd.to_numeric(pd.Series([latest[col]]), errors="coerce").iloc[0]
            summary[output_key] = None if pd.isna(value) else float(value)
    if close_col and len(history) >= 20:
        closes = pd.to_numeric(history[close_col], errors="coerce").dropna()
        if len(closes) >= 20:
            summary["return_5d_pct"] = round((closes.iloc[-1] / closes.iloc[-6] - 1) * 100, 2) if len(closes) >= 6 else None
            summary["return_20d_pct"] = round((closes.iloc[-1] / closes.iloc[-21] - 1) * 100, 2) if len(closes) >= 21 else None
            summary["return_60d_pct"] = round((closes.iloc[-1] / closes.iloc[-61] - 1) * 100, 2) if len(closes) >= 61 else None
    return summary


def _profile_payload(profile: CompanyProfile | None) -> dict[str, Any]:
    if not profile:
        return {}
    return profile.model_dump()


def _stock_data(symbol: str) -> tuple[dict[str, Any], pd.DataFrame]:
    quote = collector.get_quote(symbol)
    history = collector.get_history(symbol)
    indicators, _ = compute_indicators(history)
    meta = metadata_provider.get(symbol)
    industry = meta["industry"] if meta else None
    company_profile = build_company_profile(symbol)
    stock_data = {
        "name": quote.get("name"),
        "symbol": symbol,
        "price": quote.get("price"),
        "change_pct": quote.get("change_pct"),
        "industry": industry,
        "indicators": indicators,
        "company_profile": company_profile,
    }
    stock_data["analysis"] = analyze_stock(stock_data)
    strategy_context = detect_market_regime(stock_data, company_profile)
    select_models(strategy_context)
    stock_data["strategy_context"] = strategy_context
    stock_data["data_coverage"] = build_data_coverage(company_profile, history, stock_data)
    stock_data["quote"] = quote
    stock_data["meta"] = meta or {}
    return stock_data, history


def build_basic_stock_snapshot(
    symbol: str,
    *,
    user_question: str | None = None,
    stock_data: dict[str, Any] | None = None,
    history: pd.DataFrame | None = None,
    persist: bool = True,
) -> AnalysisSnapshot:
    if stock_data is None or history is None:
        stock_data, history = _stock_data(symbol)

    fetched_at = datetime.utcnow()
    daily_as_of = _latest_daily_date(history)
    quote = stock_data.get("quote") or {
        "symbol": symbol,
        "name": stock_data.get("name"),
        "price": stock_data.get("price"),
        "change_pct": stock_data.get("change_pct"),
    }
    evidence_items = [
        EvidenceItem(
            symbol=symbol,
            evidence_type=EvidenceType.REALTIME_QUOTE,
            category=EvidenceCategory.AUTO_FACT,
            title="Realtime quote snapshot",
            payload=quote,
            source=quote.get("provider", "easyquotation/tencent"),
            source_endpoint="easyquotation.real",
            as_of_time=fetched_at,
            fetched_at=fetched_at,
            reliability=EvidenceReliability.B,
            llm_usage=LlmUsage.FACT_WITH_LIMIT,
            interpretation_limit="Quote data may be delayed and should not be interpreted as institutional intent.",
        ),
        EvidenceItem(
            symbol=symbol,
            evidence_type=EvidenceType.DAILY_K_SUMMARY,
            category=EvidenceCategory.AUTO_FACT,
            title="Local daily K summary",
            payload=_daily_k_summary(history),
            source="local parquet base_market",
            source_endpoint="collector.get_history",
            as_of_date=daily_as_of,
            fetched_at=fetched_at,
            reliability=EvidenceReliability.B,
            llm_usage=LlmUsage.FACT_WITH_LIMIT,
            interpretation_limit="Local daily K is a market fact summary, not a trading conclusion.",
        ),
        EvidenceItem(
            symbol=symbol,
            evidence_type=EvidenceType.TECHNICAL_INDICATOR,
            category=EvidenceCategory.AUTO_SIGNAL,
            title="Technical indicators",
            payload=stock_data.get("indicators", {}),
            source="indicators.py",
            source_endpoint="compute_indicators",
            as_of_date=daily_as_of,
            fetched_at=fetched_at,
            reliability=EvidenceReliability.C,
            llm_usage=LlmUsage.WEAK_SIGNAL_ONLY,
            interpretation_limit="Technical indicators are auxiliary signals and must not be the sole basis for conclusions.",
        ),
        EvidenceItem(
            symbol=symbol,
            evidence_type=EvidenceType.COMPANY_PROFILE,
            category=EvidenceCategory.AUTO_FACT,
            title="Company profile",
            payload=_profile_payload(stock_data.get("company_profile")),
            source="stock_meta/Tushare cache/rule inference",
            source_endpoint="build_company_profile",
            fetched_at=fetched_at,
            reliability=EvidenceReliability.B,
            llm_usage=LlmUsage.FACT_WITH_LIMIT,
            interpretation_limit="Rule-inferred profile fields should be treated as bounded context, not formal disclosure.",
        ),
        EvidenceItem(
            symbol=symbol,
            evidence_type=EvidenceType.DATA_COVERAGE,
            category=EvidenceCategory.AUTO_FACT,
            title="Data coverage",
            payload=stock_data.get("data_coverage", {}),
            source="data_coverage.py",
            source_endpoint="build_data_coverage",
            fetched_at=fetched_at,
            reliability=EvidenceReliability.B,
            llm_usage=LlmUsage.CONTEXT_ONLY,
            interpretation_limit="Use this item to identify available and missing data, not as market evidence.",
        ),
    ]

    system_hypotheses = [
        EvidenceItem(
            symbol=symbol,
            evidence_type=EvidenceType.SYSTEM_MARKET_REGIME,
            category=EvidenceCategory.SYSTEM_HYPOTHESIS,
            title="Rule-based analysis and market regime",
            payload={
                "analysis": stock_data.get("analysis", {}),
                "market_regime": getattr(stock_data.get("strategy_context"), "market_regime", ""),
                "selected_models": getattr(stock_data.get("strategy_context"), "selected_models", []),
            },
            source="Stock-Pilot rule engine",
            source_endpoint="analyze_stock/detect_market_regime/select_models",
            as_of_date=daily_as_of,
            fetched_at=fetched_at,
            reliability=EvidenceReliability.H,
            llm_usage=LlmUsage.HYPOTHESIS_ONLY,
            interpretation_limit="System-generated hypothesis only. Do not cite it as a fact.",
        )
    ]

    extra_missing = []
    try:
        ts_code = to_ts_code(symbol)
        if ts_code in SUPPORTED_ETFS:
            etf_result = get_etf_facts(ts_code)
            evidence_items.extend(EvidenceItem(**item) for item in etf_result.get("evidence", []))
        else:
            dragon_result = get_dragon_tiger_facts(ts_code)
            evidence_items.extend(EvidenceItem(**item) for item in dragon_result.get("evidence", []))
            disclosure_result = get_disclosure_facts(ts_code)
            evidence_items.extend(EvidenceItem(**item) for item in disclosure_result.get("evidence", []))
            extra_missing.extend([
                {
                    "key": "announcement_full_text",
                    "label": "公告正文",
                    "reason": ANNOUNCEMENT_LIMIT,
                    "possible_sources": ["公告URL", "PDF正文解析"],
                },
                {
                    "key": "survey_full_text",
                    "label": "调研正文",
                    "reason": SURVEY_LIMIT,
                    "possible_sources": ["公告URL", "调研纪要正文解析"],
                },
            ])
    except Exception as exc:
        extra_missing.append({
            "key": "stage1_auto_facts",
            "label": "阶段1自动事实层",
            "reason": f"阶段1事实层暂不可用: {str(exc)[:120]}",
        })

    snapshot = AnalysisSnapshot(
        analysis_scope=AnalysisScope.SINGLE_STOCK,
        target_symbols=[symbol],
        user_question=user_question,
        market_data_as_of=fetched_at,
        daily_k_as_of=daily_as_of,
        evidence_items=evidence_items,
        missing_data=[*((stock_data.get("data_coverage") or {}).get("missing", [])), *extra_missing],
        system_hypotheses=system_hypotheses,
    )
    if persist:
        write_snapshot(snapshot)
    return snapshot


def write_snapshot(snapshot: AnalysisSnapshot) -> Path:
    root = Path(settings.ANALYSIS_SNAPSHOT_DIR)
    symbol_dir = root / (snapshot.target_symbols[0] if snapshot.target_symbols else "portfolio")
    symbol_dir.mkdir(parents=True, exist_ok=True)
    path = symbol_dir / f"{snapshot.snapshot_id}.json"
    path.write_text(
        json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
