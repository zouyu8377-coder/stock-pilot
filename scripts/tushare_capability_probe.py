from __future__ import annotations

import ast
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
OUT_JSON = ROOT / "docs" / "tushare_capability_report.json"

STATUSES = {
    "AVAILABLE_WITH_DATA",
    "AVAILABLE_NO_DATA",
    "PERMISSION_DENIED",
    "INVALID_ENDPOINT_OR_DEPRECATED",
    "PARAMETER_ERROR",
    "REQUEST_FAILED",
    "NOT_TESTED",
}

TARGET_STOCKS = ["601899.SH", "603993.SH", "002463.SZ", "002916.SZ", "000657.SZ"]
TARGET_ETFS = ["159382.SZ", "159934.SZ"]


def read_env_file(path: Path) -> dict[str, str]:
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def token_from_python_constant(path: Path) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.upper() in {"TOKEN", "TUSHARE_TOKEN"}:
                        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                            return node.value.value.strip()
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "token":
                        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                            return node.value.value.strip()
    except SyntaxError:
        return ""
    return ""


def load_token() -> tuple[str, str]:
    for key in ("TUSHARE_TOKEN", "TS_TOKEN", "TUSHARE_API_TOKEN"):
        value = os.getenv(key, "").strip()
        if value:
            return value, f"env:{key}"
    for env_path in (ROOT / ".env", BACKEND / ".env"):
        values = read_env_file(env_path)
        for key in ("TUSHARE_TOKEN", "TS_TOKEN", "TUSHARE_API_TOKEN"):
            if values.get(key):
                return values[key], f"env_file:{env_path.name}:{key}"
    for py_path in (
        BACKEND / "app" / "company_profile" / "providers" / "tushare_provider.py",
        BACKEND / "scripts" / "bootstrap_stock_metadata.py",
    ):
        value = token_from_python_constant(py_path)
        if value:
            return value, f"existing_code:{py_path.relative_to(ROOT).as_posix()}"
    return "", "not_found"


def classify_error(exc: Exception) -> tuple[str, str]:
    msg = str(exc)
    lower = msg.lower()
    if any(x in lower for x in ("权限", "积分", "permission", "privilege", "no access", "没有访问")):
        return "PERMISSION_DENIED", sanitize_error(msg)
    if any(x in lower for x in ("api_name", "不存在", "not found", "has no attribute", "invalid api", "接口不存在")):
        return "INVALID_ENDPOINT_OR_DEPRECATED", sanitize_error(msg)
    if any(x in lower for x in ("参数", "parameter", "must", "required", "invalid", "缺少")):
        return "PARAMETER_ERROR", sanitize_error(msg)
    if any(x in lower for x in ("timeout", "timed out", "rate", "limit", "频繁", "网络", "connection", "ssl")):
        return "REQUEST_FAILED", sanitize_error(msg)
    return "REQUEST_FAILED", sanitize_error(msg)


def sanitize_error(msg: str) -> str:
    msg = re.sub(r"[A-Za-z0-9]{24,}", "[REDACTED]", msg)
    msg = msg.replace("\n", " ")
    return msg[:240]


def df_summary(df: Any) -> dict[str, Any]:
    if df is None:
        return {"row_count": 0, "fields": [], "sample": []}
    if not isinstance(df, pd.DataFrame):
        return {"row_count": 0, "fields": [], "sample": []}
    sample = []
    if not df.empty:
        for row in df.head(2).to_dict(orient="records"):
            clean = {}
            for k, v in row.items():
                if pd.isna(v):
                    clean[k] = None
                elif isinstance(v, (pd.Timestamp, datetime)):
                    clean[k] = str(v)[:10]
                else:
                    clean[k] = v.item() if hasattr(v, "item") else v
            sample.append(clean)
    return {"row_count": int(len(df)), "fields": list(df.columns), "sample": sample}


def date_range(days: int) -> tuple[str, str]:
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    return start, end


