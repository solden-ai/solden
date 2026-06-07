from __future__ import annotations

from solden.core import database as db_module
from solden.services.memory_invariants import memory_event_invariant_violations


def test_payment_status_change_commits_operational_memory(postgres_test_db):
    db = db_module.get_db()
    db.initialize()

    payment = db.create_payment({
        "ap_item_id": "AP-payment-memory",
        "organization_id": "org-payment-memory",
        "vendor_name": "Acme Payments",
        "amount": 1250.0,
        "currency": "USD",
        "status": "ready_for_payment",
    })

    updated = db.update_payment(
        payment["id"],
        status="scheduled",
        payment_method="ach",
        notes="Scheduled by finance lead.",
        _actor_type="user",
        _actor_id="finance@example.com",
        _source="workspace_payments",
    )

    assert updated["status"] == "scheduled"
    events = db.list_box_audit_events("payment", payment["id"])
    audit = next(
        event for event in events
        if event.get("event_type") == "payment_status_changed"
    )
    assert audit["actor_id"] == "finance@example.com"
    assert audit["from_state"] == "ready_for_payment"
    assert audit["to_state"] == "scheduled"
    assert memory_event_invariant_violations(audit["payload_json"]) == []

    memory_event = audit["payload_json"]["memory_event"]
    assert memory_event["work_item"]["box_type"] == "payment"
    assert memory_event["work_item"]["box_id"] == payment["id"]
    assert memory_event["state"]["before"] == "ready_for_payment"
    assert memory_event["state"]["after"] == "scheduled"
    assert memory_event["source"]["surface"] == "workspace_payments"
