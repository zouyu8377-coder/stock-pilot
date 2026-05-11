import json

from app.ai.templates.generic import GENERIC_TEMPLATE
from app.ai.templates.baijiu import BAIJIU_TEMPLATE
from app.ai.templates.semiconductor import SEMICONDUCTOR_TEMPLATE
from app.ai.templates.bank import BANK_TEMPLATE
from app.ai.templates.gold import GOLD_TEMPLATE
from app.factors.factor_engine import get_industry_factors
from app.company_profile.schemas import CompanyProfile
from app.strategy.schemas import StrategyContext
from app.strategy.models import (
    get_sector_trend_model_rules,
    get_expectation_gap_model_rules,
    get_catalyst_model_rules,
    get_relative_strength_model_rules,
    get_alpha_beta_model_rules,
    get_risk_reward_model_rules,
)


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


def _format_strategy_context(ctx: StrategyContext | None) -> str:
    if not ctx:
        return ""

    lines = [
        f"当前交易环境：{ctx.market_regime}",
        f"适用分析模型：{', '.join(ctx.selected_models) if ctx.selected_models else '通用模型'}",
        f"技术指标权重：{ctx.technical_weight}",
        f"行业因子权重：{ctx.factor_weight}",
        f"公司逻辑权重：{ctx.company_weight}",
    ]

    if ctx.interpretation_rules:
        lines.append("\n解释原则：")
        for rule in ctx.interpretation_rules:
            lines.append(f"- {rule}")

    if ctx.strategy_notes:
        lines.append("\n策略提示：")
        for note in ctx.strategy_notes:
            lines.append(f"- {note}")

    return "\n".join(lines)


def _format_model_rules(selected_models: list[str]) -> str:
    """根据选中的模型，返回对应的规则文本"""
    rules_map = {
        "板块主升浪模型": get_sector_trend_model_rules(),
        "预期差模型": get_expectation_gap_model_rules(),
        "催化剂模型": get_catalyst_model_rules(),
        "相对强弱模型": get_relative_strength_model_rules(),
        "公司Alpha/行业Beta拆分模型": get_alpha_beta_model_rules(),
        "风险收益比模型": get_risk_reward_model_rules(),
        "趋势修复模型": get_risk_reward_model_rules(),
        "资金承接模型": get_relative_strength_model_rules(),
    }

    sections = []
    for model in selected_models:
        if model in rules_map:
            sections.append(f"### {model}")
            for rule in rules_map[model]:
                sections.append(f"- {rule}")

    return "\n".join(sections)


