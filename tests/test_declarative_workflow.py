"""Generality proof #3 — and the platform proof.

bank_match and purchase_order proved the runtime is Box-type-agnostic, but
each was still hand-coded across ~10 files. This test proves the *declarative*
layer: a brand-new Box type (`contract_review`) is spun up from a single
:class:`WorkflowSpec` declaration — no per-type table, no ``*_states.py``, no
store mixin, no routes, no migration — and driven end-to-end through the SAME
``box_registry`` CRUD dispatch + CoordinationEngine + audit hash-chain +
exception queue as every built-in type.

If this passes, "declare a workflow, get a runtime" is true.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from solden.core import box_registry  # noqa: E402
from solden.core import database as db_module  # noqa: E402
from solden.core import workflow_spec  # noqa: E402
from solden.core.coordination_engine import CoordinationEngine  # noqa: E402
from solden.core.plan import Action, Plan  # noqa: E402
from solden.core.workflow_spec import (  # noqa: E402
    IllegalWorkflowTransitionError,
    WorkflowSpec,
)

ORG = "orgGenWF"

# The ENTIRE per-type surface for a new Box type. No other code is written.
CONTRACT_REVIEW_SPEC = WorkflowSpec(
    box_type="contract_review",
    url_slug="contract-reviews",
    states=("draft", "in_review", "approved", "rejected"),
    initial_state="draft",
    terminal_states=("approved", "rejected"),
    transitions={
        "draft": {"in_review"},
        "in_review": {"approved", "rejected"},
    },
    action_states={"submit": "in_review", "approve": "approved", "reject": "rejected"},
    fields=("title", "counterparty", "value"),
    exception_state=None,  # no stall state -> illegal move raises a box_exception
)


@pytest.fixture(autouse=True)
def _register_spec():
    """Register the throwaway type, and pop it from BOTH registries after.

    Module-global registries persist across tests in a worker; the teardown
    prevents the throwaway type from leaking into unrelated tests.
    """
    workflow_spec.register_spec(CONTRACT_REVIEW_SPEC)
    try:
        yield
    finally:
        workflow_spec.unregister_spec("contract_review")


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    inst.ensure_organization(ORG, organization_name=ORG)
    return inst


def _box(db, box_id="CR-1"):
    return box_registry.create_box("contract_review", {
        "id": box_id,
        "organization_id": ORG,
        "title": "MSA renewal",
        "counterparty": "Globex",
        "value": 25000,
        "created_by": "legal@acme.test",
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


def test_spec_validation_rejects_bad_graphs():
    # An action targeting an undeclared state is caught at validation time.
    bad = WorkflowSpec(
        box_type="bad_type",
        url_slug="bad-type",
        states=("a", "b"),
        initial_state="a",
        terminal_states=("b",),
        transitions={"a": {"b"}},
        action_states={"go": "nonexistent"},
    )
    errors = workflow_spec.validate_spec(bad)
    assert any("nonexistent" in e for e in errors)
    # Reserved box_type is rejected.
    assert workflow_spec.validate_spec(
        WorkflowSpec(box_type="ap_item", url_slug="x", states=("a",),
                     initial_state="a", terminal_states=("a",))
    )


def test_register_spec_derives_a_box_type():
    bt = box_registry.get("contract_review")
    assert bt.source_table == "boxes"
    assert bt.state_field == "state"
    assert bt.initial_state == "draft"
    assert bt.exception_state is None
    assert "draft" in bt.open_states
    assert bt.terminal_states == frozenset({"approved", "rejected"})


def test_create_box_dispatches_to_generic_store(db):
    box = _box(db)
    assert box["state"] == "draft"
    assert box["id"] == "CR-1"
    assert box["box_type"] == "contract_review"
    assert box["title"] == "MSA renewal"      # declared field round-trips via data JSONB
    assert box["counterparty"] == "Globex"
    loaded = box_registry.get_box("contract_review", "CR-1", db)
    assert loaded["id"] == "CR-1"
    rows = _audit_rows(db, ORG, box_type="contract_review")
    assert any(r["box_id"] == "CR-1"
               and r["event_type"] == "contract_review_created" for r in rows)


def test_data_payload_cannot_clobber_reserved_columns(db):
    # A malicious/clumsy 'state' in the data payload must not override the column.
    box_registry.create_box("contract_review", {
        "id": "CR-evil",
        "organization_id": ORG,
        "state": "approved",          # attempt to skip the lifecycle
        "title": "sneaky",
    }, db)
    loaded = box_registry.get_box("contract_review", "CR-evil", db)
    assert loaded["state"] == "draft"  # native column wins; entry is always initial


def test_update_box_advances_state_round_trip(db):
    _box(db, box_id="CR-2")
    box_registry.update_box("contract_review", "CR-2", db, state="in_review", actor_id="legal")
    box_registry.update_box("contract_review", "CR-2", db, state="approved", actor_id="gc")
    loaded = box_registry.get_box("contract_review", "CR-2", db)
    assert loaded["state"] == "approved"


def test_illegal_transition_raises_at_store(db):
    _box(db, box_id="CR-3")
    with pytest.raises(IllegalWorkflowTransitionError):
        box_registry.update_box("contract_review", "CR-3", db, state="approved", actor_id="gc")


def test_box_lifecycle_primitives_generic_for_declared_type(db):
    _box(db, box_id="CR-4")
    exc = db.raise_box_exception(
        box_id="CR-4", box_type="contract_review", organization_id=ORG,
        exception_type="legal_review", reason="needs counsel sign-off",
        raised_by="agent", severity="medium",
    )
    assert exc and exc.get("id")
    open_excs = db.list_box_exceptions(box_id="CR-4", box_type="contract_review")
    assert any(e["id"] == exc["id"] for e in open_excs)
    db.resolve_box_exception(exception_id=exc["id"], resolved_by="gc")
    outcome = db.record_box_outcome(
        box_id="CR-4", box_type="contract_review", organization_id=ORG,
        outcome_type="approved", recorded_by="agent",
    )
    assert outcome


def test_declared_box_rides_the_shared_audit_hash_chain(db):
    _box(db, box_id="CR-5")
    box_registry.update_box("contract_review", "CR-5", db, state="in_review", actor_id="legal")
    rows = _audit_rows(db, ORG, box_type="contract_review")
    assert len(rows) >= 2
    for r in rows:
        assert r.get("hash"), "trigger did not stamp a hash"
        assert r.get("chain_seq") is not None
    created = next(r for r in rows if r["event_type"] == "contract_review_created")
    submitted = next(r for r in rows if r["event_type"] == "contract_review_in_review")
    assert submitted["prev_hash"] == created["hash"]
    assert submitted["chain_seq"] > created["chain_seq"]


def test_coordination_engine_drives_declared_type_end_to_end(db):
    _box(db, box_id="CR-6")
    engine = CoordinationEngine(db=db, organization_id=ORG)
    plan = Plan(
        event_type="contract_decision",
        actions=[
            Action("move_box_stage", "DET", {"target": "in_review", "actor_id": "legal"}),
            Action("move_box_stage", "DET", {"target": "approved", "actor_id": "gc"}),
        ],
        box_id="CR-6",
        box_type="contract_review",
        organization_id=ORG,
    )
    result = asyncio.run(engine.execute(plan))
    assert result.status == "completed"
    loaded = box_registry.get_box("contract_review", "CR-6", db)
    assert loaded["state"] == "approved"


def test_box_summary_surfaces_declared_fields(db):
    from solden.core.box_summary import build_box_summary
    _box(db, box_id="CR-sum")
    summary = build_box_summary("CR-sum", db=db, box_type="contract_review")
    assert summary.current_stage == "draft"
    assert summary.key_fields.get("title") == "MSA renewal"
    assert summary.key_fields.get("counterparty") == "Globex"


def test_entering_declared_exception_state_raises_box_exception(db):
    # A spec that DOES declare an exception_state: transitioning a Box into it
    # auto-raises a first-class box_exception (parity with how AP raises one
    # when an ap_item lands in needs_info), no bespoke Python.
    spec = WorkflowSpec(
        box_type="vendor_kyc",
        url_slug="vendor-kyc",
        states=("submitted", "in_checks", "approved", "blocked"),
        initial_state="submitted",
        terminal_states=("approved",),
        transitions={
            "submitted": {"in_checks"},
            "in_checks": {"approved", "blocked"},
            "blocked": {"in_checks"},  # recoverable, like AP's needs_info
        },
        action_states={
            "start": "in_checks", "approve": "approved",
            "block": "blocked", "recheck": "in_checks",
        },
        fields=("vendor_name",),
        exception_state="blocked",
    )
    workflow_spec.register_spec(spec)
    try:
        box_registry.create_box("vendor_kyc", {
            "id": "VK-1", "organization_id": ORG, "vendor_name": "Sketchy LLC",
        }, db)
        box_registry.update_box("vendor_kyc", "VK-1", db, state="in_checks", actor_id="ops")
        box_registry.update_box(
            "vendor_kyc", "VK-1", db, state="blocked",
            actor_id="ops", reason="sanctions hit",
        )
        excs = db.list_box_exceptions(box_id="VK-1", box_type="vendor_kyc")
        assert any(e.get("exception_type") == "vendor_kyc_exception" for e in excs)
        # exception_state is a real state the Box moves into (not a veto).
        loaded = box_registry.get_box("vendor_kyc", "VK-1", db)
        assert loaded["state"] == "blocked"
    finally:
        workflow_spec.unregister_spec("vendor_kyc")


def test_box_summary_respects_declared_summary_fields(db):
    from solden.core.box_summary import build_box_summary
    spec = WorkflowSpec(
        box_type="ticket", url_slug="tickets",
        states=("open", "closed"), initial_state="open", terminal_states=("closed",),
        transitions={"open": {"closed"}}, action_states={"close": "closed"},
        fields=("priority", "assignee", "note", "extra"),
        summary_fields=("priority", "assignee"),
    )
    workflow_spec.register_spec(spec)
    try:
        box_registry.create_box("ticket", {
            "id": "TK-1", "organization_id": ORG,
            "priority": "high", "assignee": "sam", "note": "x", "extra": "y",
        }, db)
        s = build_box_summary("TK-1", db=db, box_type="ticket")
        # only the declared summary fields, in declared order
        assert list(s.key_fields.keys()) == ["priority", "assignee"]
        assert s.key_fields["priority"] == "high"
    finally:
        workflow_spec.unregister_spec("ticket")


def test_condition_guards_a_transition(db):
    # A spec-declared condition ("amount <= 1000") gates the submitted->approved
    # edge, evaluated by the safe expression layer against the box's data. No
    # bespoke Python, no WASM.
    spec = WorkflowSpec(
        box_type="expense_claim",
        url_slug="expense-claims",
        states=("submitted", "approved", "rejected"),
        initial_state="submitted",
        terminal_states=("approved", "rejected"),
        transitions={"submitted": {"approved", "rejected"}},
        action_states={"approve": "approved", "reject": "rejected"},
        fields=("amount",),
        conditions={"submitted->approved": "amount <= 1000"},
    )
    workflow_spec.register_spec(spec)
    try:
        # within policy -> guard passes
        box_registry.create_box(
            "expense_claim", {"id": "EX-ok", "organization_id": ORG, "amount": 500}, db,
        )
        box_registry.update_box("expense_claim", "EX-ok", db, state="approved", actor_id="mgr")
        assert box_registry.get_box("expense_claim", "EX-ok", db)["state"] == "approved"

        # over policy -> guard blocks the transition (vetoed, like a hook deny)
        from solden.core.hooks.dispatcher import HookDenied
        box_registry.create_box(
            "expense_claim", {"id": "EX-no", "organization_id": ORG, "amount": 5000}, db,
        )
        with pytest.raises(HookDenied):
            box_registry.update_box("expense_claim", "EX-no", db, state="approved", actor_id="mgr")
        assert box_registry.get_box("expense_claim", "EX-no", db)["state"] == "submitted"
    finally:
        workflow_spec.unregister_spec("expense_claim")


def test_invalid_condition_is_rejected_at_registration():
    # A condition that isn't a safe expression is caught at spec validation.
    bad_expr = WorkflowSpec(
        box_type="bad_cond", url_slug="bad-cond",
        states=("a", "b"), initial_state="a", terminal_states=("b",),
        transitions={"a": {"b"}}, action_states={"go": "b"},
        conditions={"a->b": "__import__('os').system('rm -rf /')"},
    )
    assert any(
        "not a valid expression" in e for e in workflow_spec.validate_spec(bad_expr)
    )
    # A condition key that isn't a transition edge is caught too.
    bad_key = WorkflowSpec(
        box_type="bad_cond2", url_slug="bad-cond2",
        states=("a", "b"), initial_state="a", terminal_states=("b",),
        transitions={"a": {"b"}}, action_states={"go": "b"},
        conditions={"not_an_edge": "1 == 1"},
    )
    assert any("transition edge" in e for e in workflow_spec.validate_spec(bad_key))


def test_full_runtime_for_a_declared_type_end_to_end(db, monkeypatch):
    # The capstone: ONE declared type, zero bespoke Python, gets the agent's
    # full runtime — read (extraction), guard (condition), drive (engine),
    # and exception-handle (box_exception) — plus a spec-driven summary.
    spec = WorkflowSpec(
        box_type="grant_app",
        url_slug="grant-apps",
        states=("received", "validated", "approved", "blocked"),
        initial_state="received",
        terminal_states=("approved",),
        transitions={
            "received": {"validated", "blocked"},
            "validated": {"approved", "blocked"},
            "blocked": {"received"},
        },
        action_states={
            "validate": "validated", "approve": "approved",
            "block": "blocked", "reopen": "received",
        },
        fields=("applicant", "amount"),
        llm_fields=(
            {"name": "applicant", "type": "string", "description": "who applied"},
            {"name": "amount", "type": "number", "description": "requested amount"},
        ),
        conditions={"received->validated": "amount <= 10000"},
        exception_state="blocked",
        summary_fields=("applicant", "amount"),
    )
    workflow_spec.register_spec(spec)
    try:
        # 1) READ: the agent extracts the declared fields from raw text.
        import solden.core.llm_gateway as gw

        def fake_call_sync(action, messages, **k):
            return type("R", (), {"content": '{"applicant":"Acme","amount":5000}'})()
        monkeypatch.setattr(gw.get_llm_gateway(), "call_sync", fake_call_sync, raising=True)
        from solden.services.box_extraction import extract_box_fields
        data = extract_box_fields("grant_app", ORG, text="Acme requests $5,000")
        assert data == {"applicant": "Acme", "amount": 5000}
        box_registry.create_box("grant_app", {"id": "GA-1", "organization_id": ORG, **data}, db)

        # 2) GUARD + DRIVE: amount<=10000 passes the condition -> engine validates.
        engine = CoordinationEngine(db=db, organization_id=ORG)
        ok = asyncio.run(engine.execute(Plan(
            event_type="grant_decision",
            actions=[Action("move_box_stage", "DET", {"target": "validated", "actor_id": "officer"})],
            box_id="GA-1", box_type="grant_app", organization_id=ORG,
        )))
        assert ok.status == "completed"
        assert box_registry.get_box("grant_app", "GA-1", db)["state"] == "validated"

        # GUARD blocks an over-threshold box driven through the engine.
        box_registry.create_box("grant_app", {
            "id": "GA-2", "organization_id": ORG, "applicant": "BigCo", "amount": 50000,
        }, db)
        blocked = asyncio.run(engine.execute(Plan(
            event_type="grant_decision",
            actions=[Action("move_box_stage", "DET", {"target": "validated", "actor_id": "officer"})],
            box_id="GA-2", box_type="grant_app", organization_id=ORG,
        )))
        assert blocked.status == "failed"
        # The guard denied the validate; the engine then parks the box in its
        # declared exception_state (and raises a box_exception) for a human.
        assert box_registry.get_box("grant_app", "GA-2", db)["state"] == "blocked"
        ga2_excs = db.list_box_exceptions(box_id="GA-2", box_type="grant_app")
        assert any(e.get("exception_type") == "grant_app_exception" for e in ga2_excs)

        # 3) EXCEPTION: entering the declared exception_state raises a box_exception.
        box_registry.update_box(
            "grant_app", "GA-1", db, state="blocked", actor_id="officer", reason="needs review",
        )
        excs = db.list_box_exceptions(box_id="GA-1", box_type="grant_app")
        assert any(e.get("exception_type") == "grant_app_exception" for e in excs)

        # 4) SUMMARY honors the spec's declared summary_fields.
        from solden.core.box_summary import build_box_summary
        s = build_box_summary("GA-1", db=db, box_type="grant_app")
        assert list(s.key_fields.keys()) == ["applicant", "amount"]
    finally:
        workflow_spec.unregister_spec("grant_app")


def test_engine_moves_declarative_box_to_declared_exception_state(db):
    # Regression for the _move_to_exception bug: a declarative type WITH a
    # declared exception_state must actually land there on failure (the engine
    # used to pass an AP-only exception_reason kwarg that update_box rejected for
    # the boxes table, so the box silently never moved). Re-entry dedups to one
    # box_exception (stable idempotency key).
    spec = WorkflowSpec(
        box_type="review_flow", url_slug="review-flows",
        states=("draft", "in_review", "approved", "stuck"),
        initial_state="draft", terminal_states=("approved",),
        transitions={
            "draft": {"in_review", "stuck"},
            "in_review": {"approved", "stuck"},
            "stuck": {"draft"},
        },
        action_states={"submit": "in_review", "approve": "approved",
                       "park": "stuck", "reopen": "draft"},
        exception_state="stuck",
    )
    workflow_spec.register_spec(spec)
    try:
        box_registry.create_box("review_flow", {"id": "RF-1", "organization_id": ORG}, db)
        engine = CoordinationEngine(db=db, organization_id=ORG)
        # Illegal move (draft->approved) fails -> engine routes to exception_state.
        r = asyncio.run(engine.execute(Plan(
            event_type="review",
            actions=[Action("move_box_stage", "DET", {"target": "approved", "actor_id": "u"})],
            box_id="RF-1", box_type="review_flow", organization_id=ORG,
        )))
        assert r.status == "failed"
        assert box_registry.get_box("review_flow", "RF-1", db)["state"] == "stuck"
        excs = db.list_box_exceptions(box_id="RF-1", box_type="review_flow")
        assert any(e.get("exception_type") == "review_flow_exception" for e in excs)

        # Re-enter the exception state -> still one exception row (stable key).
        box_registry.update_box("review_flow", "RF-1", db, state="draft", actor_id="u")
        box_registry.update_box("review_flow", "RF-1", db, state="stuck", actor_id="u")
        excs2 = db.list_box_exceptions(box_id="RF-1", box_type="review_flow")
        only = [e for e in excs2 if e.get("exception_type") == "review_flow_exception"]
        assert len(only) == 1
    finally:
        workflow_spec.unregister_spec("review_flow")


def test_on_enter_condition_key_is_accepted():
    # on_enter:{state} guards are honored by the dispatcher, so validate_spec
    # must accept them (not only "from->to" edges).
    good = WorkflowSpec(
        box_type="oe", url_slug="oe", states=("open", "closed"), initial_state="open",
        terminal_states=("closed",), transitions={"open": {"closed"}},
        action_states={"go": "closed"},
        fields=("amount",), conditions={"on_enter:closed": "amount <= 100"},
    )
    assert workflow_spec.validate_spec(good) == []
    bad = WorkflowSpec(
        box_type="oe2", url_slug="oe2", states=("open", "closed"), initial_state="open",
        terminal_states=("closed",), transitions={"open": {"closed"}},
        action_states={"go": "closed"},
        conditions={"on_enter:nope": "1 == 1"},
    )
    assert any("not declared" in e for e in workflow_spec.validate_spec(bad))


def test_engine_exception_path_for_typeless_stall_state(db):
    # contract_review has exception_state=None; an illegal move must raise a
    # box_exception, NOT attempt the illegal state move.
    _box(db, box_id="CR-7")
    engine = CoordinationEngine(db=db, organization_id=ORG)
    plan = Plan(
        event_type="contract_decision",
        actions=[Action("move_box_stage", "DET", {"target": "approved", "actor_id": "gc"})],
        box_id="CR-7",
        box_type="contract_review",
        organization_id=ORG,
    )
    result = asyncio.run(engine.execute(plan))
    assert result.status == "failed"   # draft->approved is illegal (must pass in_review)
    loaded = box_registry.get_box("contract_review", "CR-7", db)
    assert loaded["state"] == "draft"  # unchanged
    excs = db.list_box_exceptions(box_id="CR-7", box_type="contract_review")
    assert any(e.get("exception_type") == "action_failed" for e in excs)
