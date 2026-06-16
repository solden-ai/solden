"""Operational health for scheduled company-learning evals."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from solden.core.database import SoldenDB, get_db
from solden.core.org_utils import assert_org_id
from solden.services.agent_memory import AgentMemoryService
from solden.services.agent_improvement_register import IMPROVEMENT_REGISTER_SNAPSHOT_TYPE
from solden.services.ap_learning_loop import PRIVATE_OUTCOME_EVAL_TYPE
from solden.services.company_learning_contract import (
    COMPANY_LEARNING_CONTRACT_SNAPSHOT_TYPE,
)


LEARNING_LOOP_HEALTH_CONTRACT = "solden_learning_loop_health.v1"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> Optional[datetime]:
    token = str(value or "").strip()
    if not token:
        return None
    try:
        parsed = datetime.fromisoformat(token.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _snapshot_health(snapshot: Dict[str, Any], *, now: datetime, max_age_hours: int) -> Dict[str, Any]:
    created_at = _parse_dt(snapshot.get("created_at"))
    age_hours = None
    fresh = False
    if created_at:
        age_hours = round((now - created_at).total_seconds() / 3600, 2)
        fresh = created_at >= now - timedelta(hours=max(1, int(max_age_hours or 36)))
    return {
        "observed": bool(snapshot),
        "snapshot_type": snapshot.get("snapshot_type"),
        "created_at": snapshot.get("created_at"),
        "age_hours": age_hours,
        "fresh": fresh,
    }


def _pending_policy_proposals(
    db: SoldenDB,
    organization_id: str,
    *,
    limit: int = 25,
) -> Dict[str, Any]:
    if not hasattr(db, "list_policy_proposals"):
        return {"available": False, "count": 0, "proposals": []}
    try:
        proposals = db.list_policy_proposals(
            organization_id=organization_id,
            status="pending",
            limit=limit,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "count": 0,
            "proposals": [],
            "error": str(exc),
        }
    compact = []
    for proposal in proposals[:limit]:
        if not isinstance(proposal, dict):
            continue
        evidence = proposal.get("evidence") if isinstance(proposal.get("evidence"), dict) else {}
        compact.append(
            {
                "id": proposal.get("id"),
                "proposal_kind": proposal.get("proposal_kind"),
                "vendor_name": proposal.get("vendor_name"),
                "created_at": proposal.get("created_at"),
                "has_learning_citation": bool(evidence.get("learning_citation")),
            }
        )
    return {
        "available": True,
        "count": len(compact),
        "proposals": compact,
    }


def build_learning_loop_health(
    organization_id: str,
    *,
    db: Optional[SoldenDB] = None,
    agent_memory: Optional[AgentMemoryService] = None,
    max_age_hours: int = 36,
) -> Dict[str, Any]:
    """Return freshness and completeness of the scheduled learning loop."""
    org_id = assert_org_id(organization_id, context="build_learning_loop_health")
    runtime_db = db or get_db()
    memory = agent_memory or AgentMemoryService(org_id, db=runtime_db)
    now = _now()

    private_eval = memory.latest_eval_snapshot(
        skill_id="ap_v1",
        scope="organization",
        snapshot_type=PRIVATE_OUTCOME_EVAL_TYPE,
    )
    improvement_register = memory.latest_eval_snapshot(
        skill_id="ap_v1",
        scope="organization",
        snapshot_type=IMPROVEMENT_REGISTER_SNAPSHOT_TYPE,
    )
    company_contract = memory.latest_eval_snapshot(
        skill_id="ap_v1",
        scope="organization",
        snapshot_type=COMPANY_LEARNING_CONTRACT_SNAPSHOT_TYPE,
    )

    private_eval_health = _snapshot_health(
        private_eval,
        now=now,
        max_age_hours=max_age_hours,
    )
    improvement_health = _snapshot_health(
        improvement_register,
        now=now,
        max_age_hours=max_age_hours,
    )
    company_contract_health = _snapshot_health(
        company_contract,
        now=now,
        max_age_hours=max_age_hours,
    )
    components = {
        "private_eval": private_eval_health,
        "improvement_register": improvement_health,
        "company_learning_contract": company_contract_health,
    }
    observed_count = sum(1 for row in components.values() if row.get("observed"))
    fresh_count = sum(1 for row in components.values() if row.get("fresh"))

    company_payload = company_contract.get("payload")
    company_payload = company_payload if isinstance(company_payload, dict) else {}
    company_summary = company_payload.get("summary")
    company_summary = company_summary if isinstance(company_summary, dict) else {}
    private_payload = private_eval.get("payload")
    private_payload = private_payload if isinstance(private_payload, dict) else {}
    release_gate = private_payload.get("release_gate")
    release_gate = release_gate if isinstance(release_gate, dict) else {}
    pending_policy_proposals = _pending_policy_proposals(runtime_db, org_id)

    if observed_count == 0:
        status = "no_signal"
    elif fresh_count < len(components):
        status = "stale"
    elif release_gate.get("status") == "pass":
        status = "healthy"
    else:
        status = "needs_work"

    return {
        "contract": LEARNING_LOOP_HEALTH_CONTRACT,
        "organization_id": org_id,
        "generated_at": now.isoformat(),
        "status": status,
        "max_age_hours": max(1, int(max_age_hours or 36)),
        "components": components,
        "summary": {
            "observed_components": observed_count,
            "fresh_components": fresh_count,
            "release_gate": release_gate.get("status"),
            "company_learning_status": company_summary.get("organization_learning_status"),
            "ready_for_company_learning_claim": company_summary.get("ready_for_company_learning_claim"),
            "next_learning_objective": company_summary.get("next_learning_objective_title"),
            "workflow_coverage_status": company_summary.get("workflow_coverage_status"),
            "pending_policy_proposals": pending_policy_proposals.get("count", 0),
            "pending_policy_proposals_available": pending_policy_proposals.get("available", False),
        },
        "pending_policy_proposals": pending_policy_proposals,
    }