def build_prompt(stock_data: dict) -> str:
    name = stock_data.get("name", "")
    symbol = stock_data.get("symbol", "")
    price = stock_data.get("price", 0)
    change_pct = stock_data.get("change_pct", 0)
    industry = stock_data.get("industry")
    indicators = stock_data.get("indicators", {})
    analysis = stock_data.get("analysis", {})
    company_profile: CompanyProfile | None = stock_data.get("company_profile")
    strategy_context: StrategyContext | None = stock_data.get("strategy_context")

    template = _select_template(industry)
    factors_str = _format_factors(industry)
    profile_str = _format_company_profile(company_profile)
    strategy_str = _format_strategy_context(strategy_context)
    model_rules_str = _format_model_rules(strategy_context.selected_models if strategy_context else [])

    indicators_str = json.dumps(indicators, ensure_ascii=False, indent=2)
    analysis_str = json.dumps(analysis, ensure_ascii=False, indent=2)

    profile_section = f"""
## 公司画像
{profile_str}
""" if profile_str else ""

    strategy_section = f"""
## 交易环境识别
{strategy_str}
""" if strategy_str else ""

    model_rules_section = f"""
## 适用模型规则
{model_rules_str}
""" if model_rules_str else ""

    prompt = f"""
你不是财经媒体。你是私募基金交易员。

禁止：
- 空泛宏观描述
- 新闻摘要
- 套话
- 模糊判断
- 只根据 MA、RSI、MACD 得出交易结论

你必须用**交易语言**，给出明确的买入/卖出/观望建议。

分析时必须结合：
- 公司主营业务
- 公司产业链位置
- 公司核心竞争力
- 公司概念属性
- 当前交易环境
- 适用模型规则

禁止只分析技术指标。

---

## 股票信息
- 股票名称：{name}
- 股票代码：{symbol}
- 当前价格：{price:.2f} 元
- 涨跌幅：{change_pct:+.2f}%
- 所属行业：{industry or "未知"}

{profile_section}

{strategy_section}

{model_rules_section}

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

## 数据可信度约束（必须遵守）

1. 凡是输入数据中没有明确提供的事实，不得当作已经发生的事实陈述。
2. 如果没有真实资金流数据，不得声称"北向资金正在流入/流出"，只能写成"需要观察北向资金是否回流"。
3. 如果没有公告、新闻、财报原文，不得编造具体公告或事件。
4. 可以基于行业因子提出观察变量，但不能把观察变量写成事实。
5. 胜率、赔率、风险评分均为主观交易评分，不是统计回测结果。
6. 技术指标必须服从交易环境解释，不得机械套用 RSI 超买/超卖结论。
7. 在趋势主升或事件驱动行情中，MA/RSI/MACD 只作为节奏辅助，不得作为唯一判断依据。

---

## 模型化推理要求（必须按此逻辑思考）

请按以下逻辑分析，但最终只输出 JSON：

1. 当前市场正在交易什么？
2. 这是行业 Beta，还是公司 Alpha？
3. 当前处于启动、主升、分歧、退潮、筑底、下跌中的哪一类？
4. 技术指标在该交易环境下应该如何降权或升权？
5. 当前交易假设是什么？
6. 什么条件出现说明该假设失效？
7. 当前更适合追涨、低吸、波段持有、观望，还是回避？

---

## 输出要求

生成严格JSON，字段如下：

1. trade_thesis: 当前市场正在交易的核心假设（80字以内）
2. trading_bias: 交易偏向，如"偏多震荡"/"偏空震荡"/"趋势主升"/"高位分歧"/"观望"（15字以内）
3. strategy_type: 适合的策略类型，如"回调低吸"/"趋势持有"/"箱体交易"/"事件博弈"/"只观察不参与"（15字以内）
4. trading_advice: 一句交易建议，必须短，不超过50字
5. confidence_score: 主观信心评分，0-100整数
6. odds_score: 赔率评分，0-100整数
7. risk_level: 风险等级，"低"/"中"/"高"
8. bull_score: 多头评分，0-100整数
9. bear_score: 空头评分，0-100整数
10. key_drivers: 核心驱动因素（数组，最多6项，每项24字以内，▲开头=利多，▼开头=利空）
11. key_price_levels: 关键价格位（数组，对象格式，每项包含 price/type/meaning，meaning不超过24字）
12. invalid_condition: 交易假设失效条件（80字以内）
13. bullish_triggers: 看多触发条件（数组，最多3项，每项24字以内）
14. bearish_triggers: 看空触发条件（数组，最多3项，每项24字以内）
15. short_term: 短线判断，对象格式 {{"view": "...", "action": "..."}}
16. medium_term: 中线判断，对象格式 {{"view": "...", "action": "..."}}
17. long_term: 长线判断，对象格式 {{"view": "...", "action": "..."}}
18. company_alpha: 公司自身逻辑（80字以内）
19. industry_beta: 行业/板块逻辑（80字以内）
20. industry_analysis: 行业分析（100字以内）
21. risk_factors: 风险因素（数组，最多3项，每项24字以内）
22. missing_data: 缺失数据（数组，每项20字以内）
23. market_regime: 交易环境（如"趋势主升"）
24. selected_models: 采用的模型（字符串数组）
25. summary: 总结（100字以内）

---

## 格式要求
- 必须输出合法JSON
- 不要使用markdown
- 不要输出解释文字
- 用交易语言，不是新闻语言
- 所有字段必须有值，空字符串或0也可以，不能缺字段
"""

    return prompt


