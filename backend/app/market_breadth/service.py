from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[2]
MARKET_DIR = BASE_DIR / "data" / "base_market"
METADATA_FILE = BASE_DIR / "data" / "metadata" / "stock_meta.parquet"
CACHE_FILE = BASE_DIR / "data" / "cache" / "market_breadth.json"


def _target_date() -> str | None:
    try:
        from app.core.data_updater import load_update_status

        status = load_update_status()
        return status.get("core_last_trading_date") or status.get("last_trading_date") or status.get("target_date")
    except Exception:
        return None


def _load_cache() -> dict[str, Any] | None:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None


def get_market_breadth() -> dict[str, Any]:
    """Return cached local breadth so an evidence packet never scans thousands of files."""
    target = _target_date()
    cached = _load_cache()
    if cached and cached.get("as_of") == target:
        return {**cached, "freshness_status": "current", "target_date": target, "is_stale": False}
    if cached:
        return {
            **cached,
            "freshness_status": "latest_available_target_pending",
            "target_date": target,
            "is_stale": True,
            "reason": "Latest available breadth is retained while the target-date cold-data refresh is still pending.",
        }
    return {
        "data_status": "pending_refresh",
        "as_of": cached.get("as_of") if cached else None,
        "target_date": target,
        "reason": "Market breadth aggregate will be rebuilt after the cold-data refresh.",
        "boundary": "Two-market breadth is calculated from local Shanghai/Shenzhen A-share daily-K files, not exchange-published statistics.",
    }


def _active_files() -> list[Path]:
    if not METADATA_FILE.exists():
        return []
    metadata = pd.read_parquet(METADATA_FILE, columns=["ts_code"])
    symbols: list[str] = []
    for code in metadata["ts_code"].dropna():
        parts = str(code).split(".", 1)
        if len(parts) == 2 and parts[1].lower() in {"sh", "sz"}:
            symbols.append(f"{parts[1].lower()}.{parts[0]}")
    return [MARKET_DIR / f"{symbol}.parquet" for symbol in symbols if (MARKET_DIR / f"{symbol}.parquet").exists()]


def _number(value: Any) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else float(parsed)


def rebuild_market_breadth(target_date: date | str | None = None) -> dict[str, Any]:
    """Aggregate daily OHLC facts after cold data is refreshed, then cache the result."""
    target = str(target_date or _target_date() or "")[:10]
    if not target:
        raise ValueError("A target daily-K date is required")

    exchanges = {
        "sh": _empty_exchange(),
        "sz": _empty_exchange(),
    }
    files = _active_files()
    for path in files:
        try:
            history = pd.read_parquet(path, columns=["date", "amount", "pctChg"])
            history = history.assign(_date=pd.to_datetime(history["date"], errors="coerce"))
            history = history.dropna(subset=["_date"]).sort_values("_date")
            row = history.loc[history["_date"].dt.strftime("%Y-%m-%d") == target]
            if row.empty:
                continue
            latest = row.iloc[-1]
            bucket = exchanges[path.stem.split(".", 1)[0]]
            bucket["available_count"] += 1
            bucket["turnover_yuan"] += _number(latest.get("amount")) or 0.0
            previous = history.loc[history["_date"] < latest["_date"]].tail(1)
            if not previous.empty:
                bucket["previous_turnover_yuan"] += _number(previous.iloc[-1].get("amount")) or 0.0
                bucket["previous_available_count"] += 1
            trailing = history.loc[history["_date"] <= latest["_date"]].tail(5)
            if len(trailing) == 5:
                bucket["turnover_ma_5_yuan"] += sum(_number(value) or 0.0 for value in trailing["amount"])
                bucket["turnover_ma_5_available_count"] += 1
            change = _number(latest.get("pctChg"))
            if change is None:
                continue
            if change > 0:
                bucket["advance_count"] += 1
            elif change < 0:
                bucket["decline_count"] += 1
            else:
                bucket["flat_count"] += 1
            # A-share boards have different limits; +/-9.5% is intentionally an
            # approximate breadth signal, never an exchange-published count.
            if change >= 9.5:
                bucket["limit_up_count"] += 1
            elif change <= -9.5:
                bucket["limit_down_count"] += 1
        except Exception:
            continue

    total = {key: sum(item[key] for item in exchanges.values()) for key in exchanges["sh"]}
    for item in [*exchanges.values(), total]:
        item["turnover_yuan"] = round(item["turnover_yuan"], 2)
        item["turnover_100m_yuan"] = round(item["turnover_yuan"] / 100_000_000, 2)
        item["previous_turnover_yuan"] = round(item["previous_turnover_yuan"], 2)
        item["previous_turnover_100m_yuan"] = round(item["previous_turnover_yuan"] / 100_000_000, 2)
        previous = item["previous_turnover_yuan"]
        item["turnover_change_pct"] = round((item["turnover_yuan"] / previous - 1) * 100, 2) if previous else None
        ma_count = item["turnover_ma_5_available_count"]
        item["turnover_ma_5_yuan"] = round(item["turnover_ma_5_yuan"] / 5, 2) if ma_count else None
        item["turnover_ma_5_100m_yuan"] = round(item["turnover_ma_5_yuan"] / 100_000_000, 2) if item["turnover_ma_5_yuan"] else None
        item["turnover_vs_ma_5_ratio"] = round(item["turnover_yuan"] / item["turnover_ma_5_yuan"], 4) if item["turnover_ma_5_yuan"] else None
    result = {
        "data_status": "available",
        "as_of": target,
        "universe_count": len(files),
        "coverage_count": total["available_count"],
        "coverage_pct": round(total["available_count"] / len(files) * 100, 2) if files else 0.0,
        "shanghai": exchanges["sh"],
        "shenzhen": exchanges["sz"],
        "total": total,
        "source": "local BaoStock adjusted daily-K aggregation",
        "boundary": "Two-market breadth uses local Shanghai/Shenzhen A-share daily-K files. Amount is the sum of covered-stock daily amount in yuan; it excludes unavailable files and is not an exchange-published statistic. Limit-up/down counts use a +/-9.5% approximation and exclude board-rule distinctions.",
    }
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _empty_exchange() -> dict[str, float | int]:
    return {
        "advance_count": 0,
        "decline_count": 0,
        "flat_count": 0,
        "limit_up_count": 0,
        "limit_down_count": 0,
        "turnover_yuan": 0.0,
        "previous_turnover_yuan": 0.0,
        "turnover_ma_5_yuan": 0.0,
        "available_count": 0,
        "previous_available_count": 0,
        "turnover_ma_5_available_count": 0,
    }
