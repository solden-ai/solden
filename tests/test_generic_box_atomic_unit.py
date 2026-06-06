"""Unit fence for declarative Box state+audit atomicity.

These tests avoid Postgres/Docker by exercising GenericBoxStore with a tiny
transactional fake. The invariant is the product contract: a generic Box may
not be created or moved without the matching audit row committing in the same
transaction.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from solden.core import workflow_spec
from solden.core.stores.generic_box_store import GenericBoxStore
from solden.core.workflow_spec import WorkflowSpec


SPEC = WorkflowSpec(
    box_type="unit_review",
    url_slug="unit-reviews",
    states=("draft", "review", "done"),
    initial_state="draft",
    terminal_states=("done",),
    transitions={"draft": {"review"}, "review": {"done"}},
    action_states={"submit": "review", "finish": "done"},
)


@pytest.fixture(autouse=True)
def _register_spec():
    workflow_spec.register_spec(SPEC)
    try:
        yield
    finally:
        workflow_spec.unregister_spec("unit_review")


class _FakeGenericDB(GenericBoxStore):
    def __init__(self, *, fail_audit: bool = False):
        self.fail_audit = fail_audit
        self.boxes: Dict[str, Dict[str, Any]] = {}
        self.audit_events: List[Dict[str, Any]] = []
        self.connections: List[_FakeConn] = []
        self.webhook_events: List[str] = []

    def initialize(self):
        return None

    def connect(self):
        conn = _FakeConn(self)
        self.connections.append(conn)
        return conn

    def _enqueue_generic_audit_webhook(self, event_id):
        if event_id:
            self.webhook_events.append(event_id)


class _FakeConn:
    def __init__(self, parent: _FakeGenericDB):
        self.parent = parent
        self.pending_boxes: Dict[str, Dict[str, Any]] = {}
        self.pending_audits: List[Dict[str, Any]] = []
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.parent.boxes.update({k: dict(v) for k, v in self.pending_boxes.items()})
        self.parent.audit_events.extend(dict(v) for v in self.pending_audits)
        self.pending_boxes.clear()
        self.pending_audits.clear()
        self.commits += 1

    def rollback(self):
        self.pending_boxes.clear()
        self.pending_audits.clear()
        self.rollbacks += 1


class _FakeCursor:
    def __init__(self, conn: _FakeConn):
        self.conn = conn
        self._last: List[Dict[str, Any]] = []

    def execute(self, sql: str, params=None):
        normalized = " ".join(sql.split()).lower()
        params = list(params or [])

        if normalized.startswith("insert into boxes"):
            box_id, org, box_type, state, spec_version, data_json, created_at, updated_at = params
            self.conn.pending_boxes[box_id] = {
                "id": box_id,
                "organization_id": org,
                "box_type": box_type,
                "state": state,
                "spec_version": spec_version,
                "data": data_json,
                "created_at": created_at,
                "updated_at": updated_at,
            }
            self._last = []
            return

        if normalized.startswith("select * from boxes where id"):
            box_id = params[0]
            row = self.conn.pending_boxes.get(box_id) or self.conn.parent.boxes.get(box_id)
            self._last = [dict(row)] if row else []
            return

        if normalized.startswith("select * from boxes where box_type"):
            box_type, org, limit = params
            rows = [
                dict(row)
                for row in self.conn.parent.boxes.values()
                if row.get("box_type") == box_type and row.get("organization_id") == org
            ]
            self._last = rows[: int(limit)]
            return

        if normalized.startswith("update boxes set state"):
            has_data_patch = "data = %s::jsonb" in normalized
            if has_data_patch:
                target_state, data_json, updated_at, box_id = params
            else:
                target_state, updated_at, box_id = params
                current = self.conn.pending_boxes.get(box_id) or self.conn.parent.boxes[box_id]
                data_json = current.get("data") or "{}"
            current = dict(self.conn.pending_boxes.get(box_id) or self.conn.parent.boxes[box_id])
            current.update({
                "state": target_state,
                "data": data_json,
                "updated_at": updated_at,
            })
            self.conn.pending_boxes[box_id] = current
            self._last = []
            return

        if normalized.startswith("insert into audit_events"):
            if self.conn.parent.fail_audit:
                raise RuntimeError("simulated audit insert failure")
            (
                event_id, box_id, box_type, event_type, prev_state, new_state,
                actor_type, actor_id, payload_json, external_refs, idempotency_key,
                source, correlation_id, workflow_id, run_id, decision_reason,
                governance_verdict, agent_confidence, organization_id, entity_id,
                policy_version, agent_version, capability_id, capability_version,
                tool_scope, ts,
            ) = params
            self.conn.pending_audits.append({
                "id": event_id,
                "box_id": box_id,
                "box_type": box_type,
                "event_type": event_type,
                "prev_state": prev_state,
                "new_state": new_state,
                "actor_type": actor_type,
                "actor_id": actor_id,
                "payload_json": json.loads(payload_json or "{}"),
                "external_refs": json.loads(external_refs or "{}"),
                "idempotency_key": idempotency_key,
                "source": source,
                "correlation_id": correlation_id,
                "workflow_id": workflow_id,
                "run_id": run_id,
                "decision_reason": decision_reason,
                "governance_verdict": governance_verdict,
                "agent_confidence": agent_confidence,
                "organization_id": organization_id,
                "entity_id": entity_id,
                "policy_version": policy_version,
                "agent_version": agent_version,
                "capability_id": capability_id,
                "capability_version": capability_version,
                "tool_scope": tool_scope,
                "ts": ts,
            })
            self._last = []
            return

        raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self):
        return self._last[0] if self._last else None

    def fetchall(self):
        return list(self._last)


def test_create_generic_box_rolls_back_when_audit_insert_fails():
    db = _FakeGenericDB(fail_audit=True)

    with pytest.raises(RuntimeError, match="audit insert failure"):
        db.create_generic_box("unit_review", {
            "id": "UR-create",
            "organization_id": "org-unit",
            "title": "Contract",
        })

    assert "UR-create" not in db.boxes
    assert db.audit_events == []
    assert db.connections[-1].rollbacks == 1


def test_update_generic_box_state_rolls_back_when_audit_insert_fails():
    db = _FakeGenericDB(fail_audit=True)
    db.boxes["UR-update"] = {
        "id": "UR-update",
        "organization_id": "org-unit",
        "box_type": "unit_review",
        "state": "draft",
        "spec_version": 1,
        "data": json.dumps({"title": "Contract"}),
        "created_at": "now",
        "updated_at": "now",
    }

    with pytest.raises(RuntimeError, match="audit insert failure"):
        db.update_generic_box_state(
            "unit_review",
            "UR-update",
            "review",
            actor_id="legal@example.com",
        )

    assert db.boxes["UR-update"]["state"] == "draft"
    assert db.audit_events == []
    assert db.connections[-1].rollbacks == 1


def test_update_generic_box_state_commits_state_and_audit_together():
    db = _FakeGenericDB()
    db.boxes["UR-ok"] = {
        "id": "UR-ok",
        "organization_id": "org-unit",
        "box_type": "unit_review",
        "state": "draft",
        "spec_version": 1,
        "data": json.dumps({"title": "Contract"}),
        "created_at": "now",
        "updated_at": "now",
    }

    updated = db.update_generic_box_state(
        "unit_review",
        "UR-ok",
        "review",
        actor_id="legal@example.com",
        reason="ready",
    )

    assert updated["state"] == "review"
    assert db.audit_events[-1]["event_type"] == "unit_review_review"
    assert db.audit_events[-1]["prev_state"] == "draft"
    assert db.audit_events[-1]["new_state"] == "review"
    assert db.audit_events[-1]["decision_reason"] == "ready"
    assert db.audit_events[-1]["payload_json"]["memory_event"]["event_type"] == "review"
    assert db.audit_events[-1]["payload_json"]["memory_event"]["state"]["before"] == "draft"
    assert db.audit_events[-1]["payload_json"]["memory_event"]["state"]["after"] == "review"
    assert db.audit_events[-1]["payload_json"]["decision_context"]["ui_surface"] == "workspace_workflow"
    assert db.webhook_events == [db.audit_events[-1]["id"]]
