"""GenericBoxStore — CRUD for declarative WorkflowSpec Box types.

The three original Box types each own a bespoke table. Declarative types
(defined by a :class:`solden.core.workflow_spec.WorkflowSpec`) instead share
the single ``boxes`` table: ``box_type`` names the type, ``state`` carries the
lifecycle position, ``data`` (JSONB) holds the type's declared fields, and
``spec_version`` pins the Box to the spec version it was created under.

State transitions go through :func:`update_generic_box_state`, which resolves
the Box's *pinned* spec version, validates the edge against that spec's
transition graph, and appends a typed ``audit_events`` row through the same
funnel AP / bank_match / purchase_order use — so the audit hash-chain, the
exception queue, and the export graph treat a declared Box like any other.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from solden.core.workflow_spec import (
    RESERVED_DATA_KEYS,
    IllegalWorkflowTransitionError,
    resolve_spec,
    validate_spec_transition,
)

logger = logging.getLogger(__name__)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _generic_memory_owner(
    existing: Dict[str, Any],
    patch: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Best-effort owner inference for declarative Box memory events."""
    merged = {**(existing or {}), **(patch or {})}
    for key in (
        "owner",
        "owner_email",
        "owner_label",
        "assignee_email",
        "assigned_to_email",
        "assigned_to",
        "approver_email",
        "approver",
    ):
        raw = merged.get(key)
        if isinstance(raw, dict):
            return {str(k): v for k, v in raw.items() if v not in (None, "", [], {})}
        text = _clean_text(raw)
        if not text:
            continue
        if "@" in text:
            return {"email": text, "label": text}
        return {"label": text}
    return None


def _generic_dependency_payload(
    *,
    provided: Any,
    owner: Optional[Dict[str, Any]],
    reason: str,
    box_type: str,
    target_state: str,
    exception_state: Optional[str],
) -> Optional[Any]:
    if provided not in (None, "", [], {}):
        return provided
    if exception_state and target_state == exception_state:
        owner_label = ""
        if isinstance(owner, dict):
            owner_label = _clean_text(owner.get("label") or owner.get("email"))
        return {
            "type": "blocker",
            "owner": owner_label or "Assigned owner",
            "reason": reason or f"{box_type} entered {target_state}",
        }
    return None


