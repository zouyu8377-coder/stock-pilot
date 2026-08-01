from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import requests

from app.portfolio.schemas import PortfolioPosition, PortfolioState


YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
PROVIDER = "yahoo_finance_chart"
SOURCE_ENDPOINT = "v8/finance/chart"
CACHE_TTL = timedelta(minutes=15)
_CHART_CACHE: dict[tuple[str, str, str], tuple[datetime, dict[str, Any]]] = {}
BOUNDARY = (
    "海外科技链指标来自 Yahoo Finance 延迟行情或公开行情聚合接口，仅作为外部风险偏好观察；"
    "不并入账户资产，不构成因果结论、估值结论或交易指令。"
)

TECH_TAGS = {
    "AI",
    "PCB",
    "AI_THEME_ETF",
    "SEMICONDUCTOR",
    "SEMICONDUCTOR_EQUIPMENT",
    "ADVANCED_PACKAGING",
    "MEMORY",
    "HBM",
    "HIGH_VOLATILITY",
}
MEMORY_TAGS = {"MEMORY", "HBM", "SEMICONDUCTOR", "SEMICONDUCTOR_EQUIPMENT", "AI", "AI_THEME_ETF", "PCB"}
MACRO_TAGS = TECH_TAGS | {"GOLD", "COPPER", "TUNGSTEN", "METAL_RESOURCE"}


@dataclass(frozen=True)
class IndicatorConfig:
    symbol: str
    name: str
    market: str
    category: str
    mapping_tags: frozenset[str]
    mapping_reason: str


INDICATORS: tuple[IndicatorConfig, ...] = (
    IndicatorConfig("^NDX", "Nasdaq 100", "US", "US tech risk appetite", frozenset(TECH_TAGS), "纳斯达克 100 代表美国大型成长股风险偏好。"),
    IndicatorConfig("QQQ", "Invesco QQQ ETF", "US", "US tech risk appetite", frozenset(TECH_TAGS), "QQQ 是纳指 100 ETF，可观察可交易资金风险偏好。"),
    IndicatorConfig("^IXIC", "Nasdaq Composite", "US", "US tech risk appetite", frozenset(TECH_TAGS), "纳斯达克综合指数用于观察美国成长股整体氛围。"),
    IndicatorConfig("^GSPC", "S&P 500", "US", "Broad market risk appetite", frozenset(MACRO_TAGS), "标普 500 用于观察美股整体风险偏好。"),
    IndicatorConfig("SPY", "SPDR S&P 500 ETF", "US", "Broad market risk appetite", frozenset(MACRO_TAGS), "SPY 是标普 500 ETF，可作为广谱风险偏好的资金侧参考。"),
    IndicatorConfig("^SOX", "PHLX Semiconductor Index", "US", "Semiconductor chain", frozenset(TECH_TAGS), "SOX 是全球半导体景气与估值情绪的核心风向标。"),
    IndicatorConfig("SOXX", "iShares Semiconductor ETF", "US", "Semiconductor chain", frozenset(TECH_TAGS), "SOXX 观察半导体 ETF 资金偏好。"),
    IndicatorConfig("SMH", "VanEck Semiconductor ETF", "US", "Semiconductor chain", frozenset(TECH_TAGS), "SMH 对先进制程、AI 芯片和设备链权重较高。"),
    IndicatorConfig("NVDA", "NVIDIA", "US", "AI core", frozenset(TECH_TAGS), "NVIDIA 是 AI 算力链需求预期的核心映射指标。"),
    IndicatorConfig("TSM", "TSMC ADR", "US/TW", "AI core", frozenset(TECH_TAGS), "TSMC 反映先进制程与 AI/HPC 代工链景气。"),
    IndicatorConfig("AVGO", "Broadcom", "US", "AI core", frozenset(TECH_TAGS), "Broadcom 对 AI 网络、ASIC 与服务器链预期敏感。"),
    IndicatorConfig("AMD", "AMD", "US", "AI core", frozenset(TECH_TAGS), "AMD 反映 AI 加速卡与 CPU/GPU 竞争链预期。"),
    IndicatorConfig("MU", "Micron", "US", "Memory/HBM", frozenset(MEMORY_TAGS), "Micron 反映 DRAM、NAND、HBM 供需与价格周期。"),
    IndicatorConfig("000660.KS", "SK Hynix", "KR", "Memory/HBM", frozenset(MEMORY_TAGS), "SK Hynix 是 HBM 与存储景气的重要风向标。"),
    IndicatorConfig("005930.KS", "Samsung Electronics", "KR", "Memory/HBM", frozenset(MEMORY_TAGS), "Samsung 反映韩国半导体与存储产业链风险偏好。"),
    IndicatorConfig("^KS11", "KOSPI", "KR", "Korea market", frozenset(MACRO_TAGS), "KOSPI 用于观察韩国大型科技与出口链整体氛围。"),
    IndicatorConfig("^KQ11", "KOSDAQ", "KR", "Korea growth market", frozenset(TECH_TAGS), "KOSDAQ 用于观察韩国成长股和中小科技风险偏好。"),
    IndicatorConfig("^VIX", "CBOE VIX", "US", "Macro risk", frozenset(MACRO_TAGS), "VIX 上行通常代表全球风险厌恶升温。"),
    IndicatorConfig("^TNX", "US 10Y Yield", "US", "Macro risk", frozenset(MACRO_TAGS), "美债 10 年期收益率影响成长股折现率和黄金等资产定价。"),
    IndicatorConfig("DX-Y.NYB", "US Dollar Index", "US", "Macro risk", frozenset(MACRO_TAGS), "美元指数影响全球流动性、资源品和新兴市场风险偏好。"),
    IndicatorConfig("CL=F", "WTI Crude Oil", "US", "Macro risk", frozenset(MACRO_TAGS), "原油用于观察通胀与全球增长预期扰动。"),
    IndicatorConfig("BZ=F", "Brent Crude Oil", "Global", "Macro risk", frozenset(MACRO_TAGS), "Brent 原油用于观察全球通胀和地缘风险扰动。"),
)