def call_endpoint(pro: Any, endpoint: str, params: dict[str, Any], fields: str | None = None) -> dict[str, Any]:
    try:
        if fields:
            df = pro.query(endpoint, fields=fields, **params)
        else:
            df = pro.query(endpoint, **params)
        summary = df_summary(df)
        status = "AVAILABLE_WITH_DATA" if summary["row_count"] > 0 else "AVAILABLE_NO_DATA"
        return {"endpoint": endpoint, "status": status, "params_used": list(params.keys()), **summary}
    except Exception as exc:
        status, error = classify_error(exc)
        return {"endpoint": endpoint, "status": status, "params_used": list(params.keys()), "row_count": 0, "fields": [], "sample": [], "error_summary": error}


def best_recent_trade_date(pro: Any) -> tuple[str, dict[str, Any]]:
    start, end = date_range(30)
    result = call_endpoint(pro, "trade_cal", {"exchange": "SSE", "start_date": start, "end_date": end, "is_open": "1"}, "cal_date,is_open,pretrade_date")
    trade_date = (datetime.now() - timedelta(days=3)).strftime("%Y%m%d")
    if result["status"] == "AVAILABLE_WITH_DATA" and result["sample"]:
        try:
            df = pro.query("trade_cal", exchange="SSE", start_date=start, end_date=end, is_open="1", fields="cal_date,is_open,pretrade_date")
            if df is not None and not df.empty:
                trade_date = str(df.sort_values("cal_date").iloc[-1]["cal_date"])
        except Exception:
            pass
    return trade_date, result


def read_local_data_summary() -> dict[str, Any]:
    summary: dict[str, Any] = {}
    meta_path = BACKEND / "data" / "metadata" / "stock_meta.parquet"
    if meta_path.exists():
        try:
            df = pd.read_parquet(meta_path)
            summary["stock_meta"] = {"exists": True, "row_count": int(len(df)), "fields": list(df.columns), "sample_fields_only": True}
        except Exception as exc:
            summary["stock_meta"] = {"exists": True, "error": sanitize_error(str(exc))}
    base_dir = BACKEND / "data" / "base_market"
    files = list(base_dir.glob("*.parquet")) if base_dir.exists() else []
    summary["base_market"] = {"exists": base_dir.exists(), "file_count": len(files), "samples": {}}
    for ts_code in TARGET_STOCKS:
        prefix, code = ts_code.split(".")
        path = base_dir / f"{prefix.lower()}.{code}.parquet"
        if not path.exists():
            path = base_dir / f"{code.lower()}.{prefix.lower()}.parquet"
        baostock = f"{'sh' if ts_code.endswith('.SH') else 'sz'}.{ts_code[:6]}.parquet"
        path = base_dir / baostock
        if path.exists():
            try:
                df = pd.read_parquet(path)
                date_col = "date" if "date" in df.columns else ("日期" if "日期" in df.columns else None)
                coverage = {}
                if date_col and not df.empty:
                    coverage = {"start": str(df[date_col].iloc[0])[:10], "end": str(df[date_col].iloc[-1])[:10]}
                summary["base_market"]["samples"][ts_code] = {"exists": True, "row_count": int(len(df)), "fields": list(df.columns), **coverage}
            except Exception as exc:
                summary["base_market"]["samples"][ts_code] = {"exists": True, "error": sanitize_error(str(exc))}
        else:
            summary["base_market"]["samples"][ts_code] = {"exists": False}
    return summary


