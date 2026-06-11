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

    # Dimension <-> dimension relationships: 'hierarchy' (parent contains child,
    # e.g. Division EMEA -> CC 402) and 'equivalent' (the same real-world thing
    # known by two codes/systems). Mirrors the box_links org-required pattern.
    DIMENSION_EDGES_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS dimension_edges (
            id TEXT PRIMARY KEY,
            organization_id TEXT NOT NULL,
            parent_dimension_id TEXT NOT NULL,
            child_dimension_id TEXT NOT NULL,
            edge_type TEXT NOT NULL DEFAULT 'hierarchy',
            source TEXT,
            created_at TEXT,
            UNIQUE(organization_id, parent_dimension_id, child_dimension_id, edge_type)
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
        is_active: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Create or refresh a canonical dimension. Idempotent on
        (organization_id, dimension_type, code). First-writer wins on
        ``source`` (don't let an inferred re-link downgrade an erp_coa seed).
        ``is_active`` IS writer-wins on conflict — the ERP master is
        authoritative for active/retired, so a re-sync can retire a
        dimension in place."""
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (organization_id, dimension_type, code) DO UPDATE SET
                label = COALESCE(EXCLUDED.label, context_dimensions.label),
                source = CASE
                    WHEN COALESCE(context_dimensions.source, '') IN ('', 'inferred', 'suggested', 'resolver')
                         AND EXCLUDED.source IN ('erp_master', 'erp_coa', 'erp_sync')
                    THEN EXCLUDED.source
                    ELSE COALESCE(context_dimensions.source, EXCLUDED.source)
                END,
                metadata_json = CASE
                    WHEN COALESCE(context_dimensions.metadata_json, '{}') IN ('{}', '')
                         OR EXCLUDED.source IN ('erp_master', 'erp_coa', 'erp_sync')
                    THEN EXCLUDED.metadata_json
                    ELSE context_dimensions.metadata_json
                END,
                is_active = EXCLUDED.is_active,
                updated_at = EXCLUDED.updated_at
            RETURNING *
        """
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                sql,
                (
                    dim_id, organization_id, dimension_type, code, label,
                    source, json.dumps(metadata or {}), 1 if is_active else 0,
                    now, now,
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
        self, *, organization_id: str, dimension_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Active dimensions for an org. Filtered by type (the resolver's fuzzy
        candidate set) or all types (the rollup API) when ``dimension_type`` is None."""
        self.initialize()
        with self.connect() as conn:
            cur = conn.cursor()
            if dimension_type:
                cur.execute(
                    "SELECT * FROM context_dimensions "
                    "WHERE organization_id=%s AND dimension_type=%s AND is_active=1 "
                    "ORDER BY dimension_type, code",
                    (organization_id, dimension_type),
                )
            else:
                cur.execute(
                    "SELECT * FROM context_dimensions "
                    "WHERE organization_id=%s AND is_active=1 "
                    "ORDER BY dimension_type, code",
                    (organization_id,),
                )
            rows = cur.fetchall() or []
        return [self._dim_row(r) for r in rows]

    def get_dimension(
        self, *, organization_id: str, dimension_id: str
    ) -> Optional[Dict[str, Any]]:
        """One canonical dimension by id, tenant-scoped (None if not in this org)."""
        self.initialize()
        if not (organization_id and dimension_id):
            return None
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM context_dimensions WHERE organization_id=%s AND id=%s",
                (organization_id, dimension_id),
            )
            row = cur.fetchone()
        return self._dim_row(row)

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
        self,
        *,
        organization_id: str,
        dimension_id: str,
        include_descendants: bool = False,
    ) -> List[Dict[str, Any]]:
        """Every record linked to a dimension. With ``include_descendants``,
        also every record linked anywhere under it in the hierarchy ("all
        records under EMEA" without any record knowing about EMEA)."""
        self.initialize()
        ids = [dimension_id]
        if include_descendants:
            ids += self.list_descendant_dimension_ids(
                organization_id=organization_id, dimension_id=dimension_id
            )
        placeholders = ",".join("%s" for _ in ids)
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT DISTINCT box_type, box_id, status, confidence "
                f"FROM dimension_links WHERE organization_id=%s AND dimension_id IN ({placeholders})",
                (organization_id, *ids),
            )
            rows = cur.fetchall() or []
        return [dict(r) for r in rows]

    # ---- dimension <-> dimension edges -----------------------------------

    _EDGE_MAX_DEPTH = 10

    def add_dimension_edge(
        self,
        *,
        organization_id: str,
        parent_dimension_id: str,
        child_dimension_id: str,
        edge_type: str = "hierarchy",
        source: str = "manual",
    ) -> Optional[Dict[str, Any]]:
        """Relate two dimensions. Org required; self-edges rejected; a
        hierarchy edge that would close a cycle is refused (the child must not
        already reach the parent)."""
        if not organization_id:
            raise ValueError("add_dimension_edge requires organization_id")
        if edge_type not in ("hierarchy", "equivalent"):
            raise ValueError(f"invalid edge_type: {edge_type!r}")
        if parent_dimension_id == child_dimension_id:
            raise ValueError("self-edge rejected")
        self.initialize()
        parent = self.get_dimension(
            organization_id=organization_id,
            dimension_id=parent_dimension_id,
        )
        child = self.get_dimension(
            organization_id=organization_id,
            dimension_id=child_dimension_id,
        )
        if not parent or not child:
            raise ValueError("dimension edge endpoints must exist in organization")
        if edge_type == "hierarchy":
            reachable = self.list_descendant_dimension_ids(
                organization_id=organization_id, dimension_id=child_dimension_id
            )
            if parent_dimension_id in reachable:
                raise ValueError("hierarchy cycle rejected")
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO dimension_edges
                       (id, organization_id, parent_dimension_id,
                        child_dimension_id, edge_type, source, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (organization_id, parent_dimension_id,
                                child_dimension_id, edge_type) DO NOTHING
                   RETURNING *""",
                (
                    f"DEDG-{uuid.uuid4().hex[:12]}", organization_id,
                    parent_dimension_id, child_dimension_id, edge_type,
                    source, _now_iso(),
                ),
            )
            row = cur.fetchone()
            conn.commit()
        return dict(row) if row is not None else None

    def list_dimension_children(
        self, *, organization_id: str, dimension_id: str
    ) -> List[Dict[str, Any]]:
        self.initialize()
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT cd.*, de.edge_type FROM dimension_edges de
                   JOIN context_dimensions cd ON cd.id = de.child_dimension_id
                   WHERE de.organization_id=%s AND de.parent_dimension_id=%s""",
                (organization_id, dimension_id),
            )
            rows = cur.fetchall() or []
        return [self._dim_row(r) for r in rows]

    def list_dimension_parents(
        self, *, organization_id: str, dimension_id: str
    ) -> List[Dict[str, Any]]:
        self.initialize()
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT cd.*, de.edge_type FROM dimension_edges de
                   JOIN context_dimensions cd ON cd.id = de.parent_dimension_id
                   WHERE de.organization_id=%s AND de.child_dimension_id=%s""",
                (organization_id, dimension_id),
            )
            rows = cur.fetchall() or []
        return [self._dim_row(r) for r in rows]

    def list_descendant_dimension_ids(
        self, *, organization_id: str, dimension_id: str
    ) -> List[str]:
        """All hierarchy descendant ids. Equivalence edges are not traversed."""
        return [
            str(row.get("id"))
            for row in self.list_dimension_descendants(
                organization_id=organization_id,
                dimension_id=dimension_id,
            )
            if row.get("id")
        ]

    def list_dimension_descendants(
        self, *, organization_id: str, dimension_id: str
    ) -> List[Dict[str, Any]]:
        """Hierarchy descendants with depth metadata.

        Kept in Python instead of recursive SQL so the behavior is identical
        across SQLite test runs and Postgres production.
        """
        self.initialize()
        if not (organization_id and dimension_id):
            return []
        out: List[Dict[str, Any]] = []
        seen_depth: Dict[str, int] = {}
        frontier = [
            (child, 1)
            for child in self.list_dimension_children(
                organization_id=organization_id,
                dimension_id=dimension_id,
            )
            if str(child.get("edge_type") or "hierarchy") == "hierarchy"
        ]
        while frontier:
            child, depth = frontier.pop(0)
            child_id = str(child.get("id") or "")
            if not child_id:
                continue
            if depth > self._EDGE_MAX_DEPTH:
                continue
            previous_depth = seen_depth.get(child_id)
            if previous_depth is not None and previous_depth <= depth:
                continue
            seen_depth[child_id] = depth
            row = dict(child)
            row["depth"] = depth
            out.append(row)
            if depth >= self._EDGE_MAX_DEPTH:
                continue
            for grandchild in self.list_dimension_children(
                organization_id=organization_id,
                dimension_id=child_id,
            ):
                if str(grandchild.get("edge_type") or "hierarchy") != "hierarchy":
                    continue
                frontier.append((grandchild, depth + 1))
        return out
