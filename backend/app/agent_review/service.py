from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import ValidationError

from app.agent_context.service import build_daily_review_context
from app.agent_review.schemas import DailyReviewOutput


BACKEND_DIR = Path(__file__).resolve().parents[2]
REVIEW_DIR = BACKEND_DIR / "data" / "agent_reviews"
LATEST_PATH = REVIEW_DIR / "latest.json"
REVIEW_CONTRACT_VERSION = "agent_review.v1"
PROVIDER_NAME = "volcengine_ark"
LOCAL_TZ = ZoneInfo("Asia/Shanghai")

SYSTEM_PROMPT = """
你是 Stock-Pilot 的账户与市场复盘模型。输入由本地系统生成，包含事实、
系统推断、数据时间和证据目录。

硬性规则：
1. 只能引用 evidence_catalog 中存在的 evidence_ref，不得编造事实或证据编号。
2. 陈旧证据不能描述为当前信号；缺失数据不能解释为利好或利空。
3. rotation 的机会优先级以机会阶段为主：potential_opportunity 和 early_turning
   优先于 wait_pullback；高分但 wait_pullback 不能因强度更高而排在早期机会之前。
4. 轮动机会发现不结合当前是否持仓；账户持仓只用于独立的风险审计。
5. 每个判断必须给出支持证据、反证、行动语义和失效条件。
6. 不输出买入、卖出、加仓、减仓、满仓或具体仓位指令。
7. 若证据不足，放入 watch_items 或 verification_tasks，不勉强生成机会结论。
8. verification_tasks 必须说明 target_symbols、evidence_type、missing_evidence
   和 success_criteria；有明确标的时必须给六位代码，不能只写公司名称。
9. 必须比较 previous_review，输出真正发生变化的项目；没有显著变化时明确输出
   no_action，不为制造行动而制造行动。
10. learning_feedback 只用于校准：如果当前判断重复历史失败模式，必须指出新增证据，
    否则降级为观察或核查任务。历史成绩不能替代当前证据。
11. 操作复盘按 operation_review_period 二选一：日复盘最多展开 3 项代表性操作；周复盘最多展开
    3 个代表性标的。完整事实保留在输入台账中，不要求模型逐笔复述。
12. 只输出一个 JSON 对象，不输出 Markdown、前言或解释。
13. 使用短结论模式：完整 JSON 不超过 6000 个字符；每类最多 3 条，每个字符串尽量
   控制在 100 个汉字内，不复述输入数据，不解释评分计算过程。
""".strip()

ACCOUNT_STATE_PROMPT = """
账户状态口径规则：
1. 必须严格区分“账户总盈亏”和“当前持仓浮动盈亏”。
2. 账户总盈亏反映包含历史已实现损益在内的整体账户状态，优先级高于当前持仓浮盈。
3. 若账户总盈亏为负，headline 或 summary 必须明确写出账户处于回撤/亏损状态，
   不能用“账户整体盈利”概括。
""".strip()

LOOP_PLANNING_PROMPT = """
闭环规划规则：
1. learning_feedback.operation_feedback 包含用户真实操作、当时 AI 策略及后续评价。
2. 用户操作与既有建议一致或冲突都不是结论；必须结合后续事实评价原因。
3. decision_focus 是下一周期执行计划，应优先处理：策略冲突核查、到期结果评价、
   低置信度证据补齐；不得只重复当日摘要。
4. 模型只能归纳工具取得的可追溯事实，不得把另一个模型的判断当作事实证据。
5. 如需模型辅助取证，只能用于候选来源筛选、文本归纳和冲突解释，最终事实仍需
   对应结构化数据或原始来源 evidence_ref。
6. operation_feedback.weekly_symbol_operations 是滚动五交易日操作事实。逐标的检查净买卖、
   双向操作、反向次数和策略冲突；provisional_market_result 只作临时观察，不判定成败。
""".strip()

DAILY_OPERATION_PROMPT = """
Operation review rules:
1. operation_feedback.daily_actions and weekly_symbol_operations always retain the complete local fact ledger.
2. When operation_review_period is daily, produce one overall daily reflection and select at most three representative actions. Leave weekly items empty.
3. When operation_review_period is weekly, produce one overall five-trading-day reflection and select at most three representative symbols. Leave daily items empty.
4. Prefer operations that are large, reverse direction, conflict with prior strategy, lack a user reason, or materially change concentration.
5. Missing reasons must be identified as missing, not inferred. Provisional weekly returns are not matured success/failure outcomes.
""".strip()

SOURCE_RELIABILITY_PROMPT = """
Evidence source reliability rules:
1. system:source_health reports observed tool success, partial success, and failure history.
2. Low source reliability lowers confidence; it does not prove that the underlying investment thesis is false.
3. Prefer a different whitelisted source or a manual task when the selected source repeatedly fails.
""".strip()

LEARNING_POLICY_PROMPT = """
Versioned learning policy rules:
1. learning_feedback.policy_memory is deterministic and versioned; the model cannot activate, edit, or retire policies.
2. Active policies are mandatory decision constraints. Monitoring policies may be mentioned but must not be treated as proven rules.
3. When an active policy changes a conclusion, cite learning:scorecard and state which additional evidence would override the constraint.
""".strip()


