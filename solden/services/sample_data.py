"""Sample data loader — Module 10 (onboarding sample data mode).

Synthesises a curated set of AP items so a new customer can practice
the workflow end-to-end before going live with real data. Sample
rows are tagged ``is_sample = true``; production reads filter them
out so they never contaminate live dashboards or reports.

What the sample set covers:

  - A clean low-amount auto-approval candidate (under the Module 3
    "Auto-approve <$1K USD" template) so the leader sees the
    fast-path.
  - A mid-amount needs-approval invoice that should route to the AP
    Manager.
  - A high-amount invoice that should require dual approval.
  - A vendor-not-in-ERP-master gate trigger so the operator sees
    needs_info routing.
  - A field-conflict / extraction-review case for the field-review
    flow.
  - A failed-post case to exercise the retry surface.
  - A multi-currency case (EUR) so the FX panel shows up in
    Reports → Volume.
  - A few cleanly-posted historical rows to show the timeline view
    populated.

Loader is idempotent — calling it twice doesn't double-load. Clearer
deletes only sample rows for the calling org, never production.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# Sample-vendor naming convention: every name carries the "SAMPLE"
# prefix so even if a sample row leaks into a search, the operator
# recognises it on sight as practice data, not a real vendor they
# need to chase.
_SAMPLE_PREFIX = "SAMPLE — "


@dataclass
class SampleSpec:
    suffix: str
    vendor_name: str
    amount: float
    currency: str
    days_ago: int
    state: str
    exception_code: str = ""
    note: str = ""
    # The memory trail — REAL events committed through commit_memory_event so
    # every surface renders exactly what it renders in production: decision
    # whys, escalations, "Solden's read" distillations, retries. The memory
    # layer is the product; sample data without a trail demos a field
    # extractor. Each entry: {event_type, actor_type, actor_id, summary,
    # rationale?, human_confirmation_status?, hours_offset (after creation)}.
    memory: tuple = ()


def _spec_set() -> List[SampleSpec]:
    """The curated 10-row sample set. Deterministic so re-loads always
    produce the same shape (idempotency check below dedupes by
    invoice_number)."""
    return [
        SampleSpec(
            suffix="approve-fast",
            vendor_name=f"{_SAMPLE_PREFIX}Acme Coffee Supplies",
            amount=240.00,
            currency="USD",
            days_ago=2,
            state="closed",
            note="Auto-approved under the <$1K rule.",
            memory=(
                {"event_type": "invoice_validated", "actor_type": "agent",
                 "summary": "Extracted and validated — all fields above the confidence floor.",
                 "hours_offset": 1},
                {"event_type": "approve_invoice", "actor_type": "agent",
                 "summary": "Auto-approved",
                 "rationale": "Under the $1K auto-approve rule for recurring office vendors; 12th consecutive clean invoice from this vendor.",
                 "hours_offset": 2},
                {"event_type": "posted_to_erp", "actor_type": "agent",
                 "summary": "Posted to the ERP as bill #BILL-2241.",
                 "hours_offset": 3},
            ),
        ),
        SampleSpec(
            suffix="manager-review",
            vendor_name=f"{_SAMPLE_PREFIX}Cisco Systems",
            amount=4_500.00,
            currency="USD",
            days_ago=5,
            state="needs_approval",
            note="Mid-amount; routes to AP Manager.",
            memory=(
                {"event_type": "invoice_validated", "actor_type": "agent",
                 "summary": "Validated; amount is above the $1K manager threshold.",
                 "hours_offset": 1},
                {"event_type": "escalated_for_approval", "actor_type": "agent",
                 "summary": "Routed to the AP Manager",
                 "rationale": "Amount exceeds the $1K auto-approve ceiling; vendor history is clean (8 prior invoices, no exceptions), so single approval suffices.",
                 "hours_offset": 2},
            ),
        ),
        SampleSpec(
            suffix="dual-approval",
            vendor_name=f"{_SAMPLE_PREFIX}Booking Holdings BV",
            amount=78_000.00,
            currency="USD",
            days_ago=4,
            state="needs_second_approval",
            note="Above the dual-approval threshold.",
            memory=(
                {"event_type": "escalated_for_approval", "actor_type": "agent",
                 "summary": "Dual approval required",
                 "rationale": "Amount exceeds the $50K dual-approval threshold; two approvers required by policy v3.",
                 "hours_offset": 1},
                {"event_type": "first_approval_recorded", "actor_type": "user",
                 "actor_id": "maya@samplecorp.example",
                 "summary": "First approval recorded",
                 "rationale": "Within the signed Booking Holdings contract for Q2; CFO countersign pending per dual-approval policy.",
                 "hours_offset": 26},
            ),
        ),
        SampleSpec(
            suffix="vendor-master-miss",
            vendor_name=f"{_SAMPLE_PREFIX}Mystery Office Supplies LLC",
            amount=820.00,
            currency="USD",
            days_ago=3,
            state="needs_info",
            exception_code="vendor_not_in_erp_master",
            note="Vendor not yet in ERP master — needs info.",
            memory=(
                {"event_type": "exception_raised", "actor_type": "agent",
                 "summary": "Vendor not found in the ERP master — posting is gated until the vendor exists there.",
                 "hours_offset": 1},
                {"event_type": "request_info", "actor_type": "user",
                 "actor_id": "ben@samplecorp.example",
                 "summary": "Asked AP to verify the vendor",
                 "rationale": "New vendor with no ERP master record; asked AP to confirm the W-9 and bank details before creating it — Solden never creates vendor masters itself.",
                 "hours_offset": 5},
            ),
        ),
        SampleSpec(
            suffix="field-conflict",
            vendor_name=f"{_SAMPLE_PREFIX}AWS Cloud Services",
            amount=1_240.50,
            currency="USD",
            days_ago=6,
            state="validated",
            exception_code="field_conflict",
            note="Extraction confidence below the field-review floor.",
            memory=(
                {"event_type": "field_review_required", "actor_type": "agent",
                 "summary": "Extraction confidence on the amount field is below the review floor (0.71 < 0.85) — the scanned total is ambiguous between 1,240.50 and 1,210.50.",
                 "hours_offset": 1},
            ),
        ),
        SampleSpec(
            suffix="po-required",
            vendor_name=f"{_SAMPLE_PREFIX}Cisco Systems",
            amount=12_400.00,
            currency="USD",
            days_ago=8,
            state="needs_info",
            exception_code="po_required_missing",
            note="PO required for this vendor; not on invoice.",
            memory=(
                {"event_type": "three_way_match_evaluated", "actor_type": "agent",
                 "summary": "No purchase order on the invoice; this vendor requires one.",
                 "hours_offset": 1},
                {"event_type": "request_info", "actor_type": "user",
                 "actor_id": "ben@samplecorp.example",
                 "summary": "Asked the requester for the PO",
                 "rationale": "Cisco's contract requires a PO on all hardware invoices; asked the requester for the PO number before this can move.",
                 "hours_offset": 4},
                {"event_type": "vendor_followup_scheduled", "actor_type": "agent",
                 "summary": "No reply yet — Solden will nudge again in 3 business days.",
                 "hours_offset": 52},
            ),
        ),
        SampleSpec(
            suffix="failed-post",
            vendor_name=f"{_SAMPLE_PREFIX}Verizon Communications",
            amount=890.00,
            currency="USD",
            days_ago=1,
            state="failed_post",
            exception_code="erp_post_failed",
            note="ERP rejected the post — recoverable retry.",
            memory=(
                {"event_type": "approve_invoice", "actor_type": "user",
                 "actor_id": "maya@samplecorp.example",
                 "summary": "Approved",
                 "rationale": "Standard monthly telecom spend, matches the contracted rate.",
                 "hours_offset": 1},
                {"event_type": "erp_post_failed", "actor_type": "agent",
                 "summary": "ERP rejected the post — the GL period was locked. Recoverable: retry scheduled after the period reopens.",
                 "hours_offset": 2},
            ),
        ),
        SampleSpec(
            suffix="eur-cross-currency",
            vendor_name=f"{_SAMPLE_PREFIX}Café Paris",
            amount=320.00,
            currency="EUR",
            days_ago=10,
            state="closed",
            note="EUR invoice — exercises Module 9 FX conversion.",
            memory=(
                {"event_type": "approve_invoice", "actor_type": "user",
                 "actor_id": "maya@samplecorp.example",
                 "summary": "Approved",
                 "rationale": "Team offsite catering, pre-approved in the events budget; EUR settles from the EU entity.",
                 "hours_offset": 3},
                {"event_type": "posted_to_erp", "actor_type": "agent",
                 "summary": "Posted with FX conversion at the booking-date rate.",
                 "hours_offset": 5},
            ),
        ),
        SampleSpec(
            suffix="historic-clean-1",
            vendor_name=f"{_SAMPLE_PREFIX}Slack Technologies",
            amount=180.00,
            currency="USD",
            days_ago=15,
            state="closed",
            memory=(
                {"event_type": "approve_invoice", "actor_type": "user",
                 "actor_id": "ben@samplecorp.example",
                 "summary": "Approved",
                 "rationale": "ok",
                 "hours_offset": 2},
                {"event_type": "rationale_distilled", "actor_type": "agent",
                 "summary": "Solden distilled the why from the thread",
                 "rationale": "Monthly Slack subscription, consistent with the 12-month run rate; renewal confirmed by IT in the intake thread.",
                 "human_confirmation_status": "machine_distilled",
                 "hours_offset": 3},
                {"event_type": "posted_to_erp", "actor_type": "agent",
                 "summary": "Posted to the ERP.",
                 "hours_offset": 4},
            ),
        ),
        SampleSpec(
            suffix="historic-clean-2",
            vendor_name=f"{_SAMPLE_PREFIX}GitHub Enterprise",
            amount=2_100.00,
            currency="USD",
            days_ago=22,
            state="closed",
            memory=(
                {"event_type": "approve_invoice", "actor_type": "user",
                 "actor_id": "maya@samplecorp.example",
                 "summary": "Approved",
                 "rationale": "Annual GitHub Enterprise renewal at the negotiated seat price — checked against last year's PO.",
                 "hours_offset": 2},
                {"event_type": "posted_to_erp", "actor_type": "agent",
                 "summary": "Posted to the ERP.",
                 "hours_offset": 3},
            ),
        ),
    ]


def load_sample_data(db: Any, organization_id: str) -> Dict[str, Any]:
    """Insert the curated sample set for an org. Idempotent: re-running
    against an org that already has samples returns the existing
    count without creating duplicates.

    Returns ``{loaded: N, already_present: M}`` so the API layer
    can surface either "10 samples loaded" or "you already have 10
    samples in the org" without ambiguity.
    """
    existing = count_sample_data(db, organization_id)
    if existing > 0:
        return {"loaded": 0, "already_present": existing, "total": existing}

    specs = _spec_set()
    loaded = 0
    now = datetime.now(timezone.utc)
    for spec in specs:
        item_id = f"sample-{organization_id}-{spec.suffix}-{uuid.uuid4().hex[:8]}"
        invoice_number = f"SAMPLE-{spec.suffix.upper()}"
        try:
            payload = {
                "id": item_id,
                "organization_id": organization_id,
                "vendor_name": spec.vendor_name,
                "amount": spec.amount,
                "currency": spec.currency,
                "invoice_number": invoice_number,
                "state": spec.state,
                "exception_code": spec.exception_code,
                "is_sample": True,
                "metadata": {"sample_note": spec.note},
            }
            db.create_ap_item(payload)
            # Back-date created_at + (where applicable) erp_posted_at so
            # the sample rows show up across time-series reports rather
            # than all clustered at "now". Same UPDATE flips is_sample
            # to true — the existing create_ap_item INSERT doesn't
            # include is_sample in its column list (it predates this
            # migration), so we set it here in the same trip.
            backdated_dt = now - timedelta(days=spec.days_ago)
            backdated = backdated_dt.isoformat()
            with db.connect() as conn:
                cur = conn.cursor()
                if spec.state in ("closed", "posted_to_erp"):
                    cur.execute(
                        "UPDATE ap_items SET created_at = %s, "
                        "erp_posted_at = %s, is_sample = TRUE "
                        "WHERE id = %s",
                        (backdated, backdated, item_id),
                    )
                else:
                    cur.execute(
                        "UPDATE ap_items SET created_at = %s, "
                        "is_sample = TRUE WHERE id = %s",
                        (backdated, item_id),
                    )
                conn.commit()
            _commit_sample_memory(
                db,
                organization_id=organization_id,
                item_id=item_id,
                spec=spec,
                created_at=backdated_dt,
            )
            loaded += 1
        except Exception as exc:
            logger.warning(
                "[sample_data] failed to load %s: %s", spec.suffix, exc,
            )

    return {"loaded": loaded, "already_present": 0, "total": loaded}


def _commit_sample_memory(
    db: Any,
    *,
    organization_id: str,
    item_id: str,
    spec: SampleSpec,
    created_at: datetime,
) -> None:
    """Commit the spec's memory trail through the REAL memory-event funnel —
    the surfaces must render production behavior, not props.

    Audit rows are append-only by trigger, so these events survive
    clear_sample_data. That is contained by design: org-wide memory reads
    (search_decision_reasons) require the box to still exist, so cleared
    samples' whys vanish from answers automatically.
    """
    from solden.services.memory_events import commit_memory_event

    for entry in spec.memory:
        occurred = created_at + timedelta(hours=float(entry.get("hours_offset", 1)))
        try:
            commit_memory_event(
                db,
                box_type="ap_item",
                box_id=item_id,
                organization_id=organization_id,
                event_type=str(entry["event_type"]),
                source="workspace",
                actor_type=str(entry.get("actor_type") or "agent"),
                actor_id=entry.get("actor_id") or "solden-agent",
                rationale=entry.get("rationale"),
                summary=entry.get("summary"),
                human_confirmation_status=entry.get("human_confirmation_status"),
                occurred_at=occurred.isoformat(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[sample_data] memory event failed for %s/%s: %s",
                spec.suffix, entry.get("event_type"), exc,
            )


def clear_sample_data(db: Any, organization_id: str) -> Dict[str, Any]:
    """Delete every sample row for an org. Production rows
    (``is_sample = false``) are untouched — this is the contract
    that makes "sample data does not contaminate production"
    enforceable at SQL level.

    The samples' audit/memory events are append-only (DB trigger) and
    remain; they are excluded from org-wide memory reads by the
    box-must-exist guard in search_decision_reasons."""
    deleted = 0
    try:
        with db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM ap_items "
                "WHERE organization_id = %s AND is_sample = TRUE",
                (organization_id,),
            )
            deleted = cur.rowcount or 0
            conn.commit()
    except Exception as exc:
        logger.warning(
            "[sample_data] clear failed for org=%s: %s", organization_id, exc,
        )
    return {"deleted": int(deleted)}


def count_sample_data(db: Any, organization_id: str) -> int:
    try:
        with db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*)::bigint FROM ap_items "
                "WHERE organization_id = %s AND is_sample = TRUE",
                (organization_id,),
            )
            row = cur.fetchone()
            return int((row[0] if row else 0) or 0)
    except Exception as exc:
        logger.debug(
            "[sample_data] count failed for org=%s: %s", organization_id, exc,
        )
        return 0


def list_sample_items(
    db: Any, organization_id: str, limit: int = 50,
) -> List[Dict[str, Any]]:
    """Return the sample AP items for an org so the dashboard can
    render the practice-data preview without exposing them to
    production reads."""
    try:
        with db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, vendor_name, amount, currency, invoice_number, "
                "       state, exception_code, created_at "
                "FROM ap_items "
                "WHERE organization_id = %s AND is_sample = TRUE "
                "ORDER BY created_at DESC "
                "LIMIT %s",
                (organization_id, int(limit)),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.debug(
            "[sample_data] list failed for org=%s: %s", organization_id, exc,
        )
        return []
