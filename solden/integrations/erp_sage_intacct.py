"""Sage Intacct ERP integration.

This adapter uses Sage Intacct XML Web Services for AP bill posting,
vendor lookup/create, chart-of-accounts sync, and payment-status reads.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

from solden.core.money import money_to_float
from solden.integrations.erp_context_links import build_solden_ap_record_url

logger = logging.getLogger(__name__)

_ERP_TIMEOUT = 30
_DEFAULT_INTACCT_URL = "https://api.intacct.com/ia/xml/xmlgw.phtml"
_QUERY_VALUE_RE = re.compile(r"^[A-Za-z0-9 _.\-@:/#&(),]{1,160}$")
_FIELD_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def get_http_client():
    from solden.core.http_client import get_http_client as _get_http_client

    return _get_http_client()


def _first_attr(connection: Any, *names: str) -> Optional[str]:
    for name in names:
        value = getattr(connection, name, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _base_url(connection: Any) -> str:
    return (
        _first_attr(connection, "base_url")
        or _DEFAULT_INTACCT_URL
    ).rstrip("/")


def _credentials_complete(connection: Any) -> bool:
    return all(
        _first_attr(connection, name)
        for name in (
            "sender_id",
            "sender_password",
            "company_id",
            "user_id",
            "user_password",
        )
    )


def _date_parts(value: Optional[str]) -> Dict[str, str]:
    raw = str(value or "").strip()
    try:
        if raw:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        else:
            parsed = datetime.now(timezone.utc)
    except ValueError:
        parsed = datetime.now(timezone.utc)
    return {
        "year": str(parsed.year),
        "month": str(parsed.month),
        "day": str(parsed.day),
    }


def _date_element(parent: ET.Element, tag: str, value: Optional[str]) -> None:
    node = ET.SubElement(parent, tag)
    parts = _date_parts(value)
    ET.SubElement(node, "year").text = parts["year"]
    ET.SubElement(node, "month").text = parts["month"]
    ET.SubElement(node, "day").text = parts["day"]


def _safe_query_value(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text or not _QUERY_VALUE_RE.match(text):
        return None
    return text


def _safe_xml_field(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text or not _FIELD_NAME_RE.match(text):
        return None
    return text


def _append_text(parent: ET.Element, tag: str, value: Any) -> None:
    if value is None:
        return
    text = str(value).strip()
    if not text:
        return
    ET.SubElement(parent, tag).text = text


def _build_envelope(
    connection: Any,
    function_payload: ET.Element,
    *,
    control_id: Optional[str] = None,
) -> bytes:
    control_id = control_id or f"solden-{uuid.uuid4().hex}"
    request = ET.Element("request")

    control = ET.SubElement(request, "control")
    ET.SubElement(control, "senderid").text = _first_attr(connection, "sender_id") or ""
    ET.SubElement(control, "password").text = _first_attr(connection, "sender_password") or ""
    ET.SubElement(control, "controlid").text = control_id
    ET.SubElement(control, "uniqueid").text = "false"
    ET.SubElement(control, "dtdversion").text = "3.0"
    ET.SubElement(control, "includewhitespace").text = "false"

    operation = ET.SubElement(request, "operation")
    authentication = ET.SubElement(operation, "authentication")
    login = ET.SubElement(authentication, "login")
    ET.SubElement(login, "userid").text = _first_attr(connection, "user_id") or ""
    ET.SubElement(login, "companyid").text = _first_attr(connection, "company_id") or ""
    ET.SubElement(login, "password").text = _first_attr(connection, "user_password") or ""
    location_id = _first_attr(connection, "location_id")
    if location_id:
        ET.SubElement(login, "locationid").text = location_id

    content = ET.SubElement(operation, "content")
    function = ET.SubElement(content, "function", {"controlid": control_id})
    function.append(function_payload)

    return ET.tostring(request, encoding="utf-8", xml_declaration=True)


def _first_text(element: Optional[ET.Element], *paths: str) -> Optional[str]:
    if element is None:
        return None
    for path in paths:
        node = element.find(path)
        if node is not None and node.text is not None and str(node.text).strip():
            return str(node.text).strip()
    return None


def _extract_error(root: ET.Element) -> str:
    parts: List[str] = []
    for node in root.findall(".//errormessage/error"):
        for key in ("errorno", "description", "description2", "correction"):
            text = _first_text(node, key)
            if text:
                parts.append(text)
    if not parts:
        parts.append(_first_text(root, ".//result/status") or "intacct_request_failed")
    return "; ".join(parts)[:500]


def _result(root: ET.Element) -> Optional[ET.Element]:
    found = root.find(".//operation/result")
    if found is not None:
        return found
    return root.find(".//result")


async def _post_function(connection: Any, function_payload: ET.Element) -> Dict[str, Any]:
    if not _credentials_complete(connection):
        return {
            "ok": False,
            "reason": "sage_intacct_not_configured",
            "detail": "missing_sender_or_company_user_credentials",
        }

    xml_body = _build_envelope(connection, function_payload)
    client = get_http_client()
    response = await client.post(
        _base_url(connection),
        content=xml_body,
        headers={
            "Content-Type": "application/xml",
            "Accept": "application/xml",
        },
        timeout=_ERP_TIMEOUT,
    )
    if response.status_code == 401:
        return {
            "ok": False,
            "reason": "sage_intacct_auth_failed",
            "detail": "http_401",
        }
    if response.status_code >= 400:
        return {
            "ok": False,
            "reason": f"http_{response.status_code}",
            "detail": f"http_{response.status_code}",
        }
    try:
        root = ET.fromstring(response.text or "")
    except ET.ParseError:
        return {
            "ok": False,
            "reason": "sage_intacct_non_xml_response",
            "detail": "non_xml_response",
        }

    result = _result(root)
    status = (_first_text(result, "status") or _first_text(root, ".//status") or "").lower()
    if status and status != "success":
        return {
            "ok": False,
            "reason": "sage_intacct_request_failed",
            "detail": _extract_error(root),
            "root": root,
            "result": result,
        }
    return {"ok": True, "root": root, "result": result}


def _read_by_query(object_name: str, fields: str, query: str, *, pagesize: int = 100) -> ET.Element:
    payload = ET.Element("readByQuery")
    ET.SubElement(payload, "object").text = object_name
    ET.SubElement(payload, "fields").text = fields
    ET.SubElement(payload, "query").text = query
    ET.SubElement(payload, "pagesize").text = str(pagesize)
    return payload


def _record_nodes(result: Optional[ET.Element]) -> List[ET.Element]:
    if result is None:
        return []
    data = result.find("data")
    if data is None:
        return []
    return [node for node in list(data) if isinstance(node.tag, str)]


def _record_text(record: Optional[ET.Element], *names: str) -> Optional[str]:
    if record is None:
        return None
    for name in names:
        for candidate in (name, name.upper(), name.lower()):
            text = _first_text(record, candidate)
            if text:
                return text
    return None


def _record_float(record: Optional[ET.Element], *names: str) -> Optional[float]:
    text = _record_text(record, *names)
    if text is None:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _record_dict(record: Optional[ET.Element]) -> Dict[str, Any]:
    if record is None:
        return {}
    return {
        str(child.tag): child.text
        for child in list(record)
        if isinstance(child.tag, str)
    }


def _append_solden_note(description: Optional[str], solden_url: Optional[str]) -> str:
    parts = [str(description or "").strip()]
    if solden_url:
        parts.append(f"Solden: {solden_url}")
    note = " | ".join(part for part in parts if part)
    return note[:1000]


def _line_amount(item: Dict[str, Any], fallback: float) -> float:
    if item.get("amount") is not None:
        return money_to_float(item.get("amount"))
    quantity = money_to_float(item.get("quantity", 1) or 1)
    unit = money_to_float(item.get("unit_amount", fallback) or fallback)
    return money_to_float(quantity * unit)


async def post_to_sage_intacct(connection: Any, entry: Dict[str, Any]) -> Dict[str, Any]:
    """Journal-entry writes are intentionally not enabled before sandbox proof."""
    return {
        "status": "skipped",
        "erp": "sage_intacct",
        "reason": "journal_entry_write_not_enabled_for_sage_intacct",
    }


async def post_bill_to_sage_intacct(
    connection: Any,
    bill: Any,
    gl_map: Optional[Dict[str, str]] = None,
    field_mappings: Optional[Dict[str, str]] = None,
    custom_fields: Optional[Dict[str, str]] = None,
    idempotency_key: Optional[str] = None,
    organization_id: Optional[str] = None,
    ap_item_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Post a vendor bill to Sage Intacct as an APBILL."""
    from solden.integrations.erp_router import get_account_code, _dimension_field_name

    if not _credentials_complete(connection):
        return {
            "status": "error",
            "erp": "sage_intacct",
            "reason": "sage_intacct_not_configured",
        }
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
            "erp": "sage_intacct",
            "reason": "sage_intacct_validation_failed",
            "missing_fields": missing_fields,
        }

    solden_record_url = build_solden_ap_record_url(ap_item_id)
    if idempotency_key and getattr(bill, "invoice_number", None):
        try:
            existing_bill = await find_bill_sage_intacct(
                connection, str(bill.invoice_number),
            )
        except Exception as exc:
            logger.debug(
                "[sage_intacct] find_bill pre-check failed vendor=%s invoice=%s: %s",
                getattr(bill, "vendor_name", None),
                bill.invoice_number,
                exc,
            )
            existing_bill = None
        if existing_bill and existing_bill.get("bill_id"):
            result = {
                "status": "already_posted",
                "erp": "sage_intacct",
                "bill_id": existing_bill.get("bill_id"),
                "doc_number": existing_bill.get("doc_number"),
                "amount": existing_bill.get("amount"),
                "idempotency_key": idempotency_key,
            }
            if solden_record_url:
                result["solden_record_url"] = solden_record_url
            return result

    expense_account = get_account_code("sage_intacct", "expenses", gl_map)
    fm = field_mappings or {}

    create = ET.Element("create")
    apbill = ET.SubElement(create, "APBILL")
    _append_text(apbill, "VENDORID", getattr(bill, "vendor_id", None))
    _append_text(apbill, "RECORDID", getattr(bill, "invoice_number", None))
    _append_text(apbill, "DOCNUMBER", getattr(bill, "po_number", None))
    _append_text(
        apbill,
        "DESCRIPTION",
        _append_solden_note(
            getattr(bill, "description", None)
            or f"Invoice from {getattr(bill, 'vendor_name', '')}",
            solden_record_url,
        ),
    )
    _date_element(apbill, "WHENCREATED", getattr(bill, "invoice_date", None))
    _date_element(apbill, "WHENPOSTED", getattr(bill, "invoice_date", None))
    if getattr(bill, "due_date", None):
        _date_element(apbill, "WHENDUE", getattr(bill, "due_date", None))
    _append_text(apbill, "ACTION", "Submit")
    bill_currency = str(getattr(bill, "currency", "") or "").strip().upper()
    if len(bill_currency) == 3:
        _append_text(apbill, "CURRENCY", bill_currency)
    if getattr(bill, "payment_terms", None):
        _append_text(apbill, "TERMNAME", getattr(bill, "payment_terms", None))

    if custom_fields:
        for erp_field_id, value in custom_fields.items():
            field_name = _safe_xml_field(erp_field_id)
            if field_name and value is not None:
                _append_text(apbill, field_name, value)

    items = ET.SubElement(apbill, "APBILLITEMS")
    line_items = getattr(bill, "line_items", None) or [
        {
            "description": getattr(bill, "description", None)
            or f"Invoice {getattr(bill, 'invoice_number', '')}",
            "amount": getattr(bill, "amount", 0),
        }
    ]

    dim_fields = (
        ("department_field", "DEPARTMENTID", "department"),
        ("location_field", "LOCATIONID", "location"),
        ("project_field", "PROJECTID", "project"),
        ("class_field", "CLASSID", "class"),
        ("cost_center_field", "COSTCENTERID", "cost_center"),
    )
    for item in line_items:
        line = ET.SubElement(items, "APBILLITEM")
        account = (
            item.get("account_no")
            or item.get("account_code")
            or item.get("gl_code")
            or item.get("account_id")
            or expense_account
        )
        _append_text(line, "ACCOUNTNO", account)
        _append_text(line, "TRX_AMOUNT", str(_line_amount(item, getattr(bill, "amount", 0))))
        _append_text(line, "ENTRYDESCRIPTION", item.get("description") or getattr(bill, "description", None))
        for catalog_key, default_field, source_key in dim_fields:
            dim_value = item.get(source_key) or item.get(default_field)
            if not dim_value:
                continue
            field_name = _dimension_field_name(fm, catalog_key, default_field)
            if _safe_xml_field(field_name):
                _append_text(line, field_name, dim_value)

    outcome = await _post_function(connection, create)
    if not outcome.get("ok"):
        return {
            "status": "error",
            "erp": "sage_intacct",
            "reason": outcome.get("reason") or "sage_intacct_bill_post_failed",
            "erp_error_detail": outcome.get("detail"),
        }

    record = (_record_nodes(outcome.get("result")) or [None])[0]
    bill_id = (
        _record_text(record, "RECORDNO")
        or _record_text(record, "RECORDID")
        or getattr(bill, "invoice_number", None)
    )
    result_payload: Dict[str, Any] = {
        "status": "success",
        "erp": "sage_intacct",
        "bill_id": bill_id,
        "doc_number": _record_text(record, "RECORDID") or getattr(bill, "invoice_number", None),
        "erp_journal_entry_id": str(bill_id) if bill_id is not None else None,
    }
    if solden_record_url:
        result_payload["solden_record_url"] = solden_record_url
    return result_payload


