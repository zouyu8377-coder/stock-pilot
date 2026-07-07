import pytest

from app.facts.disclosure_service import classify_announcement_title, get_disclosure_facts
from app.facts.dragon_tiger_service import get_dragon_tiger_facts
from app.facts.etf_service import get_etf_facts
from app.tushare import TushareConfigError


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("2026年年度报告", "定期报告"),
        ("2026年半年度业绩预告", "业绩预告/业绩快报"),
        ("投资者关系活动记录表", "投资者关系活动"),
        ("关于项目投资及扩产的公告", "项目投资/扩产"),
        ("关于回购公司股份的公告", "回购"),
        ("股东减持计划公告", "增减持"),
        ("股票交易异常波动暨风险提示公告", "异常波动/风险提示"),
        ("关于董事会决议的公告", "其他"),
    ],
)
def test_classify_announcement_title(title, expected):
    assert classify_announcement_title(title) == expected


class _NoTokenClient:
    def query(self, *args, **kwargs):
        raise TushareConfigError("Tushare token is not configured. Set backend env var TUSHARE_TOKEN.")


def test_stage1_fact_services_fail_soft_without_token(monkeypatch):
    monkeypatch.setattr("app.facts.etf_service.TushareLowFrequencyClient", lambda: _NoTokenClient())
    monkeypatch.setattr("app.facts.dragon_tiger_service.TushareLowFrequencyClient", lambda: _NoTokenClient())
    monkeypatch.setattr("app.facts.disclosure_service.TushareLowFrequencyClient", lambda: _NoTokenClient())

    etf = get_etf_facts("159382.SZ")
    dragon = get_dragon_tiger_facts("002463.SZ")
    disclosures = get_disclosure_facts("002463.SZ")

    assert etf["success"] is False
    assert dragon["success"] is False
    assert disclosures["success"] is False
    assert etf["data_status"] == "unavailable"
    assert dragon["data"]["events"] == []
    assert disclosures["data"]["announcements"] == []
