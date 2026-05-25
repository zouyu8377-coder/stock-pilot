from datetime import date, datetime

import pandas as pd
import pytest

from app.analysis_packet.snapshot_builder import build_basic_stock_snapshot
from app.company_profile.schemas import CompanyProfile
from app.core.config import Settings
from app.evidence.schemas import (
    DataStatus,
    EvidenceCategory,
    EvidenceItem,
    EvidenceReliability,
    EvidenceType,
    LlmUsage,
)
from app.tushare.client import TushareLowFrequencyClient
from app.tushare.exceptions import TushareConfigError


def test_tushare_token_missing_raises_config_error(tmp_path):
    config = Settings(TUSHARE_TOKEN="", TUSHARE_CACHE_ROOT=str(tmp_path))
    client = TushareLowFrequencyClient(config=config)

    with pytest.raises(TushareConfigError, match="TUSHARE_TOKEN"):
        client.require_token()


def test_tushare_token_can_be_read_from_settings(tmp_path):
    config = Settings(TUSHARE_TOKEN="test-token", TUSHARE_CACHE_ROOT=str(tmp_path))
    client = TushareLowFrequencyClient(config=config)

    assert client.require_token() == "test-token"


def test_evidence_item_rejects_system_hypothesis_as_fact():
    with pytest.raises(ValueError, match="cannot be used as fact"):
        EvidenceItem(
            evidence_type=EvidenceType.SYSTEM_MARKET_REGIME,
            category=EvidenceCategory.SYSTEM_HYPOTHESIS,
            title="Regime",
            source="rule engine",
            reliability=EvidenceReliability.H,
            llm_usage=LlmUsage.FACT,
        )


def test_evidence_item_accepts_auto_fact():
    item = EvidenceItem(
        symbol="600519",
        evidence_type=EvidenceType.REALTIME_QUOTE,
        category=EvidenceCategory.AUTO_FACT,
        title="Quote",
        payload={"price": 100},
        source="easyquotation",
        as_of_date=date.today(),
        reliability=EvidenceReliability.B,
        llm_usage=LlmUsage.FACT_WITH_LIMIT,
        data_status=DataStatus.AVAILABLE,
    )

    assert item.symbol == "600519"
    assert item.freshness_days is not None


def test_basic_single_stock_snapshot_from_existing_data_shape():
    history = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=70, freq="D").strftime("%Y-%m-%d"),
            "open": [10.0 + i * 0.1 for i in range(70)],
            "high": [10.3 + i * 0.1 for i in range(70)],
            "low": [9.8 + i * 0.1 for i in range(70)],
            "close": [10.1 + i * 0.1 for i in range(70)],
            "volume": [100000 + i for i in range(70)],
            "amount": [1000000 + i for i in range(70)],
            "pctChg": [0.1 for _ in range(70)],
        }
    )
    stock_data = {
        "name": "Test Corp",
        "symbol": "600000",
        "price": 17.0,
        "change_pct": 1.2,
        "indicators": {"ma5": 16.8, "ma10": 16.4, "ma20": 15.8, "ma30": 15.2, "ma60": 13.9, "rsi14": 55, "macd": 0.4},
        "analysis": {"trend": "bullish", "signal": "watch", "support": "16/15", "resistance": "18/19", "summary": "test"},
        "company_profile": CompanyProfile(company_name="Test Corp", main_business="Test business"),
        "data_coverage": {"provided": [], "missing": [{"label": "northbound", "reason": "not connected"}], "missing_labels": ["northbound"]},
        "quote": {"symbol": "600000", "name": "Test Corp", "price": 17.0, "change_pct": 1.2, "provider": "test"},
    }

    snapshot = build_basic_stock_snapshot("600000", stock_data=stock_data, history=history, persist=False)

    assert snapshot.analysis_scope == "single_stock"
    assert snapshot.target_symbols == ["600000"]
    assert snapshot.daily_k_as_of is not None
    assert len(snapshot.evidence_items) >= 5
    assert snapshot.system_hypotheses[0].category == EvidenceCategory.SYSTEM_HYPOTHESIS
    assert snapshot.system_hypotheses[0].llm_usage == LlmUsage.HYPOTHESIS_ONLY
    assert snapshot.model_dump(mode="json")["snapshot_id"].startswith("snap_")
