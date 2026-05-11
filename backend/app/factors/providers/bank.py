from app.factors.factor_schema import IndustryFactor


def get_bank_factors() -> list[IndustryFactor]:
    return [
        IndustryFactor(
            factor_name="LPR利率",
            description="贷款市场报价利率，1年期与5年期",
            impact="LPR下调压缩银行净息差，但提升贷款需求"
        ),
        IndustryFactor(
            factor_name="房地产",
            description="房地产销售与房价走势",
            impact="房地产是银行信贷主要投向，房价下跌增加坏账风险"
        ),
        IndustryFactor(
            factor_name="坏账率",
            description="不良贷款率与拨备覆盖率",
            impact="坏账率上升侵蚀银行利润，拨备覆盖率反映风险抵御能力"
        ),
        IndustryFactor(
            factor_name="经济周期",
            description="GDP增速、PMI等宏观经济指标",
            impact="经济复苏期银行信贷需求旺，业绩弹性大"
        ),
        IndustryFactor(
            factor_name="银行分红",
            description="股息率与派息比例",
            impact="高股息是银行股核心吸引力"
        ),
        IndustryFactor(
            factor_name="地方债务",
            description="城投债与地方政府债务化解进度",
            impact="地方债务风险影响银行资产质量预期"
        ),
    ]