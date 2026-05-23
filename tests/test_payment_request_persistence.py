"""Payment-request persistence + audit + tenant-isolation fence.

PaymentRequestService used to hold requests + their approve/reject/mark_paid
lifecycle in a process-memory dict — lost on restart, never audited, on a
financial-adjacent surface. These tests lock the DB-backed behavior.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from solden.core import database as db_module  # noqa: E402
from solden.services.payment_request import (  # noqa: E402
    PaymentRequestService, RequestStatus,
)


@pytest.fixture()
def db():
    inst = db_module.get_db()
    inst.initialize()
    return inst


def test_request_survives_a_fresh_service_instance(db):
    """The bug: a new service instance (≈ a restart) saw none of the prior
    requests because they lived in memory. Now they persist."""
    svc = PaymentRequestService("pr-org-a")
    req = svc.create_from_ui(
        user_email="op@a.com", user_name="Op", payee_name="Acme",
        amount=500.0, description="consulting",
    )
    # A brand-new service instance must still see it (read-through DB).
    fresh = PaymentRequestService("pr-org-a")
    loaded = fresh.get_request(req.request_id)
    assert loaded is not None
    assert loaded.payee_name == "Acme"
    assert loaded.amount == 500.0
    assert loaded.status == RequestStatus.PENDING


def test_approve_persists_and_audits(db):
    svc = PaymentRequestService("pr-org-a")
    req = svc.create_from_ui(
        user_email="op@a.com", user_name="Op", payee_name="Acme",
        amount=100.0, description="x",
    )
    svc.approve_request(req.request_id, approved_by="cfo@a.com", gl_code="6000")

    reloaded = PaymentRequestService("pr-org-a").get_request(req.request_id)
    assert reloaded.status == RequestStatus.APPROVED
    assert reloaded.approved_by == "cfo@a.com"
    assert reloaded.gl_code == "6000"

    # State change wrote an audit row.
    with db.connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT actor_id FROM audit_events WHERE organization_id = %s "
            "AND event_type = %s",
            ("pr-org-a", "payment_request_approved"),
        )
        rows = cur.fetchall()
    assert any(str(dict(r).get("actor_id")) == "cfo@a.com" for r in rows)


def test_reject_and_mark_paid_persist(db):
    svc = PaymentRequestService("pr-org-a")
    r1 = svc.create_from_ui(user_email="o@a.com", user_name="O", payee_name="V1",
                            amount=10.0, description="a")
    r2 = svc.create_from_ui(user_email="o@a.com", user_name="O", payee_name="V2",
                            amount=20.0, description="b")
    svc.reject_request(r1.request_id, rejected_by="m@a.com", reason="dup")
    svc.mark_paid(r2.request_id, payment_id="PAY-9")

    assert svc.get_request(r1.request_id).status == RequestStatus.REJECTED
    paid = svc.get_request(r2.request_id)
    assert paid.status == RequestStatus.PAID
    assert paid.metadata.get("payment_id") == "PAY-9"


def test_requests_are_org_scoped(db):
    a = PaymentRequestService("pr-org-a")
    b = PaymentRequestService("pr-org-b")
    req = a.create_from_ui(user_email="o@a.com", user_name="O", payee_name="SecretA",
                           amount=99.0, description="x")
    # Org B must not see org A's request.
    assert b.get_request(req.request_id) is None
    # And org B can't approve it (not found in its scope).
    with pytest.raises(ValueError):
        b.approve_request(req.request_id, approved_by="x@b.com")
    # Org A still sees it untouched.
    assert a.get_request(req.request_id).status == RequestStatus.PENDING
