from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.attractiveness.valuation import get_valuation_reference
from app.attractiveness.relative_strength import build_relative_benchmarks
from app.portfolio.schemas import PortfolioState


ROOT = Path(__file__).resolve().parents[2] / "data" / "attractiveness"
HISTORY_PATH = ROOT / "history.json"
CONSENSUS_PATH = ROOT / "consensus_registry.json"
DIMENSION_WEIGHTS = {
    "evidence_change": 30,
    "trend_strength": 25,
    "valuation_consensus": 20,
    "catalyst": 15,
    "execution": 10,
}


def _compact_symbol(symbol: str) -> str:
    return str(symbol or "").split(".", 1)[0].strip().zfill(6)


def _clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _theme_position_map(theme_radar: dict[str, Any]) -> dict[str, dict[str, Any]]:
    strength_rank = {"high": 3, "medium": 2, "weak": 1}
    result: dict[str, dict[str, Any]] = {}
    for theme in theme_radar.get("themes", []):
        for item in theme.get("related_positions", []):
            symbol = _compact_symbol(item.get("symbol", ""))
            current = result.get(symbol)
            if current and strength_rank.get(current.get("relation_strength"), 0) >= strength_rank.get(item.get("relation_strength"), 0):
                continue
            result[symbol] = {
                **item,
                "theme_id": theme.get("theme_id"),
                "theme_name": theme.get("theme_name"),
                "confirming_events": theme.get("confirming_events", []),
                "invalidating_events": theme.get("invalidating_events", []),
            }
    return result


