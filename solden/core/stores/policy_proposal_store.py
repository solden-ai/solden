"""Policy-proposal data-access mixin for SoldenDB (tribal-knowledge Build 3).

A **policy proposal** is the agent playing enacted behavior back to a human:
"you've approved Acme's escalated invoices 6 times — make it a standing rule?"
Proposals are ADVISORY rows: creating one changes no behavior; only a human
accept lands the (bounded) rule, via the existing rules table. A decline is a
deliberate non-rule — recorded with its reason and never re-proposed.

``PolicyProposalStore`` is a **mixin** — no ``__init__``; expects ``connect()``
+ ``initialize()`` from the concrete class. Mirrors ``DimensionStore``.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PolicyProposalStore:
    """Mixin providing policy-proposal persistence."""

    POLICY_PROPOSALS_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS policy_proposals (
            id TEXT PRIMARY KEY,
            organization_id TEXT NOT NULL,
            proposal_kind TEXT NOT NULL,
            vendor_name TEXT,
            behavior_summary TEXT NOT NULL,
            evidence_json TEXT DEFAULT '{}',
            proposed_rule_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            accepted_by TEXT,
            accepted_at TEXT,
            declined_by TEXT,
            declined_at TEXT,
            decline_reason TEXT,
            applied_rule_id TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """

    def _proposal_row(self, row: Any) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        d = dict(row)
        for key, target in (("evidence_json", "evidence"), ("proposed_rule_json", "proposed_rule")):
            raw = d.pop(key, None)
            if isinstance(raw, dict):
                d[target] = raw
            else:
                try:
                    d[target] = json.loads(raw or "{}")
                except Exception:
                    d[target] = {}
        return d

    def create_policy_proposal(
        self,
        *,
        organization_id: str,
        proposal_kind: str,
        vendor_name: Optional[str],
        behavior_summary: str,
        evidence: Optional[Dict[str, Any]] = None,
        proposed_rule: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Create a proposal unless one already exists for (org, kind, vendor)
        in ANY resolution state: pending (don't duplicate), declined
        (deliberate non-rule — never re-nag), or accepted (the rule already
        exists — re-proposing would stack duplicates). Returns the new row,
        or None when suppressed."""
        self.initialize()
        if not (organization_id and proposal_kind):
            return None
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, status FROM policy_proposals "
                "WHERE organization_id=%s AND proposal_kind=%s "
                "AND COALESCE(vendor_name,'')=%s "
                "AND status IN ('pending','accepted','declined') "
                "LIMIT 1",
                (organization_id, proposal_kind, str(vendor_name or "")),
            )
            if cur.fetchone():
                return None
            now = _now_iso()
            proposal_id = f"PROP-{uuid.uuid4().hex[:12]}"
            cur.execute(
                """INSERT INTO policy_proposals
                       (id, organization_id, proposal_kind, vendor_name,
                        behavior_summary, evidence_json, proposed_rule_json,
                        status, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s)
                   RETURNING *""",
                (
                    proposal_id, organization_id, proposal_kind, vendor_name,
                    behavior_summary, json.dumps(evidence or {}),
                    json.dumps(proposed_rule or {}), now, now,
                ),
            )
            row = cur.fetchone()
            conn.commit()
        return self._proposal_row(row)

    def list_policy_proposals(
        self, *, organization_id: str, status: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        self.initialize()
        params: List[Any] = [organization_id]
        sql = "SELECT * FROM policy_proposals WHERE organization_id=%s"
        if status:
            sql += " AND status=%s"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(int(limit))
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, tuple(params))
            rows = cur.fetchall() or []
        return [self._proposal_row(r) for r in rows]

    def get_policy_proposal(
        self, *, organization_id: str, proposal_id: str
    ) -> Optional[Dict[str, Any]]:
        self.initialize()
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM policy_proposals WHERE organization_id=%s AND id=%s",
                (organization_id, proposal_id),
            )
            row = cur.fetchone()
        return self._proposal_row(row)

    def resolve_policy_proposal(
        self,
        *,
        organization_id: str,
        proposal_id: str,
        resolution: str,
        actor_id: str,
        note: Optional[str] = None,
        applied_rule_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Mark a pending proposal accepted/declined. First writer wins —
        a proposal that is no longer pending returns None."""
        self.initialize()
        if resolution not in ("accepted", "declined"):
            raise ValueError(f"invalid resolution: {resolution!r}")
        now = _now_iso()
        if resolution == "accepted":
            sql = (
                "UPDATE policy_proposals SET status='accepted', accepted_by=%s, "
                "accepted_at=%s, applied_rule_id=%s, updated_at=%s "
                "WHERE organization_id=%s AND id=%s AND status='pending' RETURNING *"
            )
            params = (actor_id, now, applied_rule_id, now, organization_id, proposal_id)
        else:
            sql = (
                "UPDATE policy_proposals SET status='declined', declined_by=%s, "
                "declined_at=%s, decline_reason=%s, updated_at=%s "
                "WHERE organization_id=%s AND id=%s AND status='pending' RETURNING *"
            )
            params = (actor_id, now, note, now, organization_id, proposal_id)
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            row = cur.fetchone()
            conn.commit()
        return self._proposal_row(row)

    def set_policy_proposal_applied_rule(
        self, *, organization_id: str, proposal_id: str, applied_rule_id: str
    ) -> Optional[Dict[str, Any]]:
        """Backfill the rule linkage after a claim-first accept."""
        self.initialize()
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE policy_proposals SET applied_rule_id=%s, updated_at=%s "
                "WHERE organization_id=%s AND id=%s AND status='accepted' RETURNING *",
                (applied_rule_id, _now_iso(), organization_id, proposal_id),
            )
            row = cur.fetchone()
            conn.commit()
        return self._proposal_row(row)

    def reopen_policy_proposal(
        self, *, organization_id: str, proposal_id: str
    ) -> Optional[Dict[str, Any]]:
        """Revert a claimed-but-unapplied accept back to pending (rule creation
        failed after the claim). Only flips an accepted row with NO linked rule."""
        self.initialize()
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE policy_proposals SET status='pending', accepted_by=NULL, "
                "accepted_at=NULL, updated_at=%s "
                "WHERE organization_id=%s AND id=%s AND status='accepted' "
                "AND applied_rule_id IS NULL RETURNING *",
                (_now_iso(), organization_id, proposal_id),
            )
            row = cur.fetchone()
            conn.commit()
        return self._proposal_row(row)

    def list_recent_feedback_vendors(
        self, *, organization_id: str, window_days: int = 180, limit: int = 50
    ) -> List[str]:
        """Distinct vendors with recent human decision feedback — the
        detector's candidate set (bounded)."""
        self.initialize()
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(days=int(window_days))).isoformat()
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT vendor_name, MAX(created_at) AS last_seen "
                "FROM vendor_decision_feedback "
                "WHERE organization_id=%s AND created_at >= %s "
                "GROUP BY vendor_name ORDER BY last_seen DESC LIMIT %s",
                (organization_id, cutoff, int(limit)),
            )
            rows = cur.fetchall() or []
        return [str(dict(r).get("vendor_name") or "") for r in rows if dict(r).get("vendor_name")]
