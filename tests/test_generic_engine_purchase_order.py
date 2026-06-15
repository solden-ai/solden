"""Generic-runtime proof #2: drive a purchase_order Box through the SAME
engine primitives as ap_item and bank_match.

This is the strongest generality proof yet: purchase_order is AP-*peer*
(no parent FK, its own independent lifecycle), not AP-subordinate like
bank_match. It runs through box_registry CRUD dispatch + the
CoordinationEngine with zero AP-specific code on the path.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from solden.core import box_registry  # noqa: E402
from solden.core import database as db_module  # noqa: E402
from solden.core.coordination_engine import CoordinationEngine  # noqa: E402
from solden.core.plan import Action, Plan  # noqa: E402
from solden.services.memory_invariants import memory_event_invariant_violations  # noqa: E402

ORG = "orgGenPO"


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    inst.ensure_organization(ORG, organization_name=ORG)
    return inst


def _po(db, po_id="PO-gen-1"):
    return box_registry.create_box("purchase_order", {
        "po_id": po_id,
        "organization_id": ORG,
        "po_number": po_id,
        "vendor_name": "Acme Supplies",
        "total_amount": 5000.0,
        "currency": "GBP",
        "requested_by": "buyer@acme.test",
        "status": "draft",
    }, db)


def _audit_rows(db, organization_id, box_type=None):
    if box_type:
        sql = ("SELECT * FROM audit_events WHERE organization_id = %s "
               "AND box_type = %s ORDER BY chain_seq ASC")
        params = (organization_id, box_type)
    else:
        sql = ("SELECT * FROM audit_events WHERE organization_id = %s "
               "ORDER BY chain_seq ASC")
        params = (organization_id,)
    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def _payload_json(row):
    raw = row.get("payload_json")
    if isinstance(raw, str):
        return json.loads(raw)
    return raw if isinstance(raw, dict) else {}


def test_create_box_dispatches_to_purchase_order(db):
    po = _po(db)
    assert po["state"] == "draft"          # status aliased to state
    assert po["id"] == "PO-gen-1"          # po_id aliased to id
    loaded = box_registry.get_box("purchase_order", "PO-gen-1", db)
    assert loaded["id"] == "PO-gen-1"
    rows = _audit_rows(db, ORG, box_type="purchase_order")
    assert any(r["box_id"] == "PO-gen-1" for r in rows)


def test_update_box_advances_po_state(db):
    _po(db, po_id="PO-gen-2")
    box_registry.update_box("purchase_order", "PO-gen-2", db, state="pending_approval", actor_id="buyer")
    box_registry.update_box("purchase_order", "PO-gen-2", db, state="approved", actor_id="cfo")
    loaded = box_registry.get_box("purchase_order", "PO-gen-2", db)
    assert loaded["state"] == "approved"
    assert loaded["approved_by"] == "cfo"   # approval metadata stamped on ->approved
    rows = _audit_rows(db, ORG, box_type="purchase_order")
    approved = next(r for r in rows if r["event_type"] == "purchase_order_approved")
    assert memory_event_invariant_violations(_payload_json(approved)) == []


def test_box_lifecycle_primitives_generic_for_po(db):
    _po(db, po_id="PO-gen-3")
    exc = db.raise_box_exception(
        box_id="PO-gen-3", box_type="purchase_order", organization_id=ORG,
        exception_type="budget_review", reason="over department budget",
        raised_by="agent", severity="medium",
    )
    assert exc and exc.get("id")
    open_excs = db.list_box_exceptions(box_id="PO-gen-3", box_type="purchase_order")
    assert any(e["id"] == exc["id"] for e in open_excs)
    db.resolve_box_exception(exception_id=exc["id"], resolved_by="cfo")
    outcome = db.record_box_outcome(
        box_id="PO-gen-3", box_type="purchase_order", organization_id=ORG,
        outcome_type="approved", recorded_by="agent",
    )
    assert outcome


def test_po_rides_the_shared_audit_hash_chain(db):
    _po(db, po_id="PO-gen-4")
    box_registry.update_box("purchase_order", "PO-gen-4", db, state="pending_approval", actor_id="buyer")
    rows = _audit_rows(db, ORG, box_type="purchase_order")
    assert len(rows) >= 2
    for r in rows:
        assert r.get("hash"), "trigger did not stamp a hash"
        assert r.get("chain_seq") is not None, "trigger did not assign chain_seq"
    created = next(r for r in rows if r["event_type"] == "purchase_order_created")
    submitted = next(r for r in rows if r["event_type"] == "purchase_order_pending_approval")
    assert submitted["prev_hash"] == created["hash"]
    assert submitted["chain_seq"] > created["chain_seq"]


def test_coordination_engine_drives_po_through_approval_lifecycle(db):
    _po(db, po_id="PO-gen-5")
    engine = CoordinationEngine(db=db, organization_id=ORG)
    plan = Plan(
        event_type="po_decision",
        actions=[
            Action("move_box_stage", "DET", {"target": "pending_approval", "actor_id": "buyer"}),
            Action("move_box_stage", "DET", {"target": "approved", "actor_id": "cfo"}),
            Action("move_box_stage", "DET", {"target": "closed", "actor_id": "cfo"}),
        ],
        box_id="PO-gen-5",
        box_type="purchase_order",
        organization_id=ORG,
    )
    result = asyncio.run(engine.execute(plan))
    assert result.status == "completed"
    loaded = box_registry.get_box("purchase_order", "PO-gen-5", db)
    assert loaded["state"] == "closed"   # DRAFT->PENDING_APPROVAL->APPROVED->CLOSED via generic handler


def test_engine_exception_path_for_typeless_stall_state(db):
    # purchase_order has no exception_state; an illegal move must raise a
    # box_exception, NOT attempt an illegal state move.
    _po(db, po_id="PO-gen-6")
    engine = CoordinationEngine(db=db, organization_id=ORG)
    plan = Plan(
        event_type="po_decision",
        actions=[Action("move_box_stage", "DET", {"target": "closed", "actor_id": "cfo"})],
        box_id="PO-gen-6",
        box_type="purchase_order",
        organization_id=ORG,
    )
    result = asyncio.run(engine.execute(plan))
    assert result.status == "failed"   # draft->closed is illegal
    loaded = box_registry.get_box("purchase_order", "PO-gen-6", db)
    assert loaded["state"] == "draft"  # unchanged
    excs = db.list_box_exceptions(box_id="PO-gen-6", box_type="purchase_order")
    assert any(e.get("exception_type") == "action_failed" for e in excs)
