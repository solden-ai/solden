"""Sage Business Cloud Accounting integration.

Sage Accounting is an OAuth2 REST connector. The adapter covers AP
purchase-invoice posting, vendor lookup/create, chart-of-accounts sync,
vendor sync, payment status reads, and token refresh.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from solden.core.http_client import get_http_client
from solden.core.money import money_to_float
from solden.integrations.erp_context_links import build_solden_ap_record_url

logger = logging.getLogger(__name__)

_ERP_TIMEOUT = 30
_DEFAULT_BASE_URL = "https://api.accounting.sage.com/v3.1"
_SAGE_TOKEN_URL = os.getenv("SAGE_ACCOUNTING_TOKEN_URL", "https://oauth.accounting.sage.com/token")


def _first_attr(connection: Any, *names: str) -> Optional[str]:
    for name in names:
        value = getattr(connection, name, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _base_url(connection: Any) -> str:
    return (_first_attr(connection, "base_url") or _DEFAULT_BASE_URL).rstrip("/")


def _business_id(connection: Any) -> Optional[str]:
    return _first_attr(connection, "business_id", "tenant_id")


def _headers(connection: Any, idempotency_key: Optional[str] = None) -> Dict[str, str]:
    headers = {
        "Authorization": f"Bearer {_first_attr(connection, 'access_token') or ''}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    business_id = _business_id(connection)
    if business_id:
        headers["X-Business"] = business_id
    if idempotency_key:
        headers["X-Idempotency-Key"] = str(idempotency_key)[:128]
    return headers


def _json_or_empty(response: Any) -> Dict[str, Any]:
    try:
        return response.json() or {}
    except Exception:
        return {}


def _extract_error_detail(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return "sage_accounting_request_failed"
    for key in ("message", "error", "error_description", "detail"):
        value = payload.get(key)
        if value:
            return str(value)[:500]
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict):
            return str(first.get("message") or first.get("detail") or first)[:500]
        return str(first)[:500]
    return "sage_accounting_request_failed"


def _date(value: Optional[str]) -> str:
    raw = str(value or "").strip()
    if not raw:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return raw[:10]


def _append_note(existing: Optional[str], solden_url: Optional[str], custom_fields: Optional[Dict[str, str]] = None) -> str:
    parts = [str(existing or "").strip()]
    if solden_url:
        parts.append(f"Solden: {solden_url}")
    if custom_fields:
        markers = [
            f"{key}={value}"
            for key, value in custom_fields.items()
            if key and value is not None
        ]
        if markers:
            parts.append("solden_fields:" + ";".join(markers))
    return " | ".join(part for part in parts if part)[:1000]


def _as_list(payload: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    value = payload.get(key)
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    nested = payload.get("$items")
    if isinstance(nested, list):
        return [item for item in nested if isinstance(item, dict)]
    if isinstance(value, dict):
        items = value.get("$items") or value.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _purchase_invoice_from_body(payload: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("purchase_invoice", "purchaseInvoice", "invoice"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload if isinstance(payload, dict) else {}


def _normalize_invoice(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "bill_id": row.get("id"),
        "doc_number": row.get("reference") or row.get("invoice_number") or row.get("displayed_as"),
        "amount": row.get("total_amount") or row.get("total") or row.get("gross_amount"),
        "status": row.get("status") or row.get("payment_status"),
        "raw": row,
    }


async def refresh_sage_accounting_token(connection: Any) -> Optional[str]:
    """Refresh Sage Accounting OAuth tokens."""
    refresh_token = _first_attr(connection, "refresh_token")
    client_id = _first_attr(connection, "client_id") or os.getenv("SAGE_ACCOUNTING_CLIENT_ID", "")
    client_secret = _first_attr(connection, "client_secret") or os.getenv("SAGE_ACCOUNTING_CLIENT_SECRET", "")
    if not refresh_token or not client_id or not client_secret:
        return None

    try:
        client = get_http_client()
        response = await client.post(
            _SAGE_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            auth=(client_id, client_secret),
            headers={"Accept": "application/json"},
            timeout=_ERP_TIMEOUT,
        )
        if response.status_code >= 400:
            logger.warning("Sage Accounting token refresh failed: http_%s", response.status_code)
            return None
        tokens = _json_or_empty(response)
        connection.access_token = tokens.get("access_token") or connection.access_token
        connection.refresh_token = tokens.get("refresh_token") or connection.refresh_token
        return connection.access_token
    except Exception as exc:
        logger.warning("Sage Accounting token refresh raised %s", type(exc).__name__)
        return None


async def post_to_sage_accounting(connection: Any, entry: Dict[str, Any]) -> Dict[str, Any]:
    """Journal-entry writes are not enabled for Sage Accounting yet."""
    return {
        "status": "skipped",
        "erp": "sage_accounting",
        "reason": "journal_entry_write_not_enabled_for_sage_accounting",
    }


async def find_bill_sage_accounting(connection: Any, invoice_number: str) -> Optional[Dict[str, Any]]:
    if not _first_attr(connection, "access_token"):
        return None
    needle = str(invoice_number or "").strip()
    if not needle:
        return None
    client = get_http_client()
    response = await client.get(
        f"{_base_url(connection)}/purchase_invoices",
        params={"search": needle},
        headers=_headers(connection),
        timeout=_ERP_TIMEOUT,
    )
    if response.status_code == 401:
        return None
    if response.status_code >= 400:
        return None
    payload = _json_or_empty(response)
    for row in _as_list(payload, "purchase_invoices"):
        ref = str(row.get("reference") or row.get("invoice_number") or "").strip()
        if ref == needle:
            return _normalize_invoice(row)
    return None


def _line_amount(item: Dict[str, Any], fallback: float) -> float:
    if item.get("unit_amount") is not None:
        return money_to_float(item.get("unit_amount"))
    if item.get("amount") is not None:
        quantity = money_to_float(item.get("quantity", 1) or 1)
        amount = money_to_float(item.get("amount"))
        return money_to_float(amount / quantity) if quantity else amount
    return money_to_float(fallback)


async def post_bill_to_sage_accounting(
    connection: Any,
    bill: Any,
    gl_map: Optional[Dict[str, str]] = None,
    field_mappings: Optional[Dict[str, str]] = None,
    custom_fields: Optional[Dict[str, str]] = None,
    idempotency_key: Optional[str] = None,
    organization_id: Optional[str] = None,
    ap_item_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Post a Sage Accounting purchase invoice."""
    from solden.integrations.erp_router import get_account_code

    if not _first_attr(connection, "access_token"):
        return {"status": "error", "erp": "sage_accounting", "reason": "sage_accounting_not_configured"}
    missing_fields: List[str] = []
    if not getattr(bill, "vendor_id", None):
        missing_fields.append("vendor_id")
    try:
        amount = float(getattr(bill, "amount", 0) or 0)
    except (TypeError, ValueError):
        amount = 0.0
    if amount <= 0:
        missing_fields.append("amount")
    if missing_fields:
        return {
            "status": "error",
            "erp": "sage_accounting",
            "reason": "sage_accounting_validation_failed",
            "missing_fields": missing_fields,
        }

    solden_record_url = build_solden_ap_record_url(ap_item_id)
    if idempotency_key and getattr(bill, "invoice_number", None):
        try:
            existing_bill = await find_bill_sage_accounting(
                connection, str(bill.invoice_number),
            )
        except Exception as exc:
            logger.debug(
                "[sage_accounting] find_bill pre-check failed vendor=%s invoice=%s: %s",
                getattr(bill, "vendor_name", None),
                bill.invoice_number,
                exc,
            )
            existing_bill = None
        if existing_bill and existing_bill.get("bill_id"):
            result = {
                "status": "already_posted",
                "erp": "sage_accounting",
                "bill_id": existing_bill.get("bill_id"),
                "doc_number": existing_bill.get("doc_number"),
                "amount": existing_bill.get("amount"),
                "idempotency_key": idempotency_key,
            }
            if solden_record_url:
                result["solden_record_url"] = solden_record_url
            return result

    expense_account = get_account_code("sage_accounting", "expenses", gl_map)
    invoice: Dict[str, Any] = {
        "contact_id": getattr(bill, "vendor_id", None),
        "date": _date(getattr(bill, "invoice_date", None)),
        "due_date": _date(getattr(bill, "due_date", None)) if getattr(bill, "due_date", None) else None,
        "reference": getattr(bill, "invoice_number", None),
        "vendor_reference": getattr(bill, "po_number", None),
        "notes": _append_note(getattr(bill, "description", None), solden_record_url, custom_fields),
        "invoice_lines": [],
    }
    bill_currency = str(getattr(bill, "currency", "") or "").strip().upper()
    currency_id = (gl_map or {}).get(f"currency_id_{bill_currency}") if bill_currency else None
    if currency_id:
        invoice["currency_id"] = str(currency_id)

    line_items = getattr(bill, "line_items", None) or [
        {
            "description": getattr(bill, "description", None)
            or f"Invoice {getattr(bill, 'invoice_number', '')}",
            "amount": getattr(bill, "amount", 0),
        }
    ]
    bill_vat_code = str(getattr(bill, "vat_code", "") or "").upper()
    for item in line_items:
        quantity = money_to_float(item.get("quantity", 1) or 1)
        line = {
            "description": item.get("description") or getattr(bill, "description", None) or "",
            "ledger_account_id": (
                item.get("ledger_account_id")
                or item.get("account_id")
                or item.get("account_code")
                or item.get("gl_code")
                or expense_account
            ),
            "quantity": quantity,
            "unit_price": _line_amount(item, getattr(bill, "amount", 0)),
        }
        line_vat_code = str(item.get("vat_code") or bill_vat_code or "").upper()
        tax_rate_id = item.get("tax_rate_id") or (gl_map or {}).get(f"tax_code_{line_vat_code}")
        if tax_rate_id:
            line["tax_rate_id"] = str(tax_rate_id)
        for key in ("department_id", "project_id", "cost_centre_id", "cost_center_id"):
            if item.get(key):
                line[key] = str(item[key])
        invoice["invoice_lines"].append(line)

    if getattr(bill, "discount_amount", None) and bill.discount_amount > 0:
        invoice["invoice_lines"].append({
            "description": f"Discount ({getattr(bill, 'discount_terms', '') or 'early payment'})",
            "ledger_account_id": expense_account,
            "quantity": 1,
            "unit_price": money_to_float(-bill.discount_amount),
        })

    invoice = {key: value for key, value in invoice.items() if value is not None}
    client = get_http_client()
    response = await client.post(
        f"{_base_url(connection)}/purchase_invoices",
        json={"purchase_invoice": invoice},
        headers=_headers(connection, idempotency_key),
        timeout=_ERP_TIMEOUT,
    )
    if response.status_code == 401:
        return {
            "status": "error",
            "erp": "sage_accounting",
            "reason": "Token expired",
            "needs_reauth": True,
        }
    if response.status_code >= 400:
        payload = _json_or_empty(response)
        return {
            "status": "error",
            "erp": "sage_accounting",
            "reason": f"http_{response.status_code}",
            "erp_error_detail": _extract_error_detail(payload),
            "needs_reauth": response.status_code == 401,
        }

    row = _purchase_invoice_from_body(_json_or_empty(response))
    bill_id = row.get("id")
    result_payload: Dict[str, Any] = {
        "status": "success",
        "erp": "sage_accounting",
        "bill_id": bill_id,
        "doc_number": row.get("reference") or getattr(bill, "invoice_number", None),
        "erp_journal_entry_id": str(bill_id) if bill_id is not None else None,
    }
    if solden_record_url:
        result_payload["solden_record_url"] = solden_record_url
    return result_payload


