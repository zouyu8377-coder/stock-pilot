from app.company_profile.schemas import CompanyProfile
from app.strategy.schemas import StrategyContext


def detect_market_regime(
    stock_data: dict,
    company_profile: CompanyProfile | None = None,
    industry_factors: list | None = None,
) -> StrategyContext:
    """
    基于技术指标和公司画像，识别当前交易环境。
    纯规则引擎，不调用 AI。
    """
    ctx = StrategyContext()

    analysis = stock_data.get("analysis", {}) or {}
    indicators = stock_data.get("indicators", {}) or {}
    change_pct = stock_data.get("change_pct", 0) or 0
    industry = stock_data.get("industry", "") or ""

    trend = analysis.get("trend", "")
    signal = analysis.get("signal", "")
    rsi = indicators.get("rsi14", 50)
    macd = indicators.get("macd", 0)
    ma5 = indicators.get("ma5", 0)
    ma10 = indicators.get("ma10", 0)
    ma20 = indicators.get("ma20", 0)
    ma60 = indicators.get("ma60", 0)

    # 辅助判断：均线排列
    ma_bull = ma5 > ma10 > ma20 if ma5 and ma10 and ma20 else False
    ma_bear = ma5 < ma10 or ma20 < ma60 if ma5 and ma10 and ma20 and ma60 else False

    # 检查事件驱动特征
    event_driven = False
    if company_profile:
        concepts = company_profile.concept_tags or []
        logic = company_profile.core_logic or []
        event_keywords = [
            "央企改革", "资产注入", "并购重组", "军工", "出口管制",
            "涨价", "国产替代", "AI算力", "战略资源", "战略金属",
            "催化剂", "政策", "事件",
        ]
        for kw in event_keywords:
            if any(kw in c for c in concepts) or any(kw in l for l in logic):
                event_driven = True
                break

    # ========== 判定规则 ==========

    # 1. 趋势主升
    if (
        "偏多" in trend
        and macd >= 0
        and change_pct >= 0
        and (ma_bull or (ma5 > ma10 and ma10 > 0))
    ):
        ctx.market_regime = "趋势主升"
        ctx.technical_weight = "中"
        ctx.factor_weight = "高"
        ctx.company_weight = "高"
        ctx.interpretation_rules = [
            "强趋势中 RSI 超买不单独构成卖出理由",
            "重点观察放量滞涨、板块退潮和跌破短期趋势线",
            "MA 在主升阶段主要作为持仓纪律，而非提前看空依据",
            "趋势延续时，回调至 MA5/MA10 是低吸机会而非风险",
        ]
        ctx.strategy_notes = [
            "当前处于趋势主升环境，技术指标权重降低",
            "重点关注板块延续性和龙头强度",
            "公司逻辑和行业因子是核心判断依据",
        ]
        return ctx

    # 2. 高位分歧
    if (
        "偏多" in trend
        and rsi > 70
        and change_pct > 0
        and ("超买" in signal or ma_bull)
    ):
        ctx.market_regime = "高位分歧"
        ctx.technical_weight = "中"
        ctx.factor_weight = "高"
        ctx.company_weight = "高"
        ctx.interpretation_rules = [
            "高位分歧阶段不宜机械追涨",
            "重点观察是否放量滞涨、长上影或资金退潮",
            "强逻辑个股回调不一定破坏中期趋势，但短线风险收益下降",
            "RSI >70 在高位分歧中代表情绪过热，需警惕而非加仓",
        ]
        ctx.strategy_notes = [
            "当前处于高位分歧环境，需区分趋势延续与顶部信号",
            "关注成交量变化：缩量上涨为风险，放量上涨需看持续性",
            "公司逻辑强度决定分歧后能否继续上行",
        ]
        return ctx

    # 3. 事件驱动
    if event_driven:
        ctx.market_regime = "事件驱动"
        ctx.technical_weight = "低"
        ctx.factor_weight = "高"
        ctx.company_weight = "高"
        ctx.interpretation_rules = [
            "事件驱动行情中技术指标只辅助节奏判断",
            "核心是事件强度、兑现节奏和市场是否已经 price in",
            "未兑现的强催化剂提供安全边际，已兑现需警惕利好出尽",
            "事件证伪时，无论技术形态如何都应果断离场",
        ]
        ctx.strategy_notes = [
            "当前具备事件驱动属性，技术指标权重显著降低",
            "重点评估事件真实性和兑现时间线",
            "公司逻辑和催化剂强度是定价核心",
        ]
        return ctx

    # 4. 下跌趋势
    if (
        "偏空" in trend
        and macd < 0
        and (ma_bear or (ma5 < ma10 and ma5 > 0))
    ):
        ctx.market_regime = "下跌趋势"
        ctx.technical_weight = "高"
        ctx.factor_weight = "中"
        ctx.company_weight = "中"
        ctx.interpretation_rules = [
            "RSI 超卖只代表短线反弹需求，不代表趋势反转",
            "反弹必须观察是否放量站回关键均线",
            "未出现资金回流前不宜过早判断反转",
            "MACD <0 且均线空头排列时，任何反弹都视为减仓机会",
        ]
        ctx.strategy_notes = [
            "当前处于下跌趋势，技术指标权重提高",
            "左侧抄底风险极高，建议等待趋势确认反转",
            "公司基本面再强也拗不过趋势，观望为主",
        ]
        return ctx

    # 5. 震荡筑底
    if (
        "震荡" in trend
        and 30 <= rsi <= 55
        and abs(macd) < 5
        and not ma_bull
        and not ma_bear
    ):
        ctx.market_regime = "震荡筑底"
        ctx.technical_weight = "中"
        ctx.factor_weight = "中"
        ctx.company_weight = "高"
        ctx.interpretation_rules = [
            "重点观察箱体突破和放量确认",
            "MA20/MA60 修复权重提高",
            "底部阶段应关注公司逻辑是否具备再定价基础",
            "RSI 中性区间代表多空均衡，等待方向选择",
        ]
        ctx.strategy_notes = [
            "当前处于震荡筑底环境，等待方向确认",
            "公司 Alpha 在筑底阶段尤为重要：好的逻辑提供底部支撑",
            "箱体下沿低吸、上沿减仓，突破后加仓",
        ]
        return ctx

    # 6. 题材轮动
    if (
        "震荡" in trend
        and abs(change_pct) > 3
        and rsi > 60
        and not ma_bull
    ):
        ctx.market_regime = "题材轮动"
        ctx.technical_weight = "低"
        ctx.factor_weight = "高"
        ctx.company_weight = "中"
        ctx.interpretation_rules = [
            "题材轮动中个股涨跌与基本面关联度降低",
            "追涨轮动题材风险极高，适合埋伏而非追高",
            "轮动退潮时跌幅往往大于涨幅，严格止损",
        ]
        ctx.strategy_notes = [
            "当前处于题材轮动环境，快进快出为主",
            "关注题材切换节奏，提前布局低位题材",
            "不建议重仓参与轮动，仓位控制是关键",
        ]
        return ctx

    # 默认：震荡观察
    ctx.market_regime = "震荡观察"
    ctx.technical_weight = "中"
    ctx.factor_weight = "中"
    ctx.company_weight = "中"
    ctx.interpretation_rules = [
        "震荡环境中，技术指标提供区间判断参考",
        "MA 交叉和 MACD 金叉死叉信号需结合量能确认",
        "RSI 40-60 为中性区间，不单独作为买卖依据",
        "等待明确方向信号出现后再加仓",
    ]
    ctx.strategy_notes = [
        "当前处于震荡观察环境，方向不明朗",
        "保持轻仓或观望，等待趋势确认",
        "重点关注公司逻辑和行业催化剂是否可能打破震荡",
    ]
    return ctx
