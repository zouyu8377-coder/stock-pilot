import json
import re
from app.ai.prompt_builder import build_prompt
from app.ai.llm_client import call_llm
from app.ai.schemas import ResearchReport
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
        # Remove markdown code blocks
        cleaned = re.sub(r'^```json\s*', '', text)
        cleaned = re.sub(r'^```\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)

        # Try to find JSON object
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


def generate_research_report(stock_data: dict) -> dict:
    prompt = build_prompt(stock_data)

    try:
        raw_response = call_llm(prompt)
        print(f"[LLM] Raw response ({len(raw_response)} chars): {raw_response[:500]}...")

        data = extract_json(raw_response)
        print(f"[PARSE] Parsed JSON keys: {list(data.keys()) if data else 'None'}")

        # Validate required fields - check for new trading fields
        required_fields = ['trading_bias', 'trading_advice', 'win_rate', 'profit_loss_ratio', 'risk_level', 'bull_score', 'bear_score']
        missing = [f for f in required_fields if f not in data]

        if missing:
            print(f"[VALIDATION] Missing fields: {missing}")
            raise ValueError(f"Invalid JSON: missing {missing}")

        report = ResearchReport(**data)
        return format_research_report(report)

    except Exception as e:
        import traceback
        print(f"[ERROR] Research generation failed: {e}")
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return {
            "trading_bias": "分析失败",
            "trading_advice": "AI返回格式异常",
            "win_rate": 0,
            "profit_loss_ratio": 0.0,
            "risk_level": "高",
            "bull_score": 0,
            "bear_score": 0,
            "key_drivers": ["系统错误"],
            "sector_capital_flow": "获取失败",
            "key_price_levels": ["未知"],
            "short_term": "异常",
            "medium_term": "异常",
            "long_term": "异常",
            "industry_analysis": "AI处理异常",
            "risk_factors": ["系统错误"],
            "summary": f"错误: {str(e)[:50]}"
        }


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