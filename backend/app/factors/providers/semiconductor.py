from app.factors.factor_schema import IndustryFactor


def get_semiconductor_factors() -> list[IndustryFactor]:
    return [
        IndustryFactor(
            factor_name="SOX指数",
            description="费城半导体指数，衡量全球半导体板块表现",
            impact="SOX指数走势反映全球半导体行业景气度"
        ),
        IndustryFactor(
            factor_name="纳斯达克",
            description="美国科技股NASDAQ综合指数",
            impact="纳斯达克涨跌影响A股科技股情绪与估值"
        ),
        IndustryFactor(
            factor_name="英伟达",
            description="NVIDIA GPU供需与数据中心业务",
            impact="英伟达是AI算力龙头，其业绩指引影响整个产业链"
        ),
        IndustryFactor(
            factor_name="AI资本开支",
            description="全球云厂商资本开支计划",
            impact="AI资本开支增加直接拉动半导体需求"
        ),
        IndustryFactor(
            factor_name="国产替代",
            description="半导体设备/材料国产化进度",
            impact="国产替代加速将提升国内半导体企业市场份额"
        ),
        IndustryFactor(
            factor_name="先进制程",
            description="7nm/5nm/3nm等先进工艺产能",
            impact="先进制程产能决定高端芯片供给与价格"
        ),
    ]