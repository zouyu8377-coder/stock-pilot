from __future__ import annotations

import pandas as pd

from app.company_profile.schemas import CompanyProfile


def _date_col(df: pd.DataFrame) -> str | None:
    if "date" in df.columns:
        return "date"
    if "日期" in df.columns:
        return "日期"
    return None


def _price_col(df: pd.DataFrame, english: str, chinese: str) -> str | None:
    if english in df.columns:
        return english
    if chinese in df.columns:
        return chinese
    return None


def _volume_col(df: pd.DataFrame) -> str | None:
    if "volume" in df.columns:
        return "volume"
    if "成交量" in df.columns:
        return "成交量"
    return None


def _truthy_text(value: str | None) -> bool:
    return bool(value and value.strip() and value.strip() not in {"未知", "无"})


def _price_structure(history: pd.DataFrame) -> dict:
    high_col = _price_col(history, "high", "最高")
    close_col = _price_col(history, "close", "收盘")
    volume_col = _volume_col(history)
    date_col = _date_col(history)
    if history is None or history.empty or not high_col or not close_col:
        return {
            "available": False,
            "reason": "缺少历史价格数据",
        }

    df = history.copy()
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df[high_col] = pd.to_numeric(df[high_col], errors="coerce")
    df[close_col] = pd.to_numeric(df[close_col], errors="coerce")
    df = df.dropna(subset=[high_col, close_col])
    if df.empty:
        return {
            "available": False,
            "reason": "历史价格无法解析",
        }

    recent = df.tail(250)
    high_idx = recent[high_col].idxmax()
    previous_high = float(recent.loc[high_idx, high_col])
    previous_high_date = str(recent.loc[high_idx, date_col])[:10] if date_col else ""
    latest_close = float(df.iloc[-1][close_col])
    distance_pct = round((latest_close / previous_high - 1) * 100, 2) if previous_high else None

    volume_pressure = None
    if volume_col and volume_col in recent.columns:
        tmp = recent.copy()
        tmp[volume_col] = pd.to_numeric(tmp[volume_col], errors="coerce")
        lower = previous_high * 0.95
        upper = previous_high * 1.05
        zone_volume = tmp[(tmp[close_col] >= lower) & (tmp[close_col] <= upper)][volume_col].sum()
        total_volume = tmp[volume_col].sum()
        if total_volume:
            volume_pressure = round(float(zone_volume / total_volume * 100), 2)

    return {
        "available": True,
        "previous_high": round(previous_high, 2),
        "previous_high_date": previous_high_date,
        "latest_close": round(latest_close, 2),
        "distance_pct": distance_pct,
        "overhang_volume_pct": volume_pressure,
        "source": "本地日K线近250日",
    }


def build_data_coverage(
    company_profile: CompanyProfile | None,
    history: pd.DataFrame,
    stock_data: dict,
) -> dict:
    provided: list[dict] = []
    missing: list[dict] = []

    if company_profile and (
        _truthy_text(company_profile.main_business)
        or company_profile.core_products
        or _truthy_text(company_profile.industry_chain_position)
    ):
        provided.append({
            "key": "company_business",
            "label": "主营业务及产品结构",
            "source": "本地公司画像/Tushare缓存/规则推断",
            "detail": {
                "main_business": company_profile.main_business,
                "core_products": company_profile.core_products,
                "industry_chain_position": company_profile.industry_chain_position,
            },
        })
    else:
        missing.append({
            "key": "company_business",
            "label": "主营业务及产品结构",
            "reason": "公司画像缺少主营业务或核心产品",
            "possible_sources": ["年报", "半年报", "招股书", "公司官网"],
        })

    price_structure = _price_structure(history)
    if price_structure.get("available"):
        provided.append({
            "key": "price_overhang",
            "label": "前高与套牢区分布",
            "source": price_structure.get("source"),
            "detail": price_structure,
        })
    else:
        missing.append({
            "key": "price_overhang",
            "label": "前高与套牢区分布",
            "reason": price_structure.get("reason", "缺少价格结构数据"),
            "possible_sources": ["本地K线", "成交量价格分布"],
        })

    missing.extend([
        {
            "key": "orders_capacity",
            "label": "最新订单与产能利用率",
            "reason": "当前未接入公告/调研纪要/互动易等事件文本源",
            "possible_sources": ["投资者关系活动记录", "互动易", "定期报告", "公司公告"],
        },
        {
            "key": "northbound_flow",
            "label": "北向资金实时流向",
            "reason": "当前未接入陆股通持股或实时资金流数据",
            "possible_sources": ["深股通持股", "港交所披露", "交易所/行情数据源"],
        },
        {
            "key": "institution_holding",
            "label": "机构持仓变动",
            "reason": "当前未接入基金季报、十大流通股东或机构持仓聚合数据",
            "possible_sources": ["基金季报", "十大流通股东", "定期报告", "机构持仓数据库"],
        },
    ])

    return {
        "provided": provided,
        "missing": missing,
        "missing_labels": [item["label"] for item in missing],
    }
