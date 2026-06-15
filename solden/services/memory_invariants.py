"""Operational-memory invariants.

This module is intentionally small and boring: memory is a product primitive,
so committed memory payloads must have a minimum canonical shape and primary
source surfaces must stay wired to the memory write path.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple


class MemoryInvariantError(ValueError):
    """Raised when a memory payload is not a canonical memory event."""


@dataclass(frozen=True)
class MemoryCoverageSurface:
    name: str
    path: str
    required_tokens: Tuple[str, ...]


@dataclass(frozen=True)
class MemoryExecutionCoverage:
    name: str
    source_path: str
    test_path: str
    required_source_tokens: Tuple[str, ...]
    required_test_tokens: Tuple[str, ...]


PRIMARY_MEMORY_COVERAGE_SURFACES: Tuple[MemoryCoverageSurface, ...] = (
    MemoryCoverageSurface(
        name="audit_memory_promoter",
        path="solden/services/audit_memory.py",
        required_tokens=(
            "ensure_memory_payload_for_audit_event",
            "build_memory_event_payload",
            "assert_memory_event_payload",
        ),
    ),
    MemoryCoverageSurface(
        name="runtime_intents",
        path="solden/services/finance_agent_runtime.py",
        required_tokens=("_commit_intent_memory_event", "commit_runtime_memory_event"),
    ),
    MemoryCoverageSurface(
        name="audit_event_funnel",
        path="solden/core/stores/ap_store.py",
        required_tokens=(
            "_ensure_memory_payload_for_audit_event",
            "ensure_memory_payload_for_audit_event",
            "append_audit_event",
            "set_ap_item_owner_atomic",
        ),
    ),
    MemoryCoverageSurface(
        name="generic_workflow_atomic_funnel",
        path="solden/core/stores/generic_box_store.py",
        required_tokens=(
            "_insert_generic_audit_event_txn",
            "ensure_memory_payload_for_audit_event",
            "assert_memory_event_payload",
            "update_generic_box_state",
        ),
    ),
    MemoryCoverageSurface(
        name="purchase_order_box_state_funnel",
        path="solden/core/stores/purchase_order_store.py",
        required_tokens=("update_purchase_order_state", "append_audit_event", "purchase_order_"),
    ),
    MemoryCoverageSurface(
        name="bank_match_box_state_funnel",
        path="solden/core/stores/bank_match_store.py",
        required_tokens=("update_bank_match_state", "append_audit_event", "bank_match_"),
    ),
    MemoryCoverageSurface(
        name="box_lifecycle_exception_outcome_funnel",
        path="solden/core/stores/box_lifecycle_store.py",
        required_tokens=(
            "raise_box_exception",
            "resolve_box_exception",
            "record_box_outcome",
            "append_audit_event",
        ),
    ),
    MemoryCoverageSurface(
        name="erp_intake",
        path="solden/services/intake_adapter.py",
        required_tokens=("_capture_intake_memory_event", "capture_operational_memory_event"),
    ),
    MemoryCoverageSurface(
        name="outlook_processor",
        path="solden/services/outlook_email_processor.py",
        required_tokens=("_capture_outlook_memory_event", "capture_operational_memory_event"),
    ),
    MemoryCoverageSurface(
        name="slack_reply_sync",
        path="solden/api/slack_invoices.py",
        required_tokens=("slack_reply_synced", "capture_operational_memory_event"),
    ),
    MemoryCoverageSurface(
        name="slack_action_surface",
        path="solden/api/slack_invoices.py",
        required_tokens=("_dispatch_runtime_intent", "_audit_callback_event", "append_audit_event"),
    ),
    MemoryCoverageSurface(
        name="teams_action_surface",
        path="solden/api/teams_invoices.py",
        required_tokens=(
            "_dispatch_runtime_intent",
            "_audit_callback_event",
            "append_audit_event",
            "source_channel",
        ),
    ),
    MemoryCoverageSurface(
        name="peppol_import",
        path="solden/api/peppol.py",
        required_tokens=("peppol_intake_created", "capture_operational_memory_event"),
    ),
    MemoryCoverageSurface(
        name="ap_direct_action_routes",
        path="solden/api/ap_items_action_routes.py",
        required_tokens=(
            "_commit_ap_operational_memory",
            "commit_memory_event",
            "runtime.execute_intent",
            "append_audit_event",
        ),
    ),
    MemoryCoverageSurface(
        name="payment_request_lifecycle",
        path="solden/services/payment_request.py",
        required_tokens=(
            "_emit_audit",
            "box_type",
            "payment_request",
            "append_audit_event",
        ),
    ),
    MemoryCoverageSurface(
        name="payment_status_lifecycle",
        path="solden/core/stores/payment_store.py",
        required_tokens=(
            "update_payment",
            "payment_status_changed",
            "box_type",
            "payment",
            "append_audit_event",
        ),
    ),
    MemoryCoverageSurface(
        name="email_task_lifecycle",
        path="solden/services/email_tasks.py",
        required_tokens=(
            "_append_task_memory_event",
            "email_task_created",
            "email_task_status_changed",
            "append_audit_event",
        ),
    ),
    MemoryCoverageSurface(
        name="workflow_routes_generic_state_api",
        path="solden/api/workflow_routes.py",
        required_tokens=("update_generic_box_state", "actor_id", "reason"),
    ),
    MemoryCoverageSurface(
        name="workspace_capture_api",
        path="solden/api/workspace_records.py",
        required_tokens=("/memory-events/capture", "capture_operational_memory_event"),
    ),
    MemoryCoverageSurface(
        name="gmail_extension_capture_api",
        path="solden/api/gmail_extension.py",
        required_tokens=("/memory-events/capture", "capture_operational_memory_event"),
    ),
    MemoryCoverageSurface(
        name="surface_memory_projection",
        path="solden/services/memory_surface.py",
        required_tokens=(
            "build_surface_memory_snapshot",
            "memory_fact_pairs",
            "adaptive_card_memory_facts",
            "render_slack_memory_summary",
            "solden_memory_surface.v1",
        ),
    ),
    MemoryCoverageSurface(
        name="erp_memory_surface_api",
        path="solden/api/erp_memory_surface.py",
        required_tokens=(
            "build_box_operational_memory_record",
            "dispatch_runtime_intent",
            "erp_native_quickbooks",
            "erp_native_xero",
            "erp_native_sage_accounting",
        ),
    ),
)


PRIMARY_MEMORY_EXECUTION_COVERAGE: Tuple[MemoryExecutionCoverage, ...] = (
    MemoryExecutionCoverage(
        name="audit_memory_promoter",
        source_path="solden/services/audit_memory.py",
        test_path="tests/test_memory_layer_invariants.py",
        required_source_tokens=(
            "ensure_memory_payload_for_audit_event",
            "assert_memory_event_payload",
        ),
        required_test_tokens=(
            "test_thin_audit_rows_are_promoted_to_operational_memory",
            "assert_memory_event_payload",
        ),
    ),
    MemoryExecutionCoverage(
        name="runtime_intents",
        source_path="solden/services/finance_agent_runtime.py",
        test_path="tests/test_operational_memory.py",
        required_source_tokens=(
            "_commit_intent_memory_event",
            "commit_runtime_memory_event",
        ),
        required_test_tokens=(
            "test_runtime_intent_memory_event_captures_surface_action_context",
            "commit_runtime_memory_event",
        ),
    ),
    MemoryExecutionCoverage(
        name="audit_event_funnel",
        source_path="solden/core/stores/ap_store.py",
        test_path="tests/test_box_audit_reader.py",
        required_source_tokens=(
            "_ensure_memory_payload_for_audit_event",
            "append_audit_event",
        ),
        required_test_tokens=(
            "test_append_audit_event_promotes_plain_audit_row_to_memory_event",
            "db.append_audit_event",
        ),
    ),
    MemoryExecutionCoverage(
        name="generic_workflow_atomic_funnel",
        source_path="solden/core/stores/generic_box_store.py",
        test_path="tests/test_generic_box_atomic_unit.py",
        required_source_tokens=(
            "_insert_generic_audit_event_txn",
            "assert_memory_event_payload",
            "update_generic_box_state",
        ),
        required_test_tokens=(
            "test_update_generic_box_state_commits_state_and_audit_together",
            "payload_json",
            "memory_event",
        ),
    ),
    MemoryExecutionCoverage(
        name="purchase_order_box_state_funnel",
        source_path="solden/core/stores/purchase_order_store.py",
        test_path="tests/test_generic_engine_purchase_order.py",
        required_source_tokens=(
            "update_purchase_order_state",
            "append_audit_event",
            "record_box_outcome",
        ),
        required_test_tokens=(
            "test_update_box_advances_po_state",
            "memory_event_invariant_violations",
        ),
    ),
    MemoryExecutionCoverage(
        name="bank_match_box_state_funnel",
        source_path="solden/core/stores/bank_match_store.py",
        test_path="tests/test_generic_engine_bank_match.py",
        required_source_tokens=(
            "update_bank_match_state",
            "append_audit_event",
            "record_box_outcome",
        ),
        required_test_tokens=(
            "test_update_box_advances_bank_match_state",
            "memory_event_invariant_violations",
        ),
    ),
    MemoryExecutionCoverage(
        name="box_lifecycle_exception_outcome_funnel",
        source_path="solden/core/stores/box_lifecycle_store.py",
        test_path="tests/test_box_lifecycle_store.py",
        required_source_tokens=(
            "raise_box_exception",
            "resolve_box_exception",
            "record_box_outcome",
            "append_audit_event",
        ),
        required_test_tokens=(
            "test_outcome_emits_audit_event",
            "memory_event_invariant_violations",
        ),
    ),
    MemoryExecutionCoverage(
        name="erp_intake",
        source_path="solden/services/intake_adapter.py",
        test_path="tests/test_erp_native_intake_pipeline.py",
        required_source_tokens=(
            "_capture_intake_memory_event",
            "capture_operational_memory_event",
        ),
        required_test_tokens=(
            "memory_capture.assert_called_once",
            "erp_intake_created",
        ),
    ),
    MemoryExecutionCoverage(
        name="outlook_processor",
        source_path="solden/services/outlook_email_processor.py",
        test_path="tests/test_outlook_email_processor.py",
        required_source_tokens=(
            "_capture_outlook_memory_event",
            "capture_operational_memory_event",
        ),
        required_test_tokens=(
            "test_outlook_processor_captures_triaged_message_memory",
            "capture.assert_called_once",
        ),
    ),
    MemoryExecutionCoverage(
        name="slack_reply_sync",
        source_path="solden/api/slack_invoices.py",
        test_path="tests/test_slack_reply_memory_capture.py",
        required_source_tokens=(
            "slack_reply_synced",
            "capture_operational_memory_event",
        ),
        required_test_tokens=(
            "test_slack_reply_sync_captures_operational_memory_with_bot_token",
            "capture.assert_called_once",
        ),
    ),
    MemoryExecutionCoverage(
        name="slack_action_surface",
        source_path="solden/api/slack_invoices.py",
        test_path="tests/test_channel_approval_contract.py",
        required_source_tokens=(
            "_dispatch_runtime_intent",
            "_audit_callback_event",
            "append_audit_event",
        ),
        required_test_tokens=(
            "test_slack_interactive_request_info_duplicate_and_stale",
            "source_channel",
            "slack",
        ),
    ),
    MemoryExecutionCoverage(
        name="teams_action_surface",
        source_path="solden/api/teams_invoices.py",
        test_path="tests/test_teams_audit_integration.py",
        required_source_tokens=(
            "_dispatch_runtime_intent",
            "_audit_callback_event",
            "append_audit_event",
        ),
        required_test_tokens=(
            "test_teams_approve_dispatch_lands_ui_surface_teams",
            "memory_event_invariant_violations",
        ),
    ),
    MemoryExecutionCoverage(
        name="peppol_import",
        source_path="solden/api/peppol.py",
        test_path="tests/test_peppol_inbound.py",
        required_source_tokens=(
            "peppol_intake_created",
            "capture_operational_memory_event",
        ),
        required_test_tokens=(
            "test_api_import_creates_ap_item_with_vat_split",
            "no peppol memory event",
        ),
    ),
    MemoryExecutionCoverage(
        name="ap_direct_action_routes",
        source_path="solden/api/ap_items_action_routes.py",
        test_path="tests/test_ap_record_surfaces.py",
        required_source_tokens=(
            "_commit_ap_operational_memory",
            "commit_memory_event",
            "runtime.execute_intent",
        ),
        required_test_tokens=(
            "field-review/resolve",
            "field_correction",
            "memory_event_invariant_violations",
        ),
    ),
    MemoryExecutionCoverage(
        name="payment_request_lifecycle",
        source_path="solden/services/payment_request.py",
        test_path="tests/test_payment_request_persistence.py",
        required_source_tokens=(
            "_emit_audit",
            "payment_request",
            "append_audit_event",
        ),
        required_test_tokens=(
            "test_approve_persists_and_audits",
            "memory_event_invariant_violations",
        ),
    ),
    MemoryExecutionCoverage(
        name="payment_status_lifecycle",
        source_path="solden/core/stores/payment_store.py",
        test_path="tests/test_payment_memory_events.py",
        required_source_tokens=(
            "update_payment",
            "payment_status_changed",
            "append_audit_event",
        ),
        required_test_tokens=(
            "test_payment_status_change_commits_operational_memory",
            "memory_event_invariant_violations",
        ),
    ),
    MemoryExecutionCoverage(
        name="email_task_lifecycle",
        source_path="solden/services/email_tasks.py",
        test_path="tests/test_email_tasks_memory.py",
        required_source_tokens=(
            "_append_task_memory_event",
            "email_task_status_changed",
            "append_audit_event",
        ),
        required_test_tokens=(
            "test_email_task_status_change_commits_operational_memory",
            "memory_event_invariant_violations",
        ),
    ),
    MemoryExecutionCoverage(
        name="workspace_capture_api",
        source_path="solden/api/workspace_records.py",
        test_path="tests/test_workspace_records_api.py",
        required_source_tokens=(
            "/memory-events/capture",
            "capture_operational_memory_event",
        ),
        required_test_tokens=(
            "test_workspace_memory_capture_endpoint_commits_confirmed_context",
            "memory_event_invariant_violations",
        ),
    ),
    MemoryExecutionCoverage(
        name="gmail_extension_capture_api",
        source_path="solden/api/gmail_extension.py",
        test_path="tests/test_gmail_extension_memory_capture.py",
        required_source_tokens=(
            "/memory-events/capture",
            "capture_operational_memory_event",
        ),
        required_test_tokens=(
            "test_gmail_extension_memory_capture_endpoint_commits_confirmed_context",
            "memory_event_invariant_violations",
        ),
    ),
    MemoryExecutionCoverage(
        name="surface_memory_projection",
        source_path="solden/services/memory_surface.py",
        test_path="tests/test_operational_memory.py",
        required_source_tokens=(
            "build_surface_memory_snapshot",
            "adaptive_card_memory_facts",
            "render_slack_memory_summary",
        ),
        required_test_tokens=(
            "test_surface_memory_projection_exposes_one_contract_for_embedded_surfaces",
            "adaptive_card_memory_facts",
            "render_slack_memory_summary",
        ),
    ),
    MemoryExecutionCoverage(
        name="erp_memory_surface_api",
        source_path="solden/api/erp_memory_surface.py",
        test_path="tests/test_erp_memory_surface.py",
        required_source_tokens=(
            "build_box_operational_memory_record",
            "dispatch_runtime_intent",
            "erp_native_quickbooks",
            "erp_native_xero",
        ),
        required_test_tokens=(
            "test_quickbooks_erp_reference_returns_live_operational_memory",
            "test_xero_erp_reference_action_uses_xero_memory_surface",
        ),
    ),
)


# Vendor onboarding is intentionally excluded from primary coverage while it is
# dormant: its router is not mounted and its Box type is not registered. If that
# surface is reactivated, add it back with an executable transition regression.


NON_OPERATIONAL_MEMORY_BOX_TYPES: Tuple[str, ...] = (
    "organization",
    "vendor",
    "user",
    "workspace_audit",
    "audit_export",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def memory_event_missing_fields(payload_json: Dict[str, Any]) -> list[str]:
    payload = _dict(payload_json)
    memory_event = _dict(payload.get("memory_event"))
    work_item = _dict(memory_event.get("work_item"))
    source = _dict(memory_event.get("source"))
    decision = _dict(memory_event.get("decision"))
    evidence = _dict(memory_event.get("evidence"))
    quality = _dict(memory_event.get("quality"))
    missing: list[str] = []

    required_values = {
        "memory_event": memory_event,
        "memory_event.schema_version": memory_event.get("schema_version"),
        "memory_event.work_item.box_type": work_item.get("box_type"),
        "memory_event.work_item.box_id": work_item.get("box_id"),
        "memory_event.event_type": memory_event.get("event_type"),
        "memory_event.summary": memory_event.get("summary"),
        "memory_event.source.surface": source.get("surface"),
        "memory_event.source.captured_at": source.get("captured_at"),
        "memory_event.decision.type": decision.get("type"),
        "memory_event.evidence": evidence,
        "memory_event.evidence.captured_from": evidence.get("captured_from"),
        "memory_event.evidence.event_type": evidence.get("event_type"),
        "memory_event.quality": quality,
        "memory_event.quality.evidence_status": quality.get("evidence_status"),
        "memory_event.quality.verification_status": quality.get("verification_status"),
        "decision_context": payload.get("decision_context"),
        "summary": payload.get("summary"),
        "reason": payload.get("reason"),
    }
    for key, value in required_values.items():
        if isinstance(value, dict):
            if not value:
                missing.append(key)
        elif not _text(value):
            missing.append(key)
    return missing


def memory_event_invariant_violations(payload_json: Dict[str, Any]) -> list[str]:
    violations = memory_event_missing_fields(payload_json)
    payload = _dict(payload_json)
    memory_event = _dict(payload.get("memory_event"))
    quality = _dict(memory_event.get("quality"))

    confidence = memory_event.get("confidence")
    if confidence not in (None, ""):
        try:
            numeric = float(confidence)
        except (TypeError, ValueError):
            violations.append("memory_event.confidence must be numeric")
        else:
            if not math.isfinite(numeric) or numeric < 0 or numeric > 1:
                violations.append("memory_event.confidence must be between 0 and 1")

    quality_confidence = quality.get("confidence")
    if quality_confidence not in (None, ""):
        try:
            numeric = float(quality_confidence)
        except (TypeError, ValueError):
            violations.append("memory_event.quality.confidence must be numeric")
        else:
            if not math.isfinite(numeric) or numeric < 0 or numeric > 1:
                violations.append("memory_event.quality.confidence must be between 0 and 1")

    evidence_status = _text(quality.get("evidence_status"))
    if evidence_status and evidence_status not in {"linked", "provenance_only", "review_required"}:
        violations.append("memory_event.quality.evidence_status is invalid")

    return violations


def assert_memory_event_payload(payload_json: Dict[str, Any]) -> None:
    violations = memory_event_invariant_violations(payload_json)
    if violations:
        raise MemoryInvariantError(
            "memory_event_invariant_violation: " + ", ".join(violations)
        )


def audit_event_requires_operational_memory(*, box_type: Any, box_id: Any) -> bool:
    resolved_box_type = _text(box_type).lower()
    resolved_box_id = _text(box_id)
    if not resolved_box_type or not resolved_box_id:
        return False
    return resolved_box_type not in NON_OPERATIONAL_MEMORY_BOX_TYPES


def assert_work_item_audit_event_memory_payload(
    *,
    box_type: Any,
    box_id: Any,
    payload_json: Dict[str, Any],
) -> None:
    if not audit_event_requires_operational_memory(box_type=box_type, box_id=box_id):
        return
    assert_memory_event_payload(payload_json)


def missing_coverage_tokens(
    *,
    surface: MemoryCoverageSurface,
    source_text: str,
) -> list[str]:
    return [
        token
        for token in surface.required_tokens
        if token not in source_text
    ]


def all_coverage_paths(
    surfaces: Iterable[MemoryCoverageSurface] = PRIMARY_MEMORY_COVERAGE_SURFACES,
) -> list[str]:
    return [surface.path for surface in surfaces]


def missing_execution_coverage_tokens(
    *,
    coverage: MemoryExecutionCoverage,
    source_text: str,
    test_text: str,
) -> list[str]:
    missing = [
        f"source:{token}"
        for token in coverage.required_source_tokens
        if token not in source_text
    ]
    missing.extend(
        f"test:{token}"
        for token in coverage.required_test_tokens
        if token not in test_text
    )
    return missing
