"""LearningStore — org-scoped Postgres persistence for the compounding-learning service.

Replaces the legacy per-process SQLite file (``state/learning.db``) the
CompoundingLearningService used to write. Every method is org-scoped: rows carry
``organization_id NOT NULL`` and it is part of the primary key, so two orgs that
generate the same ``pattern_id`` (e.g. ``cat_acme_6010``) keep separate rows and
one org's learned patterns never surface in another org's reasoning.

Tables created by migration v95: ``learning_patterns`` + ``learning_corrections``.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _coerce_json(value: Any, default: Any) -> Any:
    """psycopg returns JSONB as parsed objects, but tolerate text too."""
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return default
    return value


class LearningStore:
    """Mixin: org-scoped CRUD for compounding-learning patterns + corrections.

    Combined into SoldenDB via the four-site wiring in ``database.py``.
    """

    def list_learning_patterns(
        self,
        organization_id: str,
        *,
        min_confidence: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """All learned patterns for one org above a confidence floor."""
        self.initialize()
        sql = (
            "SELECT pattern_id, pattern_type, pattern_data, confidence, "
            "usage_count, success_count, last_used, created_from "
            "FROM learning_patterns "
            "WHERE organization_id = %s AND confidence > %s"
        )
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, (organization_id, float(min_confidence)))
            rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            r["pattern_data"] = _coerce_json(r.get("pattern_data"), {})
            r["created_from"] = _coerce_json(r.get("created_from"), [])
        return rows

    def save_learning_pattern(
        self,
        organization_id: str,
        pattern: Dict[str, Any],
    ) -> None:
        """Upsert one learned pattern, scoped to (organization_id, pattern_id)."""
        self.initialize()
        now = datetime.now(timezone.utc).isoformat()
        sql = (
            "INSERT INTO learning_patterns "
            "(organization_id, pattern_id, pattern_type, pattern_data, confidence, "
            " usage_count, success_count, last_used, created_from, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb, %s, %s) "
            "ON CONFLICT (organization_id, pattern_id) DO UPDATE SET "
            "  pattern_type = EXCLUDED.pattern_type, "
            "  pattern_data = EXCLUDED.pattern_data, "
            "  confidence = EXCLUDED.confidence, "
            "  usage_count = EXCLUDED.usage_count, "
            "  success_count = EXCLUDED.success_count, "
            "  last_used = EXCLUDED.last_used, "
            "  created_from = EXCLUDED.created_from, "
            "  updated_at = EXCLUDED.updated_at"
        )
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, (
                organization_id,
                pattern["pattern_id"],
                pattern["pattern_type"],
                json.dumps(pattern.get("pattern_data") or {}),
                float(pattern.get("confidence") or 0.0),
                int(pattern.get("usage_count") or 0),
                int(pattern.get("success_count") or 0),
                pattern.get("last_used"),
                json.dumps(pattern.get("created_from") or []),
                now,
                now,
            ))
            conn.commit()

    def save_learning_correction(
        self,
        organization_id: str,
        correction: Dict[str, Any],
    ) -> None:
        """Insert one correction row, scoped to (organization_id, correction_id)."""
        self.initialize()
        now = datetime.now(timezone.utc).isoformat()
        sql = (
            "INSERT INTO learning_corrections "
            "(organization_id, correction_id, correction_type, original_value, "
            " corrected_value, user_email, context, created_at) "
            "VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s::jsonb, %s) "
            "ON CONFLICT (organization_id, correction_id) DO NOTHING"
        )
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, (
                organization_id,
                correction["correction_id"],
                correction["correction_type"],
                json.dumps(correction.get("original_value") or {}),
                json.dumps(correction.get("corrected_value") or {}),
                correction.get("user_email") or "system",
                json.dumps(correction.get("context") or {}),
                correction.get("created_at") or now,
            ))
            conn.commit()

    # ------------------------------------------------------------------ #
    # Vendor -> GL patterns (LearningService, learned from approvals)
    # ------------------------------------------------------------------ #
    def list_vendor_gl_patterns(self, organization_id: str) -> List[Dict[str, Any]]:
        """All learned vendor->GL patterns for one org."""
        self.initialize()
        sql = (
            "SELECT vendor_normalized, gl_code, vendor_name, gl_description, "
            "occurrence_count, total_amount, avg_amount, currency, last_used, confidence "
            "FROM learning_vendor_patterns WHERE organization_id = %s"
        )
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, (organization_id,))
            return [dict(r) for r in cur.fetchall()]

    def save_vendor_gl_pattern(
        self,
        organization_id: str,
        pattern: Dict[str, Any],
    ) -> None:
        """Upsert one vendor->GL pattern, scoped to (org, vendor_normalized, gl_code)."""
        self.initialize()
        now = datetime.now(timezone.utc).isoformat()
        sql = (
            "INSERT INTO learning_vendor_patterns "
            "(organization_id, vendor_normalized, gl_code, vendor_name, gl_description, "
            " occurrence_count, total_amount, avg_amount, currency, last_used, confidence, "
            " created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (organization_id, vendor_normalized, gl_code) DO UPDATE SET "
            "  vendor_name = EXCLUDED.vendor_name, "
            "  gl_description = EXCLUDED.gl_description, "
            "  occurrence_count = EXCLUDED.occurrence_count, "
            "  total_amount = EXCLUDED.total_amount, "
            "  avg_amount = EXCLUDED.avg_amount, "
            "  currency = EXCLUDED.currency, "
            "  last_used = EXCLUDED.last_used, "
            "  confidence = EXCLUDED.confidence, "
            "  updated_at = EXCLUDED.updated_at"
        )
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, (
                organization_id,
                pattern["vendor_normalized"],
                pattern["gl_code"],
                pattern.get("vendor_name") or "",
                pattern.get("gl_description"),
                int(pattern.get("occurrence_count") or 0),
                float(pattern.get("total_amount") or 0.0),
                float(pattern.get("avg_amount") or 0.0),
                pattern.get("currency") or "USD",
                pattern.get("last_used"),
                float(pattern.get("confidence") or 0.0),
                now,
                now,
            ))
            conn.commit()

    def get_learning_org_stats(self, organization_id: str) -> Dict[str, Any]:
        """Cumulative learning counters for one org (zeros if none yet)."""
        self.initialize()
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT total_learned, corrections_received, auto_approved_count "
                "FROM learning_org_stats WHERE organization_id = %s",
                (organization_id,),
            )
            row = cur.fetchone()
        if not row:
            return {"total_learned": 0, "corrections_received": 0, "auto_approved_count": 0}
        return {
            "total_learned": int(row.get("total_learned") or 0),
            "corrections_received": int(row.get("corrections_received") or 0),
            "auto_approved_count": int(row.get("auto_approved_count") or 0),
        }

    def save_learning_org_stats(
        self,
        organization_id: str,
        stats: Dict[str, Any],
    ) -> None:
        """Upsert the per-org cumulative learning counters."""
        self.initialize()
        now = datetime.now(timezone.utc).isoformat()
        sql = (
            "INSERT INTO learning_org_stats "
            "(organization_id, total_learned, corrections_received, auto_approved_count, updated_at) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (organization_id) DO UPDATE SET "
            "  total_learned = EXCLUDED.total_learned, "
            "  corrections_received = EXCLUDED.corrections_received, "
            "  auto_approved_count = EXCLUDED.auto_approved_count, "
            "  updated_at = EXCLUDED.updated_at"
        )
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, (
                organization_id,
                int(stats.get("total_learned") or 0),
                int(stats.get("corrections_received") or 0),
                int(stats.get("auto_approved_count") or 0),
                now,
            ))
            conn.commit()

    def learning_metrics(self, organization_id: str) -> Dict[str, Any]:
        """Aggregate learning metrics for one org (recomputed, not stored)."""
        self.initialize()
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) AS n FROM learning_corrections WHERE organization_id = %s",
                (organization_id,),
            )
            total_corrections = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                "SELECT COUNT(*) AS n FROM learning_patterns "
                "WHERE organization_id = %s AND confidence > 0.5",
                (organization_id,),
            )
            patterns_learned = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                "SELECT SUM(success_count) * 1.0 / NULLIF(SUM(usage_count), 0) AS acc "
                "FROM learning_patterns WHERE organization_id = %s AND usage_count > 0",
                (organization_id,),
            )
            row = cur.fetchone() or {}
            accuracy = float(row.get("acc") or 0.0)
        return {
            "total_corrections": total_corrections,
            "patterns_learned": patterns_learned,
            "accuracy": accuracy,
        }
