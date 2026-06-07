from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data_sources.akshare_etf_share import compact_fund_code, infer_exchange
from app.services.etf_share_service import DEFAULT_ETF_SHARE_TARGETS, EtfShareService


def _parse_codes(value: str | None) -> list[str]:
    if not value:
        return []
    return [compact_fund_code(item) for item in value.split(",") if item.strip()]


def _portfolio_etfs() -> tuple[list[str], dict[str, str]]:
    codes: list[str] = []
    names: dict[str, str] = {}
    try:
        from app.portfolio import portfolio_service

        snapshot = portfolio_service.load_snapshot()
    except Exception:
        return codes, names
    for position in snapshot.positions:
        code = compact_fund_code(position.symbol)
        if infer_exchange(code) == "UNKNOWN":
            continue
        codes.append(code)
        if position.name:
            names[code] = position.name
    return sorted(set(codes)), names


def main() -> int:
    parser = argparse.ArgumentParser(description="Update low-frequency ETF share cache from AKShare.")
    parser.add_argument("--codes", help="Comma-separated ETF codes, for example 159819,518880,516000")
    parser.add_argument("--start", help="Start date, YYYY-MM-DD or YYYYMMDD")
    parser.add_argument("--end", help="End date, YYYY-MM-DD or YYYYMMDD")
    parser.add_argument("--force", action="store_true", help="Ignore recent-cache skip.")
    args = parser.parse_args()

    explicit_codes = _parse_codes(args.codes)
    names: dict[str, str] = {}
    if explicit_codes:
        codes = explicit_codes
        names.update({code: DEFAULT_ETF_SHARE_TARGETS.get(code, "") for code in codes})
    else:
        codes, names = _portfolio_etfs()
        if not codes:
            print("No ETF symbols found in the current portfolio/watchlist; nothing to update.")
            return 0

    service = EtfShareService()
    results = service.update_many(codes, names=names, start=args.start, end=args.end, force=args.force)
    ok_count = 0
    for item in results:
        status = "OK" if item.success else "WARN"
        if item.success:
            ok_count += 1
        detail = item.reason or f"{item.records_written} rows"
        print(f"[{status}] {item.fund_code} {item.fund_name or ''} {item.exchange}: {detail}")
        if item.metrics:
            print(f"       latest={item.metrics.get('latest_trade_date')} share={item.metrics.get('latest_share_100m')} 100m")
        for warning in item.warnings:
            print(f"       warning: {warning}")
    return 0 if ok_count or not results else 1


if __name__ == "__main__":
    raise SystemExit(main())
