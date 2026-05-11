from app.factors.factor_schema import IndustryFactor


def get_generic_factors() -> list[IndustryFactor]:
    return [
        IndustryFactor(
            factor_name="大盘指数",
            description="上证指数/深证成指/创业板指走势",
            impact="大盘涨跌影响个股情绪与估值锚"
        ),
        IndustryFactor(
            factor_name="北向资金",
            description="外资通过沪股通/深股通净流入",
            impact="北向资金是A股重要的增量资金来源"
        ),
        IndustryFactor(
            factor_name="市场成交量",
            description="两市成交额与换手率",
            impact="成交量反映市场活跃度与资金参与程度"
        ),
        IndustryFactor(
            factor_name="风险偏好",
            description="市场风险情绪与风险溢价",
            impact="风险偏好提升利好成长股，下滑利好防御股"
        ),
        IndustryFactor(
            factor_name="宏观经济",
            description="GDP/CPI/PMI等宏观数据",
            impact="宏观数据决定企业盈利预期与政策走向"
        ),
    ]