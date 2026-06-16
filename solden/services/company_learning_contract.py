"""Organization-level learning contract.

Record-level operational memory says what happened to one piece of work.
The company-learning contract says what the organization is learning across
work: which workflow scope produced signal, which objective should improve
next, and whether the loop has enough evidence to claim compounding learning.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from solden.core.database import SoldenDB, get_db
from solden.core.org_utils import assert_org_id
from solden.services.agent_memory import AgentMemoryService


COMPANY_LEARNING_CONTRACT = "solden_company_learning_contract.v1"
COMPANY_LEARNING_CONTRACT_SNAPSHOT_TYPE = "company_learning_contract"
COMPANY_LEARNING_SCOPE_PATTERN_TYPE = "company_learning_scope"
COMPANY_LEARNING_OBJECTIVE_PATTERN_TYPE = "company_learning_objective"
DEFAULT_SKILL_ID = "ap_v1"
DEFAULT_WORKFLOW_SCOPE = "ap_source_to_pay"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _target_met(signal: Dict[str, Any]) -> bool:
    return _number(signal.get("value")) >= _number(signal.get("target"), 1.0)


def _latest_source_snapshot(
    memory: AgentMemoryService,
    *,
    skill_id: str,
) -> Dict[str, Any]:
    try:
        from solden.services.ap_learning_loop import (
            COMPANY_LEARNING_SNAPSHOT_TYPE,
            PRIVATE_OUTCOME_EVAL_TYPE,
        )
    except Exception:
        COMPANY_LEARNING_SNAPSHOT_TYPE = "company_learning_snapshot"
        PRIVATE_OUTCOME_EVAL_TYPE = "ap_private_outcome_eval"

    latest_private_eval = memory.latest_eval_snapshot(
        skill_id=skill_id,
        scope="organization",
        snapshot_type=PRIVATE_OUTCOME_EVAL_TYPE,
    )
    if latest_private_eval:
        payload = _safe_dict(latest_private_eval.get("payload"))
        payload["_snapshot_meta"] = {
            "snapshot_type": latest_private_eval.get("snapshot_type"),
            "created_at": latest_private_eval.get("created_at"),
        }
        return payload

    latest_profile = memory.latest_eval_snapshot(
        skill_id=skill_id,
        scope="organization",
        snapshot_type=COMPANY_LEARNING_SNAPSHOT_TYPE,
    )
    if latest_profile:
        payload = _safe_dict(latest_profile.get("payload"))
        payload["_snapshot_meta"] = {
            "snapshot_type": latest_profile.get("snapshot_type"),
            "created_at": latest_profile.get("created_at"),
        }
        return payload
    return {}


def _profile_from_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    if not snapshot:
        return {}
    snapshot_type = _text(snapshot.get("snapshot_type"))
    if snapshot_type == "company_learning_snapshot":
        return snapshot
    company_learning = _safe_dict(snapshot.get("company_learning"))
    profile = _safe_dict(company_learning.get("company_memory_profile"))
    if profile:
        return profile
    return snapshot if snapshot.get("maturity") else {}


def _build_signal_chain(
    *,
    snapshot: Dict[str, Any],
    profile: Dict[str, Any],
    improvement_register: Dict[str, Any],
    next_objective: Dict[str, Any],
) -> list[Dict[str, Any]]:
    summary = _safe_dict(snapshot.get("summary"))
    sample = _safe_dict(profile.get("sample"))
    register_summary = _safe_dict(improvement_register.get("summary"))
    return [
        {
            "key": "record_level_memory",
            "status": (
                "observed"
                if _number(summary.get("memory_event_coverage_rate")) > 0
                else "missing"
            ),
            "evidence": {
                "memory_event_coverage_rate": summary.get("memory_event_coverage_rate"),
                "sample_size": sample.get("total_items") or summary.get("total_items"),
            },
        },
        {
            "key": "private_outcome_eval",
            "status": "observed" if snapshot else "missing",
            "evidence": {
                "snapshot_type": snapshot.get("snapshot_type"),
                "generated_at": snapshot.get("generated_at"),
            },
        },
        {
            "key": "company_profile",
            "status": "observed" if profile else "missing",
            "evidence": {
                "maturity_level": _safe_dict(profile.get("maturity")).get("level"),
                "maturity_score": _safe_dict(profile.get("maturity")).get("score"),
            },
        },
        {
            "key": "improvement_register",
            "status": (
                "observed"
                if _text(improvement_register.get("contract"))
                else "missing"
            ),
            "evidence": {
                "open": register_summary.get("open"),
                "high_priority_open": register_summary.get("high_priority_open"),
            },
        },
        {
            "key": "runtime_learning_objective",
            "status": "observed" if _text(next_objective.get("key")) else "missing",
            "evidence": {
                "key": next_objective.get("key"),
                "target_runtime_path": next_objective.get("target_runtime_path"),
            },
        },
    ]


def _scope_row(
    *,
    snapshot: Dict[str, Any],
    profile: Dict[str, Any],
    improvement_register: Dict[str, Any],
) -> Dict[str, Any]:
    maturity = _safe_dict(profile.get("maturity"))
    signals = [
        {
            **dict(signal),
            "target_met": _target_met(signal),
        }
        for signal in _safe_list(maturity.get("signals"))
        if isinstance(signal, dict)
    ]
    sample = _safe_dict(profile.get("sample"))
    next_objective = _safe_dict(profile.get("next_learning_objective"))
    signal_chain = _build_signal_chain(
        snapshot=snapshot,
        profile=profile,
        improvement_register=improvement_register,
        next_objective=next_objective,
    )
    chain_complete = all(row.get("status") == "observed" for row in signal_chain)
    maturity_level = _text(maturity.get("level")) or "no_signal"
    sample_size = int(sample.get("total_items") or _safe_dict(snapshot.get("summary")).get("total_items") or 0)
    open_objectives = int(_safe_dict(improvement_register.get("summary")).get("open") or 0)
    high_priority_open = int(_safe_dict(improvement_register.get("summary")).get("high_priority_open") or 0)
    ready_for_scope_claim = bool(
        sample_size > 0
        and maturity_level in {"forming", "compounding"}
        and chain_complete
    )
    return {
        "scope": _text(profile.get("scope")) or _text(snapshot.get("scope")) or DEFAULT_WORKFLOW_SCOPE,
        "status": maturity_level,
        "ready_for_scope_claim": ready_for_scope_claim,
        "maturity": {
            "level": maturity_level,
            "score": maturity.get("score"),
            "signals": signals,
        },
        "sample": sample,
        "headline": profile.get("headline"),
        "learned_strengths": _safe_list(profile.get("learned_strengths")),
        "learning_gaps": _safe_list(profile.get("learning_gaps")),
        "operating_patterns": _safe_dict(profile.get("operating_patterns")),
        "next_learning_objective": next_objective,
        "signal_chain": signal_chain,
        "open_learning_objectives": open_objectives,
        "high_priority_open_objectives": high_priority_open,
        "evidence": {
            **_safe_dict(profile.get("evidence")),
            "source_snapshot_type": (
                snapshot.get("snapshot_type")
                or _safe_dict(snapshot.get("_snapshot_meta")).get("snapshot_type")
            ),
            "source_created_at": _safe_dict(snapshot.get("_snapshot_meta")).get("created_at"),
            "improvement_register_contract": improvement_register.get("contract"),
        },
        "confidence": profile.get("confidence"),
    }


def _summary_from_scope(scope: Dict[str, Any]) -> Dict[str, Any]:
    status = _text(scope.get("status")) or "no_signal"
    with_signal = bool(int(_safe_dict(scope.get("sample")).get("total_items") or 0) > 0)
    ready_for_scope_claim = bool(scope.get("ready_for_scope_claim"))
    next_objective = _safe_dict(scope.get("next_learning_objective"))
    high_priority_open = int(scope.get("high_priority_open_objectives") or 0)
    open_objectives = int(scope.get("open_learning_objectives") or 0)
    if not with_signal:
        organization_status = "no_signal"
    elif status == "compounding" and high_priority_open == 0:
        organization_status = "compounding"
    elif status in {"forming", "compounding"}:
        organization_status = "forming"
    else:
        organization_status = "instrumenting"

    return {
        "organization_learning_status": organization_status,
        "workflow_scopes_total": 1,
        "workflow_scopes_with_signal": 1 if with_signal else 0,
        "compounding_scopes": 1 if status == "compounding" else 0,
        "forming_scopes": 1 if status == "forming" else 0,
        "instrumenting_scopes": 1 if status == "instrumenting" else 0,
        "open_learning_objectives": open_objectives,
        "high_priority_open_objectives": high_priority_open,
        "next_learning_objective_key": next_objective.get("key"),
        "next_learning_objective_title": next_objective.get("title"),
        "ready_for_company_learning_claim": ready_for_scope_claim,
        "workflow_coverage_status": "ap_wedge_only",
    }


def build_company_learning_contract(
    organization_id: str,
    *,
    db: Optional[SoldenDB] = None,
    agent_memory: Optional[AgentMemoryService] = None,
    snapshot: Optional[Dict[str, Any]] = None,
    improvement_register: Optional[Dict[str, Any]] = None,
    skill_id: str = DEFAULT_SKILL_ID,
    persist: bool = False,
) -> Dict[str, Any]:
    """Build and optionally persist Solden's org-level learning contract."""
    org_id = assert_org_id(organization_id, context="build_company_learning_contract")
    runtime_db = db or get_db()
    memory = agent_memory or AgentMemoryService(org_id, db=runtime_db)
    resolved_skill_id = _text(skill_id) or DEFAULT_SKILL_ID
    source_snapshot = snapshot if isinstance(snapshot, dict) else _latest_source_snapshot(
        memory,
        skill_id=resolved_skill_id,
    )
    profile = _profile_from_snapshot(source_snapshot)

    if improvement_register is None:
        try:
            from solden.services.agent_improvement_register import (
                build_agent_improvement_register,
            )

            improvement_register = build_agent_improvement_register(
                org_id,
                db=runtime_db,
                agent_memory=memory,
                snapshot=source_snapshot,
                skill_id=resolved_skill_id,
                persist=False,
            )
        except Exception:
            improvement_register = {}
    improvement_register = _safe_dict(improvement_register)

    scope = _scope_row(
        snapshot=source_snapshot,
        profile=profile,
        improvement_register=improvement_register,
    )
    contract = {
        "contract": COMPANY_LEARNING_CONTRACT,
        "snapshot_type": COMPANY_LEARNING_CONTRACT_SNAPSHOT_TYPE,
        "organization_id": org_id,
        "skill_id": resolved_skill_id,
        "scope": "organization",
        "generated_at": _now_iso(),
        "summary": _summary_from_scope(scope),
        "workflow_coverage": {
            "status": "ap_wedge_only",
            "covered_scopes": [scope.get("scope") or DEFAULT_WORKFLOW_SCOPE],
            "claim_boundary": (
                "Company-level learning is currently proven for the AP/source-to-pay "
                "wedge, not every back-office workflow."
            ),
        },
        "scopes": [scope],
        "improvement_register_summary": _safe_dict(improvement_register.get("summary")),
        "next_learning_objective": scope.get("next_learning_objective") or {},
    }

    if persist:
        memory.record_eval_snapshot(
            skill_id=resolved_skill_id,
            scope="organization",
            snapshot_type=COMPANY_LEARNING_CONTRACT_SNAPSHOT_TYPE,
            payload=contract,
        )
        memory.record_pattern(
            skill_id=resolved_skill_id,
            pattern_type=COMPANY_LEARNING_SCOPE_PATTERN_TYPE,
            pattern_key=_text(scope.get("scope")) or DEFAULT_WORKFLOW_SCOPE,
            pattern=scope,
            confidence=_number(scope.get("confidence"), 0.5),
        )
        objective = _safe_dict(scope.get("next_learning_objective"))
        if _text(objective.get("key")):
            memory.record_pattern(
                skill_id=resolved_skill_id,
                pattern_type=COMPANY_LEARNING_OBJECTIVE_PATTERN_TYPE,
                pattern_key=_text(objective.get("key")),
                pattern=objective,
                confidence=_number(scope.get("confidence"), 0.5),
            )

    return contract
