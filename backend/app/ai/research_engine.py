import json
import re
import traceback
from pydantic import ValidationError

from app.ai.prompt_builder import build_prompt
from app.ai.llm_client import call_llm
from app.ai.schemas import ResearchReport, PriceLevel, TimeframeView
from app.ai.formatter import format_research_report


def extract_json(text: str) -> dict:
    """Enhanced JSON extraction with markdown handling"""
    if not text:
        print("[EXTRACT] Empty response")
        return {}

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON in markdown code block
    try:
        cleaned = re.sub(r'^```json\s*', '', text)
        cleaned = re.sub(r'^```\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)

        match = re.search(r'\{[\s\S]*\}', cleaned)
        if match:
            return json.loads(match.group())
    except json.JSONDecodeError as e:
        print(f"[EXTRACT] Markdown cleanup failed: {e}")

    # Try line-by-line JSON detection
    try:
        lines = text.split('\n')
        json_lines = []
        in_json = False
        brace_count = 0

        for line in lines:
            if '{' in line and not in_json:
                in_json = True
                brace_count = line.count('{') - line.count('}')
                json_lines.append(line)
            elif in_json:
                json_lines.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count == 0:
                    break

        if json_lines:
            return json.loads('\n'.join(json_lines))
    except json.JSONDecodeError as e:
        print(f"[EXTRACT] Line-by-line failed: {e}")

    print(f"[EXTRACT] All methods failed, response length: {len(text)}")
    return {}


def _build_fallback(error_msg: str = "") -> dict:
    """构建兼容新/旧结构的 fallback 响应"""
    report = ResearchReport()
    result = format_research_report(report)
    result["trading_bias"] = "分析失败"
    result["trading_advice"] = "AI返回格式异常"
    result["risk_level"] = "高"
    result["summary"] = f"错误: {error_msg[:50]}" if error_msg else "AI处理异常"
    return result


def generate_research_report(stock_data: dict) -> dict:
    prompt = build_prompt(stock_data)

    try:
        raw_response = call_llm(prompt)
        print(f"[LLM] Raw response ({len(raw_response)} chars): {raw_response[:500]}...")

        data = extract_json(raw_response)
        print(f"[PARSE] Parsed JSON keys: {list(data.keys()) if data else 'None'}")

        if not data:
            print("[VALIDATION] Empty JSON extracted")
            return _build_fallback("Empty JSON response")

        # 尝试用新 schema 解析
        try:
            report = ResearchReport(**data)
            print("[VALIDATION] ResearchReport parsed successfully (new schema)")
            return format_research_report(report)
        except ValidationError as ve:
            print(f"[VALIDATION] Pydantic validation failed: {ve}")
            # 尝试修复常见字段缺失问题后重新解析
            _patch_legacy_fields(data)
            try:
                report = ResearchReport(**data)
                print("[VALIDATION] ResearchReport parsed after patching")
                return format_research_report(report)
            except ValidationError as ve2:
                print(f"[VALIDATION] Second parse failed: {ve2}")
                # 回退：手动填充默认值
                return _build_fallback(f"Validation failed: {ve2}")

    except Exception as e:
        print(f"[ERROR] Research generation failed: {e}")
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return _build_fallback(str(e))


def _patch_legacy_fields(data: dict) -> None:
    """
    将旧版字段映射到新版结构，以便兼容。
    直接修改传入的 dict。
    """
    # key_price_levels 旧版是字符串数组，新版是对象数组
    kpl = data.get("key_price_levels", [])
    if kpl and isinstance(kpl, list) and len(kpl) > 0 and isinstance(kpl[0], str):
        data["key_price_levels"] = [
            {"price": 0, "type": "", "meaning": item}
            for item in kpl
        ]

    # short_term / medium_term / long_term 旧版可能是字符串
    for field in ["short_term", "medium_term", "long_term"]:
        val = data.get(field)
        if isinstance(val, str):
            data[field] = {"view": val, "action": ""}

    # 确保关键字段存在
    for field in ["trade_thesis", "strategy_type", "invalid_condition", "company_alpha", "industry_beta", "market_regime"]:
        if field not in data:
            data[field] = ""

    for field in ["confidence_score", "odds_score"]:
        if field not in data:
            data[field] = 50

    for field in ["bullish_triggers", "bearish_triggers", "missing_data", "selected_models"]:
        if field not in data:
            data[field] = []


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

    print("=== Testing Research Engine ===")
    result = generate_research_report(mock_data)
    print(json.dumps(result, ensure_ascii=False, indent=2))
