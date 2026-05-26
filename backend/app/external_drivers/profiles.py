from __future__ import annotations

from app.external_drivers.schemas import ExternalDriver, ExternalDriverProfile, RetrievalConfig
from app.facts.common import compact_symbol, to_ts_code


MAPPING_BOUNDARY = (
    "External-driver mapping is a product configuration used to select observation variables. "
    "It does not prove these factors dominate the stock price in the current period and must not "
    "be used as a system buy/sell conclusion."
)

DEFAULT_UNMAPPED = {
    "mapping_status": "not_configured",
    "profile_id": "DEFAULT_UNMAPPED_V1",
    "message": "当前未为该标的配置专属外部驱动因子。系统仅保留个股自身证据，不自动附加商品、汇率或板块驱动。",
    "future_extension": "可在后续根据行业、主题或用户观察需求新增映射。",
    "drivers": [],
    "boundary": MAPPING_BOUNDARY,
}


def _driver(
    factor_id: str,
    display_name: str,
    factor_type: str,
    importance: str,
    provider: str,
    endpoint: str,
    inclusion_reason: str,
    interpretation_limit: str,
    *,
    provider_symbol: str | None = None,
    status: str = "configured",
) -> ExternalDriver:
    return ExternalDriver(
        factor_id=factor_id,
        display_name=display_name,
        factor_type=factor_type,
        importance=importance,
        retrieval_config=RetrievalConfig(
            provider=provider,
            endpoint=endpoint,
            provider_symbol=provider_symbol if status == "configured" else None,
            code=provider_symbol if status == "configured" else None,
        ),
        inclusion_reason=inclusion_reason,
        interpretation_limit=interpretation_limit,
        status=status,
    )


COPPER = _driver(
    "copper_futures",
    "Copper futures daily price",
    "commodity",
    "core_if_available",
    "tushare",
    "fut_daily",
    "Resource producers may have earnings or sentiment sensitivity to copper price observations.",
    "Copper futures are background facts only; no causality or profit impact is inferred.",
    provider_symbol="CU.SHF",
)

GOLD_FUTURE = _driver(
    "gold_futures",
    "Gold futures daily price",
    "commodity",
    "conditional",
    "tushare",
    "fut_daily",
    "Gold exposure can be relevant for precious-metal miners and gold-themed instruments.",
    "Gold futures provider code still requires a successful probe before automatic retrieval.",
    status="pending_probe",
)

USDCNH = _driver(
    "usd_cnh",
    "USD/CNH daily FX",
    "fx",
    "context",
    "tushare",
    "fx_daily",
    "FX can affect globally priced commodities and overseas revenue/cost translation.",
    "FX is context only and must not be treated as a direct driver without separate evidence.",
    provider_symbol="USDCNH.FXCM",
)

AI_ETF = _driver(
    "ai_theme_etf_159382",
    "AI theme ETF share, NAV, and price",
    "theme_etf",
    "context",
    "tushare",
    "etf_share_size,fund_nav,fund_daily",
    "AI/PCB hardware names can be observed alongside a liquid AI-theme ETF proxy.",
    "ETF facts are background observations only and do not prove theme inflow into a specific stock.",
    provider_symbol="159382.SZ",
)

GOLD_ETF = _driver(
    "gold_etf_159934",
    "Gold ETF share, NAV, and price",
    "theme_etf",
    "context",
    "tushare",
    "etf_share_size,fund_nav,fund_daily",
    "Gold ETF facts can provide a listed gold-theme context observation.",
    "ETF facts are background observations only and do not prove fund flow into miners.",
    provider_symbol="159934.SZ",
)

PCB_PLACEHOLDER = _driver(
    "pcb_sector_index_placeholder",
    "PCB sector index placeholder",
    "unsupported_placeholder",
    "conditional",
    "stock-pilot",
    "not_configured",
    "PCB-specific sector-index mapping needs a verified provider code before automatic retrieval.",
    "Placeholder only; no market fact is retrieved and no conclusion should be drawn.",
    status="unsupported",
)

