"""Tribal-knowledge Build 1 — rationale distillation.

When a decision commits with a thin human rationale, the distiller reads the
PERSISTED conversation context (intake email excerpt + timeline crumbs) and
commits a strictly extractive proposed why as a `rationale_distilled` memory
event (machine_distilled, with provenance). A human confirm promotes it via
`rationale_confirmed`. Machine prose never surfaces as the operator's words.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from solden.core import database as db_module
from solden.core.auth import get_current_user
from solden.api import ap_item_detail as detail_routes
from solden.services.rationale_distillation import (
    distill_rationale_for_decision,
    gather_decision_context,
    is_thin_rationale,
)


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    inst.ensure_organization("orgRD", organization_name="orgRD")
    inst.ensure_organization("orgRDB", organization_name="orgRDB")
    return inst


def _user(org: str = "orgRD") -> SimpleNamespace:
    return SimpleNamespace(
        user_id="op-1", email="op@example.com", organization_id=org, role="user",
    )


def _make_item(db, item_id: str, org: str = "orgRD", metadata=None):
    db.create_ap_item({
        "id": item_id,
        "organization_id": org,
        "vendor_name": "Acme",
        "amount": 320.0,
        "currency": "EUR",
        "invoice_number": f"INV-{item_id}",
        "state": "needs_approval",
        "metadata": metadata or {},
    })
    return db.get_ap_item(item_id)


def _run(coro):
    return asyncio.run(coro)


# ─── Thin-rationale detection ───────────────────────────────────────


def test_thin_rationale_detection():
    assert is_thin_rationale("")
    assert is_thin_rationale(None)
    assert is_thin_rationale("ok")
    assert is_thin_rationale("Approved.")
    assert is_thin_rationale("rejected_in_teams")
    assert is_thin_rationale("fine")
    assert not is_thin_rationale(
        "Vendor confirmed the Q3 true-up against PO-1182 out-of-band."
    )


# ─── Context gathering (persisted content only) ─────────────────────


def test_gather_context_pulls_email_excerpt_and_timeline_crumbs(db):
    item = _make_item(db, "AP-rd-ctx", metadata={
        "source_snippet": "Re: Acme renewal invoice",
        "source_body_excerpt": "Hi, this covers the Q3 true-up Dana approved in the call.",
    })
    from solden.services.memory_events import commit_memory_event
    commit_memory_event(
        db,
        box_type="ap_item",
        box_id=item["id"],
        organization_id="orgRD",
        event_type="slack_reply",
        source="slack",
        actor_type="user",
        actor_id="maya@example.com",
        summary="maya@example.com replied via Slack: this one is the contract true-up, go ahead",
    )
    text, refs = gather_decision_context(
        db, ap_item_id=item["id"], organization_id="orgRD"
    )
    assert "Q3 true-up Dana approved" in text
    assert "contract true-up, go ahead" in text
    assert refs.get("audit_event_ids")


def test_gather_context_is_tenant_scoped(db):
    item = _make_item(db, "AP-rd-tenant")
    text, refs = gather_decision_context(
        db, ap_item_id=item["id"], organization_id="orgRDB"
    )
    assert text == "" and refs == {}


# ─── Distillation ───────────────────────────────────────────────────


def _gateway_returning(content: str):
    gateway = MagicMock()
    gateway.call = AsyncMock(return_value=SimpleNamespace(content=content))
    return gateway


def test_insufficient_evidence_stores_nothing(db):
    item = _make_item(db, "AP-rd-insuff", metadata={
        "source_body_excerpt": "Invoice attached. Regards, Acme billing.",
    })
    with patch("solden.core.llm_gateway.get_llm_gateway", return_value=_gateway_returning("INSUFFICIENT")):
        row = _run(distill_rationale_for_decision(
            db, organization_id="orgRD", ap_item_id=item["id"],
            decision_audit_event_id=None, decision_intent="approve_invoice",
            existing_rationale="",
        ))
    assert row is None
    events = db.list_audit_events("orgRD", event_types=["memory_event:rationale_distilled"], box_id=item["id"])
    assert events == []


def test_distill_commits_machine_distilled_event_with_provenance(db):
    item = _make_item(db, "AP-rd-ok", metadata={
        "source_body_excerpt": "Covers the Q3 true-up Dana signed off on the call.",
    })
    with patch("solden.core.llm_gateway.get_llm_gateway", return_value=_gateway_returning(
        "Approved because it covers the Q3 true-up Dana signed off on."
    )):
        row = _run(distill_rationale_for_decision(
            db, organization_id="orgRD", ap_item_id=item["id"],
            decision_audit_event_id="evt-decision-1", decision_intent="approve_invoice",
            actor_id="op@example.com", existing_rationale="ok",
        ))
    assert row is not None
    events = db.list_audit_events("orgRD", event_types=["memory_event:rationale_distilled"], box_id=item["id"])
    assert len(events) == 1
    payload = events[0].get("payload_json")
    if isinstance(payload, str):
        import json as _json
        payload = _json.loads(payload)
    me = payload["memory_event"]
    assert "Q3 true-up" in me["rationale"]
    assert me["quality"]["verification_status"] == "machine_distilled"
    assert me["source"]["refs"].get("decision_audit_event_id") == "evt-decision-1"


def test_real_rationale_skips_distillation(db):
    item = _make_item(db, "AP-rd-skip")
    gateway = _gateway_returning("should never be called")
    with patch("solden.core.llm_gateway.get_llm_gateway", return_value=gateway):
        row = _run(distill_rationale_for_decision(
            db, organization_id="orgRD", ap_item_id=item["id"],
            decision_audit_event_id=None, decision_intent="approve_invoice",
            existing_rationale="Vendor confirmed the Q3 true-up against PO-1182.",
        ))
    assert row is None
    gateway.call.assert_not_called()


def test_flag_off_is_a_noop(db, monkeypatch):
    monkeypatch.setenv("FEATURE_RATIONALE_DISTILLATION", "false")
    item = _make_item(db, "AP-rd-flag", metadata={"source_body_excerpt": "Q3 true-up."})
    gateway = _gateway_returning("anything")
    with patch("solden.core.llm_gateway.get_llm_gateway", return_value=gateway):
        row = _run(distill_rationale_for_decision(
            db, organization_id="orgRD", ap_item_id=item["id"],
            decision_audit_event_id=None, decision_intent="approve_invoice",
            existing_rationale="",
        ))
    assert row is None
    gateway.call.assert_not_called()


# ─── Fire-and-forget spawn (handler helper) ─────────────────────────


def test_spawn_helper_is_thin_gated_and_never_raises():
    from solden.services.finance_skills.ap_intent_handlers import (
        _spawn_rationale_distillation,
    )

    runtime = SimpleNamespace(db=MagicMock(), organization_id="orgRD", actor_id="op-1")

    async def scenario():
        with patch(
            "solden.services.rationale_distillation.distill_rationale_for_decision",
            new=AsyncMock(return_value=None),
        ) as distill:
            # Thin rationale -> spawns.
            _spawn_rationale_distillation(
                runtime, ap_item_id="AP-1", audit_row={"id": "evt-1"},
                decision_intent="approve_invoice", existing_rationale="",
            )
            await asyncio.sleep(0)
            assert distill.await_count == 1
            # Real rationale -> no spawn.
            _spawn_rationale_distillation(
                runtime, ap_item_id="AP-1", audit_row={"id": "evt-1"},
                decision_intent="approve_invoice",
                existing_rationale="Vendor confirmed the Q3 true-up against PO-1182.",
            )
            await asyncio.sleep(0)
            assert distill.await_count == 1

    asyncio.run(scenario())


# ─── Confirm endpoint ───────────────────────────────────────────────


@pytest.fixture()
def client_orgRD(db):
    app = FastAPI()
    app.include_router(detail_routes.router)
    app.dependency_overrides[get_current_user] = lambda: _user("orgRD")
    return TestClient(app)


@pytest.fixture()
def client_orgRDB(db):
    app = FastAPI()
    app.include_router(detail_routes.router)
    app.dependency_overrides[get_current_user] = lambda: _user("orgRDB")
    return TestClient(app)


def _distill_event(db, item_id: str) -> str:
    with patch("solden.core.llm_gateway.get_llm_gateway", return_value=_gateway_returning(
        "Approved because it covers the Q3 true-up Dana signed off on."
    )):
        _run(distill_rationale_for_decision(
            db, organization_id="orgRD", ap_item_id=item_id,
            decision_audit_event_id="evt-d", decision_intent="approve_invoice",
            existing_rationale="",
        ))
    rows = db.list_audit_events("orgRD", event_types=["memory_event:rationale_distilled"], box_id=item_id)
    return str(rows[0]["id"])


def test_confirm_promotes_to_rationale_confirmed(db, client_orgRD):
    item = _make_item(db, "AP-rd-confirm", metadata={"source_body_excerpt": "Q3 true-up per Dana."})
    event_id = _distill_event(db, item["id"])
    resp = client_orgRD.post(
        f"/api/workspace/ap-items/{item['id']}/rationale/confirm",
        json={"audit_event_id": event_id},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "confirmed"
    confirmed = db.list_audit_events("orgRD", event_types=["memory_event:rationale_confirmed"], box_id=item["id"])
    assert len(confirmed) == 1
    assert confirmed[0].get("actor_type") == "user"


def test_confirm_cross_tenant_404(db, client_orgRDB):
    item = _make_item(db, "AP-rd-x", metadata={"source_body_excerpt": "Q3 true-up per Dana."})
    event_id = _distill_event(db, item["id"])
    resp = client_orgRDB.post(
        f"/api/workspace/ap-items/{item['id']}/rationale/confirm",
        json={"audit_event_id": event_id},
    )
    assert resp.status_code == 404


def test_confirm_unknown_event_404(db, client_orgRD):
    item = _make_item(db, "AP-rd-miss")
    resp = client_orgRD.post(
        f"/api/workspace/ap-items/{item['id']}/rationale/confirm",
        json={"audit_event_id": "evt-nope"},
    )
    assert resp.status_code == 404


# ─── Timeline surfacing — distinct keys ─────────────────────────────


def test_timeline_surfaces_distilled_under_distinct_keys(db):
    from solden.services.ap_operator_audit import normalize_operator_audit_events

    item = _make_item(db, "AP-rd-surface", metadata={"source_body_excerpt": "Q3 true-up per Dana."})
    _distill_event(db, item["id"])
    raw = db.list_ap_audit_events(item["id"], order="desc") or []
    rows = normalize_operator_audit_events(raw)
    distilled = [r for r in rows if r.get("operator_distilled_rationale")]
    assert distilled, "distilled rationale must surface on the timeline"
    row = distilled[0]
    assert row["operator_distilled_status"] == "machine_distilled"
    # Machine prose must NEVER pass as the operator's own words.
    assert not row.get("operator_human_rationale")


def test_surface_injected_default_reasons_are_thin():
    """Surface default reasons are machine labels, never an operator's why.

    Regression for the Build 2 bypass: ``approved_in_netsuite_panel`` (26
    chars, not in the stock list) passed the thin check, so the high-signal
    elicitation backstop never fired for ERP-panel approvals — and the
    distiller never proposed a read for them either. The shape match
    (verb + in/from/via + surface) covers panels that don't exist yet.
    """
    from solden.services.rationale_distillation import is_thin_rationale

    surface_defaults = [
        "approved_in_netsuite_panel",
        "rejected_in_netsuite_panel",
        "info_requested_from_netsuite_panel",
        "approved_in_sap_fiori_panel",
        "rejected_in_sap_fiori_panel",
        "info_requested_from_sap_fiori_panel",
        "approved_in_sage_intacct_panel",
        "rejected_in_sage_intacct_panel",
        "info_requested_from_sage_intacct_panel",
        # a hypothetical future surface must be caught by shape, not list
        "approved_via_acme_erp_panel",
    ]
    for token in surface_defaults:
        assert is_thin_rationale(token), f"surface default escaped: {token}"

    # Real whys — including ones that mention surfaces — must NOT be flagged.
    real = [
        "Approved in NetSuite after Dana verified the PO on the call.",
        "Quarterly true-up; CFO signed off by email.",
    ]
    for text in real:
        assert not is_thin_rationale(text), f"real why misflagged: {text}"
