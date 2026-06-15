"""Policy-proposal review API (tribal-knowledge Build 3).

Lists the agent's behavior-derived standing-rule proposals and lets a human
accept (lands the BOUNDED rule via the existing rules table, versioned through
rule_versions — identical semantics to a manually created rule) or decline
(records the deliberate non-rule with its REQUIRED reason; never re-proposed).
Tenant-scoped: cross-org ids 404, no existence leak.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from solden.core.auth import get_current_user, require_workspace_admin
from solden.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workspace", tags=["policy-proposals"])


def _session_org(user: Any) -> str:
    org = str(getattr(user, "organization_id", "") or "").strip()
    if not org:
        raise HTTPException(status_code=403, detail="user_missing_organization_id")
    return org


def _actor(user: Any) -> str:
    return str(getattr(user, "email", "") or getattr(user, "user_id", "") or "user")


def _proposal_learning_citation(proposal: Dict[str, Any]) -> Dict[str, Any]:
    evidence = proposal.get("evidence") if isinstance(proposal, dict) else {}
    if not isinstance(evidence, dict):
        return {}
    citation = evidence.get("learning_citation")
    return citation if isinstance(citation, dict) else {}


def _learning_change_note(citation: Dict[str, Any]) -> str:
    if not citation:
        return ""
    snapshot = (
        citation.get("private_eval_snapshot")
        if isinstance(citation.get("private_eval_snapshot"), dict) else {}
    )
    pattern = (
        citation.get("recurring_pattern")
        if isinstance(citation.get("recurring_pattern"), dict) else {}
    )
    parts = []
    total_items = snapshot.get("total_items")
    if total_items is not None:
        parts.append(f"AP eval snapshot over {total_items} items")
    gate = str(snapshot.get("release_gate_status") or "").replace("_", " ").strip()
    if gate:
        parts.append(f"release gate {gate}")
    pattern_label = str(
        pattern.get("label") or pattern.get("pattern_key") or ""
    ).replace("_", " ").strip()
    pattern_count = pattern.get("vendor_count") or pattern.get("count")
    if pattern_label:
        if pattern_count:
            parts.append(f"{pattern_label} pattern across {pattern_count} cases")
        else:
            parts.append(f"{pattern_label} pattern")
    if not parts:
        return ""
    return "Learning evidence: " + "; ".join(parts) + "."


def _audit_resolution(
    db: Any, *, organization_id: str, event_type: str, actor: str,
    proposal: Dict[str, Any], reason: str, extra: Optional[Dict[str, Any]] = None,
) -> None:
    learning_citation = _proposal_learning_citation(proposal)
    try:
        db.append_audit_event({
            "ap_item_id": "",
            "event_type": event_type,
            "actor_type": "user",
            "actor_id": actor,
            "organization_id": organization_id,
            "reason": reason,
            "payload_json": {
                "proposal_id": proposal.get("id"),
                "proposal_kind": proposal.get("proposal_kind"),
                "vendor_name": proposal.get("vendor_name"),
                **(
                    {"learning_citation": learning_citation}
                    if learning_citation else {}
                ),
                **(extra or {}),
            },
        })
    except Exception as exc:  # noqa: BLE001
        logger.warning("[policy_proposals] %s audit failed: %s", event_type, exc)


@router.get("/policy-proposals")
def list_policy_proposals(
    status: Optional[str] = Query(default="pending"),
    _user=Depends(get_current_user),
) -> Dict[str, Any]:
    """The org's behavior-derived rule proposals (default: pending)."""
    organization_id = _session_org(_user)
    db = get_db()
    proposals = db.list_policy_proposals(
        organization_id=organization_id, status=status or None
    )
    return {
        "organization_id": organization_id,
        "status": status or None,
        "proposals": proposals,
        "count": len(proposals),
    }