TUNGSTEN_PLACEHOLDER = _driver(
    "tungsten_price_placeholder",
    "Tungsten price placeholder",
    "unsupported_placeholder",
    "conditional",
    "stock-pilot",
    "not_configured",
    "No verified tungsten daily series is configured in this round.",
    "Placeholder only; no market fact is retrieved and no conclusion should be drawn.",
    status="unsupported",
)

TIN_PLACEHOLDER = _driver(
    "tin_price_placeholder",
    "Tin price placeholder",
    "unsupported_placeholder",
    "conditional",
    "stock-pilot",
    "not_configured",
    "No verified tin daily series is configured in this round.",
    "Placeholder only; no market fact is retrieved and no conclusion should be drawn.",
    status="unsupported",
)

COBALT_MOLY_PLACEHOLDER = _driver(
    "cobalt_moly_price_placeholder",
    "Cobalt/Molybdenum price placeholder",
    "unsupported_placeholder",
    "conditional",
    "stock-pilot",
    "not_configured",
    "No verified cobalt or molybdenum daily series is configured in this round.",
    "Placeholder only; no market fact is retrieved and no conclusion should be drawn.",
    status="unsupported",
)

RESOURCE_SECTOR_PLACEHOLDER = _driver(
    "resource_sector_index_placeholder",
    "Resource sector index placeholder",
    "unsupported_placeholder",
    "conditional",
    "stock-pilot",
    "not_configured",
    "Resource sector index mapping needs a verified provider code before automatic retrieval.",
    "Placeholder only; no market fact is retrieved and no conclusion should be drawn.",
    status="unsupported",
)

COMEX_COPPER = _driver(
    "comex_copper_yahoo",
    "COMEX Copper Futures Reference",
    "commodity",
    "context",
    "yahoo_finance",
    "v8/finance/chart",
    "International copper futures background observation via Yahoo Finance COMEX delayed quote.",
    "Yahoo Finance COMEX delayed reference only; not official CME settlement, not realtime, not a causal conclusion, and not trading advice. Does not replace domestic futures prices.",
    provider_symbol="HG=F",
)

COMEX_GOLD = _driver(
    "comex_gold_yahoo",
    "COMEX Gold Futures Reference",
    "commodity",
    "context",
    "yahoo_finance",
    "v8/finance/chart",
    "International gold futures background observation via Yahoo Finance COMEX delayed quote.",
    "Yahoo Finance COMEX delayed reference only; not official CME settlement, not realtime, not a causal conclusion, and not trading advice. Does not replace domestic futures prices.",
    provider_symbol="GC=F",
)

COMEX_SILVER = _driver(
    "comex_silver_yahoo",
    "COMEX Silver Futures Reference",
    "commodity",
    "context",
    "yahoo_finance",
    "v8/finance/chart",
    "International silver futures background observation via Yahoo Finance COMEX delayed quote.",
    "Yahoo Finance COMEX delayed reference only; not official CME settlement, not realtime, not a causal conclusion, and not trading advice. Does not replace domestic futures prices.",
    provider_symbol="SI=F",
)