def main() -> int:
    token, token_source = load_token()
    probe_time = datetime.now().isoformat(timespec="seconds")
    payload: dict[str, Any] = {
        "probe_time": probe_time,
        "token_loaded": bool(token),
        "token_source_type": token_source.split(":", 1)[0],
        "business_code_modified": False,
        "python_version": sys.version.split()[0],
        "interfaces": [],
        "local_data": read_local_data_summary(),
    }
    if not token:
        OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return 2

    import tushare as ts

    payload["tushare_version"] = getattr(ts, "__version__", "unknown")
    ts.set_token(token)
    pro = ts.pro_api()

    recent_trade_date, trade_cal = best_recent_trade_date(pro)
    payload["recent_trade_date"] = recent_trade_date
    payload["interfaces"].append({"topic": "calendar", "recommended_priority": "P0", "recommended_usage": ["date_anchor"], **trade_cal})

    start_90, end_now = date_range(120)
    start_1y, _ = date_range(400)

    for sym in ["601899.SH", "002463.SZ", "002916.SZ", "000657.SZ"]:
        r = call_endpoint(pro, "stk_holdernumber", {"ts_code": sym, "start_date": start_1y, "end_date": end_now}, "ts_code,ann_date,end_date,holder_num")
        r.update({"topic": "shareholder_count", "tested_symbols": [sym], "recommended_priority": "P0", "recommended_usage": ["single_stock_evidence", "analysis_packet"]})
        payload["interfaces"].append(r)

    for endpoint in ("top_list", "top_inst"):
        tested = []
        combined = []
        statuses = []
        for params in (
            {"trade_date": recent_trade_date},
            {"ts_code": "002463.SZ", "start_date": start_1y, "end_date": end_now},
            {"ts_code": "002916.SZ", "start_date": start_1y, "end_date": end_now},
        ):
            r = call_endpoint(pro, endpoint, params)
            tested.append(params)
            combined.append(r)
            statuses.append(r["status"])
            if r["status"] == "AVAILABLE_WITH_DATA":
                break
            if r["status"] in {"PERMISSION_DENIED", "INVALID_ENDPOINT_OR_DEPRECATED"}:
                break
        best = next((x for x in combined if x["status"] == "AVAILABLE_WITH_DATA"), combined[0])
        best.update({"topic": "dragon_tiger_list" if endpoint == "top_list" else "dragon_tiger_seats", "tested_param_sets": tested, "recommended_priority": "P0" if endpoint == "top_list" else "P1", "recommended_usage": ["event_card", "analysis_packet"]})
        payload["interfaces"].append(best)

    for endpoint in ("fund_basic",):
        for market in ("E", ""):
            r = call_endpoint(pro, endpoint, {"market": market}, "ts_code,name,management,custodian,fund_type,found_date,due_date,list_date,issue_date,delist_date,issue_amount,m_fee,c_fee,duration_year,p_value,min_amount,exp_return,benchmark,status,invest_type,type,trustee,purc_startdate,redm_startdate,market")
            r.update({"topic": "fund_mapping", "tested_symbols": TARGET_ETFS, "recommended_priority": "P0", "recommended_usage": ["symbol_mapping"]})
            payload["interfaces"].append(r)
            break

    for endpoint in ("fund_share", "etf_share_size"):
        for sym in TARGET_ETFS:
            r = call_endpoint(pro, endpoint, {"ts_code": sym, "start_date": start_90, "end_date": end_now})
            r.update({"topic": "etf_share_size", "tested_symbols": [sym], "recommended_priority": "P0", "recommended_usage": ["etf_flow", "analysis_packet"]})
            payload["interfaces"].append(r)

    for endpoint in ("etf_basic", "etf_index", "etf_cash", "etf_substitute", "fund_nav", "fund_daily"):
        r = call_endpoint(pro, endpoint, {"ts_code": TARGET_ETFS[0], "start_date": start_90, "end_date": end_now})
        r.update({"topic": "etf_extended", "tested_symbols": [TARGET_ETFS[0]], "recommended_priority": "P2", "recommended_usage": ["etf_research"]})
        payload["interfaces"].append(r)

    for sym in ["002463.SZ", "002916.SZ", "601899.SH"]:
        r = call_endpoint(pro, "margin_detail", {"ts_code": sym, "start_date": start_90, "end_date": end_now})
        r.update({"topic": "margin_financing", "tested_symbols": [sym], "recommended_priority": "P1", "recommended_usage": ["risk_event_card", "analysis_packet"]})
        payload["interfaces"].append(r)

    for endpoint in ("moneyflow_ths", "moneyflow"):
        for sym in ["601899.SH", "002463.SZ", "002916.SZ"]:
            r = call_endpoint(pro, endpoint, {"ts_code": sym, "start_date": start_90, "end_date": end_now})
            r.update({"topic": "moneyflow", "tested_symbols": [sym], "recommended_priority": "P2", "recommended_usage": ["auxiliary_signal"]})
            payload["interfaces"].append(r)

    event_endpoints = [
        ("stk_holdertrade", "holder_trade"),
        ("repurchase", "repurchase"),
        ("share_float", "share_unlock"),
        ("block_trade", "block_trade"),
        ("pledge_detail", "pledge_detail"),
        ("pledge_stat", "pledge_stat"),
    ]
    for endpoint, topic in event_endpoints:
        r = call_endpoint(pro, endpoint, {"ts_code": "002463.SZ", "start_date": start_1y, "end_date": end_now})
        if r["status"] == "AVAILABLE_NO_DATA":
            r2 = call_endpoint(pro, endpoint, {"ts_code": "601899.SH", "start_date": start_1y, "end_date": end_now})
            if r2["status"] == "AVAILABLE_WITH_DATA":
                r = r2
        r.update({"topic": topic, "tested_symbols": ["002463.SZ", "601899.SH"], "recommended_priority": "P1" if topic in {"share_unlock", "holder_trade", "repurchase"} else "P2", "recommended_usage": ["risk_event_card", "portfolio_warning", "analysis_packet"]})
        payload["interfaces"].append(r)

    for endpoint, topic in (("anns_d", "announcements"), ("stk_surv", "institution_survey")):
        r = call_endpoint(pro, endpoint, {"ts_code": "002463.SZ", "start_date": start_90, "end_date": end_now})
        if r["status"] == "AVAILABLE_NO_DATA":
            r2 = call_endpoint(pro, endpoint, {"ts_code": "000657.SZ", "start_date": start_1y, "end_date": end_now})
            if r2["status"] == "AVAILABLE_WITH_DATA":
                r = r2
        r.update({"topic": topic, "tested_symbols": ["002463.SZ", "000657.SZ"], "recommended_priority": "P1", "recommended_usage": ["fact_layer", "analysis_packet"]})
        payload["interfaces"].append(r)

    for endpoint, params, topic in (
        ("index_daily", {"ts_code": "000300.SH", "start_date": start_90, "end_date": end_now}, "index_relative_strength"),
        ("ths_index", {"exchange": "A", "type": "N"}, "industry_index"),
        ("ths_daily", {"ts_code": "885800.TI", "start_date": start_90, "end_date": end_now}, "industry_index_daily"),
        ("daily", {"ts_code": "601899.SH", "start_date": start_90, "end_date": end_now}, "stock_daily_tushare"),
        ("fut_daily", {"ts_code": "CU.SHF", "start_date": start_90, "end_date": end_now}, "commodity_future"),
        ("fx_daily", {"ts_code": "USDCNH.FXCM", "start_date": start_90, "end_date": end_now}, "macro_fx"),
    ):
        r = call_endpoint(pro, endpoint, params)
        r.update({"topic": topic, "recommended_priority": "P2", "recommended_usage": ["relative_strength", "macro_context", "analysis_packet"]})
        payload["interfaces"].append(r)

    for endpoint in ("stk_mins", "stk_mins_weekly", "stk_mins_monthly"):
        r = call_endpoint(pro, endpoint, {"ts_code": "002463.SZ", "freq": "1min", "start_date": start_90, "end_date": end_now})
        r.update({"topic": "minute_bars", "tested_symbols": ["002463.SZ"], "recommended_priority": "P2", "recommended_usage": ["intraday", "minute_backtest"]})
        payload["interfaces"].append(r)

    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote sanitized capability report JSON: {OUT_JSON.relative_to(ROOT).as_posix()}")
    print(f"token_loaded={payload['token_loaded']}; interfaces={len(payload['interfaces'])}; recent_trade_date={recent_trade_date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
