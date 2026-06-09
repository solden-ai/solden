"""Dimension-graph data-access mixin for SoldenDB.

A **dimension** is a cross-system accounting object a work item references:
a GL account or a cost center (later: project, department). It is NOT a
:term:`legal entity` (that is the multi-entity ``entities`` table /
``audit_events.entity_id``), and it is NOT a Box (that is ``box_registry``).
Dimensions are reference data that records *point at*, so operational memory
can answer "everything charged to GL 5210 / CC 402" and "why is this on that
account".

Three tables, all tenant-scoped:

* ``context_dimensions``  -- the canonical object: (org, type, code) is unique.
* ``dimension_aliases``   -- alternate codes/spellings that resolve to one.
* ``dimension_links``     -- a record (box) <-> dimension edge.

``DimensionStore`` is a **mixin** -- no ``__init__`` of its own. It expects the
concrete class to provide ``self.connect()`` (context-manager connection with
dict rows) and ``self.initialize()``. Mirrors ``EntityStore`` / ``VendorStore``.
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


class DimensionStore:
    """Mixin providing dimension-graph persistence + resolution methods."""

    CONTEXT_DIMENSIONS_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS context_dimensions (
            id TEXT PRIMARY KEY,
            organization_id TEXT NOT NULL,
            dimension_type TEXT NOT NULL,
            code TEXT NOT NULL,
            label TEXT,
            source TEXT,
            metadata_json TEXT DEFAULT '{}',
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(organization_id, dimension_type, code)
        )
    """

    DIMENSION_ALIASES_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS dimension_aliases (
            id TEXT PRIMARY KEY,
            organization_id TEXT NOT NULL,
            dimension_id TEXT NOT NULL,
            alias TEXT NOT NULL,
            created_at TEXT,
            UNIQUE(organization_id, dimension_id, alias)
        )
    """

    DIMENSION_LINKS_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS dimension_links (
            id TEXT PRIMARY KEY,
            organization_id TEXT NOT NULL,
            box_type TEXT NOT NULL,
            box_id TEXT NOT NULL,
            dimension_id TEXT NOT NULL,
            confidence REAL,
            status TEXT DEFAULT 'proposed',
            linked_by TEXT,
            source TEXT,
            created_at TEXT,
            UNIQUE(organization_id, box_type, box_id, dimension_id)
        )
    """

    # ---- normalization ---------------------------------------------------

    @staticmethod
    def _normalize_dim(value: Any) -> str:
        """Case/space-fold a code or alias for tolerant matching."""
        return " ".join(str(value or "").strip().lower().split())

    def _dim_row(self, row: Any) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        d = dict(row)
        meta = d.pop("metadata_json", None)
        if isinstance(meta, str):
            try:
                d["metadata"] = json.loads(meta or "{}")
            except Exception:
                d["metadata"] = {}
        elif isinstance(meta, dict):
            d["metadata"] = meta
        return d

    # ---- canonical dimensions -------------------------------------------

    def upsert_dimension(
        self,
        *,
        organization_id: str,
        dimension_type: str,
        code: str,
        label: Optional[str] = None,
        source: str = "inferred",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create or refresh a canonical dimension. Idempotent on
        (organization_id, dimension_type, code). First-writer wins on
        ``source`` (don't let an inferred re-link downgrade an erp_coa seed)."""
        self.initialize()
        code = str(code or "").strip()
        if not (organization_id and dimension_type and code):
            return None
        now = _now_iso()
        dim_id = f"DIM-{uuid.uuid4().hex[:12]}"
        sql = """
            INSERT INTO context_dimensions
                (id, organization_id, dimension_type, code, label, source,
                 metadata_json, is_active, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s, %s)
            ON CONFLICT (organization_id, dimension_type, code) DO UPDATE SET
                label = COALESCE(EXCLUDED.label, context_dimensions.label),
                source = COALESCE(context_dimensions.source, EXCLUDED.source),
                updated_at = EXCLUDED.updated_at
            RETURNING *
        """
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                sql,
                (
                    dim_id, organization_id, dimension_type, code, label,
                    source, json.dumps(metadata or {}), now, now,
                ),
            )
            row = cur.fetchone()
            conn.commit()
        return self._dim_row(row)

    def add_dimension_alias(
        self, *, organization_id: str, dimension_id: str, alias: str
    ) -> None:
        """Record an alternate code/spelling that resolves to a dimension."""
        self.initialize()
        norm = self._normalize_dim(alias)
        if not (organization_id and dimension_id and norm):
            return
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO dimension_aliases
                       (id, organization_id, dimension_id, alias, created_at)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (organization_id, dimension_id, alias) DO NOTHING""",
                (f"DALS-{uuid.uuid4().hex[:12]}", organization_id, dimension_id, norm, _now_iso()),
            )
            conn.commit()

    def resolve_dimension(
        self, *, organization_id: str, dimension_type: str, raw_code: str
    ) -> Optional[Dict[str, Any]]:
        """Deterministic resolution ladder: exact code -> alias -> normalized
        code. Returns the dimension dict with a ``_match_kind`` hint, or None.
        Fuzzy/label matching is the resolver's job (it knows the threshold)."""
        self.initialize()
        raw = str(raw_code or "").strip()
        if not (organization_id and dimension_type and raw):
            return None
        norm = self._normalize_dim(raw)
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM context_dimensions "
                "WHERE organization_id=%s AND dimension_type=%s AND code=%s",
                (organization_id, dimension_type, raw),
            )
            row = cur.fetchone()
            if row:
                return {**self._dim_row(row), "_match_kind": "exact"}
            cur.execute(
                """SELECT cd.* FROM dimension_aliases da
                   JOIN context_dimensions cd ON cd.id = da.dimension_id
                   WHERE da.organization_id=%s AND cd.dimension_type=%s AND da.alias=%s""",
                (organization_id, dimension_type, norm),
            )
            row = cur.fetchone()
            if row:
                return {**self._dim_row(row), "_match_kind": "alias"}
            cur.execute(
                "SELECT * FROM context_dimensions "
                "WHERE organization_id=%s AND dimension_type=%s AND lower(code)=%s",
                (organization_id, dimension_type, norm),
            )
            row = cur.fetchone()
            if row:
                return {**self._dim_row(row), "_match_kind": "normalized"}
        return None

    def list_dimensions(
        self, *, organization_id: str, dimension_type: str
    ) -> List[Dict[str, Any]]:
        """All active dimensions of a type (the resolver's fuzzy candidate set)."""
        self.initialize()
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM context_dimensions "
                "WHERE organization_id=%s AND dimension_type=%s AND is_active=1",
                (organization_id, dimension_type),
            )
            rows = cur.fetchall() or []
        return [self._dim_row(r) for r in rows]

    # ---- record <-> dimension links -------------------------------------

    def link_dimension(
        self,
        *,
        organization_id: str,
        box_type: str,
        box_id: str,
        dimension_id: str,
        confidence: Optional[float] = None,
        status: str = "proposed",
        linked_by: str = "agent",
        source: str = "resolver",
    ) -> Optional[Dict[str, Any]]:
        """Link a record (box) to a dimension. Idempotent on
        (org, box_type, box_id, dimension_id) -- re-resolving updates in place."""
        self.initialize()
        if not (organization_id and box_type and box_id and dimension_id):
            return None
        sql = """
            INSERT INTO dimension_links
                (id, organization_id, box_type, box_id, dimension_id,
                 confidence, status, linked_by, source, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (organization_id, box_type, box_id, dimension_id) DO UPDATE SET
                confidence = EXCLUDED.confidence,
                status = EXCLUDED.status,
                source = EXCLUDED.source
            RETURNING *
        """
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                sql,
                (
                    f"DLNK-{uuid.uuid4().hex[:12]}", organization_id, box_type,
                    box_id, dimension_id, confidence, status, linked_by, source, _now_iso(),
                ),
            )
            row = cur.fetchone()
            conn.commit()
        return dict(row) if row is not None else None

    def list_dimension_links(
        self, *, organization_id: str, box_type: str, box_id: str
    ) -> List[Dict[str, Any]]:
        """Resolved dimensions for one record, joined to the canonical object.
        This is what the operational-memory record surfaces."""
        self.initialize()
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT dl.dimension_id, dl.confidence, dl.status, dl.source,
                          dl.linked_by, cd.dimension_type, cd.code, cd.label
                   FROM dimension_links dl
                   JOIN context_dimensions cd ON cd.id = dl.dimension_id
                   WHERE dl.organization_id=%s AND dl.box_type=%s AND dl.box_id=%s
                   ORDER BY cd.dimension_type, cd.code""",
                (organization_id, box_type, box_id),
            )
            rows = cur.fetchall() or []
        out: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            out.append({
                "dimension_id": d.get("dimension_id"),
                "dimension_type": d.get("dimension_type"),
                "code": d.get("code"),
                "label": d.get("label"),
                "status": d.get("status"),
                "confidence": d.get("confidence"),
                "source": d.get("source"),
            })
        return out

    def list_boxes_for_dimension(
        self, *, organization_id: str, dimension_id: str
    ) -> List[Dict[str, Any]]:
        """Every record linked to a dimension (the reverse edge -- the basis
        for a future 'everything on CC 402' rollup)."""
        self.initialize()
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT box_type, box_id, status, confidence FROM dimension_links "
                "WHERE organization_id=%s AND dimension_id=%s",
                (organization_id, dimension_id),
            )
            rows = cur.fetchall() or []
        return [dict(r) for r in rows]
