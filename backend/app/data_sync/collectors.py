"""Explicit read-only adapters; never call review, OCR or disclosure LLMs."""
import math
import os
import re
from copy import deepcopy
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import pandas as pd
import requests

from app.data_sync import storage as s


def universe():
    from app.portfolio.service import portfolio_service
    from app.rotation.service import load_universe
    snapshot = portfolio_service.load_snapshot().model_dump(mode="json")
    positions = snapshot.get("positions", [])
    tracked = sorted({p["symbol"].split(".")[0] for p in positions})
    stocks = sorted({p["symbol"].split(".")[0] for p in positions if p.get("asset_type", "stock") == "stock"})
    cold = set(tracked)
    for item in load_universe()["items"]:
        cold.update(str(v) for v in [item.get("primary_symbol"), *(item.get("backup_symbols") or [])] if v)
        cold.update(str(c["symbol"]) for c in item.get("components", []) if c.get("symbol"))
    return {"account": snapshot, "tracked": tracked, "stocks": stocks, "cold": sorted(cold)}


def _safe(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def history(symbol, target):
    from app.collector.history.base_market_provider import BaseMarketProvider
    frame = BaseMarketProvider().get_daily_history(symbol).copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date").drop_duplicates("date")
    frame = frame.loc[frame["date"].dt.date <= date.fromisoformat(target)]
    if frame.empty:
        raise ValueError("No completed daily bars")
    for key in ["open", "high", "low", "close", "volume", "amount", "turn", "pctChg"]:
        if key in frame:
            frame[key] = pd.to_numeric(frame[key], errors="coerce")
    latest = frame.iloc[-1]
    result = {"as_of": latest["date"].date().isoformat(), "target_date": target,
              "is_stale": latest["date"].date().isoformat() < target, "rows": len(frame),
              **{k: _safe(latest.get(k)) for k in ["open", "high", "low", "close", "volume", "amount", "turn", "pctChg"]}}
    for days in [5, 10, 20, 60]:
        result[f"ma{days}"] = _safe(frame["close"].tail(days).mean()) if len(frame) >= days else None
        if days in [5, 20, 60]:
            base = _safe(frame["close"].iloc[-days - 1]) if len(frame) > days else None
            result[f"return_{days}d_pct"] = (result["close"] / base - 1) * 100 if base and result["close"] else None
        if days in [5, 10, 20] and "volume" in frame:
            result[f"volume_ma{days}"] = _safe(frame["volume"].tail(days).mean()) if len(frame) >= days else None
    previous = _safe(frame["volume"].iloc[-6:-1].mean()) if len(frame) >= 6 and "volume" in frame else None
    result["volume_vs_previous_5_complete_days"] = result["volume"] / previous if previous and result["volume"] is not None else None
    result["volume_unit"] = "shares (source daily-K units)"
    result["amount_unit"] = "CNY"
    return result


def cold(request, progress):
    from app.core import data_updater as updater
    from app.core.etf_data_updater import _download_full_history
    lock = updater.UPDATE_LOCK_FILE
    lock.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            owner = s.read(lock, {})
            if attempt == 0 and isinstance(owner, dict) and owner.get("pid") and not s.process_alive(owner["pid"]):
                if s.read(lock, {}) == owner:
                    lock.unlink(missing_ok=True)
                continue
            return {"status": "deferred", "reason": "Existing/legacy cold-data lock retained; live or unknown owner is never deleted"}
    try:
        with os.fdopen(fd, "w") as handle:
            import json
            handle.write(json.dumps({"started_at": s.now().isoformat(), "owner": request.get("request_id"), "pid": os.getpid()}))
        status = updater.load_update_status()
        updater.save_update_status({**status, "updated_at": s.now().replace(tzinfo=None).isoformat()})
        # Resolve holidays from the provider, not from weekday arithmetic alone.
        calendar_path = s.ROOT / "trading_calendar.json"
        calendar = s.read(calendar_path, {})
        today = s.now().date()
        if calendar.get("checked_on") != today.isoformat():
            updater._ensure_baostock_login()
            response = updater.bs.query_trade_dates(start_date=(today - timedelta(days=35)).isoformat(), end_date=today.isoformat())
            if response is None or response.error_code != "0":
                raise RuntimeError("Trading calendar unavailable; daily-K target not certified")
            sessions = []
            while response.next():
                row = dict(zip(response.fields, response.get_row_data()))
                if row.get("is_trading_day") == "1":
                    sessions.append(row["calendar_date"])
            if not sessions:
                raise ValueError("Empty trading calendar")
            calendar = {"checked_on": today.isoformat(), "sessions": sessions, "source": "baostock.query_trade_dates"}
            s.write(calendar_path, calendar)
        cutoff = updater.get_last_trading_date().isoformat()
        candidates = [d for d in calendar["sessions"] if d <= cutoff]
        if not candidates:
            raise ValueError("No completed trading session in calendar")
        target = max(candidates)
        result = {"status": "complete", "target_date": target, "calendar_verified": True, "items": [], "failures": []}
        from app.data_sync.references import DOMESTIC
        symbols = [*[item[0] for item in DOMESTIC], *[updater._compact_to_baostock_symbol(v) for v in request["universe"]["cold"]]]
        for code in dict.fromkeys(symbols):
            if not code:
                continue
            path = updater.BASE_MARKET_DIR / f"{code}.parquet"
            try:
                if not updater.is_symbol_updated(path, date.fromisoformat(target)):
                    if path.exists():
                        ok, reason = updater.update_single_symbol(path, date.fromisoformat(target))
                    else:
                        ok, reason = _download_full_history(code)
                    if not ok:
                        raise RuntimeError(reason)
                if not updater.is_symbol_updated(path, date.fromisoformat(target)):
                    raise ValueError("Provider returned no target-date bar (suspension/source delay possible)")
                result["items"].append({"symbol": code, "as_of": target})
            except Exception as exc:
                result["failures"].append({"symbol": code, "reason": str(exc)[:300]})
                result["status"] = "partial"
            progress(result)
        return result
    finally:
        updater._logout_baostock()
        lock.unlink(missing_ok=True)


def market(request, progress):
    from app.collector.realtime.easyquotation_provider import EasyQuotationProvider
    provider = EasyQuotationProvider()
    target = request["target_date"]
    result = {"status": "complete", "target_date": target, "items": [], "failures": []}
    for symbol in request["universe"]["tracked"]:
        item = {"symbol": symbol, "retrieved_at": s.now().isoformat()}
        try:
            quote = provider.get_quote(symbol)
            if not _safe(quote.get("price")) or _safe(quote["price"]) <= 0:
                raise ValueError("Missing/invalid live price")
            item["quote"] = quote
            item["quote"]["retrieved_at"] = item["retrieved_at"]
            item["quote"]["volume_unit"] = "lots (100 shares); Tencent source"
            item["quote"]["amount_unit"] = "CNY 10,000; Tencent source"
            raw_time = quote.get("quote_market_time")
            item["quote"]["market_time_local"] = str(raw_time).replace(" ", "T") + "+08:00" if raw_time and len(str(raw_time)) == 19 else raw_time
            calendar = s.read(s.ROOT / "trading_calendar.json", {})
            today = s.now().date().isoformat()
            today_session = today in calendar.get("sessions", [])
            expected = today if today_session and s.now().hour >= 9 else target
            item["quote"]["expected_market_date"] = expected
            item["quote"]["is_stale"] = not raw_time or str(raw_time)[:10] < expected
            try:
                market_time = datetime.fromisoformat(str(raw_time))
                if market_time.tzinfo is None:
                    market_time = market_time.replace(tzinfo=s.TZ)
                lag = max(0, (s.now() - market_time).total_seconds())
                item["quote"]["observation_lag_seconds"] = int(lag)
                minute = s.now().hour * 60 + s.now().minute
                in_session = today_session and (570 <= minute <= 690 or 780 <= minute <= 900)
                item["quote"]["is_stale"] |= in_session and lag > 900
            except (ValueError, TypeError):
                item["quote"]["is_stale"] = True
            if item["quote"]["is_stale"]:
                result["failures"].append({"symbol": symbol, "source": "quote", "reason": "Source quote date/time is missing or stale (including >15min lag during trading)"})
        except Exception as exc:
            item["quote"] = {"data_status": "unavailable", "reason": str(exc)[:250]}
            result["failures"].append({"symbol": symbol, "source": "quote", "reason": str(exc)[:250]})
        try:
            item["daily"] = history(symbol, target)
            if item["daily"]["is_stale"]:
                result["failures"].append({"symbol": symbol, "source": "daily", "reason": "Stored bar is older than target"})
        except Exception as exc:
            item["daily"] = {"data_status": "unavailable", "reason": str(exc)[:250]}
            result["failures"].append({"symbol": symbol, "source": "daily", "reason": str(exc)[:250]})
        result["items"].append(item)
        result["status"] = "partial" if result["failures"] else "complete"
        progress(result)
    return result


def load_document(row, symbol):
    from app.disclosure_verification.service import _download_pdf, _extract_pdf_pages, _select_relevant_text, _symbol_context
    key = str(row["announcement_id"])
    if not key.isdigit():
        raise ValueError("Invalid announcement ID")
    path = s.ROOT / "documents" / f"{symbol}-{key}.json"
    document = s.read(path)
    if not document or document.get("excerpt_version") != "financial-v3":
        pdf_path = path.with_suffix(".pdf")
        content = pdf_path.read_bytes() if pdf_path.exists() else _download_pdf(row["pdf_url"])
        if not pdf_path.exists():
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(content)
        pages = _extract_pdf_pages(content)
        text = financial_excerpt(pages) if document_type(row.get("title", "")) != "announcement" else _select_relevant_text(pages, _symbol_context(symbol)["keywords"], max_chars=8000)
        if not text:
            raise ValueError("PDF has no extractable text; scanned pages require OCR")
        document = {**row, "symbol": symbol, "selected_text": text, "retrieved_at": s.now().isoformat(),
                    "excerpt_version": "financial-v3", "local_pdf": pdf_path.name}
        s.write(path, document)
    document["document_type"] = document_type(row.get("title", ""))
    return document


def disclosures(request, progress):
    from app.disclosure_verification.service import _fetch_cninfo_announcements
    result = {"status": "complete", "documents": [], "failures": [], "checked_symbols": [],
              "boundary": "450 days, up to 4 index pages; newest annual/quarter/interim reports plus recent announcement, at most 4 documents per stock; excerpts only, no model verification"}
    for symbol in request["universe"]["stocks"]:
        try:
            rows = _fetch_cninfo_announcements(symbol, (s.now().date() - timedelta(days=450)).isoformat(), s.now().date().isoformat(), max_pages=4)
            if not any(document_type(row.get("title", "")) == "annual_report" for row in rows):
                try:
                    annual = _fetch_cninfo_announcements(symbol, (s.now().date() - timedelta(days=450)).isoformat(), s.now().date().isoformat(),
                                                         max_pages=1, category="category_ndbg_szsh")
                    rows = list({str(row["announcement_id"]): row for row in [*rows, *annual]}.values())
                except Exception as exc:
                    result["failures"].append({"symbol": symbol, "source": "annual_report_index", "reason": str(exc)[:300]})
                    result["status"] = "partial"
            rows.sort(key=lambda row: row.get("announced_at") or "", reverse=True)
            selected = select_documents(rows)
            for row in selected:
                try:
                    result["documents"].append(load_document(row, symbol))
                except Exception as exc:
                    result["failures"].append({"symbol": symbol, "announcement_id": row.get("announcement_id"), "reason": str(exc)[:300]})
                    result["status"] = "partial"
                progress(result)
            result["checked_symbols"].append({"symbol": symbol, "index_count": len(rows), "checked_at": s.now().isoformat(),
                "annual_report_found": any(d.get("symbol") == symbol and d.get("document_type") == "annual_report" for d in result["documents"]),
                "annual_index_candidate": any(document_type(r.get("title", "")) == "annual_report" for r in selected),
                "index_window_complete": None})
        except Exception as exc:
            result["failures"].append({"symbol": symbol, "reason": str(exc)[:300]})
            result["status"] = "partial"
        progress(result)
    return result


def document_type(title):
    if any(word in title for word in ["摘要", "英文", "取消", "作废", "说明会", "公告", "决议", "提示", "议案"]):
        return "announcement"
    if not re.search(r"(?:年度报告|季度报告)(?:全文|[（(](?:更新后|修订版|修订稿|更正后)[）)])?$", title.strip()):
        return "announcement"
    if "年度报告" in title and "半年度" not in title:
        return "annual_report"
    if "季度报告" in title or "半年度报告" in title:
        return "periodic_report"
    return "announcement"


def select_documents(rows):
    # Keep the annual report even when many newer routine announcements exist.
    selected = []
    for kind, limit in [("annual_report", 1), ("periodic_report", 2), ("announcement", 1)]:
        selected.extend([row for row in rows if document_type(row.get("title", "")) == kind][:limit])
    return selected


def financial_excerpt(pages):
    # Financial overview first; keyword-frequency ranking otherwise selects footnotes or IR logs.
    anchors = [r"主要(?:会计|财务)数据", r"主要会计数据和财务指标", r"合并现金流量表", r"合并利润表", r"经营情况讨论与分析|管理层讨论与分析"]
    selected, used = [], set()
    for pattern in anchors:
        for index, page in enumerate(pages):
            if index not in used and not ("目录" in page[:150] and page.count(".") > 8) and re.search(pattern, page):
                selected.append(page[:3000])
                used.add(index)
                break
    if not selected:
        selected = pages[:4]
    return "\n\n".join(selected)[:12000]


def rotation(request, progress):
    from app.rotation.service import build_rotation_bundle
    snapshot = deepcopy(request["universe"]["account"])
    cached = s.read(s.ROOT / "market.json", {}).get("data", {})
    prices = {item["symbol"]: item for item in cached.get("items", [])}
    total = float(snapshot.get("cash_available") or 0) + float(snapshot.get("repo_amount") or 0)
    missing = []
    for position in snapshot.get("positions", []):
        if not float(position.get("quantity") or 0):
            continue
        item = prices.get(position["symbol"].split(".")[0], {})
        price = _safe(item.get("quote", {}).get("price")) or _safe(item.get("daily", {}).get("close"))
        if price:
            position["market_value"] = float(position["quantity"]) * price
            total += position["market_value"]
        else:
            missing.append(position["symbol"])
    bundle = build_rotation_bundle(portfolio_context={"snapshot": snapshot, "metrics": {"total_assets": total if not missing else 0}})
    fields = ["sector_id", "name", "category", "proxy_type", "selected_symbol", "proxy_components", "latest_date", "latest_close",
              "returns", "moving_averages", "benchmark", "relative_strength", "flow", "data_quality", "missing_fields", "proxy_meta"]
    items = [{key: item.get(key) for key in fields} for item in [*bundle.get("benchmarks", []), *bundle.get("sectors", [])]]
    stale = [item.get("sector_id") for item in items if item.get("latest_date") != request["target_date"]]
    return {"status": "partial" if stale or missing else "complete", "as_of": bundle.get("as_of"), "items": items,
            "missing_account_prices": missing, "stale_directions": stale,
            "boundary": "Deterministic local proxy facts; account context reuses collected quotes, never refetches or recommends trades"}


def breadth(request, progress):
    from app.market_breadth.service import rebuild_market_breadth
    from app.market_breadth.service import MARKET_DIR
    from app.data_sync.service import signature
    revision = signature([(p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in sorted(MARKET_DIR.glob("*.parquet"))])
    previous = s.read(s.ROOT / "breadth.json", {}).get("data", {})
    if previous.get("source_revision") == revision and previous.get("as_of") == request["target_date"]:
        return previous
    result = rebuild_market_breadth(request["target_date"])
    return {**result, "source_revision": revision, "status": "complete" if result.get("coverage_pct", 0) >= 95 else "partial",
            "next_action": "Full-market backfill required if coverage is incomplete; unchanged files are not rescanned"}


def backfill(request, progress):
    """Bounded full-universe increments; persist verified dates to resume next run."""
    from app.core.data_updater import METADATA_FILE, _ts_code_to_baostock_symbol
    from app.core.etf_data_updater import ETF_META_FILE
    symbols = set()
    for path in (METADATA_FILE, ETF_META_FILE):
        if path.exists():
            for value in pd.read_parquet(path, columns=["ts_code"])["ts_code"].dropna():
                symbol = _ts_code_to_baostock_symbol(str(value))
                if symbol:
                    symbols.add(symbol)
    if not symbols:
        return {"status": "failed", "reason": "股票与ETF元数据不存在，不能声明全市场补齐"}
    target = request["target_date"]
    path = s.ROOT / "backfill_cursor.json"
    state = s.read(path, {})
    if state.get("target_date") != target:
        state = {"target_date": target, "completed": [], "attempted_at": {}}
    done = set(state["completed"]) & symbols
    attempts = state["attempted_at"]
    # Untouched files first; failed symbols wait an hour before a retry.
    def eligible(symbol):
        try:
            return (s.now() - datetime.fromisoformat(attempts[symbol])).total_seconds() >= 3600
        except (KeyError, ValueError, TypeError):
            return True
    pending = sorted(symbols - done, key=lambda code: (code in attempts, code))
    batch = [code for code in pending if eligible(code)][:200]
    if not batch:
        return {"status": "complete" if len(done) == len(symbols) else "partial", "completed_count": len(done),
                "total_symbols": len(symbols), "remaining_count": len(symbols - done), "target_date": target}
    seen = set()
    def checkpoint(value):
        for row in value.get("items", []):
            if row["symbol"] in symbols:
                done.add(row["symbol"])
        for row in [*value.get("items", []), *value.get("failures", [])]:
            code = row["symbol"]
            if code not in seen:
                attempts[code] = s.now().isoformat()
                seen.add(code)
        state.update(completed=sorted(done), attempted_at=attempts)
        s.write(path, state)
        progress({**value, "completed_count": len(done), "total_symbols": len(symbols), "remaining_count": len(symbols - done)})
    result = cold({**request, "universe": {**request["universe"], "cold": batch}}, checkpoint)
    return {**result, "status": "complete" if len(done) == len(symbols) else "partial",
            "completed_count": len(done), "total_symbols": len(symbols), "remaining_count": len(symbols - done),
            "boundary": "全市场元数据范围，每轮最多200个标的，逐文件核验目标日期；余项在下一轮启动或定时采集续传，不把本批完成当成全量完成。"}


PUBLIC_FEEDS = {"fed_monetary": "https://www.federalreserve.gov/feeds/press_monetary.xml",
                "bls_releases": "https://www.bls.gov/feed/bls_latest.rss"}


def public(request, progress):
    from app.external_drivers.yahoo_comex_provider import get_comex_fact
    result = {"status": "complete", "commodities": [], "releases": [], "failures": []}
    for factor in ["comex_gold_yahoo", "comex_copper_yahoo"]:
        try:
            value = get_comex_fact(factor, include_series=True)
            if value.get("data_status") != "available":
                raise ValueError(value.get("reason"))
            result["commodities"].append(value)
        except Exception as exc:
            result["failures"].append({"source": factor, "reason": str(exc)[:300]})
        progress(result)
    for source, url in PUBLIC_FEEDS.items():
        try:
            response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 Stock-Pilot data-sync"})
            response.raise_for_status()
            root = ElementTree.fromstring(response.content)
            for item in root.findall("./channel/item")[:12]:
                raw = item.findtext("pubDate")
                result["releases"].append({"source": source, "source_url": url, "title": item.findtext("title"),
                    "url": item.findtext("link"), "published_at": parsedate_to_datetime(raw).isoformat() if raw else None})
        except Exception as exc:
            result["failures"].append({"source": source, "reason": str(exc)[:300]})
        progress(result)
    registry = s.read(s.BACKEND / "data" / "market_events" / "event_registry.json", {})
    result["local_event_registry_updated_at"] = registry.get("updated_at") or registry.get("registry_updated_at")
    result["boundary"] = "Official release feeds are headlines/dates, NOT a refreshed future event calendar or full news coverage. COMEX is delayed reference, not settlement."
    result["remaining_gaps"] = ["Future macro calendar and geopolitical/industry news need separately verified sources; no claim of automatic complete coverage"]
    result["status"] = "partial" if result["failures"] else "complete"
    return result


from app.data_sync.references import collect as references

STAGES = {"cold": cold, "market": market, "references": references, "disclosures": disclosures,
          "rotation": rotation, "breadth": breadth, "public": public, "backfill": backfill}
