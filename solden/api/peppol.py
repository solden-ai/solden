"""PEPPOL UBL inbound + outbound API (Wave 4 / F1 + F2).

Inbound (F1):
  POST /api/workspace/peppol/import
  POST /api/workspace/peppol/preview

Outbound (F2):
  POST /api/workspace/peppol/credit-notes
      Body: { ap_item_id, credit_amount, reason, credit_note_id?, issue_date? }
      Returns: { credit_note_id, ap_item_id, ubl_xml }
      Generates a UBL CreditNote (TypeCode 381) referencing the
      original invoice. The supplier on the credit note is the
      issuing org; the customer is the vendor we are crediting.
"""
from __future__ import annotations

import hashlib
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from solden.core.auth import TokenData, get_current_user
from solden.core.database import get_db
from solden.services.peppol_ubl_generator import (
    build_credit_note_from_ap_item,
)
from solden.services.peppol_ubl_parser import (
    ParsedPeppolInvoice,
    parse_peppol_ubl_invoice,
)

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/workspace/peppol",
    tags=["peppol"],
)


_MAX_BODY_BYTES = 5 * 1024 * 1024  # 5 MB cap


# ── Models ──────────────────────────────────────────────────────────


class PeppolImportResponse(BaseModel):
    ap_item_id: str
    invoice_id: Optional[str] = None
    supplier_name: Optional[str] = None
    payable_amount: Optional[float] = None
    currency: Optional[str] = None
    derived_treatment: Optional[str] = None
    derived_vat_code: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class PeppolPreviewResponse(BaseModel):
    invoice_id: Optional[str] = None
    supplier_name: Optional[str] = None
    supplier_country: Optional[str] = None
    supplier_vat_id: Optional[str] = None
    issue_date: Optional[str] = None
    due_date: Optional[str] = None
    currency: Optional[str] = None
    line_extension_amount: Optional[float] = None
    tax_exclusive_amount: Optional[float] = None
    tax_inclusive_amount: Optional[float] = None
    payable_amount: Optional[float] = None
    tax_amount: Optional[float] = None
    derived_treatment: Optional[str] = None
    derived_vat_code: Optional[str] = None
    derived_vat_rate: Optional[float] = None
    line_items_count: int = 0
    warnings: List[str] = Field(default_factory=list)


def _serialize_preview(parsed: ParsedPeppolInvoice) -> PeppolPreviewResponse:
    return PeppolPreviewResponse(
        invoice_id=parsed.invoice_id,
        supplier_name=parsed.supplier_name,
        supplier_country=parsed.supplier_country,
        supplier_vat_id=parsed.supplier_vat_id,
        issue_date=parsed.issue_date,
        due_date=parsed.due_date,
        currency=parsed.currency,
        line_extension_amount=(
            float(parsed.line_extension_amount)
            if parsed.line_extension_amount is not None else None
        ),
        tax_exclusive_amount=(
            float(parsed.tax_exclusive_amount)
            if parsed.tax_exclusive_amount is not None else None
        ),
        tax_inclusive_amount=(
            float(parsed.tax_inclusive_amount)
            if parsed.tax_inclusive_amount is not None else None
        ),
        payable_amount=(
            float(parsed.payable_amount)
            if parsed.payable_amount is not None else None
        ),
        tax_amount=(
            float(parsed.tax_amount)
            if parsed.tax_amount is not None else None
        ),
        derived_treatment=parsed.derived_treatment,
        derived_vat_code=parsed.derived_vat_code,
        derived_vat_rate=(
            float(parsed.derived_vat_rate)
            if parsed.derived_vat_rate is not None else None
        ),
        line_items_count=len(parsed.line_items or []),
        warnings=list(parsed.warnings),
    )


def _decimal_to_float(value: Optional[Decimal]) -> Optional[float]:
    return float(value) if value is not None else None


def _peppol_source_id(parsed: ParsedPeppolInvoice, raw: bytes) -> str:
    if parsed.invoice_id:
        return parsed.invoice_id
    return f"sha256:{hashlib.sha256(raw).hexdigest()[:32]}"


def _serialize_tax_subtotals(parsed: ParsedPeppolInvoice) -> List[Dict[str, Any]]:
    return [
        {
            "taxable_amount": _decimal_to_float(s.get("taxable_amount")),
            "tax_amount": _decimal_to_float(s.get("tax_amount")),
            "category_id": s.get("category_id"),
            "percent": _decimal_to_float(s.get("percent")),
        }
        for s in parsed.tax_subtotals
    ]


