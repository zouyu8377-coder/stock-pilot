from __future__ import annotations

import logging
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from app.data_sources.akshare_etf_share import (
    AkshareEtfShareError,
    compact_fund_code,
    fetch_sse_etf_share,
    fetch_szse_etf_share_history,
    fetch_szse_etf_share_latest,
    infer_exchange,
)


logger = logging.getLogger(__name__)

ETF_SHARE_ROOT = Path(__file__).resolve().parents[2] / "data" / "etf_share"
ETF_SHARE_LIMIT = (
    "ETF share observations are low-frequency fund-size facts only. They are not buy/sell signals "
    "and do not imply future price direction."
)

DEFAULT_ETF_SHARE_TARGETS = {
    "159819": "创业板人工智能 ETF",
    "518880": "黄金 ETF",
    "516000": "半导体设备 ETF",
    "515400": "大数据 ETF 富国",
}


@dataclass
class EtfShareUpdateResult:
    fund_code: str
    fund_name: str = ""
    exchange: str = "UNKNOWN"
    success: bool = False
    data_status: str = "unavailable"
    records_written: int = 0
    cache_path: str | None = None
    reason: str | None = None
    metrics: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)


def _today() -> date:
    return datetime.now().date()


def _normalize_date(value: str | date | None, default: date) -> date:
    if value is None:
        return default
    if isinstance(value, date):
        return value
    return pd.to_datetime(value).date()


def _safe_read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        if path.suffix == ".parquet":
            return pd.read_parquet(path)
        return pd.read_csv(path)
    except Exception as exc:
        logger.warning("Failed to read ETF share cache %s: %s", path, exc)
        return pd.DataFrame()


def _write_cache(path: Path, df: pd.DataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = df.copy()
    if "raw_fields" in frame.columns:
        frame["raw_fields"] = frame["raw_fields"].map(
            lambda value: json.dumps(value, ensure_ascii=False, default=str) if isinstance(value, dict) else value
        )
    try:
        frame.to_parquet(path, index=False)
        return path
    except Exception as exc:
        csv_path = path.with_suffix(".csv")
        logger.warning("Failed to write parquet %s, falling back to csv: %s", path, exc)
        frame.to_csv(csv_path, index=False)
        return csv_path


def _cache_path(root: Path, code: str) -> Path:
    parquet = root / f"{compact_fund_code(code)}.parquet"
    if parquet.exists():
        return parquet
    csv_path = parquet.with_suffix(".csv")
    return csv_path if csv_path.exists() else parquet


def _clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=[
            "trade_date",
            "fund_code",
            "fund_name",
            "exchange",
            "fund_share",
            "fund_share_100m",
            "nav",
            "source",
            "fetched_at",
            "raw_fields",
        ])
    frame = df.copy()
    frame["fund_code"] = frame["fund_code"].map(compact_fund_code)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["fund_share"] = pd.to_numeric(frame["fund_share"], errors="coerce")
    frame["fund_share_100m"] = pd.to_numeric(frame["fund_share_100m"], errors="coerce")
    frame["nav"] = pd.to_numeric(frame.get("nav"), errors="coerce") if "nav" in frame.columns else None
    frame = frame.dropna(subset=["trade_date", "fund_code", "fund_share"])
    if "fetched_at" not in frame.columns:
        frame["fetched_at"] = datetime.utcnow().isoformat()
    return frame


def _merge_cache(existing: pd.DataFrame, records: list[dict[str, Any]]) -> pd.DataFrame:
    incoming = pd.DataFrame(records)
    frame = pd.concat([_clean_frame(existing), _clean_frame(incoming)], ignore_index=True)
    if frame.empty:
        return frame
    frame = frame.sort_values(["fund_code", "trade_date", "fetched_at"])
    frame = frame.drop_duplicates(subset=["fund_code", "trade_date"], keep="last")
    return frame.sort_values("trade_date").reset_index(drop=True)


def compute_share_metrics(df: pd.DataFrame) -> dict[str, Any] | None:
    frame = _clean_frame(df)
    if frame.empty:
        return None
    frame = frame.sort_values("trade_date").reset_index(drop=True)
    latest = frame.iloc[-1]
    values = frame["fund_share"].tolist()

    def chg(offset: int) -> float | None:
        if len(values) <= offset:
            return None
        previous = values[-1 - offset]
        current = values[-1]
        if previous is None or pd.isna(previous) or previous == 0 or current is None or pd.isna(current):
            return None
        return round(current / previous - 1, 6)

    return {
        "fund_code": latest.get("fund_code"),
        "fund_name": latest.get("fund_name") or "",
        "latest_trade_date": latest.get("trade_date"),
        "latest_share_100m": round(float(latest.get("fund_share_100m")), 4),
        "share_chg_1d": chg(1),
        "share_chg_5d": chg(5),
        "share_chg_20d": chg(20),
        "source": latest.get("source") or "akshare",
        "data_status": "available",
        "interpretation_limit": ETF_SHARE_LIMIT,
    }