async def find_bill_sage_intacct(connection: Any, invoice_number: str) -> Optional[Dict[str, Any]]:
    value = _safe_query_value(invoice_number)
    if not value:
        return None
    outcome = await _post_function(
        connection,
        _read_by_query(
            "APBILL",
            "RECORDNO,RECORDID,DOCNUMBER,TOTALENTERED,TOTALDUE,STATE",
            f"RECORDID = '{value}'",
            pagesize=1,
        ),
    )
    if not outcome.get("ok"):
        return None
    record = (_record_nodes(outcome.get("result")) or [None])[0]
    if record is None:
        return None
    return {
        "bill_id": _record_text(record, "RECORDNO") or _record_text(record, "RECORDID"),
        "doc_number": _record_text(record, "RECORDID") or _record_text(record, "DOCNUMBER"),
        "amount": _record_float(record, "TOTALENTERED", "TOTALDUE"),
        "state": _record_text(record, "STATE"),
    }


async def find_vendor_sage_intacct(
    connection: Any,
    name: Optional[str] = None,
    email: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    query = None
    value = _safe_query_value(name)
    if value:
        query = f"NAME = '{value}'"
    if query is None:
        value = _safe_query_value(email)
        if value:
            query = f"EMAIL1 = '{value}'"
    if query is None:
        return None
    outcome = await _post_function(
        connection,
        _read_by_query("VENDOR", "VENDORID,NAME,EMAIL1,STATUS", query, pagesize=1),
    )
    if not outcome.get("ok"):
        return None
    record = (_record_nodes(outcome.get("result")) or [None])[0]
    if record is None:
        return None
    return {
        "vendor_id": _record_text(record, "VENDORID"),
        "name": _record_text(record, "NAME"),
        "email": _record_text(record, "EMAIL1"),
        "active": str(_record_text(record, "STATUS") or "").lower() != "inactive",
    }


def _vendor_id_from_name(name: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "_", str(name or "").upper()).strip("_")
    return (token or f"SOLDEN_{uuid.uuid4().hex[:8].upper()}")[:30]


async def create_vendor_sage_intacct(connection: Any, vendor: Any) -> Dict[str, Any]:
    if not _credentials_complete(connection):
        return {"status": "error", "erp": "sage_intacct", "reason": "sage_intacct_not_configured"}
    name = str(getattr(vendor, "name", "") or "").strip()
    if not name:
        return {"status": "error", "erp": "sage_intacct", "reason": "missing_vendor_name"}
    vendor_id = _vendor_id_from_name(name)
    create = ET.Element("create")
    node = ET.SubElement(create, "VENDOR")
    _append_text(node, "VENDORID", vendor_id)
    _append_text(node, "NAME", name)
    _append_text(node, "EMAIL1", getattr(vendor, "email", None))
    _append_text(node, "PHONE1", getattr(vendor, "phone", None))
    _append_text(node, "TAXID", getattr(vendor, "tax_id", None))
    outcome = await _post_function(connection, create)
    if not outcome.get("ok"):
        return {
            "status": "error",
            "erp": "sage_intacct",
            "reason": outcome.get("reason") or "sage_intacct_vendor_create_failed",
            "erp_error_detail": outcome.get("detail"),
        }
    record = (_record_nodes(outcome.get("result")) or [None])[0]
    return {
        "status": "success",
        "erp": "sage_intacct",
        "vendor_id": _record_text(record, "VENDORID") or vendor_id,
        "name": name,
    }


async def get_chart_of_accounts_sage_intacct(connection: Any) -> List[Dict[str, Any]]:
    outcome = await _post_function(
        connection,
        _read_by_query(
            "GLACCOUNT",
            "ACCOUNTNO,TITLE,ACCOUNTTYPE,NORMALBALANCE,STATUS",
            "STATUS != 'inactive'",
            pagesize=1000,
        ),
    )
    if not outcome.get("ok"):
        return []
    accounts: List[Dict[str, Any]] = []
    for record in _record_nodes(outcome.get("result")):
        code = _record_text(record, "ACCOUNTNO")
        accounts.append({
            "id": code,
            "code": code,
            "name": _record_text(record, "TITLE") or code,
            "type": _record_text(record, "ACCOUNTTYPE"),
            "normal_balance": _record_text(record, "NORMALBALANCE"),
            "active": str(_record_text(record, "STATUS") or "").lower() != "inactive",
            "raw": _record_dict(record),
        })
    return accounts


async def test_connection_sage_intacct(connection: Any) -> Dict[str, Any]:
    """Run a cheap read-only Sage Intacct test query."""
    outcome = await _post_function(
        connection,
        _read_by_query("GLACCOUNT", "ACCOUNTNO,TITLE", "STATUS != 'inactive'", pagesize=1),
    )
    if not outcome.get("ok"):
        return {
            "ok": False,
            "detail": outcome.get("reason") or "sage_intacct_test_failed",
        }
    records = _record_nodes(outcome.get("result"))
    first = records[0] if records else None
    return {
        "ok": True,
        "response_summary": {
            "account_seen": _record_text(first, "ACCOUNTNO"),
            "company_id": _first_attr(connection, "company_id"),
        },
    }


async def list_all_vendors_sage_intacct(connection: Any) -> List[Dict[str, Any]]:
    outcome = await _post_function(
        connection,
        _read_by_query("VENDOR", "VENDORID,NAME,EMAIL1,STATUS", "STATUS != 'inactive'", pagesize=1000),
    )
    if not outcome.get("ok"):
        return []
    vendors: List[Dict[str, Any]] = []
    for record in _record_nodes(outcome.get("result")):
        vendors.append({
            "vendor_id": _record_text(record, "VENDORID"),
            "name": _record_text(record, "NAME"),
            "email": _record_text(record, "EMAIL1"),
            "active": str(_record_text(record, "STATUS") or "").lower() != "inactive",
            "erp_type": "sage_intacct",
        })
    return vendors


async def get_payment_status_sage_intacct(connection: Any, erp_reference: str) -> Dict[str, Any]:
    ref = _safe_query_value(erp_reference)
    if not ref:
        return {"paid": False, "reason": "invalid_bill_reference"}
    outcome = await _post_function(
        connection,
        _read_by_query(
            "APBILL",
            "RECORDNO,RECORDID,STATE,TOTALENTERED,TOTALPAID,TOTALDUE",
            f"RECORDNO = '{ref}' OR RECORDID = '{ref}'",
            pagesize=1,
        ),
    )
    if not outcome.get("ok"):
        return {"paid": False, "reason": outcome.get("reason") or "lookup_failed"}
    record = (_record_nodes(outcome.get("result")) or [None])[0]
    if record is None:
        return {"paid": False, "reason": "not_found"}
    total = _record_float(record, "TOTALENTERED") or 0.0
    paid_amount = _record_float(record, "TOTALPAID") or 0.0
    remaining = _record_float(record, "TOTALDUE")
    if remaining is None:
        remaining = max(total - paid_amount, 0.0)
    state = str(_record_text(record, "STATE") or "").lower()
    return {
        "paid": paid_amount > 0 and remaining <= 0.01,
        "partial": paid_amount > 0 and remaining > 0.01,
        "payment_amount": paid_amount,
        "remaining_balance": remaining,
        "status": state or None,
        "payment_reference": _record_text(record, "RECORDNO"),
    }
