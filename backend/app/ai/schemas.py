from pydantic import BaseModel, Field


class ResearchReport(BaseModel):
    # Trading decision
    trading_bias: str = Field(default="震荡")
    trading_advice: str = Field(default="等待分析")
    win_rate: int = Field(default=50)
    profit_loss_ratio: float = Field(default=1.0)
    risk_level: str = Field(default="中")

    # Multi、空力量
    bull_score: int = Field(default=50)
    bear_score: int = Field(default=50)

    # Key drivers
    key_drivers: list[str] = Field(default_factory=lambda: ["暂无"])

    # Sector capital flow
    sector_capital_flow: str = Field(default="暂无数据")

    # Price levels
    key_price_levels: list[str] = Field(default_factory=lambda: ["暂无"])

    # Legacy fields
    market_state: str = Field(default="震荡")
    short_term: str = Field(default="观望")
    medium_term: str = Field(default="震荡")
    long_term: str = Field(default="待定")
    industry_analysis: str = Field(default="暂无")
    risk_factors: list[str] = Field(default_factory=lambda: ["暂无"])
    summary: str = Field(default="暂无分析")