class GenericBoxStore:
    """Mixin: declarative-Box CRUD over the ``boxes`` table. Combined into SoldenDB."""

    def create_generic_box(
        self,
        box_type: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Insert a new declarative Box in its spec's initial state.

        ``payload`` must carry ``organization_id``; everything not a reserved
        column becomes the Box's ``data``. The Box always enters at the spec's
        ``initial_state`` (a caller-supplied ``state`` is ignored), mirroring
        the controlled-entry rule the bespoke stores enforce.
        """
        self.initialize()
        organization_id = payload.get("organization_id")
        if not organization_id:
            raise ValueError("create_generic_box requires organization_id")

        spec = resolve_spec(box_type, organization_id)
        if spec is None:
            raise ValueError(f"No WorkflowSpec registered for box_type={box_type!r}")

        box_id = payload.get("id") or f"BX-{uuid.uuid4().hex[:16]}"
        now = datetime.now(timezone.utc).isoformat()
        state = spec.initial_state
        # Pin to the version the active spec resolved at (1 for code built-ins).
        spec_version = int(payload.get("spec_version") or getattr(spec, "version", 1) or 1)

        data: Dict[str, Any] = {}
        if isinstance(payload.get("data"), dict):
            data.update(payload["data"])
        for k, v in payload.items():
            if k not in RESERVED_DATA_KEYS:
                data[k] = v

        sql = """
            INSERT INTO boxes
            (id, organization_id, box_type, state, spec_version, data,
             created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
        """
        event_id: Optional[str] = None
        with self.connect() as conn:
            try:
                cur = conn.cursor()
                cur.execute(sql, (
                    box_id, organization_id, box_type, state, spec_version,
                    json.dumps(data), now, now,
                ))
                event_id = self._insert_generic_audit_event_txn(conn, {
                    "box_id": box_id,
                    "box_type": box_type,
                    "event_type": f"{box_type}_created",
                    "to_state": state,
                    "actor_type": "system",
                    "actor_id": payload.get("created_by") or "system",
                    "organization_id": organization_id,
                    "policy_version": spec.policy_version,
                    "payload_json": {"spec_version": spec_version},
                    "idempotency_key": f"box-created:{box_id}",
                })
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise

        self._enqueue_generic_audit_webhook(event_id)

        return self.get_generic_box(box_type, box_id)  # type: ignore[return-value]

    def _insert_generic_audit_event_txn(
        self,
        conn: Any,
        payload: Dict[str, Any],
    ) -> str:
        """Insert one audit row on the caller's open transaction.

        Generic Boxes do not get to move state without the timeline row that
        proves the move. ``append_audit_event`` owns the public audit funnel,
        but it opens and commits its own connection. Declarative workflows need
        the stricter AP invariant here: row mutation and audit insert share one
        transaction, and the caller commits only after both statements land.
        """
        event_id = str(payload.get("id") or f"EVT-{uuid.uuid4().hex}")
        now = payload.get("ts") or datetime.now(timezone.utc).isoformat()
        raw_idempotency_key = payload.get("idempotency_key")
        idempotency_key: Optional[str] = (
            str(raw_idempotency_key).strip()
            if raw_idempotency_key is not None
            else ""
        ) or None

        payload_json = payload.get("payload_json")
        if payload_json is None:
            payload_json = {}
            reason = payload.get("reason")
            if reason:
                payload_json["reason"] = reason
            metadata = payload.get("metadata") or {}
            if isinstance(metadata, dict):
                payload_json.update(metadata)
        external_refs = payload.get("external_refs") or {}

        box_id = payload.get("box_id")
        box_type = payload.get("box_type")
        if box_id is None or box_type is None:
            raise ValueError(
                "_insert_generic_audit_event_txn requires box_id and box_type"
            )

        governance_verdict = payload.get("governance_verdict")
        agent_confidence = payload.get("agent_confidence")
        if isinstance(payload_json, dict):
            if governance_verdict is None:
                verdict_block = payload_json.get("governance_verdict")
                if isinstance(verdict_block, dict):
                    if verdict_block.get("should_execute") is False:
                        governance_verdict = "vetoed"
                    elif "should_execute" in verdict_block:
                        governance_verdict = "should_execute"
            if agent_confidence is None:
                for key in ("agent_confidence", "confidence_score", "confidence"):
                    value = payload_json.get(key)
                    if value is None:
                        continue
                    try:
                        agent_confidence = float(value)
                        break
                    except (TypeError, ValueError):
                        continue

        policy_version = payload.get("policy_version")
        if policy_version is None and isinstance(payload_json, dict):
            nested = payload_json.get("policy_version")
            if nested:
                policy_version = str(nested)

        capability_id = payload.get("capability_id")
        capability_version = payload.get("capability_version")
        tool_scope = payload.get("tool_scope")
        if isinstance(payload_json, dict):
            if capability_id is None:
                capability_id = payload_json.get("capability_id")
            if capability_version is None:
                capability_version = payload_json.get("capability_version")
            if tool_scope is None:
                tool_scope = payload_json.get("tool_scope")
        if tool_scope is None:
            tool_scope_json = None
        elif isinstance(tool_scope, str):
            tool_scope_json = tool_scope
        else:
            tool_scope_json = json.dumps(tool_scope)

        sql = """
            INSERT INTO audit_events
            (id, box_id, box_type, event_type, prev_state, new_state,
             actor_type, actor_id, payload_json, external_refs,
             idempotency_key, source, correlation_id, workflow_id, run_id,
             decision_reason, governance_verdict, agent_confidence,
             organization_id, entity_id, policy_version, agent_version,
             capability_id, capability_version, tool_scope, ts)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cur = conn.cursor()
        cur.execute(sql, (
            event_id,
            box_id,
            box_type,
            payload.get("event_type"),
            payload.get("from_state"),
            payload.get("to_state"),
            payload.get("actor_type"),
            payload.get("actor_id"),
            json.dumps(payload_json or {}),
            json.dumps(external_refs or {}),
            idempotency_key,
            payload.get("source"),
            payload.get("correlation_id"),
            payload.get("workflow_id"),
            payload.get("run_id"),
            payload.get("decision_reason") or payload.get("reason"),
            governance_verdict,
            agent_confidence,
            payload.get("organization_id"),
            payload.get("entity_id"),
            policy_version,
            payload.get("agent_version"),
            capability_id,
            capability_version,
            tool_scope_json,
            now,
        ))
        return event_id

    def _enqueue_generic_audit_webhook(self, event_id: Optional[str]) -> None:
        if not event_id:
            return
        try:
            from solden.services.celery_tasks import dispatch_audit_webhooks
            dispatch_audit_webhooks.delay(event_id)
        except Exception as fanout_exc:
            logger.warning(
                "[GenericBoxStore] webhook fan-out enqueue failed for %s: %s",
                event_id, fanout_exc,
            )

    def get_generic_box(
        self,
        box_type: str,
        box_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Return one declarative Box by id, or None.

        The ``data`` JSONB is merged up into the row dict so generic readers
        (engine, box_summary) can read declared fields by key — but the
        authoritative native columns always win, so a ``data`` payload can
        never shadow ``state`` / ``id`` / ``organization_id`` etc.
        """
        self.initialize()
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM boxes WHERE id = %s", (box_id,))
            row = cur.fetchone()
        if not row:
            return None
        return self._deserialize_generic_box(dict(row))

    def list_generic_boxes(
        self,
        box_type: str,
        organization_id: str,
        *,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """All Boxes of *box_type* in an org, newest first."""
        self.initialize()
        sql = (
            "SELECT * FROM boxes "
            "WHERE box_type = %s AND organization_id = %s "
            "ORDER BY created_at DESC LIMIT %s"
        )
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, (box_type, organization_id, int(limit)))
            rows = [dict(r) for r in cur.fetchall()]
        return [self._deserialize_generic_box(r) for r in rows]

    def update_generic_box_state(
        self,
        box_type: str,
        box_id: str,
        target_state: str,
        *,
        actor_id: str,
        reason: str = "",
        action: Optional[str] = None,
        source: str = "workspace_workflow",
        owner: Any = None,
        dependency: Any = None,
        evidence: Any = None,
        next_action: Optional[str] = None,
        summary: Optional[str] = None,
        source_refs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Advance a declarative Box, validating against its *pinned* spec.

        Raises :class:`IllegalWorkflowTransitionError` if the edge is invalid.
        Validation uses the spec version the Box was created under, not the
        org's currently-active version — so activating a new spec version
        never strands or illegally-moves in-flight Boxes.
        """
        if not str(actor_id or "").strip():
            raise ValueError(
                "update_generic_box_state requires a non-empty actor_id "
                "for audit-trail integrity"
            )
        existing = self.get_generic_box(box_type, box_id)
        if not existing:
            raise IllegalWorkflowTransitionError(f"box {box_id!r} not found")

        organization_id = existing.get("organization_id")
        spec_version = existing.get("spec_version")
        spec = resolve_spec(box_type, organization_id, spec_version)
        if spec is None:
            raise IllegalWorkflowTransitionError(
                f"No WorkflowSpec resolvable for box_type={box_type!r} "
                f"version={spec_version!r}"
            )

        current_state = str(existing.get("state") or "")
        if not validate_spec_transition(spec, current_state, target_state):
            raise IllegalWorkflowTransitionError(
                f"Illegal {box_type} transition: {current_state!r} -> "
                f"{target_state!r} (box_id={box_id})"
            )

        # Transition guards + hooks. Condition guards (safe expression layer)
        # are ALWAYS enforced; customer code hooks/effects require
        # FEATURE_WORKFLOW_HOOKS. A deny vetoes the transition; an allow may
        # carry a whitelisted data patch (reserved columns can never be patched).
        from solden.core.hooks.dispatcher import HookDenied, run_transition_hooks
        decision = run_transition_hooks(
            spec, existing, current_state, target_state, actor=actor_id,
        )
        if not decision.allow:
            raise HookDenied(decision.deny_reason or "hook_denied")
        patch = {
            k: v for k, v in (decision.data_patch or {}).items()
            if k not in RESERVED_DATA_KEYS
        }

        now = datetime.now(timezone.utc).isoformat()
        inferred_owner = owner if owner not in (None, "", [], {}) else _generic_memory_owner(existing, patch)
        inferred_dependency = _generic_dependency_payload(
            provided=dependency,
            owner=inferred_owner if isinstance(inferred_owner, dict) else None,
            reason=str(reason or "").strip(),
            box_type=box_type,
            target_state=target_state,
            exception_state=spec.exception_state,
        )
        memory_summary = (
            str(summary or "").strip()
            or str(reason or "").strip()
            or f"{box_type.replace('_', ' ')} moved to {target_state.replace('_', ' ')}."
        )
        memory_payload: Dict[str, Any] = {}
        try:
            from solden.services.memory_events import build_memory_event_payload

            memory_payload = build_memory_event_payload(
                box_type=box_type,
                box_id=box_id,
                organization_id=organization_id,
                event_type=str(action or target_state or "state_changed"),
                source=str(source or "").strip() or "workspace_workflow",
                actor_type="user",
                actor_id=actor_id,
                actor_label=actor_id,
                previous_state=current_state,
                resulting_state=target_state,
                owner=inferred_owner,
                dependency=inferred_dependency,
                decision={
                    "type": str(action or target_state or "state_changed"),
                    "resulting_state": target_state,
                },
                rationale=str(reason or "").strip() or memory_summary,
                evidence=evidence,
                human_confirmation_status="confirmed",
                next_action=next_action,
                summary=memory_summary,
                source_refs=source_refs,
                occurred_at=now,
            )
            memory_payload["spec_version"] = spec_version
        except Exception as exc:
            logger.debug(
                "[GenericBoxStore] memory payload build failed for %s/%s: %s",
                box_type, box_id, exc,
            )
            memory_payload = {"spec_version": spec_version}
        event_id: Optional[str] = None
        with self.connect() as conn:
            try:
                cur = conn.cursor()
                if patch:
                    merged = {**(existing.get("data") or {}), **patch}
                    cur.execute(
                        "UPDATE boxes SET state = %s, data = %s::jsonb, updated_at = %s "
                        "WHERE id = %s",
                        (target_state, json.dumps(merged), now, box_id),
                    )
                else:
                    cur.execute(
                        "UPDATE boxes SET state = %s, updated_at = %s WHERE id = %s",
                        (target_state, now, box_id),
                    )
                event_id = self._insert_generic_audit_event_txn(conn, {
                    "box_id": box_id,
                    "box_type": box_type,
                    "event_type": f"{box_type}_{target_state}",
                    "from_state": current_state,
                    "to_state": target_state,
                    "actor_type": "user",
                    "actor_id": actor_id,
                    "organization_id": organization_id,
                    "policy_version": spec.policy_version,
                    "decision_reason": reason or None,
                    "payload_json": memory_payload,
                    "external_refs": source_refs or {},
                    "source": str(source or "").strip() or "workspace_workflow",
                    "idempotency_key": f"box-{target_state}:{box_id}:{now}",
                })
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise

        self._enqueue_generic_audit_webhook(event_id)

        # §8 lifecycle parity: entering the spec's declared exception_state
        # raises a first-class box_exception, mirroring how AP raises one when
        # an ap_item lands in needs_info/failed_post. Same audit + webhook
        # funnel, so declarative Boxes show up in the exception queue too. The
        # mirror is best-effort: a failure here must not unwind the committed
        # transition.
        if (
            spec.exception_state
            and target_state == spec.exception_state
            and hasattr(self, "raise_box_exception")
        ):
            try:
                self.raise_box_exception(
                    box_id=box_id,
                    box_type=box_type,
                    organization_id=organization_id,
                    exception_type=f"{box_type}_exception",
                    reason=reason or f"Box entered exception state {target_state!r}",
                    metadata={"source": "update_generic_box_state", "state": target_state},
                    raised_by=str(actor_id or "system"),
                    raised_actor_type="user",
                    # Stable key (no timestamp): re-entering the exception state
                    # dedups to one row instead of spamming the queue/webhooks.
                    idempotency_key=f"{box_type}-excp:{box_id}:{target_state}",
                )
            except Exception as mirror_exc:
                logger.warning(
                    "[GenericBoxStore] box_exception mirror failed for %s: %s",
                    box_id, mirror_exc,
                )

        return self.get_generic_box(box_type, box_id)  # type: ignore[return-value]

    def record_hook_run(
        self,
        *,
        organization_id: str,
        box_type: str,
        box_id: str,
        hook_key: str,
        outcome: str,
        deny_reason: str = "",
        duration_ms: Optional[int] = None,
        error: str = "",
    ) -> None:
        """Append an audit row for one hook execution (best-effort)."""
        self.initialize()
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO workflow_hook_runs "
                "(id, organization_id, box_type, box_id, hook_key, outcome, "
                " deny_reason, duration_ms, error, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    f"HR-{uuid.uuid4().hex[:16]}", organization_id, box_type,
                    box_id, hook_key, outcome, deny_reason or None,
                    duration_ms, error or None, now,
                ),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _deserialize_generic_box(self, row: Dict[str, Any]) -> Dict[str, Any]:
        data = row.get("data")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                data = {}
        if not isinstance(data, dict):
            data = {}
        # Merge data FIRST, then let the authoritative native columns win.
        merged: Dict[str, Any] = dict(data)
        for key in (
            "id", "organization_id", "box_type", "state",
            "spec_version", "created_at", "updated_at",
        ):
            if key in row:
                merged[key] = row[key]
        merged["data"] = data
        return merged
