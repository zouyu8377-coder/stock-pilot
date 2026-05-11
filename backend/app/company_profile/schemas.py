from pydantic import BaseModel, Field


class CompanyProfile(BaseModel):
    company_name: str = ""
    main_business: str = ""
    core_products: list[str] = Field(default_factory=list)
    industry_chain_position: str = ""
    core_logic: list[str] = Field(default_factory=list)
    concept_tags: list[str] = Field(default_factory=list)
    company_type: list[str] = Field(default_factory=list)
    profit_driver: str = ""
    competitive_advantage: str = ""
    risk_points: list[str] = Field(default_factory=list)
