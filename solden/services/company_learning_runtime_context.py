"""Runtime context from company-learning artifacts.

This is the small, read-only bridge between the learning loop and runtime
surfaces. It does not decide policy or mutate work. It packages the latest
company-learning contract, improvement register, and human-reviewable policy
proposals into a bounded context that callers can cite or display.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from solden.core.database import SoldenDB, get_db
from solden.core.org_utils import assert_org_id
from solden.services.agent_improvement_register import IMPROVEMENT_REGISTER_SNAPSHOT_TYPE
from solden.services.agent_memory import AgentMemoryService
from solden.services.company_learning_contract import (
    COMPANY_LEARNING_CONTRACT_SNAPSHOT_TYPE,
)
from solden.services.learning_loop_health import build_learning_loop_health


COMPANY_LEARNING_RUNTIME_CONTEXT = "solden_company_learning_runtime_context.v1"
COMPANY_LEARNING_MEMORY_CONTEXT = "solden_company_learning_memory_context.v1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _latest_payload(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    payload = snapshot.get("payload") if isinstance(snapshot, dict) else {}
    return payload if isinstance(payload, dict) else {}


def _compact_objectives(register: Dict[str, Any], *, limit: int = 5) -> List[Dict[str, Any]]:
    items = register.get("items") if isinstance(register.get("items"), list) else []
    compact: List[Dict[str, Any]] = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        metric = _safe_dict(item.get("metric"))
        evidence = _safe_dict(item.get("evidence"))
        compact.append(
            {
                "key": item.get("key"),
                "title": item.get("title"),
                "status": item.get("status"),
                "priority": item.get("priority"),
                "action_type": item.get("action_type"),
                "target_runtime_path": item.get("target_runtime_path"),
                "metric": {
                    "name": metric.get("name"),
                    "value": metric.get("value"),
                    "target": metric.get("target"),
                    "target_met": metric.get("target_met"),
                },
                "evidence": {
                    "sample_size": evidence.get("sample_size"),
                    "failed_case_count": evidence.get("failed_case_count"),
                    "blocker_count": evidence.get("blocker_count"),
                },
            }
        )
    return compact


def _compact_policy_proposals(
    db: SoldenDB,
    organization_id: str,
    *,
    vendor_name: Optional[str],
    include: bool,
    limit: int = 10,
) -> Dict[str, Any]:
    if not include:
        return {"available": False, "count": 0, "proposals": []}
    if not hasattr(db, "list_policy_proposals"):
        return {"available": False, "count": 0, "proposals": []}
    try:
        proposals = db.list_policy_proposals(
            organization_id=organization_id,
            status="pending",
            limit=limit,
        )
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "count": 0, "proposals": [], "error": str(exc)}

    vendor_token = _text(vendor_name).casefold()
    compact: List[Dict[str, Any]] = []
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        proposal_vendor = _text(proposal.get("vendor_name"))
        if vendor_token and proposal_vendor.casefold() != vendor_token:
            continue
        evidence = _safe_dict(proposal.get("evidence"))
        compact.append(
            {
                "id": proposal.get("id"),
                "proposal_kind": proposal.get("proposal_kind"),
                "vendor_name": proposal.get("vendor_name"),
                "behavior_summary": proposal.get("behavior_summary"),
                "created_at": proposal.get("created_at"),
                "has_learning_citation": bool(evidence.get("learning_citation")),
            }
        )
        if len(compact) >= limit:
            break
    return {"available": True, "count": len(compact), "proposals": compact}


def _runtime_guidance(
    *,
    company_summary: Dict[str, Any],
    register_summary: Dict[str, Any],
    proposals: Dict[str, Any],
) -> List[str]:
    guidance: List[str] = []
    objective = _text(company_summary.get("next_learning_objective_title"))
    if objective:
        guidance.append(f"Current learning objective: {objective}.")
    open_count = int(register_summary.get("open") or 0)
    high_count = int(register_summary.get("high_priority_open") or 0)
    if open_count:
        if high_count:
            guidance.append(
                f"{open_count} open improvement objective(s), including {high_count} high-priority."
            )
        else:
            guidance.append(f"{open_count} open improvement objective(s).")
    proposal_count = int(proposals.get("count") or 0)
    if proposal_count:
        guidance.append(f"{proposal_count} learned policy proposal(s) await human review.")
    return guidance


def build_company_learning_runtime_context(
    organization_id: str,
    *,
    db: Optional[SoldenDB] = None,
    agent_memory: Optional[AgentMemoryService] = None,
    vendor_name: Optional[str] = None,
    include_policy_proposals: bool = True,
    max_age_hours: int = 36,
) -> Dict[str, Any]:
    """Return bounded company-learning context suitable for runtime use."""
    org_id = assert_org_id(organization_id, context="build_company_learning_runtime_context")
    runtime_db = db or get_db()
    memory = agent_memory or AgentMemoryService(org_id, db=runtime_db)

    health = build_learning_loop_health(
        org_id,
        db=runtime_db,
        agent_memory=memory,
        max_age_hours=max_age_hours,
    )
    improvement_snapshot = memory.latest_eval_snapshot(
        skill_id="ap_v1",
        scope="organization",
        snapshot_type=IMPROVEMENT_REGISTER_SNAPSHOT_TYPE,
    )
    company_snapshot = memory.latest_eval_snapshot(
        skill_id="ap_v1",
        scope="organization",
        snapshot_type=COMPANY_LEARNING_CONTRACT_SNAPSHOT_TYPE,
    )

    improvement_register = _latest_payload(improvement_snapshot)
    company_contract = _latest_payload(company_snapshot)
    company_summary = _safe_dict(company_contract.get("summary"))
    register_summary = _safe_dict(improvement_register.get("summary"))
    proposals = _compact_policy_proposals(
        runtime_db,
        org_id,
        vendor_name=vendor_name,
        include=include_policy_proposals,
    )
    components = _safe_dict(health.get("components"))
    company_component = _safe_dict(components.get("company_learning_contract"))
    improvement_component = _safe_dict(components.get("improvement_register"))
    private_component = _safe_dict(components.get("private_eval"))
    health_status = _text(health.get("status")) or "no_signal"
    usable = bool(
        health_status in {"healthy", "needs_work"}
        and company_component.get("fresh")
        and improvement_component.get("fresh")
        and private_component.get("fresh")
        and company_contract
    )
    status = "available" if usable else health_status
    objectives = _compact_objectives(improvement_register)
    guidance = _runtime_guidance(
        company_summary=company_summary,
        register_summary=register_summary,
        proposals=proposals,
    )

    return {
        "contract": COMPANY_LEARNING_RUNTIME_CONTEXT,
        "organization_id": org_id,
        "generated_at": _now_iso(),
        "status": status,
        "usable": usable,
        "vendor_name": vendor_name,
        "health": {
            "status": health_status,
            "max_age_hours": health.get("max_age_hours"),
            "components": components,
        },
        "summary": {
            "company_learning_status": company_summary.get("organization_learning_status"),
            "ready_for_company_learning_claim": company_summary.get("ready_for_company_learning_claim"),
            "workflow_coverage_status": company_summary.get("workflow_coverage_status"),
            "next_learning_objective": company_summary.get("next_learning_objective_title"),
            "open_improvement_objectives": register_summary.get("open"),
            "high_priority_open_objectives": register_summary.get("high_priority_open"),
            "pending_policy_proposals": proposals.get("count", 0),
        },
        "runtime_guidance": guidance,
        "improvement_objectives": objectives,
        "pending_policy_proposals": proposals,
        "citations": [
            {
                "type": "private_eval",
                "snapshot_type": private_component.get("snapshot_type"),
                "created_at": private_component.get("created_at"),
            },
            {
                "type": "improvement_register",
                "snapshot_type": improvement_component.get("snapshot_type"),
                "created_at": improvement_component.get("created_at"),
            },
            {
                "type": "company_learning_contract",
                "snapshot_type": company_component.get("snapshot_type"),
                "created_at": company_component.get("created_at"),
            },
        ],
    }


def compact_company_learning_context_for_memory(
    context: Dict[str, Any],
    *,
    guidance_limit: int = 3,
    objective_limit: int = 3,
    citation_limit: int = 3,
) -> Optional[Dict[str, Any]]:
    """Compact runtime-learning context for embedding inside memory evidence."""
    if not isinstance(context, dict) or not context.get("usable"):
        return None
    summary = _safe_dict(context.get("summary"))
    guidance = context.get("runtime_guidance") if isinstance(context.get("runtime_guidance"), list) else []
    objectives = (
        context.get("improvement_objectives")
        if isinstance(context.get("improvement_objectives"), list)
        else []
    )
    citations = context.get("citations") if isinstance(context.get("citations"), list) else []
    return {
        "contract": COMPANY_LEARNING_MEMORY_CONTEXT,
        "status": context.get("status"),
        "source_contract": context.get("contract"),
        "summary": {
            "company_learning_status": summary.get("company_learning_status"),
            "ready_for_company_learning_claim": summary.get("ready_for_company_learning_claim"),
            "workflow_coverage_status": summary.get("workflow_coverage_status"),
            "next_learning_objective": summary.get("next_learning_objective"),
            "open_improvement_objectives": summary.get("open_improvement_objectives"),
            "high_priority_open_objectives": summary.get("high_priority_open_objectives"),
        },
        "runtime_guidance": guidance[: max(0, int(guidance_limit or 0))],
        "improvement_objectives": objectives[: max(0, int(objective_limit or 0))],
        "citations": citations[: max(0, int(citation_limit or 0))],
    }


def build_company_learning_memory_context(
    organization_id: str,
    *,
    db: Optional[SoldenDB] = None,
    agent_memory: Optional[AgentMemoryService] = None,
    vendor_name: Optional[str] = None,
    max_age_hours: int = 36,
) -> Optional[Dict[str, Any]]:
    """Return a compact, non-authoritative learning context for memory events.

    This intentionally excludes pending policy proposals. Memory rows may be
    visible on many surfaces, while proposal review is role-gated elsewhere.
    """
    context = build_company_learning_runtime_context(
        organization_id,
        db=db,
        agent_memory=agent_memory,
        vendor_name=vendor_name,
        include_policy_proposals=False,
        max_age_hours=max_age_hours,
    )
    return compact_company_learning_context_for_memory(context)
