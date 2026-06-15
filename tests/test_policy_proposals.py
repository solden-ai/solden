"""Tribal-knowledge Build 3 — behavior → standing-policy proposals.

Covers the store (idempotency: pending AND declined suppress re-create),
the deterministic detector (threshold, clean-window, bounded amount cap,
flag-off), and the accept/decline endpoints (accept lands a bounded
rules-table row visible to the decision cascade; decline requires the reason).
"""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from solden.core import database as db_module
from solden.core.auth import get_current_user
from solden.api import policy_proposals as proposal_routes
from solden.services.agent_memory import AgentMemoryService
from solden.services.ap_learning_loop import PRIVATE_OUTCOME_EVAL_TYPE
from solden.services.policy_proposals import detect_policy_proposals


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    inst.ensure_organization("orgPP", organization_name="orgPP")
    inst.ensure_organization("orgPPB", organization_name="orgPPB")
    return inst


def _user(org: str = "orgPP", workspace_role: str = "admin") -> SimpleNamespace:
    return SimpleNamespace(
        user_id="op-1", email="op@example.com", organization_id=org,
        role="user", workspace_role=workspace_role,
    )


def _client(org: str, workspace_role: str = "admin") -> TestClient:
    app = FastAPI()
    app.include_router(proposal_routes.router)
    app.dependency_overrides[get_current_user] = lambda: _user(org, workspace_role)
    return TestClient(app)


@pytest.fixture()
def client_orgPP(db):
    return _client("orgPP")


@pytest.fixture()
def client_orgPPB(db):
    return _client("orgPPB")


def _seed_behavior(db, vendor="Acme", approves=6, org="orgPP", amount=900.0):
    """Seed the REAL writers: feedback rows (approve after escalate) + invoice
    history (for the amount bound)."""
    for i in range(approves):
        db.record_vendor_decision_feedback(
            org, vendor,
            ap_item_id=f"AP-pp-{vendor}-{i}",
            human_decision="approve",
            agent_recommendation="escalate",
            decision_override=True,
            actor_id="op@example.com",
        )


def _seed_history(db, vendor="Acme", org="orgPP", amount=900.0):
    # Insert directly — the detector only reads `amount`.
    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO vendor_invoice_history "
            "(id, organization_id, vendor_name, ap_item_id, amount, currency, "
            " was_approved, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, 1, NOW()::text)",
            (f"VIH-{vendor}-1", org, vendor, f"AP-pp-{vendor}-hist", amount, "EUR"),
        )
        conn.commit()


def _seed_learning_citation(db, vendor="Acme", org="orgPP"):
    memory = AgentMemoryService(org, db=db)
    memory.record_eval_snapshot(
        skill_id="ap_v1",
        scope="organization",
        snapshot_type=PRIVATE_OUTCOME_EVAL_TYPE,
        payload={
            "contract": "solden_ap_learning_loop.v1",
            "scope": "ap_source_to_pay",
            "summary": {
                "total_items": 12,
                "memory_event_coverage_rate": 1.0,
                "agent_trace_rate": 0.92,
                "evidence_link_rate": 0.83,
                "outcome_traceability_rate": 0.75,
            },
            "release_gate": {"status": "needs_work"},
        },
    )
    memory.record_pattern(
        skill_id="ap_v1",
        pattern_type="company_ap_blocker",
        pattern_key="critical_field_low_confidence",
        pattern={
            "key": "critical_field_low_confidence",
            "label": "Critical Field Low Confidence",
            "count": 4,
            "share": 0.33,
            "affected_vendors": [{"vendor_name": vendor, "count": 2}],
            "common_next_actions": [{"next_action": "Confirm the vendor and amount"}],
            "example_item_ids": ["AP-EVAL-2", "AP-EVAL-1"],
        },
        confidence=0.86,
    )


# ─── Store ──────────────────────────────────────────────────────────


def test_store_create_and_suppression(db):
    first = db.create_policy_proposal(
        organization_id="orgPP", proposal_kind="vendor_standing_approval",
        vendor_name="Acme", behavior_summary="6 approvals after escalate",
        proposed_rule={"name": "r"},
    )
    assert first and first["status"] == "pending"
    # Pending suppresses duplicates.
    assert db.create_policy_proposal(
        organization_id="orgPP", proposal_kind="vendor_standing_approval",
        vendor_name="Acme", behavior_summary="again", proposed_rule={"name": "r"},
    ) is None
    # Decline = deliberate non-rule -> still suppressed (never re-nag).
    db.resolve_policy_proposal(
        organization_id="orgPP", proposal_id=first["id"],
        resolution="declined", actor_id="op@example.com", note="case-by-case",
    )
    assert db.create_policy_proposal(
        organization_id="orgPP", proposal_kind="vendor_standing_approval",
        vendor_name="Acme", behavior_summary="again", proposed_rule={"name": "r"},
    ) is None
    # Accepted also suppresses — the rule exists; re-proposing would stack rules.
    acc = db.create_policy_proposal(
        organization_id="orgPP", proposal_kind="vendor_standing_approval",
        vendor_name="AcceptedCo", behavior_summary="x", proposed_rule={"name": "r"},
    )
    db.resolve_policy_proposal(
        organization_id="orgPP", proposal_id=acc["id"],
        resolution="accepted", actor_id="op@example.com",
    )
    assert db.create_policy_proposal(
        organization_id="orgPP", proposal_kind="vendor_standing_approval",
        vendor_name="AcceptedCo", behavior_summary="x", proposed_rule={"name": "r"},
    ) is None