class OverseasTechChainError(Exception):
    pass


def _safe_float(value: Any, digits: int = 4) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _pct(curr: float | None, past: float | None) -> float | None:
    if curr is None or past in (None, 0):
        return None
    return round((curr / past - 1) * 100, 2)


def _mean(values: list[float], digits: int = 4) -> float | None:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), digits)


def _provider_time(ts: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def fetch_yahoo_chart(symbol: str, range_days: str = "60d", interval: str = "1d") -> dict[str, Any]:
    cache_key = (symbol, range_days, interval)
    now = datetime.now(timezone.utc)
    cached = _CHART_CACHE.get(cache_key)
    if cached and now - cached[0] <= CACHE_TTL:
        return cached[1]
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        )
    }
    try:
        response = requests.get(
            YAHOO_CHART_URL.format(symbol=symbol),
            params={"range": range_days, "interval": interval},
            headers=headers,
            timeout=8,
        )
    except requests.RequestException as exc:
        raise OverseasTechChainError(f"Yahoo request failed: {exc}") from exc
    if response.status_code != 200:
        raise OverseasTechChainError(f"Yahoo returned HTTP {response.status_code}")
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise OverseasTechChainError(f"Yahoo response is not JSON: {exc}") from exc
    error = payload.get("chart", {}).get("error")
    if error:
        raise OverseasTechChainError(f"Yahoo chart error: {error}")
    _CHART_CACHE[cache_key] = (now, payload)
    return payload


