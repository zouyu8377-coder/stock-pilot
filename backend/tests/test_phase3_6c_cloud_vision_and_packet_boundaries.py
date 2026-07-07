import pandas as pd

from app.analysis.data_coverage import build_data_coverage
from app.analysis_packet.snapshot_builder import _daily_k_summary
from app.company_profile.schemas import CompanyProfile


def test_data_coverage_does_not_mark_rule_inferred_business_as_provided():
    history = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=70),
        "high": [10 + i * 0.1 for i in range(70)],
        "close": [9 + i * 0.1 for i in range(70)],
        "volume": [1000] * 70,
    })
    profile = CompanyProfile(
        company_name="沪电股份",
        main_business="",
        core_products=[],
        industry_chain_position="规则推断模板，不是结构化事实",
        company_type=["AI_PCB"],
    )

    coverage = build_data_coverage(profile, history, {})

    assert not any(item["key"] == "company_business" for item in coverage["provided"])
    business_missing = next(item for item in coverage["missing"] if item["key"] == "company_business")
    assert business_missing["data_status"] == "context_only_or_missing"
    assert "规则画像仅作上下文参考" in business_missing["reason"]


def test_daily_k_summary_marks_interval_returns_as_derived_observations():
    history = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=70),
        "open": [10 + i * 0.1 for i in range(70)],
        "high": [10.5 + i * 0.1 for i in range(70)],
        "low": [9.5 + i * 0.1 for i in range(70)],
        "close": [10 + i * 0.1 for i in range(70)],
        "volume": [1000] * 70,
        "amount": [10000] * 70,
        "pctChg": [1] * 70,
    })

    summary = _daily_k_summary(history)

    assert summary["return_5d_pct"] is not None
    assert "派生观察" in summary["boundary"]
    assert "买卖结论" in summary["boundary"]