def _peppol_vat_update_kwargs(parsed: ParsedPeppolInvoice) -> Dict[str, Any]:
    update_kwargs: Dict[str, Any] = {}
    if parsed.tax_exclusive_amount is not None:
        update_kwargs["net_amount"] = parsed.tax_exclusive_amount
    if parsed.tax_amount is not None:
        update_kwargs["vat_amount"] = parsed.tax_amount
    if parsed.derived_vat_rate is not None:
        update_kwargs["vat_rate"] = parsed.derived_vat_rate
    if parsed.derived_vat_code:
        update_kwargs["vat_code"] = parsed.derived_vat_code
    if parsed.derived_treatment:
        update_kwargs["tax_treatment"] = parsed.derived_treatment
    if parsed.supplier_country:
        update_kwargs["bill_country"] = parsed.supplier_country
    return update_kwargs


def _build_peppol_invoice_data(
    *,
    parsed: ParsedPeppolInvoice,
    raw: bytes,
    user: TokenData,
):
    from solden.services.invoice_models import InvoiceData

    source_id = _peppol_source_id(parsed, raw)
    invoice_kwargs = parsed.to_invoice_data_kwargs()
    return InvoiceData(
        **invoice_kwargs,
        source_type="peppol_ubl",
        source_id=source_id,
        erp_native=False,
        subject=(
            f"PEPPOL e-invoice {parsed.invoice_id or source_id} "
            f"from {parsed.supplier_name}"
        ),
        sender=(
            f"{parsed.supplier_name} <peppol:{parsed.supplier_vat_id}>"
            if parsed.supplier_vat_id
            else f"{parsed.supplier_name} via PEPPOL"
        ),
        confidence=1.0,
        organization_id=user.organization_id,
        user_id=user.user_id,
        correlation_id=f"peppol:{user.organization_id}:{source_id}",
        erp_metadata={
            "intake_source": "peppol_ubl",
            "peppol_invoice_id": parsed.invoice_id,
            "peppol_source_id": source_id,
            "peppol_customization_id": parsed.customization_id,
            "peppol_profile_id": parsed.profile_id,
            "invoice_type_code": parsed.invoice_type_code,
            "supplier_vat_id": parsed.supplier_vat_id,
            "supplier_country": parsed.supplier_country,
            "customer_name": parsed.customer_name,
            "customer_vat_id": parsed.customer_vat_id,
            "tax_subtotals": _serialize_tax_subtotals(parsed),
            "warnings": list(parsed.warnings),
        },
    )


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/preview", response_model=PeppolPreviewResponse)
async def peppol_preview(
    request: Request,
    user: TokenData = Depends(get_current_user),
):
    """Pure parse — no AP item created. Useful for an import-dry-run
    button in the workspace UI."""
    raw = await request.body()
    if not raw:
        raise HTTPException(status_code=400, detail="empty_body")
    if len(raw) > _MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="body_too_large")
    parsed = parse_peppol_ubl_invoice(raw)
    return _serialize_preview(parsed)


