"""Small, explicit reference universe. ETF/futures proxies are never called indices."""
from datetime import datetime, timedelta
import math
from zoneinfo import ZoneInfo

from app.data_sync import storage as s

DOMESTIC = (
    ("sh.000001", "上证指数", "mainland", "index"),
    ("sh.000300", "沪深300", "mainland", "index"),
    ("sh.518880", "黄金ETF（境内黄金代理）", "gold", "etf_proxy"),
    ("sh.512400", "有色金属ETF（行业代理）", "nonferrous", "etf_proxy"),
)
OVERSEAS = (
    ("^IXIC", "纳斯达克综合指数", "us_equity", "index"),
    ("DX-Y.NYB", "美元指数", "usd", "index"),
    ("GC=F", "COMEX黄金期货参考", "gold", "futures_reference"),
    ("HG=F", "COMEX铜期货参考", "nonferrous", "futures_reference"),
)
REQUIRED_GROUPS = {"mainland": "境内大盘", "us_equity": "纳斯达克", "usd": "美元指数", "gold": "黄金", "nonferrous": "有色资源"}


def observation_fresh(item, now, target):
    try:
        valid_price = math.isfinite(float(item.get("price"))) and float(item["price"]) > 0
    except (ValueError, TypeError):
        valid_price = False
    if not valid_price or not item.get("observed_at"):
        return False
    if item.get("market") == "CN":
        return str(item["observed_at"])[:10] >= target
    try:
        observed = datetime.fromisoformat(item["observed_at"])
        if observed.tzinfo is None:
            return False
        age = (now - observed).total_seconds()
        if age < -300:
            return False
        end = item.get("session_end")
        start = item.get("session_start")
        if start and end:
            start, end = datetime.fromisoformat(start), datetime.fromisoformat(end)
            if start <= now <= end:
                return age <= 1800
            if now > end and now - end < timedelta(hours=36):
                return observed >= end - timedelta(minutes=30)
        # Different market holidays are not inferred from the A-share calendar.
        local = now.astimezone(ZoneInfo(item.get("exchange_timezone") or "America/New_York"))
        return age <= (96 if local.weekday() in {0, 5, 6} else 48) * 3600
    except (ValueError, TypeError, KeyError):
        return False


def collect(request, progress):
    from app.collector.history.base_market_provider import BaseMarketProvider
    from app.overseas_tech_chain.service import fetch_yahoo_chart, _parse_closes, _provider_time
    target = request["target_date"]
    result = {"status": "complete", "items": [], "failures": [],
              "boundary": "参考数据按各自交易时区及源观测时间检查；海外为延迟参考，不以A股日期要求美股当日收盘。无明确交易时段时仅检查48/96小时时效，不声称已认证海外节假日日历。ETF与期货是显式代理，不是同名现货指数。"}
    for symbol, name, group, kind in (*DOMESTIC, *OVERSEAS):
        item = {"symbol": symbol, "name": name, "group": group, "kind": kind,
                "market": "CN" if symbol.startswith(("sh.", "sz.")) else "overseas", "retrieved_at": s.now().isoformat()}
        try:
            if item["market"] == "CN":
                import pandas as pd
                frame = BaseMarketProvider().get_daily_history(symbol, limit=5).copy()
                frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
                frame = frame.dropna(subset=["date"]).sort_values("date")
                frame = frame.loc[frame["date"].dt.strftime("%Y-%m-%d") <= target]
                if frame.empty:
                    raise ValueError("无已完成交易日日K")
                last = frame.iloc[-1]
                item.update(price=float(last["close"]), observed_at=last["date"].date().isoformat(), provider="local_daily_k")
            else:
                rows, meta = _parse_closes(fetch_yahoo_chart(symbol))
                period = meta.get("currentTradingPeriod", {}).get("regular", {})
                item.update(price=meta.get("regularMarketPrice") or rows[-1]["close"],
                            observed_at=_provider_time(meta.get("regularMarketTime")) or rows[-1]["data_time"],
                            session_start=_provider_time(period.get("start")), session_end=_provider_time(period.get("end")),
                            exchange_timezone=meta.get("exchangeTimezoneName"), provider="yahoo_finance_chart", quote_type="delayed_reference")
            item["fresh"] = observation_fresh(item, s.now(), target)
            if not item["fresh"]:
                raise ValueError("源观测时间缺失或超过本市场允许时效")
            item["status"] = "available"
        except Exception as exc:
            item.update(status="unavailable", fresh=False, reason=str(exc)[:300])
            result["failures"].append({"symbol": symbol, "reason": item["reason"]})
            result["status"] = "partial"
        result["items"].append(item)
        progress(result)
    return result
