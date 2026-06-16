"""Durable improvement register from private outcome eval traces.

The AP learning loop already produces candidate improvements. This module turns
those candidates into a normalized register so the product can answer:
what did the trace teach us, is it still open, and what runtime path owns it?
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from solden.core.database import SoldenDB, get_db
from solden.core.org_utils import assert_org_id
from solden.services.agent_memory import AgentMemoryService


IMPROVEMENT_REGISTER_CONTRACT = "solden_agent_improvement_register.v1"
IMPROVEMENT_REGISTER_SNAPSHOT_TYPE = "agent_improvement_register"
IMPROVEMENT_REGISTER_PATTERN_TYPE = "agent_improvement_register_item"
_DEFAULT_SKILL_ID = "ap_v1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metric_direction(metric_name: str) -> str:
    token = _text(metric_name).lower()
    if token.endswith("_share") or token.endswith("_rate_to_reduce"):
        return "lower_is_better"
    return "higher_is_better"


def _metric_status(metric: Dict[str, Any]) -> Dict[str, Any]:
    metric = metric if isinstance(metric, dict) else {}
    current = _number(metric.get("value"))
    target = _number(metric.get("target"))
    direction = _metric_direction(metric.get("name") or "")
    if current is None or target is None:
        return {
            "direction": direction,
            "target_met": False,
            "distance_to_target": None,
        }
    if direction == "lower_is_better":
        target_met = current <= target
        distance = max(0.0, current - target)
    else:
        target_met = current >= target
        distance = max(0.0, target - current)
    return {
        "direction": direction,
        "target_met": target_met,
        "distance_to_target": round(distance, 4),
    }


def _priority_rank(priority: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(_text(priority).lower(), 9)


def _status_for_candidate(candidate: Dict[str, Any]) -> str:
    metric_state = _metric_status(candidate.get("metric") or {})
    if metric_state.get("target_met"):
        return "resolved"
    if _text(candidate.get("priority")).lower() == "high":
        return "open"
    return "watching"


def _candidates_from_snapshot(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    payload = snapshot.get("payload") if isinstance(snapshot.get("payload"), dict) else snapshot
    payload = payload if isinstance(payload, dict) else {}
    company_learning = payload.get("company_learning")
    company_learning = company_learning if isinstance(company_learning, dict) else {}
    candidates = company_learning.get("agent_improvement_candidates")
    return [dict(row) for row in candidates or [] if isinstance(row, dict)]


def _candidates_from_patterns(
    agent_memory: AgentMemoryService,
    *,
    skill_id: str,
    limit: int,
) -> List[Dict[str, Any]]:
    rows = agent_memory.list_patterns(
        skill_id=skill_id,
        pattern_type="agent_improvement_candidate",
        limit=limit,
    )
    candidates: List[Dict[str, Any]] = []
    for row in rows:
        pattern = row.get("pattern") if isinstance(row, dict) else {}
        if not isinstance(pattern, dict):
            continue
        candidate = dict(pattern)
        candidate["_pattern_meta"] = {
            "confidence": row.get("confidence"),
            "usage_count": row.get("usage_count"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "last_seen_at": row.get("last_seen_at"),
        }
        candidates.append(candidate)
    return candidates


def _normalize_candidate(candidate: Dict[str, Any], *, index: int) -> Dict[str, Any]:
    key = _text(candidate.get("key")) or f"candidate_{index + 1}"
    metric = candidate.get("metric") if isinstance(candidate.get("metric"), dict) else {}
    evidence = candidate.get("evidence") if isinstance(candidate.get("evidence"), dict) else {}
    metric_state = _metric_status(metric)
    status = _status_for_candidate(candidate)
    pattern_meta = candidate.get("_pattern_meta")
    pattern_meta = pattern_meta if isinstance(pattern_meta, dict) else {}
    return {
        "id": f"air_{key}",
        "key": key,
        "title": candidate.get("title") or key.replace("_", " ").title(),
        "status": status,
        "priority": _text(candidate.get("priority")).lower() or "medium",
        "action_type": candidate.get("action_type"),
        "target_runtime_path": candidate.get("target_runtime_path"),
        "metric": {
            **metric,
            **metric_state,
        },
        "evidence": evidence,
        "rationale": candidate.get("rationale"),
        "source": candidate.get("source") or {},
        "confidence": candidate.get("confidence") if candidate.get("confidence") is not None else pattern_meta.get("confidence"),
        "pattern": {
            "usage_count": pattern_meta.get("usage_count"),
            "created_at": pattern_meta.get("created_at"),
            "updated_at": pattern_meta.get("updated_at"),
            "last_seen_at": pattern_meta.get("last_seen_at"),
        },
    }


def _summarize(items: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(items)
    open_rows = [row for row in rows if row.get("status") != "resolved"]
    high_open = [
        row for row in open_rows
        if _text(row.get("priority")).lower() == "high"
    ]
    next_item = open_rows[0] if open_rows else (rows[0] if rows else None)
    return {
        "total": len(rows),
        "open": len(open_rows),
        "resolved": sum(1 for row in rows if row.get("status") == "resolved"),
        "high_priority_open": len(high_open),
        "next_item_key": next_item.get("key") if isinstance(next_item, dict) else None,
        "next_item_title": next_item.get("title") if isinstance(next_item, dict) else None,
    }


def build_agent_improvement_register(
    organization_id: str,
    *,
    db: Optional[SoldenDB] = None,
    agent_memory: Optional[AgentMemoryService] = None,
    snapshot: Optional[Dict[str, Any]] = None,
    skill_id: str = _DEFAULT_SKILL_ID,
    limit: int = 10,
    persist: bool = False,
) -> Dict[str, Any]:
    """Build and optionally persist the improvement register for an org."""
    org_id = assert_org_id(organization_id, context="build_agent_improvement_register")
    runtime_db = db or get_db()
    memory = agent_memory or AgentMemoryService(org_id, db=runtime_db)
    resolved_skill_id = _text(skill_id) or _DEFAULT_SKILL_ID
    safe_limit = max(1, min(int(limit or 10), 50))

    candidates = _candidates_from_snapshot(snapshot or {})
    source_snapshot = snapshot or {}
    if not candidates:
        source_snapshot = memory.latest_eval_snapshot(
            skill_id=resolved_skill_id,
            scope="organization",
            snapshot_type="ap_private_outcome_eval",
        )
        candidates = _candidates_from_snapshot(source_snapshot)
    if not candidates:
        candidates = _candidates_from_patterns(
            memory,
            skill_id=resolved_skill_id,
            limit=safe_limit,
        )

    items = [
        _normalize_candidate(candidate, index=index)
        for index, candidate in enumerate(candidates[:safe_limit])
    ]
    items.sort(
        key=lambda row: (
            row.get("status") == "resolved",
            _priority_rank(row.get("priority") or ""),
            -int((row.get("evidence") or {}).get("failed_case_count") or 0),
            _text(row.get("key")),
        )
    )
    register = {
        "contract": IMPROVEMENT_REGISTER_CONTRACT,
        "snapshot_type": IMPROVEMENT_REGISTER_SNAPSHOT_TYPE,
        "organization_id": org_id,
        "skill_id": resolved_skill_id,
        "scope": "ap_source_to_pay",
        "generated_at": _now_iso(),
        "source": {
            "snapshot_type": (
                source_snapshot.get("snapshot_type")
                if isinstance(source_snapshot, dict)
                else None
            ),
            "created_at": (
                source_snapshot.get("created_at")
                if isinstance(source_snapshot, dict)
                else None
            ),
        },
        "summary": _summarize(items),
        "items": items,
    }
    if persist and items:
        memory.record_eval_snapshot(
            skill_id=resolved_skill_id,
            scope="organization",
            snapshot_type=IMPROVEMENT_REGISTER_SNAPSHOT_TYPE,
            payload=register,
        )
        for item in items:
            memory.record_pattern(
                skill_id=resolved_skill_id,
                pattern_type=IMPROVEMENT_REGISTER_PATTERN_TYPE,
                pattern_key=_text(item.get("key")),
                pattern=item,
                confidence=float(item.get("confidence") or 0.5),
            )
    return register