def _event_map(event_radar: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for event in event_radar.get("events", []):
        if int(event.get("days_until") or 0) < 0:
            continue
        for position in event.get("related_positions", []):
            symbol = _compact_symbol(position.get("symbol", ""))
            result.setdefault(symbol, []).append(event)
    for events in result.values():
        events.sort(key=lambda item: int(item.get("days_until") or 999))
    return result


def _question_statuses(verification: dict[str, Any]) -> dict[str, str]:
    rank = {"not_found": 0, "partially_supported": 1, "supported": 2, "contradicted": 3}
    result: dict[str, str] = {}
    for item in verification.get("items") or []:
        question = str(item.get("question") or "").strip()
        status = str(item.get("status") or "")
        if not question or status not in rank:
            continue
        current = result.get(question)
        if current is None or rank[status] > rank[current]:
            result[question] = status
    return result


def _evidence_dimension(
    theme_position: dict[str, Any],
    previous_counts: dict[str, Any] | None = None,
    previous_questions: dict[str, str] | None = None,
) -> dict[str, Any]:
    verification = theme_position.get("announcement_verification") or {}
    if verification.get("status") != "verified":
        return {
            "score": None,
            "coverage": 0,
            "reasons": ["公告正文验证尚未形成可用结论"],
            "as_of": verification.get("generated_at"),
        }
    counts = verification.get("counts") or {}
    supported = int(counts.get("supported") or 0)
    partial = int(counts.get("partially_supported") or 0)
    contradicted = int(counts.get("contradicted") or 0)
    not_found = int(counts.get("not_found") or 0)
    total = supported + partial + contradicted + not_found
    if total == 0:
        return {"score": None, "coverage": 0, "reasons": ["公告验证没有可计分项目"], "as_of": verification.get("generated_at")}
    score = _clamp(50 + supported * 14 + partial * 7 - contradicted * 24 - not_found * 4)
    delta = None
    if previous_counts:
        previous_net = (
            int(previous_counts.get("supported") or 0) * 2
            + int(previous_counts.get("partially_supported") or 0)
            - int(previous_counts.get("contradicted") or 0) * 3
        )
        current_net = supported * 2 + partial - contradicted * 3
        delta = current_net - previous_net
        score = _clamp(score + max(-15, min(15, delta * 5)))
    reasons = [
        f"公告验证支持 {supported} 项、部分支持 {partial} 项",
        f"反证 {contradicted} 项、未找到 {not_found} 项",
    ]
    if delta is not None:
        reasons.insert(0, f"较上次证据净变化 {delta:+d}")
    question_statuses = _question_statuses(verification)
    status_value = {"not_found": 0, "partially_supported": 1, "supported": 2, "contradicted": -2}
    question_changes = []
    if previous_questions:
        for question, status in question_statuses.items():
            previous_status = previous_questions.get(question)
            if previous_status and previous_status != status:
                direction = status_value[status] - status_value.get(previous_status, 0)
                question_changes.append({
                    "question": question,
                    "from": previous_status,
                    "to": status,
                    "direction": "improved" if direction > 0 else "weakened",
                })
                score = _clamp(score + (6 if direction > 0 else -10))
    for change in question_changes[:2]:
        reasons.insert(
            0,
            f"{change['question'][:24]}：{change['from']} → {change['to']}",
        )
    return {
        "score": score,
        "coverage": min(100, 45 + total * 15),
        "reasons": reasons,
        "as_of": verification.get("generated_at"),
        "evidence_counts": counts,
        "evidence_delta": delta,
        "question_statuses": question_statuses,
        "question_changes": question_changes,
    }


def _etf_evidence_dimension(theme_position: dict[str, Any], valuation: dict[str, Any]) -> dict[str, Any]:
    has_theme = bool(theme_position)
    relation_score = (
        {"high": 68, "medium": 58, "weak": 45}.get(
            str(theme_position.get("relation_strength") or ""),
            50,
        )
        if has_theme
        else 45
    )
    share_1d = valuation.get("share_change_1d_pct")
    share_5d = valuation.get("share_change_5d_pct")
    share_20d = valuation.get("share_change_20d_pct")
    score = float(relation_score)
    reasons = (
        [f"ETF主题关联强度：{theme_position.get('relation_strength') or '已映射'}"]
        if has_theme
        else ["ETF主题尚未映射，先使用基金份额事实"]
    )
    coverage = 45 if has_theme else 20
    if share_1d is not None:
        score += max(-5, min(5, float(share_1d) * 0.5))
        coverage += 15
        reasons.append(f"ETF份额1日变化 {float(share_1d):+.2f}%")
    if share_5d is not None:
        score += max(-8, min(8, float(share_5d) * 0.8))
        coverage += 20
        reasons.append(f"ETF份额5日变化 {float(share_5d):+.2f}%")
    if share_20d is not None:
        score += max(-12, min(12, float(share_20d) * 0.5))
        coverage += 25
        reasons.append(f"ETF份额20日变化 {float(share_20d):+.2f}%")
    if theme_position.get("role_in_theme"):
        coverage += 10
    return {
        "score": _clamp(score),
        "coverage": min(100, coverage),
        "reasons": reasons,
        "as_of": valuation.get("share_data_as_of") or valuation.get("as_of"),
        "evidence_type": "etf_theme_and_share_flow",
    }


def _trend_dimension(trend: dict[str, Any], benchmarks: dict[str, Any]) -> dict[str, Any]:
    if trend.get("data_status") != "available":
        return {"score": None, "coverage": 0, "reasons": ["本地日 K 趋势数据不可用"]}
    trend_as_of = str(trend.get("daily_k_as_of") or "")
    market = benchmarks.get("market") or {}
    market_freshness = market.get("freshness") or {}
    if market_freshness.get("status") == "stale":
        return {
            "score": None,
            "coverage": 0,
            "reasons": [f"行情基准已过期 {market_freshness.get('stale_days')} 天，暂停相对强度计分"],
            "benchmarks": benchmarks,
            "data_status": "stale",
        }
    if trend_as_of and market.get("as_of") and trend_as_of != market.get("as_of"):
        return {
            "score": None,
            "coverage": 0,
            "reasons": [f"标的日期 {trend_as_of} 与沪深300日期 {market.get('as_of')} 未对齐"],
            "benchmarks": benchmarks,
            "data_status": "misaligned",
        }
    score = 50.0
    reasons: list[str] = []
    price_vs_ma20 = trend.get("price_vs_ma20_pct")
    return_20d = trend.get("return_20d_pct")
    return_60d = trend.get("return_60d_pct")
    rsi = trend.get("rsi14")
    if price_vs_ma20 is not None:
        score += max(-20, min(20, float(price_vs_ma20) * 2))
        reasons.append(f"现价相对 MA20 {float(price_vs_ma20):+.2f}%")
    if return_20d is not None:
        score += max(-18, min(18, float(return_20d) * 0.7))
        reasons.append(f"20 日收益 {float(return_20d):+.2f}%")
        for key, weight in (("market", 0.45), ("industry", 0.35), ("theme", 0.20)):
            reference = benchmarks.get(key) or {}
            benchmark_20d = reference.get("return_20d_pct") if reference.get("status") == "available" else None
            if benchmark_20d is None or reference.get("as_of") != trend_as_of:
                continue
            excess = float(return_20d) - float(benchmark_20d)
            score += max(-10, min(10, excess * weight))
            reasons.append(f"相对{reference.get('label')}超额 {excess:+.2f}%")
    if return_60d is not None:
        score += max(-10, min(10, float(return_60d) * 0.2))
    state = str(trend.get("trend_state") or "")
    if "强" in state:
        score += 8
    if "弱" in state or "下方" in state:
        score -= 8
    if rsi is not None and float(rsi) >= 75:
        score -= 8
        reasons.append("RSI 偏高，追价吸引力折扣")
    return {
        "score": _clamp(score),
        "coverage": min(
            100,
            55 + sum(15 for item in benchmarks.values() if item.get("status") == "available" and item.get("as_of") == trend_as_of),
        ),
        "reasons": reasons or [state or "趋势状态可用"],
        "benchmarks": benchmarks,
        "data_status": "available",
    }


def _valuation_dimension(
    symbol: str,
    price: float | None,
    registry: dict[str, Any],
    market_valuation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = (registry.get("symbols") or {}).get(symbol)
    market_valuation = market_valuation or get_valuation_reference(symbol)
    if not isinstance(item, dict):
        if market_valuation.get("status") == "available":
            percentiles = [
                value for value in (
                    market_valuation.get("pe_percentile_3y"),
                    market_valuation.get("pb_percentile_3y"),
                    market_valuation.get("ps_percentile_3y"),
                    market_valuation.get("price_percentile_3y"),
                )
                if value is not None
            ]
            if percentiles:
                average = sum(percentiles) / len(percentiles)
                basis = (
                    "自身3年价格分位"
                    if market_valuation.get("price_percentile_3y") is not None
                    else "自身3年估值平均分位"
                )
                return {
                    "score": _clamp(100 - average),
                    "coverage": (
                        55
                        if market_valuation.get("asset_type") == "etf"
                        else min(75, 45 + len(percentiles) * 15)
                    ),
                    "reasons": [f"{basis} {average:.1f}%（越低代表价格位置越低）"],
                    "reference": market_valuation,
                }
        return {
            "score": None,
            "coverage": 0,
            "reasons": ["暂无可靠的历史估值、盈利预测或机构目标价共识"],
            "reference": market_valuation,
        }
    target = item.get("target_price_median")
    institutions = int(item.get("institution_count") or 0)
    published_at = item.get("published_at")
    if target is None or not price or institutions < 2:
        return {
            "score": None,
            "coverage": 0,
            "reasons": ["机构覆盖不足或目标价缺少可验证的中位数"],
            "reference": item,
        }
    upside = (float(target) / float(price) - 1) * 100
    dispersion = item.get("target_price_dispersion_pct")
    score = 50 + max(-35, min(35, upside * 1.2))
    if dispersion is not None:
        score -= max(0, float(dispersion) - 20) * 0.5
    coverage = min(100, 45 + institutions * 7)
    return {
        "score": _clamp(score),
        "coverage": coverage,
        "reasons": [
            f"目标价中位数隐含空间 {upside:+.1f}%",
            f"覆盖机构 {institutions} 家",
        ],
        "reference": {
            **item,
            "published_at": published_at,
            "implied_upside_pct": round(upside, 2),
            "market_valuation": market_valuation,
        },
    }


def _catalyst_dimension(theme_position: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    verification = theme_position.get("announcement_verification") or {}
    score = 45.0
    has_theme_mapping = bool(theme_position.get("theme_id") or theme_position.get("theme_name"))
    coverage = 50 if has_theme_mapping else 25
    reasons: list[str] = []
    data_status = "available_no_near_term_catalyst" if has_theme_mapping else "limited_theme_mapping"
    if verification.get("trigger") == "new_announcement":
        score += 25
        coverage += 30
        data_status = "new_announcement_verified"
        reasons.append("发现新公告并已完成正文验证")
    if events:
        nearest = events[0]
        days = int(nearest.get("days_until") or 0)
        impact = float(nearest.get("impact_score") or 0)
        score += 15 if days <= 14 else 8
        coverage += 25
        data_status = "upcoming_event"
        reasons.append(f"{nearest.get('title') or '相关事件'}将在 {days} 天后发生")
        if impact >= 85:
            score -= 8
            reasons.append("高影响事件同时提高不确定性")
    confirming = theme_position.get("confirming_events") or []
    if confirming:
        coverage += 15
        reasons.append(f"已登记 {len(confirming)} 项主题确认信号")
    elif has_theme_mapping and not events:
        coverage += 10
        reasons.append("已检查主题事件清单，近期暂无明确新增催化")
    return {
        "score": _clamp(score),
        "coverage": min(100, coverage),
        "reasons": reasons or ["主题映射有限，暂无法充分判断催化状态"],
        "nearest_event": events[0] if events else None,
        "data_status": data_status,
    }


def _price_limit_pct(symbol: str, name: str) -> float:
    if "ST" in str(name or "").upper():
        return 5.0
    if symbol.startswith(("4", "8", "92")):
        return 30.0
    if symbol.startswith(("300", "301", "688")):
        return 20.0
    return 10.0


def _execution_dimension(symbol: str, name: str, trend: dict[str, Any], active: bool) -> dict[str, Any]:
    latest_pct = trend.get("latest_pct_chg")
    limit_pct = _price_limit_pct(symbol, name)
    limit_up = latest_pct is not None and float(latest_pct) >= limit_pct - 0.2
    limit_down = latest_pct is not None and float(latest_pct) <= -limit_pct + 0.2
    score = 100
    reasons = ["未检测到涨跌停阻断"]
    if limit_up:
        score = 20
        reasons = ["接近或处于涨停，新增买入可能无法成交"]
    elif limit_down:
        score = 35
        reasons = ["接近或处于跌停，风险处置可能无法成交"]
    if active:
        reasons.append("按当前约定，全部持仓额度视为可用")
    return {
        "score": score,
        "coverage": 100,
        "reasons": reasons,
        "constraints": {
            "limit_pct": limit_pct,
            "limit_up": limit_up,
            "limit_down": limit_down,
            "t_plus_one_modeled": False,
            "all_existing_holdings_available": True,
        },
    }


def _score_dimensions(dimensions: list[dict[str, Any]]) -> tuple[int | None, int]:
    available = [item for item in dimensions if item.get("score") is not None]
    available_weight = sum(int(item["weight"]) for item in available)
    if not available_weight:
        return None, 0
    score = sum(float(item["score"]) * int(item["weight"]) for item in available) / available_weight
    coverage = sum(int(item["weight"]) * float(item.get("coverage") or 0) / 100 for item in dimensions)
    return _clamp(score), _clamp(coverage)


def _account_constraints(
    state: PortfolioState,
    position: Any,
    attractiveness_score: int | None,
    execution: dict[str, Any],
) -> dict[str, Any]:
    total_assets = max(float(state.metrics.total_assets or 0), 0.01)
    current_weight = float(position.market_value or 0) / total_assets * 100
    position_limit = float(position.target_max_weight or state.snapshot.risk_limits.max_position_weight)
    position_headroom = max(0.0, position_limit - current_weight)
    direction = position.directions[0] if position.directions else "UNCLASSIFIED"
    theme_weight = next(
        (float(item.weight_pct) for item in state.metrics.primary_theme_exposures if item.theme == direction),
        0.0,
    )
    theme_headroom = max(0.0, float(state.snapshot.risk_limits.max_theme_weight) - theme_weight)
    cash_headroom = max(
        0.0,
        float(state.metrics.cash_ratio_pct or 0) - float(state.snapshot.risk_limits.min_cash_ratio),
    )
    executable = not execution.get("limit_up") and not execution.get("limit_down")
    readiness = _clamp(
        min(100, position_headroom / max(position_limit, 1) * 100) * 0.30
        + min(100, theme_headroom / max(float(state.snapshot.risk_limits.max_theme_weight), 1) * 100) * 0.30
        + min(100, cash_headroom / 15 * 100) * 0.25
        + (100 if executable else 20) * 0.15
    )
    eligible = (
        attractiveness_score is not None
        and attractiveness_score >= 70
        and readiness >= 50
        and position_headroom >= 2
        and theme_headroom >= 2
        and cash_headroom > 0
        and executable
    )
    blockers = []
    if readiness < 50:
        blockers.append("账户准备度低于50")
    if position_headroom < 2:
        blockers.append("单票仓位余量不足")
    if theme_headroom < 2:
        blockers.append("主题仓位余量不足")
    if cash_headroom <= 0:
        blockers.append("现金已触及底线")
    if not executable:
        blockers.append("涨跌停阻断")
    return {
        "readiness_score": readiness,
        "eligible_after_account_constraints": eligible,
        "position_weight_pct": round(current_weight, 2),
        "position_limit_pct": round(position_limit, 2),
        "position_headroom_pct": round(position_headroom, 2),
        "theme": direction,
        "theme_weight_pct": round(theme_weight, 2),
        "theme_limit_pct": round(float(state.snapshot.risk_limits.max_theme_weight), 2),
        "theme_headroom_pct": round(theme_headroom, 2),
        "cash_headroom_pct": round(cash_headroom, 2),
        "blockers": blockers,
    }


def _attractiveness_validation(history: dict[str, Any]) -> dict[str, Any]:
    completed: list[dict[str, Any]] = []
    pending = 0
    for symbol, entries in (history.get("symbols") or {}).items():
        try:
            frame = pd.read_parquet(
                Path(__file__).resolve().parents[2]
                / "data"
                / "base_market"
                / (f"sh.{symbol}.parquet" if symbol.startswith(("5", "6")) else f"sz.{symbol}.parquet")
            ).reset_index(drop=True)
            dates = pd.to_datetime(frame["date"], errors="coerce")
            closes = pd.to_numeric(frame["close"], errors="coerce")
        except Exception:
            continue
        for entry in entries:
            generated = pd.to_datetime(entry.get("generated_at"), errors="coerce", utc=True)
            if pd.isna(generated):
                continue
            matching = frame.index[dates.dt.date >= generated.date()]
            if len(matching) < 61:
                pending += 1
                continue
            index = int(matching[0])
            if index + 60 >= len(closes) or closes.iloc[index] <= 0:
                pending += 1
                continue
            completed.append({
                "symbol": symbol,
                "generated_at": entry.get("generated_at"),
                "score": entry.get("score"),
                "portfolio_priority_score": entry.get("portfolio_priority_score"),
                "eligible": entry.get("eligible"),
                "theme_id": entry.get("theme_id"),
                "return_20d_pct": round((closes.iloc[index + 20] / closes.iloc[index] - 1) * 100, 2),
                "return_60d_pct": round((closes.iloc[index + 60] / closes.iloc[index] - 1) * 100, 2),
            })
    if len(completed) < 20:
        return {
            "status": "insufficient_history",
            "completed_samples": len(completed),
            "pending_samples": pending,
            "minimum_samples": 20,
            "note": "吸引力快照需积累并等待未来20/60个交易日，当前不报告胜率。",
        }
    high = [item for item in completed if float(item.get("score") or 0) >= 70]
    selected: list[dict[str, Any]] = []
    by_snapshot: dict[str, list[dict[str, Any]]] = {}
    for item in completed:
        if item.get("eligible"):
            by_snapshot.setdefault(str(item.get("generated_at")), []).append(item)
    for items in by_snapshot.values():
        items.sort(key=lambda value: float(value.get("portfolio_priority_score") or 0), reverse=True)
        used_themes: set[str] = set()
        for item in items:
            theme_id = str(item.get("theme_id") or "unmapped")
            if theme_id in used_themes:
                continue
            used_themes.add(theme_id)
            selected.append(item)
            if len(used_themes) >= 3:
                break
    return {
        "status": "available",
        "completed_samples": len(completed),
        "high_score_samples": len(high),
        "high_score_positive_20d_pct": round(sum(item["return_20d_pct"] > 0 for item in high) / len(high) * 100, 2) if high else None,
        "high_score_average_20d_pct": round(sum(item["return_20d_pct"] for item in high) / len(high), 2) if high else None,
        "high_score_average_60d_pct": round(sum(item["return_60d_pct"] for item in high) / len(high), 2) if high else None,
        "portfolio_selection": {
            "samples": len(selected),
            "average_20d_pct": round(sum(item["return_20d_pct"] for item in selected) / len(selected), 2) if selected else None,
            "average_60d_pct": round(sum(item["return_60d_pct"] for item in selected) / len(selected), 2) if selected else None,
            "rule": "每个快照按组合优先分排序，同一主题只保留一只，最多选择三个候选。",
        },
        "limitations": [
            "事后分层统计，不是参数优化或未来收益保证。",
            "按当前约定不建模持仓级T+1；涨跌停仍作为执行阻断。",
        ],
    }


def _history_changes(rows: list[dict[str, Any]], generated_at: str) -> None:
    history = _load_json(HISTORY_PATH, {"version": "attractiveness_history.v1", "symbols": {}})
    symbols = history.setdefault("symbols", {})
    for row in rows:
        symbol = row["symbol"]
        entries = symbols.setdefault(symbol, [])
        previous = entries[-1] if entries else None
        score = row.get("score")
        row["previous_score"] = previous.get("score") if previous else None
        row["score_change"] = (
            int(score) - int(previous["score"])
            if score is not None and previous and previous.get("score") is not None
            else None
        )
        if previous and previous.get("score") == score and previous.get("coverage") == row.get("coverage"):
            continue
        entries.append({
            "generated_at": generated_at,
            "score": score,
            "coverage": row.get("coverage"),
            "reference_price": row.get("reference_price"),
            "dimension_scores": {item["key"]: item.get("score") for item in row.get("dimensions", [])},
            "evidence_counts": row.get("evidence_counts"),
            "question_statuses": row.get("question_statuses"),
            "portfolio_priority_score": row.get("portfolio_priority_score"),
            "theme_id": row.get("theme_id"),
            "account_readiness_score": row.get("account_readiness_score"),
            "eligible": row.get("account_constraints", {}).get("eligible_after_account_constraints"),
        })
        symbols[symbol] = entries[-60:]
    _write_json(HISTORY_PATH, history)


def build_attractiveness_radar(
    state: PortfolioState,
    *,
    trends: dict[str, dict[str, Any]],
    theme_radar: dict[str, Any],
    event_radar: dict[str, Any],
    persist_history: bool = False,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    theme_positions = _theme_position_map(theme_radar)
    events = _event_map(event_radar)
    consensus = _load_json(CONSENSUS_PATH, {"version": "consensus_reference.v1", "symbols": {}})
    history = _load_json(HISTORY_PATH, {"version": "attractiveness_history.v1", "symbols": {}})
    previous_by_symbol = {
        symbol: entries[-1]
        for symbol, entries in (history.get("symbols") or {}).items()
        if entries
    }
    rows: list[dict[str, Any]] = []
    for position in state.snapshot.positions:
        symbol = _compact_symbol(position.symbol)
        trend = trends.get(symbol, {})
        theme_position = theme_positions.get(symbol, {})
        previous = previous_by_symbol.get(symbol, {})
        valuation_reference = get_valuation_reference(symbol)
        evidence = (
            _etf_evidence_dimension(theme_position, valuation_reference)
            if symbol.startswith(("15", "16", "51", "56", "58"))
            else _evidence_dimension(
                theme_position,
                previous.get("evidence_counts"),
                previous.get("question_statuses"),
            )
        )
        execution = _execution_dimension(symbol, position.name, trend, float(position.quantity or 0) > 0)
        benchmarks = build_relative_benchmarks(symbol, theme_position, theme_radar)
        dimensions = [
            {"key": "evidence_change", "label": "预期差与证据变化", "weight": 30, **evidence},
            {"key": "trend_strength", "label": "趋势与相对强度", "weight": 25, **_trend_dimension(trend, benchmarks)},
            {
                "key": "valuation_consensus",
                "label": "估值与价格位置",
                "weight": 20,
                **_valuation_dimension(
                    symbol,
                    position.market_price or position.system_quote_price,
                    consensus,
                    valuation_reference,
                ),
            },
            {"key": "catalyst", "label": "催化剂与时效", "weight": 15, **_catalyst_dimension(theme_position, events.get(symbol, []))},
            {
                "key": "execution",
                "label": "交易可执行性",
                "weight": 10,
                **execution,
            },
        ]
        score, coverage = _score_dimensions(dimensions)
        confidence = "高" if coverage >= 90 else "中高" if coverage >= 75 else "中" if coverage >= 60 else "中低"
        constraints = _account_constraints(state, position, score, execution.get("constraints", {}))
        rows.append({
            "symbol": symbol,
            "name": position.name,
            "position_status": "active" if float(position.quantity or 0) > 0 else "watchlist",
            "score": score,
            "coverage": coverage,
            "confidence": confidence,
            "reference_price": position.market_price or position.system_quote_price,
            "dimensions": dimensions,
            "evidence_counts": evidence.get("evidence_counts"),
            "question_statuses": evidence.get("question_statuses"),
            "question_changes": evidence.get("question_changes", []),
            "theme_id": theme_position.get("theme_id"),
            "theme_name": theme_position.get("theme_name"),
            "top_reasons": [
                reason
                for item in sorted(
                    [item for item in dimensions if item.get("score") is not None],
                    key=lambda value: float(value.get("score") or 0),
                    reverse=True,
                )[:2]
                for reason in (item.get("reasons") or [])[:1]
            ],
            "execution_constraints": dimensions[-1].get("constraints", {}),
            "account_constraints": constraints,
            "account_readiness_score": constraints["readiness_score"],
            "data_health": {
                "trend_status": next((item.get("data_status") for item in dimensions if item["key"] == "trend_strength"), None),
                "trend_as_of": trend.get("daily_k_as_of"),
                "announcement_checked_at": (theme_position.get("announcement_verification") or {}).get("index_checked_at"),
                "announcement_status": (theme_position.get("announcement_verification") or {}).get("status") or "unavailable",
                "valuation_status": next(
                    (
                        (item.get("reference") or {}).get("status", "configured_reference")
                        for item in dimensions if item["key"] == "valuation_consensus"
                    ),
                    "unavailable",
                ),
            },
        })
    theme_groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        row["portfolio_priority_score"] = _clamp(
            float(row.get("score") or 0) * 0.50
            + float(row.get("account_readiness_score") or 0) * 0.30
            + float(row.get("coverage") or 0) * 0.20
        )
        theme_groups.setdefault(str(row.get("theme_id") or "unmapped"), []).append(row)
    for group in theme_groups.values():
        group.sort(key=lambda item: item["portfolio_priority_score"], reverse=True)
        leader = group[0]
        for index, row in enumerate(group, start=1):
            row["theme_rank"] = index
            row["opportunity_cost"] = {
                "preferred_within_theme": index == 1,
                "dominated_by_symbol": None if index == 1 else leader["symbol"],
                "dominated_by_name": None if index == 1 else leader["name"],
                "priority_gap": 0 if index == 1 else leader["portfolio_priority_score"] - row["portfolio_priority_score"],
            }
    if persist_history:
        _history_changes(rows, generated_at)
    rows.sort(key=lambda item: (item.get("score") is not None, item.get("score") or 0), reverse=True)
    return {
        "generated_at": generated_at,
        "model": "attractiveness_rules_v1",
        "dimension_weights": DIMENSION_WEIGHTS,
        "positions": rows,
        "consensus_registry_version": consensus.get("version"),
        "benchmark": next(
            (
                item.get("benchmarks", {}).get("market")
                for row in rows
                for item in row.get("dimensions", [])
                if item.get("key") == "trend_strength" and item.get("benchmarks")
            ),
            {"status": "unavailable"},
        ),
        "validation": _attractiveness_validation(history),
        "data_quality": {
            "valuation_source_status": "local_free",
            "benchmark_status": next(
                (
                    item.get("benchmarks", {}).get("market", {}).get("status")
                    for row in rows
                    for item in row.get("dimensions", [])
                    if item.get("key") == "trend_strength" and item.get("benchmarks")
                ),
                "unavailable",
            ),
            "history_snapshot_count": sum(len(items) for items in (history.get("symbols") or {}).values()),
        },
        "boundary": (
            "吸引力衡量新增风险敞口的相对价值，不等同于目标价或买入指令。"
            "缺失估值和价格位置时不填中性分，只降低覆盖率；最终动作仍需同时满足健康度与执行约束。"
        ),
    }
