from __future__ import annotations

import base64
import hashlib
import hmac
import json

from solden.api.netsuite_panel import _build_operational_memory, _verify_panel_jwt
from solden.services.erp_payment_dispatcher import parse_netsuite_payment_payload


SUITEAPP_ROOT = "integrations/netsuite-suiteapp/src"


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _signed_panel_token(secret: str, *, issuer: str, audience: str, alg: str = "HS256") -> str:
    def b64url(payload: bytes) -> str:
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    header = {"alg": alg, "typ": "JWT"}
    body = {
        "iss": issuer,
        "aud": audience,
        "accountId": "TSTACCT123",
        "billId": "9001",
        "iat": 1,
        "exp": 4102444800,
    }
    signing_input = ".".join(
        (
            b64url(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            b64url(json.dumps(body, separators=(",", ":")).encode("utf-8")),
        )
    )
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return signing_input + "." + b64url(signature)


def test_suitelet_mints_hmac_jwt_from_tenant_settings():
    source = _read(
        f"{SUITEAPP_ROOT}/FileCabinet/SuiteApps/com.clearledgr.suiteapp/sl_clearledgr_panel.js"
    )

    assert "DEMO_PHASE_2" not in source
    assert "N/crypto" in source
    assert "customrecord_cl_settings" in source
    assert "mintPanelJwt" in source
    assert "JWT_TTL_SECONDS = 15 * 60" in source
    assert "cryptoMod.createHmac" in source
    assert "cl-token" in source


def test_user_event_signs_webhooks_with_netsuite_secret_key_only():
    source = _read(
        f"{SUITEAPP_ROOT}/FileCabinet/SuiteApps/com.clearledgr.suiteapp/ue_clearledgr_panel.js"
    )

    assert "DEMO_PHASE_2" not in source
    assert "createSecretKey(secretRef)" in source
    assert "cryptoMod.createHmac" in source
    assert "cryptoMod.createHash" not in source
    assert "fallbackHexHmacSha256" not in source


def test_backend_panel_jwt_requires_expected_issuer_audience_and_alg():
    secret = "panel-secret"
    valid = _signed_panel_token(
        secret,
        issuer="solden-netsuite-suiteapp",
        audience="solden-netsuite-panel",
    )
    assert _verify_panel_jwt(valid, secret)

    wrong_audience = _signed_panel_token(
        secret,
        issuer="solden-netsuite-suiteapp",
        audience="wrong-audience",
    )
    assert _verify_panel_jwt(wrong_audience, secret) is None

    wrong_issuer = _signed_panel_token(
        secret,
        issuer="wrong-issuer",
        audience="solden-netsuite-panel",
    )
    assert _verify_panel_jwt(wrong_issuer, secret) is None

    wrong_alg = _signed_panel_token(
        secret,
        issuer="solden-netsuite-suiteapp",
        audience="solden-netsuite-panel",
        alg="HS512",
    )
    assert _verify_panel_jwt(wrong_alg, secret) is None


def test_netsuite_panel_renders_current_work_memory_fields():
    html = _read(
        f"{SUITEAPP_ROOT}/FileCabinet/SuiteApps/com.clearledgr.suiteapp/ui/panel.html"
    )
    js = _read(
        f"{SUITEAPP_ROOT}/FileCabinet/SuiteApps/com.clearledgr.suiteapp/ui/panel.js"
    )

    for dom_id in (
        "cl-memory",
        "cl-owner",
        "cl-waiting-on",
        "cl-waiting-reason",
        "cl-next-step",
    ):
        assert dom_id in html
    assert "renderMemory(data.memory" in js
    assert "/accounts-payable/" in js
    assert "app.soldenai.com/ap-items" not in js


def test_netsuite_panel_memory_names_owner_waiting_reason_and_next_step():
    memory = _build_operational_memory(
        item={
            "state": "needs_approval",
            "owner_email": "controller@example.com",
            "owner_source": "auto",
            "exception_code": "po_match_required",
        },
        timeline=[
            {
                "event_type": "state_transition",
                "summary": "Validated",
                "created_at": "2026-06-03T09:00:00Z",
            },
            {
                "event_type": "state_transition",
                "summary": "Routed for approval",
                "created_at": "2026-06-03T10:00:00Z",
            }
        ],
        exceptions=[],
        outcome=None,
    )

    assert memory["owner"]["email"] == "controller@example.com"
    assert memory["waiting_on"] == "controller@example.com"
    assert memory["waiting_reason"] == "Po match required"
    assert "approve" in memory["next_step"].lower()
    assert memory["last_event"]["summary"] == "Routed for approval"


def test_netsuite_bill_paid_summary_payload_emits_payment_event():
    payload = {
        "event_type": "vendorbill.paid",
        "occurred_at": "2026-06-03T11:00:00Z",
        "bill": {
            "ns_internal_id": "9001",
            "transaction_number": "VBILL-9001",
            "tran_id": "INV-9001",
            "amount": "1500.25",
            "currency": "USD",
            "status_label": "Paid In Full",
        },
    }

    events = parse_netsuite_payment_payload(json.dumps(payload).encode("utf-8"))

    assert len(events) == 1
    event = events[0]
    assert event.source == "netsuite"
    assert event.erp_bill_reference == "9001"
    assert event.payment_id == "ns-bill-9001-paid"
    assert event.status == "confirmed"
    assert event.amount == 1500.25
    assert event.currency == "USD"
    assert event.payment_reference == "VBILL-9001"
