from app.strategy.schemas import StrategyContext


# 模型名称到规则函数的映射
MODEL_RULES = {
    "板块主升浪模型": "sector_trend",
    "预期差模型": "expectation_gap",
    "催化剂模型": "catalyst",
    "相对强弱模型": "relative_strength",
    "公司Alpha/行业Beta拆分模型": "alpha_beta",
    "风险收益比模型": "risk_reward",
    "趋势修复模型": "risk_reward",
    "资金承接模型": "relative_strength",
}


def select_models(strategy_context: StrategyContext) -> list[str]:
    """
    根据 market_regime 选择适用的分析模型。
    同时把结果写回 strategy_context.selected_models。
    """
    regime = strategy_context.market_regime

    if regime == "趋势主升":
        models = ["板块主升浪模型", "相对强弱模型", "风险收益比模型", "公司Alpha/行业Beta拆分模型"]
    elif regime == "高位分歧":
        models = ["板块主升浪模型", "风险收益比模型", "资金承接模型", "催化剂模型"]
    elif regime == "事件驱动":
        models = ["催化剂模型", "预期差模型", "公司Alpha/行业Beta拆分模型"]
    elif regime == "下跌趋势":
        models = ["风险收益比模型", "趋势修复模型", "预期差模型"]
    elif regime == "震荡筑底":
        models = ["预期差模型", "风险收益比模型", "公司Alpha/行业Beta拆分模型", "催化剂模型"]
    elif regime == "题材轮动":
        models = ["催化剂模型", "板块主升浪模型", "风险收益比模型"]
    else:  # 震荡观察
        models = ["风险收益比模型", "公司Alpha/行业Beta拆分模型", "预期差模型"]

    strategy_context.selected_models = models
    return models
