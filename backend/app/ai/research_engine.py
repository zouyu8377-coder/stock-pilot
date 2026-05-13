import json
import re
import time
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


def _build_fallback(error_msg: str = "", stock_data: dict | None = None) -> dict:
    """构建兼容新/旧结构的 fallback 响应"""
    report = ResearchReport()
    result = format_research_report(report)
    result["trading_bias"] = "分析失败"
    result["trading_advice"] = "AI返回格式异常"
    result["risk_level"] = "高"
    result["summary"] = f"错误: {error_msg[:50]}" if error_msg else "AI处理异常"
    result["is_fallback"] = True
    if stock_data:
        _apply_data_coverage(
            result,
            stock_data,
            set((stock_data.get("data_coverage") or {}).get("missing_labels", [])),
        )
    return result


def generate_research_report(stock_data: dict) -> dict:
    prompt = build_prompt(stock_data)
    allowed_missing = set((stock_data.get("data_coverage") or {}).get("missing_labels", []))
    print(f"[LLM] Prompt length: chars={len(prompt)}, bytes={len(prompt.encode('utf-8'))}")

    try:
        started = time.perf_counter()
        raw_response = call_llm(prompt)
        elapsed = time.perf_counter() - started
        print(f"[LLM] Request completed in {elapsed:.1f}s")
        print(f"[LLM] Raw response ({len(raw_response)} chars): {raw_response[:500]}...")

        data = extract_json(raw_response)
        print(f"[PARSE] Parsed JSON keys: {list(data.keys()) if data else 'None'}")

        if not data:
            print("[VALIDATION] Empty JSON extracted")
            data = _retry_compact_json(prompt)
            if not data:
                return _build_fallback("Empty JSON response", stock_data)

        # 尝试用新 schema 解析
        try:
            report = ResearchReport(**data)
            print("[VALIDATION] ResearchReport parsed successfully (new schema)")
            result = format_research_report(report)
            _apply_data_coverage(result, stock_data, allowed_missing)
            return result
        except ValidationError as ve:
            print(f"[VALIDATION] Pydantic validation failed: {ve}")
            # 尝试修复常见字段缺失问题后重新解析
            _patch_legacy_fields(data)
            try:
                report = ResearchReport(**data)
                print("[VALIDATION] ResearchReport parsed after patching")
                result = format_research_report(report)
                _apply_data_coverage(result, stock_data, allowed_missing)
                return result
            except ValidationError as ve2:
                print(f"[VALIDATION] Second parse failed: {ve2}")
                # 回退：手动填充默认值
                return _build_fallback(f"Validation failed: {ve2}", stock_data)

    except Exception as e:
        print(f"[ERROR] Research generation failed: {e}")
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        return _build_fallback(str(e), stock_data)


def _retry_compact_json(prompt: str) -> dict:
    retry_prompt = f"""{prompt}

重要：上一次输出不是完整 JSON。请重新输出更紧凑的合法 JSON：
- key_drivers 最多 4 项
- key_price_levels 最多 3 项
- bullish_triggers / bearish_triggers / risk_factors 各最多 2 项
- 所有文本字段尽量短
- 不要输出 markdown，不要解释
"""
    try:
        started = time.perf_counter()
        raw_response = call_llm(retry_prompt)
        elapsed = time.perf_counter() - started
        print(f"[LLM] Compact retry completed in {elapsed:.1f}s")
        print(f"[LLM] Compact retry response ({len(raw_response)} chars): {raw_response[:500]}...")
        return extract_json(raw_response)
    except Exception as e:
        print(f"[LLM] Compact retry failed: {e}")
        return {}


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


def _apply_data_coverage(result: dict, stock_data: dict, allowed_missing: set[str]) -> None:
    data_coverage = stock_data.get("data_coverage") or {}
    if allowed_missing:
        result["missing_data"] = [
            item
            for item in result.get("missing_data", [])
            if item in allowed_missing
        ]
    result["data_coverage"] = data_coverage


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
