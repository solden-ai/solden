"""Sage Intacct implementation of the IntakeAdapter protocol.

Sage Intacct does not give Solden one universal webhook payload shape.
Customers can emit Smart Event / Platform Services HTTP calls with
either RECORDNO or RECORDID. This adapter accepts the signed event,
fetches the authoritative APBILL from XML Web Services when possible,
and hands the result to the same invoice workflow used by email,
PEPPOL, NetSuite, SAP, QuickBooks, and Xero.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Mapping, Optional

from solden.core.ap_states import APState
from solden.core.database import get_db
from solden.core.erp_webhook_verify import verify_sage_intacct_signature
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
    "add": "create",
    "added": "create",
    "post": "posted",
    "posted": "posted",
    "submit": "posted",
    "submitted": "posted",
    "update": "update",
    "updated": "update",
    "edit": "update",
    "edited": "update",
    "change": "update",
    "changed": "update",
    "block": "blocked",
    "blocked": "blocked",
    "hold": "blocked",
    "held": "blocked",
    "release": "released",
    "released": "released",
    "unblock": "released",
    "unblocked": "released",
    "paid": "paid",
    "payment": "paid",
    "fullypaid": "paid",
    "fully_paid": "paid",
    "void": "cancelled",
    "voided": "cancelled",
    "cancel": "cancelled",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "delete": "delete",
    "deleted": "delete",
}


class SageIntacctIntakeAdapter:
    """Sage Intacct APBILL webhook intake."""

    source_type = "sage_intacct"

    async def verify_signature(
        self, raw: bytes, headers: Mapping[str, str], secret: str,
    ) -> bool:
        signature = (
            headers.get("x-sage-intacct-signature")
            or headers.get("X-Sage-Intacct-Signature")
            or headers.get("x-sage-signature")
            or headers.get("X-Sage-Signature")
        )
        timestamp = (
            headers.get("x-sage-intacct-timestamp")
            or headers.get("X-Sage-Intacct-Timestamp")
            or headers.get("x-sage-timestamp")
            or headers.get("X-Sage-Timestamp")
        )
        return verify_sage_intacct_signature(raw, signature, timestamp, secret)

    async def parse_envelope(
        self, raw: bytes, headers: Mapping[str, str], organization_id: str,
    ) -> IntakeEnvelope:
        payload = _json_dict(raw)
        body = _payload_body(payload)
        record_no = _first_present(
            body, "record_no", "recordNo", "RECORDNO", "bill_id", "billId", "id",
        )
        record_id = _first_present(
            body, "record_id", "recordId", "RECORDID", "invoice_number",
            "invoiceNumber", "doc_number", "docNumber", "DOCNUMBER",
        )
        source_id = record_no or record_id
        raw_event = _first_present(
            body, "event_type", "eventType", "operation", "action", "status", "state",
        )
        event_type = _normalize_event_type(raw_event)
        return IntakeEnvelope(
            source_type=self.source_type,
            event_type=event_type,
            source_id=str(source_id or "").strip(),
            organization_id=organization_id,
            raw_payload=payload,
            event_id=str(_first_present(body, "event_id", "eventId", "idempotency_key") or "").strip() or None,
            received_at=str(_first_present(body, "event_time", "eventTime", "timestamp", "created_at") or "").strip() or None,
            channel_metadata={
                "sage_intacct_record_no": str(record_no or "").strip(),
                "sage_intacct_record_id": str(record_id or "").strip(),
                "sage_intacct_company_id": str(_first_present(body, "company_id", "companyId") or "").strip(),
                "sage_intacct_operation": str(raw_event or "").strip(),
            },
        )

    async def enrich(
        self, organization_id: str, envelope: IntakeEnvelope,
    ) -> InvoiceData:
        connection = self._resolve_connection(organization_id)
        payload_bill = _payload_body(envelope.raw_payload)
        if connection is not None:
            bill = await self._fetch_bill(connection, envelope.source_id)
            if bill:
                return self._build_invoice_from_bill(envelope, bill, organization_id)
        if _looks_like_bill_payload(payload_bill):
            return self._build_invoice_from_bill(envelope, payload_bill, organization_id)
        return self._thin_invoice_from_envelope(envelope, organization_id)

    async def derive_state_update(
        self, organization_id: str, envelope: IntakeEnvelope,
    ) -> StateUpdate:
        if envelope.event_type in {"paid", "cancelled", "delete"}:
            return StateUpdate(target_state=APState.CLOSED.value)
        if envelope.event_type == "blocked":
            return StateUpdate(
                target_state=APState.NEEDS_APPROVAL.value,
                field_updates={"exception_type": "erp_native_blocked"},
            )
        if envelope.event_type in {"update", "released"}:
            return StateUpdate(target_state=None, idempotent_no_op_allowed=True)
        return StateUpdate(target_state=None)

    @staticmethod
    def _resolve_connection(organization_id: str):
        db = get_db()
        if not hasattr(db, "get_erp_connections"):
            return None
        try:
            for row in db.get_erp_connections(organization_id):
                if str(row.get("erp_type") or "").lower() == "sage_intacct":
                    return _erp_connection_from_row(row)
        except Exception as exc:  # noqa: BLE001
            logger.warning("sage_intacct_intake_adapter: connection lookup failed - %s", exc)
        return None

    @staticmethod
    async def _fetch_bill(connection: Any, bill_reference: str) -> Optional[Dict[str, Any]]:
        ref = str(bill_reference or "").strip()
        if not ref:
            return None
        try:
            from solden.integrations import erp_sage_intacct as sage

            value = sage._safe_query_value(ref)
            if not value:
                return None
            outcome = await sage._post_function(
                connection,
                sage._read_by_query(
                    "APBILL",
                    (
                        "RECORDNO,RECORDID,DOCNUMBER,VENDORID,VENDORNAME,"
                        "TOTALENTERED,TOTALDUE,TOTALPAID,STATE,WHENCREATED,"
                        "WHENDUE,CURRENCY,DESCRIPTION"
                    ),
                    f"RECORDNO = '{value}' OR RECORDID = '{value}'",
                    pagesize=1,
                ),
            )
            if not outcome.get("ok"):
                return None
            record = (sage._record_nodes(outcome.get("result")) or [None])[0]
            if record is None:
                return None
            return sage._record_dict(record)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "sage_intacct_intake_adapter: APBILL fetch failed ref=%s - %s",
                ref, exc,
            )
            return None

    def _thin_invoice_from_envelope(
        self, envelope: IntakeEnvelope, organization_id: str,
    ) -> InvoiceData:
        from solden.services.extraction_provenance import (
            METHOD_API_PASSTHROUGH,
            SOURCE_ERP_NATIVE_SAGE_INTACCT,
            build_passthrough_evidence,
            build_passthrough_provenance,
        )

        provenance = build_passthrough_provenance(
            source=SOURCE_ERP_NATIVE_SAGE_INTACCT,
            source_ref=envelope.source_id,
            method=METHOD_API_PASSTHROUGH,
            fields={"invoice_number": envelope.source_id},
        )
        return InvoiceData(
            source_type="sage_intacct",
            source_id=envelope.source_id,
            erp_native=True,
            erp_metadata={
                "sage_intacct_bill_id": envelope.source_id,
                "sage_intacct_record_no": envelope.channel_metadata.get("sage_intacct_record_no"),
                "sage_intacct_record_id": envelope.channel_metadata.get("sage_intacct_record_id"),
                "fallback_thin_intake": True,
            },
            subject=f"Sage Intacct AP bill {envelope.source_id}",
            sender="<sage-intacct@erp-native>",
            vendor_name="Unknown vendor",
            amount=0.0,
            currency="USD",
            invoice_number=envelope.source_id,
            confidence=1.0,
            organization_id=organization_id,
            correlation_id=f"erp-intake:sage-intacct:{envelope.event_id or envelope.source_id}",
            field_provenance=provenance,
            field_evidence=build_passthrough_evidence(
                field_provenance=provenance,
                source_label="Sage Intacct (thin intake)",
            ),
        )

    @staticmethod
    def _build_invoice_from_bill(
        envelope: IntakeEnvelope,
        bill: Dict[str, Any],
        organization_id: str,
    ) -> InvoiceData:
        record_no = str(_first_present(bill, "RECORDNO", "record_no", "id") or envelope.source_id).strip()
        record_id = str(_first_present(bill, "RECORDID", "record_id", "invoice_number") or "").strip()
        doc_number = str(_first_present(bill, "DOCNUMBER", "doc_number") or "").strip()
        invoice_number = record_id or doc_number or record_no or envelope.source_id
        vendor_id = str(_first_present(bill, "VENDORID", "vendor_id") or "").strip()
        vendor_name = str(
            _first_present(bill, "VENDORNAME", "vendor_name", "vendorName")
            or vendor_id
            or "Unknown vendor"
        ).strip()
        amount = _safe_float(_first_present(bill, "TOTALENTERED", "TOTALDUE", "amount", "total"), default=0.0)
        currency = str(_first_present(bill, "CURRENCY", "currency") or "USD").upper()
        due_date = _date_string(_first_present(bill, "WHENDUE", "due_date"))
        invoice_date = _date_string(_first_present(bill, "WHENCREATED", "invoice_date", "date"))
        description = str(_first_present(bill, "DESCRIPTION", "description") or "").strip()

        erp_metadata = {
            "sage_intacct_bill_id": record_no or envelope.source_id,
            "sage_intacct_record_no": record_no,
            "sage_intacct_record_id": record_id,
            "sage_intacct_doc_number": doc_number,
            "sage_intacct_vendor_id": vendor_id,
            "sage_intacct_invoice_date": invoice_date,
            "sage_intacct_description": description,
            "sage_intacct_state": _first_present(bill, "STATE", "state"),
            "sage_intacct_event_id": envelope.event_id,
        }
        erp_metadata = {k: v for k, v in erp_metadata.items() if v not in (None, "")}

        from solden.services.extraction_provenance import (
            METHOD_API_PASSTHROUGH,
            SOURCE_ERP_NATIVE_SAGE_INTACCT,
            build_passthrough_evidence,
            build_passthrough_provenance,
        )

        provenance = build_passthrough_provenance(
            source=SOURCE_ERP_NATIVE_SAGE_INTACCT,
            source_ref=record_no or envelope.source_id,
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
            source_type="sage_intacct",
            source_id=record_no or envelope.source_id,
            erp_native=True,
            erp_metadata=erp_metadata,
            subject=f"Sage Intacct bill {invoice_number} - {vendor_name}",
            sender=f"{vendor_name} <sage-intacct@erp-native>",
            vendor_name=vendor_name,
            amount=amount,
            currency=currency,
            invoice_number=invoice_number,
            due_date=due_date,
            confidence=1.0,
            organization_id=organization_id,
            correlation_id=f"erp-intake:sage-intacct:{envelope.event_id or envelope.source_id}",
            field_confidences={
                "vendor_name": 1.0, "amount": 1.0, "currency": 1.0,
                "invoice_number": 1.0, "due_date": 1.0, "invoice_date": 1.0,
            },
            field_provenance=provenance,
            field_evidence=build_passthrough_evidence(
                field_provenance=provenance,
                source_label="Sage Intacct",
            ),
        )


def _json_dict(raw: bytes) -> Dict[str, Any]:
    try:
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
    except (ValueError, UnicodeDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _payload_body(payload: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("apbill", "APBILL", "bill", "data", "record", "object"):
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


def _looks_like_bill_payload(payload: Dict[str, Any]) -> bool:
    return any(
        _first_present(payload, *keys) is not None
        for keys in (
            ("RECORDNO", "record_no", "id"),
            ("RECORDID", "record_id", "invoice_number"),
            ("TOTALENTERED", "TOTALDUE", "amount", "total"),
        )
    )


def _safe_float(value: Any, *, default: Optional[float] = None) -> Optional[float]:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _date_string(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    if isinstance(value, dict):
        year = str(value.get("year") or "").zfill(4)
        month = str(value.get("month") or "").zfill(2)
        day = str(value.get("day") or "").zfill(2)
        if year.strip("0") and month.strip("0") and day.strip("0"):
            return f"{year}-{month}-{day}"
        return None
    raw = str(value).strip()
    return raw[:10] if len(raw) >= 10 else raw


_SAGE_INTACCT_ADAPTER = SageIntacctIntakeAdapter()
register_adapter(_SAGE_INTACCT_ADAPTER)