PROFILES = [
    ExternalDriverProfile(
        profile_id="ZIJIN_RESOURCE_METALS_V1",
        profile_name="Zijin Mining external drivers",
        description="Metal and FX context for Zijin Mining including COMEX international reference.",
        applies_to_symbols=["601899.SH"],
        applies_to_primary_themes=["METAL_RESOURCE", "GOLD"],
        drivers=[COPPER, GOLD_FUTURE, USDCNH, GOLD_ETF, COMEX_COPPER, COMEX_GOLD],
        boundary=MAPPING_BOUNDARY,
    ),
    ExternalDriverProfile(
        profile_id="AI_PCB_HARDWARE_V1",
        profile_name="AI PCB hardware external drivers",
        description="AI ETF context and PCB placeholder for AI/PCB hardware names.",
        applies_to_symbols=["002916.SZ", "002463.SZ"],
        applies_to_primary_themes=["AI_PCB"],
        drivers=[AI_ETF, PCB_PLACEHOLDER],
        boundary=MAPPING_BOUNDARY,
    ),
    ExternalDriverProfile(
        profile_id="LUOMO_RESOURCE_METALS_V1",
        profile_name="Luomo Mining external drivers",
        description="Copper and FX context for Luomo Mining; cobalt/molybdenum remain uncovered; COMEX copper reference added.",
        applies_to_symbols=["603993.SH"],
        applies_to_primary_themes=["METAL_RESOURCE"],
        drivers=[COPPER, USDCNH, COBALT_MOLY_PLACEHOLDER, RESOURCE_SECTOR_PLACEHOLDER, COMEX_COPPER],
        boundary=MAPPING_BOUNDARY,
    ),
    ExternalDriverProfile(
        profile_id="XIYAN_TIN_RESOURCE_V1",
        profile_name="Xiyan tin resource external drivers",
        description="Tin placeholder and FX context for Xiyan; tin price is not verified in this round.",
        applies_to_symbols=["000960.SZ"],
        applies_to_primary_themes=["METAL_RESOURCE"],
        drivers=[TIN_PLACEHOLDER, USDCNH, RESOURCE_SECTOR_PLACEHOLDER],
        boundary=MAPPING_BOUNDARY,
    ),
    ExternalDriverProfile(
        profile_id="ZHONGWU_RESOURCE_AI_PCB_V1",
        profile_name="Zhongwu resource and AI/PCB external drivers",
        description="Resource-side placeholders plus AI-theme ETF context for Zhongwu High-Tech.",
        applies_to_symbols=["000657.SZ"],
        applies_to_primary_themes=["METAL_RESOURCE", "AI_PCB", "TUNGSTEN"],
        drivers=[TUNGSTEN_PLACEHOLDER, COPPER, AI_ETF, PCB_PLACEHOLDER],
        boundary=MAPPING_BOUNDARY,
    ),
    ExternalDriverProfile(
        profile_id="AI_THEME_ETF_SELF_V1",
        profile_name="AI theme ETF self facts",
        description="ETF share, NAV, and price facts for the AI theme ETF itself.",
        applies_to_symbols=["159382.SZ"],
        applies_to_primary_themes=["AI_THEME_ETF"],
        drivers=[AI_ETF],
        boundary=MAPPING_BOUNDARY,
    ),
    ExternalDriverProfile(
        profile_id="GOLD_ETF_SELF_V1",
        profile_name="Gold ETF self facts",
        description="ETF share, NAV, and price facts for the gold ETF itself plus COMEX gold reference.",
        applies_to_symbols=["159934.SZ"],
        applies_to_primary_themes=["GOLD"],
        drivers=[GOLD_ETF, COMEX_GOLD],
        boundary=MAPPING_BOUNDARY,
    ),
    ExternalDriverProfile(
        profile_id="COMEX_SILVER_CAPABILITY_V1",
        profile_name="COMEX Silver capability placeholder",
        description="COMEX silver futures reference is supported as a provider capability but not mapped to current holdings.",
        applies_to_symbols=[],
        applies_to_primary_themes=[],
        drivers=[COMEX_SILVER],
        boundary=MAPPING_BOUNDARY,
    ),
]


def find_profile(symbol: str, primary_theme: str | None = None) -> ExternalDriverProfile | None:
    ts_code = to_ts_code(symbol)
    compact = compact_symbol(symbol)
    for profile in PROFILES:
        symbols = {to_ts_code(item) for item in profile.applies_to_symbols}
        compacts = {compact_symbol(item) for item in profile.applies_to_symbols}
        if ts_code in symbols or compact in compacts:
            return profile
    return None
