"""PaymentRequestStore mixin — CRUD for ad-hoc payment requests.

Persists the ``payment_requests`` table (migration v98). Replaces the prior
in-memory dict in ``PaymentRequestService`` so a request + its approve/reject/
mark_paid lifecycle survives restarts and is org-scoped at the SQL level.
State transitions are audited by the service (which holds the actor context).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Columns an UPDATE may touch — guards against arbitrary-column writes.
_PAYMENT_REQUEST_ALLOWED_COLUMNS = frozenset({
    "status", "approved_by", "approved_at", "rejection_reason",
    "payment_id", "gl_code", "cost_center", "metadata_json",
})


def _decode_row(row: Any) -> Dict[str, Any]:
    out = dict(row)
    raw = out.get("metadata_json")
    if isinstance(raw, str):
        try:
            out["metadata_json"] = json.loads(raw) if raw.strip() else {}
        except (ValueError, TypeError):
            out["metadata_json"] = {}
    return out


class PaymentRequestStore:
    """Mixin providing payment-request persistence. Composed into SoldenDB."""

    def create_payment_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a payment request. ``payload`` must carry ``id`` +
        ``organization_id``; missing org fails closed."""
        self.initialize()
        org = str(payload.get("organization_id") or "").strip()
        if not org:
            raise ValueError("create_payment_request requires a non-empty organization_id")
        now = datetime.now(timezone.utc).isoformat()
        metadata = payload.get("metadata_json")
        if metadata is None:
            metadata = payload.get("metadata") or {}
        metadata_json = metadata if isinstance(metadata, str) else json.dumps(metadata or {})

        sql = """
            INSERT INTO payment_requests
            (id, organization_id, source, source_id, requester_name,
             requester_email, request_type, payee_name, payee_email, amount,
             currency, description, gl_code, cost_center, status, approved_by,
             approved_at, rejection_reason, payment_id, metadata_json,
             created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            payload["id"], org,
            payload.get("source"), payload.get("source_id"),
            payload.get("requester_name"), payload.get("requester_email"),
            payload.get("request_type") or "other",
            payload.get("payee_name"), payload.get("payee_email"),
            float(payload.get("amount") or 0.0),
            payload.get("currency") or "USD",
            payload.get("description"), payload.get("gl_code"),
            payload.get("cost_center"),
            payload.get("status") or "pending",
            payload.get("approved_by"), payload.get("approved_at"),
            payload.get("rejection_reason"), payload.get("payment_id"),
            metadata_json,
            payload.get("created_at") or now,
            payload.get("updated_at") or now,
        )
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
        return self.get_payment_request(payload["id"], org)

    def get_payment_request(
        self, request_id: str, organization_id: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch a payment request by id, scoped to an org (fails closed)."""
        self.initialize()
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM payment_requests WHERE id = %s AND organization_id = %s",
                (request_id, organization_id),
            )
            row = cur.fetchone()
        return _decode_row(row) if row else None

    def list_payment_requests(
        self,
        organization_id: str,
        *,
        status: Optional[str] = None,
        source: Optional[str] = None,
        requester_email: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """List an org's payment requests, optionally filtered."""
        self.initialize()
        clauses = ["organization_id = %s"]
        params: List[Any] = [organization_id]
        if status:
            clauses.append("status = %s")
            params.append(status)
        if source:
            clauses.append("source = %s")
            params.append(source)
        if requester_email:
            clauses.append("requester_email = %s")
            params.append(requester_email)
        params.append(limit)
        sql = (
            f"SELECT * FROM payment_requests WHERE {' AND '.join(clauses)} "
            f"ORDER BY created_at DESC LIMIT %s"
        )
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            return [_decode_row(r) for r in cur.fetchall()]

    def update_payment_request(
        self, request_id: str, organization_id: str, **kwargs
    ) -> bool:
        """Update a payment request in place, scoped to an org. Only whitelisted
        columns are writable; org-scoping means a known id from another tenant
        mutates nothing."""
        self.initialize()
        updates = {
            k: (json.dumps(v) if k == "metadata_json" and not isinstance(v, str) else v)
            for k, v in kwargs.items()
            if k in _PAYMENT_REQUEST_ALLOWED_COLUMNS
        }
        if not updates:
            return False
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        set_clause = ", ".join(f"{k} = %s" for k in updates)
        sql = (
            f"UPDATE payment_requests SET {set_clause} "
            f"WHERE id = %s AND organization_id = %s"
        )
        params = list(updates.values()) + [request_id, organization_id]
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            return cur.rowcount > 0