@router.post("/import", response_model=PeppolImportResponse)
async def peppol_import(
    request: Request,
    user: TokenData = Depends(get_current_user),
):
    """Parse + enter the canonical invoice workflow.

    PEPPOL is a first-class intake channel: the route parses the UBL
    payload into ``InvoiceData`` and lets ``InvoiceWorkflowService`` own
    AP item creation, validation, routing, audit, and downstream memory.
    The route then adds PEPPOL-specific VAT fields to the created item.
    """
    raw = await request.body()
    if not raw:
        raise HTTPException(status_code=400, detail="empty_body")
    if len(raw) > _MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="body_too_large")
    parsed = parse_peppol_ubl_invoice(raw)

    # Hard-fail conditions: no payable amount means we can't even put
    # a sensible row in ap_items.
    if parsed.payable_amount is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "peppol_invoice_unparseable:missing_payable_amount; "
                f"warnings={parsed.warnings}"
            ),
        )
    if not parsed.supplier_name:
        raise HTTPException(
            status_code=400,
            detail=(
                "peppol_invoice_unparseable:missing_supplier_name; "
                f"warnings={parsed.warnings}"
            ),
        )

    db = get_db()
    invoice = _build_peppol_invoice_data(parsed=parsed, raw=raw, user=user)
    from solden.services.invoice_workflow import get_invoice_workflow

    workflow = get_invoice_workflow(user.organization_id)
    workflow_result = await workflow.process_new_invoice(invoice)
    if not isinstance(workflow_result, dict):
        raise HTTPException(status_code=500, detail="peppol_workflow_failed")

    row = db.get_invoice_status(invoice.gmail_id)
    ap_item_id = (
        (row or {}).get("id")
        or workflow_result.get("ap_item_id")
        or workflow_result.get("invoice_id")
    )
    if workflow_result.get("status") == "error" and not ap_item_id:
        raise HTTPException(status_code=422, detail=workflow_result)
    if workflow_result.get("status") == "held" and not ap_item_id:
        raise HTTPException(status_code=423, detail=workflow_result)
    if not ap_item_id:
        raise HTTPException(status_code=500, detail="peppol_ap_item_not_created")
    response_warnings = list(parsed.warnings)
    if workflow_result.get("status") == "error":
        response_warnings.append(
            f"workflow_warning:{workflow_result.get('error') or 'unknown'}"
        )

    # Wire the VAT split now so the JE preview (E4) is correct
    # without an extra vat-recalculate call.
    update_kwargs = _peppol_vat_update_kwargs(parsed)
    if update_kwargs:
        db.update_ap_item(
            ap_item_id,
            **update_kwargs,
            _actor_type="user",
            _actor_id=user.user_id,
            _source="peppol_import",
        )

    # Operational-memory boundary: an inbound e-invoice is a work item entering
    # from a channel. Link it to the new box and write the memory event, the way
    # the other intakes do; PEPPOL was creating the item outside the layer.
    try:
        from solden.services.operational_memory_capture import (
            capture_operational_memory_event,
        )

        capture_operational_memory_event(
            db,
            organization_id=user.organization_id,
            actor_type="user",
            actor_id=user.user_id,
            observed={
                "box_type": "ap_item",
                "box_id": ap_item_id,
                "ap_item_id": ap_item_id,
                "source": "peppol_ubl",
                "event_type": "peppol_intake_created",
                "summary": (
                    f"Imported PEPPOL/UBL e-invoice {parsed.invoice_id or ''} "
                    f"from {parsed.supplier_name}."
                ),
                "rationale": (
                    "Inbound PEPPOL/UBL e-invoice parsed and created as a work item."
                ),
                "evidence": {
                    "type": "peppol_ubl",
                    "invoice_id": parsed.invoice_id,
                    "supplier_name": parsed.supplier_name,
                    "warnings": response_warnings,
                },
                "confidence": 1.0,
                "auto_commit": True,
                "source_refs": {
                    "ap_item_id": ap_item_id,
                    "peppol_invoice_id": parsed.invoice_id,
                },
                "external_refs": {"peppol_invoice_id": parsed.invoice_id},
                "idempotency_key": (
                    f"memory-event:peppol:{user.organization_id}:"
                    f"{parsed.invoice_id or ap_item_id}"
                ),
            },
        )
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning(
            "[peppol] operational-memory capture failed for %s: %s", ap_item_id, exc
        )

    return PeppolImportResponse(
        ap_item_id=ap_item_id,
        invoice_id=parsed.invoice_id,
        supplier_name=parsed.supplier_name,
        payable_amount=(
            float(parsed.payable_amount)
            if parsed.payable_amount is not None else None
        ),
        currency=parsed.currency,
        derived_treatment=parsed.derived_treatment,
        derived_vat_code=parsed.derived_vat_code,
        warnings=response_warnings,
    )


# ── Outbound (F2) ──────────────────────────────────────────────────


class CreditNoteRequest(BaseModel):
    ap_item_id: str = Field(..., min_length=1)
    credit_amount: float = Field(..., gt=0)
    reason: str = Field(..., min_length=1, max_length=1000)
    credit_note_id: Optional[str] = Field(None, max_length=128)
    issue_date: Optional[str] = Field(None, max_length=32)


class CreditNoteResponse(BaseModel):
    credit_note_id: str
    ap_item_id: str
    ubl_xml: str


@router.post("/credit-notes", response_model=CreditNoteResponse)
def issue_credit_note(
    body: CreditNoteRequest,
    user: TokenData = Depends(get_current_user),
):
    """Generate a UBL CreditNote XML payload referencing one
    ``ap_items`` row.

    The credit note is org-scoped: the AP item must belong to the
    authenticated user's organization. Cross-org access surfaces 404.
    """
    db = get_db()
    item = db.get_ap_item(body.ap_item_id)
    if item is None or item.get("organization_id") != user.organization_id:
        raise HTTPException(status_code=404, detail="ap_item_not_found")

    org = db.get_organization(user.organization_id) or {
        "id": user.organization_id,
        "organization_name": user.organization_id,
    }

    try:
        xml = build_credit_note_from_ap_item(
            ap_item=item,
            organization=org,
            credit_amount=Decimal(str(body.credit_amount)),
            credit_reason=body.reason,
            credit_note_id=body.credit_note_id,
            issue_date=body.issue_date,
        )
    except Exception as exc:
        logger.exception(
            "peppol credit note generation failed for ap_item=%s",
            body.ap_item_id,
        )
        raise HTTPException(status_code=500, detail=f"generation_failed:{exc}")

    cn_id = body.credit_note_id or f"CN-{item.get('id')}"
    return CreditNoteResponse(
        credit_note_id=cn_id,
        ap_item_id=body.ap_item_id,
        ubl_xml=xml.decode("utf-8"),
    )
