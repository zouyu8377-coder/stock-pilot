"""Business questions shared by collection and the portfolio research dossier."""

QUESTIONS = {
    "CXO": ["订单或客户项目需求是否改善？", "产能利用率、收入增长和利润率是否同步验证？", "海外政策与客户研发投入是否改变预期？"],
    "MEDICAL_ETF": ["ETF 成分结构是否仍代表医药主线？", "行业政策是否出现方向性变化？", "份额或资金流能否验证资金关注？"],
    "INSURANCE": ["保费、新业务价值和投资收益是否改善？", "利率和资本市场变化如何影响经营与估值？"],
    "PCB": ["服务器及其他PCB业务收入、订单和毛利率如何变化？", "客户资本开支与产能扩张是否支持后续需求？"],
    "INNOVATION_DRUG": ["核心创新药销售与研发管线进展是否达到预期？", "收入、利润及授权收入是否可持续？", "医保、集采和审批政策是否改变经营前景？"],
    "GOLD": ["产品跟踪对象、费用与跟踪偏离是否发生变化？", "黄金、美元与实际利率的变化是否支持持有逻辑？"],
    "COPPER": ["铜价、产销量和单位成本是否支持利润预期？", "供需、库存与项目投产是否改变行业前景？"],
    "EV_AUTOMOTIVE": ["销量、产品结构与单车盈利是否改善？", "海外政策、竞争与产能变化是否影响经营预期？"],
}


def business_questions(directions):
    return list(dict.fromkeys(q for d in directions for q in QUESTIONS.get(str(d).upper(), [])))
