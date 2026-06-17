from __future__ import annotations

from solden.core import database as db_module
from solden.services import email_tasks
from solden.services.memory_invariants import memory_event_invariant_violations


def test_email_task_status_change_commits_operational_memory(postgres_test_db):
    db = db_module.get_db()
    db.initialize()
    email_tasks.init_tasks_db()

    task = email_tasks.create_task_from_email(
        email_id="msg-memory-1",
        email_subject="Close evidence needed",
        email_sender="controller@example.com",
        thread_id="thread-memory-1",
        created_by="controller@example.com",
        task_type="collect_docs",
        title="Collect close evidence",
        description="Attach the missing close evidence.",
        assignee_email="finance@example.com",
        organization_id="org-email-task-memory",
    )

    updated = email_tasks.update_task_status(
        task["task_id"],
        "completed",
        changed_by="finance@example.com",
        notes="Evidence attached.",
    )

    assert updated["status"] == "completed"
    events = db.list_box_audit_events("email_task", task["task_id"])
    audit = next(
        event for event in events
        if event.get("event_type") == "email_task_status_changed"
    )
    assert audit["actor_id"] == "finance@example.com"
    assert audit["from_state"] == "open"
    assert audit["to_state"] == "completed"
    assert memory_event_invariant_violations(audit["payload_json"]) == []

    memory_event = audit["payload_json"]["memory_event"]
    assert memory_event["work_item"]["box_type"] == "email_task"
    assert memory_event["work_item"]["box_id"] == task["task_id"]
    assert memory_event["state"]["before"] == "open"
    assert memory_event["state"]["after"] == "completed"


def test_email_task_assignment_commits_operational_memory(postgres_test_db):
    db = db_module.get_db()
    db.initialize()
    email_tasks.init_tasks_db()

    task = email_tasks.create_task_from_email(
        email_id="msg-memory-assign-1",
        email_subject="Invoice context needed",
        email_sender="controller@example.com",
        thread_id="thread-memory-assign-1",
        created_by="controller@example.com",
        task_type="follow_up",
        title="Confirm invoice owner",
        description="Confirm who owns the invoice follow-up.",
        assignee_email="finance@example.com",
        organization_id="org-email-task-memory",
    )

    updated = email_tasks.assign_task(
        task["task_id"],
        "ap-manager@example.com",
        assigned_by="controller@example.com",
    )

    assert updated["assignee_email"] == "ap-manager@example.com"
    events = db.list_box_audit_events("email_task", task["task_id"])
    audit = next(
        event for event in events
        if event.get("event_type") == "email_task_assigned"
    )
    assert audit["actor_id"] == "controller@example.com"
    assert memory_event_invariant_violations(audit["payload_json"]) == []

    memory_event = audit["payload_json"]["memory_event"]
    assert memory_event["work_item"]["box_type"] == "email_task"
    assert memory_event["work_item"]["box_id"] == task["task_id"]
    assert memory_event["decision"]["type"] == "email_task_assigned"
    assert memory_event["rationale"] == "controller@example.com assigned the task."
    assert audit["payload_json"]["task"]["assignee_email"] == "ap-manager@example.com"


def test_email_task_comment_commits_operational_memory(postgres_test_db):
    db = db_module.get_db()
    db.initialize()
    email_tasks.init_tasks_db()

    task = email_tasks.create_task_from_email(
        email_id="msg-memory-comment-1",
        email_subject="Approval evidence",
        email_sender="controller@example.com",
        thread_id="thread-memory-comment-1",
        created_by="controller@example.com",
        task_type="collect_docs",
        title="Attach approval evidence",
        description="Attach the approval email to the record.",
        assignee_email="finance@example.com",
        organization_id="org-email-task-memory",
    )

    comment = email_tasks.add_comment(
        task["task_id"],
        "finance@example.com",
        "Approval email attached to the source thread.",
    )

    assert comment["comment_id"].startswith("comment_")
    events = db.list_box_audit_events("email_task", task["task_id"])
    audit = next(
        event for event in events
        if event.get("event_type") == "email_task_comment_added"
    )
    assert audit["actor_id"] == "finance@example.com"
    assert memory_event_invariant_violations(audit["payload_json"]) == []

    memory_event = audit["payload_json"]["memory_event"]
    assert memory_event["work_item"]["box_type"] == "email_task"
    assert memory_event["work_item"]["box_id"] == task["task_id"]
    assert memory_event["decision"]["type"] == "email_task_comment_added"
    assert memory_event["rationale"] == "Approval email attached to the source thread."
