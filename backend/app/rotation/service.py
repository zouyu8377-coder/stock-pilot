from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.portfolio.service import portfolio_service

APP_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = APP_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
BASE_MARKET_DIR = DATA_DIR / "base_market"
CACHE_DIR = DATA_DIR / "cache"
UNIVERSE_PATH = Path(__file__).resolve().parent / "rotation_universe.json"
CACHE_PATH = CACHE_DIR / "rotation_radar.json"
HISTORY_PATH = CACHE_DIR / "rotation_history.json"
STATUS_PATH = CACHE_DIR / "rotation_status.json"
STOCK_META_PATH = DATA_DIR / "metadata" / "stock_meta.parquet"
ETF_META_PATH = DATA_DIR / "metadata" / "etf_meta.parquet"
_SECURITY_META: dict[str, dict[str, Any]] | None = None


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_universe() -> dict[str, Any]:
    universe = _read_json(UNIVERSE_PATH, {})
    sectors = universe.get("sectors") or []
    benchmarks = universe.get("benchmarks") or []
    return {
        "version": universe.get("version", "unknown"),
        "benchmarks": benchmarks,
        "sectors": sectors,
        "items": benchmarks + sectors,
    }


def _baostock_code(symbol: str) -> str:
    symbol = str(symbol).split(".")[0]
    exchange = "sh" if symbol.startswith(("5", "6", "9")) else "sz"
    return f"{exchange}.{symbol}"


