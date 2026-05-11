import json

from app.ai.templates.generic import GENERIC_TEMPLATE
from app.ai.templates.baijiu import BAIJIU_TEMPLATE
from app.ai.templates.semiconductor import SEMICONDUCTOR_TEMPLATE
from app.ai.templates.bank import BANK_TEMPLATE
from app.ai.templates.gold import GOLD_TEMPLATE
from app.factors.factor_engine import get_industry_factors
from app.company_profile.schemas import CompanyProfile


def _select_template(industry: str | None) -> str:
    if not industry:
        return GENERIC_TEMPLATE

    industry_lower = industry.lower()

    if "白酒" in industry_lower or "酒" in industry_lower:
        return BAIJIU_TEMPLATE

    if "半导体" in industry_lower or "芯片" in industry_lower or "集成电路" in industry_lower:
        return SEMICONDUCTOR_TEMPLATE

    if "银行" in industry_lower or "金融" in industry_lower:
        return BANK_TEMPLATE

    if "黄金" in industry_lower or "贵金属" in industry_lower or "有色" in industry_lower:
        return GOLD_TEMPLATE

    return GENERIC_TEMPLATE


def _format_factors(industry: str | None) -> str:
    factors = get_industry_factors(industry)
    lines = []
    for f in factors:
        lines.append(f"- {f.factor_name}: {f.impact}")
    return "\n".join(lines)


def _format_company_profile(profile: CompanyProfile | None) -> str:
    if not profile:
        return ""

    lines = [
        f"公司主营业务：{profile.main_business or '未知'}",
        f"核心产品：{', '.join(profile.core_products) if profile.core_products else '未知'}",
        f"产业链位置：{profile.industry_chain_position or '未知'}",
        f"核心逻辑：{', '.join(profile.core_logic) if profile.core_logic else '未知'}",
        f"概念标签：{', '.join(profile.concept_tags) if profile.concept_tags else '无'}",
        f"竞争优势：{profile.competitive_advantage or '未知'}",
        f"主要风险：{', '.join(profile.risk_points) if profile.risk_points else '未知'}",
    ]
    return "\n".join(lines)


def build_prompt(stock_data: dict) -> str:
    name = stock_data.get("name", "")
    symbol = stock_data.get("symbol", "")
    price = stock_data.get("price", 0)
    change_pct = stock_data.get("change_pct", 0)
    industry = stock_data.get("industry")
    indicators = stock_data.get("indicators", {})
    analysis = stock_data.get("analysis", {})
    company_profile: CompanyProfile | None = stock_data.get("company_profile")

    template = _select_template(industry)
    factors_str = _format_factors(industry)
    profile_str = _format_company_profile(company_profile)

    indicators_str = json.dumps(indicators, ensure_ascii=False, indent=2)
    analysis_str = json.dumps(analysis, ensure_ascii=False, indent=2)

    profile_section = f"""
## 公司画像
{profile_str}
""" if profile_str else ""

    prompt = f"""
你不是财经媒体。
你是私募基金交易员。

禁止：
- 空泛宏观描述
- 新闻摘要
- 套话
- 模糊判断

你必须用**交易语言**，给出明确的买入/卖出/观望建议。

分析时必须结合：
- 公司主营业务
- 公司产业链位置
- 公司核心竞争力
- 公司概念属性

禁止只分析技术指标。

---

## 股票信息
- 股票名称：{name}
- 股票代码：{symbol}
- 当前价格：{price:.2f} 元
- 涨跌幅：{change_pct:+.2f}%
- 所属行业：{industry or "未知"}

{profile_section}

## 技术指标
{indicators_str}

## AI快速分析结论
{analysis_str}

---

## 行业关键因子
{factors_str}

---

## 行业分析模板
{template}

---

## 输出要求

生成严格JSON，字段如下：

1. trading_bias: 交易偏向，如"偏多"/"偏空"/"震荡"（10字以内）
2. trading_advice: 交易建议，明确说明当前是否适合买入（40字以内）
3. win_rate: 胜率（0-100的整数）
4. profit_loss_ratio: 盈亏比（浮点数，如1.8）
5. risk_level: 风险等级，"低"/"中"/"高"
6. bull_score: 多头评分（0-100整数）
7. bear_score: 空头评分（0-100整数）
8. key_drivers: 核心驱动因素（数组，最多6项，每项20字以内，▲开头=利多，▼开头=利空）
9. sector_capital_flow: 行业资金观察（60字以内）
10. key_price_levels: 关键价格位（数组，最多4项，每项15字以内）
11. short_term: 短线判断（10字以内）
12. medium_term: 中线判断（10字以内）
13. long_term: 长线判断（10字以内）
14. industry_analysis: 行业分析（80字以内）
15. risk_factors: 风险因素（数组，最多3项）
16. summary: 总结（80字以内）

---

## 格式要求
- 必须输出合法JSON
- 不要使用markdown
- 不要输出解释文字
- 用交易语言，不是新闻语言
"""

    return prompt


if __name__ == "__main__":
    mock_data = {
        "name": "贵州茅台",
        "symbol": "600519",
        "price": 1372.99,
        "change_pct": 0.14,
        "industry": "白酒行业",
        "indicators": {
            "ma5": 1381.0,
            "ma10": 1400.02,
            "ma20": 1421.52,
            "rsi14": 27.44,
            "macd": -16.49
        },
        "analysis": {
            "trend": "偏空",
            "signal": "观望",
            "support": "1370/1350",
            "resistance": "1381/1400",
            "summary": "短线超卖但趋势偏弱，等待企稳信号"
        }
    }

    prompt = build_prompt(mock_data)
    print(prompt)