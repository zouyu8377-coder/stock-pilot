from pydantic import BaseModel


class IndustryFactor(BaseModel):
    factor_name: str
    description: str
    impact: str