def test_store_tenant_isolation(db):
    row = db.create_policy_proposal(
        organization_id="orgPP", proposal_kind="vendor_standing_approval",
        vendor_name="Iso", behavior_summary="x", proposed_rule={"name": "r"},
    )
    assert db.get_policy_proposal(organization_id="orgPPB", proposal_id=row["id"]) is None
    assert db.list_policy_proposals(organization_id="orgPPB", status="pending") == []


# ─── Detector ───────────────────────────────────────────────────────


def test_detector_proposes_bounded_rule(db):
    _seed_behavior(db, vendor="Acme", approves=6)
    _seed_history(db, vendor="Acme", amount=900.0)
    created = detect_policy_proposals(db, "orgPP")
    assert len(created) == 1
    proposal = created[0]
    assert proposal["vendor_name"] == "Acme"
    rule = proposal["proposed_rule"]
    conds = {c["field"]: c for c in rule["conditions"]["all_of"]}
    assert conds["vendor_name"]["value"] == "Acme"
    # Bounded: 1.2 x max APPROVED amount, never unbounded — and currency-scoped.
    assert conds["amount"]["op"] == "lt"
    assert conds["amount"]["value"] == pytest.approx(1080.0)
    assert conds["currency"] == {"field": "currency", "op": "eq", "value": "EUR"}
    assert rule["actions"] == [{"type": "auto_approve"}]


def test_detector_attaches_learning_loop_citation(db):
    _seed_behavior(db, vendor="LearningCo", approves=6)
    _seed_history(db, vendor="LearningCo", amount=900.0)
    _seed_learning_citation(db, vendor="LearningCo")

    created = detect_policy_proposals(db, "orgPP")

    proposal = next(p for p in created if p["vendor_name"] == "LearningCo")
    citation = proposal["evidence"]["learning_citation"]
    snapshot = citation["private_eval_snapshot"]
    assert snapshot["snapshot_type"] == PRIVATE_OUTCOME_EVAL_TYPE
    assert snapshot["total_items"] == 12
    assert snapshot["release_gate_status"] == "needs_work"
    pattern = citation["recurring_pattern"]
    assert pattern["pattern_key"] == "critical_field_low_confidence"
    assert pattern["vendor_count"] == 2
    assert pattern["example_item_ids"] == ["AP-EVAL-2", "AP-EVAL-1"]

    created_events = db.list_audit_events(
        "orgPP", event_types=["policy_proposal_created"], limit=10
    )
    audit = next(
        e for e in created_events
        if e["payload_json"].get("proposal_id") == proposal["id"]
    )
    assert audit["payload_json"]["learning_citation"]["recurring_pattern"][
        "vendor_count"
    ] == 2


def test_detector_cap_ignores_rejected_history(db):
    """A rejected high-amount invoice must not inflate the auto-approve bound."""
    _seed_behavior(db, vendor="TaintCo", approves=6)
    _seed_history(db, vendor="TaintCo", amount=900.0)
    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO vendor_invoice_history "
            "(id, organization_id, vendor_name, ap_item_id, amount, currency, "
            " was_approved, final_state, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, 0, 'rejected', NOW()::text)",
            ("VIH-TaintCo-rej", "orgPP", "TaintCo", "AP-pp-TaintCo-rej", 50000.0, "EUR"),
        )
        conn.commit()
    created = [p for p in detect_policy_proposals(db, "orgPP") if p["vendor_name"] == "TaintCo"]
    assert created
    conds = {c["field"]: c for c in created[0]["proposed_rule"]["conditions"]["all_of"]}
    assert conds["amount"]["value"] == pytest.approx(1080.0)  # not 60,000


def test_detector_below_threshold_or_rejections_no_proposal(db):
    _seed_behavior(db, vendor="FewVendor", approves=3)
    _seed_history(db, vendor="FewVendor")
    assert detect_policy_proposals(db, "orgPP") == []

    _seed_behavior(db, vendor="MixedVendor", approves=6)
    _seed_history(db, vendor="MixedVendor")
    db.record_vendor_decision_feedback(
        "orgPP", "MixedVendor", ap_item_id="AP-rej",
        human_decision="reject", agent_recommendation="approve",
        decision_override=True, actor_id="op@example.com",
    )
    assert all(p["vendor_name"] != "MixedVendor" for p in detect_policy_proposals(db, "orgPP"))