@router.post("/policy-proposals/{proposal_id}/accept")
def accept_policy_proposal(
    proposal_id: str,
    body: Optional[Dict[str, Any]] = None,
    _user=Depends(require_workspace_admin),
) -> Dict[str, Any]:
    """Accept: lands the proposal's bounded rule in the rules table (the
    cascade's existing Step-1 mechanism), attributed to the accepting human.

    Admin-gated — accepting creates a live auto-approve rule, the same
    consequence as the admin-gated manual rules CRUD.

    Order is CLAIM-FIRST: atomically flip the proposal to accepted (first
    writer wins), THEN create the rule, then backfill the linkage. A lost
    race returns 409 having created NOTHING; a rule-creation failure reopens
    the claim — no path leaves an orphan live rule.
    """
    organization_id = _session_org(_user)
    db = get_db()
    actor = _actor(_user)
    proposal = db.get_policy_proposal(
        organization_id=organization_id, proposal_id=proposal_id
    )
    if not proposal:
        raise HTTPException(status_code=404, detail="proposal_not_found")
    if proposal.get("status") != "pending":
        raise HTTPException(status_code=409, detail="proposal_already_resolved")
    rule_payload = dict(proposal.get("proposed_rule") or {})
    if not rule_payload:
        raise HTTPException(status_code=409, detail="proposal_missing_rule")

    note = str((body or {}).get("note") or "").strip()
    resolved = db.resolve_policy_proposal(
        organization_id=organization_id,
        proposal_id=proposal_id,
        resolution="accepted",
        actor_id=actor,
        note=note or None,
    )
    if not resolved:
        # Lost the claim — nothing was created.
        raise HTTPException(status_code=409, detail="proposal_already_resolved")

    rule_payload["organization_id"] = organization_id
    rule_payload["created_by"] = actor
    change_note = _learning_change_note(_proposal_learning_citation(proposal))
    if change_note:
        rule_payload["change_note"] = change_note
        rule_payload["description"] = rule_payload.get("description") or change_note
    try:
        rule = db.create_rule(rule_payload)
    except Exception as exc:  # noqa: BLE001
        # Reopen the claim so a retry is possible; never leave a half-applied
        # accept (claimed but ruleless beats orphan-rule, and we undo even that).
        try:
            db.reopen_policy_proposal(
                organization_id=organization_id, proposal_id=proposal_id
            )
        except Exception as reopen_exc:  # noqa: BLE001
            logger.warning("[policy_proposals] reopen failed: %s", reopen_exc)
        logger.warning("[policy_proposals] rule creation failed: %s", exc)
        raise HTTPException(status_code=500, detail="rule_creation_failed")

    resolved = db.set_policy_proposal_applied_rule(
        organization_id=organization_id,
        proposal_id=proposal_id,
        applied_rule_id=str(rule.get("id") or ""),
    ) or resolved

    rationale = str(proposal.get("behavior_summary") or "")
    if note:
        rationale = f"{rationale} Operator note: {note}"
    _audit_resolution(
        db, organization_id=organization_id, event_type="policy_proposal_accepted",
        actor=actor, proposal=proposal, reason=rationale,
        extra={"applied_rule_id": rule.get("id")},
    )
    return {"status": "accepted", "proposal": resolved, "rule": rule}


@router.post("/policy-proposals/{proposal_id}/decline")
def decline_policy_proposal(
    proposal_id: str,
    body: Optional[Dict[str, Any]] = None,
    _user=Depends(require_workspace_admin),
) -> Dict[str, Any]:
    """Decline: records the deliberate non-rule. The reason is REQUIRED — "we
    handle these case-by-case because..." is itself tribal knowledge."""
    organization_id = _session_org(_user)
    db = get_db()
    actor = _actor(_user)
    reason = str((body or {}).get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="decline_reason_required")
    proposal = db.get_policy_proposal(
        organization_id=organization_id, proposal_id=proposal_id
    )
    if not proposal:
        raise HTTPException(status_code=404, detail="proposal_not_found")
    if proposal.get("status") != "pending":
        raise HTTPException(status_code=409, detail="proposal_already_resolved")

    resolved = db.resolve_policy_proposal(
        organization_id=organization_id,
        proposal_id=proposal_id,
        resolution="declined",
        actor_id=actor,
        note=reason,
    )
    if not resolved:
        raise HTTPException(status_code=409, detail="proposal_already_resolved")
    _audit_resolution(
        db, organization_id=organization_id, event_type="policy_proposal_declined",
        actor=actor, proposal=proposal,
        reason=f"Deliberate non-rule: {reason}",
    )
    return {"status": "declined", "proposal": resolved}
