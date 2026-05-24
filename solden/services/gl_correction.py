"""
GL Code Correction Service

Allows users to correct GL codes on invoices and teaches the system
to apply better mappings in the future.

The correction → learning loop:
1. User sees suggested GL code
2. User corrects it in sidebar
3. System records correction
4. Learning service uses corrections to improve future suggestions
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid

from solden.core.database import get_db
from solden.core.org_utils import assert_org_id
from solden.services.finance_learning import get_finance_learning_service

logger = logging.getLogger(__name__)


@dataclass
class GLCorrection:
    """A GL code correction."""
    correction_id: str
    invoice_id: str
    vendor: str
    
    # The correction
    original_gl: str
    original_gl_description: str
    corrected_gl: str
    corrected_gl_description: str
    
    # Context
    amount: Optional[float] = None
    category: Optional[str] = None
    reason: Optional[str] = None
    
    # Metadata
    corrected_by: str = "user"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    applied_to_invoice: bool = False
    learned: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            # ``id`` is the gl_corrections PK; keep it in sync with the
            # service-level correction_id so a stored row round-trips.
            "id": self.correction_id,
            "correction_id": self.correction_id,
            "invoice_id": self.invoice_id,
            "vendor": self.vendor,
            "original_gl": self.original_gl,
            "original_gl_description": self.original_gl_description,
            "corrected_gl": self.corrected_gl,
            "corrected_gl_description": self.corrected_gl_description,
            "amount": self.amount,
            "category": self.category,
            "reason": self.reason,
            "corrected_by": self.corrected_by,
            "timestamp": self.timestamp,
            "applied_to_invoice": self.applied_to_invoice,
            "learned": self.learned,
        }


@dataclass
class GLAccount:
    """A GL account in the chart of accounts."""
    code: str
    name: str
    account_type: str  # expense, asset, liability, equity, revenue
    category: Optional[str] = None
    parent_code: Optional[str] = None
    is_active: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "account_type": self.account_type,
            "category": self.category,
            "parent_code": self.parent_code,
            "is_active": self.is_active,
        }


# Default chart of accounts for demo
DEFAULT_GL_ACCOUNTS = [
    GLAccount("5000", "Operating Expenses", "expense", "Operations"),
    GLAccount("5100", "Office Supplies", "expense", "Operations"),
    GLAccount("5200", "Software & Subscriptions", "expense", "Technology"),
    GLAccount("5210", "Cloud Infrastructure", "expense", "Technology"),
    GLAccount("5220", "SaaS Tools", "expense", "Technology"),
    GLAccount("5300", "Professional Services", "expense", "Professional"),
    GLAccount("5310", "Legal Fees", "expense", "Professional"),
    GLAccount("5320", "Accounting Fees", "expense", "Professional"),
    GLAccount("5330", "Consulting Fees", "expense", "Professional"),
    GLAccount("5400", "Marketing & Advertising", "expense", "Marketing"),
    GLAccount("5410", "Digital Advertising", "expense", "Marketing"),
    GLAccount("5420", "Events & Sponsorships", "expense", "Marketing"),
    GLAccount("5500", "Travel & Entertainment", "expense", "T&E"),
    GLAccount("5510", "Airfare", "expense", "T&E"),
    GLAccount("5520", "Hotels", "expense", "T&E"),
    GLAccount("5530", "Meals", "expense", "T&E"),
    GLAccount("5600", "Utilities", "expense", "Facilities"),
    GLAccount("5700", "Rent & Occupancy", "expense", "Facilities"),
    GLAccount("5800", "Insurance", "expense", "Risk"),
    GLAccount("5900", "Depreciation", "expense", "Non-Cash"),
    GLAccount("6000", "Cost of Goods Sold", "expense", "COGS"),
    GLAccount("6100", "Contractor Payments", "expense", "Payroll"),
    GLAccount("6200", "Employee Benefits", "expense", "Payroll"),
    GLAccount("6250", "Payment Processing Fees", "expense", "Operations"),
    GLAccount("7000", "Other Expenses", "expense", "Other"),
]


class GLCorrectionService:
    """GL code correction persistence + analytics (org-scoped, DB-backed).

    The correction -> learning loop has two halves:
      - Learning rules (vendor/field patterns) are owned by the generic
        ``finance_learning.record_manual_field_correction`` path, which the
        live operator-correction sites already call for every field.
      - This service owns the GL-specific persistence layer: it writes each
        GL correction to the ``gl_corrections`` table and reads it back for
        history, analytics, and a corrections-history suggestion source.

    All reads and writes go through the DB (no in-process cache), so history
    and stats are correct across workers and restarts.
    """

    def __init__(self, organization_id: str):
        self.organization_id = assert_org_id(
            organization_id, context="GLCorrectionService"
        )
        # Built-in label map only. The real chart of accounts is ERP-sourced
        # via /api/workspace/chart-of-accounts; this list just renders a human
        # description next to a GL code.
        self._gl_accounts: List[GLAccount] = list(DEFAULT_GL_ACCOUNTS)

    @property
    def db(self):
        """Resolve the DB lazily so a cached singleton never holds a stale handle."""
        return get_db()

    # ------------------------------------------------------------------ #
    # Writes                                                             #
    # ------------------------------------------------------------------ #

    def persist_correction(
        self,
        *,
        invoice_id: str,
        vendor: str,
        original_gl: str,
        corrected_gl: str,
        corrected_by: str = "user",
        amount: Optional[float] = None,
        category: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> GLCorrection:
        """Persist a GL correction to the gl_corrections table.

        Write-only: does NOT record a learning rule. Call this from a site
        that already records the generic field correction (the live
        operator-correction path), so learning stays single-pathed.
        """
        correction = GLCorrection(
            correction_id=f"GLC-{uuid.uuid4().hex[:8]}",
            invoice_id=invoice_id,
            vendor=vendor,
            original_gl=original_gl,
            original_gl_description=self._get_gl_description(original_gl),
            corrected_gl=corrected_gl,
            corrected_gl_description=self._get_gl_description(corrected_gl),
            amount=amount,
            category=category,
            reason=reason,
            corrected_by=corrected_by,
        )
        self._save_correction(correction)
        return correction

    def correct_gl_code(
        self,
        invoice_id: str,
        vendor: str,
        original_gl: str,
        corrected_gl: str,
        corrected_by: str = "user",
        amount: Optional[float] = None,
        category: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> GLCorrection:
        """Standalone GL correction entry: persist AND record learning.

        Use this when the caller is NOT already on the generic
        ``record_manual_field_correction`` path. The live operator-correction
        sites call :meth:`persist_correction` instead (learning is recorded
        upstream there), so this never double-records.
        """
        correction = self.persist_correction(
            invoice_id=invoice_id,
            vendor=vendor,
            original_gl=original_gl,
            corrected_gl=corrected_gl,
            corrected_by=corrected_by,
            amount=amount,
            category=category,
            reason=reason,
        )
        try:
            learning = get_finance_learning_service(self.organization_id, db=self.db)
            learning.record_manual_field_correction(
                field="gl_code",
                original_value=original_gl,
                corrected_value=corrected_gl,
                context={
                    "vendor": vendor,
                    "amount": amount,
                    "category": category,
                    "original_description": correction.original_gl_description,
                    "corrected_description": correction.corrected_gl_description,
                },
                actor_id=corrected_by,
                invoice_id=invoice_id,
                feedback=reason,
            )
            correction.learned = True
        except Exception as exc:
            logger.warning("Failed to record GL correction for learning: %s", exc)
        return correction

    def _save_correction(self, correction: GLCorrection) -> None:
        """Persist a correction row to the gl_corrections table."""
        try:
            self.db.save_gl_correction(self.organization_id, correction.to_dict())
        except Exception as exc:
            logger.warning("Failed to save GL correction: %s", exc)

    # ------------------------------------------------------------------ #
    # Reads (DB-backed, org-scoped)                                      #
    # ------------------------------------------------------------------ #

    def get_recent_corrections(
        self,
        vendor: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Recent GL corrections for the org, newest first.

        Returns plain row dicts (id, invoice_id, vendor, original_gl,
        corrected_gl, reason, corrected_by, corrected_at, ...).
        """
        fetch_limit = 500 if vendor else limit
        rows = self.db.get_gl_corrections(self.organization_id, limit=fetch_limit)
        if vendor:
            vl = vendor.lower()
            rows = [r for r in rows if vl in str(r.get("vendor", "")).lower()]
        return rows[:limit]

    def get_correction_stats(self) -> Dict[str, Any]:
        """GL correction analytics: totals, by-vendor, common remaps, 30/60-day trend."""
        stats = self.db.get_gl_stats(self.organization_id)
        stats["unique_vendors"] = len(stats.get("by_vendor") or [])
        return stats

    def get_history_suggestion(self, vendor: str) -> Optional[Dict[str, Any]]:
        """Suggest a GL code from this org's correction history for a vendor.

        Returns the most frequently corrected-to GL code for the vendor
        (with a frequency-weighted confidence), or None when there isn't
        enough signal. DB-backed and org-scoped.
        """
        if not vendor:
            return None
        rows = self.get_recent_corrections(vendor=vendor, limit=200)
        if not rows:
            return None
        gl_counts: Dict[str, int] = {}
        for r in rows:
            code = r.get("corrected_gl")
            if code:
                gl_counts[code] = gl_counts.get(code, 0) + 1
        if not gl_counts:
            return None
        best = max(gl_counts, key=lambda k: gl_counts[k])
        total = len(rows)
        confidence = min(0.95, gl_counts[best] / total * (0.5 + total * 0.1))
        if confidence <= 0.5:
            return None
        return {
            "gl_code": best,
            "suggested_gl": best,
            "gl_description": self._get_gl_description(best),
            "confidence": round(confidence, 2),
            "source": "corrections_history",
        }

    def _get_gl_description(self, gl_code: str) -> str:
        """Human-readable description for a GL code, from the built-in label map."""
        for account in self._gl_accounts:
            if account.code == gl_code:
                return account.name
        return "Unknown Account"


# Singleton (per org)
_gl_correction_services: Dict[str, GLCorrectionService] = {}


def get_gl_correction(organization_id: str) -> GLCorrectionService:
    """Get the GL correction service for an organization."""
    organization_id = assert_org_id(
        organization_id, context="get_gl_correction"
    )
    if organization_id not in _gl_correction_services:
        _gl_correction_services[organization_id] = GLCorrectionService(organization_id)
    return _gl_correction_services[organization_id]