class EtfShareService:
    def __init__(self, cache_root: Path | str | None = None):
        self.cache_root = Path(cache_root or ETF_SHARE_ROOT)

    def cache_path(self, code: str) -> Path:
        return _cache_path(self.cache_root, code)

    def read_cache(self, code: str) -> pd.DataFrame:
        return _safe_read(self.cache_path(code))

    def has_recent_cache(self, code: str, end: date | None = None) -> bool:
        frame = _clean_frame(self.read_cache(code))
        if frame.empty:
            return False
        latest = pd.to_datetime(frame["trade_date"], errors="coerce").max()
        if pd.isna(latest):
            return False
        target = end or _today()
        return latest.date() >= target - timedelta(days=3)

    def update_one(
        self,
        code: str,
        *,
        fund_name: str = "",
        start: str | date | None = None,
        end: str | date | None = None,
        force: bool = False,
    ) -> EtfShareUpdateResult:
        compact = compact_fund_code(code)
        exchange = infer_exchange(compact)
        end_date = _normalize_date(end, _today())
        start_date = _normalize_date(start, end_date - timedelta(days=140))
        if (end_date - start_date).days > 186:
            start_date = end_date - timedelta(days=186)
        result = EtfShareUpdateResult(fund_code=compact, fund_name=fund_name, exchange=exchange)
        if exchange == "UNKNOWN":
            result.reason = "Non-ETF or unsupported exchange prefix; skipped."
            return result
        if not force and self.has_recent_cache(compact, end=end_date):
            frame = self.read_cache(compact)
            result.success = True
            result.data_status = "available"
            result.cache_path = str(self.cache_path(compact))
            result.metrics = compute_share_metrics(frame)
            result.reason = "Recent cache exists; skipped request."
            return result

        records: list[dict[str, Any]] = []
        warnings: list[str] = []
        try:
            if exchange == "SSE":
                records = fetch_sse_etf_share(compact, end_date.strftime("%Y%m%d"))
            elif exchange == "SZSE":
                try:
                    records = fetch_szse_etf_share_history(
                        compact,
                        start_date.strftime("%Y%m%d"),
                        end_date.strftime("%Y%m%d"),
                    )
                except AkshareEtfShareError as exc:
                    warnings.append(str(exc))
                    records = fetch_szse_etf_share_latest(compact)
        except AkshareEtfShareError as exc:
            result.reason = str(exc)
            result.warnings = warnings
            return result

        if not records:
            result.reason = "AKShare request succeeded but no row matched the fund code."
            result.warnings = warnings
            return result
        for record in records:
            if not record.get("fund_name") and fund_name:
                record["fund_name"] = fund_name
        existing = self.read_cache(compact)
        merged = _merge_cache(existing, records)
        written_path = _write_cache(self.cache_root / f"{compact}.parquet", merged)
        result.success = True
        result.data_status = "available"
        result.records_written = len(records)
        result.cache_path = str(written_path)
        result.metrics = compute_share_metrics(merged)
        result.warnings = warnings
        if result.metrics and not result.metrics.get("fund_name") and fund_name:
            result.metrics["fund_name"] = fund_name
        return result

    def update_many(
        self,
        codes: list[str],
        *,
        names: dict[str, str] | None = None,
        start: str | date | None = None,
        end: str | date | None = None,
        force: bool = False,
    ) -> list[EtfShareUpdateResult]:
        names = {compact_fund_code(k): v for k, v in (names or {}).items()}
        results = []
        for code in codes:
            compact = compact_fund_code(code)
            try:
                results.append(self.update_one(compact, fund_name=names.get(compact, ""), start=start, end=end, force=force))
            except Exception as exc:
                logger.warning("ETF share update failed for %s: %s", compact, exc)
                results.append(EtfShareUpdateResult(
                    fund_code=compact,
                    fund_name=names.get(compact, ""),
                    exchange=infer_exchange(compact),
                    reason=str(exc)[:240],
                ))
        return results

    def observation_for_code(self, code: str, fund_name: str = "") -> dict[str, Any]:
        compact = compact_fund_code(code)
        frame = self.read_cache(compact)
        metrics = compute_share_metrics(frame)
        if metrics:
            if not metrics.get("fund_name") and fund_name:
                metrics["fund_name"] = fund_name
            return metrics
        return {
            "fund_code": compact,
            "fund_name": fund_name,
            "data_status": "unavailable",
            "reason": "No local ETF share cache. Run backend/scripts/update_etf_share.py first.",
            "source": "akshare",
            "interpretation_limit": ETF_SHARE_LIMIT,
        }

    def observations_for_codes(self, codes: list[str], names: dict[str, str] | None = None) -> list[dict[str, Any]]:
        names = {compact_fund_code(k): v for k, v in (names or {}).items()}
        return [self.observation_for_code(code, names.get(compact_fund_code(code), "")) for code in codes]


etf_share_service = EtfShareService()
