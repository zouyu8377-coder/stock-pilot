from app.collector.metadata_provider import metadata_provider
from app.company_profile.providers.business_provider import BusinessProvider
from app.company_profile.providers.concept_provider import ConceptProvider
from app.company_profile.providers.profile_cache import ProfileCache
from app.company_profile.providers.tushare_provider import TushareProvider
from app.company_profile.schemas import CompanyProfile


business_provider = BusinessProvider()
concept_provider = ConceptProvider()
profile_cache = ProfileCache()
tushare_provider = TushareProvider()


def build_company_profile(symbol: str) -> CompanyProfile:
    """
    构建公司画像。优先读缓存，否则组装新画像并写入缓存。
    """
    # Step 0: 读缓存
    cached = profile_cache.get(symbol)
    if cached:
        print(f"[ProfileEngine] cache hit for {symbol}")
        return cached

    # Step 1: 读取 stock_meta 基础信息
    meta = metadata_provider.get(symbol)
    name = meta.get("name", "") if meta else ""
    industry = meta.get("industry", "") if meta else ""

    # Step 2: 调用 Tushare 补充信息
    tushare_info = tushare_provider.get_company_info(symbol)

    # Step 3: 调用 concept_provider 获取概念标签
    concept_tags = concept_provider.get_concepts(name)

    # Step 4: 调用 business_provider 组装画像
    profile = business_provider.build_profile(
        symbol=symbol,
        name=name,
        industry=industry,
        tushare_info=tushare_info,
        concept_tags=concept_tags,
    )

    # Step 5: 写入缓存
    profile_cache.set(symbol, profile)

    return profile
