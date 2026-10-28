from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[2]
POLICY_DIR = BACKEND_DIR / "data" / "agent_learning"
POLICY_PATH = POLICY_DIR / "policies.json"

REASON_RULES = {
    "risk_omission": {
        "title": "重复出现风险遗漏",
        "trigger": "同类结果中风险遗漏达到样本门槛且失败占比较高",
        "adjustment": "相关判断必须补充反证和下行情景；证据不足时降低置信度并生成核查任务。",
    },
    "timing_or_threshold": {
        "title": "方向可能正确但时点或阈值不稳定",
        "trigger": "多次结果被归因为时点或阈值问题",
        "adjustment": "把行动语义改为等待可验证触发条件，不把方向判断直接转换为操作倾向。",
    },
    "signal_not_realized": {
        "title": "信号缺少后续兑现",
        "trigger": "多次信号在评价窗口内未形成有效跟随",
        "adjustment": "要求趋势、量能或基本面至少一项形成后续确认，否则维持观察。",
    },
    "direction_judgment": {
        "title": "方向判断存在重复偏差",
        "trigger": "方向相关结果多次不被后续市场支持",
        "adjustment": "降低同类方向判断的先验权重，并优先寻找相反证据。",
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read() -> dict[str, Any]:
    if not POLICY_PATH.exists():
        return {"contract_version": "learning_policy_registry.v1", "policies": []}
    try:
        payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"contract_version": "learning_policy_registry.v1", "policies": []}
    return payload if isinstance(payload, dict) else {"contract_version": "learning_policy_registry.v1", "policies": []}


def _write(payload: dict[str, Any]) -> None:
    POLICY_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = POLICY_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(POLICY_PATH)


def _upsert_policy(
    existing: dict[str, dict[str, Any]],
    *,
    policy_id: str,
    title: str,
    trigger: str,
    adjustment: str,
    sample_count: int,
    adverse_count: int,
    evidence_refs: list[str],
    activation_threshold: int = 3,
) -> dict[str, Any]:
    previous = existing.get(policy_id)
    adverse_rate = round(adverse_count / sample_count * 100, 1) if sample_count else 0.0
    status = "active" if sample_count >= activation_threshold and adverse_rate >= 60 else "monitoring"
    confidence = "high" if sample_count >= 8 else "medium" if sample_count >= activation_threshold else "low"
    state = {
        "status": status,
        "sample_count": sample_count,
        "adverse_count": adverse_count,
        "adverse_rate_pct": adverse_rate,
        "confidence": confidence,
        "adjustment": adjustment,
    }
    previous_state = {
        key: previous.get(key)
        for key in state
    } if previous else None
    changed = previous_state != state
    version = int(previous.get("version") or 0) + 1 if previous and changed else int(previous.get("version") or 1) if previous else 1
    history = list(previous.get("history") or []) if previous else []
    if changed:
        history.append({"version": version, "changed_at": _now_iso(), **state})
    return {
        "policy_id": policy_id,
        "version": version,
        "status": status,
        "title": title,
        "trigger": trigger,
        "adjustment": adjustment,
        "sample_count": sample_count,
        "adverse_count": adverse_count,
        "adverse_rate_pct": adverse_rate,
        "confidence": confidence,
        "evidence_refs": evidence_refs[-10:],
        "created_at": previous.get("created_at") if previous else _now_iso(),
        "updated_at": _now_iso() if changed else previous.get("updated_at") if previous else _now_iso(),
        "history": history[-20:],
    }


def refresh_learning_policies(loop_state: dict[str, Any]) -> dict[str, Any]:
    registry = _read()
    existing = {
        str(item.get("policy_id")): item
        for item in registry.get("policies", [])
        if item.get("policy_id")
    }
    evaluated = []
    for item in [*loop_state.get("recommendations", []), *loop_state.get("portfolio_actions", [])]:
        outcome = item.get("outcome") or {}
        if outcome.get("verdict") and outcome.get("causal_verification") == "verified":
            evaluated.append((item, outcome))

    policies = []
    for category, rule in REASON_RULES.items():
        matching = [
            (item, outcome)
            for item, outcome in evaluated
            if category in (outcome.get("reason_categories") or [])
        ]
        if not matching:
            continue
        adverse = sum(1 for _, outcome in matching if outcome.get("verdict") == "not_supported")
        refs = [
            str(item.get("action_id") or item.get("recommendation_id") or "")
            for item, _ in matching
        ]
        policies.append(_upsert_policy(
            existing,
            policy_id=f"outcome:{category}",
            title=rule["title"],
            trigger=rule["trigger"],
            adjustment=rule["adjustment"],
            sample_count=len(matching),
            adverse_count=adverse,
            evidence_refs=refs,
        ))

    confirmed_actions = [
        item for item in loop_state.get("portfolio_actions", [])
        if item.get("learning_eligible")
    ]
    missing_reason = [item for item in confirmed_actions if not item.get("user_reason")]
    if confirmed_actions:
        policies.append(_upsert_policy(
            existing,
            policy_id="process:missing_trade_reason",
            title="交易理由记录缺失",
            trigger="已确认操作中存在较高比例的理由缺失",
            adjustment="理由缺失的操作只能进入低置信度学习样本；后续上传确认时优先提示补充触发条件与失效条件。",
            sample_count=len(confirmed_actions),
            adverse_count=len(missing_reason),
            evidence_refs=[str(item.get("action_id") or "") for item in missing_reason],
        ))

    weekly = loop_state.get("weekly_operations") or {}
    reversal_items = [item for item in weekly.get("items", []) if int(item.get("reversal_count") or 0) >= 2]
    if weekly.get("symbol_count"):
        policies.append(_upsert_policy(
            existing,
            policy_id="process:weekly_direction_reversal",
            title="周内方向反转偏多",
            trigger="五交易日内多个标的出现两次及以上买卖方向反转",
            adjustment="周内反向操作需要明确新证据或风险约束；缺少理由时在复盘中列为纪律问题。",
            sample_count=int(weekly.get("symbol_count") or 0),
            adverse_count=len(reversal_items),
            evidence_refs=[str(item.get("evidence_ref") or "") for item in reversal_items],
            activation_threshold=2,
        ))

    payload = {
        "contract_version": "learning_policy_registry.v1",
        "generated_at": _now_iso(),
        "policies": sorted(policies, key=lambda item: (item["status"] != "active", item["policy_id"])),
        "summary": {
            "policy_count": len(policies),
            "active_count": sum(1 for item in policies if item["status"] == "active"),
            "monitoring_count": sum(1 for item in policies if item["status"] == "monitoring"),
        },
        "boundary": "策略规则由确定性样本门槛生成；模型只能读取和解释，不能自行激活或修改规则。",
    }
    _write(payload)
    return payload


def learning_policy_snapshot() -> dict[str, Any]:
    return _read()
