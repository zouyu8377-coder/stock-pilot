from app.factors.factor_schema import IndustryFactor


def get_baijiu_factors() -> list[IndustryFactor]:
    return [
        IndustryFactor(
            factor_name="北向资金",
            description="外资通过沪股通/深股通持仓白酒板块",
            impact="北向资金净流入通常提振白酒板块估值"
        ),
        IndustryFactor(
            factor_name="飞天茅台批价",
            description="53度飞天茅台散瓶/原箱一批价",
            impact="茅台批价是白酒行业景气度的风向标"
        ),
        IndustryFactor(
            factor_name="中秋消费",
            description="中秋节期间白酒动销情况",
            impact="中秋是白酒传统旺季，销量直接影响三季度业绩"
        ),
        IndustryFactor(
            factor_name="春节消费",
            description="春节前白酒备货与消费情况",
            impact="春节是白酒最重要的消费旺季"
        ),
        IndustryFactor(
            factor_name="社零数据",
            description="社会消费品零售总额增速",
            impact="消费数据反映居民购买力，白酒属于可选消费"
        ),
        IndustryFactor(
            factor_name="白酒渠道库存",
            description="经销商库存周转天数",
            impact="库存过高预示价格压力，库存合理则景气无忧"
        ),
    ]