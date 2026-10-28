from datetime import date
from app.disclosure_verification.freshness import annotate_verification


def finding(title="2025年半年度报告", when="2025-08-22", status="contradicted"):
    return dict(question="毛利率是否改善", source_title=title, announced_at=when, status=status, quote_verified=True)


def test_old_full_report_and_summary_are_one_historical_finding():
    source = {"items": [finding(), finding("2025年半年度报告摘要")]}
    result = annotate_verification(source, today=date(2026, 9, 8))
    assert result["counts"]["contradicted"] == 0
    assert len(result["historical_items"]) == 1
    assert len(source["items"]) == 2


def test_current_verified_disclosure_remains_actionable_and_unknown_date_does_not():
    result = annotate_verification({"items": [finding(when="2026-08-22"), finding(when=None)]}, today=date(2026, 9, 8))
    assert result["counts"]["contradicted"] == 1
    assert len(result["historical_items"]) == 1
