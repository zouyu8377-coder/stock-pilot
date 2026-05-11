from pydantic import BaseModel, Field


class StrategyContext(BaseModel):
    market_regime: str = "震荡观察"
    selected_models: list[str] = Field(default_factory=list)
    technical_weight: str = "中"
    factor_weight: str = "中"
    company_weight: str = "中"
    interpretation_rules: list[str] = Field(default_factory=list)
    strategy_notes: list[str] = Field(default_factory=list)