async def find_vendor_sage_accounting(
    connection: Any,
    name: Optional[str] = None,
    email: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if not _first_attr(connection, "access_token"):
        return None
    search = str(name or email or "").strip()
    if not search:
        return None
    client = get_http_client()
    response = await client.get(
        f"{_base_url(connection)}/contacts",
        params={"search": search},
        headers=_headers(connection),
        timeout=_ERP_TIMEOUT,
    )
    if response.status_code >= 400:
        return None
    target = search.lower()
    for row in _as_list(_json_or_empty(response), "contacts"):
        row_name = str(row.get("name") or "").strip()
        row_email = str(row.get("email") or row.get("main_contact_person", {}).get("email") or "").strip()
        if row_name.lower() == target or (email and row_email.lower() == target):
            return {
                "vendor_id": row.get("id"),
                "name": row_name,
                "email": row_email or None,
                "active": not bool(row.get("archived")),
            }
    return None


def _contact_reference(name: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "-", str(name or "").upper()).strip("-")
    return (token or "SOLDEN-VENDOR")[:30]


async def create_vendor_sage_accounting(connection: Any, vendor: Any) -> Dict[str, Any]:
    if not _first_attr(connection, "access_token"):
        return {"status": "error", "erp": "sage_accounting", "reason": "sage_accounting_not_configured"}
    name = str(getattr(vendor, "name", "") or "").strip()
    if not name:
        return {"status": "error", "erp": "sage_accounting", "reason": "missing_vendor_name"}
    contact: Dict[str, Any] = {
        "name": name,
        "reference": _contact_reference(name),
    }
    email = str(getattr(vendor, "email", "") or "").strip()
    if email:
        contact["main_contact_person"] = {"email": email}
    tax_id = str(getattr(vendor, "tax_id", "") or "").strip()
    if tax_id:
        contact["tax_number"] = tax_id
    client = get_http_client()
    response = await client.post(
        f"{_base_url(connection)}/contacts",
        json={"contact": contact},
        headers=_headers(connection),
        timeout=_ERP_TIMEOUT,
    )
    if response.status_code == 401:
        return {"status": "error", "erp": "sage_accounting", "reason": "Token expired", "needs_reauth": True}
    if response.status_code >= 400:
        return {
            "status": "error",
            "erp": "sage_accounting",
            "reason": f"http_{response.status_code}",
            "erp_error_detail": _extract_error_detail(_json_or_empty(response)),
        }
    body = _json_or_empty(response)
    row = body.get("contact") if isinstance(body.get("contact"), dict) else body
    return {
        "status": "success",
        "erp": "sage_accounting",
        "vendor_id": row.get("id"),
        "name": row.get("name") or name,
    }


async def get_chart_of_accounts_sage_accounting(connection: Any) -> List[Dict[str, Any]]:
    if not _first_attr(connection, "access_token"):
        return []
    client = get_http_client()
    response = await client.get(
        f"{_base_url(connection)}/ledger_accounts",
        headers=_headers(connection),
        timeout=_ERP_TIMEOUT,
    )
    if response.status_code >= 400:
        return []
    accounts: List[Dict[str, Any]] = []
    for row in _as_list(_json_or_empty(response), "ledger_accounts"):
        accounts.append({
            "id": row.get("id"),
            "code": row.get("nominal_code") or row.get("displayed_as") or row.get("id"),
            "name": row.get("name") or row.get("displayed_as"),
            "type": row.get("ledger_account_type", {}).get("displayed_as") if isinstance(row.get("ledger_account_type"), dict) else row.get("type"),
            "active": not bool(row.get("archived")),
            "raw": row,
        })
    return accounts


async def list_all_vendors_sage_accounting(connection: Any) -> List[Dict[str, Any]]:
    if not _first_attr(connection, "access_token"):
        return []
    client = get_http_client()
    response = await client.get(
        f"{_base_url(connection)}/contacts",
        headers=_headers(connection),
        timeout=_ERP_TIMEOUT,
    )
    if response.status_code >= 400:
        return []
    vendors: List[Dict[str, Any]] = []
    for row in _as_list(_json_or_empty(response), "contacts"):
        vendors.append({
            "vendor_id": row.get("id"),
            "name": row.get("name"),
            "email": row.get("email") or (row.get("main_contact_person") or {}).get("email"),
            "active": not bool(row.get("archived")),
            "erp_type": "sage_accounting",
        })
    return vendors


async def get_payment_status_sage_accounting(connection: Any, erp_reference: str) -> Dict[str, Any]:
    if not _first_attr(connection, "access_token"):
        return {"paid": False, "reason": "sage_accounting_not_configured"}
    ref = str(erp_reference or "").strip()
    if not ref:
        return {"paid": False, "reason": "invalid_bill_reference"}
    client = get_http_client()
    response = await client.get(
        f"{_base_url(connection)}/purchase_invoices/{ref}",
        headers=_headers(connection),
        timeout=_ERP_TIMEOUT,
    )
    if response.status_code == 401:
        return {"paid": False, "reason": "Token expired", "needs_reauth": True}
    if response.status_code == 404:
        return {"paid": False, "reason": "not_found"}
    if response.status_code >= 400:
        return {"paid": False, "reason": f"http_{response.status_code}"}
    row = _purchase_invoice_from_body(_json_or_empty(response))
    total = float(row.get("total_amount") or row.get("gross_amount") or row.get("total") or 0)
    paid_amount = float(row.get("paid_amount") or row.get("amount_paid") or 0)
    outstanding = row.get("outstanding_amount") or row.get("amount_due")
    if outstanding is None:
        outstanding = max(total - paid_amount, 0.0)
    outstanding = float(outstanding or 0)
    status = str(row.get("status") or row.get("payment_status") or "").lower()
    return {
        "paid": paid_amount > 0 and outstanding <= 0.01 or status in {"paid", "paid_in_full"},
        "partial": paid_amount > 0 and outstanding > 0.01,
        "payment_amount": paid_amount,
        "remaining_balance": outstanding,
        "status": status or None,
        "payment_reference": row.get("id") or ref,
    }


async def discover_sage_accounting_business_id(access_token: str, base_url: Optional[str] = None) -> Optional[str]:
    """Best-effort business discovery after OAuth.

    Sage tenants vary by region/account setup; failing to discover a
    business id should not fail OAuth. The REST requests can still rely
    on the token's default business when Sage allows it.
    """
    if not access_token:
        return None
    root = (base_url or _DEFAULT_BASE_URL).rstrip("/")
    try:
        client = get_http_client()
        response = await client.get(
            f"{root}/businesses",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            timeout=15,
        )
        if response.status_code >= 400:
            return None
        businesses = _as_list(_json_or_empty(response), "businesses")
        if businesses:
            return businesses[0].get("id")
    except Exception:
        return None
    return None
