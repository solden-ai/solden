"""AP learning-loop evaluation over operational memory and outcomes.

This is the first concrete slice of the "hill-climbing" system for the AP
wedge. It does not train a model. It turns real work traces into private eval
snapshots and company-level patterns that agents can later use and that pilots
can be scored against.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from solden.core.database import SoldenDB, get_db
from solden.core.org_utils import assert_org_id, coerce_org_id
from solden.services.agent_memory import AgentMemoryService
from solden.services.operational_memory import build_box_operational_memory_record


LEARNING_LOOP_CONTRACT = "solden_ap_learning_loop.v1"
PRIVATE_OUTCOME_EVAL_TYPE = "ap_private_outcome_eval"
DEFAULT_SCHEDULED_EVAL_WINDOW_DAYS = 30
DEFAULT_SCHEDULED_EVAL_LIMIT = 1000

_TERMINAL_STATES = {
    "closed",
    "rejected",
    "reversed",
    "posted_to_erp",
    "payment_executed",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_json_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _parse_iso(value: Any) -> Optional[datetime]:
    text = _text(value)
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _slug(value: Any) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", _text(value).lower()).strip("_")
    return token or "unknown"


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / max(1, denominator), 4)


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(value, maximum))


def _scheduled_org_ids_from_env() -> List[str]:
    raw = (
        os.getenv("SOLDEN_AP_LEARNING_LOOP_ORG_IDS")
        or os.getenv("AP_LEARNING_LOOP_ORG_IDS")
        or ""
    )
    org_ids: List[str] = []
    seen = set()
    for part in raw.split(","):
        org_id = coerce_org_id(part)
        if not org_id or org_id in seen:
            continue
        seen.add(org_id)
        org_ids.append(org_id)
    return org_ids


def _discover_scheduled_org_ids(db: SoldenDB) -> List[str]:
    org_ids: List[str] = []
    if hasattr(db, "list_organizations_with_ap_items"):
        try:
            org_ids.extend(db.list_organizations_with_ap_items() or [])
        except Exception:
            pass
    if not org_ids and hasattr(db, "list_organizations"):
        try:
            for row in db.list_organizations(limit=500) or []:
                if not isinstance(row, dict):
                    continue
                if row.get("is_active") is False or row.get("deleted_at"):
                    continue
                org_ids.append(row.get("id") or row.get("organization_id"))
        except Exception:
            pass

    normalized: List[str] = []
    seen = set()
    for org_id in org_ids:
        token = coerce_org_id(org_id)
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def _has_value(value: Any) -> bool:
    if value in (None, "", [], {}):
        return False
    if isinstance(value, dict):
        return any(_has_value(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_value(v) for v in value)
    return True


def _is_memory_event(event: Dict[str, Any]) -> bool:
    event_type = _text(event.get("event_type")).lower()
    if event_type.startswith("memory_event:"):
        return True
    payload = event.get("payload_json")
    payload = payload if isinstance(payload, dict) else _safe_json_dict(payload)
    return isinstance(payload.get("memory_event"), dict)


def _event_surface(event: Dict[str, Any]) -> str:
    payload = event.get("payload_json")
    payload = payload if isinstance(payload, dict) else _safe_json_dict(payload)
    memory_event = payload.get("memory_event") if isinstance(payload, dict) else {}
    if isinstance(memory_event, dict):
        source = memory_event.get("source") if isinstance(memory_event.get("source"), dict) else {}
        surface = _text(source.get("surface"))
        if surface:
            return surface
    decision_context = payload.get("decision_context") if isinstance(payload, dict) else {}
    if isinstance(decision_context, dict):
        surface = _text(decision_context.get("ui_surface"))
        if surface:
            return surface
    return _text(event.get("source")) or "unknown"


def _agent_observed_event(event: Dict[str, Any]) -> bool:
    return (
        _text(event.get("actor_type")).lower() == "agent"
        or _text(event.get("source")).lower().startswith("agent")
        or "agent" in _text(event.get("event_type")).lower()
    )


def _outcome_data(outcome: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(outcome, dict):
        return {}
    data = outcome.get("data")
    if isinstance(data, dict):
        return dict(data)
    return _safe_json_dict(outcome.get("data_json"))


def _memory_completeness(record: Dict[str, Any]) -> Tuple[float, List[str]]:
    context = record.get("context_summary") if isinstance(record, dict) else {}
    context = context if isinstance(context, dict) else {}
    evidence = context.get("evidence") if isinstance(context.get("evidence"), dict) else {}
    has_traceable_why = bool(
        record.get("decision_ledger")
        or record.get("open_exceptions")
        or record.get("outcome")
    )
    required = {
        "what_is_happening": context.get("what_is_happening"),
        "why_it_is_happening": (
            context.get("why_it_is_happening") if has_traceable_why else None
        ),
        "who_owns_it": context.get("who_owns_it"),
        "next_action": context.get("next_action"),
        "where_it_happened": context.get("where_it_happened"),
        "evidence": evidence,
    }
    missing = [key for key, value in required.items() if not _has_value(value)]
    score = round((len(required) - len(missing)) / len(required), 4)
    return score, missing


def _blocker_key(item: Dict[str, Any], record: Dict[str, Any]) -> str:
    context = record.get("context_summary") if isinstance(record, dict) else {}
    execution_state = record.get("execution_state") if isinstance(record, dict) else {}
    candidates = [
        item.get("exception_code"),
        _safe_json_dict(item.get("metadata")).get("exception_code"),
        context.get("why_it_is_happening") if isinstance(context, dict) else None,
        execution_state.get("waiting_reason") if isinstance(execution_state, dict) else None,
    ]
    for candidate in candidates:
        text = _text(candidate)
        if text:
            return text
    return "unknown"


class APLearningLoopService:
    """Build private evals and org-level learning summaries for AP."""

    def __init__(
        self,
        organization_id: str,
        *,
        db: Optional[SoldenDB] = None,
        agent_memory: Optional[AgentMemoryService] = None,
    ) -> None:
        self.organization_id = assert_org_id(
            organization_id, context="APLearningLoopService"
        )
        self.db = db or get_db()
        self.agent_memory = agent_memory or AgentMemoryService(
            self.organization_id, db=self.db
        )

    def _list_ap_items(
        self,
        *,
        limit: int,
        from_ts: Optional[str] = None,
        to_ts: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not hasattr(self.db, "list_ap_items"):
            return []
        rows = self.db.list_ap_items(self.organization_id, limit=max(1, int(limit)))
        parsed_from = _parse_iso(from_ts)
        parsed_to = _parse_iso(to_ts)
        filtered: List[Dict[str, Any]] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            item = dict(row)
            if entity_id and _text(item.get("entity_id")) != _text(entity_id):
                continue
            created_at = _parse_iso(item.get("created_at"))
            if parsed_from and created_at and created_at < parsed_from:
                continue
            if parsed_to and created_at and created_at >= parsed_to:
                continue
            filtered.append(item)
        return filtered

    def _list_outcomes(self, *, limit: int) -> Dict[str, Dict[str, Any]]:
        if not hasattr(self.db, "list_outcomes_by_type"):
            return {}
        rows = self.db.list_outcomes_by_type(
            self.organization_id,
            box_type="ap_item",
            limit=max(1, int(limit)),
        )
        outcomes: Dict[str, Dict[str, Any]] = {}
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            box_id = _text(row.get("box_id"))
            if box_id:
                outcomes[box_id] = dict(row)
        return outcomes

    def _list_events(self, item_id: str) -> List[Dict[str, Any]]:
        if not hasattr(self.db, "list_box_audit_events"):
            return []
        try:
            rows = self.db.list_box_audit_events(
                box_type="ap_item", box_id=item_id, limit=250, order="asc"
            )
        except Exception:
            return []
        return [dict(row) for row in rows or [] if isinstance(row, dict)]

    def _list_agent_memory_events(self, item_id: str) -> List[Dict[str, Any]]:
        try:
            rows = self.agent_memory.list_memory_events(ap_item_id=item_id)
        except Exception:
            return []
        return [dict(row) for row in rows or [] if isinstance(row, dict)]

    def _build_memory_record(
        self,
        *,
        item: Dict[str, Any],
        outcome: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        try:
            return build_box_operational_memory_record(
                db=self.db,
                box_type="ap_item",
                box_id=_text(item.get("id")),
                item=item,
                outcome=outcome,
            )
        except Exception:
            return {}

    def evaluate_private_outcomes(
        self,
        *,
        limit: int = 1000,
        persist: bool = True,
        from_ts: Optional[str] = None,
        to_ts: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Evaluate the AP wedge against customer-private outcome traces."""
        items = self._list_ap_items(
            limit=limit,
            from_ts=from_ts,
            to_ts=to_ts,
            entity_id=entity_id,
        )
        outcomes_by_id = self._list_outcomes(limit=limit)

        eval_cases: List[Dict[str, Any]] = []
        blocker_buckets: Dict[str, Dict[str, Any]] = {}
        vendor_buckets: Dict[str, Counter] = defaultdict(Counter)
        owner_buckets: Counter = Counter()
        surface_counts: Counter = Counter()
        total_memory_score = 0.0
        memory_event_items = 0
        evidence_linked_items = 0
        agent_trace_items = 0
        terminal_items = 0
        terminal_with_outcome = 0

        for item in items:
            item_id = _text(item.get("id"))
            if not item_id:
                continue
            outcome = outcomes_by_id.get(item_id)
            record = self._build_memory_record(item=item, outcome=outcome)
            events = self._list_events(item_id)
            agent_memory_events = self._list_agent_memory_events(item_id)
            memory_events = [event for event in events if _is_memory_event(event)]
            agent_events = [event for event in events if _agent_observed_event(event)]
            for event in events:
                surface_counts[_event_surface(event)] += 1

            memory_score, missing_context = _memory_completeness(record)
            total_memory_score += memory_score
            if memory_events:
                memory_event_items += 1
            context = record.get("context_summary") if isinstance(record, dict) else {}
            evidence = context.get("evidence") if isinstance(context, dict) else {}
            if _has_value(evidence):
                evidence_linked_items += 1
            if agent_events or agent_memory_events:
                agent_trace_items += 1

            state = _text(item.get("state")).lower()
            is_terminal = state in _TERMINAL_STATES or bool(outcome)
            if is_terminal:
                terminal_items += 1
                if outcome:
                    terminal_with_outcome += 1

            owner = ""
            execution_state = record.get("execution_state") if isinstance(record, dict) else {}
            if isinstance(execution_state, dict):
                owner = _text(execution_state.get("waiting_on"))
            if owner:
                owner_buckets[owner] += 1

            blocker_label = _blocker_key(item, record)
            blocker_id = _slug(blocker_label)
            bucket = blocker_buckets.setdefault(
                blocker_id,
                {
                    "key": blocker_id,
                    "label": blocker_label,
                    "count": 0,
                    "vendors": Counter(),
                    "owners": Counter(),
                    "example_item_ids": [],
                    "next_actions": Counter(),
                },
            )
            bucket["count"] += 1
            vendor_name = _text(item.get("vendor_name") or item.get("vendor"))
            if vendor_name:
                bucket["vendors"][vendor_name] += 1
                vendor_buckets[vendor_name][blocker_id] += 1
            if owner:
                bucket["owners"][owner] += 1
            if len(bucket["example_item_ids"]) < 3:
                bucket["example_item_ids"].append(item_id)
            next_action = _text(context.get("next_action")) if isinstance(context, dict) else ""
            if next_action and not is_terminal:
                bucket["next_actions"][next_action] += 1

            eval_cases.append(
                {
                    "ap_item_id": item_id,
                    "vendor_name": vendor_name or None,
                    "state": item.get("state"),
                    "outcome_type": outcome.get("outcome_type") if outcome else None,
                    "outcome_data": _outcome_data(outcome or {}),
                    "memory_completeness_score": memory_score,
                    "missing_context": missing_context,
                    "has_memory_events": bool(memory_events),
                    "has_agent_trace": bool(agent_events or agent_memory_events),
                    "agent_trace_count": len(agent_events) + len(agent_memory_events),
                    "has_evidence": _has_value(evidence),
                    "surface_count": len({_event_surface(event) for event in events}),
                }
            )

        item_count = len(eval_cases)
        recurring_blockers = self._summarize_blockers(
            blocker_buckets.values(),
            item_count=item_count,
        )
        vendor_patterns = self._summarize_vendor_patterns(vendor_buckets)
        company_learning = {
            "recurring_blockers": recurring_blockers,
            "vendor_patterns": vendor_patterns,
            "owner_wait_patterns": [
                {"owner": owner, "count": count}
                for owner, count in owner_buckets.most_common(10)
            ],
            "surface_mix": [
                {"surface": surface, "event_count": count}
                for surface, count in surface_counts.most_common(12)
            ],
            "recommended_actions": self._recommended_actions(
                recurring_blockers=recurring_blockers,
                agent_trace_rate=_ratio(agent_trace_items, item_count),
                evidence_link_rate=_ratio(evidence_linked_items, item_count),
            ),
        }
        summary = {
            "total_items": item_count,
            "terminal_items": terminal_items,
            "terminal_outcomes_recorded": terminal_with_outcome,
            "outcome_traceability_rate": _ratio(terminal_with_outcome, terminal_items),
            "memory_event_coverage_rate": _ratio(memory_event_items, item_count),
            "agent_trace_rate": _ratio(agent_trace_items, item_count),
            "evidence_link_rate": _ratio(evidence_linked_items, item_count),
            "average_memory_completeness_score": round(
                total_memory_score / max(1, item_count), 4
            ),
        }
        snapshot = {
            "contract": LEARNING_LOOP_CONTRACT,
            "snapshot_type": PRIVATE_OUTCOME_EVAL_TYPE,
            "organization_id": self.organization_id,
            "generated_at": _now_iso(),
            "scope": "ap_source_to_pay",
            "params": {
                "from": from_ts,
                "to": to_ts,
                "entity_id": entity_id,
                "limit": int(limit),
            },
            "summary": summary,
            "company_learning": company_learning,
            "private_eval_cases": eval_cases,
            "release_gate": self._release_gate(summary),
        }
        if persist:
            self.persist_snapshot(snapshot)
        return snapshot

    def persist_snapshot(self, snapshot: Dict[str, Any]) -> None:
        self.agent_memory.record_eval_snapshot(
            skill_id="ap_v1",
            scope="organization",
            snapshot_type=PRIVATE_OUTCOME_EVAL_TYPE,
            payload=snapshot,
        )
        for blocker in snapshot.get("company_learning", {}).get("recurring_blockers", []):
            if not isinstance(blocker, dict):
                continue
            self.agent_memory.record_pattern(
                skill_id="ap_v1",
                pattern_type="company_ap_blocker",
                pattern_key=_text(blocker.get("key")),
                pattern=blocker,
                confidence=float(blocker.get("confidence") or 0.5),
            )

    @staticmethod
    def _summarize_blockers(
        buckets: Iterable[Dict[str, Any]],
        *,
        item_count: int,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for bucket in buckets:
            count = int(bucket.get("count") or 0)
            if count <= 0:
                continue
            vendors = bucket.get("vendors")
            owners = bucket.get("owners")
            next_actions = bucket.get("next_actions")
            rows.append(
                {
                    "key": bucket.get("key"),
                    "label": bucket.get("label"),
                    "count": count,
                    "share": _ratio(count, item_count),
                    "affected_vendors": [
                        {"vendor_name": vendor, "count": vendor_count}
                        for vendor, vendor_count in (
                            vendors.most_common(5) if isinstance(vendors, Counter) else []
                        )
                    ],
                    "waiting_on": [
                        {"owner": owner, "count": owner_count}
                        for owner, owner_count in (
                            owners.most_common(5) if isinstance(owners, Counter) else []
                        )
                    ],
                    "common_next_actions": [
                        {"next_action": action, "count": action_count}
                        for action, action_count in (
                            next_actions.most_common(3)
                            if isinstance(next_actions, Counter)
                            else []
                        )
                    ],
                    "example_item_ids": list(bucket.get("example_item_ids") or [])[:3],
                    "confidence": min(0.95, round(0.45 + _ratio(count, item_count), 4)),
                }
            )
        rows.sort(key=lambda row: (-int(row.get("count") or 0), _text(row.get("label"))))
        return rows[:10]

    @staticmethod
    def _summarize_vendor_patterns(
        vendor_buckets: Dict[str, Counter],
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for vendor, blockers in vendor_buckets.items():
            total = sum(blockers.values())
            if total <= 0:
                continue
            rows.append(
                {
                    "vendor_name": vendor,
                    "total_items": total,
                    "top_blockers": [
                        {"key": key, "count": count}
                        for key, count in blockers.most_common(3)
                    ],
                }
            )
        rows.sort(key=lambda row: (-int(row.get("total_items") or 0), row["vendor_name"]))
        return rows[:10]

    @staticmethod
    def _recommended_actions(
        *,
        recurring_blockers: List[Dict[str, Any]],
        agent_trace_rate: float,
        evidence_link_rate: float,
    ) -> List[str]:
        actions: List[str] = []
        if recurring_blockers:
            actions.append(
                "Tune AP policy and intake checks around the top recurring blocker before expanding workflow scope."
            )
        if agent_trace_rate < 1.0:
            actions.append(
                "Route every AP agent decision through AgentMemoryService so future evals can replay the trace."
            )
        if evidence_link_rate < 1.0:
            actions.append(
                "Require source evidence on every AP state change before it counts as learning signal."
            )
        if not actions:
            actions.append(
                "AP learning loop is producing traceable memory, evidence, and outcomes; monitor drift weekly."
            )
        return actions

    @staticmethod
    def _release_gate(summary: Dict[str, Any]) -> Dict[str, Any]:
        checks = {
            "memory_event_coverage": float(summary.get("memory_event_coverage_rate") or 0) >= 0.95,
            "agent_trace_coverage": float(summary.get("agent_trace_rate") or 0) >= 0.8,
            "evidence_linkage": float(summary.get("evidence_link_rate") or 0) >= 0.9,
            "outcome_traceability": float(summary.get("outcome_traceability_rate") or 0) >= 0.9,
        }
        return {
            "status": "pass" if all(checks.values()) else "needs_work",
            "checks": checks,
        }


def run_scheduled_ap_learning_loop_evals(
    *,
    organization_ids: Optional[Iterable[str]] = None,
    db: Optional[SoldenDB] = None,
    limit: Optional[int] = None,
    window_days: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Run and persist AP private-outcome evals for pilot workspaces.

    The scheduled path is intentionally conservative: it scopes to configured
    pilot orgs when ``SOLDEN_AP_LEARNING_LOOP_ORG_IDS`` is set, falls back to
    orgs with AP items, and skips empty orgs so the memory store does not fill
    with zero-signal snapshots.
    """
    runtime_db = db or get_db()
    if hasattr(runtime_db, "initialize"):
        runtime_db.initialize()

    resolved_limit = int(
        limit
        if limit is not None
        else _env_int(
            "AP_LEARNING_LOOP_EVAL_LIMIT",
            DEFAULT_SCHEDULED_EVAL_LIMIT,
            minimum=1,
            maximum=5000,
        )
    )
    resolved_window_days = int(
        window_days
        if window_days is not None
        else _env_int(
            "AP_LEARNING_LOOP_WINDOW_DAYS",
            DEFAULT_SCHEDULED_EVAL_WINDOW_DAYS,
            minimum=1,
            maximum=365,
        )
    )
    now_dt = now or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    now_dt = now_dt.astimezone(timezone.utc)
    from_ts = (now_dt - timedelta(days=resolved_window_days)).isoformat()
    to_ts = now_dt.isoformat()

    configured_org_ids = _scheduled_org_ids_from_env()
    if configured_org_ids:
        candidate_org_ids = configured_org_ids
    elif organization_ids is None:
        candidate_org_ids = _discover_scheduled_org_ids(runtime_db)
    else:
        candidate_org_ids = list(organization_ids)

    org_ids: List[str] = []
    seen = set()
    for org_id in candidate_org_ids:
        token = coerce_org_id(org_id)
        if not token or token in seen:
            continue
        seen.add(token)
        org_ids.append(token)

    summary: Dict[str, Any] = {
        "status": "ok",
        "orgs_discovered": len(org_ids),
        "processed": 0,
        "skipped": 0,
        "errors": 0,
        "window_days": resolved_window_days,
        "limit": resolved_limit,
        "from": from_ts,
        "to": to_ts,
        "per_org": [],
    }

    for org_id in org_ids:
        try:
            service = APLearningLoopService(org_id, db=runtime_db)
            snapshot = service.evaluate_private_outcomes(
                limit=resolved_limit,
                persist=False,
                from_ts=from_ts,
                to_ts=to_ts,
            )
            total_items = int(snapshot.get("summary", {}).get("total_items") or 0)
            if total_items <= 0:
                summary["skipped"] += 1
                summary["per_org"].append(
                    {
                        "organization_id": org_id,
                        "status": "skipped_no_ap_items",
                        "total_items": 0,
                    }
                )
                continue
            service.persist_snapshot(snapshot)
            summary["processed"] += 1
            summary["per_org"].append(
                {
                    "organization_id": org_id,
                    "status": "persisted",
                    "total_items": total_items,
                    "release_gate": snapshot.get("release_gate", {}).get("status"),
                    "snapshot_type": PRIVATE_OUTCOME_EVAL_TYPE,
                }
            )
        except Exception as exc:
            summary["errors"] += 1
            summary["status"] = "partial_error"
            summary["per_org"].append(
                {
                    "organization_id": org_id,
                    "status": "error",
                    "error": str(exc),
                }
            )

    return summary
