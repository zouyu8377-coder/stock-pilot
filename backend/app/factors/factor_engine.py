from app.factors.factor_schema import IndustryFactor
from app.factors.providers import baijiu, semiconductor, gold, bank, generic


def get_industry_factors(industry: str | None) -> list[IndustryFactor]:
    if not industry:
        return generic.get_generic_factors()

    industry_lower = industry.lower()

    if "白酒" in industry_lower or "酒" in industry_lower:
        return baijiu.get_baijiu_factors()

    if "半导体" in industry_lower or "芯片" in industry_lower or "集成电路" in industry_lower:
        return semiconductor.get_semiconductor_factors()

    if "银行" in industry_lower or "金融" in industry_lower:
        return bank.get_bank_factors()

    if "黄金" in industry_lower or "贵金属" in industry_lower or "有色" in industry_lower:
        return gold.get_gold_factors()

    return generic.get_generic_factors()