"""
Simple rule-based stock analyzer.
No LLM calls - purely technical indicators.
Generates professional technical analysis like Tonghuashifu/Dongfang Caifu.
"""


def analyze_stock(stock: dict) -> dict:
    indicators = stock.get("indicators", {})
    price = stock.get("price", 0)
    change_pct = stock.get("change_pct", 0)

    ma5 = indicators.get("ma5", 0)
    ma10 = indicators.get("ma10", 0)
    ma20 = indicators.get("ma20", 0)
    rsi = indicators.get("rsi14", 50)
    macd = indicators.get("macd", 0)

    # Generate trend
    if price > ma5 > ma10 > ma20:
        trend = "偏多"
    elif price < ma5 < ma10 < ma20:
        trend = "偏空"
    else:
        trend = "震荡"

    # Generate signal
    if rsi < 30:
        signal = "超卖"
    elif rsi > 70:
        signal = "超买"
    elif macd > 0:
        signal = "金叉"
    elif macd < 0:
        signal = "死叉"
    else:
        signal = "观望"

    # Generate support/resistance
    support = f"{price * 0.98:.0f}/{price * 0.95:.0f}"
    resistance = f"{price * 1.02:.0f}/{price * 1.05:.0f}"

    # Generate professional summary like trading software
    summary_parts = []

    # RSI analysis
    if rsi < 30:
        summary_parts.append(f"当前RSI={rsi:.1f}，短线进入超卖区域，存在技术性反弹需求")
    elif rsi > 70:
        summary_parts.append(f"当前RSI={rsi:.1f}，短线进入超买区域，需警惕回调压力")
    else:
        summary_parts.append(f"当前RSI={rsi:.1f}，位于中性区间")

    # MACD analysis
    if macd > 0:
        summary_parts.append("MACD维持多头结构，短线相对强势")
    elif macd < 0:
        summary_parts.append("MACD仍处于空头区间，趋势偏弱")

    # MA analysis
    if ma5 > ma10:
        summary_parts.append("短期均线维持向上态势")
    elif ma5 < ma10:
        summary_parts.append("短期均线呈下行态势")

    # Overall assessment
    if trend == "偏多" and macd > 0:
        summary_parts.append("综合来看，短线多头动能占优")
    elif trend == "偏空" and macd < 0:
        summary_parts.append("综合来看，短线空头压力较大，建议观望")
    else:
        summary_parts.append("综合来看，短线处于震荡整理阶段")

    summary = "。".join(summary_parts)

    return {
        "trend": trend,
        "signal": signal,
        "support": support,
        "resistance": resistance,
        "summary": summary
    }