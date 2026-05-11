from app.factors.factor_schema import IndustryFactor


def get_gold_factors() -> list[IndustryFactor]:
    return [
        IndustryFactor(
            factor_name="美元指数 DXY",
            description="美元相对于一篮子货币的加权指数",
            impact="美元走强通常压制黄金价格，负相关性明显"
        ),
        IndustryFactor(
            factor_name="美债收益率",
            description="10年期美国国债实际收益率",
            impact="美债收益率上升提升持有黄金的机会成本"
        ),
        IndustryFactor(
            factor_name="黄金期货",
            description="COMEX黄金期货价格与持仓",
            impact="期货市场情绪影响短期金价走势"
        ),
        IndustryFactor(
            factor_name="VIX恐慌指数",
            description="CBOE波动率指数，衡量市场恐慌程度",
            impact="VIX上升通常推动黄金避险需求"
        ),
        IndustryFactor(
            factor_name="地缘政治风险",
            description="俄乌冲突、中东局势、中美关系等",
            impact="地缘风险上升提升黄金避险属性"
        ),
        IndustryFactor(
            factor_name="美联储利率",
            description="联邦基金利率与货币政策预期",
            impact="降息预期利好黄金，加息预期利空"
        ),
    ]