def test_detector_requires_observed_amounts(db):
    _seed_behavior(db, vendor="NoHistory", approves=6)
    # No invoice history -> can't bound the rule -> no proposal.
    assert all(p["vendor_name"] != "NoHistory" for p in detect_policy_proposals(db, "orgPP"))


def test_detector_flag_off(db, monkeypatch):
    monkeypatch.setenv("FEATURE_POLICY_PROPOSALS", "false")
    _seed_behavior(db, vendor="FlagVendor", approves=6)
    _seed_history(db, vendor="FlagVendor")
    assert detect_policy_proposals(db, "orgPP") == []


# ─── Accept / decline endpoints ─────────────────────────────────────


def _pending_proposal(db, vendor="Acme"):
    _seed_behavior(db, vendor=vendor, approves=6)
    _seed_history(db, vendor=vendor, amount=900.0)
    created = detect_policy_proposals(db, "orgPP")
    assert created
    return created[0]


def test_accept_lands_bounded_rule_visible_to_cascade(db, client_orgPP):
    _seed_learning_citation(db, vendor="AcceptCo")
    proposal = _pending_proposal(db, vendor="AcceptCo")
    resp = client_orgPP.post(
        f"/api/workspace/policy-proposals/{proposal['id']}/accept",
        json={"note": "They're our landlord; rent is stable."},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "accepted"
    rule_id = body["rule"]["id"]
    # The rule is REAL: visible to the decision cascade's rule listing.
    rules = db.list_rules("orgPP", workflow="ap")
    mine = [r for r in rules if r["id"] == rule_id]
    assert mine and mine[0].get("created_by") == "op@example.com"
    assert "Learning evidence" in mine[0].get("description")
    # Proposal marked accepted + linked.
    after = db.get_policy_proposal(organization_id="orgPP", proposal_id=proposal["id"])
    assert after["status"] == "accepted"
    assert after["applied_rule_id"] == rule_id
    accepted_events = db.list_audit_events(
        "orgPP", event_types=["policy_proposal_accepted"], limit=10
    )
    accepted_audit = next(
        e for e in accepted_events
        if e["payload_json"].get("proposal_id") == proposal["id"]
    )
    assert accepted_audit["payload_json"]["learning_citation"][
        "private_eval_snapshot"
    ]["total_items"] == 12
    # Re-accept -> 409, and claim-first means the 409 path created NOTHING.
    rules_before = len(db.list_rules("orgPP", workflow="ap"))
    assert client_orgPP.post(
        f"/api/workspace/policy-proposals/{proposal['id']}/accept", json={},
    ).status_code == 409
    assert len(db.list_rules("orgPP", workflow="ap")) == rules_before


def test_decline_requires_reason_and_records_non_rule(db, client_orgPP):
    proposal = _pending_proposal(db, vendor="DeclineCo")
    assert client_orgPP.post(
        f"/api/workspace/policy-proposals/{proposal['id']}/decline", json={},
    ).status_code == 400
    resp = client_orgPP.post(
        f"/api/workspace/policy-proposals/{proposal['id']}/decline",
        json={"reason": "Amounts vary too much; we want eyes on each one."},
    )
    assert resp.status_code == 200
    after = db.get_policy_proposal(organization_id="orgPP", proposal_id=proposal["id"])
    assert after["status"] == "declined"
    assert "eyes on each one" in after["decline_reason"]
    # And the vendor is never re-proposed.
    assert all(
        p["vendor_name"] != "DeclineCo" for p in detect_policy_proposals(db, "orgPP")
    )


def test_endpoints_tenant_isolation(db, client_orgPPB):
    proposal = _pending_proposal(db, vendor="IsoCo")
    assert client_orgPPB.post(
        f"/api/workspace/policy-proposals/{proposal['id']}/accept", json={},
    ).status_code == 404
    assert client_orgPPB.get("/api/workspace/policy-proposals").json()["count"] == 0

def test_accept_and_decline_require_workspace_admin(db):
    """A non-admin seat must not be able to land (or suppress) a money rule."""
    proposal = _pending_proposal(db, vendor="RoleCo")
    member = _client("orgPP", workspace_role="member")
    assert member.post(
        f"/api/workspace/policy-proposals/{proposal['id']}/accept", json={},
    ).status_code == 403
    assert member.post(
        f"/api/workspace/policy-proposals/{proposal['id']}/decline",
        json={"reason": "no"},
    ).status_code == 403
    # Still pending — the member changed nothing.
    after = db.get_policy_proposal(organization_id="orgPP", proposal_id=proposal["id"])
    assert after["status"] == "pending"
