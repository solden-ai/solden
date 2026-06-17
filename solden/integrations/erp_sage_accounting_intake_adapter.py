"""Sage Business Cloud Accounting implementation of IntakeAdapter."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Mapping, Optional

from solden.core.ap_states import APState
from solden.core.database import get_db
from solden.core.erp_webhook_verify import verify_sage_accounting_signature
from solden.core.http_client import get_http_client
from solden.integrations.erp_router import _erp_connection_from_row
from solden.services.intake_adapter import (
    IntakeEnvelope,
    StateUpdate,
    register_adapter,
)
from solden.services.invoice_models import InvoiceData

logger = logging.getLogger(__name__)


_EVENT_TYPE_MAP = {
    "create": "create",
    "created": "create",
    "post": "posted",
    "posted": "posted",
    "update": "update",
    "updated": "update",
    "change": "update",
    "changed": "update",
    "paid": "paid",
    "fully_paid": "paid",
    "fullypaid": "paid",
    "void": "cancelled",
    "voided": "cancelled",
    "cancel": "cancelled",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "delete": "delete",
    "deleted": "delete",
}


class SageAccountingIntakeAdapter:
    """Sage Accounting purchase-invoice webhook intake."""

    source_type = "sage_accounting"

    async def verify_signature(
        self, raw: bytes, headers: Mapping[str, str], secret: str,
    ) -> bool:
        signature = (
            headers.get("x-sage-accounting-signature")
            or headers.get("X-Sage-Accounting-Signature")
            or headers.get("x-sage-signature")
            or headers.get("X-Sage-Signature")
        )
        timestamp = (
            headers.get("x-sage-accounting-timestamp")
            or headers.get("X-Sage-Accounting-Timestamp")
            or headers.get("x-sage-timestamp")
            or headers.get("X-Sage-Timestamp")
        )
        return verify_sage_accounting_signature(raw, signature, timestamp, secret)

    async def parse_envelope(
        self, raw: bytes, headers: Mapping[str, str], organization_id: str,
    ) -> IntakeEnvelope:
        payload = _json_dict(raw)
        body = _payload_body(payload)
        resource_type = str(_first_present(
            body, "resource_type", "resourceType", "event_category",
            "eventCategory", "object", "entity", "type",
        ) or "").strip()
        if resource_type and not _is_purchase_invoice_resource(resource_type):
            event_type = ""
        else:
            event_type = _normalize_event_type(_first_present(
                body, "event_type", "eventType", "operation", "action",
                "status", "payment_status", "paymentStatus",
            ))

        source_id = _first_present(
            body, "resource_id", "resourceId", "purchase_invoice_id",
            "purchaseInvoiceId", "invoice_id", "invoiceId", "id",
        )
        return IntakeEnvelope(
            source_type=self.source_type,
            event_type=event_type,
            source_id=str(source_id or "").strip(),
            organization_id=organization_id,
            raw_payload=payload,
            event_id=str(_first_present(body, "event_id", "eventId", "idempotency_key") or "").strip() or None,
            received_at=str(_first_present(body, "event_time", "eventTime", "timestamp", "created_at") or "").strip() or None,
            channel_metadata={
                "sage_accounting_business_id": str(_first_present(body, "business_id", "businessId", "tenant_id") or "").strip(),
                "sage_accounting_resource_type": resource_type,
            },
        )

    async def enrich(
        self, organization_id: str, envelope: IntakeEnvelope,
    ) -> InvoiceData:
        connection = self._resolve_connection(organization_id)
        payload_invoice = _payload_body(envelope.raw_payload)
        if _looks_like_invoice_payload(payload_invoice):
            return self._build_invoice_from_purchase_invoice(
                envelope, payload_invoice, organization_id,
            )
        if connection is not None:
            invoice = await self._fetch_purchase_invoice(connection, envelope.source_id)
            if invoice:
                return self._build_invoice_from_purchase_invoice(
                    envelope, invoice, organization_id,
                )
        return self._thin_invoice_from_envelope(envelope, organization_id)

    async def derive_state_update(
        self, organization_id: str, envelope: IntakeEnvelope,
    ) -> StateUpdate:
        if envelope.event_type in {"paid", "cancelled", "delete"}:
            return StateUpdate(target_state=APState.CLOSED.value)
        if envelope.event_type == "update":
            return StateUpdate(target_state=None, idempotent_no_op_allowed=True)
        return StateUpdate(target_state=None)

    @staticmethod
    def _resolve_connection(organization_id: str):
        db = get_db()
        if not hasattr(db, "get_erp_connections"):
            return None
        try:
            for row in db.get_erp_connections(organization_id):
                if str(row.get("erp_type") or "").lower() == "sage_accounting":
                    return _erp_connection_from_row(row)
        except Exception as exc:  # noqa: BLE001
            logger.warning("sage_accounting_intake_adapter: connection lookup failed - %s", exc)
        return None

    @staticmethod
    async def _fetch_purchase_invoice(connection: Any, invoice_id: str) -> Optional[Dict[str, Any]]:
        ref = str(invoice_id or "").strip()
        if not ref:
            return None
        try:
            from solden.integrations import erp_sage_accounting as sage

            client = get_http_client()
            response = await client.get(
                f"{sage._base_url(connection)}/purchase_invoices/{ref}",
                headers=sage._headers(connection),
                timeout=30,
            )
            if response.status_code >= 400:
                logger.warning(
                    "sage_accounting_intake_adapter: purchase_invoice fetch %s returned %d",
                    ref, response.status_code,
                )
                return None
            payload = response.json() or {}
            invoice = sage._purchase_invoice_from_body(payload)
            return invoice if isinstance(invoice, dict) else None
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "sage_accounting_intake_adapter: purchase_invoice fetch failed ref=%s - %s",
                ref, exc,
            )
            return None

    def _thin_invoice_from_envelope(
        self, envelope: IntakeEnvelope, organization_id: str,
    ) -> InvoiceData:
        from solden.services.extraction_provenance import (
            METHOD_API_PASSTHROUGH,
            SOURCE_ERP_NATIVE_SAGE_ACCOUNTING,
            build_passthrough_evidence,
            build_passthrough_provenance,
        )

        provenance = build_passthrough_provenance(
            source=SOURCE_ERP_NATIVE_SAGE_ACCOUNTING,
            source_ref=envelope.source_id,
            method=METHOD_API_PASSTHROUGH,
            fields={"invoice_number": envelope.source_id},
        )
        return InvoiceData(
            source_type="sage_accounting",
            source_id=envelope.source_id,
            erp_native=True,
            erp_metadata={
                "sage_accounting_purchase_invoice_id": envelope.source_id,
                "sage_accounting_business_id": envelope.channel_metadata.get("sage_accounting_business_id"),
                "fallback_thin_intake": True,
            },
            subject=f"Sage Accounting purchase invoice {envelope.source_id}",
            sender="<sage-accounting@erp-native>",
            vendor_name="Unknown vendor",
            amount=0.0,
            currency="USD",
            invoice_number=envelope.source_id,
            confidence=1.0,
            organization_id=organization_id,
            correlation_id=f"erp-intake:sage-accounting:{envelope.event_id or envelope.source_id}",
            field_provenance=provenance,
            field_evidence=build_passthrough_evidence(
                field_provenance=provenance,
                source_label="Sage Accounting (thin intake)",
            ),
        )

    @staticmethod
    def _build_invoice_from_purchase_invoice(
        envelope: IntakeEnvelope,
        invoice: Dict[str, Any],
        organization_id: str,
    ) -> InvoiceData:
        invoice_id = str(_first_present(invoice, "id", "resource_id") or envelope.source_id).strip()
        contact = invoice.get("contact") if isinstance(invoice.get("contact"), dict) else {}
        vendor_name = str(
            contact.get("name")
            or _first_present(invoice, "contact_name", "vendor_name", "displayed_as")
            or "Unknown vendor"
        ).strip()
        vendor_id = str(contact.get("id") or _first_present(invoice, "contact_id", "vendor_id") or "").strip()
        contact_email = str(
            contact.get("email")
            or (contact.get("main_contact_person") or {}).get("email")
            or _first_present(invoice, "email", "contact_email")
            or ""
        ).strip()
        amount = _safe_float(
            _first_present(invoice, "total_amount", "gross_amount", "total", "amount"),
            default=0.0,
        )
        currency = _currency(_first_present(invoice, "currency", "currency_code", "currency_id"))
        invoice_number = str(
            _first_present(invoice, "reference", "invoice_number", "displayed_as")
            or invoice_id
            or envelope.source_id
        ).strip()
        due_date = _date_string(_first_present(invoice, "due_date", "payment_due_date"))
        invoice_date = _date_string(_first_present(invoice, "date", "invoice_date", "created_at"))
        line_items = _line_items(invoice)

        erp_metadata = {
            "sage_accounting_purchase_invoice_id": invoice_id or envelope.source_id,
            "sage_accounting_business_id": envelope.channel_metadata.get("sage_accounting_business_id"),
            "sage_accounting_contact_id": vendor_id,
            "sage_accounting_invoice_date": invoice_date,
            "sage_accounting_status": _first_present(invoice, "status", "payment_status"),
            "sage_accounting_event_id": envelope.event_id,
        }
        erp_metadata = {k: v for k, v in erp_metadata.items() if v not in (None, "")}

        from solden.services.extraction_provenance import (
            METHOD_API_PASSTHROUGH,
            SOURCE_ERP_NATIVE_SAGE_ACCOUNTING,
            build_passthrough_evidence,
            build_passthrough_provenance,
        )

        provenance = build_passthrough_provenance(
            source=SOURCE_ERP_NATIVE_SAGE_ACCOUNTING,
            source_ref=invoice_id or envelope.source_id,
            method=METHOD_API_PASSTHROUGH,
            fields={
                "vendor_name": vendor_name,
                "amount": amount,
                "currency": currency,
                "invoice_number": invoice_number,
                "due_date": due_date,
                "invoice_date": invoice_date,
            },
            confidences={
                "vendor_name": 1.0, "amount": 1.0, "currency": 1.0,
                "invoice_number": 1.0, "due_date": 1.0, "invoice_date": 1.0,
            },
        )
        return InvoiceData(
            source_type="sage_accounting",
            source_id=invoice_id or envelope.source_id,
            erp_native=True,
            erp_metadata=erp_metadata,
            subject=f"Sage Accounting purchase invoice {invoice_number} - {vendor_name}",
            sender=contact_email or f"{vendor_name} <sage-accounting@erp-native>",
            vendor_name=vendor_name,
            amount=amount,
            currency=currency,
            invoice_number=invoice_number,
            due_date=due_date,
            confidence=1.0,
            line_items=line_items or None,
            organization_id=organization_id,
            correlation_id=f"erp-intake:sage-accounting:{envelope.event_id or envelope.source_id}",
            field_confidences={
                "vendor_name": 1.0, "amount": 1.0, "currency": 1.0,
                "invoice_number": 1.0, "due_date": 1.0, "invoice_date": 1.0,
            },
            field_provenance=provenance,
            field_evidence=build_passthrough_evidence(
                field_provenance=provenance,
                source_label="Sage Accounting",
            ),
        )


def _json_dict(raw: bytes) -> Dict[str, Any]:
    try:
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
    except (ValueError, UnicodeDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _payload_body(payload: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("purchase_invoice", "purchaseInvoice", "invoice", "data", "resource"):
        value = payload.get(key)
        if isinstance(value, dict):
            merged = dict(payload)
            merged.update(value)
            return merged
    return payload


def _first_present(source: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = source.get(key)
        if value not in (None, ""):
            return value
    return None


def _normalize_event_type(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not raw:
        return ""
    compact = raw.replace("_", "")
    return _EVENT_TYPE_MAP.get(raw) or _EVENT_TYPE_MAP.get(compact) or ""


def _is_purchase_invoice_resource(resource_type: str) -> bool:
    normalized = resource_type.strip().lower().replace("-", "_").replace(" ", "_")
    return normalized in {
        "purchase_invoice",
        "purchase_invoices",
        "purchaseinvoice",
        "purchaseinvoices",
        "supplier_invoice",
        "vendor_bill",
    }


def _looks_like_invoice_payload(payload: Dict[str, Any]) -> bool:
    return any(
        _first_present(payload, *keys) is not None
        for keys in (
            ("id", "resource_id"),
            ("reference", "invoice_number"),
            ("total_amount", "gross_amount", "total", "amount"),
        )
    )


def _safe_float(value: Any, *, default: Optional[float] = None) -> Optional[float]:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _currency(value: Any) -> str:
    if isinstance(value, dict):
        raw = value.get("iso_code") or value.get("code") or value.get("id") or value.get("displayed_as")
    else:
        raw = value
    text = str(raw or "USD").strip().upper()
    return text[:3] if len(text) >= 3 else "USD"


def _date_string(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    raw = str(value).strip()
    return raw[:10] if len(raw) >= 10 else raw


def _line_items(invoice: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = invoice.get("invoice_lines") or invoice.get("lines") or invoice.get("line_items") or []
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append({
            "description": str(row.get("description") or row.get("displayed_as") or "").strip(),
            "quantity": _safe_float(row.get("quantity")),
            "unit_price": _safe_float(row.get("unit_price") or row.get("unit_amount")),
            "amount": _safe_float(row.get("total_amount") or row.get("net_amount") or row.get("amount")),
            "gl_code": row.get("ledger_account_id") or row.get("ledger_account") or row.get("account_id"),
            "tax_amount": _safe_float(row.get("tax_amount") or row.get("total_tax")),
        })
    return out


_SAGE_ACCOUNTING_ADAPTER = SageAccountingIntakeAdapter()
register_adapter(_SAGE_ACCOUNTING_ADAPTER)
