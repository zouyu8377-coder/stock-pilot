from pydantic import BaseModel


class CompanyProfile(BaseModel):
    company_name: str = ""
    main_business: str = ""
    core_products: list[str] = []
    industry_chain_position: str = ""
    core_logic: list[str] = []
    concept_tags: list[str] = []
    company_type: list[str] = []
    profit_driver: str = ""
    competitive_advantage: str = ""
    risk_points: list[str] = []
