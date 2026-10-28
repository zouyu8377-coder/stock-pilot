"""Allowlisted tools. Public quotes are optional; financial documents are synthetic."""
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

TZ = ZoneInfo("Asia/Shanghai")
SYMBOLS = {"600519": "消费样本A", "600036": "银行样本B", "510300": "宽基样本C"}
ALLOWED_TOOLS = {"market", "disclosure", "events"}
SCENARIOS = [
    {"id": "evidence_gap", "name": "缺失证据补全", "description": "分析侧请求量价与财报，采集后形成新版结论。"},
    {"id": "sufficient", "name": "资料充分直接验收", "description": "初始资料已充分，不强行制造返工。"},
    {"id": "stale_handoff", "name": "旧版本回传拦截", "description": "拒绝旧资料版本，限定返工后重新验收。"},
    {"id": "conflicting_evidence", "name": "利润与现金流冲突", "description": "补充现金流后收缩最初判断。"},
    {"id": "tool_failure", "name": "工具失败后恢复", "description": "注入一次工具故障，重试后继续。"},
    {"id": "unavailable", "name": "证据不可得", "description": "重试耗尽后保留缺口，不伪造成功。"},
    {"id": "permission_blocked", "name": "越权请求拦截", "description": "拒绝交易类工具，退回受限取证。"},
]


def check(request):
    if request.tool not in ALLOWED_TOOLS:
        raise ValueError("工具越权：仅允许 market / disclosure / events；不允许交易、脚本、URL 或路径。")
    if len(set(request.symbols)) != len(request.symbols) or not set(request.symbols) <= SYMBOLS.keys():
        raise ValueError("标的越权：仅允许合成账户的 600519 / 600036 / 510300。")


def public_quotes(symbols):
    # The analyst cannot supply a URL or change the request destination.
    response = requests.get(
        "https://qt.gtimg.cn/q=" + ",".join("sh" + symbol for symbol in symbols),
        timeout=(3, 5), allow_redirects=False,
    )
    response.raise_for_status()
    if response.status_code != 200 or len(response.content) > 128_000:
        raise ValueError("公开行情响应异常或超过大小上限")
    response.encoding = "gbk"
    quotes = {}
    for line in response.text.splitlines():
        if '="' not in line:
            continue
        fields = line.split('="', 1)[1].rstrip('";\r\n').split("~")
        if len(fields) < 35 or fields[2] not in symbols:
            continue
        price = float(fields[3])
        change = float(fields[32])
        if not math.isfinite(price) or price <= 0 or not math.isfinite(change):
            raise ValueError("行情价格不合法")
        observed = datetime.strptime(fields[30], "%Y%m%d%H%M%S").replace(tzinfo=TZ)
        age = (datetime.now(TZ) - observed).total_seconds()
        if age < -300:
            raise ValueError("行情时间位于未来，拒绝使用")
        quotes[fields[2]] = {"symbol": fields[2], "name": fields[1], "price": price,
                              "change_pct": change, "observed_at": observed.isoformat(), "stale": age > 4 * 86400}
    if set(quotes) != set(symbols):
        raise ValueError("公开行情缺少所请求标的；未回填合成报价")
    return list(quotes.values())


def collect(request, run, attempt):
    check(request)
    if run["scenario"] == "tool_failure" and request.tool == "market" and attempt == 1:
        raise TimeoutError("演示故障注入：首次市场工具超时（不是实际网络故障）")
    if run["scenario"] == "unavailable" and request.tool == "market":
        raise TimeoutError("演示故障注入：市场资料持续不可得")
    synthetic = not (request.tool == "market" and run["public_market"])
    source = "constructed_fixture" if synthetic else "tencent_public_quote"
    if request.tool == "market":
        prices = {"600519": 1200.0, "600036": 36.0, "510300": 4.0}
        rows = public_quotes(request.symbols) if not synthetic else [
            {"symbol": symbol, "name": SYMBOLS[symbol], "price": prices[symbol], "change_pct": -1.2,
             "observed_at": "2026-10-23T15:00:00+08:00", "stale": False}
            for symbol in request.symbols
        ]
        quantities = {p["symbol"]: p["quantity"] for p in run["context"]["payload"]["account"]["positions"]}
        cash = run["context"]["payload"]["account"]["cash"]
        for row in rows:
            row["quantity"] = quantities[row["symbol"]]
            row["market_value"] = round(row["quantity"] * row["price"], 2)
        covered_value = sum(row["market_value"] for row in rows)
        complete = set(request.symbols) == set(quantities)
        total = cash + covered_value if complete else None
        for row in rows:
            row["account_weight_pct"] = round(row["market_value"] / total * 100, 2) if total else None
        return {"kind": "market", "source": source, "synthetic": synthetic,
                "observed_at": min(row["observed_at"] for row in rows),
                "stale": any(row["stale"] for row in rows), "rows": rows,
                "account_total": total, "cash_pct": round(cash / total * 100, 2) if total else None,
                "note": "真实公开报价，账户数量仍为合成数据" if not synthetic else "构造报价，非标的真实历史行情；场景参考日2026-10-26"}
    if request.tool == "disclosure":
        cashflow = request.topic == "cashflow"
        return {"kind": "disclosure", "source": source, "synthetic": True, "stale": False,
                "observed_at": "2026-09-30T00:00:00+08:00", "topic": request.topic,
                "symbols": request.symbols,
                "revenue_growth_pct": 12.0,
                "operating_cashflow_growth_pct": -18.0 if cashflow and run["scenario"] == "conflicting_evidence" else (10.0 if run["scenario"] != "conflicting_evidence" else None),
                "note": "合成财报素材，不代表这些证券的实际财务数据，不可用于真实投资判断。"}
    return {"kind": "events", "source": source, "synthetic": True, "stale": False,
            "observed_at": "2026-10-23T00:00:00+08:00", "symbols": request.symbols,
            "events": ["演示事件：下一次公告披露前复核经营假设"], "note": "合成事件，不是真实事件日历"}