def _load_env() -> None:
    load_dotenv(BACKEND_DIR / ".env")


def _model_name() -> str:
    _load_env()
    return os.getenv("AGENT_REVIEW_MODEL") or os.getenv("LLM_MODEL") or "deepseek-v4-pro"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _operation_review_period(reference: datetime | None = None) -> str:
    value = reference or datetime.now(LOCAL_TZ)
    if value.tzinfo is None:
        value = value.replace(tzinfo=LOCAL_TZ)
    return "weekly" if value.astimezone(LOCAL_TZ).weekday() == 4 else "daily"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _json_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _pick(payload: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {
        key: payload.get(key)
        for key in keys
        if payload.get(key) is not None
    }


def _compact_holdings(portfolio_facts: dict[str, Any]) -> list[dict[str, Any]]:
    trends = {
        str(item.get("symbol") or ""): item
        for item in portfolio_facts.get("holding_trend_evidence", [])
    }
    items: list[dict[str, Any]] = []
    for holding in portfolio_facts.get("holdings", []):
        symbol = str(holding.get("symbol") or "")
        trend = trends.get(symbol, {})
        items.append({
            "evidence_ref": f"holding:{symbol}",
            "scope": "portfolio_holding",
            "facts": _pick(holding, (
                "symbol",
                "name",
                "avg_cost",
                "market_price",
                "unrealized_pnl_pct",
                "portfolio_weight_pct",
                "position_status",
                "confirmed_primary_theme",
                "confirmed_theme_tags",
                "confirmed_directions",
                "confirmed_risk_flags",
                "confirmed_position_role",
            )),
            "trend_evidence": _pick(trend, (
                "data_status",
                "daily_k_as_of",
                "latest_pct_chg",
                "return_5d_pct",
                "return_20d_pct",
                "return_60d_pct",
                "rsi14",
                "price_vs_ma20_pct",
                "trend_state",
                "strategy_observation",
                "interpretation_limit",
                "reason",
            )),
        })
    return items


def _compact_events(portfolio_facts: dict[str, Any]) -> list[dict[str, Any]]:
    events = portfolio_facts.get("market_events", {}).get("events", [])[:8]
    items: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        facts = _pick(event, (
            "event_id",
            "date",
            "category",
            "title",
            "days_until",
            "status",
            "impact_level",
            "impact_score",
            "portfolio_readout",
            "focus_points",
        ))
        facts["impact_channels"] = [
            _pick(channel, ("channel", "label"))
            for channel in event.get("matched_impact_channels", [])[:4]
        ]
        facts["related_positions"] = [
            _pick(position, ("symbol", "name", "portfolio_weight_pct"))
            for position in event.get("related_positions", [])[:6]
        ]
        items.append({
            "evidence_ref": f"event:{event.get('event_id') or index + 1}",
            "scope": "market_event",
            "facts": facts,
        })
    return items


def _compact_rotation(
    rotation_facts: dict[str, Any],
    rotation_inferences: dict[str, Any],
) -> list[dict[str, Any]]:
    assessments = {
        str(item.get("sector_id") or ""): item
        for item in rotation_inferences.get("sector_opportunity_assessments", [])
    }
    items: list[dict[str, Any]] = []
    for evidence in rotation_facts.get("sector_evidence", []):
        sector_id = str(evidence.get("sector_id") or "")
        assessment = assessments.get(sector_id, {})
        score = assessment.get("score", {})
        proxy_components = [
            _pick(component, ("symbol", "name", "weight"))
            for component in evidence.get("proxy_components", [])[:5]
        ]
        items.append({
            "evidence_ref": f"rotation:{sector_id}",
            "scope": "rotation_sector",
            "facts": {
                **_pick(evidence, (
                "sector_id",
                "name",
                "category",
                "proxy_type",
                "primary_symbol",
                "selected_symbol",
                "latest_date",
                "returns",
                "relative_strength",
                "flow",
                "data_quality",
                "missing_fields",
                "stale_days_to_market",
                )),
                "proxy_components": proxy_components,
            },
            "system_inference": {
                **_pick(assessment, (
                "score_delta_1d",
                "score_delta_5d",
                "score_delta_10d",
                "maturity",
                "opportunity_stage",
                "action_label",
                "chasing_risk",
                "opportunity_reason",
                "ma20_distance_pct",
                )),
                "score_total": score.get("total"),
            },
        })
    return items


def _compact_portfolio_inferences(portfolio_inferences: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, item in enumerate(portfolio_inferences.get("primary_direction_grouping", [])):
        direction = item.get("direction") or index + 1
        items.append({
            "evidence_ref": f"portfolio_direction:{direction}",
            "scope": "portfolio_direction",
            "system_inference": _pick(item, ("direction", "weight_pct", "symbols")),
        })
    for queue_name in ("opportunity_queue", "risk_queue"):
        for index, item in enumerate(portfolio_inferences.get(queue_name, [])):
            if index >= 4:
                break
            symbol = item.get("symbol") or index + 1
            items.append({
                "evidence_ref": f"portfolio_{queue_name}:{symbol}",
                "scope": f"portfolio_{queue_name}",
                "system_inference": _pick(item, (
                    "symbol",
                    "name",
                    "position_status",
                    "position_role",
                    "primary_direction",
                    "portfolio_weight_pct",
                    "unrealized_pnl_pct",
                    "trend_state",
                    "return_20d_pct",
                    "price_vs_ma20_pct",
                    "score",
                    "evidence_refs",
                )),
            })
    risk_observations = portfolio_inferences.get("risk_observations", {})
    for index, item in enumerate(risk_observations.get("risk_observations", [])):
        risk_key = item.get("risk_flag") or item.get("theme") or index + 1
        items.append({
            "evidence_ref": f"portfolio_risk:{risk_key}",
            "scope": "portfolio_risk_observation",
            "system_inference": _pick(item, (
                "risk_flag",
                "theme",
                "weight_pct",
                "symbols",
                "observation",
            )),
        })
    return items


def _compact_previous_review() -> dict[str, Any] | None:
    previous = _read_json(LATEST_PATH)
    if not previous or previous.get("status") != "completed":
        return None
    review = previous.get("review") or {}
    return {
        "run_id": previous.get("run_id"),
        "completed_at": previous.get("completed_at"),
        "headline": review.get("headline"),
        "summary": review.get("summary"),
        "opportunities": review.get("opportunities", []),
        "risks": review.get("risks", []),
        "watch_items": review.get("watch_items", []),
        "decision_focus": review.get("decision_focus", []),
    }


def build_review_model_input(context: dict[str, Any]) -> dict[str, Any]:
    from app.agent_review.outcomes import build_learning_feedback
    from app.agent_review.tasks import task_health

    facts = context.get("facts", {})
    operation_review_period = _operation_review_period()
    inferences = context.get("inferences", {})
    portfolio_facts = facts.get("portfolio", {})
    rotation_facts = facts.get("rotation", {})
    portfolio_inferences = inferences.get("portfolio", {})
    rotation_inferences = inferences.get("rotation", {})

    account_facts = portfolio_facts.get("account", {})
    account_total_pnl = account_facts.get("account_total_pnl")
    holding_pnl = account_facts.get("current_holding_unrealized_pnl")
    evidence_catalog: list[dict[str, Any]] = [{
        "evidence_ref": "account:overview",
        "scope": "account_overview",
        "facts": {
            **_pick(account_facts, (
                "total_assets",
                "invested_ratio_pct",
                "cash_ratio_pct",
                "active_position_count",
                "watchlist_position_count",
                "account_actual_total_cost",
                "account_total_pnl",
                "account_total_pnl_pct",
                "account_total_pnl_status",
                "current_holding_cost_basis",
                "current_holding_unrealized_pnl",
                "current_holding_unrealized_pnl_pct",
                "current_holding_unrealized_pnl_status",
            )),
            "account_state_semantics": {
                "priority": "account_total_pnl_over_current_holding_pnl",
                "account_total_state": (
                    "drawdown" if account_total_pnl is not None and account_total_pnl < 0
                    else "profit" if account_total_pnl is not None and account_total_pnl > 0
                    else "flat" if account_total_pnl == 0
                    else "unavailable"
                ),
                "current_holding_state": (
                    "profit" if holding_pnl is not None and holding_pnl > 0
                    else "loss" if holding_pnl is not None and holding_pnl < 0
                    else "flat" if holding_pnl == 0
                    else "unavailable"
                ),
            },
        },
    }]
    evidence_catalog.extend(_compact_holdings(portfolio_facts))
    evidence_catalog.extend(_compact_events(portfolio_facts))
    evidence_catalog.extend(_compact_rotation(rotation_facts, rotation_inferences))
    evidence_catalog.extend(_compact_portfolio_inferences(portfolio_inferences))
    gaps = context.get("missing_data", [])
    if gaps:
        samples: list[dict[str, Any]] = []
        for gap in gaps[:12]:
            detail = gap.get("detail", {}) if isinstance(gap, dict) else {}
            samples.append({
                "scope": gap.get("scope") if isinstance(gap, dict) else None,
                **_pick(detail, ("key", "symbol", "reason")),
            })
        evidence_catalog.append({
            "evidence_ref": "gap:summary",
            "scope": "missing_data",
            "facts": {
                "count": len(gaps),
                "samples": samples,
            },
        })
    learning_feedback = build_learning_feedback()
    weekly_operations = (
        learning_feedback.get("operation_feedback", {})
        .get("weekly_symbol_operations", {})
    )
    daily_date = str(weekly_operations.get("window_end") or "")
    daily_items = []
    for item in weekly_operations.get("items", []):
        evidence_catalog.append({
            "evidence_ref": item.get("evidence_ref"),
            "scope": "weekly_symbol_operation",
            "facts": item,
        })
        for action in item.get("sequence", []):
            if action.get("trading_date") != daily_date or not action.get("action_id"):
                continue
            quantity_delta = float(action.get("quantity_delta") or 0)
            daily_action = {
                **action,
                "symbol": item.get("symbol"),
                "name": item.get("name"),
                "action_type": "buy" if quantity_delta > 0 else "sell",
                "evidence_ref": f"operation:action:{action.get('action_id')}",
            }
            daily_items.append(daily_action)
            evidence_catalog.append({
                "evidence_ref": daily_action["evidence_ref"],
                "scope": "daily_confirmed_operation",
                "facts": daily_action,
            })
    daily_operations = {
        "trading_date": daily_date,
        "action_count": len(daily_items),
        "items": daily_items,
    }
    learning_feedback.setdefault("operation_feedback", {})["daily_actions"] = daily_operations
    scorecard_feedback = {
        **learning_feedback,
        "operation_feedback": {
            key: value
            for key, value in learning_feedback.get("operation_feedback", {}).items()
            if key not in {"weekly_symbol_operations", "daily_actions"}
        },
    }
    evidence_catalog.append({
        "evidence_ref": "learning:scorecard",
        "scope": "historical_decision_feedback",
        "facts": scorecard_feedback,
    })
    evidence_catalog.append({
        "evidence_ref": "system:source_health",
        "scope": "evidence_source_reliability",
        "facts": task_health().get("source_health", []),
    })

    return {
        "task": (
            "生成今日账户与市场复盘，优先发现早期机会，独立审计账户风险；"
            "与上一版比较，只突出真实变化；按 operation_review_period 对交易操作做整体复盘，"
            "仅展开最多三项最有代表性的操作或标的，"
            "并给出最多三项今日决策焦点。"
        ),
        "operation_review_period": operation_review_period,
        "agent_goal": {
            "primary": "持续发现可验证机会、控制账户风险，并评价用户操作与既有建议的成败原因",
            "cycle": [
                "observe_account_and_market",
                "compare_user_actions_with_prior_strategy",
                "plan_verification",
                "execute_bounded_tools",
                "evaluate_matured_outcomes",
                "feed_results_into_next_cycle",
            ],
            "evidence_policy": {
                "model_assistance": "triage_and_summarize_only",
                "fact_requirement": "structured_data_or_primary_source_evidence_ref",
                "human_approval": "required_for_portfolio_changes",
            },
        },
        "context_meta": context.get("meta", {}),
        "evidence_catalog": evidence_catalog,
        "previous_review": _compact_previous_review(),
        "learning_feedback": learning_feedback,
        "required_output_contract": {
            "operation_review_period": "daily|weekly，必须与输入一致",
            "headline": "string",
            "data_status": {
                "usable": "boolean",
                "stale_evidence_refs": ["evidence_ref"],
                "missing_evidence_refs": ["evidence_ref"],
                "summary": "string",
            },
            "opportunities": ["review_item"],
            "risks": ["review_item"],
            "watch_items": ["review_item"],
            "verification_tasks": [{
                "priority": "high|medium|low",
                "subject": "string",
                "task": "string",
                "reason": "string",
                "target_symbols": ["六位证券代码"],
                "evidence_type": "market_snapshot|rotation|event_outcome|announcement|financial|manual",
                "missing_evidence": ["当前缺少的具体事实"],
                "success_criteria": "取得什么结果才算完成核查",
            }],
            "changes_since_previous_review": [{
                "subject": "string",
                "change_type": "new|strengthened|weakened|resolved|unchanged",
                "summary": "string",
                "evidence_refs": ["evidence_ref"],
            }],
            "decision_focus": [{
                "priority": "high|medium|low",
                "subject": "string",
                "action": "verify|monitor|review_risk|wait|no_action",
                "reason": "string",
                "evidence_refs": ["evidence_ref"],
            }],
            "daily_operation_review": {
                "trading_date": "YYYY-MM-DD",
                "action_count": "integer",
                "items": [{
                    "action_id": "input action_id",
                    "symbol": "six-digit symbol",
                    "name": "string",
                    "action_type": "buy|sell",
                    "operation_summary": "facts and direct portfolio effect",
                    "strategy_reflection": "representative-action reflection against prior AI strategy",
                    "next_review_condition": "next verification condition",
                    "evidence_refs": ["operation:action:action_id"],
                }],
                "overall_reflection": "daily operation discipline and unresolved issues",
            },
            "weekly_operation_review": {
                "window_start": "YYYY-MM-DD",
                "window_end": "YYYY-MM-DD",
                "trading_days": ["最近五个交易日"],
                "action_count": "integer",
                "symbol_count": "integer",
                "items": [{
                    "symbol": "六位证券代码",
                    "name": "string",
                    "operation_summary": "合并描述买卖次数、净变化和方向反转",
                    "strategy_reflection": "结合当时AI策略反思，不以临时收益判定成败",
                    "next_review_condition": "下一次需要核查的条件",
                    "evidence_refs": ["operation:weekly:日期:代码"],
                }],
                "overall_reflection": "本周操作纪律、策略一致性与待验证问题",
            },
            "summary": "string",
            "review_item": {
                "item_id": "string",
                "subject": "string",
                "conclusion": "string",
                "confidence": "high|medium|low",
                "evidence_refs": ["evidence_ref"],
                "counter_evidence_refs": ["evidence_ref"],
                "action_semantics": "string",
                "invalidation_conditions": ["string"],
            },
        },
        "output_limits": {
            "max_opportunities": 3,
            "max_risks": 3,
            "max_watch_items": 3,
            "max_verification_tasks": 6,
            "max_changes": 5,
            "max_decision_focus": 3,
            "max_daily_operation_items": 3,
            "max_weekly_operation_items": 3,
            "max_total_json_characters": 6000,
            "max_invalidation_conditions_per_item": 2,
        },
    }


def _extract_json(content: str) -> dict[str, Any]:
    text = content.strip()
    candidates = [text]
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        candidates.insert(0, fenced.group(1))
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        candidates.append(text[first:last + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("模型未返回可解析的 JSON 对象")


def _call_model(messages: list[dict[str, str]]) -> tuple[str, dict[str, int], str]:
    _load_env()
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = _model_name()
    if not api_key or not base_url:
        raise RuntimeError("火山引擎 LLM_BASE_URL 或 LLM_API_KEY 未配置")
    max_tokens = int(os.getenv("AGENT_REVIEW_MAX_TOKENS", "2500"))
    timeout_seconds = float(os.getenv("AGENT_REVIEW_TIMEOUT_SECONDS", "180"))
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=httpx.Timeout(timeout_seconds, connect=15),
        max_retries=1,
    )
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        stream=False,
    )
    content = response.choices[0].message.content or ""
    usage = response.usage
    return content, {
        "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
    }, str(response.choices[0].finish_reason or "")


def suggest_trade_reason(
    transactions: list[dict[str, Any]],
    current_positions: list[dict[str, Any]],
) -> dict[str, Any]:
    prompt = {
        "task": (
            "根据已确认前的成交事实生成一条供用户修改的交易理由草稿。"
            "不得猜测截图中不存在的动机，不得给出新的买卖建议。"
        ),
        "transactions": transactions[:12],
        "related_current_positions": current_positions[:12],
        "required_output": {
            "reason_summary": "不超过120字；未知动机明确写待用户补充",
            "confidence": "high|medium|low",
            "questions": ["最多3个需要用户补充的问题"],
        },
    }
    content, usage, _ = _call_model([
        {
            "role": "system",
            "content": (
                "你是交易日志整理助手，只整理用户已发生的成交事实。"
                "不提供投资建议，不虚构交易动机，只输出 JSON。"
            ),
        },
        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
    ])
    parsed = _extract_json(content)
    reason = str(parsed.get("reason_summary") or "").strip()
    confidence = str(parsed.get("confidence") or "low")
    questions = [
        str(item).strip()
        for item in parsed.get("questions", [])
        if str(item).strip()
    ][:3]
    if confidence not in {"high", "medium", "low"}:
        confidence = "low"
    if not reason:
        reason = "已记录本次成交；具体交易动机待用户补充。"
    return {
        "reason_summary": reason[:200],
        "confidence": confidence,
        "questions": questions,
        "model": _model_name(),
        "usage": usage,
    }


def _direct_trade_instruction(payload: dict[str, Any]) -> bool:
    text = json.dumps(payload, ensure_ascii=False)
    patterns = [
        r"建议.{0,4}(买入|卖出|加仓|减仓|满仓)",
        r"应该.{0,4}(买入|卖出|加仓|减仓|满仓)",
        r"(立即|直接|现在).{0,4}(买入|卖出|加仓|减仓|满仓)",
        r"(买入|卖出|加仓|减仓).{0,8}\d+%",
    ]
    return any(re.search(pattern, text) for pattern in patterns)


def _normalize_security_code(value: Any) -> str:
    match = re.search(r"\d{6}", str(value or ""))
    return match.group(0) if match else str(value or "")


def _normalize_review_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(payload, ensure_ascii=False))
    for field in (
        "opportunities",
        "risks",
        "watch_items",
        "verification_tasks",
        "changes_since_previous_review",
        "decision_focus",
    ):
        if normalized.get(field) is None:
            normalized[field] = []
    for task in normalized.get("verification_tasks") or []:
        symbols = []
        for value in task.get("target_symbols", []):
            symbol = _normalize_security_code(value)
            if symbol and symbol not in symbols:
                symbols.append(symbol)
        task["target_symbols"] = symbols[:5]
    for section in ("daily_operation_review", "weekly_operation_review"):
        if normalized.get(section) is None:
            normalized[section] = {}
        section_payload = normalized.get(section) or {}
        normalized[section] = section_payload
        if section == "daily_operation_review":
            defaults = {
                "trading_date": "",
                "action_count": 0,
                "items": [],
                "overall_reflection": "当日没有需要复盘的已确认操作。",
            }
        else:
            defaults = {
                "window_start": "",
                "window_end": "",
                "trading_days": [],
                "action_count": 0,
                "symbol_count": 0,
                "items": [],
                "overall_reflection": "本周没有需要复盘的已确认操作。",
            }
        for key, default in defaults.items():
            if section_payload.get(key) is None:
                section_payload[key] = default
        for item in section_payload.get("items", []):
            item["symbol"] = _normalize_security_code(item.get("symbol"))
            if section == "daily_operation_review":
                action_type = str(item.get("action_type") or "").lower()
                if action_type in {"increased", "opened", "买入"}:
                    item["action_type"] = "buy"
                elif action_type in {"reduced", "closed", "卖出"}:
                    item["action_type"] = "sell"
    if normalized.get("operation_review_period") is None:
        normalized["operation_review_period"] = "daily"
    return normalized


def _validate_review(
    payload: dict[str, Any],
    model_input: dict[str, Any],
) -> tuple[DailyReviewOutput, list[str], list[str]]:
    review = DailyReviewOutput.model_validate(_normalize_review_payload(payload))
    daily_input = (
        model_input.get("learning_feedback", {})
        .get("operation_feedback", {})
        .get("daily_actions", {})
    )
    weekly_input = (
        model_input.get("learning_feedback", {})
        .get("operation_feedback", {})
        .get("weekly_symbol_operations", {})
    )
    expected_period = str(model_input.get("operation_review_period") or "daily")
    review.operation_review_period = expected_period
    expected_daily_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for item in daily_input.get("items", []):
        symbol = _normalize_security_code(item.get("symbol"))
        expected_daily_by_symbol.setdefault(symbol, []).append(item)
    for item in review.daily_operation_review.items:
        candidates = expected_daily_by_symbol.get(item.symbol, [])
        if not candidates:
            continue
        expected = candidates.pop(0)
        item.action_id = str(expected.get("action_id") or item.action_id)
        item.action_type = str(expected.get("action_type") or item.action_type)
        item.evidence_refs = [str(expected.get("evidence_ref"))]
    weekly_by_symbol = {
        _normalize_security_code(item.get("symbol")): item
        for item in weekly_input.get("items", [])
        if item.get("symbol")
    }
    for item in review.weekly_operation_review.items:
        expected = weekly_by_symbol.get(item.symbol)
        if expected:
            item.evidence_refs = [str(expected.get("evidence_ref"))]
    if expected_period == "daily":
        review.weekly_operation_review.items = []
    else:
        review.daily_operation_review.items = []
    allowed_refs = {
        str(item["evidence_ref"])
        for item in model_input["evidence_catalog"]
    }
    used_refs: set[str] = set(review.data_status.stale_evidence_refs)
    used_refs.update(review.data_status.missing_evidence_refs)
    for group in (review.opportunities, review.risks, review.watch_items):
        for item in group:
            used_refs.update(item.evidence_refs)
            used_refs.update(item.counter_evidence_refs)
    for item in review.changes_since_previous_review:
        used_refs.update(item.evidence_refs)
    for item in review.decision_focus:
        used_refs.update(item.evidence_refs)
    for item in review.daily_operation_review.items:
        used_refs.update(item.evidence_refs)
    for item in review.weekly_operation_review.items:
        used_refs.update(item.evidence_refs)
    unknown_refs = sorted(used_refs - allowed_refs)
    errors: list[str] = []
    policy_warnings: list[str] = []
    if not review.decision_focus:
        errors.append("decision_focus 至少需要一项；无显著动作时必须输出 no_action")
    expected_daily_ids = {
        str(item.get("action_id") or "")
        for item in daily_input.get("items", [])
        if item.get("action_id")
    }
    reviewed_daily_ids = {item.action_id for item in review.daily_operation_review.items}
    if expected_period == "daily":
        extra = sorted(reviewed_daily_ids - expected_daily_ids)
        if extra:
            errors.append(f"日复盘包含未知操作：{extra}")
        if expected_daily_ids and not reviewed_daily_ids:
            errors.append("日复盘应至少选择一项代表性操作")
    review.daily_operation_review.trading_date = str(daily_input.get("trading_date") or "")
    review.daily_operation_review.action_count = (
        int(daily_input.get("action_count") or 0) if expected_period == "daily" else 0
    )
    expected_weekly_symbols = {
        str(item.get("symbol") or "")
        for item in weekly_input.get("items", [])
        if item.get("symbol")
    }
    reviewed_weekly_symbols = {item.symbol for item in review.weekly_operation_review.items}
    if expected_period == "weekly":
        extra = sorted(reviewed_weekly_symbols - expected_weekly_symbols)
        if extra:
            errors.append(f"周复盘包含未知标的：{extra}")
        if expected_weekly_symbols and not reviewed_weekly_symbols:
            errors.append("周复盘应至少选择一个代表性标的")
    review.weekly_operation_review.window_start = str(weekly_input.get("window_start") or "")
    review.weekly_operation_review.window_end = str(weekly_input.get("window_end") or "")
    review.weekly_operation_review.trading_days = list(weekly_input.get("trading_dates") or [])[:5]
    review.weekly_operation_review.action_count = (
        int(weekly_input.get("action_count") or 0) if expected_period == "weekly" else 0
    )
    review.weekly_operation_review.symbol_count = (
        int(weekly_input.get("symbol_count") or 0) if expected_period == "weekly" else 0
    )
    if unknown_refs:
        errors.append(f"存在未提供的证据编号：{', '.join(unknown_refs)}")
    instruction_payload = review.model_dump(mode="json")
    instruction_payload.pop("daily_operation_review", None)
    instruction_payload.pop("weekly_operation_review", None)
    if _direct_trade_instruction(instruction_payload):
        errors.append("输出包含禁止的直接交易指令")

    account_evidence = next(
        (
            item.get("facts", {})
            for item in model_input.get("evidence_catalog", [])
            if item.get("evidence_ref") == "account:overview"
        ),
        {},
    )
    if account_evidence.get("account_total_pnl") is not None and account_evidence["account_total_pnl"] < 0:
        account_summary = f"{review.headline} {review.summary}"
        if not re.search(r"账户.{0,8}(回撤|亏损|总盈亏.{0,4}负)|总账户.{0,8}(回撤|亏损)", account_summary):
            errors.append("账户总盈亏为负时，headline 或 summary 必须明确说明账户整体处于回撤/亏损状态")

    meta = model_input.get("context_meta", {})
    rotation_status = meta.get("freshness", {}).get("rotation", {}).get("status")
    if rotation_status == "stale":
        valid_opportunities = []
        for item in review.opportunities:
            if item.evidence_refs and all(ref.startswith("rotation:") for ref in item.evidence_refs):
                policy_warnings.append(f"机会 {item.subject} 仅由陈旧轮动证据支持，已降级为观察项")
                if len(review.watch_items) < 3:
                    review.watch_items.append(item.model_copy(update={
                        "conclusion": (
                            f"{item.conclusion[:110]}；但轮动证据陈旧，当前不构成机会结论。"
                        ),
                        "confidence": "low",
                        "action_semantics": "等待轮动数据更新后重新评估，当前仅列入事实核查队列。",
                    }))
                continue
            valid_opportunities.append(item)
        review.opportunities = valid_opportunities
    return review, errors, policy_warnings


def _generate_with_correction(model_input: dict[str, Any]) -> tuple[DailyReviewOutput, dict[str, int], list[str]]:
    messages = [
        {
            "role": "system",
            "content": f"{SYSTEM_PROMPT}\n\n{ACCOUNT_STATE_PROMPT}\n\n{LOOP_PLANNING_PROMPT}\n\n{DAILY_OPERATION_PROMPT}\n\n{SOURCE_RELIABILITY_PROMPT}\n\n{LEARNING_POLICY_PROMPT}",
        },
        {"role": "user", "content": json.dumps(model_input, ensure_ascii=False)},
    ]
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    validation_warnings: list[str] = []
    last_error = ""
    for attempt in range(2):
        content, usage, finish_reason = _call_model(messages)
        for key in total_usage:
            total_usage[key] += usage[key]
        try:
            if not content.strip():
                raise ValueError(
                    f"模型返回空正文（finish_reason={finish_reason}, "
                    f"completion_tokens={usage['completion_tokens']}）"
                )
            parsed = _extract_json(content)
            review, errors, policy_warnings = _validate_review(parsed, model_input)
            validation_warnings.extend(policy_warnings)
            if finish_reason == "length":
                errors.append("模型输出达到长度上限")
            if not errors:
                return review, total_usage, validation_warnings
            last_error = "；".join(errors)
        except (ValueError, ValidationError) as exc:
            last_error = (
                f"{str(exc)[:900]}；finish_reason={finish_reason}；"
                f"content_chars={len(content)}；completion_tokens={usage['completion_tokens']}"
            )
        if attempt == 0:
            validation_warnings.append(f"首次输出未通过校验：{last_error}")
            correction = {
                "role": "user",
                "content": (
                    f"上一次输出未通过系统校验：{last_error}。"
                    "请仅修正这些问题，重新输出完整 JSON；不得新增证据编号。"
                    "必须压缩到 6000 字符以内。"
                ),
            }
            if finish_reason == "length":
                messages.append(correction)
            else:
                messages.extend([
                    {"role": "assistant", "content": content},
                    correction,
                ])
    raise ValueError(f"模型输出两次未通过校验：{last_error}")


def _persist_run(payload: dict[str, Any], *, update_latest: bool) -> None:
    run_id = payload["run_id"]
    _write_json(REVIEW_DIR / f"{run_id}.json", payload)
    if update_latest:
        _write_json(LATEST_PATH, payload)


def _completed_payload(
    *,
    run_id: str,
    started_at: datetime,
    model: str,
    context: dict[str, Any],
    model_input: dict[str, Any],
    review: DailyReviewOutput,
    usage: dict[str, int],
    validation_warnings: list[str],
    force_context: bool,
    review_mode: str,
    parent_run_id: str | None = None,
    tool_evidence_count: int = 0,
) -> dict[str, Any]:
    completed_at = _now()
    return {
        "contract_version": REVIEW_CONTRACT_VERSION,
        "run_id": run_id,
        "status": "completed",
        "review_mode": review_mode,
        "parent_run_id": parent_run_id,
        "provider": PROVIDER_NAME,
        "model": model,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "elapsed_ms": round((completed_at - started_at).total_seconds() * 1000),
        "usage": usage,
        "context": {
            "fingerprint": _json_hash(model_input),
            "data_time": context.get("meta", {}).get("data_time", {}),
            "freshness": context.get("meta", {}).get("freshness", {}),
            "evidence_count": len(model_input["evidence_catalog"]),
            "tool_evidence_count": tool_evidence_count,
            "force_context": force_context,
        },
        "validation_warnings": validation_warnings,
        "review": review.model_dump(mode="json"),
    }


def _sync_tasks(payload: dict[str, Any]) -> None:
    from app.agent_review.tasks import sync_review_tasks

    sync_review_tasks(payload)


def _register_outcomes(payload: dict[str, Any], model_input: dict[str, Any]) -> None:
    from app.agent_review.outcomes import register_review_outcomes

    register_review_outcomes(payload, model_input)


def generate_daily_review(*, force_context: bool = False) -> dict[str, Any]:
    started_at = _now()
    run_id = f"daily-{started_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    model = _model_name()
    try:
        context = build_daily_review_context(force=force_context)
        model_input = build_review_model_input(context)
        review, usage, validation_warnings = _generate_with_correction(model_input)
        payload = _completed_payload(
            run_id=run_id,
            started_at=started_at,
            model=model,
            context=context,
            model_input=model_input,
            review=review,
            usage=usage,
            validation_warnings=validation_warnings,
            force_context=force_context,
            review_mode="initial",
        )
        _persist_run(payload, update_latest=True)
        _sync_tasks(payload)
        _register_outcomes(payload, model_input)
        return payload
    except Exception as exc:
        completed_at = _now()
        failure = {
            "contract_version": REVIEW_CONTRACT_VERSION,
            "run_id": run_id,
            "status": "failed",
            "provider": PROVIDER_NAME,
            "model": model,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "elapsed_ms": round((completed_at - started_at).total_seconds() * 1000),
            "error": str(exc)[:1500],
        }
        _persist_run(failure, update_latest=False)
        raise


def generate_followup_review(*, parent_run_id: str | None = None) -> dict[str, Any]:
    from app.agent_review.tasks import task_evidence

    parent = load_latest_review()
    if not parent:
        raise ValueError("尚未生成初始复盘")
    if parent_run_id and parent.get("run_id") != parent_run_id:
        raise ValueError("指定复盘不是当前最新版本，请刷新页面后重试")
    parent_run_id = str(parent["run_id"])
    evidence = task_evidence(origin_run_id=parent_run_id)
    if not evidence:
        raise ValueError("尚无已完成的自动核查结果")

    started_at = _now()
    run_id = f"daily-{started_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    model = _model_name()
    try:
        context = build_daily_review_context(force=False)
        model_input = build_review_model_input(context)
        model_input["task"] = (
            "根据初始复盘和新增工具证据更新今日复盘。只更新被新证据影响的判断，"
            "未被验证的结论继续保持观察状态。"
        )
        model_input["parent_review"] = {
            "run_id": parent_run_id,
            "headline": parent.get("review", {}).get("headline"),
            "opportunities": parent.get("review", {}).get("opportunities", []),
            "risks": parent.get("review", {}).get("risks", []),
            "watch_items": parent.get("review", {}).get("watch_items", []),
        }
        model_input["evidence_catalog"].extend(evidence)
        review, usage, validation_warnings = _generate_with_correction(model_input)
        payload = _completed_payload(
            run_id=run_id,
            started_at=started_at,
            model=model,
            context=context,
            model_input=model_input,
            review=review,
            usage=usage,
            validation_warnings=validation_warnings,
            force_context=False,
            review_mode="verification_followup",
            parent_run_id=parent_run_id,
            tool_evidence_count=len(evidence),
        )
        _persist_run(payload, update_latest=True)
        _sync_tasks(payload)
        _register_outcomes(payload, model_input)
        return payload
    except Exception as exc:
        completed_at = _now()
        failure = {
            "contract_version": REVIEW_CONTRACT_VERSION,
            "run_id": run_id,
            "status": "failed",
            "review_mode": "verification_followup",
            "parent_run_id": parent_run_id,
            "provider": PROVIDER_NAME,
            "model": model,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "elapsed_ms": round((completed_at - started_at).total_seconds() * 1000),
            "error": str(exc)[:1500],
        }
        _persist_run(failure, update_latest=False)
        raise


def load_latest_review() -> dict[str, Any] | None:
    return _read_json(LATEST_PATH)


def list_review_history(limit: int = 10) -> list[dict[str, Any]]:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for path in sorted(REVIEW_DIR.glob("daily-*.json"), reverse=True):
        payload = _read_json(path)
        if not payload:
            continue
        items.append({
            key: payload.get(key)
            for key in (
                "run_id",
                "status",
                "review_mode",
                "parent_run_id",
                "provider",
                "model",
                "started_at",
                "completed_at",
                "elapsed_ms",
                "usage",
                "context",
                "validation_warnings",
                "error",
            )
        })
        if len(items) >= max(1, min(limit, 50)):
            break
    return items


def get_agent_review_status() -> dict[str, Any]:
    _load_env()
    latest = load_latest_review()
    return {
        "enabled": bool(os.getenv("LLM_API_KEY") and os.getenv("LLM_BASE_URL")),
        "provider": PROVIDER_NAME,
        "model": _model_name(),
        "max_tokens": int(os.getenv("AGENT_REVIEW_MAX_TOKENS", "2500")),
        "timeout_seconds": float(os.getenv("AGENT_REVIEW_TIMEOUT_SECONDS", "180")),
        "latest_run_id": latest.get("run_id") if latest else None,
        "latest_completed_at": latest.get("completed_at") if latest else None,
        "latest_status": latest.get("status") if latest else None,
        "privacy_boundary": (
            "账户与轮动上下文仅在用户主动生成复盘，或明确启用自动任务循环后，"
            "发送至已配置的火山引擎模型；"
            "不会自动执行交易或调仓。"
        ),
    }
