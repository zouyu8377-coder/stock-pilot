from pydantic import BaseModel, Field


class PriceLevel(BaseModel):
    price: float = 0
    type: str = ""
    meaning: str = ""


class TimeframeView(BaseModel):
    view: str = ""
    action: str = ""


class ResearchReport(BaseModel):
    # 交易假设与策略
    trade_thesis: str = Field(default="")
    trading_bias: str = Field(default="震荡观察")
    strategy_type: str = Field(default="观望")
    trading_advice: str = Field(default="等待分析")

    # 评分体系
    confidence_score: int = Field(default=50)
    odds_score: int = Field(default=50)
    risk_level: str = Field(default="中")

    # 多空力量
    bull_score: int = Field(default=50)
    bear_score: int = Field(default=50)

    # 核心驱动
    key_drivers: list[str] = Field(default_factory=list)

    # 结构化价格位
    key_price_levels: list[PriceLevel] = Field(default_factory=list)

    # 触发条件与失效条件
    invalid_condition: str = Field(default="")
    bullish_triggers: list[str] = Field(default_factory=list)
    bearish_triggers: list[str] = Field(default_factory=list)

    # 短中长期
    short_term: TimeframeView = Field(default_factory=TimeframeView)
    medium_term: TimeframeView = Field(default_factory=TimeframeView)
    long_term: TimeframeView = Field(default_factory=TimeframeView)

    # Alpha / Beta 拆分
    company_alpha: str = Field(default="")
    industry_beta: str = Field(default="")
    industry_analysis: str = Field(default="")

    # 风险与数据缺口
    risk_factors: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)

    # 交易环境（来自策略模型层）
    market_regime: str = Field(default="震荡观察")
    selected_models: list[str] = Field(default_factory=list)

    # 总结
    summary: str = Field(default="")

    # 兼容旧字段
    sector_capital_flow: str = Field(default="")
    market_state: str = Field(default="")
