"""
Yahoo Finance / COMEX capability probe.

This script performs read-only requests against Yahoo Finance public endpoints
for COMEX copper (HG=F), gold (GC=F), and silver (SI=F) delayed reference quotes.

Safety rules:
- No user account data is transmitted.
- No holdings or portfolio information is sent.
- Only public ticker symbols are requested.
- Token values are never printed.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# Add backend parent to path so `app` imports work when run standalone
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.external_drivers.yahoo_comex_provider import FACTOR_CONFIG, YahooComexError, fetch_yahoo_comex_series


def main():
    results = []
    for factor_id, config in FACTOR_CONFIG.items():
        print(f"Probing {factor_id} ({config['yahoo_symbol']}) ...")
        try:
            df, meta = fetch_yahoo_comex_series(factor_id, range_days="5d")
            latest = df.iloc[0].to_dict() if not df.empty else {}
            result = {
                "factor_id": factor_id,
                "yahoo_symbol": config["yahoo_symbol"],
                "product": config["product"],
                "provider": "yahoo_finance",
                "status": "available",
                "latest_trade_date": latest.get("trade_date"),
                "close": latest.get("close"),
                "currency": meta.get("currency"),
                "exchange_name": meta.get("exchange_name"),
                "instrument_type": meta.get("instrument_type"),
                "quote_delay_status": meta.get("quote_delay_status"),
                "packet_eligible": True,
                "limitation": (
                    "Yahoo Finance COMEX delayed reference; not official CME settlement; "
                    "interface may change; not a causal conclusion or trading advice."
                ),
            }
        except YahooComexError as exc:
            result = {
                "factor_id": factor_id,
                "yahoo_symbol": config["yahoo_symbol"],
                "product": config["product"],
                "provider": "yahoo_finance",
                "status": "unavailable",
                "reason": str(exc),
                "quote_delay_status": "delayed_or_unverified",
                "packet_eligible": False,
                "limitation": "Probe failed; may be network, rate limit, or interface change.",
            }
        results.append(result)
        print(f"  -> {result['status']}")

    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "summary": {
            "available": sum(1 for r in results if r["status"] == "available"),
            "unavailable": sum(1 for r in results if r["status"] == "unavailable"),
        },
        "results": results,
        "privacy_note": "No account, token, holding, or personal data was transmitted.",
    }

    import os
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.makedirs(os.path.join(project_root, "docs"), exist_ok=True)
    json_path = os.path.join(project_root, "docs", "yahoo_comex_capability_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nSaved JSON: {json_path}")

    md_lines = [
        "# Yahoo Finance / COMEX Capability Report",
        "",
        f"Generated at: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Available: {report['summary']['available']}",
        f"- Unavailable: {report['summary']['unavailable']}",
        "",
        "## Results",
        "",
        "| factor_id | yahoo_symbol | product | status | latest_trade_date | close | limitation |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        md_lines.append(
            f"| {r['factor_id']} | {r['yahoo_symbol']} | {r['product']} | {r['status']} | "
            f"{r.get('latest_trade_date', '-')} | {r.get('close', '-')} | {r['limitation']} |"
        )

    md_lines.extend([
        "",
        "## Privacy",
        "",
        report["privacy_note"],
        "",
        "## Boundary",
        "",
        "Yahoo Finance / COMEX data is delayed reference only; not official CME settlement; not a causal conclusion; not trading advice.",
    ])

    md_path = os.path.join(project_root, "docs", "yahoo_comex_capability_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print(f"Saved Markdown: {md_path}")


if __name__ == "__main__":
    main()
