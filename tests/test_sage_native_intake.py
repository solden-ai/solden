"""Sage ERP-native intake coverage.

These tests lock Sage Intacct + Sage Accounting into the same runtime
contract as the other ERP-native sources: signed webhook -> registered
adapter -> canonical InvoiceData with field provenance.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from solden.api import erp_webhooks  # noqa: E402
from solden.core.erp_webhook_verify import sign_timestamped  # noqa: E402
from solden.integrations.erp_sage_accounting_intake_adapter import (  # noqa: E402
    SageAccountingIntakeAdapter,
)
from solden.integrations.erp_sage_intacct_intake_adapter import (  # noqa: E402
    SageIntacctIntakeAdapter,
)
from solden.services.intake_adapter import list_registered_sources  # noqa: E402


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(erp_webhooks.router)
    return TestClient(app)


def _signed_headers(raw: bytes, secret: str, *, prefix: str) -> dict:
    ts = int(time.time())
    return {
        f"X-{prefix}-Timestamp": str(ts),
        f"X-{prefix}-Signature": sign_timestamped(raw, secret, ts),
        "Content-Type": "application/json",
    }


def test_sage_adapters_are_registered():
    sources = set(list_registered_sources())
    assert "sage_intacct" in sources
    assert "sage_accounting" in sources


@pytest.mark.asyncio
async def test_sage_intacct_adapter_maps_full_apbill_payload_to_invoice_data():
    adapter = SageIntacctIntakeAdapter()
    raw = json.dumps({
        "event_type": "created",
        "record_no": "9001",
        "APBILL": {
            "RECORDNO": "9001",
            "RECORDID": "INV-SAGE-1",
            "DOCNUMBER": "PO-44",
            "VENDORID": "V001",
            "VENDORNAME": "Acme Supplies",
            "TOTALENTERED": "1234.56",
            "CURRENCY": "USD",
            "WHENDUE": "2026-07-01",
            "WHENCREATED": "2026-06-12",
        },
    }).encode("utf-8")
    env = await adapter.parse_envelope(raw, {}, "org-1")
    invoice = await adapter.enrich("org-1", env)

    assert env.event_type == "create"
    assert invoice.source_type == "sage_intacct"
    assert invoice.source_id == "9001"
    assert invoice.erp_native is True
    assert invoice.vendor_name == "Acme Supplies"
    assert invoice.erp_metadata["sage_intacct_vendor_id"] == "V001"
    assert invoice.invoice_number == "INV-SAGE-1"
    assert invoice.amount == 1234.56
    assert invoice.currency == "USD"
    assert invoice.field_provenance["amount"]["source"] == "erp_native_sage_intacct"
    assert invoice.field_evidence["invoice_number"]["source_label"] == "Sage Intacct"


@pytest.mark.asyncio
async def test_sage_accounting_adapter_filters_non_purchase_invoice_event():
    adapter = SageAccountingIntakeAdapter()
    raw = json.dumps({
        "event_type": "created",
        "resource_type": "sales_invoice",
        "resource_id": "sales-1",
    }).encode("utf-8")
    env = await adapter.parse_envelope(raw, {}, "org-1")
    assert env.event_type == ""


@pytest.mark.asyncio
async def test_sage_accounting_adapter_maps_purchase_invoice_to_invoice_data():
    adapter = SageAccountingIntakeAdapter()
    raw = json.dumps({
        "event_type": "created",
        "resource_type": "purchase_invoice",
        "purchase_invoice": {
            "id": "pi-123",
            "reference": "PI-2026-01",
            "total_amount": "88.10",
            "currency": {"iso_code": "GBP"},
            "due_date": "2026-07-05",
            "date": "2026-06-12",
            "contact": {
                "id": "contact-1",
                "name": "Northwind Traders",
                "email": "ap@northwind.example",
            },
            "invoice_lines": [
                {
                    "description": "Cloud subscription",
                    "quantity": 1,
                    "unit_price": "88.10",
                    "ledger_account_id": "6000",
                },
            ],
        },
    }).encode("utf-8")
    env = await adapter.parse_envelope(raw, {}, "org-1")
    invoice = await adapter.enrich("org-1", env)

    assert env.event_type == "create"
    assert invoice.source_type == "sage_accounting"
    assert invoice.source_id == "pi-123"
    assert invoice.erp_native is True
    assert invoice.vendor_name == "Northwind Traders"
    assert invoice.erp_metadata["sage_accounting_contact_id"] == "contact-1"
    assert invoice.invoice_number == "PI-2026-01"
    assert invoice.amount == 88.10
    assert invoice.currency == "GBP"
    assert invoice.line_items[0]["gl_code"] == "6000"
    assert invoice.field_provenance["vendor_name"]["source"] == "erp_native_sage_accounting"
    assert invoice.field_evidence["amount"]["source_label"] == "Sage Accounting"


def test_sage_intacct_webhook_accepts_signed_event_and_dispatches():
    client = _client()
    secret = "sage-secret"
    raw = json.dumps({"event_type": "created", "record_no": "9001"}).encode("utf-8")
    handle = AsyncMock(return_value={"ok": True, "source_type": "sage_intacct"})

    with patch.object(erp_webhooks, "_resolve_webhook_secret", return_value=secret), \
         patch.object(erp_webhooks, "_record_webhook_event"), \
         patch("solden.services.intake_adapter.handle_intake_event", new=handle):
        resp = client.post(
            "/erp/webhooks/sage-intacct/org-1",
            content=raw,
            headers=_signed_headers(raw, secret, prefix="Sage-Intacct"),
        )

    assert resp.status_code == 200, resp.text
    handle.assert_awaited_once()
    assert handle.call_args.kwargs["source_type"] == "sage_intacct"
    assert handle.call_args.kwargs["organization_id"] == "org-1"


def test_sage_accounting_webhook_rejects_bad_signature_before_dispatch():
    client = _client()
    raw = json.dumps({
        "event_type": "created",
        "resource_type": "purchase_invoice",
        "resource_id": "pi-123",
    }).encode("utf-8")
    handle = AsyncMock(return_value={"ok": True})

    headers = _signed_headers(raw, "wrong-secret", prefix="Sage-Accounting")
    with patch.object(erp_webhooks, "_resolve_webhook_secret", return_value="real-secret"), \
         patch.object(erp_webhooks, "_record_webhook_event"), \
         patch("solden.services.intake_adapter.handle_intake_event", new=handle):
        resp = client.post(
            "/erp/webhooks/sage-accounting/org-1",
            content=raw,
            headers=headers,
        )

    assert resp.status_code == 401
    handle.assert_not_awaited()


def test_sage_accounting_webhook_accepts_signed_event_and_dispatches():
    client = _client()
    secret = "sage-secret"
    raw = json.dumps({
        "event_type": "created",
        "resource_type": "purchase_invoice",
        "resource_id": "pi-123",
    }).encode("utf-8")
    handle = AsyncMock(return_value={"ok": True, "source_type": "sage_accounting"})

    with patch.object(erp_webhooks, "_resolve_webhook_secret", return_value=secret), \
         patch.object(erp_webhooks, "_record_webhook_event"), \
         patch("solden.services.intake_adapter.handle_intake_event", new=handle):
        resp = client.post(
            "/erp/webhooks/sage-accounting/org-1",
            content=raw,
            headers=_signed_headers(raw, secret, prefix="Sage-Accounting"),
        )

    assert resp.status_code == 200, resp.text
    handle.assert_awaited_once()
    assert handle.call_args.kwargs["source_type"] == "sage_accounting"