def build_human_prompt(stock_data: dict) -> str:
    """
    构建面向通用 LLM（如 ChatGPT、Claude）的自然语言提示词。
    将 stock_data 直接嵌入为可读文本，要求 LLM 以对话式分析报告输出，而非 JSON。
    用户可直接复制粘贴到任何 LLM 对话窗口中使用。
    """
    name = stock_data.get("name", "")
    symbol = stock_data.get("symbol", "")
    price = stock_data.get("price", 0)
    change_pct = stock_data.get("change_pct", 0)
    industry = stock_data.get("industry")
    indicators = stock_data.get("indicators", {})
    analysis = stock_data.get("analysis", {})
    company_profile: CompanyProfile | None = stock_data.get("company_profile")
    strategy_context: StrategyContext | None = stock_data.get("strategy_context")

    template = _select_template(industry)
    factors_str = _format_factors(industry)
    profile_str = _format_company_profile(company_profile)
    strategy_str = _format_strategy_context(strategy_context)
    model_rules_str = _format_model_rules(strategy_context.selected_models if strategy_context else [])

    # 将技术指标格式化为可读列表
    indicators_lines = []
    for k, v in indicators.items():
        indicators_lines.append(f"- {k}: {v}")
    indicators_text = "\n".join(indicators_lines) if indicators_lines else "（暂无）"

    # 将快速分析结论格式化为可读列表
    analysis_lines = []
    for k, v in analysis.items():
        analysis_lines.append(f"- {k}: {v}")
    analysis_text = "\n".join(analysis_lines) if analysis_lines else "（暂无）"

    profile_section = f"""
## 公司画像
{profile_str}
""" if profile_str else ""

    strategy_section = f"""
## 交易环境识别
{strategy_str}
""" if strategy_str else ""

    model_rules_section = f"""
## 适用模型规则
{model_rules_str}
""" if model_rules_str else ""

    prompt = f"""你是一位私募基金交易员，不是财经媒体评论员。

请基于以下提供的真实市场数据，对 {name}（{symbol}）进行模型化交易分析，并输出一份可直接阅读的中文交易分析报告。

---

## 股票信息
- 股票名称：{name}
- 股票代码：{symbol}
- 当前价格：{price:.2f} 元
- 涨跌幅：{change_pct:+.2f}%
- 所属行业：{industry or "未知"}

{profile_section}

{strategy_section}

{model_rules_section}

## 技术指标
{indicators_text}

## AI 快速分析结论
{analysis_text}

---

## 行业关键因子
{factors_str}

---

## 行业分析模板参考
{template}

---

## 数据可信度约束（必须遵守）

1. 凡是输入数据中没有明确提供的事实，不得当作已经发生的事实陈述。
2. 如果没有真实资金流数据，不得声称"北向资金正在流入/流出"，只能写成"需要观察北向资金是否回流"。
3. 如果没有公告、新闻、财报原文，不得编造具体公告或事件。
4. 可以基于行业因子提出观察变量，但不能把观察变量写成事实。
5. 胜率、赔率、风险评分均为主观交易评分，不是统计回测结果。
6. 技术指标必须服从交易环境解释，不得机械套用 RSI 超买/超卖结论。
7. 在趋势主升或事件驱动行情中，MA/RSI/MACD 只作为节奏辅助，不得作为唯一判断依据。

---

## 模型化推理要求（必须按此逻辑思考）

1. 当前市场正在交易什么？
2. 这是行业 Beta，还是公司 Alpha？
3. 当前处于启动、主升、分歧、退潮、筑底、下跌中的哪一类？
4. 技术指标在该交易环境下应该如何降权或升权？
5. 当前交易假设是什么？
6. 什么条件出现说明该假设失效？
7. 当前更适合追涨、低吸、波段持有、观望，还是回避？

---

## 输出要求

请输出一份结构清晰的**中文交易分析报告**，包含以下章节（使用 markdown 格式）：

### 1. 当前交易观点
- 核心假设（一句话概括当前市场正在交易什么）
- 交易偏向（偏多/偏空/震荡/趋势主升/高位分歧/观望 等）
- 策略类型（回调低吸/趋势持有/箱体交易/事件博弈/只观察不参与 等）
- 一句明确的交易建议

### 2. 评分
- 信心评分（0-100）与理由
- 赔率评分（0-100）与理由
- 风险等级（低/中/高）与理由

### 3. 多空力量对比
- 多头评分（0-100）与核心依据
- 空头评分（0-100）与核心依据

### 4. 核心驱动因素
- 最多 6 项，利多前置 ▲，利空前置 ▼

### 5. 关键价格位
- 支撑/压力/观察位，注明价位（如有）和含义

### 6. 触发条件
- 看多触发（最多 3 项）
- 看空触发（最多 3 项）

### 7. 短中长期判断
- 短线：观点 + 操作建议
- 中线：观点 + 操作建议
- 长线：观点 + 操作建议

### 8. Alpha / Beta 拆分
- 公司自身逻辑（Alpha）
- 行业/板块逻辑（Beta）

### 9. 交易假设失效条件
- 什么信号出现说明当前假设不再成立

### 10. 数据缺口
- 哪些关键信息缺失，可能影响判断

### 11. 风险提示
- 最多 3 项主要风险

### 12. 总结
- 100 字以内的高度概括

---

## 格式要求
- 用交易语言，不是新闻语言
- 禁止空泛宏观描述、套话、模糊判断
- 禁止只根据 MA、RSI、MACD 得出交易结论
- 所有分析必须结合公司画像、交易环境和模型规则
- 不要用 JSON 输出，用自然语言段落和列表
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
