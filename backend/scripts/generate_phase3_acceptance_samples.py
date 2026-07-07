from __future__ import annotations

import json
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.analysis_packet import packet_service
from app.portfolio.schemas import ManualEvidenceCreate, PortfolioPositionInput, PortfolioSnapshotInput
from app.portfolio.service import PortfolioService


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "docs" / "acceptance_samples"


DEMO_PRICES = {
    "300001": 20.0,
    "000960": 20.0,
    "000657": 10.0,
}


def _demo_quote(symbol: str) -> dict:
    compact = symbol.split(".", 1)[0].zfill(6)
    return {
        "symbol": compact,
        "name": {
            "300001": "Demo AI PCB",
            "000960": "Demo Metal Resource",
            "000657": "Demo Composite Resource",
        }.get(compact, f"Demo {compact}"),
        "price": DEMO_PRICES.get(compact, 10.0),
        "provider": "phase3_acceptance_demo_quote",
    }


def _write(name: str, result: dict) -> None:
    packet = result["packet"]
    markdown = result["markdown"]
    (OUT_DIR / f"{name}.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / f"{name}.md").write_text(markdown, encoding="utf-8")
    if packet_service.has_mojibake(markdown):
        raise RuntimeError(f"Mojibake marker found in {name}.md")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    demo_root = ROOT / "backend" / "data" / "phase3_acceptance_demo"
    if demo_root.exists():
        shutil.rmtree(demo_root)
    demo_service = PortfolioService(root=demo_root)

    import app.portfolio.service as portfolio_service_module

    portfolio_service_module.collector.get_quote = _demo_quote
    packet_service.portfolio_service = demo_service

    demo_service.save_snapshot(PortfolioSnapshotInput(
        portfolio_id="phase3_demo",
        snapshot_time=datetime(2026, 5, 25, 9, 30, 0),
        total_assets=100000,
        cash_available=30000,
        repo_amount=20000,
        repo_available_date=date(2026, 5, 26),
        notes="Phase 3.5 demo portfolio. Uses non-sensitive synthetic quantities and costs.",
        positions=[
            PortfolioPositionInput(
                symbol="300001",
                name="Demo AI PCB",
                quantity=1000,
                available_quantity=1000,
                avg_cost=18,
                position_role="observation",
                primary_theme="AI_PCB",
                theme_tags=["AI_PCB"],
                user_plan="Demo plan: observe whether thesis evidence improves.",
                invalid_condition="Demo invalid condition: evidence package remains incomplete.",
                target_max_weight=25,
            ),
            PortfolioPositionInput(
                symbol="000960",
                name="Demo Metal Resource",
                quantity=1000,
                available_quantity=1000,
                avg_cost=19,
                position_role="trend",
                primary_theme="METAL_RESOURCE",
                theme_tags=["METAL_RESOURCE"],
                user_plan="Demo plan: track resource exposure only.",
                invalid_condition="Demo invalid condition: thesis not verified.",
                target_max_weight=25,
            ),
            PortfolioPositionInput(
                symbol="000657",
                name="Demo Composite Resource",
                quantity=1000,
                available_quantity=800,
                avg_cost=9,
                position_role="short_term",
                primary_theme="METAL_RESOURCE",
                theme_tags=["METAL_RESOURCE", "TUNGSTEN", "HIGH_VOLATILITY", "COMPOSITE_EXPOSURE"],
                user_plan="Demo plan: composite exposure should be reviewed separately.",
                invalid_condition="Demo invalid condition: composite risk becomes unclear.",
                target_max_weight=15,
            ),
        ],
    ))

    demo_service.add_manual_evidence(ManualEvidenceCreate(
        symbol="000657",
        evidence_type="shareholder_count_manual",
        title="Demo included shareholder-count note",
        text="Non-sensitive demo evidence: shareholder count manually entered for packet inclusion test.",
        as_of_date=date(2026, 5, 20),
        holder_num=12345,
        source="phase3_acceptance_demo",
        include_in_analysis_packet=True,
    ))
    demo_service.add_manual_evidence(ManualEvidenceCreate(
        symbol="000657",
        evidence_type="manual_market_observation",
        title="Demo included observation",
        text="Non-sensitive demo observation used to verify manual evidence export.",
        as_of_date=date(2026, 5, 21),
        source="phase3_acceptance_demo",
        include_in_analysis_packet=True,
    ))
    demo_service.add_manual_evidence(ManualEvidenceCreate(
        symbol="000657",
        evidence_type="manual_market_observation",
        title="Demo excluded observation",
        text="This evidence must not appear in exported packets.",
        as_of_date=date(2026, 5, 22),
        source="phase3_acceptance_demo",
        include_in_analysis_packet=False,
    ))

    _write("phase3_single_etf_packet", packet_service.build_single_stock_packet("159382.SZ", persist=False))
    _write("phase3_single_holding_packet", packet_service.build_single_stock_packet("000657", persist=False))
    _write("phase3_portfolio_packet", packet_service.build_portfolio_packet(persist=False))
    print(f"Wrote samples to {OUT_DIR}")


if __name__ == "__main__":
    main()