def _parse_closes(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    result = (payload.get("chart", {}).get("result") or [{}])[0]
    if not result:
        raise OverseasTechChainError("Empty Yahoo chart result")
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    rows: list[dict[str, Any]] = []
    for index, ts in enumerate(timestamps):
        close = _safe_float(closes[index] if index < len(closes) else None)
        if close is None:
            continue
        rows.append({
            "timestamp": ts,
            "data_time": _provider_time(ts),
            "close": close,
        })
    if len(rows) < 2:
        raise OverseasTechChainError("Not enough close points")
    meta = result.get("meta") or {}
    return rows, meta


def _position_tags(position: PortfolioPosition) -> set[str]:
    tags = set(position.directions or []) | set(position.theme_tags or []) | set(position.risk_flags or [])
    text = f"{position.name} {position.symbol}".upper()
    if any(key in text for key in ("AI", "PCB", "沪电", "深南", "胜宏", "生益", "工业富联", "中际旭创", "新易盛")):
        tags.add("AI")
        tags.add("PCB")
    if any(key in text for key in ("兆易", "存储", "DRAM", "HBM", "江波龙", "佰维", "澜起")):
        tags.add("MEMORY")
    if any(key in text for key in ("半导体", "芯片", "设备", "北方华创", "中微", "韦尔")):
        tags.add("SEMICONDUCTOR")
    return {str(tag).upper() for tag in tags if tag}


def _is_active(position: PortfolioPosition) -> bool:
    return float(position.quantity or 0) > 0 and (position.market_value or 0) > 0


def _related_holdings(state: PortfolioState, config: IndicatorConfig) -> list[dict[str, Any]]:
    related: list[dict[str, Any]] = []
    config_tags = {tag.upper() for tag in config.mapping_tags}
    weights = {
        str(item.get("symbol", "")): float(item.get("weight_pct") or 0)
        for item in state.metrics.position_weights
    }
    for position in state.snapshot.positions:
        tags = _position_tags(position)
        matched = sorted(tags & config_tags)
        if not matched:
            continue
        related.append({
            "symbol": position.symbol,
            "name": position.name or position.symbol,
            "portfolio_weight_pct": round(weights.get(position.symbol, 0.0), 2),
            "position_status": "active" if _is_active(position) else "watchlist",
            "matched_tags": matched,
        })
    related.sort(key=lambda item: item.get("portfolio_weight_pct") or 0, reverse=True)
    return related[:8]


def _trend_state(latest: float | None, ma5: float | None, ma20: float | None) -> str:
    if latest is None or ma5 is None or ma20 is None:
        return "数据不足"
    if latest >= ma5 and latest >= ma20:
        return "MA20上方 / 短期偏强"
    if latest < ma20:
        return "跌破MA20 / 趋势转弱"
    if latest < ma5:
        return "跌破MA5 / 短期降温"
    return "震荡观察"


def _risk_note(config: IndicatorConfig, item: dict[str, Any]) -> str:
    state = item.get("trend_state") or "数据不足"
    if config.category == "Macro risk":
        if config.symbol == "^VIX":
            return f"波动率指标，{state}；VIX 上行时需关注高波动持仓的同步回撤。"
        return f"宏观风险偏好指标，{state}；用于观察成长股折现率或全球流动性扰动。"
    if config.category in {"Memory/HBM", "Semiconductor chain", "AI core"}:
        return f"{config.category} 风向标，{state}；对 AI/半导体/PCB 映射持仓只作情绪传导观察。"
    return f"海外风险偏好指标，{state}；仅用于观察外部情绪是否与账户高弹性方向共振。"


def _build_indicator(
    config: IndicatorConfig,
    state: PortfolioState,
    fetcher: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    try:
        rows, meta = _parse_closes(fetcher(config.symbol))
    except Exception as exc:
        return {
            "name": config.name,
            "symbol": config.symbol,
            "market": config.market,
            "category": config.category,
            "data_status": "unavailable",
            "missing_reason": str(exc),
            "provider": PROVIDER,
            "source_endpoint_or_method": SOURCE_ENDPOINT,
            "related_holdings": _related_holdings(state, config),
            "mapping_reason": config.mapping_reason,
            "risk_note": "数据暂不可用，不能据此判断海外风险偏好。",
            "interpretation_limit": BOUNDARY,
        }
    closes = [row["close"] for row in rows]
    latest = _safe_float(meta.get("regularMarketPrice")) or closes[-1]
    ma5 = _mean(closes[-5:])
    ma20 = _mean(closes[-20:])
    item = {
        "name": config.name,
        "symbol": config.symbol,
        "market": config.market,
        "category": config.category,
        "latest_price": latest,
        "change_1d_pct": _pct(latest, closes[-2] if len(closes) >= 2 else None),
        "change_5d_pct": _pct(latest, closes[-6] if len(closes) >= 6 else None),
        "change_20d_pct": _pct(latest, closes[-21] if len(closes) >= 21 else None),
        "ma5": ma5,
        "ma20": ma20,
        "relative_ma20_pct": _pct(latest, ma20),
        "trend_state": _trend_state(latest, ma5, ma20),
        "data_time": _provider_time(meta.get("regularMarketTime")) or rows[-1]["data_time"],
        "trade_data_time": rows[-1]["data_time"],
        "currency": meta.get("currency"),
        "data_status": "available",
        "provider": PROVIDER,
        "source_endpoint_or_method": SOURCE_ENDPOINT,
        "quote_delay_status": "delayed_or_unverified",
        "related_holdings": _related_holdings(state, config),
        "mapping_reason": config.mapping_reason,
        "interpretation_limit": BOUNDARY,
    }
    item["risk_note"] = _risk_note(config, item)
    return item


def _tech_growth_exposure_pct(state: PortfolioState) -> float:
    total_assets = state.metrics.total_assets or state.metrics.total_market_value or 0
    if total_assets <= 0:
        return 0.0
    exposure = 0.0
    for position in state.snapshot.positions:
        if not _is_active(position):
            continue
        if _position_tags(position) & TECH_TAGS:
            exposure += float(position.market_value or 0)
    return round(exposure / total_assets * 100, 2)


def _risk_level(indicators: list[dict[str, Any]], tech_exposure_pct: float) -> dict[str, Any]:
    by_symbol = {item.get("symbol"): item for item in indicators}
    watch = [by_symbol.get(symbol) for symbol in ("^SOX", "^NDX", "000660.KS", "MU")]
    watch = [item for item in watch if item and item.get("data_status") == "available"]
    same_day_stress = [
        item for item in watch
        if (item.get("change_1d_pct") is not None and item["change_1d_pct"] <= -2)
        and item.get("latest_price") is not None
        and item.get("ma5") is not None
        and item["latest_price"] < item["ma5"]
    ]
    ma20_breaks = [
        item for item in watch
        if item.get("latest_price") is not None
        and item.get("ma20") is not None
        and item["latest_price"] < item["ma20"]
    ]
    if len(ma20_breaks) >= 4 and tech_exposure_pct > 70:
        level = "Extreme"
        judgment = "海外 AI/半导体核心指标同步跌破 MA20，且账户科技成长暴露高，进入极端联动观察。"
    elif len(same_day_stress) >= 3:
        level = "High"
        judgment = "SOX / Nasdaq / SK Hynix / Micron 中至少 3 个出现单日大跌并跌破 MA5，海外链路压力较高。"
    elif any(item.get("latest_price") is not None and item.get("ma5") is not None and item["latest_price"] < item["ma5"] for item in watch):
        level = "Medium"
        judgment = "部分海外半导体或 AI 指标跌破 MA5，但尚未形成核心指标同步破位。"
    else:
        level = "Low"
        judgment = "多数核心指标未触发同步转弱条件，海外风险偏好暂未显示系统性压力。"
    return {
        "level": level,
        "judgment": judgment,
        "tech_growth_exposure_pct": tech_exposure_pct,
        "triggered_symbols": [item.get("symbol") for item in same_day_stress],
        "ma20_break_symbols": [item.get("symbol") for item in ma20_breaks],
        "rule_version": "overseas_tech_chain_risk_v1",
    }


def _sensitivity_summary(state: PortfolioState, indicators: list[dict[str, Any]], tech_exposure_pct: float) -> dict[str, Any]:
    related: dict[str, dict[str, Any]] = {}
    for item in indicators:
        for holding in item.get("related_holdings") or []:
            symbol = holding["symbol"]
            entry = related.setdefault(symbol, {
                "symbol": symbol,
                "name": holding.get("name") or symbol,
                "portfolio_weight_pct": holding.get("portfolio_weight_pct"),
                "matched_indicators": [],
                "matched_tags": set(),
            })
            entry["matched_indicators"].append(item.get("symbol"))
            entry["matched_tags"].update(holding.get("matched_tags") or [])
    holdings = []
    for entry in related.values():
        entry["matched_indicators"] = sorted(set(entry["matched_indicators"]))
        entry["matched_tags"] = sorted(entry["matched_tags"])
        holdings.append(entry)
    holdings.sort(key=lambda item: item.get("portfolio_weight_pct") or 0, reverse=True)
    return {
        "tech_growth_exposure_pct": tech_exposure_pct,
        "sensitive_holdings": holdings[:10],
        "summary": (
            f"账户科技成长相关暴露约 {tech_exposure_pct:.2f}%，海外 AI/半导体/存储链指标"
            "主要映射到上述敏感持仓；该映射用于观察风险偏好传导，不代表因果关系。"
        ),
    }


def _leading_signals(indicators: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = []
    for item in indicators:
        if item.get("symbol") in {"^SOX", "^NDX", "NVDA", "TSM", "MU", "000660.KS", "^VIX", "^TNX", "DX-Y.NYB"}:
            selected.append({
                "symbol": item.get("symbol"),
                "name": item.get("name"),
                "change_1d_pct": item.get("change_1d_pct"),
                "change_5d_pct": item.get("change_5d_pct"),
                "relative_ma20_pct": item.get("relative_ma20_pct"),
                "trend_state": item.get("trend_state"),
                "data_status": item.get("data_status"),
            })
    return selected


def _event_watchlist() -> list[dict[str, Any]]:
    return [
        {
            "group": "AI semiconductor earnings",
            "items": ["NVIDIA earnings / GTC / product release", "Broadcom earnings", "AMD earnings", "ASML earnings"],
            "observation": "观察 AI 算力、网络、先进制程与半导体设备链的需求指引变化。",
            "schedule_status": "date_to_be_verified",
        },
        {
            "group": "Foundry and memory cycle",
            "items": ["TSMC monthly revenue / earnings", "Micron earnings", "SK Hynix earnings", "Samsung Electronics earnings"],
            "observation": "观察先进制程、HBM/DRAM/NAND 供需和 AI 服务器链景气。",
            "schedule_status": "date_to_be_verified",
        },
        {
            "group": "Hyperscaler capex",
            "items": ["Microsoft earnings", "Alphabet earnings", "Amazon earnings", "Meta earnings"],
            "observation": "观察云厂商 AI 资本开支、数据中心建设和服务器链需求。",
            "schedule_status": "date_to_be_verified",
        },
        {
            "group": "Macro risk appetite",
            "items": ["US CPI", "US PCE", "US nonfarm payrolls", "FOMC", "US 10Y yield", "DXY", "WTI / Brent crude"],
            "observation": "观察利率、美元、通胀和油价对全球风险偏好及成长股折现率的扰动。",
            "schedule_status": "macro_calendar_or_market_data",
        },
    ]


def build_overseas_tech_chain(
    state: PortfolioState,
    *,
    fetcher: Callable[[str], dict[str, Any]] | None = None,
    max_workers: int = 6,
) -> dict[str, Any]:
    fetcher = fetcher or fetch_yahoo_chart
    generated_at = datetime.now(timezone.utc).isoformat()
    indicators: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_build_indicator, config, state, fetcher): index
            for index, config in enumerate(INDICATORS)
        }
        results: dict[int, dict[str, Any]] = {}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    indicators = [results[index] for index in sorted(results)]
    tech_exposure_pct = _tech_growth_exposure_pct(state)
    risk = _risk_level(indicators, tech_exposure_pct)
    sensitivity = _sensitivity_summary(state, indicators, tech_exposure_pct)
    stress_count = len(risk.get("triggered_symbols") or [])
    if stress_count:
        open_observation = (
            "海外 AI/半导体链出现同步压力，A 股开盘后前 30-60 分钟优先观察 PCB、AI ETF、"
            "半导体和存储相关持仓是否跟随放量走弱；该提示仅为观察顺序，不是交易指令。"
        )
    else:
        open_observation = (
            "海外链路未触发同步压力条件，A 股开盘仍需观察高弹性持仓是否与海外科技链方向一致；"
            "该提示仅为情绪传导观察。"
        )
    return {
        "generated_at": generated_at,
        "provider": PROVIDER,
        "source_endpoint_or_method": SOURCE_ENDPOINT,
        "data_status": "available" if any(item.get("data_status") == "available" for item in indicators) else "unavailable",
        "indicator_count": len(indicators),
        "available_indicator_count": sum(1 for item in indicators if item.get("data_status") == "available"),
        "indicators": indicators,
        "overseas_indicators": indicators,
        "account_sensitivity_summary": sensitivity,
        "overseas_sensitivity": sensitivity,
        "risk_level": risk,
        "open_sentiment_observation": open_observation,
        "sentiment_path": [
            "US tech / semiconductor close",
            "Korea memory / growth board",
            "A-share open first 30-60 minutes",
            "PCB / AI ETF / semiconductor / memory mapped holdings",
        ],
        "leading_signals": _leading_signals(indicators),
        "event_watchlist": _event_watchlist(),
        "boundary": BOUNDARY,
    }
