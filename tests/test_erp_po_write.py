"""ERP PO write-back — dispatch, flag gating, QB/Xero reference adapters (mocked HTTP)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from solden.integrations import erp_po_write  # noqa: E402


class _FakeResp:
    def __init__(self, status_code, body, headers=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}

    def json(self):
        return self._body


class _FakeClient:
    def __init__(self, resp):
        self._resp = resp
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self._resp


def _conn(erp_type, **kw):
    defaults = {"access_token": "tok", "realm_id": None, "tenant_id": None, "base_url": None}
    defaults.update(kw)
    return SimpleNamespace(type=erp_type, **defaults)


def _po(**kw):
    base = {"po_id": "PO-erp-1", "po_number": "PO-erp-1", "vendor_name": "Acme",
            "vendor_id": "V1", "total_amount": 1000.0, "currency": "GBP",
            "line_items": [{"description": "Widget", "quantity": 2, "unit_price": 500.0}]}
    base.update(kw)
    return base


def test_disabled_when_flag_off(monkeypatch):
    monkeypatch.setattr(erp_po_write, "is_procurement_erp_write_enabled", lambda: False)
    out = asyncio.run(erp_po_write.create_purchase_order("org1", _po()))
    assert out["status"] == "disabled"


def test_idempotent_when_already_issued(monkeypatch):
    monkeypatch.setattr(erp_po_write, "is_procurement_erp_write_enabled", lambda: True)
    out = asyncio.run(erp_po_write.create_purchase_order("org1", _po(erp_po_id="EXISTING")))
    assert out["status"] == "already_issued" and out["erp_po_id"] == "EXISTING"


def test_quickbooks_adapter_builds_request_and_returns_id(monkeypatch):
    monkeypatch.setattr(erp_po_write, "is_procurement_erp_write_enabled", lambda: True)
    monkeypatch.setattr(
        "solden.integrations.erp_router.get_erp_connection",
        lambda org: _conn("quickbooks", realm_id="REALM9"),
    )
    fake = _FakeClient(_FakeResp(200, {"PurchaseOrder": {"Id": "QB-PO-77"}}))
    monkeypatch.setattr(erp_po_write, "get_http_client", lambda: fake)
    out = asyncio.run(erp_po_write.create_purchase_order("org1", _po(), idempotency_key="idem-1"))
    assert out["status"] == "success" and out["erp_po_id"] == "QB-PO-77"
    url, kwargs = fake.calls[0]
    assert "/v3/company/REALM9/purchaseorder" in url
    assert "requestid=idem-1" in url
    assert kwargs["headers"]["Authorization"] == "Bearer tok"
    assert kwargs["json"]["VendorRef"]["value"] == "V1"


def test_xero_adapter_builds_request_and_returns_id(monkeypatch):
    monkeypatch.setattr(erp_po_write, "is_procurement_erp_write_enabled", lambda: True)
    monkeypatch.setattr(
        "solden.integrations.erp_router.get_erp_connection",
        lambda org: _conn("xero", tenant_id="TEN1"),
    )
    fake = _FakeClient(_FakeResp(200, {"PurchaseOrders": [{"PurchaseOrderID": "XERO-PO-5"}]}))
    monkeypatch.setattr(erp_po_write, "get_http_client", lambda: fake)
    out = asyncio.run(erp_po_write.create_purchase_order("org1", _po(), idempotency_key="idem-2"))
    assert out["status"] == "success" and out["erp_po_id"] == "XERO-PO-5"
    url, kwargs = fake.calls[0]
    assert url == "https://api.xero.com/api.xro/2.0/PurchaseOrders"
    assert kwargs["headers"]["Xero-tenant-id"] == "TEN1"
    assert kwargs["headers"]["Idempotency-Key"] == "idem-2"
    assert kwargs["json"]["PurchaseOrders"][0]["Contact"]["Name"] == "Acme"


def test_netsuite_adapter_builds_request_and_returns_id(monkeypatch):
    monkeypatch.setattr(erp_po_write, "is_procurement_erp_write_enabled", lambda: True)
    monkeypatch.setattr(
        "solden.integrations.erp_router.get_erp_connection",
        lambda org: _conn("netsuite", account_id="ACC1"),
    )
    monkeypatch.setattr("solden.integrations.erp_netsuite._oauth_header", lambda c, m, u: "OAuth sig")
    fake = _FakeClient(_FakeResp(
        204, None,
        headers={"Location": "https://ACC1.suitetalk.api.netsuite.com/services/rest/record/v1/purchaseOrder/NS-PO-42"},
    ))
    monkeypatch.setattr(erp_po_write, "get_http_client", lambda: fake)
    out = asyncio.run(erp_po_write.create_purchase_order("org1", _po()))
    assert out["status"] == "success" and out["erp_po_id"] == "NS-PO-42"
    url, kwargs = fake.calls[0]
    assert "ACC1.suitetalk.api.netsuite.com" in url and url.endswith("/purchaseOrder")
    assert kwargs["headers"]["Authorization"] == "OAuth sig"
    assert kwargs["json"]["entity"]["id"] == "V1"


def test_sap_adapter_builds_request_and_returns_id(monkeypatch):
    monkeypatch.setattr(erp_po_write, "is_procurement_erp_write_enabled", lambda: True)
    monkeypatch.setattr(
        "solden.integrations.erp_router.get_erp_connection",
        lambda org: _conn("sap", base_url="https://sap.example"),
    )

    async def _auth(conn):
        return {"Authorization": "Bearer tok"}

    async def _csrf(base, path, auth):
        return "csrf123"

    monkeypatch.setattr("solden.integrations.erp_sap_s4hana._build_auth_headers", _auth)
    monkeypatch.setattr("solden.integrations.erp_sap_s4hana._fetch_csrf_token", _csrf)
    fake = _FakeClient(_FakeResp(201, {"d": {"PurchaseOrder": "SAP-PO-1"}}))
    monkeypatch.setattr(erp_po_write, "get_http_client", lambda: fake)
    out = asyncio.run(erp_po_write.create_purchase_order("org1", _po()))
    assert out["status"] == "success" and out["erp_po_id"] == "SAP-PO-1"
    url, kwargs = fake.calls[0]
    assert url.endswith("/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder")
    assert kwargs["headers"]["X-CSRF-Token"] == "csrf123"
    assert kwargs["json"]["Supplier"] == "V1"


def test_no_connection(monkeypatch):
    monkeypatch.setattr(erp_po_write, "is_procurement_erp_write_enabled", lambda: True)
    monkeypatch.setattr("solden.integrations.erp_router.get_erp_connection", lambda org: None)
    out = asyncio.run(erp_po_write.create_purchase_order("org1", _po()))
    assert out["status"] == "error" and out["reason"] == "no_erp_connection"


def test_quickbooks_401_needs_reauth(monkeypatch):
    monkeypatch.setattr(erp_po_write, "is_procurement_erp_write_enabled", lambda: True)
    monkeypatch.setattr(
        "solden.integrations.erp_router.get_erp_connection",
        lambda org: _conn("quickbooks", realm_id="R"),
    )
    monkeypatch.setattr(erp_po_write, "get_http_client", lambda: _FakeClient(_FakeResp(401, {})))
    out = asyncio.run(erp_po_write.create_purchase_order("org1", _po()))
    assert out.get("needs_reauth") is True