def _load_symbol_frame(symbol: str) -> pd.DataFrame:
    path = BASE_MARKET_DIR / f"{_baostock_code(symbol)}.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    if "date" not in df.columns or "close" not in df.columns:
        return pd.DataFrame()
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    for col in ["close", "amount", "volume"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
        else:
            out[col] = None
    out = out.dropna(subset=["date", "close"]).sort_values("date")
    return out[["date", "close", "amount", "volume"]].tail(260).reset_index(drop=True)


def _load_proxy_frame(item: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    if item.get("proxy_type") == "synthetic":
        parts = []
        component_status = []
        for component in item.get("components", []):
            symbol = str(component.get("symbol", ""))
            weight = float(component.get("weight") or 0)
            frame = _load_symbol_frame(symbol)
            if frame.empty:
                component_status.append({"symbol": symbol, "status": "missing"})
                continue
            series = frame.set_index("date")
            returns = series["close"].pct_change().fillna(0)
            part = pd.DataFrame(
                {
                    f"ret_{symbol}": returns,
                    f"amount_{symbol}": series["amount"],
                    f"volume_{symbol}": series["volume"],
                }
            )
            part.attrs["weight"] = weight
            parts.append(part)
            component_status.append(
                {
                    "symbol": symbol,
                    "status": "available",
                    "latest_date": str(frame["date"].max()),
                    "rows": int(len(frame)),
                }
            )
        if not parts:
            return pd.DataFrame(), {"component_status": component_status}
        joined = pd.concat(parts, axis=1).sort_index()
        ret_cols = [col for col in joined.columns if col.startswith("ret_")]
        amount_cols = [col for col in joined.columns if col.startswith("amount_")]
        volume_cols = [col for col in joined.columns if col.startswith("volume_")]
        weighted = []
        for col in ret_cols:
            symbol = col.replace("ret_", "")
            weight = next((float(c.get("weight") or 0) for c in item.get("components", []) if str(c.get("symbol")) == symbol), 0)
            weighted.append(joined[col] * weight)
        returns = pd.concat(weighted, axis=1).sum(axis=1, min_count=max(1, math.ceil(len(ret_cols) / 2)))
        level = (1 + returns.fillna(0)).cumprod() * 100
        out = pd.DataFrame(
            {
                "date": joined.index,
                "close": level,
                "amount": joined[amount_cols].sum(axis=1, min_count=1) if amount_cols else None,
                "volume": joined[volume_cols].sum(axis=1, min_count=1) if volume_cols else None,
            }
        ).dropna(subset=["close"]).reset_index(drop=True)
        return out, {"component_status": component_status}

    symbols = [item.get("primary_symbol")] + list(item.get("backup_symbols") or [])
    tried = []
    for symbol in [str(s) for s in symbols if s]:
        frame = _load_symbol_frame(symbol)
        tried.append({"symbol": symbol, "available": not frame.empty})
        if not frame.empty:
            return frame, {"selected_symbol": symbol, "proxy_candidates": tried}
    return pd.DataFrame(), {"proxy_candidates": tried}


def _pct_change(frame: pd.DataFrame, days: int) -> float | None:
    if len(frame) <= days:
        return None
    latest = float(frame["close"].iloc[-1])
    base = float(frame["close"].iloc[-days - 1])
    if not base:
        return None
    return round((latest / base - 1) * 100, 2)


def _ma(frame: pd.DataFrame, days: int) -> float | None:
    if len(frame) < days:
        return None
    return float(frame["close"].tail(days).mean())


def _ratio(latest: float | None, base: float | None) -> float | None:
    if latest is None or base in (None, 0):
        return None
    return round((latest / base - 1) * 100, 2)


def _security_meta() -> dict[str, dict[str, Any]]:
    global _SECURITY_META
    if _SECURITY_META is not None:
        return _SECURITY_META
    result: dict[str, dict[str, Any]] = {}
    for path, asset_type in [(STOCK_META_PATH, "stock"), (ETF_META_PATH, "etf")]:
        if not path.exists():
            continue
        frame = pd.read_parquet(path)
        for row in frame.to_dict("records"):
            symbol = str(row.get("symbol") or "").split(".")[0].zfill(6)
            if symbol:
                result[symbol] = {
                    "name": row.get("name") or symbol,
                    "asset_type": asset_type,
                    "industry": row.get("industry"),
                }
    _SECURITY_META = result
    return result


def _annualized_volatility(frame: pd.DataFrame, days: int = 20) -> float | None:
    values = frame["close"].pct_change().dropna().tail(days)
    if len(values) < max(5, days // 2):
        return None
    return round(float(values.std(ddof=0) * math.sqrt(252) * 100), 2)


def _max_drawdown(frame: pd.DataFrame, days: int = 60) -> float | None:
    values = frame["close"].dropna().tail(days)
    if len(values) < 5:
        return None
    drawdown = values / values.cummax() - 1
    return round(float(drawdown.min() * 100), 2)


def _relative_win_rate(frame: pd.DataFrame, benchmark_frame: pd.DataFrame, days: int = 60, window: int = 5) -> float | None:
    if frame.empty or benchmark_frame.empty:
        return None
    aligned = frame[["date", "close"]].merge(
        benchmark_frame[["date", "close"]],
        on="date",
        suffixes=("_sector", "_benchmark"),
    )
    if len(aligned) <= window:
        return None
    sector_returns = aligned["close_sector"].pct_change(window)
    benchmark_returns = aligned["close_benchmark"].pct_change(window)
    valid = sector_returns.notna() & benchmark_returns.notna()
    comparisons = (sector_returns[valid] > benchmark_returns[valid]).tail(days)
    if comparisons.empty:
        return None
    return round(float(comparisons.mean() * 100), 2)


def _trend_state(latest: float, ma20: float | None, ma60: float | None) -> str:
    if ma20 is None or ma60 is None:
        return "数据不足"
    if latest >= ma20 >= ma60:
        return "多头排列"
    if latest >= ma20 and ma20 < ma60:
        return "修复中"
    if latest < ma20 and ma20 >= ma60:
        return "短线转弱"
    return "空头结构"


def _security_research(symbol: str, role: str, benchmark_frame: pd.DataFrame) -> dict[str, Any]:
    frame = _load_symbol_frame(symbol)
    meta = _security_meta().get(symbol, {})
    base = {
        "symbol": symbol,
        "name": meta.get("name") or symbol,
        "asset_type": meta.get("asset_type") or ("etf" if symbol.startswith(("5", "15")) else "stock"),
        "industry": meta.get("industry"),
        "role": role,
        "data_quality": "unavailable" if frame.empty else "available",
    }
    if frame.empty:
        return base
    latest = float(frame["close"].iloc[-1])
    ma20 = _ma(frame, 20)
    ma60 = _ma(frame, 60)
    return_20d = _pct_change(frame, 20)
    benchmark_20d = _pct_change(benchmark_frame, 20) if not benchmark_frame.empty else None
    amount_5 = frame["amount"].tail(5).mean()
    amount_20 = frame["amount"].tail(20).mean()
    return {
        **base,
        "latest_date": str(frame["date"].iloc[-1]),
        "latest_close": round(latest, 4),
        "returns": {f"return_{days}d": _pct_change(frame, days) for days in [1, 5, 20, 60]},
        "relative_strength_20d": (
            round(float(return_20d) - float(benchmark_20d), 2)
            if return_20d is not None and benchmark_20d is not None
            else None
        ),
        "ma20_distance_pct": _ratio(latest, ma20),
        "above_ma20": latest >= ma20 if ma20 is not None else None,
        "above_ma60": latest >= ma60 if ma60 is not None else None,
        "trend_state": _trend_state(latest, ma20, ma60),
        "amount_ratio_5d": _ratio(
            float(amount_5) if pd.notna(amount_5) else None,
            float(amount_20) if pd.notna(amount_20) else None,
        ),
        "volatility_20d": _annualized_volatility(frame),
        "max_drawdown_60d": _max_drawdown(frame),
    }


def _normalized_trend_series(frame: pd.DataFrame, benchmark_frame: pd.DataFrame, days: int = 120) -> list[dict[str, Any]]:
    if frame.empty or benchmark_frame.empty:
        return []
    aligned = frame[["date", "close"]].merge(
        benchmark_frame[["date", "close"]],
        on="date",
        suffixes=("_sector", "_benchmark"),
    ).tail(days)
    if aligned.empty:
        return []
    sector_base = float(aligned["close_sector"].iloc[0])
    benchmark_base = float(aligned["close_benchmark"].iloc[0])
    if not sector_base or not benchmark_base:
        return []
    return [
        {
            "date": str(row.date),
            "sector": round(float(row.close_sector) / sector_base * 100, 2),
            "benchmark": round(float(row.close_benchmark) / benchmark_base * 100, 2),
        }
        for row in aligned.itertuples(index=False)
    ]


def _percentage(values: list[bool]) -> float | None:
    return round(sum(values) / len(values) * 100, 2) if values else None


def _sector_evidence_analysis(
    sector: dict[str, Any],
    breadth: dict[str, Any],
    objective: dict[str, Any],
) -> dict[str, Any]:
    supports: list[str] = []
    cautions: list[str] = []
    above_ma20 = breadth.get("above_ma20_pct")
    outperform = breadth.get("outperform_hs300_20d_pct")
    win_rate = objective.get("relative_win_rate_5d")
    amount_ratio = sector.get("flow", {}).get("amount_ratio_5d")
    volatility = objective.get("volatility_20d")
    drawdown = objective.get("max_drawdown_60d")
    dispersion = breadth.get("return_dispersion_20d")

    if sector.get("ma20_distance_pct") is not None and sector["ma20_distance_pct"] >= 0:
        supports.append(f"方向代理价格位于 MA20 上方 {sector['ma20_distance_pct']:.1f}%")
    else:
        cautions.append("方向代理价格尚未站稳 MA20")
    if above_ma20 is not None:
        target = supports if above_ma20 >= 60 else cautions
        target.append(f"代表股中 {above_ma20:.0f}% 位于 MA20 上方")
    if outperform is not None:
        target = supports if outperform >= 60 else cautions
        target.append(f"代表股中 {outperform:.0f}% 的 20 日表现跑赢沪深300")
    if win_rate is not None:
        target = supports if win_rate >= 55 else cautions
        target.append(f"过去 60 日滚动 5 日跑赢沪深300的比例为 {win_rate:.0f}%")
    if amount_ratio is not None:
        target = supports if amount_ratio >= 0 else cautions
        target.append(f"近 5 日成交额较 20 日均值{'增加' if amount_ratio >= 0 else '减少'} {abs(amount_ratio):.1f}%")
    if volatility is not None and volatility >= 35:
        cautions.append(f"20 日年化波动率 {volatility:.1f}%，波动偏高")
    if drawdown is not None and drawdown <= -15:
        cautions.append(f"近 60 日最大回撤 {drawdown:.1f}%，回撤控制较弱")
    if dispersion is not None and dispersion >= 12:
        cautions.append(f"代表股 20 日收益离散度 {dispersion:.1f}%，内部走势分化")

    coverage = int(breadth.get("available_count") or 0)
    total = int(breadth.get("constituent_count") or 0)
    confidence = "高" if total and coverage == total and len(supports) >= 3 else "中" if coverage >= max(2, total // 2) else "低"
    stage = sector.get("opportunity_stage")
    if stage == "potential_opportunity" and (above_ma20 or 0) >= 60:
        conclusion = "方向强度已获得多数代表股确认，可继续研究，但仍需等待具体标的出现合适价格。"
    elif stage in {"potential_opportunity", "early_turning"}:
        conclusion = "方向代理开始转强，但成分扩散尚不充分，应先验证龙头持续性，避免把单一 ETF 上涨误判为行业机会。"
    elif stage == "wait_pullback":
        conclusion = "中期强度仍在，但短期位置或波动不利，等待回踩和成交额重新确认更稳妥。"
    else:
        conclusion = "当前支持证据不足，方向暂时只保留观察，不宜因单日涨幅提高优先级。"
    return {
        "method": "规则综合判断，不调用大模型",
        "confidence": confidence,
        "conclusion": conclusion,
        "supports": supports,
        "cautions": cautions,
    }


def _base_factors(item: dict[str, Any], frame: pd.DataFrame, benchmark_frame: pd.DataFrame, market_latest: str | None) -> dict[str, Any]:
    latest_close = float(frame["close"].iloc[-1])
    latest_date = str(frame["date"].max())
    ma_values = {f"ma{d}": _ma(frame, d) for d in [5, 10, 20, 30, 60]}
    returns = {f"return_{d}d": _pct_change(frame, d) for d in [1, 5, 10, 20, 60]}
    bench_returns = {f"benchmark_return_{d}d": _pct_change(benchmark_frame, d) if not benchmark_frame.empty else None for d in [5, 20, 60]}
    rel = {
        f"relative_strength_{d}d": (
            round((returns.get(f"return_{d}d") or 0) - (bench_returns.get(f"benchmark_return_{d}d") or 0), 2)
            if returns.get(f"return_{d}d") is not None and bench_returns.get(f"benchmark_return_{d}d") is not None
            else None
        )
        for d in [5, 20, 60]
    }
    amount_5 = frame["amount"].tail(5).mean() if "amount" in frame else None
    amount_20 = frame["amount"].tail(20).mean() if "amount" in frame else None
    volume_5 = frame["volume"].tail(5).mean() if "volume" in frame else None
    volume_20 = frame["volume"].tail(20).mean() if "volume" in frame else None
    stale_days = None
    if market_latest:
      stale_days = (pd.to_datetime(market_latest) - pd.to_datetime(latest_date)).days
    missing = [k for k, v in {**returns, **ma_values, **rel}.items() if v is None]
    quality = "available"
    if frame.empty:
        quality = "unavailable"
    elif missing:
        quality = "partial"
    if stale_days is not None and stale_days >= 2:
        quality = "stale" if quality == "available" else quality
    return {
        "sector_id": item["sector_id"],
        "name": item["name"],
        "category": item.get("category", ""),
        "proxy_type": item.get("proxy_type", "etf"),
        "primary_symbol": item.get("primary_symbol"),
        "selected_symbol": item.get("_selected_symbol") or item.get("primary_symbol"),
        "proxy_components": item.get("components") or (
            [
                {
                    "symbol": item.get("_selected_symbol") or item.get("primary_symbol"),
                    "name": item.get("name"),
                    "weight": 1,
                }
            ]
            if item.get("_selected_symbol") or item.get("primary_symbol")
            else []
        ),
        "ranking_enabled": bool(item.get("ranking_enabled", True)),
        "latest_date": latest_date,
        "latest_close": round(latest_close, 4),
        "returns": returns,
        "moving_averages": {k: round(v, 4) if v is not None else None for k, v in ma_values.items()},
        "benchmark": {
            "sector_id": "hs300",
            "symbol": "510300",
            "returns": bench_returns,
        },
        "relative_strength": rel,
        "flow": {
            "amount_ratio_5d": _ratio(float(amount_5) if pd.notna(amount_5) else None, float(amount_20) if pd.notna(amount_20) else None),
            "volume_ratio_5d": _ratio(float(volume_5) if pd.notna(volume_5) else None, float(volume_20) if pd.notna(volume_20) else None),
            "etf_share_change_5d": None,
        },
        "data_quality": quality,
        "missing_fields": missing + ["etf_share_change_5d"],
        "stale_days_to_market": stale_days,
    }


def _bounded_score(value: float | None, low: float, high: float, weight: float) -> float:
    if value is None:
        return 0
    if high == low:
        return 0
    raw = (value - low) / (high - low)
    return max(0, min(1, raw)) * weight


def _trend_score(f: dict[str, Any]) -> float:
    price = f["latest_close"]
    ma = f["moving_averages"]
    checks = [
        (price > (ma.get("ma5") or math.inf), 4),
        (price > (ma.get("ma20") or math.inf), 7),
        (price > (ma.get("ma60") or math.inf), 8),
        ((ma.get("ma5") or 0) > (ma.get("ma20") or math.inf), 3),
        ((ma.get("ma20") or 0) > (ma.get("ma60") or math.inf), 3),
    ]
    return round(sum(weight for ok, weight in checks if ok), 2)


def _percentile_scores(items: list[dict[str, Any]], key_path: tuple[str, str], target: str, weight: float) -> None:
    values = []
    for item in items:
        value = item.get(key_path[0], {}).get(key_path[1])
        if value is not None:
            values.append((item["sector_id"], float(value)))
    if not values:
        for item in items:
            item[target] = 0
        return
    ordered = sorted(values, key=lambda pair: pair[1])
    denom = max(len(ordered) - 1, 1)
    pct = {sector_id: rank / denom for rank, (sector_id, _) in enumerate(ordered)}
    for item in items:
        item[target] = round(pct.get(item["sector_id"], 0.0) * weight, 2)


def _apply_scores(items: list[dict[str, Any]]) -> None:
    ranking = [item for item in items if item.get("ranking_enabled")]
    for item in items:
        item["score"] = {
            "trend": _trend_score(item),
            "momentum": 0,
            "relative_strength": 0,
            "flow": 0,
            "total": 0,
        }
    for path, target, weight in [
        (("returns", "return_5d"), "_mom_5", 8),
        (("returns", "return_10d"), "_mom_10", 7),
        (("returns", "return_20d"), "_mom_20", 10),
        (("relative_strength", "relative_strength_5d"), "_rs_5", 7),
        (("relative_strength", "relative_strength_20d"), "_rs_20", 11),
        (("relative_strength", "relative_strength_60d"), "_rs_60", 7),
        (("flow", "amount_ratio_5d"), "_flow_amount", 15),
        (("flow", "volume_ratio_5d"), "_flow_volume", 10),
    ]:
        _percentile_scores(ranking, path, target, weight)
    for item in items:
        if not item.get("ranking_enabled"):
            continue
        momentum = item.pop("_mom_5", 0) + item.pop("_mom_10", 0) + item.pop("_mom_20", 0)
        relative = item.pop("_rs_5", 0) + item.pop("_rs_20", 0) + item.pop("_rs_60", 0)
        flow = item.pop("_flow_amount", 0) + item.pop("_flow_volume", 0)
        score = item["score"]
        score["momentum"] = round(momentum, 2)
        score["relative_strength"] = round(relative, 2)
        score["flow"] = round(flow, 2)
        score["total"] = round(score["trend"] + momentum + relative + flow, 2)
    for item in items:
        for key in list(item.keys()):
            if key.startswith("_"):
                item.pop(key, None)


def _load_history() -> list[dict[str, Any]]:
    history = _read_json(HISTORY_PATH, [])
    return history if isinstance(history, list) else []


def _attach_history(items: list[dict[str, Any]], history: list[dict[str, Any]]) -> None:
    by_sector: dict[str, list[dict[str, Any]]] = {}
    for record in history:
        by_sector.setdefault(record.get("sector_id"), []).append(record)
    for records in by_sector.values():
        records.sort(key=lambda r: r.get("trade_date") or "")
    for item in items:
        records = [r for r in by_sector.get(item["sector_id"], []) if r.get("trade_date") != item.get("latest_date")]
        last = records[-1] if records else None
        item["score_delta_1d"] = round(item["score"]["total"] - float(last.get("total_score", 0)), 2) if last else None
        item["score_delta_5d"] = item["score_delta_1d"]
        item["score_delta_10d"] = item["score_delta_1d"]


def _classify_maturity(item: dict[str, Any]) -> str:
    score = item["score"]
    total = score["total"]
    delta = item.get("score_delta_5d")
    price = item["latest_close"]
    ma20 = item["moving_averages"].get("ma20")
    rel20 = item["relative_strength"].get("relative_strength_20d")
    if total >= 75 and score["trend"] >= 18 and score["relative_strength"] >= 16:
        return "leading"
    if total >= 65 and (delta is None or delta >= 0):
        return "spreading"
    if 45 <= total < 70 and (delta is None or delta > 0) and (ma20 is None or price >= ma20) and (rel20 is None or rel20 >= -2):
        return "emerging"
    if total < 45 or ((ma20 is not None and price < ma20) and (rel20 is not None and rel20 < 0)):
        return "declining"
    if total >= 55 and delta is not None and delta < 0:
        return "cooling"
    return "neutral"


def _ma_distance_pct(item: dict[str, Any]) -> float | None:
    price = item.get("latest_close")
    ma20 = item.get("moving_averages", {}).get("ma20")
    if price is None or not ma20:
        return None
    return round((float(price) / float(ma20) - 1) * 100, 2)


def _classify_opportunity(item: dict[str, Any]) -> dict[str, Any]:
    if item.get("data_quality") == "unavailable":
        return {
            "stage": "avoid_now",
            "label": "暂不参与",
            "chasing_risk": "unknown",
            "reason": "代理标的行情缺失，暂不纳入机会判断。",
        }
    score = item["score"]
    total = float(score.get("total") or 0)
    trend = float(score.get("trend") or 0)
    flow = float(score.get("flow") or 0)
    returns = item.get("returns", {})
    rel = item.get("relative_strength", {})
    return_5d = returns.get("return_5d")
    return_20d = returns.get("return_20d")
    rel20 = rel.get("relative_strength_20d")
    price = item.get("latest_close")
    ma20 = item.get("moving_averages", {}).get("ma20")
    ma_distance = _ma_distance_pct(item)

    chasing_risk = "low"
    risk_reasons = []
    if return_5d is not None and return_5d >= 10:
        chasing_risk = "high"
        risk_reasons.append("5日涨幅过快")
    if ma_distance is not None and ma_distance >= 12:
        chasing_risk = "high"
        risk_reasons.append("价格偏离MA20较大")
    if chasing_risk != "high" and ((return_5d is not None and return_5d >= 6) or (ma_distance is not None and ma_distance >= 8)):
        chasing_risk = "medium"
        risk_reasons.append("短期位置偏热")
    if return_20d is not None and return_20d >= 18 and return_5d is not None and return_5d < 0:
        chasing_risk = "medium" if chasing_risk == "low" else chasing_risk
        risk_reasons.append("中期涨幅后短线转弱")

    above_ma20 = ma20 is None or (price is not None and price >= ma20)
    rel_ok = rel20 is None or rel20 >= 0
    rel_repairing = rel20 is None or rel20 >= -2

    if total >= 58 and trend >= 10 and above_ma20 and rel_ok and chasing_risk != "high":
        return {
            "stage": "potential_opportunity",
            "label": "潜在机会",
            "chasing_risk": chasing_risk,
            "reason": "趋势、相对强度和量能已有确认，且短期追高风险未进入高位。",
        }
    if 42 <= total < 68 and above_ma20 and rel_repairing and (flow >= 10 or (return_5d is not None and return_5d > -3)):
        return {
            "stage": "early_turning",
            "label": "早期转强",
            "chasing_risk": chasing_risk,
            "reason": "总分未到强势区，但价格位置和相对表现开始修复，适合进入观察池。",
        }
    if total >= 62 and chasing_risk in {"medium", "high"}:
        return {
            "stage": "wait_pullback",
            "label": "强势但等回踩",
            "chasing_risk": chasing_risk,
            "reason": "方向强度已确认，但短期位置偏热，适合等待分歧或回踩验证。",
        }
    reason = "趋势、相对强度或量能尚未形成足够确认。"
    if risk_reasons:
        reason = f"{reason} {'；'.join(risk_reasons)}。"
    return {
        "stage": "avoid_now",
        "label": "暂不参与",
        "chasing_risk": chasing_risk,
        "reason": reason,
    }


def _position_value(position: dict[str, Any]) -> float:
    for key in ["market_value", "broker_screenshot_market_value"]:
        value = position.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    return 0.0


def _portfolio_context(items: list[dict[str, Any]], universe_items: list[dict[str, Any]]) -> None:
    try:
        state = portfolio_service.get_state()
        snapshot = state.snapshot.model_dump()
        metrics = state.metrics.model_dump()
    except Exception:
        snapshot = {"positions": []}
        metrics = {"total_assets": 0}
    total_assets = float(metrics.get("total_assets") or 0)
    positions = snapshot.get("positions") or []
    config = {item["sector_id"]: item for item in universe_items}
    for item in items:
        rule = config.get(item["sector_id"], {})
        main_symbols = set(rule.get("main_symbols") or [])
        weak_symbols = set(rule.get("weak_symbols") or [])
        main_tags = set(rule.get("main_holding_tags") or [])
        weak_tags = set(rule.get("weak_holding_tags") or [])
        related = []
        exposure = 0.0
        for position in positions:
            symbol = str(position.get("symbol") or "")
            tags = set(position.get("theme_tags") or []) | set(position.get("directions") or []) | set(position.get("risk_flags") or [])
            relation = None
            if symbol in main_symbols or tags.intersection(main_tags):
                relation = "main"
                exposure += _position_value(position)
            elif symbol in weak_symbols or tags.intersection(weak_tags):
                relation = "weak"
            if relation:
                related.append(
                    {
                        "symbol": symbol,
                        "name": position.get("name") or symbol,
                        "relation": relation,
                        "market_value": _position_value(position),
                        "position_role": position.get("position_role"),
                    }
                )
        exposure_pct = round(exposure / total_assets * 100, 2) if total_assets else 0
        maturity = item.get("maturity")
        relation = "neutral"
        if exposure_pct >= 15 and maturity in {"cooling", "declining"}:
            relation = "heavy_and_cooling"
        elif exposure_pct >= 15 and maturity in {"leading", "spreading"}:
            relation = "heavy_and_leading"
        elif exposure_pct <= 5 and maturity in {"leading", "spreading"}:
            relation = "underexposed_and_strengthening"
        elif exposure_pct == 0 and maturity == "emerging":
            relation = "unallocated_and_emerging"
        elif related and exposure_pct == 0:
            relation = "watch_position"
        item["account_exposure"] = {
            "main_exposure_value": round(exposure, 2),
            "main_exposure_pct": exposure_pct,
            "related_holdings": related,
            "relation": relation,
            "mapping_rule": "main_relations_count_into_exposure; weak_relations_only_for_observation",
        }


def _persist_history(items: list[dict[str, Any]]) -> None:
    history = _load_history()
    keys = {(item["sector_id"], item["latest_date"]) for item in items if item.get("ranking_enabled")}
    history = [record for record in history if (record.get("sector_id"), record.get("trade_date")) not in keys]
    for item in items:
        if not item.get("ranking_enabled"):
            continue
        history.append(
            {
                "trade_date": item["latest_date"],
                "sector_id": item["sector_id"],
                "total_score": item["score"]["total"],
                "maturity": item["maturity"],
                "updated_at": _now_iso(),
            }
        )
    history.sort(key=lambda r: (r.get("trade_date") or "", r.get("sector_id") or ""))
    _write_json(HISTORY_PATH, history[-2000:])


def _status_payload(status: str, items: list[dict[str, Any]], errors: list[str], as_of: str | None) -> dict[str, Any]:
    total = len([item for item in items if item.get("ranking_enabled")])
    failed = len([item for item in items if item.get("data_quality") == "unavailable"])
    stale = len([item for item in items if item.get("ranking_enabled") and item.get("data_quality") == "stale"])
    completed = max(total - failed, 0)
    return {
        "status": status,
        "provider": "local_rotation_cache",
        "target_date": as_of,
        "last_trading_date": as_of,
        "completed_count": completed,
        "failed_count": failed,
        "stale_count": stale,
        "total_symbols": total,
        "remaining_count": 0,
        "processed_count": total,
        "progress": round(completed / total * 100, 2) if total else 0,
        "updated_at": _now_iso(),
        "failure_reasons": {"unavailable": failed} if failed else {},
        "phase": "rotation_snapshot",
        "errors": errors[:10],
    }


def build_rotation_bundle() -> dict[str, Any]:
    universe = load_universe()
    raw_items = universe["items"]
    frames: dict[str, pd.DataFrame] = {}
    metadata: dict[str, dict[str, Any]] = {}
    latest_dates = []
    for item in raw_items:
        frame, meta = _load_proxy_frame(item)
        if not frame.empty:
            latest_dates.append(str(frame["date"].max()))
            enriched = {**item}
            if meta.get("selected_symbol"):
                enriched["_selected_symbol"] = meta["selected_symbol"]
            item = enriched
        frames[item["sector_id"]] = frame
        metadata[item["sector_id"]] = meta
    market_latest = max(latest_dates) if latest_dates else None
    benchmark_frame = frames.get("hs300", pd.DataFrame())
    factors = []
    errors = []
    for item in raw_items:
        frame = frames.get(item["sector_id"], pd.DataFrame())
        if frame.empty:
            factors.append(
                {
                    "sector_id": item["sector_id"],
                    "name": item["name"],
                    "category": item.get("category", ""),
                    "proxy_type": item.get("proxy_type", "etf"),
                    "primary_symbol": item.get("primary_symbol"),
                    "selected_symbol": None,
                    "proxy_components": item.get("components") or [],
                    "ranking_enabled": bool(item.get("ranking_enabled", True)),
                    "latest_date": None,
                    "latest_close": None,
                    "returns": {},
                    "moving_averages": {},
                    "benchmark": {"sector_id": "hs300", "symbol": "510300", "returns": {}},
                    "relative_strength": {},
                    "flow": {},
                    "score": {"trend": 0, "momentum": 0, "relative_strength": 0, "flow": 0, "total": 0},
                    "data_quality": "unavailable",
                    "missing_fields": ["market_data"],
                    "stale_days_to_market": None,
                    "proxy_meta": metadata.get(item["sector_id"], {}),
                }
            )
            errors.append(f"{item['sector_id']} missing market data")
            continue
        enriched = {**item}
        if metadata.get(item["sector_id"], {}).get("selected_symbol"):
            enriched["_selected_symbol"] = metadata[item["sector_id"]]["selected_symbol"]
        factor = _base_factors(enriched, frame, benchmark_frame, market_latest)
        factor["proxy_meta"] = metadata.get(item["sector_id"], {})
        factors.append(factor)
    _apply_scores(factors)
    history = _load_history()
    _attach_history(factors, history)
    for item in factors:
        item["maturity"] = _classify_maturity(item) if item.get("ranking_enabled") and item.get("data_quality") != "unavailable" else "unavailable"
        opportunity = _classify_opportunity(item) if item.get("ranking_enabled") else {
            "stage": "benchmark",
            "label": "只作风格参照",
            "chasing_risk": "none",
            "reason": "宽基指数仅用于风格参照，不参与机会排序。",
        }
        item["opportunity_stage"] = opportunity["stage"]
        item["action_label"] = opportunity["label"]
        item["chasing_risk"] = opportunity["chasing_risk"]
        item["opportunity_reason"] = opportunity["reason"]
        item["ma20_distance_pct"] = _ma_distance_pct(item)
    _portfolio_context(factors, raw_items)
    opportunity_priority = {
        "potential_opportunity": 0,
        "early_turning": 1,
        "wait_pullback": 2,
        "avoid_now": 3,
    }
    ranking = sorted(
        [item for item in factors if item.get("ranking_enabled")],
        key=lambda row: (opportunity_priority.get(row.get("opportunity_stage"), 9), -row["score"]["total"]),
    )
    potential_opportunities = [item for item in ranking if item.get("opportunity_stage") == "potential_opportunity"][:8]
    early_turning = [item for item in ranking if item.get("opportunity_stage") == "early_turning"][:8]
    wait_pullback = [item for item in ranking if item.get("opportunity_stage") == "wait_pullback"][:8]
    avoid_now = [item for item in ranking if item.get("opportunity_stage") == "avoid_now"][:8]
    strengthening = [
        item for item in ranking
        if item["maturity"] in {"leading", "spreading", "emerging"} and item.get("data_quality") != "unavailable"
    ][:8]
    cooling = [
        item for item in ranking
        if item["maturity"] in {"cooling", "declining"} and item.get("data_quality") != "unavailable"
    ][:8]
    alerts = [
        item for item in ranking
        if item.get("account_exposure", {}).get("relation") in {"heavy_and_cooling", "underexposed_and_strengthening", "unallocated_and_emerging", "heavy_and_leading"}
    ][:8]
    opportunity_names = "、".join([item["name"] for item in potential_opportunities[:3]]) or "暂无明确潜在机会"
    early_names = "、".join([item["name"] for item in early_turning[:3]]) or "暂无早期转强方向"
    pullback_names = "、".join([item["name"] for item in wait_pullback[:2]]) or "暂无强势待回踩方向"
    payload = {
        "generated_at": _now_iso(),
        "as_of": market_latest,
        "universe_version": universe["version"],
        "market_style": {
            "headline": f"潜在机会：{opportunity_names}",
            "cooling": f"早期转强：{early_names}；强势但等回踩：{pullback_names}",
            "benchmark_note": "宽基只作风格参照，不参与行业排名。",
        },
        "summary": {
            "sector_count": len(ranking),
            "available_count": len([item for item in ranking if item.get("data_quality") != "unavailable"]),
            "stale_count": len([item for item in ranking if item.get("data_quality") == "stale"]),
            "potential_opportunity_count": len([item for item in ranking if item.get("opportunity_stage") == "potential_opportunity"]),
            "early_turning_count": len([item for item in ranking if item.get("opportunity_stage") == "early_turning"]),
            "wait_pullback_count": len([item for item in ranking if item.get("opportunity_stage") == "wait_pullback"]),
            "avoid_now_count": len([item for item in ranking if item.get("opportunity_stage") == "avoid_now"]),
            "strengthening_count": len(strengthening),
            "cooling_count": len(cooling),
            "portfolio_alert_count": len(alerts),
        },
        "potential_opportunities": potential_opportunities,
        "early_turning": early_turning,
        "wait_pullback": wait_pullback,
        "avoid_now": avoid_now,
        "strengthening": strengthening,
        "cooling": cooling,
        "portfolio_alerts": alerts,
        "benchmarks": [item for item in factors if not item.get("ranking_enabled")],
        "sectors": ranking,
        "boundary": "轮动雷达基于本地冷数据和代理标的计算，只提示市场结构变化，不构成买卖建议。",
    }
    _persist_history(factors)
    status_name = "partial_failed" if errors else "stale" if any(item.get("data_quality") == "stale" for item in ranking) else "complete"
    status = _status_payload(status_name, factors, errors, market_latest)
    _write_json(CACHE_PATH, payload)
    _write_json(STATUS_PATH, status)
    return payload


def get_rotation_bundle(force: bool = False) -> dict[str, Any]:
    if force or not CACHE_PATH.exists():
        return build_rotation_bundle()
    cached = _read_json(CACHE_PATH, None)
    if not cached:
        return build_rotation_bundle()
    return cached


def refresh_rotation_if_needed() -> dict[str, Any]:
    status = load_rotation_status()
    cached = _read_json(CACHE_PATH, None)
    if not cached or status.get("status") in {"unknown", "unavailable", "stale", "partial_failed"}:
        return build_rotation_bundle()
    return cached


def load_rotation_status() -> dict[str, Any]:
    status = _read_json(STATUS_PATH, None)
    if status:
        return status
    return {
        "status": "unavailable",
        "provider": "local_rotation_cache",
        "target_date": None,
        "last_trading_date": None,
        "completed_count": 0,
        "failed_count": 0,
        "total_symbols": 0,
        "remaining_count": 0,
        "processed_count": 0,
        "progress": 0,
        "updated_at": None,
        "failure_reasons": {},
        "phase": "not_built",
    }


def get_sector_detail(sector_id: str) -> dict[str, Any] | None:
    bundle = get_rotation_bundle(force=False)
    for group in ["sectors", "benchmarks"]:
        for item in bundle.get(group, []):
            if item.get("sector_id") == sector_id:
                return item
    return None


def get_sector_research(sector_id: str) -> dict[str, Any] | None:
    sector = get_sector_detail(sector_id)
    if not sector:
        return None
    universe = load_universe()
    config = next((item for item in universe["items"] if item.get("sector_id") == sector_id), None)
    if not config:
        return None

    benchmark_config = next((item for item in universe["benchmarks"] if item.get("sector_id") == "hs300"), {})
    benchmark_frame, _ = _load_proxy_frame(benchmark_config)
    proxy_frame, proxy_meta = _load_proxy_frame(config)
    selected_symbol = sector.get("selected_symbol") or proxy_meta.get("selected_symbol") or config.get("primary_symbol")

    etf_symbols: list[str] = []
    if config.get("proxy_type") == "etf":
        for symbol in [selected_symbol, config.get("primary_symbol"), *(config.get("backup_symbols") or [])]:
            value = str(symbol or "")
            if value and value not in etf_symbols:
                etf_symbols.append(value)
    stock_symbols = list(config.get("research_symbols") or [])
    if not stock_symbols and config.get("proxy_type") == "synthetic":
        stock_symbols = [str(item.get("symbol") or "") for item in config.get("components") or []]

    securities = [
        *[_security_research(symbol, "direction_etf", benchmark_frame) for symbol in etf_symbols],
        *[_security_research(symbol, "representative_stock", benchmark_frame) for symbol in stock_symbols if symbol],
    ]
    stocks = [
        item for item in securities
        if item.get("role") == "representative_stock" and item.get("data_quality") == "available"
    ]
    return_20d_values = [
        float(item["returns"]["return_20d"])
        for item in stocks
        if item.get("returns", {}).get("return_20d") is not None
    ]
    breadth = {
        "constituent_count": len(stock_symbols),
        "available_count": len(stocks),
        "above_ma20_pct": _percentage([bool(item["above_ma20"]) for item in stocks if item.get("above_ma20") is not None]),
        "above_ma60_pct": _percentage([bool(item["above_ma60"]) for item in stocks if item.get("above_ma60") is not None]),
        "advancing_5d_pct": _percentage([
            float(item["returns"]["return_5d"]) > 0
            for item in stocks
            if item.get("returns", {}).get("return_5d") is not None
        ]),
        "positive_20d_pct": _percentage([value > 0 for value in return_20d_values]),
        "outperform_hs300_20d_pct": _percentage([
            float(item["relative_strength_20d"]) > 0
            for item in stocks
            if item.get("relative_strength_20d") is not None
        ]),
        "median_return_20d": round(float(pd.Series(return_20d_values).median()), 2) if return_20d_values else None,
        "return_dispersion_20d": (
            round(float(pd.Series(return_20d_values).std(ddof=0)), 2)
            if len(return_20d_values) >= 2
            else None
        ),
    }
    objective = {
        "relative_win_rate_5d": _relative_win_rate(proxy_frame, benchmark_frame),
        "volatility_20d": _annualized_volatility(proxy_frame),
        "max_drawdown_60d": _max_drawdown(proxy_frame),
        "return_60d": _pct_change(proxy_frame, 60),
        "data_coverage_pct": (
            round(len(stocks) / len(stock_symbols) * 100, 2)
            if stock_symbols
            else 0
        ),
    }
    research_dates = [
        str(item["latest_date"])
        for item in securities
        if item.get("latest_date")
    ]
    return {
        **sector,
        "research_generated_at": _now_iso(),
        "research_as_of": max(research_dates) if research_dates else sector.get("latest_date"),
        "research_universe": {
            "etf_count": len(etf_symbols),
            "representative_stock_count": len(stock_symbols),
            "selection_note": "ETF用于刻画方向整体价格，代表股用于验证行业扩散；名单为研究代理池，不等同于指数完整成分。",
        },
        "securities": securities,
        "breadth": breadth,
        "objective_metrics": objective,
        "evidence_analysis": _sector_evidence_analysis(sector, breadth, objective),
        "trend_series": _normalized_trend_series(proxy_frame, benchmark_frame),
    }


def get_sector_history(sector_id: str) -> list[dict[str, Any]]:
    return [record for record in _load_history() if record.get("sector_id") == sector_id]
